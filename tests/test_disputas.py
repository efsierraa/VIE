"""Resolución de disputas a dos partes: portería (guarda o admin) y residente
deben aceptar; cuando ambos confirman, el paquete queda como recibido."""
from conftest import login

from app.database import SessionLocal
from app.models import EditLog, Package
from app.utils import utcnow

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _paquete_en_disputa(client) -> dict:
    """Paquete entregado y luego marcado 'No lo recibí' por el residente."""
    from app.models import User
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    db.close()
    login(client, "guarda1")
    r = client.post(
        "/api/packages",
        json={"resident_id": rid, "description": "paquete en disputa", "photo_b64": FOTO},
    )
    pkg = r.json()["package"]
    r = client.post(f"/api/packages/{pkg['uuid']}/entregar", json={"cedula": "987654321"})
    assert r.status_code == 200
    login(client, "residente1")
    r = client.post(f"/api/packages/{pkg['uuid']}/disputar")
    assert r.status_code == 200
    return r.json()["package"]


def test_resolucion_a_dos_partes_guarda_y_residente(client):
    pkg = _paquete_en_disputa(client)

    # la portería acepta primero: la disputa sigue abierta
    login(client, "guarda1")
    r = client.post(f"/api/packages/{pkg['uuid']}/resolver")
    assert r.status_code == 200
    assert r.json()["resuelta"] is False
    assert r.json()["package"]["status"] == "disputa"
    assert r.json()["package"]["resuelta_porteria"] is True

    # doble confirmación del mismo lado no procede
    r = client.post(f"/api/packages/{pkg['uuid']}/resolver")
    assert r.status_code == 400

    # el residente acepta: ambas partes → confirmado
    login(client, "residente1")
    r = client.post(f"/api/packages/{pkg['uuid']}/resolver")
    assert r.status_code == 200
    assert r.json()["resuelta"] is True
    p = r.json()["package"]
    assert p["status"] == "confirmado"
    assert p["resuelta_residente"] is True
    assert p["resuelta_at"]


def test_resolucion_admin_y_residente(client):
    pkg = _paquete_en_disputa(client)

    # el residente acepta primero
    login(client, "residente1")
    r = client.post(f"/api/packages/{pkg['uuid']}/resolver")
    assert r.status_code == 200
    assert r.json()["resuelta"] is False

    # administración completa el acuerdo
    login(client, "admin1")
    r = client.post(f"/api/packages/{pkg['uuid']}/resolver")
    assert r.status_code == 200
    assert r.json()["resuelta"] is True
    assert r.json()["package"]["status"] == "confirmado"


def test_residente_ajeno_no_resuelve(client):
    pkg = _paquete_en_disputa(client)
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Resi Dos", "apellidos": "B", "username": "residenteB", "password": "clave123", "role": "residente", "tower": "2", "apartment": "202"},
    )
    assert r.status_code == 200
    login(client, "residenteB")
    r = client.post(f"/api/packages/{pkg['uuid']}/resolver")
    assert r.status_code == 403


def test_resolver_sin_disputa_rechazado(client):
    from app.models import User
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    db.close()
    login(client, "guarda1")
    r = client.post(
        "/api/packages",
        json={"resident_id": rid, "description": "sin disputa", "photo_b64": FOTO},
    )
    pkg = r.json()["package"]
    r = client.post(f"/api/packages/{pkg['uuid']}/resolver")
    assert r.status_code == 400
    assert "disputa" in r.json()["detail"]

    # limpiar: cancelar para no dejar pendientes en la BD compartida de la sesión
    client.post(f"/api/packages/{pkg['uuid']}/cancelar")


def test_resolucion_queda_en_control_de_ediciones(client):
    pkg = _paquete_en_disputa(client)
    login(client, "guarda1")
    client.post(f"/api/packages/{pkg['uuid']}/resolver")
    login(client, "residente1")
    client.post(f"/api/packages/{pkg['uuid']}/resolver")

    db = SessionLocal()
    edits = db.query(EditLog).filter(EditLog.entity_uuid == pkg["uuid"]).all()
    textos = " | ".join(e.cambios for e in edits)
    assert "portería (guarda1)" in textos
    assert "residente (residente1)" in textos
    db.close()


def test_botones_resolver_por_vista(client):
    pkg = _paquete_en_disputa(client)

    # el residente ve el botón y el estado del acuerdo
    login(client, "residente1")
    page = client.get("/residente")
    assert 'data-resolver="' in page.text
    assert "Resolver disputa" in page.text

    # el guarda la ve en entregados hoy (fue entregada hoy)
    login(client, "guarda1")
    page = client.get("/guarda/paquetes")
    assert 'data-resolver="' in page.text

    # el admin la ve en el historial de paquetes
    login(client, "admin1")
    page = client.get("/admin/historial?tipo=paquetes")
    assert 'data-resolver="' in page.text
