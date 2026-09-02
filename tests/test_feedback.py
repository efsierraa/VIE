from conftest import login

from app.database import SessionLocal
from app.models import User


def _crear(client, username, role="residente", tower="7", apartment="701"):
    r = client.post(
        "/api/users",
        json={
            "nombres": "Prueba",
            "apellidos": "Nueva",
            "username": username,
            "password": "clave123",
            "role": role,
            "tower": tower,
            "apartment": apartment,
        },
    )
    assert r.status_code == 200, r.json()


def test_usuario_cambia_su_clave(client):
    login(client, "admin1")
    _crear(client, "cambiapw")
    login(client, "cambiapw")

    r = client.post("/api/me/password", json={"actual": "clave-errada", "nueva": "nueva123"})
    assert r.status_code == 400

    r = client.post("/api/me/password", json={"actual": "clave123", "nueva": "nueva123"})
    assert r.status_code == 200

    # vuelve a entrar con la clave nueva
    r = client.post("/login", data={"username": "cambiapw", "password": "nueva123"}, follow_redirects=False)
    assert r.status_code == 303


def test_admin_asigna_clave(client):
    login(client, "admin1")
    _crear(client, "asignapw")
    db = SessionLocal()
    uid = db.query(User).filter(User.username == "asignapw").first().id
    db.close()

    r = client.post(f"/api/users/{uid}/password", json={"nueva": "corta"})
    assert r.status_code == 400

    r = client.post(f"/api/users/{uid}/password", json={"nueva": "nueva456"})
    assert r.status_code == 200

    # entra con la clave asignada por administración
    login(client, "asignapw", password="nueva456")


def test_importar_usuarios_csv(client):
    login(client, "admin1")
    contenido = (
        "nombres,apellidos,usuario,clave,rol,torre,apartamento\n"
        "Camila,Rojas,camilar,clave123,residente,3,301\n"
        "Malo,Row,malorol,clave123,spiderman,9,901\n"
    )
    r = client.post("/api/users/csv", files={"file": ("usuarios.csv", contenido.encode("utf-8"), "text/csv")})
    assert r.status_code == 200
    j = r.json()
    assert j["creados"] == 1
    assert len(j["errores"]) == 1
    assert "línea 3" in j["errores"][0]

    # la cuenta importada funciona
    login(client, "camilar")


def test_csv_con_encabezado_malo(client):
    login(client, "admin1")
    r = client.post("/api/users/csv", files={"file": ("x.csv", b"a,b,c\n1,2,3", "text/csv")})
    assert r.status_code == 400


def test_ver_qr_de_visita_pendiente(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": "Revisitada", "subject": "x", "visitor_role": "visitante", "hours": 4},
    )
    j = r.json()
    visit_uuid = j["visit"]["uuid"]
    code = j["visit"]["short_code"]

    # el residente reabre el pase sin crear una visita nueva
    r = client.get(f"/api/visits/{visit_uuid}/pass")
    assert r.status_code == 200
    assert r.json()["qr_data_uri"].startswith("data:image/png;base64,")
    assert r.json()["visit"]["short_code"] == code

    # tras usarse, ya no se puede reabrir
    login(client, "guarda1")
    client.post("/api/scan", json={"code": code, "action": "entrada"})
    login(client, "residente1")
    r = client.get(f"/api/visits/{visit_uuid}/pass")
    assert r.status_code == 400


def test_otro_residente_no_abre_pase_ajeno(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": "Ajena", "subject": "x", "visitor_role": "visitante", "hours": 4},
    )
    visit_uuid = r.json()["visit"]["uuid"]
    login(client, "residente2")
    r = client.get(f"/api/visits/{visit_uuid}/pass")
    assert r.status_code == 404


def test_exportar_excel(client):
    # genera un ingreso de hoy para que el reporte tenga datos
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": "Exportada", "subject": "prueba", "visitor_role": "visitante", "hours": 4},
    )
    code = r.json()["visit"]["short_code"]
    login(client, "guarda1")
    client.post("/api/scan", json={"code": code, "action": "entrada"})

    login(client, "admin1")
    r = client.get("/admin/exportar")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"  # un .xlsx es un zip

    r = client.get("/admin/exportar?desde=2020-01-01&hasta=2040-12-31")
    assert r.status_code == 200
