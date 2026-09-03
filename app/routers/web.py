import base64
import io
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import openpyxl
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import (
    LoginRequired,
    PageForbidden,
    create_session,
    current_user_or_none,
    destroy_session,
    require_page,
    verify_password,
)
from app.database import get_db
from app.limitador import registrar_intento, verificar_limite
from app.models import PACKAGE_STATUS, VISIT_STATUS, Package, Visit, User
from app.routers.api import qr_data_uri
from app.security import sign_package
from app.utils import format_duration, utcnow

log = logging.getLogger("vie")
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
BOGOTA = ZoneInfo("America/Bogota")

HOME = {"admin": "/admin", "guarda": "/guarda", "residente": "/residente"}

NAVEGACION = {
    "guarda": [
        ("ingresos", "/guarda", "Ingresos"),
        ("paquetes", "/guarda/paquetes", "Paquetes"),
    ],
    "admin": [
        ("inicio", "/admin", "Inicio"),
        ("cuentas", "/admin/cuentas", "Cuentas"),
        ("historial", "/admin/historial", "Historial"),
    ],
}


def nav_de(role: str, activa: str | None = None) -> list[dict]:
    return [
        {"url": url, "nombre": nombre, "activa": clave == activa}
        for clave, url, nombre in NAVEGACION.get(role, [])
    ]


def fmt_dt(dt) -> str:
    """Hora UTC guardada → hora local de Bogotá para mostrar."""
    if not dt:
        return "—"
    return dt.replace(tzinfo=timezone.utc).astimezone(BOGOTA).strftime("%d/%m %H:%M")


def fmt_date(dt) -> str:
    if not dt:
        return "—"
    return dt.replace(tzinfo=timezone.utc).astimezone(BOGOTA).strftime("%d/%m/%Y")


templates.env.filters["dt"] = fmt_dt
templates.env.filters["fdate"] = fmt_date
templates.env.filters["dur"] = format_duration


def name_map(db: Session, visits: list[Visit]) -> dict[int, str]:
    ids = {v.resident_id for v in visits} | {v.entry_guard_id for v in visits} | {v.exit_guard_id for v in visits}
    ids.discard(None)
    if not ids:
        return {}
    users = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: u.nombre_completo for u in users}


def paquetes_con_nombres(db: Session, pkgs: list[Package]) -> list[dict]:
    """Paquetes + datos listos para las tablas: destinatario, cédula, foto y quién entregó."""
    ids = {p.resident_id for p in pkgs} | {p.delivered_by for p in pkgs if p.delivered_by}
    usuarios = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    out = []
    for p in pkgs:
        residente = usuarios.get(p.resident_id)
        out.append(
            {
                "p": p,
                "descripcion": p.description or "",
                "foto_disponible": p.photo is not None,
                "destinatario": (p.nombre_tercero or "—") if p.tercero else (residente.nombre_completo if residente else "—"),
                "cedula": p.cedula_tercero or "",
                "destino": "" if p.tercero or not residente else f"T{residente.tower} · {residente.apartment}",
                "entrego": usuarios[p.delivered_by].nombre_completo if p.delivered_by and p.delivered_by in usuarios else "",
            }
        )
    return out


def day_window_utc(day) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=BOGOTA).astimezone(timezone.utc).replace(tzinfo=None)
    end = datetime.combine(day, time.max, tzinfo=BOGOTA).astimezone(timezone.utc).replace(tzinfo=None)
    return start, end


# --- Sesión ----------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_none(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse(HOME[user.role], status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_none(request, db)
    if user:
        return RedirectResponse(HOME[user.role], status_code=303)
    return templates.TemplateResponse(request, "login.html", {"user": None})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    verificar_limite(request, "login", 10, 600)
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    if user is None or not user.active or not verify_password(password, user.password_hash):
        registrar_intento(request, "login")
        log.warning("login_fallido ip=%s usuario=%s", request.client.host if request.client else "?", username)
        return templates.TemplateResponse(
            request, "login.html", {"user": None, "error": "Usuario o clave incorrectos"}
        )
    log.info("login_ok usuario=%s", user.username)
    response = RedirectResponse(HOME[user.role], status_code=303)
    create_session(response, user.id)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    destroy_session(response)
    return response


@router.get("/acerca", response_class=HTMLResponse)
def acerca_page(request: Request, db: Session = Depends(get_db)):
    """Pública: la historia, principios y cómo colaborar. Sin sesión también."""
    user = current_user_or_none(request, db)
    return templates.TemplateResponse(
        request,
        "acerca.html",
        {"user": user, "tabs": nav_de(user.role) if user else []},
    )


# --- Residente ---------------------------------------------------------------


@router.get("/residente", response_class=HTMLResponse)
def residente_page(
    request: Request,
    user: User = Depends(require_page("residente")),
    db: Session = Depends(get_db),
):
    visits = (
        db.query(Visit)
        .filter(Visit.resident_id == user.id)
        .order_by(Visit.id.desc())
        .limit(20)
        .all()
    )
    pkgs = (
        db.query(Package)
        .filter(Package.resident_id == user.id)
        .order_by(Package.id.desc())
        .limit(10)
        .all()
    )
    paquetes = []
    for p in pkgs:
        en_porteria = p.status == "en_porteria"
        paquetes.append(
            {
                "p": p,
                "photo": (
                    f"data:{p.photo_mime};base64," + base64.b64encode(p.photo).decode()
                    if en_porteria and p.photo
                    else None
                ),
                "qr": qr_data_uri(sign_package(p.uuid)) if en_porteria else None,
            }
        )
    pendientes = sum(1 for p in pkgs if p.status == "en_porteria")
    return templates.TemplateResponse(
        request,
        "residente.html",
        {"user": user, "visits": visits, "paquetes": paquetes, "pendientes": pendientes, "tabs": []},
    )


# --- Guarda · Ingresos -------------------------------------------------------


@router.get("/guarda", response_class=HTMLResponse)
def guarda_page(
    request: Request,
    user: User = Depends(require_page("guarda")),
    db: Session = Depends(get_db),
):
    today_local = utcnow().replace(tzinfo=timezone.utc).astimezone(BOGOTA).date()
    start_utc, _ = day_window_utc(today_local)
    visits = (
        db.query(Visit)
        .filter(Visit.entry_at.isnot(None), Visit.entry_at >= start_utc)
        .order_by(Visit.entry_at.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "guarda.html",
        {
            "user": user,
            "visits": visits,
            "names": name_map(db, visits),
            "tabs": nav_de("guarda", "ingresos"),
        },
    )


# --- Guarda · Paquetes -------------------------------------------------------


@router.get("/guarda/paquetes", response_class=HTMLResponse)
def guarda_paquetes_page(
    request: Request,
    user: User = Depends(require_page("guarda")),
    db: Session = Depends(get_db),
):
    pendientes = (
        db.query(Package)
        .filter(Package.status == "en_porteria")
        .order_by(Package.created_at.desc())
        .limit(50)
        .all()
    )
    today_local = utcnow().replace(tzinfo=timezone.utc).astimezone(BOGOTA).date()
    start_utc, _ = day_window_utc(today_local)
    entregados_hoy = (
        db.query(Package)
        .filter(Package.delivered_at.isnot(None), Package.delivered_at >= start_utc)
        .order_by(Package.delivered_at.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "guarda_paquetes.html",
        {
            "user": user,
            "pendientes": paquetes_con_nombres(db, pendientes),
            "entregados_hoy": paquetes_con_nombres(db, entregados_hoy),
            "tabs": nav_de("guarda", "paquetes"),
        },
    )


# --- Admin · Inicio (dashboard) ----------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    user: User = Depends(require_page("admin")),
    db: Session = Depends(get_db),
):
    today_local = utcnow().replace(tzinfo=timezone.utc).astimezone(BOGOTA).date()
    start_utc, _ = day_window_utc(today_local)
    stats = {
        "hoy": db.query(Visit).filter(Visit.entry_at.isnot(None), Visit.entry_at >= start_utc).count(),
        "dentro": db.query(Visit).filter(Visit.status == "dentro").count(),
        "pendientes": db.query(Visit).filter(Visit.status == "pendiente").count(),
        "paquetes": db.query(Package).filter(Package.status == "en_porteria").count(),
        "sin_residente": db.query(Package).filter(Package.tercero.is_(True), Package.status == "en_porteria").count(),
        "activos": db.query(User).filter(User.active.is_(True)).count(),
    }
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"user": user, "stats": stats, "tabs": nav_de("admin", "inicio")},
    )


# --- Admin · Cuentas ---------------------------------------------------------


@router.get("/admin/cuentas", response_class=HTMLResponse)
def admin_cuentas_page(
    request: Request,
    user: User = Depends(require_page("admin")),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.role, User.username).all()
    return templates.TemplateResponse(
        request,
        "admin_cuentas.html",
        {"user": user, "users": users, "tabs": nav_de("admin", "cuentas")},
    )


# --- Admin · Historial (unificado, con filtros adaptables) --------------------


@router.get("/admin/historial", response_class=HTMLResponse)
def admin_historial_page(
    request: Request,
    user: User = Depends(require_page("admin")),
    tipo: str = "ambos",
    fecha: str = "",
    estado: str = "",
    q: str = "",
    torre: str = "",
    db: Session = Depends(get_db),
):
    if tipo not in ("ingresos", "paquetes", "ambos"):
        tipo = "ambos"
    ver_ingresos = tipo in ("ingresos", "ambos")
    ver_paquetes = tipo in ("paquetes", "ambos")

    # un estado pertenece a un solo dominio: si se filtra por él, el otro dominio no aplica
    if estado:
        if estado in VISIT_STATUS and estado not in PACKAGE_STATUS:
            ver_paquetes = False
        if estado in PACKAGE_STATUS and estado not in VISIT_STATUS:
            ver_ingresos = False

    fecha_dia = None
    if fecha:
        try:
            fecha_dia = datetime.strptime(fecha, "%Y-%m-%d").date()
        except ValueError:
            fecha_dia = None

    visits = []
    if ver_ingresos:
        query = db.query(Visit)
        if fecha_dia:
            start_utc, end_utc = day_window_utc(fecha_dia)
            query = query.filter(Visit.entry_at.isnot(None), Visit.entry_at >= start_utc, Visit.entry_at <= end_utc)
        if estado and estado in VISIT_STATUS:
            query = query.filter(Visit.status == estado)
        if q.strip():
            for token in q.strip().split():
                like = f"%{token}%"
                query = query.filter(or_(Visit.visitor_name.ilike(like), Visit.subject.ilike(like)))
        if torre.strip():
            query = query.filter(Visit.tower == torre.strip().upper())
        visits = query.order_by(Visit.id.desc()).limit(100).all()

    pkgs = []
    if ver_paquetes:
        query = db.query(Package)
        if fecha_dia:
            start_utc, end_utc = day_window_utc(fecha_dia)
            query = query.filter(Package.created_at >= start_utc, Package.created_at <= end_utc)
        if estado and estado in PACKAGE_STATUS:
            query = query.filter(Package.status == estado)
        if q.strip():
            for token in q.strip().split():
                like = f"%{token}%"
                query = query.filter(
                    or_(
                        Package.nombre_tercero.ilike(like),
                        Package.description.ilike(like),
                        Package.short_code.ilike(like),
                    )
                )
        pkgs = query.order_by(Package.id.desc()).limit(100).all()

    return templates.TemplateResponse(
        request,
        "admin_historial.html",
        {
            "user": user,
            "tipo": tipo,
            "ver_ingresos": ver_ingresos,
            "ver_paquetes": ver_paquetes,
            "visits": visits,
            "names": name_map(db, visits) if visits else {},
            "paquetes_hist": paquetes_con_nombres(db, pkgs) if pkgs else [],
            "f_fecha": fecha,
            "f_estado": estado,
            "f_q": q,
            "f_torre": torre,
            "tabs": nav_de("admin", "historial"),
        },
    )


@router.get("/admin/exportar")
def exportar_visitas(
    user: User = Depends(require_page("admin")),
    ingresos: str = "",
    paquetes: str = "",
    desde: str = "",
    hasta: str = "",
    db: Session = Depends(get_db),
):
    quiere_ingresos = ingresos == "1"
    quiere_paquetes = paquetes == "1"
    if not (quiere_ingresos or quiere_paquetes):
        raise HTTPException(400, "Elige al menos una opción: ingresos o paquetes")

    hoy = utcnow().replace(tzinfo=timezone.utc).astimezone(BOGOTA).date()
    try:
        d1 = datetime.strptime(desde, "%Y-%m-%d").date() if desde else hoy - timedelta(days=30)
    except ValueError:
        d1 = hoy - timedelta(days=30)
    try:
        d2 = datetime.strptime(hasta, "%Y-%m-%d").date() if hasta else hoy
    except ValueError:
        d2 = hoy
    if d1 > d2:
        d1, d2 = d2, d1
    start_utc, end_utc = day_window_utc(d1)[0], day_window_utc(d2)[1]

    wb = openpyxl.Workbook()
    hoja_base = wb.active
    if not quiere_ingresos:
        wb.remove(hoja_base)  # sin hoja "Sheet" huérfana cuando se exporta solo paquetes
    if quiere_ingresos:
        visits = (
            db.query(Visit)
            .filter(Visit.entry_at.isnot(None), Visit.entry_at >= start_utc, Visit.entry_at <= end_utc)
            .order_by(Visit.entry_at)
            .all()
        )
        names = name_map(db, visits)
        hoja_base.title = "Ingresos"
        hoja_base.append(
            [
                "Fecha entrada", "Hora entrada", "Visitante", "Identificación", "Rol",
                "Asunto", "Torre", "Apartamento", "Autorizó", "Estado",
                "Hora salida", "Duración", "Registró", "Entrada manual",
            ]
        )
        for v in visits:
            entrada = v.entry_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA)
            salida = v.exit_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if v.exit_at else None
            dur = format_duration(v.exit_at - v.entry_at) if v.exit_at and v.entry_at else ""
            hoja_base.append(
                [
                    entrada.strftime("%d/%m/%Y"),
                    entrada.strftime("%H:%M"),
                    v.visitor_name,
                    v.id_number or "",
                    v.visitor_role,
                    v.subject,
                    v.tower,
                    v.apartment,
                    names.get(v.resident_id, ""),
                    v.status,
                    salida.strftime("%H:%M") if salida else "",
                    dur,
                    names.get(v.entry_guard_id, ""),
                    "sí" if v.manual else "no",
                ]
            )

    if quiere_paquetes:
        pkgs = (
            db.query(Package)
            .filter(Package.created_at >= start_utc, Package.created_at <= end_utc)
            .order_by(Package.created_at)
            .all()
        )
        ids_pkg = {p.resident_id for p in pkgs} | {p.delivered_by for p in pkgs if p.delivered_by}
        usuarios_pkg = {u.id: u for u in db.query(User).filter(User.id.in_(ids_pkg)).all()} if ids_pkg else {}
        _hoja_paquetes(wb, pkgs, usuarios_pkg)

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="vie_{d1.isoformat()}_{d2.isoformat()}.xlsx"'},
    )


def _hoja_paquetes(wb, pkgs, usuarios):
    ws = wb.create_sheet("Paquetes")
    ws.append(
        [
            "Fecha registro", "Destinatario", "Cédula", "Torre", "Apartamento", "Descripción",
            "Estado", "Entregado", "Confirmado", "Entregó",
        ]
    )
    for p in pkgs:
        creado = p.created_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if p.created_at else None
        entregado = p.delivered_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if p.delivered_at else None
        confirmado = p.confirmed_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if p.confirmed_at else None
        if p.tercero:
            destinatario = (p.nombre_tercero or "") + " (no registrado)"
            torre, apto = "", ""
        else:
            residente = usuarios.get(p.resident_id)
            destinatario = residente.nombre_completo if residente else ""
            torre = residente.tower if residente else ""
            apto = residente.apartment if residente else ""
        cedula = p.cedula_tercero or ""
        ws.append(
            [
                creado.strftime("%d/%m/%Y %H:%M") if creado else "",
                destinatario,
                cedula,
                torre,
                apto,
                p.description or "",
                p.status,
                entregado.strftime("%d/%m/%Y %H:%M") if entregado else "",
                confirmado.strftime("%d/%m/%Y %H:%M") if confirmado else "",
                usuarios[p.delivered_by].nombre_completo if p.delivered_by and p.delivered_by in usuarios else "",
            ]
        )
