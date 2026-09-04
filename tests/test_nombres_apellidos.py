"""Nombres y apellidos en campos separados y claros, en todo el proyecto."""
from conftest import login

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def test_visita_con_dos_campos(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={
            "visitor_nombres": "Juan María",
            "visitor_apellidos": "Pérez Gómez",
            "subject": "visita familiar",
            "visitor_role": "visitante",
            "hours": 4,
        },
    )
    assert r.status_code == 200
    v = r.json()["visit"]
    assert v["visitor_nombres"] == "Juan María"
    assert v["visitor_apellidos"] == "Pérez Gómez"
    assert v["visitor_name"] == "Juan María Pérez Gómez"  # concatenado para mostrar y buscar


def test_visita_solo_con_nombre_completo_compat(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": "Cliente Antiguo", "subject": "x", "visitor_role": "visitante", "hours": 4},
    )
    assert r.status_code == 200
    v = r.json()["visit"]
    assert v["visitor_name"] == "Cliente Antiguo"
    assert v["visitor_nombres"] is None and v["visitor_apellidos"] is None


def test_dos_campos_incompletos_rechazados(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_nombres": "Solo Nombres", "subject": "x", "visitor_role": "visitante", "hours": 4},
    )
    assert r.status_code == 400
    assert "separados" in r.json()["detail"]


def test_entrada_manual_con_dos_campos(client):
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_nombres": "Ana Lucía",
            "visitor_apellidos": "Torres Río",
            "subject": "domiciliario",
            "visitor_role": "domiciliario",
            "tower": "3",
            "apartment": "301",
        },
    )
    assert r.status_code == 200
    v = r.json()["visit"]
    assert v["visitor_nombres"] == "Ana Lucía"
    assert v["visitor_apellidos"] == "Torres Río"
    assert v["visitor_name"] == "Ana Lucía Torres Río"


def test_paquete_tercero_con_dos_campos(client):
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={
            "nombres": "Camilo",
            "apellidos": "Restrepo",
            "tower": "4",
            "apartment": "1005",
            "photo_b64": FOTO,
        },
    )
    assert r.status_code == 200
    p = r.json()["package"]
    assert p["tercero_nombres"] == "Camilo"
    assert p["tercero_apellidos"] == "Restrepo"
    assert p["nombre_tercero"] == "Camilo Restrepo"


def test_formularios_con_dos_campos(client):
    login(client, "residente1")
    page = client.get("/residente")
    assert 'name="visitor_nombres"' in page.text
    assert 'name="visitor_apellidos"' in page.text
    assert 'name="visitor_name"' not in page.text

    login(client, "guarda1")
    page = client.get("/guarda")
    assert 'name="visitor_nombres"' in page.text
    assert 'name="visitor_apellidos"' in page.text

    page = client.get("/guarda/paquetes")
    assert 'id="pkg-tercero-nombres"' in page.text
    assert 'id="pkg-tercero-apellidos"' in page.text
    assert 'id="pkg-tercero-nombre"' not in page.text


def test_escaneo_muestra_nombres_y_apellidos(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={
            "visitor_nombres": "Lucía",
            "visitor_apellidos": "Mejía",
            "subject": "x",
            "visitor_role": "visitante",
            "hours": 4,
        },
    )
    visit = r.json()["visit"]
    login(client, "guarda1")
    r = client.post("/api/scan", json={"code": visit["short_code"], "action": "entrada"})
    assert r.status_code == 200
    v = r.json()["visit"]
    assert v["visitor_nombres"] == "Lucía"
    assert v["visitor_apellidos"] == "Mejía"
