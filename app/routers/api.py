import base64
import csv
import io
import secrets
from datetime import timedelta
from uuid import uuid4

import qrcode
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import hash_password, require_api, verify_password
from app.database import get_db
from app.models import ROLES, VALID_HOURS, VISITOR_ROLES, User, Visit
from app.security import sign_visit, verify_token
from app.utils import format_duration, utcnow

router = APIRouter(prefix="/api")

# Sin letras ambiguas (I, L, O se confunden con 1, 0)
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_short_code(db: Session) -> str:
    """Código corto de 6 caracteres, único, para digitar en portería."""
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not db.query(Visit).filter(Visit.short_code == code).first():
            return code


def qr_data_uri(text: str) -> str:
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def visit_dict(v: Visit) -> dict:
    return {
        "id": v.id,
        "uuid": v.uuid,
        "short_code": v.short_code,
        "visitor_name": v.visitor_name,
        "subject": v.subject,
        "id_number": v.id_number,
        "visitor_role": v.visitor_role,
        "tower": v.tower,
        "apartment": v.apartment,
        "status": v.status,
        "manual": v.manual,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "expires_at": v.expires_at.isoformat() if v.expires_at else None,
        "entry_at": v.entry_at.isoformat() if v.entry_at else None,
        "exit_at": v.exit_at.isoformat() if v.exit_at else None,
    }


class VisitIn(BaseModel):
    visitor_name: str
    subject: str
    id_number: str | None = None
    visitor_role: str
    hours: int = 12


class ScanIn(BaseModel):
    token: str | None = None  # contenido del QR (código largo firmado)
    code: str | None = None  # código corto digitado por el guarda
    action: str  # entrada | salida


class ManualIn(BaseModel):
    visitor_name: str
    subject: str
    id_number: str | None = None
    visitor_role: str
    tower: str
    apartment: str


class UserIn(BaseModel):
    nombres: str
    apellidos: str
    username: str
    password: str
    role: str
    tower: str | None = None
    apartment: str | None = None


class PasswordAssign(BaseModel):
    nueva: str


class PasswordChange(BaseModel):
    actual: str
    nueva: str


def _crear_usuario(
    db: Session,
    *,
    nombres: str,
    apellidos: str,
    username: str,
    password: str,
    role: str,
    tower: str | None = None,
    apartment: str | None = None,
) -> User:
    """Crea un usuario validando todo; levanta ValueError con el mensaje para el humano."""
    username = username.strip().lower()
    nombres = nombres.strip()
    apellidos = apellidos.strip()
    tower = (tower or "").strip().upper() or None
    apartment = (apartment or "").strip() or None
    if len(username) < 3:
        raise ValueError("El usuario debe tener al menos 3 caracteres")
    if len(password) < 6:
        raise ValueError("La clave debe tener al menos 6 caracteres")
    if not nombres or not apellidos:
        raise ValueError("Nombres y apellidos son obligatorios")
    if role not in ROLES:
        raise ValueError("Rol no válido")
    if role == "residente" and not (tower and apartment):
        raise ValueError("Un residente requiere torre y apartamento")
    if db.query(User).filter(User.username == username).first():
        raise ValueError(f"El usuario '{username}' ya existe")
    user = User(
        username=username,
        password_hash=hash_password(password),
        nombres=nombres,
        apellidos=apellidos,
        role=role,
        tower=tower,
        apartment=apartment,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Residente -------------------------------------------------------------


@router.post("/visits")
def create_visit(
    data: VisitIn,
    user: User = Depends(require_api("residente")),
    db: Session = Depends(get_db),
):
    visitor_name = data.visitor_name.strip()
    subject = data.subject.strip()
    if not visitor_name or not subject:
        raise HTTPException(400, "Nombre y asunto son obligatorios")
    if data.visitor_role not in VISITOR_ROLES:
        raise HTTPException(400, "Rol de visitante no válido")
    if data.hours not in VALID_HOURS:
        raise HTTPException(400, "Vigencia no válida")
    if not user.tower or not user.apartment:
        raise HTTPException(400, "Tu cuenta no tiene torre/apartamento; pide a administración que la complete")

    visit = Visit(
        uuid=str(uuid4()),
        short_code=new_short_code(db),
        visitor_name=visitor_name,
        subject=subject,
        id_number=(data.id_number or "").strip() or None,
        visitor_role=data.visitor_role,
        resident_id=user.id,
        tower=user.tower,
        apartment=user.apartment,
        expires_at=utcnow() + timedelta(hours=data.hours),
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)

    token = sign_visit(visit.uuid)
    return {"ok": True, "token": token, "qr_data_uri": qr_data_uri(token), "visit": visit_dict(visit)}


@router.get("/visits/mine")
def my_visits(user: User = Depends(require_api("residente")), db: Session = Depends(get_db)):
    visits = (
        db.query(Visit)
        .filter(Visit.resident_id == user.id)
        .order_by(Visit.id.desc())
        .limit(20)
        .all()
    )
    return {"ok": True, "visits": [visit_dict(v) for v in visits]}


@router.post("/visits/{visit_uuid}/cancel")
def cancel_visit(
    visit_uuid: str,
    user: User = Depends(require_api("residente")),
    db: Session = Depends(get_db),
):
    visit = db.query(Visit).filter(Visit.uuid == visit_uuid).first()
    if visit is None or visit.resident_id != user.id:
        raise HTTPException(404, "Visita no encontrada")
    if visit.status != "pendiente":
        raise HTTPException(400, "Solo se puede cancelar una visita pendiente")
    visit.status = "cancelada"
    db.commit()
    return {"ok": True, "visit": visit_dict(visit)}


@router.get("/visits/{visit_uuid}/pass")
def visit_pass(
    visit_uuid: str,
    user: User = Depends(require_api("residente")),
    db: Session = Depends(get_db),
):
    """Vuelve a mostrar el pase (QR + código corto) de una visita pendiente."""
    visit = db.query(Visit).filter(Visit.uuid == visit_uuid).first()
    if visit is None or visit.resident_id != user.id:
        raise HTTPException(404, "Visita no encontrada")
    if visit.status != "pendiente":
        raise HTTPException(400, "Este pase ya fue usado o cancelado")
    token = sign_visit(visit.uuid)
    return {"ok": True, "token": token, "qr_data_uri": qr_data_uri(token), "visit": visit_dict(visit)}


# --- Guarda ---------------------------------------------------------------


@router.post("/scan")
def scan(
    data: ScanIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    if data.action not in ("entrada", "salida"):
        raise HTTPException(400, "Acción no válida")

    if data.code:
        visit = db.query(Visit).filter(Visit.short_code == data.code.strip().upper()).first()
        if visit is None:
            raise HTTPException(400, "Código corto no válido")
    else:
        if not data.token:
            raise HTTPException(400, "Falta el código o el QR")
        visit_uuid = verify_token(data.token)
        if visit_uuid is None:
            raise HTTPException(400, "QR inválido o alterado")
        visit = db.query(Visit).filter(Visit.uuid == visit_uuid).first()
        if visit is None:
            raise HTTPException(400, "QR inválido o alterado")

    now = utcnow()
    if visit.status == "pendiente":
        if now > visit.expires_at:
            raise HTTPException(400, "QR expirado")
        if data.action != "entrada":
            raise HTTPException(400, "El visitante aún no ha ingresado")
        visit.status = "dentro"
        visit.entry_at = now
        visit.entry_guard_id = guard.id
        db.commit()
        return {"ok": True, "message": "Entrada registrada", "visit": visit_dict(visit)}

    if visit.status == "dentro":
        if data.action != "salida":
            raise HTTPException(400, "El visitante ya ingresó; usa el modo salida")
        visit.status = "finalizada"
        visit.exit_at = now
        visit.exit_guard_id = guard.id
        db.commit()
        duration = format_duration(visit.exit_at - visit.entry_at) if visit.entry_at else "—"
        return {"ok": True, "message": f"Salida registrada · duración de la visita: {duration}", "visit": visit_dict(visit)}

    if visit.status == "finalizada":
        raise HTTPException(400, "Visita ya finalizada")
    raise HTTPException(400, "Visita cancelada")


@router.post("/visits/manual")
def manual_entry(
    data: ManualIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    visitor_name = data.visitor_name.strip()
    subject = data.subject.strip()
    tower = data.tower.strip().upper()
    apartment = data.apartment.strip()
    if not visitor_name or not subject or not tower or not apartment:
        raise HTTPException(400, "Nombre, asunto, torre y apartamento son obligatorios")
    if data.visitor_role not in VISITOR_ROLES:
        raise HTTPException(400, "Rol de visitante no válido")

    visit = Visit(
        uuid=str(uuid4()),
        short_code=new_short_code(db),
        visitor_name=visitor_name,
        subject=subject,
        id_number=(data.id_number or "").strip() or None,
        visitor_role=data.visitor_role,
        resident_id=guard.id,
        tower=tower,
        apartment=apartment,
        status="dentro",
        manual=True,
        expires_at=utcnow() + timedelta(hours=24),
        entry_at=utcnow(),
        entry_guard_id=guard.id,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return {"ok": True, "message": "Entrada manual registrada", "visit": visit_dict(visit)}


# --- Administración --------------------------------------------------------


@router.post("/users")
def create_user(
    data: UserIn,
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    try:
        _crear_usuario(
            db,
            nombres=data.nombres,
            apellidos=data.apellidos,
            username=data.username,
            password=data.password,
            role=data.role,
            tower=data.tower,
            apartment=data.apartment,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/users/csv")
async def import_users_csv(
    file: UploadFile = File(...),
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    """CSV con encabezado: nombres,apellidos,usuario,clave,rol,torre,apartamento."""
    raw = await file.read()
    try:
        texto = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = raw.decode("cp1252", errors="replace")
    filas = list(csv.reader(io.StringIO(texto)))
    if not filas:
        raise HTTPException(400, "El CSV está vacío")
    esperado = ["nombres", "apellidos", "usuario", "clave", "rol", "torre", "apartamento"]
    encabezado = [c.strip().lower() for c in filas[0]]
    if encabezado != esperado:
        raise HTTPException(400, "El CSV debe iniciar con la fila: " + ",".join(esperado))

    creados, errores = 0, []
    for num, fila in enumerate(filas[1:], start=2):
        if not any(c.strip() for c in fila):
            continue
        if len(fila) < 7:
            errores.append(f"línea {num}: faltan columnas")
            continue
        nombres, apellidos, username, clave, rol, torre, apto = (c.strip() for c in fila[:7])
        try:
            _crear_usuario(
                db,
                nombres=nombres,
                apellidos=apellidos,
                username=username,
                password=clave,
                role=rol,
                tower=torre,
                apartment=apto,
            )
            creados += 1
        except ValueError as e:
            errores.append(f"línea {num}: {e}")
    return {"ok": True, "creados": creados, "errores": errores}


@router.post("/users/{user_id}/password")
def assign_password(
    user_id: int,
    data: PasswordAssign,
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    """Asigna una clave nueva (las claves guardadas no se pueden ver, solo reemplazar)."""
    if len(data.nueva) < 6:
        raise HTTPException(400, "La clave debe tener al menos 6 caracteres")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    user.password_hash = hash_password(data.nueva)
    db.commit()
    return {"ok": True}


@router.post("/me/password")
def change_my_password(
    data: PasswordChange,
    user: User = Depends(require_api()),
    db: Session = Depends(get_db),
):
    if not verify_password(data.actual, user.password_hash):
        raise HTTPException(400, "La clave actual es incorrecta")
    if len(data.nueva) < 6:
        raise HTTPException(400, "La nueva clave debe tener al menos 6 caracteres")
    user.password_hash = hash_password(data.nueva)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/toggle")
def toggle_user(
    user_id: int,
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    if user.id == admin.id:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta")
    user.active = not user.active
    db.commit()
    return {"ok": True, "active": user.active}
