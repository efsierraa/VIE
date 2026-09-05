"""Robustez ante errores 500: validaciones de longitud (Postgres las exige,
SQLite no — sin ellas el error era un 500 ciego) y handler global que devuelve
JSON con traza en el log en vez de HTML que rompe el .json() del cliente."""
import asyncio
import json

from conftest import login
from fastapi import Request

from app.main import error_interno


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
