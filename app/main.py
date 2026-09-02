from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import api, web


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
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
            f"<p>{exc.user.full_name}, tu rol no tiene acceso a esta sección.</p>"
            "<p><a href='/'>Volver</a></p></main></body>"
        ),
        status_code=403,
    )
