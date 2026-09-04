"""Control de ediciones legible: etiqueta de paquete con destinatario y código,
y diff de edición sin 'None' en campos vacíos."""
from conftest import login

from app.database import SessionLocal
from app.models import Package, User


def _residente1_id() -> int:
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    db.close()
    return rid


def test_diff_id_vacio_sin_none(client):
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_nombres": "Diff",
            "visitor_apellidos": "Limpio",
            "subject": "x",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
            "id_number": "1234567",
        },
    )
    visit = r.json()["visit"]

    # el admin borra el ID (queda vacío, no 'None')
    login(client, "admin1")
    r = client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Diff",
            "visitor_apellidos": "Limpio",
            "subject": "x",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
            "id_number": "",
        },
    )
    assert r.status_code == 200

    page = client.get("/admin/historial").text
    control = page.split("Control de ediciones")[1].split("</section>")[0]
    assert "'None'" not in control
    assert "ID: &#39;1234567&#39; → &#39;&#39;" in control  # el HTML escapa las comillas


def test_etiqueta_paquete_registrado_con_codigo(client):
    FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    login(client, "guarda1")
    r = client.post(
        "/api/packages",
        json={"resident_id": _residente1_id(), "description": "paquete etiqueta", "photo_b64": FOTO},
    )
    pkg = r.json()["package"]
    client.post(f"/api/packages/{pkg['uuid']}/entregar", json={"cedula": "555"})
    login(client, "residente1")
    client.post(f"/api/packages/{pkg['uuid']}/disputar")
    login(client, "admin1")
    client.post(f"/api/packages/{pkg['uuid']}/resolver")
    login(client, "residente1")
    client.post(f"/api/packages/{pkg['uuid']}/resolver")

    # el control se consulta como administrador
    login(client, "admin1")
    page = client.get("/admin/historial").text
    control = page.split("Control de ediciones")[1].split("</section>")[0]
    assert "Paquete de ?" not in control
    assert f"Paquete de Residenta Uno (código {pkg['short_code']})" in control
    assert "aceptada por portería (admin1)" in control
    assert "aceptada por residente (residente1)" in control
