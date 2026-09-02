from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
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
from app.models import Visit, User
from app.utils import format_duration, utcnow

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
BOGOTA = ZoneInfo("America/Bogota")

HOME = {"admin": "/admin", "celador": "/celador", "residente": "/residente"}


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
    return {u.id: u.full_name for u in users}


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
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"user": None, "error": "Usuario o clave incorrectos"}
        )
    response = RedirectResponse(HOME[user.role], status_code=303)
    create_session(response, user.id)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    destroy_session(response)
    return response


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
    return templates.TemplateResponse(
        request, "residente.html", {"user": user, "visits": visits}
    )


# --- Celador -----------------------------------------------------------------


@router.get("/celador", response_class=HTMLResponse)
def celador_page(
    request: Request,
    user: User = Depends(require_page("celador")),
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
        "celador.html",
        {"user": user, "visits": visits, "names": name_map(db, visits)},
    )


# --- Administración ----------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    user: User = Depends(require_page("admin")),
    date: str | None = None,
    tower: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Visit)

    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            day = None
        if day:
            start_utc, end_utc = day_window_utc(day)
            query = query.filter(Visit.entry_at.isnot(None), Visit.entry_at >= start_utc, Visit.entry_at <= end_utc)
    if tower:
        query = query.filter(Visit.tower == tower.strip().upper())
    if status:
        query = query.filter(Visit.status == status)

    visits = query.order_by(Visit.id.desc()).limit(100).all()
    users = db.query(User).order_by(User.role, User.username).all()
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "visits": visits,
            "users": users,
            "names": name_map(db, visits),
            "f_date": date or "",
            "f_tower": tower or "",
            "f_status": status or "",
        },
    )
