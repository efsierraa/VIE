from conftest import login


def test_codigo_corto_flujo_completo(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": "Visita con Código", "subject": "visita", "visitor_role": "visitante", "hours": 4},
    )
    assert r.status_code == 200
    j = r.json()
    code = j["visit"]["short_code"]
    assert code is not None and len(code) == 6
    assert code.isalnum() and code == code.upper()

    # el guarda digita el código corto (incluso en minúscula) en modo entrada
    login(client, "guarda1")
    r = client.post("/api/scan", json={"code": code.lower(), "action": "entrada"})
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "dentro"

    # un solo uso: la entrada no se repite
    r = client.post("/api/scan", json={"code": code, "action": "entrada"})
    assert r.status_code == 400

    # la salida también se marca con el código corto
    r = client.post("/api/scan", json={"code": code, "action": "salida"})
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "finalizada"

    r = client.post("/api/scan", json={"code": code, "action": "salida"})
    assert r.status_code == 400


def test_codigo_corto_inexistente(client):
    login(client, "guarda1")
    r = client.post("/api/scan", json={"code": "ZZZZZZ", "action": "entrada"})
    assert r.status_code == 400
    assert "no válido" in r.json()["detail"]


def test_scan_sin_codigo_ni_token(client):
    login(client, "guarda1")
    r = client.post("/api/scan", json={"action": "entrada"})
    assert r.status_code == 400


def test_entrada_manual_genera_codigo_para_salida(client):
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_name": "Domi Urbano",
            "subject": "entrega",
            "visitor_role": "domiciliario",
            "tower": "5",
            "apartment": "502",
        },
    )
    assert r.status_code == 200
    code = r.json()["visit"]["short_code"]
    assert code is not None and len(code) == 6

    # la salida de una entrada manual también se marca digitando el código
    r = client.post("/api/scan", json={"code": code, "action": "salida"})
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "finalizada"
