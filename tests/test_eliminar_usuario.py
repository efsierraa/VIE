"""Administración borra cuentas sin historial; si tienen historial (visitas,
paquetes o control de ediciones que las referencian por FK) el borrado se
rechaza y se sugiere desactivarlas para preservar la auditoría."""
from datetime import timedelta
from uuid import uuid4

from conftest import login

from app.database import SessionLocal
from app.models import EditLog, Package, User, Visit
from app.utils import utcnow


def _id_de(username: str) -> int:
    with SessionLocal() as db:
        return db.query(User).filter(User.username == username).first().id


def _crear_cuenta(client, username: str, role: str) -> int:
    data = {"nombres": "Prueba", "apellidos": "Borrar", "username": username, "password": "clave12345", "role": role}
    if role == "residente":
        data["tower"] = "9"
        data["apartment"] = "901"
    r = client.post("/api/users", json=data)
    assert r.status_code == 200, r.text
    return _id_de(username)


def test_borra_cuenta_sin_historial(client):
    login(client, "admin1")
    uid = _crear_cuenta(client, "borraok", "guarda")
    r = client.delete(f"/api/users/{uid}")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    with SessionLocal() as db:
        assert db.query(User).filter(User.id == uid).first() is None


def test_rechaza_residente_con_visitas(client):
    login(client, "admin1")
    uid = _crear_cuenta(client, "borravisita", "residente")
    with SessionLocal() as db:
        db.add(
            Visit(
                uuid=str(uuid4()),
                visitor_name="Visita Prueba",
                subject="Entrega",
                visitor_role="visitante",
                resident_id=uid,
                tower="9",
                apartment="901",
                status="finalizada",
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        db.commit()
    r = client.delete(f"/api/users/{uid}")
    assert r.status_code == 400
    assert "visitas" in r.json()["detail"]
    assert "desact" in r.json()["detail"]


def test_rechaza_guarda_con_entradas_registradas(client):
    login(client, "admin1")
    uid = _crear_cuenta(client, "borraentrada", "guarda")
    with SessionLocal() as db:
        r1 = db.query(User).filter(User.username == "residente1").first()
        db.add(
            Visit(
                uuid=str(uuid4()),
                visitor_name="Visita Entrada",
                subject="Domicilio",
                visitor_role="domiciliario",
                resident_id=r1.id,
                tower="1",
                apartment="101",
                status="dentro",
                entry_guard_id=uid,
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        db.commit()
    r = client.delete(f"/api/users/{uid}")
    assert r.status_code == 400
    assert "visitas" in r.json()["detail"]


def test_rechaza_residente_con_paquetes(client):
    login(client, "admin1")
    uid = _crear_cuenta(client, "borrapaquete", "residente")
    with SessionLocal() as db:
        db.add(Package(uuid=str(uuid4()), resident_id=uid, description="Caja"))
        db.commit()
    r = client.delete(f"/api/users/{uid}")
    assert r.status_code == 400
    assert "paquetes" in r.json()["detail"]


def test_rechaza_guarda_con_ediciones_registradas(client):
    login(client, "admin1")
    uid = _crear_cuenta(client, "borraedicion", "guarda")
    with SessionLocal() as db:
        db.add(
            EditLog(
                entity_type="visita",
                entity_uuid=str(uuid4()),
                editor_id=uid,
                cambios="asunto: 'x' → 'y'",
            )
        )
        db.commit()
    r = client.delete(f"/api/users/{uid}")
    assert r.status_code == 400
    assert "ediciones" in r.json()["detail"]


def test_no_borra_su_propia_cuenta(client):
    login(client, "admin1")
    r = client.delete(f"/api/users/{_id_de('admin1')}")
    assert r.status_code == 400
    assert "propia" in r.json()["detail"]


def test_rechaza_usuario_inexistente(client):
    login(client, "admin1")
    r = client.delete("/api/users/999999")
    assert r.status_code == 404


def test_solo_admin_puede_borrar(client):
    uid = _id_de("guarda1")
    for credenciales in ("guarda1", "residente1"):
        login(client, credenciales)
        r = client.delete(f"/api/users/{uid}")
        assert r.status_code == 403
