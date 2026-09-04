"""Pase de identificación del ingreso manual: QR + código válidos por 1 hora,
salida como la de cualquier visitante (flujo domiciliario) y el guarda puede
ver/reenviar el pase mientras la visita dure."""
from datetime import timedelta

from conftest import login

from app.database import SessionLocal
from app.models import Visit
from app.routers.api import auto_finalizar_visitas
from app.utils import utcnow


def _entrada_manual(client, nombres="Manual", apellidos="Con Pase") -> dict:
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_nombres": nombres,
            "visitor_apellidos": apellidos,
            "subject": "visita sin QR previo",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
        },
    )
    assert r.status_code == 200
    return r.json()


def test_entrada_manual_genera_pase_de_1_hora(client):
    j = _entrada_manual(client)
    assert j["token"]
    assert j["qr_data_uri"].startswith("data:image/png")

    from datetime import datetime
    vence = datetime.fromisoformat(j["visit"]["expires_at"])
    delta = vence - utcnow().replace(tzinfo=None)
    assert timedelta(minutes=55) < delta < timedelta(minutes=65), "el pase debe valer 1 hora"


def test_salida_con_el_pase_manual_como_el_domiciliario(client):
    j = _entrada_manual(client, "Sale", "Con Codigo")
    code = j["visit"]["short_code"]

    # escanear en modo entrada no procede: la entrada ya quedó registrada
    r = client.post("/api/scan", json={"code": code, "action": "entrada"})
    assert r.status_code == 400
    assert "modo salida" in r.json()["detail"]

    # el guarda cambia a modo Salida y escanea el QR (o digita el código)
    r = client.post("/api/scan", json={"code": code, "action": "salida"})
    assert r.status_code == 200
    assert r.json()["visit"]["status"] == "finalizada"
    assert r.json()["visit"]["exit_at"]


def test_salida_automatica_al_vencer_la_hora(client):
    j = _entrada_manual(client, "Olvida", "Salir")
    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == j["visit"]["uuid"]).first()
    v.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()

    assert auto_finalizar_visitas(SessionLocal()) >= 1

    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == j["visit"]["uuid"]).first()
    assert v.status == "finalizada" and v.salida_auto is True
    db.close()


def test_guarda_ve_y_reenvia_el_pase_de_una_visita_activa(client):
    # visita de residente: el visitante perdió el pase que le mandaron
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_nombres": "Perdio", "visitor_apellidos": "El Pase", "subject": "x", "visitor_role": "visitante", "hours": 4},
    )
    visit = r.json()["visit"]
    login(client, "guarda1")
    client.post("/api/scan", json={"code": visit["short_code"], "action": "entrada"})

    # el guarda la recupera mientras esté dentro
    r = client.get(f"/api/visits/{visit['uuid']}/pass")
    assert r.status_code == 200
    assert r.json()["qr_data_uri"].startswith("data:image/png")
    assert r.json()["visit"]["short_code"] == visit["short_code"]

    # y también el pase de una visita manual
    manual = _entrada_manual(client)
    r = client.get(f"/api/visits/{manual['visit']['uuid']}/pass")
    assert r.status_code == 200

    # el residente ajeno no puede
    login(client, "residente2")
    r = client.get(f"/api/visits/{visit['uuid']}/pass")
    assert r.status_code == 404


def test_pase_de_visita_finalizada_rechazado(client):
    j = _entrada_manual(client, "Ya", "Salió")
    client.post("/api/scan", json={"code": j["visit"]["short_code"], "action": "salida"})
    r = client.get(f"/api/visits/{j['visit']['uuid']}/pass")
    assert r.status_code == 400
    assert "usado" in r.json()["detail"]


def test_boton_ver_qr_en_tablas_del_guarda(client):
    j = _entrada_manual(client, "Boton", "Pase")
    uuid = j["visit"]["uuid"]
    login(client, "guarda1")

    page = client.get("/guarda")
    assert page.text.count('data-verqr="' + uuid) == 2  # en activas e ingresos de hoy

    # tras finalizar, el botón desaparece de ambas tablas
    client.post("/api/scan", json={"code": j["visit"]["short_code"], "action": "salida"})
    page = client.get("/guarda")
    assert 'data-verqr="' + uuid not in page.text
