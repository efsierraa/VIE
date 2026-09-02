from conftest import login


def test_anon_redirige_a_login(client):
    r = client.get("/residente", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_paginas_por_rol(client):
    login(client, "residente1")
    assert client.get("/residente").status_code == 200
    assert client.get("/guarda").status_code == 403
    assert client.get("/admin").status_code == 403

    login(client, "guarda1")
    assert client.get("/guarda").status_code == 200
    assert client.get("/residente").status_code == 403

    login(client, "admin1")
    assert client.get("/admin").status_code == 200
    assert client.get("/guarda").status_code == 403


def test_api_rechaza_roles_equivocados(client):
    login(client, "residente1")
    r = client.post("/api/scan", json={"token": "x", "action": "entrada"})
    assert r.status_code == 403
    r = client.post("/api/users", json={"nombres": "X", "apellidos": "Y", "username": "xy", "password": "clave123", "role": "admin"})
    assert r.status_code == 403

    login(client, "guarda1")
    r = client.post("/api/visits", json={"visitor_name": "A", "subject": "B", "visitor_role": "visitante", "hours": 2})
    assert r.status_code == 403
    r = client.post("/api/users", json={"nombres": "X", "apellidos": "Y", "username": "xy", "password": "clave123", "role": "admin"})
    assert r.status_code == 403


def test_admin_crea_guarda(client):
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Guarda", "apellidos": "Nuevo", "username": "guardanuevo", "password": "clave123", "role": "guarda"},
    )
    assert r.status_code == 200


def test_admin_no_se_desactiva_a_si_mismo(client):
    login(client, "admin1")
    r = client.post("/api/users", json={"nombres": "Admin", "apellidos": "Dos", "username": "admin2", "password": "clave123", "role": "admin"})
    assert r.status_code == 200
