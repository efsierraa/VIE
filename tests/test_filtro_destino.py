"""Filtro del historial admin por torre y/o apartamento, en ingresos y paquetes."""
import uuid as uuid_mod
from datetime import timedelta

from conftest import login

from app.database import SessionLocal
from app.models import Package, User, Visit
from app.utils import utcnow

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _sembrar_destinos():
    """Visitas en T1-101, T1-202, T2-202 y paquetes tercero con los mismos destinos."""
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    db.close()
    db = SessionLocal()
    for i, (t, a) in enumerate([("1", "101"), ("1", "202"), ("2", "202")]):
        db.add(
            Visit(
                uuid=str(uuid_mod.uuid4()),
                visitor_name=f"Destino {i}",
                subject=f"visita {t}-{a}",
                visitor_role="visitante",
                resident_id=rid,
                tower=t,
                apartment=a,
                expires_at=utcnow() + timedelta(hours=2),
                entry_at=utcnow(),
                status="dentro",
            )
        )
    for i, (t, a) in enumerate([("1", "101"), ("1", "202"), ("2", "202")]):
        db.add(
            Package(
                uuid=str(uuid_mod.uuid4()),
                resident_id=rid,
                tercero=True,
                nombre_tercero=f"Tercero {i}",
                tower=t,
                apartment=a,
                photo=b"\xff\xd8x",
                photo_mime="image/jpeg",
                status="entregado",
                delivered_at=utcnow(),
            )
        )
    db.commit()
    db.close()


def test_filtro_torre_y_apto_ingresos(client):
    _sembrar_destinos()
    login(client, "admin1")

    # torre sola: las dos de T1
    page = client.get("/admin/historial?tipo=ingresos&torre=1").text
    assert "Destino 0" in page and "Destino 1" in page
    assert "Destino 2" not in page

    # apartamento solo: las dos que terminan en 202
    page = client.get("/admin/historial?tipo=ingresos&apto=202").text
    assert "Destino 1" in page and "Destino 2" in page
    assert "Destino 0" not in page

    # torre + apartamento: solo la intersección
    page = client.get("/admin/historial?tipo=ingresos&torre=1&apto=202").text
    assert "Destino 1" in page
    assert "Destino 0" not in page and "Destino 2" not in page


def test_filtro_torre_y_apto_paquetes(client):
    _sembrar_destinos()
    login(client, "admin1")

    # torre sola (antes no filtraba paquetes)
    page = client.get("/admin/historial?tipo=paquetes&torre=1").text
    assert "Tercero 0" in page and "Tercero 1" in page
    assert "Tercero 2" not in page

    # apartamento solo
    page = client.get("/admin/historial?tipo=paquetes&apto=202").text
    assert "Tercero 1" in page and "Tercero 2" in page
    assert "Tercero 0" not in page

    # torre + apartamento
    page = client.get("/admin/historial?tipo=paquetes&torre=1&apto=101").text
    assert "Tercero 0" in page
    assert "Tercero 1" not in page and "Tercero 2" not in page


def test_filtro_preservado_en_paginador(client):
    _sembrar_destinos()
    login(client, "admin1")
    page = client.get("/admin/historial?tipo=ambos&torre=1&apto=101").text
    # los enlaces del paginador conservan torre y apto
    assert "torre=1" in page and "apto=101" in page


def test_inputs_de_filtro_en_la_plantilla(client):
    login(client, "admin1")
    page = client.get("/admin/historial?tipo=paquetes").text
    assert 'name="torre"' in page  # antes se ocultaba para paquetes
    assert 'name="apto"' in page
