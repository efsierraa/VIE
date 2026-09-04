import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect

from app.database import Base, SessionLocal, engine
from app.models import User
from app.routers import api, web

def _ensure_schema():
    """Crea tablas y columnas nuevas sin borrar datos existentes."""
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("users")}
    faltantes = {"nombres", "apellidos"} - cols
    if faltantes:
        with engine.begin() as conn:
            for col in faltantes:
                conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {col} VARCHAR(120)")
        with SessionLocal() as db:
            viejos = db.query(User).filter(User.nombres.is_(None) | User.apellidos.is_(None)).all()
            for u in viejos:
                partes = (u.full_name or "").strip().split(" ", 1)
                u.nombres = partes[0] or u.username
                u.apellidos = partes[1] if len(partes) > 1 else "-"
            db.commit()
    pkg_cols = {c["name"] for c in insp.get_columns("packages")}
    if "tercero" not in pkg_cols:
        # Postgres exige FALSE en un BOOLEAN; SQLite acepta 0
        falso = "FALSE" if engine.dialect.name == "postgresql" else "0"
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE packages ADD COLUMN tercero BOOLEAN DEFAULT {falso} NOT NULL")
            conn.exec_driver_sql("ALTER TABLE packages ADD COLUMN nombre_tercero VARCHAR(120)")
            conn.exec_driver_sql("ALTER TABLE packages ADD COLUMN cedula_tercero VARCHAR(30)")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_packages_cedula_tercero ON packages (cedula_tercero)"
            )
    faltan_destino = {"tower", "apartment"} - pkg_cols
    if faltan_destino:
        with engine.begin() as conn:
            for col in faltan_destino:
                conn.exec_driver_sql(f"ALTER TABLE packages ADD COLUMN {col} VARCHAR(10)")
    if "salida_auto" not in {c["name"] for c in insp.get_columns("visits")}:
        falso = "FALSE" if engine.dialect.name == "postgresql" else "0"
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE visits ADD COLUMN salida_auto BOOLEAN DEFAULT {falso} NOT NULL")
    vis_cols = {c["name"] for c in insp.get_columns("visits")}
    for col in ("visitor_nombres", "visitor_apellidos"):
        if col not in vis_cols:
            with engine.begin() as conn:
                conn.exec_driver_sql(f"ALTER TABLE visits ADD COLUMN {col} VARCHAR(80)")
    pkg_cols = {c["name"] for c in insp.get_columns("packages")}
    for col in ("tercero_nombres", "tercero_apellidos"):
        if col not in pkg_cols:
            with engine.begin() as conn:
                conn.exec_driver_sql(f"ALTER TABLE packages ADD COLUMN {col} VARCHAR(80)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_schema()
    with SessionLocal() as db:
        api.limpiar_fotos_vencidas(db)
        api.auto_finalizar_visitas(db)  # salida automática de visitas cuyo QR ya expiró
    yield


app = FastAPI(title="VIE — Vigilancia de Ingresos y Egresos", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web.router)
app.include_router(api.router)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    """Cabeceras básicas de seguridad en todas las respuestas."""
    respuesta = await call_next(request)
    h = respuesta.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(self), geolocation=(), payment=()")
    h.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; connect-src 'self'; "
        "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'",
    )
    if os.environ.get("VIE_COOKIE_SECURE") == "1":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return respuesta


@app.exception_handler(web.LoginRequired)
def login_required_handler(request: Request, exc: web.LoginRequired):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(web.PageForbidden)
def forbidden_handler(request: Request, exc: web.PageForbidden):
    return HTMLResponse(
        content=(
            "<!doctype html><html lang='es'><meta charset='utf-8'>"
            "<title>VIE — No autorizado</title>"
            "<link rel='stylesheet' href='/static/style.css'>"
            "<body><main class='card center'><h1>No autorizado</h1>"
            f"<p>{exc.user.nombre_completo}, tu rol no tiene acceso a esta sección.</p>"
            "<p><a href='/'>Volver</a></p></main></body>"
        ),
        status_code=403,
    )
