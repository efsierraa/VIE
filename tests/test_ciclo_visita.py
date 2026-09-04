"""Ciclo de vida completo de la visita: salida automática, visitas extendidas y activas."""
import uuid as uuid_mod
from datetime import timedelta

from conftest import login

from app.database import SessionLocal
from app.models import Package, User, Visit
from app.routers.api import auto_finalizar_visitas
from app.utils import utcnow

FOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _visita_dentro_vencida(client, nombre="Olvidada", horas=2) -> dict:
    """Visita que entró y cuyo QR ya expiró sin que nadie marcara la salida."""
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": nombre, "subject": "x", "visitor_role": "visitante", "hours": horas},
    )
    visit = r.json()["visit"]
    login(client, "guarda1")
    r = client.post("/api/scan", json={"code": visit["short_code"], "action": "entrada"})
    assert r.status_code == 200

    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    v.expires_at = utcnow() - timedelta(minutes=5)  # forzar la expiración
    db.commit()
    db.close()
    return visit


def test_salida_automatica_al_expirar(client):
    visit = _visita_dentro_vencida(client, "Olvidada Auto")

    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    assert v.status == "dentro"  # aún no hay nadie que la cierre
    db.close()

    cerradas = auto_finalizar_visitas(SessionLocal())
    assert cerradas >= 1

    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    assert v.status == "finalizada"
    assert v.exit_at == v.expires_at  # la salida queda a la hora de expiración
    assert v.salida_auto is True  # marca auditable de salida automática
    db.close()

    # una salida manual ya no procede
    login(client, "guarda1")
    r = client.post("/api/scan", json={"code": visit["short_code"], "action": "salida"})
    assert r.status_code == 400
    assert "finalizada" in r.json()["detail"]


def test_activas_y_stats_excluyen_vencidas(client):
    login(client, "guarda1")
    _visita_dentro_vencida(client, "Vencida Activa")

    # entre arranques, la lista de activas ya la excluye (filtro perezoso)
    page = client.get("/guarda")
    assert "Vencida Activa" not in page.text.split("Visitas activas")[1].split("</section>")[0]


def test_visita_extendida_no_se_cierra_antes(client):
    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": "Visita Larga", "subject": "familia de visita", "visitor_role": "visitante", "hours": 168},
    )
    assert r.status_code == 200
    visit = r.json()["visit"]
    login(client, "guarda1")
    client.post("/api/scan", json={"code": visit["short_code"], "action": "entrada"})

    # la salida automática no la toca: su vigencia es de 7 días
    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    assert v.status == "dentro" and v.salida_auto is False
    db.close()

    # aparece en la lista de activas, marcada como extendida
    page = client.get("/guarda")
    assert "Visita Larga" in page.text.split("Visitas activas")[1].split("</section>")[0]
    assert "extendida" in page.text


def test_busqueda_de_activas_por_nombre(client):
    login(client, "residente1")
    for nombre in ("Ana Activa", "Beto Activo"):
        r = client.post(
            "/api/visits",
            json={"visitor_name": nombre, "subject": "x", "visitor_role": "visitante", "hours": 8},
        )
        visit = r.json()["visit"]
        login(client, "guarda1")
        client.post("/api/scan", json={"code": visit["short_code"], "action": "entrada"})
        login(client, "residente1")

    login(client, "guarda1")
    page = client.get("/guarda?q_activas=Ana")
    activas = page.text.split("Visitas activas")[1].split("</section>")[0]
    assert "Ana Activa" in activas
    assert "Beto Activo" not in activas


def _visitas_hoy_masivas(n, prefijo="Hoy"):
    """Visitas que ingresaron hoy, directo en la BD."""
    db = SessionLocal()
    rid = db.query(User).filter(User.username == "residente1").first().id
    for i in range(1, n + 1):
        db.add(
            Visit(
                uuid=str(uuid_mod.uuid4()),
                visitor_name=f"{prefijo} {i:03d}",
                subject=f"visita {i}",
                visitor_role="visitante",
                resident_id=rid,
                tower="1",
                apartment="101",
                expires_at=utcnow() + timedelta(hours=2),
                entry_at=utcnow(),
                status="dentro",
            )
        )
    db.commit()
    db.close()


def test_paginacion_ingresos_de_hoy(client):
    prefijo = "Hoy" + uuid_mod.uuid4().hex[:6].upper()  # único por corrida: la sesión comparte BD
    _visitas_hoy_masivas(55, prefijo=prefijo)

    login(client, "guarda1")
    page1 = client.get("/guarda")
    assert f"{prefijo} 055" in page1.text  # la más reciente, primera página
    assert f"{prefijo} 001" not in page1.text
    assert "Siguiente →" in page1.text

    page2 = client.get(f"/guarda?pagina_h=2")
    assert f"{prefijo} 001" in page2.text
    assert "← Anterior" in page2.text


def test_paginacion_activas(client):
    _visitas_hoy_masivas(30, prefijo="Activa Masiva")

    login(client, "guarda1")
    page1 = client.get("/guarda?pagina_a=1")
    activas = page1.text.split("Visitas activas")[1].split("</section>")[0]
    assert "Siguiente →" in activas

    page2 = client.get("/guarda?pagina_a=2")
    activas2 = page2.text.split("Visitas activas")[1].split("</section>")[0]
    assert "← Anterior" in activas2


def test_paginacion_entregados_hoy_paquetes(client):
    login(client, "guarda1")
    db = SessionLocal()
    gid = db.query(User).filter(User.username == "guarda1").first().id
    for i in range(1, 56):
        db.add(
            Package(
                uuid=str(uuid_mod.uuid4()),
                resident_id=gid,
                tercero=True,
                nombre_tercero=f"Entregado Hoy {i:03d}",
                tower="1",
                apartment="101",
                photo=b"\xff\xd8x",
                photo_mime="image/jpeg",
                status="entregado",
                delivered_at=utcnow(),
                delivered_by=gid,
            )
        )
    db.commit()
    db.close()

    page1 = client.get("/guarda/paquetes?pagina_e=1")
    assert "Entregado Hoy 055" in page1.text
    assert "Siguiente →" in page1.text

    page2 = client.get("/guarda/paquetes?pagina_e=2")
    assert "Entregado Hoy 001" in page2.text


def test_export_incluye_salida_automatica(client):
    import openpyxl
    from io import BytesIO

    login(client, "residente1")
    r = client.post(
        "/api/visits",
        json={"visitor_name": "Salida Auto Export", "subject": "x", "visitor_role": "visitante", "hours": 2},
    )
    visit = r.json()["visit"]
    login(client, "guarda1")
    client.post("/api/scan", json={"code": visit["short_code"], "action": "entrada"})
    db = SessionLocal()
    v = db.query(Visit).filter(Visit.uuid == visit["uuid"]).first()
    v.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()
    auto_finalizar_visitas(SessionLocal())

    login(client, "admin1")
    r = client.get("/admin/exportar?ingresos=1")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.content))
    hoja = wb["Ingresos"]
    fila_auto = None
    for fila in hoja.iter_rows(min_row=2, values_only=True):
        if fila[2] == "Salida Auto Export":
            fila_auto = fila
            break
    assert fila_auto is not None
    assert fila_auto[10]  # hora de salida registrada aunque fuera automática
