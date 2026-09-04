import base64
import io
import logging
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode
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
from app.models import (
    MINUTOS_GRACIA_EDICION,
    PACKAGE_STATUS,
    VISIT_STATUS,
    EditLog,
    Package,
    Visit,
    User,
)
from app.routers.api import qr_data_uri
from app.security import sign_package
from app.utils import format_duration, utcnow

log = logging.getLogger("vie")
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
BOGOTA = ZoneInfo("America/Bogota")

HOME = {"admin": "/admin", "guarda": "/guarda/paquetes", "residente": "/residente"}
templates.env.globals["HOME"] = HOME  # el chip del usuario enlaza al inicio de su rol

NAVEGACION = {
    "guarda": [
        ("paquetes", "/guarda/paquetes", "Paquetes"),
        ("ingresos", "/guarda", "Ingresos"),
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


def es_extendida(v) -> bool:
    """Visita extendida: vigencia mayor a 24 horas."""
    if not v.expires_at or not v.created_at:
        return False
    return (v.expires_at - v.created_at) > timedelta(hours=24)


templates.env.filters["extendida"] = es_extendida


def editable_visita(v, user_id: int) -> bool:
    """El guarda puede editar su ingreso manual durante el periodo de gracia."""
    if not v.manual:
        return False
    if (v.entry_guard_id or v.resident_id) != user_id:
        return False
    momento = v.entry_at or v.created_at
    return utcnow() - momento <= timedelta(minutes=MINUTOS_GRACIA_EDICION)


def editable_paquete(p, user_id: int) -> bool:
    """El guarda puede editar su paquete de tercero mientras siga en portería."""
    if not p.tercero or p.status != "en_porteria":
        return False
    if (p.delivered_by or p.resident_id) != user_id:
        return False
    return utcnow() - p.created_at <= timedelta(minutes=MINUTOS_GRACIA_EDICION)


def editados_en(db: Session, uuids: set) -> set:
    """Uuids de la página que tienen al menos una edición registrada."""
    if not uuids:
        return set()
    return {row[0] for row in db.query(EditLog.entity_uuid).filter(EditLog.entity_uuid.in_(uuids)).all()}


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
        if p.tower and p.apartment:
            destino = f"T{p.tower} · {p.apartment}"  # el destino grabado en el paquete
        elif not p.tercero and residente:
            destino = f"T{residente.tower} · {residente.apartment}"  # registros viejos: perfil
        else:
            destino = ""
        out.append(
            {
                "p": p,
                "descripcion": p.description or "",
                "foto_disponible": p.photo is not None,
                "destinatario": (p.nombre_tercero or "—") if p.tercero else (residente.nombre_completo if residente else "—"),
                "cedula": p.cedula_tercero or "",
                "celular": (p.tercero_celular or "") if p.tercero else (residente.celular if residente else ""),
                "destino": destino,
                "entrego": usuarios[p.delivered_by].nombre_completo if p.delivered_by and p.delivered_by in usuarios else "",
            }
        )
    return out


def day_window_utc(day) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=BOGOTA).astimezone(timezone.utc).replace(tzinfo=None)
    end = datetime.combine(day, time.max, tzinfo=BOGOTA).astimezone(timezone.utc).replace(tzinfo=None)
    return start, end


# --- Paginación (server-side, estilo Google: Anterior · Página N · Siguiente) --


def _pagina(valor: str) -> int:
    try:
        return max(int(valor), 1)
    except (TypeError, ValueError):
        return 1


def paginar(query, pagina: int, por: int):
    """Slice de resultados sin COUNT: pide por+1 filas para saber si hay siguiente."""
    items = query.offset((pagina - 1) * por).limit(por + 1).all()
    return items[:por], pagina > 1, len(items) > por


def pager(pagina: int, anterior: bool, siguiente: bool, ruta: str, filtros: dict, clave: str) -> dict:
    """Contexto del paginador; los enlaces conservan todos los filtros."""
    limpios = {k: v for k, v in filtros.items() if v}
    return {
        "pagina": pagina,
        "anterior": anterior,
        "siguiente": siguiente,
        "url_anterior": ruta + "?" + urlencode({**limpios, clave: pagina - 1}),
        "url_siguiente": ruta + "?" + urlencode({**limpios, clave: pagina + 1}),
    }


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
    pagina_v: str = "1",
    pagina_p: str = "1",
    db: Session = Depends(get_db),
):
    visits, v_ant, v_sig = paginar(
        db.query(Visit).filter(Visit.resident_id == user.id).order_by(Visit.id.desc()),
        _pagina(pagina_v),
        25,
    )
    pkgs, p_ant, p_sig = paginar(
        db.query(Package).filter(Package.resident_id == user.id).order_by(Package.id.desc()),
        _pagina(pagina_p),
        25,
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
    pendientes = (
        db.query(Package)
        .filter(Package.resident_id == user.id, Package.status == "en_porteria")
        .count()
    )
    return templates.TemplateResponse(
        request,
        "residente.html",
        {
            "user": user,
            "visits": visits,
            "paquetes": paquetes,
            "pendientes": pendientes,
            "pager_v": pager(_pagina(pagina_v), v_ant, v_sig, "/residente", {}, "pagina_v"),
            "pager_p": pager(_pagina(pagina_p), p_ant, p_sig, "/residente", {}, "pagina_p"),
            "tabs": [],
        },
    )


# --- Guarda · Ingresos -------------------------------------------------------


@router.get("/guarda", response_class=HTMLResponse)
def guarda_page(
    request: Request,
    user: User = Depends(require_page("guarda")),
    pagina_h: str = "1",
    pagina_a: str = "1",
    q_activas: str = "",
    db: Session = Depends(get_db),
):
    today_local = utcnow().replace(tzinfo=timezone.utc).astimezone(BOGOTA).date()
    start_utc, _ = day_window_utc(today_local)
    ingresos, h_ant, h_sig = paginar(
        db.query(Visit)
        .filter(Visit.entry_at.isnot(None), Visit.entry_at >= start_utc)
        .order_by(Visit.entry_at.desc()),
        _pagina(pagina_h),
        50,
    )

    # Visitas activas: dentro del edificio y con QR aún vigente
    activas_q = db.query(Visit).filter(Visit.status == "dentro", Visit.expires_at > utcnow())
    q_a = q_activas.strip()
    if q_a:
        activas_q = activas_q.filter(Visit.visitor_name.ilike(f"%{q_a}%"))
    activas, a_ant, a_sig = paginar(activas_q.order_by(Visit.entry_at.desc()), _pagina(pagina_a), 25)

    return templates.TemplateResponse(
        request,
        "guarda.html",
        {
            "user": user,
            "visits": ingresos,
            "names": name_map(db, list(ingresos) + list(activas)),
            "activas": activas,
            "f_q_activas": q_activas,
            "editables": {v.uuid for v in list(ingresos) + list(activas) if editable_visita(v, user.id)},
            "editados": editados_en(db, {v.uuid for v in list(ingresos) + list(activas)}),
            "pager_h": pager(_pagina(pagina_h), h_ant, h_sig, "/guarda", {}, "pagina_h"),
            "pager_a": pager(_pagina(pagina_a), a_ant, a_sig, "/guarda", {"q_activas": q_a}, "pagina_a"),
            "tabs": nav_de("guarda", "ingresos"),
        },
    )


# --- Guarda · Paquetes -------------------------------------------------------


@router.get("/guarda/paquetes", response_class=HTMLResponse)
def guarda_paquetes_page(
    request: Request,
    user: User = Depends(require_page("guarda")),
    pagina: str = "1",
    pagina_e: str = "1",
    db: Session = Depends(get_db),
):
    pendientes, p_ant, p_sig = paginar(
        db.query(Package)
        .filter(Package.status == "en_porteria")
        .order_by(Package.created_at.desc()),
        _pagina(pagina),
        50,
    )
    today_local = utcnow().replace(tzinfo=timezone.utc).astimezone(BOGOTA).date()
    start_utc, _ = day_window_utc(today_local)
    entregados_hoy, e_ant, e_sig = paginar(
        db.query(Package)
        .filter(Package.delivered_at.isnot(None), Package.delivered_at >= start_utc)
        .order_by(Package.delivered_at.desc()),
        _pagina(pagina_e),
        50,
    )
    pend_items = paquetes_con_nombres(db, pendientes)
    ent_items = paquetes_con_nombres(db, entregados_hoy)
    return templates.TemplateResponse(
        request,
        "guarda_paquetes.html",
        {
            "user": user,
            "pendientes": pend_items,
            "entregados_hoy": ent_items,
            "editables": {i["p"].uuid for i in pend_items + ent_items if editable_paquete(i["p"], user.id)},
            "editados": editados_en(db, {i["p"].uuid for i in pend_items + ent_items}),
            "pager_p": pager(_pagina(pagina), p_ant, p_sig, "/guarda/paquetes", {}, "pagina"),
            "pager_e": pager(_pagina(pagina_e), e_ant, e_sig, "/guarda/paquetes", {}, "pagina_e"),
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


@router.get("/cuenta", response_class=HTMLResponse)
def cuenta_page(
    request: Request,
    user: User = Depends(require_page("admin", "guarda", "residente")),
):
    """Mi cuenta: celular propio y cambio de clave, para todos los roles."""
    return templates.TemplateResponse(
        request,
        "cuenta.html",
        {"user": user, "tabs": nav_de(user.role, "")},
    )


# --- Admin · Cuentas ---------------------------------------------------------


@router.get("/admin/cuentas", response_class=HTMLResponse)
def admin_cuentas_page(
    request: Request,
    user: User = Depends(require_page("admin")),
    q: str = "",
    pagina: str = "1",
    db: Session = Depends(get_db),
):
    query = db.query(User).order_by(User.role, User.username)
    if q.strip():
        for token in q.strip().split():
            like = f"%{token}%"
            query = query.filter(
                or_(User.username.ilike(like), User.nombres.ilike(like), User.apellidos.ilike(like))
            )
    users, u_ant, u_sig = paginar(query, _pagina(pagina), 50)
    return templates.TemplateResponse(
        request,
        "admin_cuentas.html",
        {
            "user": user,
            "users": users,
            "f_q": q,
            "pager_u": pager(_pagina(pagina), u_ant, u_sig, "/admin/cuentas", {"q": q}, "pagina"),
            "tabs": nav_de("admin", "cuentas"),
        },
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
    apto: str = "",
    pagina_v: str = "1",
    pagina_p: str = "1",
    pagina_ed: str = "1",
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
    pager_ingresos = pager(1, False, False, "/admin/historial", {}, "pagina_v")
    if ver_ingresos:
        query = db.query(Visit).order_by(Visit.id.desc())
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
        if apto.strip():
            query = query.filter(Visit.apartment == apto.strip())
        visits, v_ant, v_sig = paginar(query, _pagina(pagina_v), 50)
        pager_ingresos = pager(_pagina(pagina_v), v_ant, v_sig, "/admin/historial", {"tipo": tipo, "fecha": fecha, "estado": estado, "q": q, "torre": torre, "apto": apto}, "pagina_v")

    pkgs = []
    pager_paquetes = pager(1, False, False, "/admin/historial", {}, "pagina_p")
    if ver_paquetes:
        query = db.query(Package).order_by(Package.id.desc())
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
        if torre.strip():
            query = query.filter(Package.tower == torre.strip().upper())
        if apto.strip():
            query = query.filter(Package.apartment == apto.strip())
        pkgs, p_ant, p_sig = paginar(query, _pagina(pagina_p), 50)
        pager_paquetes = pager(_pagina(pagina_p), p_ant, p_sig, "/admin/historial", {"tipo": tipo, "fecha": fecha, "estado": estado, "q": q, "torre": torre, "apto": apto}, "pagina_p")

    paquetes_hist = paquetes_con_nombres(db, pkgs) if pkgs else []
    uids = {v.uuid for v in visits} | {i["p"].uuid for i in paquetes_hist}
    editados = editados_en(db, uids)

    # Control de ediciones: qué cambió, quién y cuándo
    logs, ed_ant, ed_sig = paginar(
        db.query(EditLog).order_by(EditLog.id.desc()),
        _pagina(pagina_ed),
        25,
    )
    pager_ed = pager(_pagina(pagina_ed), ed_ant, ed_sig, "/admin/historial", {"tipo": tipo}, "pagina_ed")
    l_uuids = {l.entity_uuid for l in logs}
    v_map = {v.uuid: v.visitor_name for v in db.query(Visit).filter(Visit.uuid.in_(l_uuids))} if l_uuids else {}
    pkgs_map = {p.uuid: p for p in db.query(Package).filter(Package.uuid.in_(l_uuids))} if l_uuids else {}
    uid_residentes = {p.resident_id for p in pkgs_map.values() if not p.tercero and p.resident_id}
    res_map = {u.id: u.nombre_completo for u in db.query(User).filter(User.id.in_(uid_residentes))} if uid_residentes else {}
    cuentas_map = {
        u.username: u.nombre_completo
        for u in db.query(User).filter(User.username.in_(l_uuids))
    } if l_uuids else {}

    def _etiqueta_paquete(p: Package) -> str:
        if p.tercero:
            nombre = p.nombre_tercero or "sin nombre en la etiqueta"
            sufijo = "no registrado"
        else:
            nombre = res_map.get(p.resident_id) or "residente sin asignar"
            sufijo = f"código {p.short_code}" if p.short_code else "sin código"
        return f"Paquete de {nombre} ({sufijo})"

    def _etiqueta_log(l: EditLog) -> str:
        if l.entity_type == "usuario":
            return f"Cuenta de {l.entity_uuid} — {cuentas_map.get(l.entity_uuid, '?')}"
        if l.entity_uuid in v_map:
            return "Visita de " + v_map[l.entity_uuid]
        if l.entity_uuid in pkgs_map:
            return _etiqueta_paquete(pkgs_map[l.entity_uuid])
        return "—"

    labels = {l.entity_uuid: _etiqueta_log(l) for l in logs}

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
            "paquetes_hist": paquetes_hist,
            "pager_ingresos": pager_ingresos,
            "pager_paquetes": pager_paquetes,
            "editados": editados,
            "logs": logs,
            "labels": labels,
            "pager_ed": pager_ed,
            "f_fecha": fecha,
            "f_estado": estado,
            "f_q": q,
            "f_torre": torre,
            "f_apto": apto,
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
                "Fecha entrada", "Hora entrada", "Visitante", "Identificación", "Celular", "Rol",
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
                    v.visitor_celular or "",
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
            "Fecha registro", "Destinatario", "Cédula", "Celular", "Torre", "Apartamento", "Descripción",
            "Estado", "Entregado", "Confirmado", "Entregó",
        ]
    )
    for p in pkgs:
        creado = p.created_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if p.created_at else None
        entregado = p.delivered_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if p.delivered_at else None
        confirmado = p.confirmed_at.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if p.confirmed_at else None
        if p.tercero:
            destinatario = (p.nombre_tercero or "") + " (no registrado)"
            celular = p.tercero_celular or ""
            torre, apto = p.tower or "", p.apartment or ""
        else:
            residente = usuarios.get(p.resident_id)
            destinatario = residente.nombre_completo if residente else ""
            celular = residente.celular if residente else ""
            torre = residente.tower if residente else ""
            apto = residente.apartment if residente else ""
        cedula = p.cedula_tercero or ""
        ws.append(
            [
                creado.strftime("%d/%m/%Y %H:%M") if creado else "",
                destinatario,
                cedula,
                celular,
                torre,
                apto,
                p.description or "",
                p.status,
                entregado.strftime("%d/%m/%Y %H:%M") if entregado else "",
                confirmado.strftime("%d/%m/%Y %H:%M") if confirmado else "",
                usuarios[p.delivered_by].nombre_completo if p.delivered_by and p.delivered_by in usuarios else "",
            ]
        )
