import base64
import io

import pytest
from conftest import login

import app.limitador as limitador


def test_cabeceras_de_seguridad(client):
    r = client.get("/login")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "same-origin"
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "img-src 'self' data: blob:" in csp
    assert "default-src 'self'" in csp


def test_limitador_frena_login_fuerza_bruta(client, monkeypatch):
    monkeypatch.setattr(limitador, "HABILITADO", True)
    limitador._intentos.clear()
    try:
        # 10 fallos permitidos: devuelven la página de login con el error
        for _ in range(10):
            r = client.post("/login", data={"username": "admin1", "password": "incorrecta"})
            assert r.status_code == 200
        # el intento 11 recibe 429
        r = client.post("/login", data={"username": "admin1", "password": "incorrecta"})
        assert r.status_code == 429

        # con la clave correcta TAMBIÉN se frena: no hay forma de distinguir
        r = client.post("/login", data={"username": "admin1", "password": "clave123"})
        assert r.status_code == 429
    finally:
        limitador.HABILITADO = False
        limitador._intentos.clear()

    # limitador desactivado de nuevo: el login vuelve a funcionar
    login(client, "admin1")


def test_foto_reencodada_y_sin_exif(client):
    from PIL import Image

    from app.routers.api import decodificar_foto

    img = Image.new("RGB", (50, 50), "red")
    exif = Image.Exif()
    exif[0x010F] = "Fabricante-Test"  # etiqueta Make
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    guardada = Image.open(io.BytesIO(buf.getvalue()))
    assert guardada.getexif().get(0x010F) == "Fabricante-Test"  # EXIF presente antes

    foto, mime = decodificar_foto("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    assert mime == "image/jpeg"
    salida = Image.open(io.BytesIO(foto))
    assert salida.format == "JPEG"
    assert not salida.getexif()  # EXIF eliminado: sin marca del dispositivo ni GPS


def test_foto_grande_se_reescala_en_el_servidor(client):
    from PIL import Image

    from app.routers.api import decodificar_foto

    img = Image.new("RGB", (2400, 1200), "blue")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    foto, _ = decodificar_foto("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    assert max(Image.open(io.BytesIO(foto)).size) <= 1200


def test_archivo_que_no_es_imagen_rechazado():
    from app.routers.api import decodificar_foto

    basura = base64.b64encode(b"esto definitivamente no es una imagen").decode()
    with pytest.raises(ValueError, match="no es una imagen"):
        decodificar_foto("data:image/png;base64," + basura)
