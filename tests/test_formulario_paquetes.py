"""El bloque tercero oculto no puede llevar required: el navegador no puede
enfocar esos inputs y bloquea en silencio el envío del formulario completo."""
from conftest import login


def test_inputs_tercero_ocultos_sin_required(client):
    login(client, "guarda1")
    page = client.get("/guarda/paquetes")
    bloque = page.text.split('id="pkg-bloque-tercero"')[1].split('<label>Descripci')[0]
    assert "required" not in bloque

    # la validación vive en el JS: solo aplica cuando el tercero está marcado
    js = open("app/static/js/guarda_paquetes.js", encoding="utf-8").read()
    assert "Torre y apartamento son obligatorios" in js
    assert "Digita nombres y apellidos" in js


def test_registro_paquete_residente_sin_bloqueo_html(client):
    """Flujo completo de la captura del bug: residente seleccionado + foto +
    descripcion, sin marcar tercero. El formulario se envía sin que los
    required ocultos lo bloqueen (el API responde ok)."""
    FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    login(client, "guarda1")
    r = client.get("/api/residentes?q=Mariana")
    if r.status_code == 200 and r.json()["residentes"]:
        rid = r.json()["residentes"][0]["id"]
    else:
        from app.database import SessionLocal
        from app.models import User
        db = SessionLocal()
        rid = db.query(User).filter(User.username == "residente1").first().id
        db.close()

    r = client.post(
        "/api/packages",
        json={"resident_id": rid, "description": "Amazon", "photo_b64": FOTO},
    )
    assert r.status_code == 200
    assert r.json()["ok"]

    # limpiar: cancelar el paquete para no contaminar la BD compartida de la sesión
    uuid = r.json()["package"]["uuid"]
    client.post(f"/api/packages/{uuid}/cancelar")
