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
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_schema()
    with SessionLocal() as db:
        api.limpiar_fotos_vencidas(db)
    yield


app = FastAPI(title="VIE — Vigilancia de Ingresos y Egresos", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web.router)
app.include_router(api.router)


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
