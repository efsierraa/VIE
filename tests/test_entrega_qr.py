"""Entrega de paquetes verificada por QR: el reclamo firmado queda como
metodo_entrega="qr" (exonera al celador ante disputa), el código digitado
queda como "codigo", y el guarda no puede generar el QR de paquetes de
residentes. Regla en docs/entrega-qr.md."""
import pytest
from conftest import login

from app.database import SessionLocal
from app.models import EditLog, Package, User
from app.security import sign_package


@pytest.fixture(autouse=True)
def _limpiar_huellas():
    """La BD de pruebas es compartida: borra lo creado aquí para no contaminar
    a los archivos que corren después."""
    yield
    with SessionLocal() as db:
        db.query(EditLog).filter(EditLog.entity_uuid.like("pkg-qr-%")).delete(synchronize_session=False)
        db.query(Package).filter(Package.uuid.like("pkg-qr-%")).delete(synchronize_session=False)
        db.query(User).filter(User.username.like("qrres%")).delete(synchronize_session=False)
        db.commit()


def _paquete_residente(client, codigo: str) -> tuple[str, str]:
    """Crea residente fresco + su paquete en portería. Devuelve (uuid, username)."""
    username = f"qrres{codigo.lower()}"
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Prueba", "apellidos": "Qr", "username": username, "password": "clave12345", "role": "residente", "tower": "8", "apartment": "802"},
    )
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        r1 = db.query(User).filter(User.username == username).first()
        p = Package(uuid=f"pkg-qr-{codigo}", short_code=codigo, resident_id=r1.id, description="caja qr", status="en_porteria", tower="8", apartment="802")
        db.add(p)
        db.commit()
        return p.uuid, username


def _paquete_tercero(client) -> str:
    login(client, "admin1")
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin1").first()
        p = Package(uuid="pkg-qr-tercero", resident_id=admin.id, nombre_tercero="Tercero Qr", tercero=True, tercero_nombres="Tercero", tercero_apellidos="Qr", description="caja tercero", status="en_porteria", tower="8", apartment="803")
        db.add(p)
        db.commit()
        return p.uuid


def test_entrega_con_qr_valido_registra_metodo(client):
    uuid, _ = _paquete_residente(client, "QRAA11")
    login(client, "guarda1")
    r = client.post(f"/api/packages/{uuid}/entregar", json={"token": sign_package(uuid)})
    assert r.status_code == 200, r.text
    assert r.json()["package"]["metodo_entrega"] == "qr"
    with SessionLocal() as db:
        p = db.query(Package).filter(Package.uuid == uuid).first()
        assert p.status == "entregado"
        assert p.metodo_entrega == "qr"


def test_entrega_con_qr_alterado_se_rechaza(client):
    uuid, _ = _paquete_residente(client, "QRAA22")
    login(client, "guarda1")
    r = client.post(f"/api/packages/{uuid}/entregar", json={"token": sign_package("otro-paquete") + "x"})
    assert r.status_code == 400
    with SessionLocal() as db:
        assert db.query(Package).filter(Package.uuid == uuid).first().status == "en_porteria"


def test_entrega_con_codigo_digitado_registra_metodo(client):
    uuid, _ = _paquete_residente(client, "QRAA33")
    login(client, "guarda1")
    r = client.post(f"/api/packages/{uuid}/entregar")
    assert r.status_code == 200, r.text
    assert r.json()["package"]["metodo_entrega"] == "codigo"


def test_disputa_con_qr_deja_nota_exoneratoria(client):
    uuid, usuario = _paquete_residente(client, "QRAA44")
    login(client, "guarda1")
    r = client.post(f"/api/packages/{uuid}/entregar", json={"token": sign_package(uuid)})
    assert r.status_code == 200, r.text
    # el residente disputa
    login(client, usuario, password="clave12345")
    r = client.post(f"/api/packages/{uuid}/disputar")
    assert r.status_code == 200, r.text
    # portería resuelve
    login(client, "guarda1")
    r = client.post(f"/api/packages/{uuid}/resolver")
    assert r.status_code == 200, r.text
    assert r.json()["exonera"] is True
    with SessionLocal() as db:
        edit = (
            db.query(EditLog)
            .filter(EditLog.entity_uuid == uuid, EditLog.entity_type == "paquete")
            .order_by(EditLog.id.desc())
            .first()
        )
        assert "entrega verificada por QR" in edit.cambios
        assert "(responsabilidad del residente)" in edit.cambios


def test_tercero_entregado_por_busqueda(client):
    uuid = _paquete_tercero(client)
    login(client, "guarda1")
    r = client.post(f"/api/packages/{uuid}/entregar", json={"cedula": "123456789"})
    assert r.status_code == 200, r.text
    assert r.json()["package"]["metodo_entrega"] == "busqueda"


def test_guarda_sin_acceso_al_qr_de_residente(client):
    uuid, _ = _paquete_residente(client, "QRAA55")
    login(client, "guarda1")
    r = client.get(f"/api/packages/{uuid}/pass")
    assert r.status_code == 403


def test_guarda_con_acceso_al_qr_de_tercero_y_admin_todo(client):
    uuid = _paquete_tercero(client)
    login(client, "guarda1")
    r = client.get(f"/api/packages/{uuid}/pass")
    assert r.status_code == 200, r.text
    # el tercero reclama con su QR + cédula: metodo qr
    r = client.post(f"/api/packages/{uuid}/entregar", json={"cedula": "987654321", "token": sign_package(uuid)})
    assert r.status_code == 200, r.text
    assert r.json()["package"]["metodo_entrega"] == "qr"

    # admin puede ver el QR de un paquete de residente (soporte)
    login(client, "admin1")
    uuid_res, _ = _paquete_residente(client, "QRAA66")
    r = client.get(f"/api/packages/{uuid_res}/pass")
    assert r.status_code == 200, r.text
