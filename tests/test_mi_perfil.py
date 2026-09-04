"""Mi perfil: self-service seguro. El usuario edita solo su celular (auditable);
nombres, torre y apartamento son exclusivos de administración."""
from conftest import login

from app.database import SessionLocal
from app.models import User


def _uid(username: str) -> int:
    db = SessionLocal()
    uid = db.query(User).filter(User.username == username).first().id
    db.close()
    return uid


def test_guarda_y_residente_editan_su_celular(client):
    for usuario in ("guarda1", "residente1"):
        login(client, usuario)
        r = client.patch("/api/perfil", json={"celular": "300 777 6655"})
        assert r.status_code == 200
        assert r.json()["celular"] == "573007776655"

    # la auto-edición queda en el control de ediciones con el propio usuario como editor
    login(client, "admin1")
    page = client.get("/admin/historial").text
    control = page.split("Control de ediciones")[1].split("</section>")[0]
    assert "Cuenta de guarda1" in control
    assert "573007776655" in control


def test_perfil_ignora_datos_sensibles(client):
    """Enviar nombres/torre/apto por /api/perfil no debe cambiar nada de eso."""
    uid = _uid("residente2")
    login(client, "residente2")
    r = client.patch(
        "/api/perfil",
        json={"celular": "301 222 3344", "nombres": "Hacked", "apellidos": "Name", "tower": "9", "apartment": "999"},
    )
    assert r.status_code == 200

    db = SessionLocal()
    u = db.query(User).filter(User.id == uid).first()
    assert u.nombres == "Residente"  # intacto
    assert u.apellidos == "Dos"
    assert u.tower == "2"
    assert u.apartment == "202"
    assert u.celular == "573012223344"  # solo el celular cambió
    db.close()

    # administración sí puede cambiar el destino (ya existe ese flujo)
    login(client, "admin1")
    r = client.patch(
        f"/api/users/{uid}/editar",
        json={"nombres": "Residente", "apellidos": "Dos", "tower": "3", "apartment": "303"},
    )
    assert r.status_code == 200
    db = SessionLocal()
    u = db.query(User).filter(User.id == uid).first()
    assert u.tower == "3" and u.apartment == "303"
    db.close()


def test_mi_perfil_datos_solo_lectura(client):
    login(client, "residente2")
    page = client.get("/cuenta").text
    assert "Mi perfil" in page
    assert "Mis datos" in page
    assert "Destino:" in page  # en solo lectura, con el destino vigente sea cual sea
    assert "los actualiza administración" in page
    assert 'id="cel-form"' in page  # su celular sí se edita
