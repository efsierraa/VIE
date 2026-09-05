"""Guarda de piscina: ingresos de adultos, niños con acompañante (nunca solos)
e invitados con padrino; salida en grupo; admin supervisa con filtros y Excel."""
import uuid as uuid_mod
from datetime import timedelta

from conftest import login

from app.database import SessionLocal
from app.models import PoolAccess, User
from app.utils import utcnow


def _piscina(client):
    login(client, "admin1")
    r = client.post(
        "/api/users",
        json={"nombres": "Guarda", "apellidos": "Piscina", "username": "piscina1", "password": "clave123", "role": "piscina"},
    )
    assert r.status_code in (200, 400)  # 400 si ya existe (BD compartida): igual sirve
    login(client, "piscina1")
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    db.close()
    return rid


def test_ingreso_adulto(client):
    rid = _piscina(client)
    r = client.post("/api/piscina/ingreso", json={"resident_id": rid})
    assert r.status_code == 200
    assert "entró a la piscina" in r.json()["message"]

    # entrada duplicada bloqueada
    r = client.post("/api/piscina/ingreso", json={"resident_id": rid})
    assert r.status_code == 400
    assert "ya está en la piscina" in r.json()["detail"]


def test_ingreso_nino_crea_adulto_vinculados(client):
    rid = _piscina(client)
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombre": "Juanito", "edad": 7}]},
    )
    assert r.status_code == 200
    assert "Juanito" in r.json()["message"]

    db = SessionLocal()
    ninos = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Juanito").all()
    assert ninos and ninos[0].acompanante_acceso_id
    adulto = db.query(PoolAccess).filter(PoolAccess.id == ninos[0].acompanante_acceso_id).first()
    assert adulto.persona_tipo == "adulto" and adulto.exit_at is None
    db.close()


def test_nino_sin_nombre_y_acompanante_invalido_rechazados(client):
    rid = _piscina(client)
    r = client.post("/api/piscina/ingreso-nino", json={"acompanante_id": rid, "ninos": [{"nombre": "  "}]})
    assert r.status_code == 400

    login(client, "piscina1")
    db = SessionLocal()
    gid = db.query(User).filter(User.username == "guarda1").first().id
    db.close()
    r = client.post("/api/piscina/ingreso-nino", json={"acompanante_id": gid, "ninos": [{"nombre": "Sin Acomp"}]})
    assert r.status_code == 404  # el acompañante debe ser un residente


def test_ingreso_invitado_con_padrino_y_ninos(client):
    rid = _piscina(client)
    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={"nombre": "Visita Pool", "padrino_id": rid, "ninos": [{"nombre": "Nina Pool", "edad": 5}]},
    )
    assert r.status_code == 200

    db = SessionLocal()
    nina = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Nina Pool").first()
    assert nina is not None and nina.acompanante_acceso_id
    inv = db.query(PoolAccess).filter(PoolAccess.id == nina.acompanante_acceso_id).first()
    assert inv.persona_tipo == "invitado" and inv.invitado_nombre == "Visita Pool" and inv.resident_id == rid
    db.close()


def _ids_juanito(client) -> tuple[int, int]:
    """Fila del niño Juanito y de su acompañante (de tests previos de la sesión)."""
    db = SessionLocal()
    nino = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Juanito").first()
    ids = (nino.id, nino.acompanante_acceso_id)
    db.close()
    return ids


def test_nino_no_sale_solo(client):
    _piscina(client)
    nino_id, _ = _ids_juanito(client)
    r = client.post(f"/api/piscina/salida/{nino_id}")
    assert r.status_code == 400
    assert "acompañante" in r.json()["detail"]


def test_salida_adulto_cierra_grupo(client):
    _piscina(client)
    nino_id, adulto_id = _ids_juanito(client)
    r = client.post(f"/api/piscina/salida/{adulto_id}")
    assert r.status_code == 200
    assert "Juanito" in r.json()["message"]
    assert len(r.json()["salidos"]) >= 2

    db = SessionLocal()
    for fid in (nino_id, adulto_id):
        assert db.query(PoolAccess).filter(PoolAccess.id == fid).first().exit_at is not None
    db.close()


def test_invitado_sale_con_sus_ninos_y_padrino_libre(client):
    rid = _piscina(client)
    db = SessionLocal()
    nina = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Nina Pool").first()
    inv_id, nina_id = nina.acompanante_acceso_id, nina.id
    padrino = db.query(PoolAccess).filter(
        PoolAccess.resident_id == rid, PoolAccess.persona_tipo == "adulto", PoolAccess.exit_at.is_(None)
    ).first()
    db.close()

    # el padrino sale libre aunque sus invitados sigan dentro
    if padrino:
        r = client.post(f"/api/piscina/salida/{padrino.id}")
        assert r.status_code == 200

    # el invitado sale en grupo con su niña
    r = client.post(f"/api/piscina/salida/{inv_id}")
    assert r.status_code == 200
    assert "Nina Pool" in r.json()["message"]
    db = SessionLocal()
    assert db.query(PoolAccess).filter(PoolAccess.id == nina_id).first().exit_at is not None
    db.close()


def test_roles_piscina_aislados(client):
    _piscina(client)
    page = client.get("/piscina")
    assert page.status_code == 200
    assert "En la piscina ahora" in page.text

    r = client.get("/guarda")
    assert r.status_code == 403  # la piscina no actúa en portería
    login(client, "guarda1")
    r = client.get("/piscina")
    assert r.status_code == 403


def test_historial_piscina_con_filtros(client):
    _piscina(client)
    login(client, "admin1")
    page = client.get("/admin/historial?tipo=piscina").text
    assert "Piscina" in page
    assert "Juanito" in page

    page = client.get("/admin/historial?tipo=piscina&torre=1").text
    assert "Juanito" in page  # el destino se hereda del residente

    page = client.get("/admin/historial?tipo=piscina&q=Nina").text
    assert "Nina Pool" in page
    assert "Juanito" not in page.split("Piscina</h2>")[1].split("</section>")[0]


def test_export_piscina(client):
    import openpyxl
    from io import BytesIO

    _piscina(client)
    login(client, "admin1")
    r = client.get("/admin/exportar?piscina=1")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.content))
    assert "Piscina" in wb.sheetnames
    hoja = wb["Piscina"]
    encabezados = [c.value for c in hoja[1]]
    assert "Persona" in encabezados and "Vínculo" in encabezados


def test_paginacion_activos_piscina(client):
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    for i in range(1, 32):
        db.add(
            PoolAccess(
                persona_tipo="adulto",
                resident_id=rid,
                tower="1",
                apartment="101",
                entry_at=utcnow() - timedelta(minutes=i),
            )
        )
    db.commit()
    db.close()

    login(client, "piscina1")
    page1 = client.get("/piscina")
    assert "Siguiente →" in page1.text

    page2 = client.get("/piscina?pagina_a=2")
    assert "← Anterior" in page2.text


def test_cuentas_ofrece_rol_piscina(client):
    """El rol piscina se puede crear desde Admin · Cuentas (formulario y CSV)."""
    login(client, "admin1")
    page = client.get("/admin/cuentas").text
    assert '<option value="piscina">Guarda de piscina</option>' in page
    assert "residente, guarda, piscina o admin" in page

    r = client.post(
        "/api/users",
        json={"nombres": "Pool", "apellidos": "Dos", "username": "piscina2", "password": "clave123", "role": "piscina"},
    )
    assert r.status_code == 200
    login(client, "piscina2")
    page = client.get("/piscina")
    assert page.status_code == 200
