"""Edición de datos manuales: gracia de 1 hora para el guarda, admin a voluntad,
y control de ediciones (qué cambió, quién y cuándo)."""
from datetime import timedelta

from conftest import login
from sqlalchemy import text

from app.database import SessionLocal
from app.models import EditLog, Visit
from app.utils import utcnow

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _visita_manual(client, nombres="Digita", apellidos="Dedo") -> dict:
    login(client, "guarda1")
    r = client.post(
        "/api/visits/manual",
        json={
            "visitor_nombres": nombres,
            "visitor_apellidos": apellidos,
            "subject": "visita sin QR",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
        },
    )
    assert r.status_code == 200
    return r.json()["visit"]


def test_guarda_edita_su_visita_en_gracia(client):
    visit = _visita_manual(client)
    r = client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Digita Corregido",
            "visitor_apellidos": "Dedo",
            "subject": "domiciliario de correa",
            "visitor_role": "domiciliario",
            "tower": "2",
            "apartment": "205",
        },
    )
    assert r.status_code == 200
    v = r.json()["visit"]
    assert v["visitor_name"] == "Digita Corregido Dedo"  # nombre completo regenerado
    assert v["subject"] == "domiciliario de correa"
    assert v["apartment"] == "205"
    assert v["visitor_role"] == "domiciliario"

    db = SessionLocal()
    edits = db.query(EditLog).filter(EditLog.entity_uuid == visit["uuid"]).all()
    assert len(edits) == 1
    assert edits[0].cambios.startswith("nombres:")
    db.close()


def test_guarda_fuera_de_gracia_rechazado(client):
    visit = _visita_manual(client, "Tarde", "Fuera")
    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    v.entry_at = utcnow() - timedelta(hours=2)  # la gracia de 1 hora ya venció
    db.commit()
    db.close()

    r = client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Tarde",
            "visitor_apellidos": "Fuera",
            "subject": "x",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
        },
    )
    assert r.status_code == 400
    assert "gracia" in r.json()["detail"]


def test_guarda_no_edita_lo_ajeno(client):
    visit = _visita_manual(client, "Ajeno", "Otro")

    # otro guarda lo intenta
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Guarda Dos", "apellidos": "Noche", "username": "guarda2", "password": "clave123", "role": "guarda"},
    )
    assert r.status_code == 200
    login(client, "guarda2")
    r = client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Ajeno",
            "visitor_apellidos": "Otro",
            "subject": "x",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
        },
    )
    assert r.status_code == 403


def test_admin_edita_a_voluntad(client):
    visit = _visita_manual(client, "Admin", "Edita")
    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    v.entry_at = utcnow() - timedelta(days=3)  # sin límite de tiempo para el admin
    db.commit()
    db.close()

    login(client, "admin1")
    r = client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Admin",
            "visitor_apellidos": "Edita",
            "subject": "corregido por administración",
            "visitor_role": "visitante",
            "tower": "9",
            "apartment": "901",
        },
    )
    assert r.status_code == 200
    assert r.json()["visit"]["tower"] == "9"


def test_visita_de_residente_no_editable(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_nombres": "Residente", "visitor_apellidos": "Crea", "subject": "x", "visitor_role": "visitante", "hours": 4},
    )
    visit = r.json()["visit"]
    for quien in ("guarda1", "admin1"):
        login(client, quien)
        r = client.patch(
            f"/api/visits/{visit['uuid']}/editar",
            json={
                "visitor_nombres": "Residente",
                "visitor_apellidos": "Crea",
                "subject": "y",
                "visitor_role": "visitante",
                "tower": "1",
                "apartment": "101",
            },
        )
        assert r.status_code == 404  # las visitas de residente no se editan aquí


def test_edita_paquete_tercero(client):
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={"nombres": "Camilo", "apellidos": "Restrepo", "tower": "4", "apartment": "1005", "photo_b64": FOTO},
    )
    pkg = r.json()["package"]

    # el guarda que lo registró, dentro de la gracia
    r = client.patch(
        f"/api/packages/{pkg['uuid']}/editar",
        json={"nombres": "Camilo José", "apellidos": "Restrepo", "tower": "4", "apartment": "1005", "description": "caja Amazon"},
    )
    assert r.status_code == 200
    assert r.json()["package"]["nombre_tercero"] == "Camilo José Restrepo"

    # fuera de gracia: el guarda ya no, el admin sí
    db = SessionLocal()
    db.execute(
        text("UPDATE packages SET created_at = :t WHERE uuid = :u"),
        {"t": utcnow() - timedelta(hours=3), "u": pkg["uuid"]},
    )
    db.commit()
    db.close()

    r = client.patch(
        f"/api/packages/{pkg['uuid']}/editar",
        json={"nombres": "Camilo José", "apellidos": "Restrepo", "tower": "5", "apartment": "1005"},
    )
    assert r.status_code == 400
    assert "gracia" in r.json()["detail"]

    login(client, "admin1")
    r = client.patch(
        f"/api/packages/{pkg['uuid']}/editar",
        json={"nombres": "Camilo José", "apellidos": "Restrepo", "tower": "5", "apartment": "1005"},
    )
    assert r.status_code == 200
    assert r.json()["package"]["tower"] == "5"


def test_campos_invalidos_rechazados(client):
    visit = _visita_manual(client, "Invalido", "Campo")
    login(client, "guarda1")
    r = client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Invalido",
            "visitor_apellidos": "",
            "subject": "x",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
        },
    )
    assert r.status_code == 400
    assert "separados" in r.json()["detail"]


def test_control_de_ediciones_en_admin(client):
    visit = _visita_manual(client, "Control", "Visible")
    login(client, "guarda1")
    client.patch(
        f"/api/visits/{visit['uuid']}/editar",
        json={
            "visitor_nombres": "Control Editado",
            "visitor_apellidos": "Visible",
            "subject": "visita sin QR",
            "visitor_role": "visitante",
            "tower": "2",
            "apartment": "201",
        },
    )

    login(client, "admin1")
    page = client.get("/admin/historial")
    assert "Control de ediciones" in page.text
    assert "guarda1" in page.text  # quién editó
    assert "Visita de Control Editado Visible" in page.text  # qué registro
    assert "nombres:" in page.text  # qué cambió
    seccion_visita = page.text.split("Control Editado Visible")[1].split("</tr>")[0]
    assert 'data-editar-visita="' in seccion_visita  # el admin ve el botón Editar

    # el chip de editada aparece en la fila del historial
    assert "editada" in page.text


def _fila_ingreso(client, nombre: str) -> str:
    """Busca la fila del visitante en las páginas de 'Ingresos de hoy' (la suite acumula cientos)."""
    for pag in range(1, 6):
        hoy = client.get(f"/guarda?pagina_h={pag}").text.split("Ingresos de hoy")[1]
        if nombre in hoy:
            return hoy.split(nombre)[1].split("</tr>")[0]
    return ""


def test_paquete_entregado_no_editable(client):
    """Una vez entregado, la información del paquete queda congelada (ni guarda ni admin)."""
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={"nombres": "Congelado", "apellidos": "Tras Entrega", "tower": "4", "apartment": "1005", "photo_b64": FOTO},
    )
    pkg = r.json()["package"]

    # entrega con cédula
    r = client.post(f"/api/packages/{pkg['uuid']}/entregar", json={"cedula": "123456789"})
    assert r.status_code == 200

    for quien in ("guarda1", "admin1"):
        login(client, quien)
        r = client.patch(
            f"/api/packages/{pkg['uuid']}/editar",
            json={"nombres": "Cambio", "apellidos": "Prohibido", "tower": "4", "apartment": "1005"},
        )
        assert r.status_code == 400
        assert "entregado" in r.json()["detail"]

    # la información quedó intacta
    db = SessionLocal()
    from app.models import Package
    p = db.query(Package).filter(Package.uuid == pkg["uuid"]).first()
    assert p.nombre_tercero == "Congelado Tras Entrega"
    db.close()


def test_editar_paquete_no_confirma_entrega(client):
    """Editar solo cambia la información: el paquete sigue en portería."""
    login(client, "guarda1")
    r = client.post(
        "/api/packages/manual",
        json={"nombres": "Sin", "apellidos": "Confirmar", "tower": "3", "apartment": "301", "photo_b64": FOTO},
    )
    pkg = r.json()["package"]

    r = client.patch(
        f"/api/packages/{pkg['uuid']}/editar",
        json={"nombres": "Sin", "apellidos": "Confirmar Igual", "tower": "3", "apartment": "301"},
    )
    assert r.status_code == 200
    assert r.json()["package"]["status"] == "en_porteria"  # la edición no entrega


def test_boton_editar_visible_solo_en_gracia(client):
    visit = _visita_manual(client, "Boton", "Gracia")
    login(client, "guarda1")
    fila = _fila_ingreso(client, "Boton Gracia")
    assert 'data-editar-visita="' in fila

    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    v.entry_at = utcnow() - timedelta(hours=2)
    db.commit()
    db.close()

    fila = _fila_ingreso(client, "Boton Gracia")
    assert 'data-editar-visita="' not in fila
