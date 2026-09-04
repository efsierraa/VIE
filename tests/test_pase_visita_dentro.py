"""El residente puede ver y compartir el pase de una visita que ya está dentro."""
from conftest import login


def _visita_dentro(client, nombre="Dentro Pase") -> dict:
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_nombres": nombre, "visitor_apellidos": "Prueba", "subject": "x", "visitor_role": "visitante", "hours": 8},
    )
    visit = r.json()["visit"]
    login(client, "guarda1")
    client.post("/api/scan", json={"code": visit["short_code"], "action": "entrada"})
    return visit


def test_pase_disponible_para_visita_dentro(client):
    visit = _visita_dentro(client, "Dentro Pase")

    login(client, "residente1")
    r = client.get(f"/api/visits/{visit['uuid']}/pass")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"]
    assert j["qr_data_uri"].startswith("data:image/png")
    assert j["token"]
    assert j["visit"]["status"] == "dentro"
    assert j["visit"]["visitor_nombres"] == "Dentro Pase"


def test_pase_no_disponible_para_visita_finalizada(client):
    visit = _visita_dentro(client, "Finalizada Pase")

    login(client, "guarda1")
    client.post("/api/scan", json={"code": visit["short_code"], "action": "salida"})

    login(client, "residente1")
    r = client.get(f"/api/visits/{visit['uuid']}/pass")
    assert r.status_code == 400
    assert "usado" in r.json()["detail"]


def test_boton_ver_qr_para_visita_dentro(client):
    _visita_dentro(client, "Boton Dentro")

    login(client, "residente1")
    page = client.get("/residente")
    assert "Boton Dentro" in page.text
    seccion = page.text.split("Boton Dentro")[1].split("</tr>")[0]
    assert 'data-verqr="' in seccion
    assert "Cancelar" not in seccion  # solo se cancela lo pendiente
