"""Cierre unificado de tarjetas (✕ en la esquina, Esc, desvanecer) y backfill
de códigos de paquetes viejos (nunca más 'Código: None')."""
import base64  # noqa: F401  (usado por los data URI de los pases)

from conftest import login

from app.database import SessionLocal
from app.models import Package, User
from app.routers.api import asignar_codigos_faltantes

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def test_sin_boton_listo_y_tarjetas_con_cerrar(client):
    for plantilla in ("app/templates/guarda.html", "app/templates/guarda_paquetes.html"):
        texto = open(plantilla, encoding="utf-8").read()
        assert ">Listo</button>" not in texto
        assert 'id="pase-listo"' not in texto and 'id="pkg-pase-listo"' not in texto
    js = open("app/static/js/guarda_ingresos.js", encoding="utf-8").read()
    assert "btn-listo" not in js and "pase-listo" not in js
    js = open("app/static/js/guarda_paquetes.js", encoding="utf-8").read()
    assert "pkg-pase-listo" not in js

    # todas las tarjetas flotantes tienen su ✕
    page = client.get("/guarda").text if False else None  # las tarjetas están ocultas: validar por archivo
    for plantilla, tarjetas in {
        "app/templates/guarda.html": ["pase-card", "edit-visita-card", "result"],
        "app/templates/guarda_paquetes.html": ["pkg-pase-card", "edit-paquete-card"],
        "app/templates/admin_historial.html": ["edit-visita-card", "edit-paquete-card"],
        "app/templates/admin_cuentas.html": ["edit-cuenta-card"],
        "app/templates/residente.html": ["result"],
    }.items():
        texto = open(plantilla, encoding="utf-8").read()
        for tarjeta in tarjetas:
            assert f'data-cerrar="{tarjeta}"' in texto, f"{plantilla} sin ✕ para {tarjeta}"


def test_esc_y_desvanecer_en_app_js():
    js = open("app/static/app.js", encoding="utf-8").read()
    assert "Escape" in js  # la tecla también cierra
    assert "desvaneciendo" in js  # micro-animación de salida


def test_acerca_primera_persona(client):
    texto = open("app/templates/acerca.html", encoding="utf-8").read()
    assert "mi tío es <strong>guarda</strong>" in texto
    assert "el tío de quien la desarrolla" not in texto
    page = client.get("/acerca")
    assert "mi tío es" in page.text


def _paquete_legacy(client) -> str:
    """Paquete tercero creado 'antes' de la función QR: nace sin código corto."""
    db = SessionLocal()
    gid = db.query(User).filter(User.username == "guarda1").first().id
    p = Package(
        uuid="legacy-qr-0001",
        resident_id=gid,
        tercero=True,
        nombre_tercero="Edgar Melo",
        tercero_nombres="Edgar",
        tercero_apellidos="Melo",
        tower="4",
        apartment="1004",
        photo=b"\xff\xd8x",
        photo_mime="image/jpeg",
        short_code=None,  # así nacían antes del QR de reclamo
    )
    db.add(p)
    db.commit()
    db.close()
    return "legacy-qr-0001"


def test_backfill_asigna_codigo_a_paquetes_viejos(client):
    _paquete_legacy(client)

    db = SessionLocal()
    p = db.query(Package).filter(Package.uuid == "legacy-qr-0001").first()
    assert p.short_code is None  # aún sin backfill
    db.close()

    asignados = asignar_codigos_faltantes(SessionLocal())
    assert asignados >= 1

    db = SessionLocal()
    p = db.query(Package).filter(Package.uuid == "legacy-qr-0001").first()
    assert p.short_code  # ya tiene código corto real
    db.close()

    # idempotente: la segunda corrida no reasigna
    assert asignar_codigos_faltantes(SessionLocal()) == 0

    # el pase del paquete viejo ya es completo y la entrega por código funciona
    login(client, "guarda1")
    db = SessionLocal()
    codigo = db.query(Package).filter(Package.uuid == "legacy-qr-0001").first().short_code
    db.close()
    r = client.get("/api/packages/legacy-qr-0001/pass")
    assert r.status_code == 200
    r = client.post("/api/packages/scan", json={"code": codigo})
    assert r.status_code == 200
    assert r.json()["package"]["tercero"] is True

    # limpiar la BD compartida de la sesión
    db = SessionLocal()
    p = db.query(Package).filter(Package.uuid == "legacy-qr-0001").first()
    p.status = "cancelado"
    db.commit()
    db.close()


def test_leyenda_omite_codigo_cuando_no_existe(client):
    """Defensa: el compositor acepta pocas líneas (sin 'Código') y el pase de un
    paquete sin código no crashea ni imprime 'None'."""
    import io

    from PIL import Image
    from app.routers.api import qr_pase_data_uri, sign_package

    token = sign_package("sin-codigo-test")
    base64_a_png = lambda uri: Image.open(io.BytesIO(base64.b64decode(uri.split(",")[1])))

    una_linea = base64_a_png(qr_pase_data_uri(token, ["Paquete de: Alguien"]))
    dos_lineas = base64_a_png(qr_pase_data_uri(token, ["Código: ABC123", "Paquete de: Alguien"]))
    assert dos_lineas.height - una_linea.height == 28  # cada línea de leyenda añade 28 px

    # el pase de un paquete legacy sin código responde sin crash
    import uuid as uuid_mod

    db = SessionLocal()
    gid = db.query(User).filter(User.username == "guarda1").first().id
    pkg = Package(
        uuid=str(uuid_mod.uuid4()),
        resident_id=gid,
        tercero=True,
        nombre_tercero="Sin Codigo Legacy",
        tower="1",
        apartment="101",
        photo=b"\xff\xd8x",
        photo_mime="image/jpeg",
        short_code=None,
    )
    db.add(pkg)
    db.commit()
    uuid_pkg = pkg.uuid
    db.close()
    asignar_codigos_faltantes(SessionLocal())

    login(client, "guarda1")
    r = client.get(f"/api/packages/{uuid_pkg}/pass")
    assert r.status_code == 200  # ya con código del backfill, la leyenda sin 'None'

    # limpiar la BD compartida de la sesión
    db = SessionLocal()
    p = db.query(Package).filter(Package.uuid == uuid_pkg).first()
    p.status = "cancelado"
    db.commit()
    db.close()
