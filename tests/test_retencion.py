from datetime import timedelta
from uuid import uuid4

from tests.conftest import login


def _visita(db, estado="finalizada", dias=400):
    from app.models import Visit
    from app.utils import utcnow

    ahora = utcnow()
    v = Visit(
        uuid=str(uuid4()),
        short_code=None,
        visitor_name="Visita Vieja",
        visitor_nombres="Visita",
        visitor_apellidos="Vieja",
        subject="prueba retención",
        visitor_role="visitante",
        resident_id=1,
        tower="1",
        apartment="101",
        status=estado,
        created_at=ahora - timedelta(days=dias),
        expires_at=ahora - timedelta(days=dias - 1),
        entry_at=ahora - timedelta(days=dias),
        exit_at=ahora - timedelta(days=dias) + timedelta(hours=1),
    )
    db.add(v)
    db.commit()
    return v.uuid


def test_purga_solo_terminal_antigua(client):
    from app.database import SessionLocal
    from app.models import Visit
    from app.routers.api import purgar_visitas_antiguas

    login(client, "admin1")
    with SessionLocal() as db:
        uuid_vieja = _visita(db, "finalizada", 400)
        uuid_cancel = _visita(db, "cancelada", 500)
        uuid_reciente = _visita(db, "finalizada", 10)
        uuid_dentro = _visita(db, "dentro", 400)
        n = purgar_visitas_antiguas(db, meses=12)
        assert n >= 2
        assert db.query(Visit).filter(Visit.uuid == uuid_vieja).first() is None
        assert db.query(Visit).filter(Visit.uuid == uuid_cancel).first() is None
        assert db.query(Visit).filter(Visit.uuid == uuid_reciente).first() is not None
        assert db.query(Visit).filter(Visit.uuid == uuid_dentro).first() is not None


def test_endpoint_manual_requiere_admin(client):
    from tests.conftest import login as _login

    # sin sesión -> 401
    r = client.post("/api/admin/retencion/ejecutar")
    assert r.status_code == 401
    _login(client, "admin1")
    r2 = client.post("/api/admin/retencion/ejecutar")
    assert r2.status_code == 200
    assert "purgadas" in r2.json()
