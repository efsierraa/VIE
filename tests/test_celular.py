"""Celular opcional en todo el sistema: perfiles, visitas, paquetes tercero,
visualización en tablas/historiales, Excel y el botón condicional de WhatsApp."""
import io

from conftest import login

from app.database import SessionLocal
from app.models import User
from app.routers.api import normalizar_celular

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _residente1_id() -> int:
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    db.close()
    return rid


def test_normalizacion_de_celulares():
    assert normalizar_celular("300 123 4567") == "573001234567"
    assert normalizar_celular("+57 (300) 123-4567") == "573001234567"
    assert normalizar_celular("573001234567") == "573001234567"
    assert normalizar_celular("") is None
    assert normalizar_celular(None) is None
    assert normalizar_celular("12345678901234") == "12345678901234"  # internacional


def test_celular_invalido_rechazado(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={
            "visitor_nombres": "Cel", "visitor_apellidos": "Malo",
            "subject": "x", "visitor_role": "visitante",
            "visitor_celular": "123",  # muy corto
        },
    )
    assert r.status_code == 400
    assert "celular" in r.json()["detail"].lower()


def test_visita_con_y_sin_celular(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={
            "visitor_nombres": "Con", "visitor_apellidos": "Celular",
            "subject": "x", "visitor_role": "visitante",
            "visitor_celular": "300 123 4567",
        },
    )
    v = r.json()["visit"]
    assert v["visitor_celular"] == "573001234567"

    r = client.post(
        "/api/visits",
        json={"visitor_nombres": "Sin", "visitor_apellidos": "Celular", "subject": "y", "visitor_role": "visitante"},
    )
    assert r.json()["visit"]["visitor_celular"] is None


def test_formulario_residente_tiene_campo_celular(client):
    login(client, "residente1")
    page = client.get("/residente")
    assert 'name="visitor_celular"' in page.text


def test_entrada_manual_con_celular_para_whatsapp(client):
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_nombres": "Manual", "visitor_apellidos": "Whats",
            "subject": "x", "visitor_role": "visitante",
            "tower": "2", "apartment": "201",
            "visitor_celular": "301 555 7788",
        },
    )
    j = r.json()
    assert j["visit"]["visitor_celular"] == "573015557788"
    assert j["qr_data_uri"].startswith("data:image/png")  # el pase listo para enviar

    page = client.get("/guarda").text
    assert "573015557788" in page  # visible en ingresos de hoy / activas


def test_editar_visita_actualiza_celular_y_lo_registra(client):
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_nombres": "Edita", "visitor_apellidos": "Cel",
            "subject": "x", "visitor_role": "visitante", "tower": "2", "apartment": "201",
        },
    )
    visit = r.json()["visit"]
    assert visit["visitor_celular"] is None

    r = client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Edita", "visitor_apellidos": "Cel",
            "subject": "x", "visitor_role": "visitante",
            "tower": "2", "apartment": "201",
            "visitor_celular": "300 444 5566",
        },
    )
    assert r.status_code == 200
    assert r.json()["visit"]["visitor_celular"] == "573004445566"

    login(client, "admin1")
    page = client.get("/admin/historial").text
    control = page.split("Control de ediciones")[1].split("</section>")[0]
    assert "celular: &#39;&#39; → &#39;573004445566&#39;" in control  # el HTML escapa las comillas


def test_paquete_tercero_con_celular(client):
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={
            "nombres": "Tercero", "apellidos": "Con Cel",
            "tower": "4", "apartment": "1005",
            "celular": "311 222 3344",
            "photo_b64": FOTO,
        },
    )
    p = r.json()["package"]
    assert p["tercero_celular"] == "573112223344"

    # visible en la tabla de pendientes
    page = client.get("/guarda/paquetes").text
    assert "573112223344" in page

    # editar lo actualiza
    r = client.patch(
        f"/api/packages/{p['uuid']}/editar",
        json={
            "nombres": "Tercero", "apellidos": "Con Cel",
            "tower": "4", "apartment": "1005",
            "celular": "311 999 8877",
        },
    )
    assert r.json()["package"]["tercero_celular"] == "573119998877"


def test_crear_cuenta_con_celular(client):
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={
            "nombres": "Perfil", "apellidos": "Con Cel",
            "username": "perfilcel", "password": "clave123",
            "role": "residente", "tower": "5", "apartment": "501",
            "celular": "310 777 8899",
        },
    )
    assert r.status_code == 200
    page = client.get("/admin/cuentas").text
    assert "573107778899" in page  # columna Celular de la tabla


def test_csv_con_columna_celular(client):
    login(client, "admin1")
    csv_content = (
        "nombres,apellidos,usuario,clave,rol,torre,apartamento,celular\n"
        "Csv,Concel,csvcel,clave123,residente,6,601,312 999 0000\n"
    )
    r = client.post(
        "/api/users/csv",
        files={"file": ("usuarios.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["creados"] == 1

    page = client.get("/admin/cuentas").text
    assert "573129990000" in page


def test_csv_sin_columna_celular_sigue_funcionando(client):
    login(client, "admin1")
    csv_content = (
        "nombres,apellidos,usuario,clave,rol,torre,apartamento\n"
        "Csv,Scel,csvscel,clave123,residente,6,602\n"
    )
    r = client.post(
        "/api/users/csv",
        files={"file": ("usuarios.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["creados"] == 1


def test_mi_celular_self_service_por_rol(client):
    for usuario, clave in (("guarda1", "guarda1"), ("residente1", "residente1")):
        login(client, usuario)
        r = client.patch("/api/perfil", json={"celular": "300 000 1111"})
        assert r.status_code == 200
        assert r.json()["celular"] == "573000001111"

    login(client, "admin1")
    r = client.patch("/api/perfil", json={"celular": "300 000 2222"})
    assert r.json()["celular"] == "573000002222"

    # se puede vaciar
    r = client.patch("/api/perfil", json={"celular": ""})
    assert r.json()["celular"] is None

    page = client.get("/cuenta").text
    assert 'id="cel-form"' in page


def test_excel_incluye_columna_celular(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={
            "visitor_nombres": "Excel", "visitor_apellidos": "Cel",
            "subject": "x", "visitor_role": "visitante",
            "visitor_celular": "315 444 5566",
        },
    )
    # el export trae los ingresos del día: registrar la entrada de la visita
    code = r.json()["visit"]["short_code"]
    login(client, "guarda1")
    client.post("/api/scan", json={"code": code, "action": "entrada"})

    login(client, "admin1")
    import openpyxl
    r = client.get("/admin/exportar?ingresos=1")
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ingresos = wb["Ingresos"]
    encabezados = [c.value for c in ingresos[1]]
    assert "Celular" in encabezados
    idx = encabezados.index("Celular")
    encontrado = any(fila[idx] == "573154445566" for fila in ingresos.iter_rows(min_row=2, values_only=True))
    assert encontrado


def test_botones_whatsapp_solo_con_celular(client):
    """La lógica condicional vive en el JS: verifica los datos que la alimentan."""
    js = open("app/static/js/guarda_ingresos.js", encoding="utf-8").read()
    assert "wa.me/" in js
    assert "if (v.visitor_celular)" in js

    js = open("app/static/js/residente.js", encoding="utf-8").read()
    assert "wa.me/" in js
    assert "if (v.visitor_celular)" in js
