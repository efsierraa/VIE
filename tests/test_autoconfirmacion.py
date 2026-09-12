"""Autoconfirmación de paquetes (30 días), recordatorio en tiempo real del
residente e inspección admin de entregados sin confirmar.
Regla en docs/paquetes-confirmacion.md."""
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import login

from app.database import SessionLocal
from app.models import Package, User
from app.routers import api
from app.utils import utcnow


@pytest.fixture(autouse=True)
def _limpiar_huellas():
    """La BD de pruebas es compartida: borra lo creado aquí para no contaminar
    a los archivos que corren después (pendientes de residente1, etc.)."""
    yield
    with SessionLocal() as db:
        db.query(Package).filter(
            Package.short_code.like("AUT%") | Package.short_code.like("WKL%") | Package.short_code.like("INS%")
        ).delete(synchronize_session=False)
        db.query(User).filter(User.username.like("wklres%")).delete(synchronize_session=False)
        db.commit()


def _paquete(residente_id: int, status: str, dias_hace: int, codigo: str) -> Package:
    with SessionLocal() as db:
        p = Package(
            uuid=str(uuid4()),
            short_code=codigo,
            resident_id=residente_id,
            description=f"prueba {codigo}",
            status=status,
            delivered_at=utcnow() - timedelta(days=dias_hace) if status in ("entregado", "disputa", "confirmado") else None,
            tower="1",
            apartment="101",
        )
        db.add(p)
        db.commit()
        return p.id


def _residente_fresco(client, username: str) -> int:
    """Residente sin paquetes previos: el weeksletter queda determinístico."""
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Prueba", "apellidos": "Semanal", "username": username, "password": "clave12345", "role": "residente", "tower": "8", "apartment": "801"},
    )
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        return db.query(User).filter(User.username == username).first().id


def test_autoconfirmacion_a_30_dias(client):
    with SessionLocal() as db:
        r1 = db.query(User).filter(User.username == "residente1").first()
        viejo = _paquete(r1.id, "entregado", 31, "AUT1A")
        fresco = _paquete(r1.id, "entregado", 29, "AUT2B")
        disputado = _paquete(r1.id, "disputa", 40, "AUT3C")
        porteria = _paquete(r1.id, "en_porteria", 40, "AUT4D")

        api.autoconfirmar_paquetes(db)

        p_viejo = db.query(Package).filter(Package.id == viejo).first()
        assert p_viejo.status == "confirmado"
        assert p_viejo.confirmed_at is not None
        assert db.query(Package).filter(Package.id == fresco).first().status == "entregado"
        assert db.query(Package).filter(Package.id == disputado).first().status == "disputa"
        assert db.query(Package).filter(Package.id == porteria).first().status == "en_porteria"


def test_recordatorio_tiempo_real(client):
    """El banner se calcula al cargar: sin tabla de avisos ni horarios."""
    uid = _residente_fresco(client, "wklres1")
    # sin entregados: sin aviso
    with SessionLocal() as db:
        assert api.texto_recordatorio_paquetes(db, uid) is None
    login(client, "wklres1", password="clave12345")
    assert "Recordatorio" not in client.get("/residente").text

    _paquete(uid, "entregado", 10, "WKL1A")  # 30 - 10 = 20 días restantes
    _paquete(uid, "entregado", 25, "WKL2B")  # el más antiguo manda: 5 días restantes
    with SessionLocal() as db:
        texto = api.texto_recordatorio_paquetes(db, uid)
        assert texto is not None
        assert "2 paquetes entregados sin confirmar" in texto
        assert "Quedan 5 días" in texto
        assert "automáticamente" in texto
    page = client.get("/residente").text
    assert "Recordatorio" in page
    assert "2 paquetes entregados sin confirmar" in page
    assert "Quedan 5 días" in page

    # al confirmar el último, el aviso desaparece en la próxima carga
    with SessionLocal() as db:
        for p in db.query(Package).filter(Package.resident_id == uid, Package.status == "entregado").all():
            p.status = "confirmado"
            p.confirmed_at = utcnow()
        db.commit()
    assert "Recordatorio" not in client.get("/residente").text


def test_admin_inspecciona_entregados_sin_confirmar(client):
    with SessionLocal() as db:
        r1 = db.query(User).filter(User.username == "residente1").first()
        _paquete(r1.id, "entregado", 15, "INS1D")
        esperados = db.query(Package).filter(Package.status == "entregado").count()

    login(client, "admin1")
    page = client.get("/admin").text
    assert f"<strong>{esperados}</strong><span>entregados sin confirmar</span>" in page

    page = client.get("/admin/historial?tipo=paquetes&estado=entregado").text
    assert "INS1D" in page
    assert "15 días sin confirmar (auto a 30)" in page
