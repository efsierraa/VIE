import base64
from datetime import timedelta
from io import BytesIO

from conftest import login

from app.database import SessionLocal
from app.models import Package
from app.routers.api import limpiar_fotos_vencidas
from app.utils import utcnow

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _registrar_paquete(client):
    r = client.get("/api/residentes?q=Residenta")
    assert r.status_code == 200
    residentes = r.json()["residentes"]
    assert residentes
    rid = next(x["id"] for x in residentes if x["username"] == "residente1")
    r = client.post(
        "/api/packages",
        json={"resident_id": rid, "description": "caja de prueba", "photo_b64": FOTO},
    )
    assert r.status_code == 200, r.json()
    return r.json()["package"]


def test_flujo_completo_paquete(client):
    login(client, "guarda1")
    pkg = _registrar_paquete(client)
    assert pkg["status"] == "en_porteria"
    code = pkg["short_code"]
    assert len(code) == 6

    # el residente lo ve con foto y QR
    login(client, "residente1")
    r = client.get("/api/packages/mine")
    j = r.json()
    assert j["pendientes"] == 1
    mios = next(p for p in j["packages"] if p["uuid"] == pkg["uuid"])
    assert mios["photo_data_uri"].startswith("data:image/png;base64,")
    assert mios["qr_data_uri"].startswith("data:image/png;base64,")

    r = client.get(f"/api/packages/{pkg['uuid']}/pass")
    assert r.status_code == 200

    # el guarda escanea: ve la foto, aún no marca nada
    login(client, "guarda1")
    r = client.post("/api/packages/scan", json={"code": code.lower()})
    assert r.status_code == 200
    assert r.json()["package"]["photo_data_uri"].startswith("data:image/png;base64,")
    assert r.json()["package"]["status"] == "en_porteria"
    assert r.json()["residente"]["tower"] == "1"

    # entrega: el reloj de borrado de la foto arranca
    r = client.post(f"/api/packages/{pkg['uuid']}/entregar")
    assert r.status_code == 200
    assert r.json()["package"]["status"] == "entregado"
    assert r.json()["package"]["photo_delete_after"] is not None

    # el código ya no sirve
    r = client.post("/api/packages/scan", json={"code": code})
    assert r.status_code == 400

    # el residente confirma la recepción
    login(client, "residente1")
    r = client.post(f"/api/packages/{pkg['uuid']}/confirmar")
    assert r.status_code == 200
    assert r.json()["package"]["status"] == "confirmado"


def test_qr_de_paquete_y_de_visita_no_se_confunden(client):
    from app.security import sign_visit

    login(client, "guarda1")
    pkg = _registrar_paquete(client)
    token_visita = sign_visit(pkg["uuid"])  # sal equivocada a propósito
    r = client.post("/api/packages/scan", json={"token": token_visita})
    assert r.status_code == 400


def test_disputa(client):
    login(client, "guarda1")
    pkg = _registrar_paquete(client)
    client.post(f"/api/packages/{pkg['uuid']}/entregar")
    login(client, "residente1")
    r = client.post(f"/api/packages/{pkg['uuid']}/disputar")
    assert r.status_code == 200
    assert r.json()["package"]["status"] == "disputa"


def test_cancelar_borra_la_foto_de_inmediato(client):
    login(client, "guarda1")
    pkg = _registrar_paquete(client)
    r = client.post(f"/api/packages/{pkg['uuid']}/cancelar")
    assert r.status_code == 200
    assert r.json()["package"]["status"] == "cancelado"
    db = SessionLocal()
    p = db.query(Package).filter(Package.uuid == pkg["uuid"]).first()
    assert p.photo is None
    db.close()


def test_residente_no_registra_ni_escanea(client):
    login(client, "residente1")
    r = client.post("/api/packages", json={"resident_id": 1, "description": "x", "photo_b64": FOTO})
    assert r.status_code == 403
    r = client.post("/api/packages/scan", json={"code": "ABC123"})
    assert r.status_code == 403


def test_otro_residente_no_ve_pase_ajeno(client):
    login(client, "guarda1")
    pkg = _registrar_paquete(client)
    login(client, "residente2")
    r = client.get(f"/api/packages/{pkg['uuid']}/pass")
    assert r.status_code == 404


def test_limpieza_fotos_vencidas(client):
    login(client, "guarda1")
    pkg = _registrar_paquete(client)
    client.post(f"/api/packages/{pkg['uuid']}/entregar")

    # forzar el vencimiento del plazo
    db = SessionLocal()
    p = db.query(Package).filter(Package.uuid == pkg["uuid"]).first()
    assert p.photo is not None
    p.photo_delete_after = utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()

    db = SessionLocal()
    borradas = limpiar_fotos_vencidas(db)
    db.close()
    assert borradas >= 1

    # el registro queda, la foto se libera
    db = SessionLocal()
    p = db.query(Package).filter(Package.uuid == pkg["uuid"]).first()
    assert p.photo is None
    assert p.status == "entregado"
    db.close()


def test_export_incluye_hoja_paquetes(client):
    import openpyxl

    login(client, "guarda1")
    _registrar_paquete(client)
    login(client, "admin1")
    r = client.get("/admin/exportar")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.content))
    assert "Paquetes" in wb.sheetnames
    assert "Ingresos" in wb.sheetnames
