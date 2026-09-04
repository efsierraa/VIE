"""Pases unificados por WhatsApp: QR con leyenda incrustada + texto siempre juntos,
botón condicional al celular, y QR de reclamo para paquetes de tercero."""
import base64
import io

from conftest import login

from PIL import Image

from app.database import SessionLocal
from app.models import Package, User

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _alto_qr(data_uri: str) -> int:
    return Image.open(io.BytesIO(base64.b64decode(data_uri.split(",")[1]))).height


def test_qr_de_visita_lleva_leyenda_incrustada(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_nombres": "Leyenda", "visitor_apellidos": "Incrusta", "subject": "x", "visitor_role": "visitante", "hours": 4},
    )
    j = r.json()

    # la imagen compuesta mide más que un QR cuadrado del mismo token
    import qrcode
    desnudo = qrcode.make(j["token"], box_size=6, border=2)
    assert _alto_qr(j["qr_data_uri"]) > desnudo.height


def test_qr_manual_lleva_validez_1_hora_en_la_leyenda(client):
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={"visitor_nombres": "Manual", "visitor_apellidos": "Leyenda", "subject": "x", "visitor_role": "visitante", "tower": "2", "apartment": "201"},
    )
    j = r.json()
    import qrcode
    desnudo = qrcode.make(j["token"], box_size=6, border=2)
    assert _alto_qr(j["qr_data_uri"]) > desnudo.height  # tres líneas de leyenda


def test_placeholder_y_botones_limpios(client):
    login(client, "residente1")
    page = client.get("/residente").text
    assert "entrega a domicilio" in page
    assert "entrega de domo" not in page
    assert 'id="btn-wa"' in page
    assert 'id="btn-download"' in page
    assert 'id="btn-share"' not in page
    assert 'id="btn-copy"' not in page


def test_apellidos_en_negrilla_para_cotejo(client):
    js = open("app/static/js/porteria.js", encoding="utf-8").read()
    assert "· <strong>Apellidos: " in js
    assert "<strong>Nombres: " not in js  # la negrilla va en los apellidos


def test_paquete_tercero_genera_qr_de_reclamo(client):
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={"nombres": "Tercero", "apellidos": "Con QR", "tower": "4", "apartment": "1005", "photo_b64": FOTO},
    )
    j = r.json()
    p = j["package"]
    assert p["short_code"]  # ahora el tercero tiene código corto
    assert j["qr_data_uri"].startswith("data:image/png")
    assert j["token"]
    assert _alto_qr(j["qr_data_uri"]) > 300  # leyenda incrustada

    # entrega por código corto digitado: el flujo con cédula
    r = client.post("/api/packages/scan", json={"code": p["short_code"]})
    assert r.status_code == 200
    assert r.json()["package"]["tercero"] is True
    assert r.json()["package"]["photo_data_uri"].startswith("data:image")

    # y por escaneo del QR (token firmado)
    r = client.post("/api/packages/scan", json={"token": j["token"]})
    assert r.status_code == 200


def test_qr_tercero_muere_tras_entrega(client):
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={"nombres": "Muere", "apellidos": "Tras Entrega", "tower": "4", "apartment": "1005", "photo_b64": FOTO},
    )
    j = r.json()
    pkg = j["package"]
    client.post(f"/api/packages/{pkg['uuid']}/entregar", json={"cedula": "12345"})
    r = client.post("/api/packages/scan", json={"code": pkg["short_code"]})
    assert r.status_code == 400
    assert "entregado" in r.json()["detail"]


def test_guarda_reabre_qr_de_paquete_pendiente(client):
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={"nombres": "Reabre", "apellidos": "QR", "tower": "4", "apartment": "1005", "celular": "300 111 2222", "photo_b64": FOTO},
    )
    pkg = r.json()["package"]

    r = client.get(f"/api/packages/{pkg['uuid']}/pass")
    assert r.status_code == 200
    assert r.json()["qr_data_uri"].startswith("data:image/png")
    assert r.json()["package"]["tercero"] is True

    # el residente ajeno no puede
    login(client, "residente2")
    r = client.get(f"/api/packages/{pkg['uuid']}/pass")
    assert r.status_code == 404


def test_envio_whatsapp_condicional_al_celular(client):
    js = open("app/static/js/guarda_paquetes.js", encoding="utf-8").read()
    assert "if (j.package.tercero_celular)" in js  # solo con celular
    assert "compartirPase(" in js
    js = open("app/static/js/residente.js", encoding="utf-8").read()
    assert "if (v.visitor_celular)" in js
    assert "wa.me" not in js  # sin respaldo de solo-texto
    app = open("app/static/app.js", encoding="utf-8").read()
    assert "navigator.share({files: [archivo], text: texto})" in app  # imagen + texto juntos


def test_ver_qr_en_pendientes_con_tarjeta_de_pase(client):
    login(client, "guarda1")
    page = client.get("/guarda/paquetes").text
    assert 'data-verqr-pkg="' in page
    assert 'id="pkg-pase-card"' in page
    assert 'id="pkg-pase-wa"' in page
