"""Paginación server-side: con cientos de registros nada desaparece en silencio."""
import base64
import uuid as uuid_mod
from datetime import timedelta
from io import BytesIO

from conftest import login

from app.database import SessionLocal
from app.models import Package, User, Visit
from app.utils import utcnow

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _visitas_masivas(residente_id, n, prefijo="Masiva"):
    """Inserta n visitas directo en la BD (rápido) con nombres Masiva 001..n.

    Con entrada registrada para que aparezcan en el export de ingresos.
    """
    db = SessionLocal()
    for i in range(1, n + 1):
        db.add(
            Visit(
                uuid=str(uuid_mod.uuid4()),
                visitor_name=f"{prefijo} {i:03d}",
                subject=f"visita {i}",
                visitor_role="visitante",
                resident_id=residente_id,
                tower="1",
                apartment="101",
                expires_at=utcnow() + timedelta(hours=1),
                entry_at=utcnow(),
                status="dentro",
            )
        )
    db.commit()
    db.close()


def _residente_id(username="residente1") -> int:
    db = SessionLocal()
    rid = db.query(User).filter(User.username == username).first().id
    db.close()
    return rid


def test_historial_admin_paginado(client):
    _visitas_masivas(_residente_id(), 55)

    login(client, "admin1")
    page1 = client.get("/admin/historial?tipo=ingresos")
    assert "Masiva 055" in page1.text  # la más reciente, primera página
    assert "Masiva 001" not in page1.text  # quedó en la página 2
    assert "Siguiente →" in page1.text

    page2 = client.get("/admin/historial?tipo=ingresos&pagina_v=2")
    assert "Masiva 001" in page2.text
    assert "Masiva 005" in page2.text  # las 5 más viejas de este lote caen en la página 2
    assert "← Anterior" in page2.text


def test_historial_filtros_y_pagina_combinados(client):
    _visitas_masivas(_residente_id(), 55)

    login(client, "admin1")
    # el filtro viaja con la página
    page = client.get("/admin/historial?tipo=ingresos&q=055")
    assert "Masiva 055" in page.text
    ingresos = page.text.split("Ingresos</h2>")[1].split("</section>")[0]
    assert "Siguiente →" not in ingresos  # pocas coincidencias: sin paginador en la tabla de ingresos
    # (el Control de ediciones, al pie de la página, tiene su propio paginador)

    # torre viaja también en los enlaces del paginador
    page = client.get("/admin/historial?tipo=ingresos&torre=1")
    assert "Masiva 055" in page.text
    assert "torre=1" in page.text


def test_residente_paginado(client):
    _visitas_masivas(_residente_id(), 30, prefijo="Residente Masiva")

    login(client, "residente1")
    page1 = client.get("/residente")
    assert "Residente Masiva 030" in page1.text  # la más reciente
    assert "Residente Masiva 001" not in page1.text
    assert "Siguiente →" in page1.text

    page2 = client.get("/residente?pagina_v=2")
    assert "Residente Masiva 001" in page2.text
    assert "← Anterior" in page2.text


def test_pendientes_guarda_paginado(client):
    gid = None
    login(client, "guarda1")
    db = SessionLocal()
    gid = db.query(User).filter(User.username == "guarda1").first().id
    for i in range(1, 56):
        db.add(
            Package(
                uuid=str(uuid_mod.uuid4()),
                resident_id=gid,
                tercero=True,
                nombre_tercero=f"Tercero {i:03d}",
                description=f"paquete {i}",
                photo=b"\xff\xd8fake",
                photo_mime="image/jpeg",
            )
        )
    db.commit()
    db.close()

    page1 = client.get("/guarda/paquetes")
    assert "Tercero 055" in page1.text
    assert "Tercero 001" not in page1.text
    assert "Siguiente →" in page1.text

    page2 = client.get("/guarda/paquetes?pagina=2")
    assert "Tercero 001" in page2.text
    assert "← Anterior" in page2.text


def test_export_no_se_pagina_trae_todo(client):
    _visitas_masivas(_residente_id(), 55)

    login(client, "admin1")
    r = client.get("/admin/exportar?ingresos=1")
    assert r.status_code == 200

    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(r.content))
    hoja = wb["Ingresos"]
    assert hoja.max_row >= 56  # encabezado + las 55 visitas, sin límite de página
