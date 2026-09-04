"""Administración edita cuentas (nombres, celular, torre, apto) con control de
ediciones, y la lista de cuentas tiene buscador y paginación."""
from conftest import login

from app.database import SessionLocal
from app.models import EditLog, User


def _cuenta(client) -> int:
    db = SessionLocal()
    existente = db.query(User).filter(User.username == "cuentaedit").first()
    if existente:
        uid = existente.id
        db.close()
        login(client, "admin1")  # el fixture client es nuevo por test: siempre iniciar sesión
        return uid
    db.close()
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Cuenta", "apellidos": "Editable", "username": "cuentaedit", "password": "clave123", "role": "residente", "tower": "7", "apartment": "701"},
    )
    assert r.status_code == 200
    db = SessionLocal()
    uid = db.query(User).filter(User.username == "cuentaedit").first().id
    db.close()
    return uid


def test_admin_edita_celular_y_nombres(client):
    uid = _cuenta(client)

    r = client.patch(
        f"/api/users/{uid}/editar",
        json={"nombres": "Cuenta Editada", "apellidos": "Editable", "celular": "320 123 4567", "tower": "7", "apartment": "702"},
    )
    assert r.status_code == 200

    db = SessionLocal()
    u = db.query(User).filter(User.id == uid).first()
    assert u.celular == "573201234567"
    assert u.nombres == "Cuenta Editada"
    assert u.apartment == "702"
    assert u.username == "cuentaedit"  # la identidad no cambia
    assert u.role == "residente"
    db.close()

    # visible en la tabla de cuentas
    page = client.get("/admin/cuentas").text
    assert "Cuenta Editada" in page
    assert "573201234567" in page


def test_edicion_de_cuenta_en_control_de_ediciones(client):
    uid = _cuenta(client)
    client.patch(
        f"/api/users/{uid}/editar",
        json={"nombres": "Cuenta", "apellidos": "Editable", "celular": "321 999 8877", "tower": "7", "apartment": "701"},
    )

    page = client.get("/admin/historial").text
    control = page.split("Control de ediciones")[1].split("</section>")[0]
    assert "Cuenta de cuentaedit" in control  # el nombre actual puede variar (tests previos)
    assert "celular:" in control and "573219998877" in control


def test_no_admin_no_edita_cuentas(client):
    uid = _cuenta(client)
    login(client, "guarda1")
    r = client.patch(
        f"/api/users/{uid}/editar",
        json={"nombres": "Hack", "apellidos": "Intento", "tower": "1", "apartment": "101"},
    )
    assert r.status_code == 403


def test_residente_requiere_torre_y_apto(client):
    uid = _cuenta(client)
    login(client, "admin1")
    r = client.patch(
        f"/api/users/{uid}/editar",
        json={"nombres": "Cuenta", "apellidos": "Editable", "tower": "", "apartment": ""},
    )
    assert r.status_code == 400
    assert "torre y apartamento" in r.json()["detail"]


def test_celular_invalido_rechazado(client):
    uid = _cuenta(client)
    login(client, "admin1")
    r = client.patch(
        f"/api/users/{uid}/editar",
        json={"nombres": "Cuenta", "apellidos": "Editable", "celular": "12", "tower": "7", "apartment": "701"},
    )
    assert r.status_code == 400
    assert "celular" in r.json()["detail"].lower()


def test_paginacion_y_busqueda_de_cuentas(client):
    from app.auth import hash_password

    db = SessionLocal()
    for i in range(1, 56):
        nombre = f"Masiva{i:03d}"
        if not db.query(User).filter(User.username == f"masiva{i:03d}").first():
            db.add(
                User(
                    username=f"masiva{i:03d}",
                    password_hash=hash_password("clave123"),
                    nombres=nombre,
                    apellidos="Lote",
                    role="residente",
                    tower="9",
                    apartment=f"9{i:02d}",
                )
            )
    db.commit()
    db.close()

    login(client, "admin1")
    page1 = client.get("/admin/cuentas").text
    assert "Siguiente →" in page1

    page = client.get("/admin/cuentas?q=Masiva017").text
    assert "Masiva017 Lote" in page
    assert "Masiva016" not in page.split("Masiva017")[0] if "Masiva016" in page else True
    # la búsqueda filtra: el usuario "masiva" no aparece en resultados de "Masiva017"
    resultados = page.split("<tbody>")[1].split("</tbody>")[0]
    assert "masiva054" not in resultados
