"""Guarda de piscina: ingresos de adultos, niños con acompañante (nunca solos)
e invitados con padrino; salida en grupo; admin supervisa con filtros y Excel."""
import uuid as uuid_mod
from datetime import timedelta

import pytest

from conftest import login

from app.database import SessionLocal
from app.main import _ensure_schema
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
        json={"acompanante_id": rid, "ninos": [{"nombres": "Juanito", "apellidos": "Pérez", "edad": 7}]},
    )
    assert r.status_code == 200
    assert "Juanito" in r.json()["message"]

    db = SessionLocal()
    ninos = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Juanito Pérez").all()
    assert ninos and ninos[0].acompanante_acceso_id
    adulto = db.query(PoolAccess).filter(PoolAccess.id == ninos[0].acompanante_acceso_id).first()
    assert adulto.persona_tipo == "adulto" and adulto.exit_at is None
    db.close()


def test_nino_incompleto_y_acompanante_invalido_rechazados(client):
    rid = _piscina(client)
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombres": "", "apellidos": ""}]},
    )
    assert r.status_code == 400
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombres": "Juanito", "apellidos": "  "}]},
    )
    assert r.status_code == 400
    assert "apellidos" in r.json()["detail"]

    login(client, "piscina1")
    db = SessionLocal()
    gid = db.query(User).filter(User.username == "guarda1").first().id
    db.close()
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": gid, "ninos": [{"nombres": "Sin", "apellidos": "Acomp"}]},
    )
    assert r.status_code == 404  # el acompañante debe ser un residente


def test_ingreso_invitado_con_padrino_y_ninos(client):
    rid = _piscina(client)
    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={
            "nombres": "Visita",
            "apellidos": "Pool",
            "padrino_id": rid,
            "ninos": [{"nombres": "Nina", "apellidos": "Pool", "edad": 5}],
        },
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
    completos = ["Ana María Ruiz", "Luis Eduardo Ruiz", "Camila Ruiz"]
    partes = [("Ana María", "Ruiz"), ("Luis Eduardo", "Ruiz"), ("Camila", "Ruiz")]
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={
            "acompanante_id": rid,
            "ninos": [{"nombres": nom, "apellidos": ape, "edad": i + 5} for i, (nom, ape) in enumerate(partes)],
        },
    )
    assert r.status_code == 200
    for n in completos:
        assert n in r.json()["message"]

    db = SessionLocal()
    filas = [db.query(PoolAccess).filter(PoolAccess.menor_nombre == n).first() for n in completos]
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
    completos = ["Pedrito Soto", "María Fe Soto"]
    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={
            "nombres": "Invitada",
            "apellidos": "Varios",
            "padrino_id": rid,
            "ninos": [
                {"nombres": "Pedrito", "apellidos": "Soto", "edad": 4},
                {"nombres": "María Fe", "apellidos": "Soto", "edad": 9},
            ],
        },
    )
    assert r.status_code == 200

    db = SessionLocal()
    ninos = [db.query(PoolAccess).filter(PoolAccess.menor_nombre == n).first() for n in completos]
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
        json={"nombres": "Invitado", "apellidos": "Solo", "padrino_id": rid, "ninos": []},
    )
    assert r.status_code == 200


def test_nombres_incompletos_rechazados_en_ambos_ingresos(client):
    """Niños e invitados se registran con nombres y apellidos separados, ambos obligatorios."""
    rid = _rid2(client)
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombres": "Juanito", "apellidos": "", "edad": 7}]},
    )
    assert r.status_code == 400
    assert "apellidos" in r.json()["detail"]

    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={"nombres": "Invitado", "apellidos": "  ", "padrino_id": rid, "ninos": [{"nombres": "Pedrito", "apellidos": "", "edad": 4}]},
    )
    assert r.status_code == 400
    assert "apellidos" in r.json()["detail"]

    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={"nombres": "Invitado", "apellidos": "", "padrino_id": rid, "ninos": []},
    )
    assert r.status_code == 400


def test_maximo_ninos_rechazado(client):
    rid = _rid2(client)
    ninos = [{"nombres": "Niño", "apellidos": f"Prueba {i}", "edad": 5} for i in range(11)]
    r = client.post("/api/piscina/ingreso-nino", json={"acompanante_id": rid, "ninos": ninos})
    assert r.status_code == 400
    assert "Máximo" in r.json()["detail"]


def _cerrar_abiertos_de(rid: int):
    """Aísla pruebas: cierra las filas abiertas del residente (estado de tests previos)."""
    db = SessionLocal()
    for f in db.query(PoolAccess).filter(PoolAccess.resident_id == rid, PoolAccess.exit_at.is_(None)).all():
        f.exit_at = utcnow()
    db.commit()
    db.close()


def test_padrino_entra_aun_con_invitado_dentro(client):
    """El invitado dentro no cuenta como el padrino dentro: este puede entrar."""
    rid = _rid2(client)
    _cerrar_abiertos_de(rid)
    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={"nombres": "Invitado", "apellidos": "Anticipado", "padrino_id": rid, "ninos": []},
    )
    assert r.status_code == 200
    r = client.post("/api/piscina/ingreso", json={"resident_id": rid})
    assert r.status_code == 200
    assert "entró a la piscina" in r.json()["message"]


def test_ninos_del_residente_no_quedan_ligados_a_su_invitado(client):
    """Registrar niños del padrino con su invitado dentro no traslada los niños a la
    fila del invitado (era el bug del 'Salir con 4' con solo 2 niños)."""
    rid = _rid2(client)
    _cerrar_abiertos_de(rid)
    r = client.post(
        "/api/piscina/ingreso-invitado",
        json={
            "nombres": "Invitado",
            "apellidos": "Cofundido",
            "padrino_id": rid,
            "ninos": [{"nombres": "Nina", "apellidos": "Propia", "edad": 5}],
        },
    )
    assert r.status_code == 200

    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombres": "Hijo", "apellidos": "Del Padrino", "edad": 7}]},
    )
    assert r.status_code == 200

    db = SessionLocal()
    inv = db.query(PoolAccess).filter(
        PoolAccess.persona_tipo == "invitado", PoolAccess.invitado_nombre == "Invitado Cofundido"
    ).first()
    hijo = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Hijo Del Padrino").first()
    adulto = db.query(PoolAccess).filter(PoolAccess.id == hijo.acompanante_acceso_id).first()
    assert hijo.acompanante_acceso_id != inv.id
    assert adulto.persona_tipo == "adulto" and adulto.resident_id == rid
    nina = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Nina Propia").first()
    assert nina.acompanante_acceso_id == inv.id  # la niña del invitado sigue con él
    db.close()


def test_invitado_duplicado_rechazado(client):
    """El mismo invitado no entra dos veces: el reintento se rechaza con aviso claro."""
    rid = _rid2(client)
    _cerrar_abiertos_de(rid)
    datos = {"nombres": "Doble", "apellidos": "Invitado", "padrino_id": rid, "ninos": []}
    assert client.post("/api/piscina/ingreso-invitado", json=datos).status_code == 200
    r = client.post("/api/piscina/ingreso-invitado", json=datos)
    assert r.status_code == 400
    assert "ya está en la piscina" in r.json()["detail"]


def test_nino_repetido_rechazado_y_mixto_avisa(client):
    """Reintentar un niño ya dentro no lo duplica: todo-repetido rechaza, mixto entra
    solo el nuevo y avisa cuáles ya estaban."""
    rid = _rid2(client)
    _cerrar_abiertos_de(rid)
    nino = {"nombres": "Doble", "apellidos": "Nino", "edad": 6}
    r = client.post("/api/piscina/ingreso-nino", json={"acompanante_id": rid, "ninos": [nino]})
    assert r.status_code == 200

    r = client.post("/api/piscina/ingreso-nino", json={"acompanante_id": rid, "ninos": [dict(nino)]})
    assert r.status_code == 400
    assert "están en la piscina" in r.json()["detail"]

    db = SessionLocal()
    cuantos = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Doble Nino", PoolAccess.exit_at.is_(None)).count()
    db.close()
    assert cuantos == 1

    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [dict(nino), {"nombres": "Nueva", "apellidos": "Nina", "edad": 4}]},
    )
    assert r.status_code == 200
    assert "ya estaban dentro: Doble Nino" in r.json()["message"]
    assert "Nueva Nina" in r.json()["message"]


def test_migracion_limpia_duplicados_y_bloquea_nuevos(client):
    """La migración elimina niños abiertos duplicados (conserva el más viejo) y el
    índice único bloquea todo reintento que llegue hasta la BD, aunque dos
    peticiones competan por insertar."""
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente2").first().id
    adulto = PoolAccess(persona_tipo="adulto", resident_id=rid, tower="2", apartment="202")
    db.add(adulto)
    db.flush()
    original = PoolAccess(persona_tipo="nino", resident_id=rid, acompanante_acceso_id=adulto.id, menor_nombre="Duplicado Test", tower="2", apartment="202")
    gemelo = PoolAccess(persona_tipo="nino", resident_id=rid, acompanante_acceso_id=adulto.id, menor_nombre="Duplicado Test", tower="2", apartment="202")
    db.add_all([original, gemelo])
    db.commit()
    id_viejo, id_nuevo = original.id, gemelo.id
    db.close()

    _ensure_schema()

    db = SessionLocal()
    quedan = db.query(PoolAccess).filter(PoolAccess.menor_nombre == "Duplicado Test").all()
    assert [f.id for f in quedan] == [id_viejo]
    with pytest.raises(Exception):
        db.add(PoolAccess(persona_tipo="nino", resident_id=rid, acompanante_acceso_id=adulto.id, menor_nombre="Duplicado Test", tower="2", apartment="202"))
        db.commit()
    db.rollback()
    db.close()


def test_busqueda_pool_por_destino_y_nombres(client):
    """El buscador de 'En la piscina ahora' encuentra por T·apto y por nombres
    (niño, invitado o acompañante); número sin su par no arroja resultados."""
    rid = _rid2(client)
    _cerrar_abiertos_de(rid)
    db = SessionLocal()
    u = db.query(User).filter(User.id == rid).first()
    destino = f"T{u.tower} {u.apartment}"  # administración puede haber movido al residente en otros tests
    db.close()
    client.post("/api/piscina/ingreso", json={"resident_id": rid})
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombres": "Busca", "apellidos": "Mucho", "edad": 5}]},
    )
    assert r.status_code == 200

    login(client, "piscina1")
    page = client.get("/piscina", params={"q": destino}).text
    assert "Busca Mucho" in page
    assert "Piscina vacía" not in page

    page = client.get("/piscina", params={"q": "Busca"}).text  # nombre del niño
    assert "Busca Mucho" in page

    page = client.get("/piscina", params={"q": "Residente Dos"}).text  # acompañante residente
    assert "Busca Mucho" in page

    page = client.get("/piscina", params={"q": "202"}).text  # apto sin torre: nada
    assert "Piscina vacía" in page

    page = client.get("/piscina").text
    assert "Busca Mucho" in page


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
    assert ">Niño<" in page  # la etiqueta del tipo lleva la ñ, no el valor crudo "nino"

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


def test_contador_salida_sin_duplicar(client):
    """Un niño abierto aparece en activos y en hoy; el botón debe contar la fila
    una sola vez: 'Salir con 1' (el bug contaba 2 por procesar la fila dos veces)."""
    rid = _rid2(client)
    _cerrar_abiertos_de(rid)
    client.post("/api/piscina/ingreso", json={"resident_id": rid})
    r = client.post(
        "/api/piscina/ingreso-nino",
        json={"acompanante_id": rid, "ninos": [{"nombres": "Unica", "apellidos": "Cuenta", "edad": 6}]},
    )
    assert r.status_code == 200

    login(client, "piscina1")
    page = client.get("/piscina").text
    assert "Salir con 1" in page
    assert "Salir con 2" not in page
