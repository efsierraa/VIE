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
        json={"acompanante_id": rid, "ninos": [{"nombre": "Juanito Pérez", "edad": 7}]},
    )
    assert r.status_code == 200
    assert "Juanito" in r.json()["message"]

    db = SessionLocal()
    ninos = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Juanito Pérez").all()
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
    nino = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Juanito Pérez").first()
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


def _rid2(client):
    _piscina(client)
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente2").first().id
    db.close()
    return rid


def test_ingreso_tres_ninos_una_sola_fila_adulto(client):
    """Un adulto entra con varios niños de una vez: una fila de adulto, N filas ligadas."""
    rid = _rid2(client)
    nombres = ["Ana María Ruiz", "Luis Eduardo Ruiz", "Camila Ruiz"]
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombre": n, "edad": i + 5} for i, n in enumerate(nombres)]},
    )
    assert r.status_code == 200
    for n in nombres:
        assert n in r.json()["message"]

    db = SessionLocal()
    filas = [db.query(PoolAccess).filter(PoolAccess.menor_nombre == n).first() for n in nombres]
    assert all(f is not None and f.exit_at is None for f in filas)
    adultos = {f.acompanante_acceso_id for f in filas}
    assert len(adultos) == 1
    adulto = db.query(PoolAccess).filter(PoolAccess.id == adultos.pop()).first()
    assert adulto.persona_tipo == "adulto" and adulto.resident_id == rid and adulto.exit_at is None
    ids_ninos, adulto_id = [f.id for f in filas], adulto.id
    db.close()

    r = client.post(f"/api/piscina/salida/{adulto_id}")
    assert r.status_code == 200
    assert len(r.json()["salidos"]) == 4
    db = SessionLocal()
    for fid in ids_ninos + [adulto_id]:
        assert db.query(PoolAccess).filter(PoolAccess.id == fid).first().exit_at is not None
    db.close()


def test_invitado_con_varios_ninos_sale_en_grupo(client):
    rid = _rid2(client)
    nombres = ["Pedrito Soto", "María Fe Soto"]
    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={"nombre": "Invitada Varios", "padrino_id": rid, "ninos": [{"nombre": n, "edad": 4} for n in nombres]},
    )
    assert r.status_code == 200

    db = SessionLocal()
    ninos = [db.query(PoolAccess).filter(PoolAccess.menor_nombre == n).first() for n in nombres]
    assert all(n is not None for n in ninos)
    filas_inv = {n.acompanante_acceso_id for n in ninos}
    assert len(filas_inv) == 1
    inv = db.query(PoolAccess).filter(PoolAccess.id == filas_inv.pop()).first()
    assert inv.persona_tipo == "invitado" and inv.invitado_nombre == "Invitada Varios"
    inv_id, ids_ninos = inv.id, [n.id for n in ninos]
    db.close()

    r = client.post(f"/api/piscina/salida/{inv_id}")
    assert r.status_code == 200
    assert len(r.json()["salidos"]) == 3
    db = SessionLocal()
    for fid in ids_ninos:
        assert db.query(PoolAccess).filter(PoolAccess.id == fid).first().exit_at is not None
    db.close()


def test_invitado_sin_ninos(client):
    rid = _rid2(client)
    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={"nombre": "Invitado Solo", "padrino_id": rid, "ninos": []},
    )
    assert r.status_code == 200


def test_nino_una_palabra_rechazado_en_ambos_ingresos(client):
    """Los niños se registran con nombres y apellidos, sean de residente o de invitado."""
    rid = _rid2(client)
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombre": "Juanito", "edad": 7}]},
    )
    assert r.status_code == 400
    assert "nombres y apellidos" in r.json()["detail"]

    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={"nombre": "Invitado Palabra", "padrino_id": rid, "ninos": [{"nombre": "Pedrito", "edad": 4}]},
    )
    assert r.status_code == 400
    assert "nombres y apellidos" in r.json()["detail"]


def test_maximo_ninos_rechazado(client):
    rid = _rid2(client)
    ninos = [{"nombre": f"Niño Prueba {i}", "edad": 5} for i in range(11)]
    r = client.post("/api/piscina/ingreso-nino", json={"acompanante_id": rid, "ninos": ninos})
    assert r.status_code == 400
    assert "Máximo" in r.json()["detail"]


def test_busqueda_residentes_disponible_para_piscina(client):
    """El guarda de piscina busca residentes (acompañante/padrino) sin 403."""
    _piscina(client)
    r = client.get("/api/residentes?q=Residenta")
    assert r.status_code == 200
    datos = r.json()["residentes"]
    assert datos and datos[0]["username"] == "residente1"


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
