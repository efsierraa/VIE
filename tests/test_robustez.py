"""Robustez ante errores 500: validaciones de longitud (Postgres las exige,
SQLite no — sin ellas el error era un 500 ciego), handler global que devuelve
JSON con traza en el log en vez de HTML que rompe el .json() del cliente, y
migración que relaja la columna legado full_name (NOT NULL en la BD vieja)."""
import asyncio
import json
from unittest.mock import MagicMock

from conftest import login
from fastapi import Request

import app.main as main
from app.database import SessionLocal
from app.main import error_interno
from app.models import User


def test_crear_cuenta_con_campos_largos_da_400_no_500(client):
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Ok", "apellidos": "Ok", "username": "u" * 51, "password": "clave12345", "role": "guarda"},
    )
    assert r.status_code == 400
    assert "largos" in r.json()["detail"]

    r = client.post(
        "/api/users",
        json={"nombres": "Ok", "apellidos": "Ok", "username": "torrelarga", "password": "clave12345", "role": "residente", "tower": "T" * 11, "apartment": "101"},
    )
    assert r.status_code == 400
    assert "Torre" in r.json()["detail"]


def test_editar_cuenta_con_datos_largos_da_400_no_500(client):
    login(client, "admin1")
    r = client.patch(
        "/api/users/1/editar",
        json={"nombres": "Administración", "apellidos": "General", "tower": "", "apartment": "A" * 11},
    )
    assert r.status_code == 400
    assert "largos" in r.json()["detail"]


def test_handler_global_devuelve_json_500():
    scope = {
        "type": "http",
        "method": "PATCH",
        "path": "/api/users/1/editar",
        "headers": [(b"x-request-id", b"abc123")],
        "client": ("127.0.0.1", 5000),
    }
    respuesta = asyncio.run(error_interno(Request(scope), ValueError("boom")))
    assert respuesta.status_code == 500
    assert respuesta.headers["content-type"] == "application/json"
    assert json.loads(respuesta.body) == {"detail": "Error interno del servidor"}


def test_crear_cuenta_sin_columna_legado_full_name(client):
    """Crear cuenta no debe depender de full_name (legado): en producción
    Postgres quedó NOT NULL y cada 'Crear cuenta' terminaba en 500."""
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={
            "nombres": "Elena",
            "apellidos": "Oyola",
            "username": "eoyola",
            "password": "clave12345",
            "role": "guarda",
            "celular": "573203912140",
        },
    )
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == "eoyola").first()
        assert u is not None
        assert u.nombres == "Elena"
        assert u.apellidos == "Oyola"
        assert u.full_name is None


def _engine_falso(dialecto: str, nullable: bool) -> MagicMock:
    eng = MagicMock()
    eng.dialect.name = dialecto
    inspector = MagicMock()
    inspector.get_columns.return_value = [{"name": "full_name", "nullable": nullable}]
    return eng, inspector


def test_migracion_relaja_full_name_not_null(monkeypatch):
    eng, inspector = _engine_falso("postgresql", nullable=False)
    monkeypatch.setattr(main, "inspect", lambda _: inspector)
    assert main._relajar_full_name_legado(eng) is True
    conn = eng.begin.return_value.__enter__.return_value
    assert "ALTER TABLE users ALTER COLUMN full_name DROP NOT NULL" in conn.exec_driver_sql.call_args[0][0]


def test_migracion_full_name_intacta_si_ya_es_nullable(monkeypatch):
    for dialecto, nullable in (("postgresql", True), ("sqlite", False), ("sqlite", True)):
        eng, inspector = _engine_falso(dialecto, nullable)
        monkeypatch.setattr(main, "inspect", lambda _: inspector)
        assert main._relajar_full_name_legado(eng) is False
        eng.begin.assert_not_called()
