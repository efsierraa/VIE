from datetime import timedelta

from conftest import login

from app.database import SessionLocal
from app.models import Visit
from app.utils import utcnow


def _crear_visita(client, nombre="Juan Pérez"):
    r = client.post(
        "/api/visits",
        json={"visitor_name": nombre, "subject": "visita familiar", "visitor_role": "visitante", "hours": 12},
    )
    assert r.status_code == 200, r.json()
    return r.json()


def test_flujo_completo_entrada_salida(client):
    login(client, "residente1")
    j = _crear_visita(client)
    token = j["token"]
    assert j["visit"]["status"] == "pendiente"
    assert j["qr_data_uri"].startswith("data:image/png;base64,")
    assert j["visit"]["tower"] == "1"
    assert j["visit"]["apartment"] == "101"

    login(client, "guarda1")
    r = client.post("/api/scan", json={"token": token, "action": "entrada"})
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "dentro"

    # el QR es de un solo uso: segunda entrada falla
    r = client.post("/api/scan", json={"token": token, "action": "entrada"})
    assert r.status_code == 400

    r = client.post("/api/scan", json={"token": token, "action": "salida"})
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "finalizada"
    assert "duración" in r.json()["message"]

    r = client.post("/api/scan", json={"token": token, "action": "salida"})
    assert r.status_code == 400


def test_qr_alterado_rechazado(client):
    login(client, "residente1")
    j = _crear_visita(client, "Visita Alterada")
    token = j["token"]
    # alterar un carácter del medio: el último puede decodificar igual en base64
    token_malo = token[:2] + ("X" if token[2] != "X" else "Y") + token[3:]

    login(client, "guarda1")
    r = client.post("/api/scan", json={"token": token_malo, "action": "entrada"})
    assert r.status_code == 400
    assert "alterado" in r.json()["detail"]


def test_qr_expirado_rechazado(client):
    login(client, "residente1")
    j = _crear_visita(client, "Visita Vencida")

    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == j["visit"]["uuid"]).first()
    v.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()

    login(client, "guarda1")
    r = client.post("/api/scan", json={"token": j["token"], "action": "entrada"})
    assert r.status_code == 400
    assert "expirado" in r.json()["detail"]


def test_entrada_manual(client):
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_name": "Domiciliario Rápido",
            "subject": "entrega",
            "visitor_role": "domiciliario",
            "tower": "3",
            "apartment": "301",
        },
    )
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "dentro"
    assert r.json()["visit"]["manual"] is True


def test_residente_cancela_su_visita(client):
    login(client, "residente1")
    j = _crear_visita(client, "Visita a Cancelar")
    r = client.post(f"/api/visits/{j['visit']['uuid']}/cancel")
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "cancelada"


def test_otro_residente_no_cancela_ajena(client):
    login(client, "residente1")
    j = _crear_visita(client, "Visita Ajena")
    login(client, "residente2")
    r = client.post(f"/api/visits/{j['visit']['uuid']}/cancel")
    assert r.status_code == 404


def test_residente_requiere_torre_y_apto(client):
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"username": "sinapto", "password": "clave123", "nombres": "Sin", "apellidos": "Apto", "role": "residente"},
    )
    assert r.status_code == 400
    assert "torre" in r.json()["detail"].lower()
