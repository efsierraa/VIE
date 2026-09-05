import json
import logging
import os
import time
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.models import User
from app.routers import api, web


class _JsonFormatter(logging.Formatter):
    """Logs JSON a stdout: Render los recoge; retención 7 días en plan gratis."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
                "level": record.levelname.lower(),
                "logger": record.name,
                "msg": record.getMessage(),
            },
            ensure_ascii=False,
        )


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
_vie_log = logging.getLogger("vie")
_vie_log.handlers = [_handler]
_vie_log.setLevel(logging.INFO)
_vie_log.propagate = False

def _relajar_full_name_legado(eng) -> bool:
    """full_name es legado: en la BD vieja (Postgres) quedó NOT NULL y provoca
    NotNullViolation en todo INSERT de usuario nuevo (SQLite no la exige)."""
    if eng.dialect.name != "postgresql":
        return False
    col = next((c for c in inspect(eng).get_columns("users") if c["name"] == "full_name"), None)
    if col is None or col["nullable"]:
        return False
    with eng.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE users ALTER COLUMN full_name DROP NOT NULL")
    return True


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
    _relajar_full_name_legado(engine)
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
    if "visitor_celular" not in vis_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE visits ADD COLUMN visitor_celular VARCHAR(20)")
    pkg_cols = {c["name"] for c in insp.get_columns("packages")}
    for col in ("tercero_nombres", "tercero_apellidos"):
        if col not in pkg_cols:
            with engine.begin() as conn:
                conn.exec_driver_sql(f"ALTER TABLE packages ADD COLUMN {col} VARCHAR(80)")
    if "tercero_celular" not in pkg_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE packages ADD COLUMN tercero_celular VARCHAR(20)")
    usr_cols = {c["name"] for c in insp.get_columns("users")}
    if "celular" not in usr_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN celular VARCHAR(20)")
    # 2FA TOTP (SOC2 CC6.1)
    if "totp_secret" not in usr_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN totp_secret VARCHAR(64)")
    if "totp_enabled" not in usr_cols:
        falso = "FALSE" if engine.dialect.name == "postgresql" else "0"
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT {falso} NOT NULL")
    if "totp_backup_hashes" not in usr_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN totp_backup_hashes TEXT")
    faltan_resolucion = {"resuelta_porteria", "resuelta_residente", "resuelta_at"} - pkg_cols
    if faltan_resolucion:
        falso = "FALSE" if engine.dialect.name == "postgresql" else "0"
        with engine.begin() as conn:
            for col in faltan_resolucion:
                if col == "resuelta_at":
                    conn.exec_driver_sql("ALTER TABLE packages ADD COLUMN resuelta_at TIMESTAMP")
                else:
                    conn.exec_driver_sql(f"ALTER TABLE packages ADD COLUMN {col} BOOLEAN DEFAULT {falso} NOT NULL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_schema()
    with SessionLocal() as db:
        api.limpiar_fotos_vencidas(db)
        api.auto_finalizar_visitas(db)  # salida automática de visitas cuyo QR ya expiró
        api.asignar_codigos_faltantes(db)  # paquetes viejos sin código (tercero pre-QR)
        api.purgar_visitas_antiguas(db)  # SOC2/CC + habeas data: retención 12 meses
    yield


app = FastAPI(title="VIE — Vigilancia de Ingresos y Egresos", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web.router)
app.include_router(api.router)


@app.middleware("http")
async def request_id(request: Request, call_next):
    """Propaga X-Request-Id para correlacionar logs y respuestas."""
    rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    respuesta = await call_next(request)
    respuesta.headers["X-Request-Id"] = rid
    return respuesta


@app.get("/health")
def health() -> JSONResponse:
    """Salud pública para Render/uptime: app + base de datos."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return JSONResponse({"ok": True, "db": "up"})
    except Exception:
        _vie_log.warning("health_db_down")
        return JSONResponse({"ok": False, "db": "down"}, status_code=503)


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


@app.exception_handler(Exception)
async def error_interno(request: Request, exc: Exception):
    """Última red: un error no manejado queda en el log con traceback y contexto,
    y el cliente recibe JSON (nunca HTML) para que el JS no rompa parseando."""
    rid = request.headers.get("X-Request-Id", "?")
    _vie_log.error(
        "error_interno rid=%s metodo=%s ruta=%s traza=%s",
        rid,
        request.method,
        request.url.path,
        traceback.format_exc(limit=8),
    )
    return JSONResponse({"detail": "Error interno del servidor"}, status_code=500)
