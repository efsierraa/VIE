import base64
import binascii
import csv
import io
import logging
import re
import secrets
from datetime import timedelta
from uuid import uuid4

import qrcode
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import hash_password, require_api, verify_password
from app.database import get_db
from app.limitador import registrar_intento, verificar_limite
from app.models import (
    DIAS_FOTO_ENTREGADA,
    HORAS_VISITA_MANUAL,
    MINUTOS_GRACIA_EDICION,
    ROLES,
    VALID_HOURS,
    VISITOR_ROLES,
    EditLog,
    Package,
    User,
    Visit,
)
from app.security import sign_package, sign_visit, verify_package_token, verify_token
from app.utils import format_duration, utcnow

router = APIRouter(prefix="/api")
log = logging.getLogger("vie")

# Sin letras ambiguas (I, L, O se confunden con 1, 0)
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _codigo_unico(db: Session, modelo) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not db.query(modelo).filter(modelo.short_code == code).first():
            return code


def new_short_code(db: Session) -> str:
    """Código corto de 6 caracteres, único, para digitar en portería."""
    return _codigo_unico(db, Visit)


def qr_data_uri(text: str) -> str:
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def qr_pase_data_uri(token: str, lineas: list[str]) -> str:
    """QR del pase con leyenda incrustada debajo: la imagen sola identifica el pase
    (código corto y de quién es) — imprescindible al compartir por WhatsApp."""
    qr = qrcode.make(token, box_size=6, border=2).convert("RGB")
    ancho = qr.width
    alto_leyenda = 28 * len(lineas) + 14
    lienzo = Image.new("RGB", (ancho, qr.height + alto_leyenda), "white")
    lienzo.paste(qr, (0, 0))
    dibujo = ImageDraw.Draw(lienzo)
    try:
        fuente = ImageFont.truetype("DejaVuSans-Bold.ttf", 19)
    except OSError:
        fuente = ImageFont.load_default()
    y = qr.height + 8
    for linea in lineas:
        caja = dibujo.textbbox((0, 0), linea, font=fuente)
        dibujo.text(((ancho - (caja[2] - caja[0])) // 2, y), linea, fill="black", font=fuente)
        y += 28
    buf = io.BytesIO()
    lienzo.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def visit_dict(v: Visit) -> dict:
    return {
        "id": v.id,
        "uuid": v.uuid,
        "short_code": v.short_code,
        "visitor_name": v.visitor_name,
        "visitor_nombres": v.visitor_nombres,
        "visitor_apellidos": v.visitor_apellidos,
        "visitor_celular": v.visitor_celular,
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


def resolver_nombre(nombres: str | None, apellidos: str | None, fallback: str | None = None) -> tuple[str, str | None, str | None]:
    """Dos campos obligatorios y claros: nombres y apellidos por separado.

    Devuelve (nombre completo, nombres, apellidos). El campo antiguo de nombre
    completo se acepta solo para compatibilidad con clientes anteriores.
    """
    n = (nombres or "").strip()
    a = (apellidos or "").strip()
    if n or a:
        if not n or not a:
            raise HTTPException(400, "Nombres y apellidos son obligatorios en campos separados")
        if len(n) > 80 or len(a) > 80:
            raise HTTPException(400, "Nombres o apellidos demasiado largos (máximo 80)")
        return f"{n} {a}", n, a
    completo = (fallback or "").strip()
    if not completo:
        raise HTTPException(400, "Nombres y apellidos son obligatorios en campos separados")
    return completo, None, None


def normalizar_celular(cel: str | None) -> str | None:
    """Celular opcional: solo dígitos; 10 dígitos (colombiano) lleva prefijo 57.

    Vacío → None (el campo nunca es obligatorio). Inválido → 400.
    """
    digitos = "".join(ch for ch in (cel or "") if ch.isdigit())
    if not digitos:
        return None
    if len(digitos) == 10:
        digitos = "57" + digitos
    if not 7 <= len(digitos) <= 15:
        raise HTTPException(400, "Número de celular no válido (7 a 15 dígitos)")
    return digitos


class VisitIn(BaseModel):
    visitor_nombres: str | None = None
    visitor_apellidos: str | None = None
    visitor_name: str | None = None  # compatibilidad: clientes antiguos
    visitor_celular: str | None = None  # opcional: activa "Enviar por WhatsApp"
    subject: str
    id_number: str | None = None
    visitor_role: str
    hours: int = 12


class ScanIn(BaseModel):
    token: str | None = None  # contenido del QR (código largo firmado)
    code: str | None = None  # código corto digitado por el guarda
    action: str  # entrada | salida


class ManualIn(BaseModel):
    visitor_nombres: str | None = None
    visitor_apellidos: str | None = None
    visitor_name: str | None = None  # compatibilidad: clientes antiguos
    visitor_celular: str | None = None  # opcional: activa "Enviar por WhatsApp"
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
    celular: str | None = None  # opcional


class PasswordAssign(BaseModel):
    nueva: str


class PasswordChange(BaseModel):
    actual: str
    nueva: str


class PerfilIn(BaseModel):
    celular: str | None = None  # opcional: cada quien actualiza el suyo


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
    celular: str | None = None,
    creado_por: str = "sistema",
) -> User:
    """Crea un usuario validando todo; levanta ValueError con el mensaje para el humano."""
    username = username.strip().lower()
    nombres = nombres.strip()
    apellidos = apellidos.strip()
    tower = (tower or "").strip().upper() or None
    apartment = (apartment or "").strip() or None
    if len(username) < 3:
        raise ValueError("El usuario debe tener al menos 3 caracteres")
    if len(password) < 8:
        raise ValueError("La clave debe tener al menos 8 caracteres")
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
        celular=normalizar_celular(celular),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("usuario_creado username=%s rol=%s por=%s", user.username, user.role, creado_por)
    return user


# --- Residente -------------------------------------------------------------


@router.post("/visits")
def create_visit(
    data: VisitIn,
    user: User = Depends(require_api("residente")),
    db: Session = Depends(get_db),
):
    visitor_name, v_nombres, v_apellidos = resolver_nombre(
        data.visitor_nombres, data.visitor_apellidos, data.visitor_name
    )
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
        visitor_nombres=v_nombres,
        visitor_apellidos=v_apellidos,
        visitor_celular=normalizar_celular(data.visitor_celular),
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
    return {
        "ok": True,
        "token": token,
        "qr_data_uri": qr_pase_data_uri(token, [f"Código: {visit.short_code}", f"Visitante: {visit.visitor_name}"]),
        "visit": visit_dict(visit),
    }


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
    user: User = Depends(require_api("residente", "guarda", "admin")),
    db: Session = Depends(get_db),
):
    """Vuelve a mostrar el pase (QR + código corto) de una visita pendiente o dentro.

    El residente solo las suyas; el guarda y administración, cualquier visita activa —
    para re-mostrar el pase cuando el visitante lo perdió. Una visita 'dentro'
    conserva el pase: el QR sirve para marcar la salida."""
    visit = db.query(Visit).filter(Visit.uuid == visit_uuid).first()
    if visit is None:
        raise HTTPException(404, "Visita no encontrada")
    if user.role == "residente" and visit.resident_id != user.id:
        raise HTTPException(404, "Visita no encontrada")
    if visit.status not in ("pendiente", "dentro"):
        raise HTTPException(400, "Este pase ya fue usado o cancelado")
    token = sign_visit(visit.uuid)
    return {
        "ok": True,
        "token": token,
        "qr_data_uri": qr_pase_data_uri(token, [f"Código: {visit.short_code}", f"Visitante: {visit.visitor_name}"]),
        "visit": visit_dict(visit),
    }


# --- Guarda ---------------------------------------------------------------


@router.post("/scan")
def scan(
    request: Request,
    data: ScanIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    verificar_limite(request, "scan", 120, 600)
    registrar_intento(request, "scan")
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

    return _procesar_visita(db, guard, visit, data.action)


def _procesar_visita(db: Session, guard: User, visit: Visit, action: str) -> dict:
    """Transiciones de estado de la visita: entrada y salida opcional."""
    now = utcnow()
    if visit.status == "pendiente":
        if now > visit.expires_at:
            raise HTTPException(400, "QR expirado")
        if action != "entrada":
            raise HTTPException(400, "El visitante aún no ha ingresado")
        visit.status = "dentro"
        visit.entry_at = now
        visit.entry_guard_id = guard.id
        db.commit()
        return {"ok": True, "message": "Entrada registrada", "visit": visit_dict(visit)}

    if visit.status == "dentro":
        if action != "salida":
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


@router.post("/scan/qr")
def escanear_qr(
    request: Request,
    data: ScanIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    """Un solo punto para la cámara: resuelve por la firma si el QR es de visita o de paquete."""
    verificar_limite(request, "scan", 120, 600)
    registrar_intento(request, "scan")
    if not data.token:
        raise HTTPException(400, "Falta el QR")

    visit_uuid = verify_token(data.token)
    if visit_uuid is not None:
        visit = db.query(Visit).filter(Visit.uuid == visit_uuid).first()
        if visit is not None:
            if data.action not in ("entrada", "salida"):
                raise HTTPException(400, "Acción no válida")
            return {**_procesar_visita(db, guard, visit, data.action), "tipo": "visita"}

    pkg_uuid = verify_package_token(data.token)
    if pkg_uuid is not None:
        pkg = db.query(Package).filter(Package.uuid == pkg_uuid).first()
        if pkg is None:
            raise HTTPException(400, "QR inválido o alterado")
        if pkg.status != "en_porteria":
            raise HTTPException(400, "Este paquete ya fue entregado o cancelado")
        if pkg.tercero:
            # el QR del tercero abre el reclamo con cédula: la foto ayuda a cotejar
            return {"tipo": "paquete", "ok": True, "package": package_dict(pkg, include_photo=True)}
        residente = db.get(User, pkg.resident_id)
        return {
            "tipo": "paquete",
            "ok": True,
            "package": package_dict(pkg, include_photo=True),
            "residente": {
                "nombre": residente.nombre_completo,
                "tower": residente.tower,
                "apartment": residente.apartment,
            },
        }

    raise HTTPException(400, "QR inválido o alterado")


@router.post("/visits/manual")
def manual_entry(
    data: ManualIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    visitor_name, v_nombres, v_apellidos = resolver_nombre(
        data.visitor_nombres, data.visitor_apellidos, data.visitor_name
    )
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
        visitor_nombres=v_nombres,
        visitor_apellidos=v_apellidos,
        visitor_celular=normalizar_celular(data.visitor_celular),
        subject=subject,
        id_number=(data.id_number or "").strip() or None,
        visitor_role=data.visitor_role,
        resident_id=guard.id,
        tower=tower,
        apartment=apartment,
        status="dentro",
        manual=True,
        expires_at=utcnow() + timedelta(hours=HORAS_VISITA_MANUAL),
        entry_at=utcnow(),
        entry_guard_id=guard.id,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    token = sign_visit(visit.uuid)
    return {
        "ok": True,
        "message": "Entrada manual registrada",
        "token": token,
        "qr_data_uri": qr_pase_data_uri(token, [f"Código: {visit.short_code}", f"Visitante: {visit.visitor_name}", "Vigente 1 hora"]),
        "visit": visit_dict(visit),
    }


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
            celular=data.celular,
            creado_por=admin.username,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.patch("/perfil")
def actualizar_perfil(
    data: PerfilIn,
    user: User = Depends(require_api("residente", "guarda", "admin")),
    db: Session = Depends(get_db),
):
    """Cada quien actualiza su propio celular (opcional). El resto de sus datos
    (nombres, torre, apto) solo los cambia administración."""
    nuevo = normalizar_celular(data.celular)
    cambios = []
    if (user.celular or "") != (nuevo or ""):
        cambios.append(f"celular: '{user.celular or ''}' → '{nuevo or ''}'")
    user.celular = nuevo
    _registrar_edicion(db, "usuario", user.username, user, cambios)
    db.commit()
    return {"ok": True, "celular": user.celular}


class EditarCuentaIn(BaseModel):
    nombres: str
    apellidos: str
    celular: str | None = None  # opcional
    tower: str | None = None
    apartment: str | None = None


@router.patch("/users/{user_id}/editar")
def editar_cuenta(
    user_id: int,
    data: EditarCuentaIn,
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    """Administración corrige una cuenta: nombres, apellidos, celular, torre y apartamento.

    El usuario y el rol no se tocan (son la identidad); la clave y el estado tienen
    sus propios controles. Toda edición queda en el control de ediciones."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Cuenta no encontrada")

    nombres = data.nombres.strip()
    apellidos = data.apellidos.strip()
    if not nombres or not apellidos:
        raise HTTPException(400, "Nombres y apellidos son obligatorios")
    if len(nombres) > 80 or len(apellidos) > 80:
        raise HTTPException(400, "Nombres o apellidos demasiado largos")
    tower = (data.tower or "").strip().upper() or None
    apartment = (data.apartment or "").strip() or None
    if user.role == "residente" and not (tower and apartment):
        raise HTTPException(400, "Un residente requiere torre y apartamento")
    celular = normalizar_celular(data.celular)

    cambios = []
    pares = (
        ("nombres", user.nombres, nombres),
        ("apellidos", user.apellidos, apellidos),
        ("celular", user.celular, celular),
        ("torre", user.tower, tower),
        ("apto", user.apartment, apartment),
    )
    for etiqueta, antes, despues in pares:
        if (antes or "") != (despues or ""):
            cambios.append(f"{etiqueta}: '{antes or ''}' → '{despues or ''}'")

    user.nombres = nombres
    user.apellidos = apellidos
    user.celular = celular
    user.tower = tower
    user.apartment = apartment
    _registrar_edicion(db, "usuario", user.username, admin, cambios)
    db.commit()
    log.info("cuenta_editada username=%s por=%s campos=%s", user.username, admin.username, len(cambios))
    return {"ok": True, "message": "Cuenta actualizada"}


@router.post("/users/csv")
async def import_users_csv(
    file: UploadFile = File(...),
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    """CSV con encabezado: nombres,apellidos,usuario,clave,rol,torre,apartamento (celular opcional)."""
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
    con_celular = len(encabezado) == 8 and encabezado[7] == "celular"
    if encabezado != esperado and not con_celular:
        raise HTTPException(400, "El CSV debe iniciar con la fila: " + ",".join(esperado) + " (celular opcional)")

    creados, errores = 0, []
    for num, fila in enumerate(filas[1:], start=2):
        if not any(c.strip() for c in fila):
            continue
        if len(fila) < 7:
            errores.append(f"línea {num}: faltan columnas")
            continue
        nombres, apellidos, username, clave, rol, torre, apto = (c.strip() for c in fila[:7])
        celular = fila[7].strip() if con_celular and len(fila) > 7 else None
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
                celular=celular,
                creado_por=f"{admin.username} (csv)",
            )
            creados += 1
        except ValueError as e:
            errores.append(f"línea {num}: {e}")
    log.info("csv_importado por=%s creados=%s errores=%s", admin.username, creados, len(errores))
    return {"ok": True, "creados": creados, "errores": errores}


@router.post("/users/{user_id}/password")
def assign_password(
    user_id: int,
    data: PasswordAssign,
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    """Asigna una clave nueva (las claves guardadas no se pueden ver, solo reemplazar)."""
    if len(data.nueva) < 8:
        raise HTTPException(400, "La clave debe tener al menos 8 caracteres")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    user.password_hash = hash_password(data.nueva)
    db.commit()
    log.info("clave_asignada admin=%s destino=%s", admin.username, user.username)
    return {"ok": True}


@router.post("/me/password")
def change_my_password(
    request: Request,
    data: PasswordChange,
    user: User = Depends(require_api()),
    db: Session = Depends(get_db),
):
    verificar_limite(request, "pw-me", 10, 600)
    if not verify_password(data.actual, user.password_hash):
        registrar_intento(request, "pw-me")
        log.warning("cambio_clave_fallado usuario=%s ip=%s", user.username, request.client.host if request.client else "?")
        raise HTTPException(400, "La clave actual es incorrecta")
    if len(data.nueva) < 8:
        raise HTTPException(400, "La nueva clave debe tener al menos 8 caracteres")
    user.password_hash = hash_password(data.nueva)
    db.commit()
    log.info("clave_cambiada usuario=%s", user.username)
    return {"ok": True}


# --- Paquetes ---------------------------------------------------------------

FOTO_MAX_BYTES = 2_000_000
FOTO_MIMES = ("image/jpeg", "image/png", "image/webp")


class PackageIn(BaseModel):
    resident_id: int
    description: str | None = None
    photo_b64: str  # data URI: data:image/jpeg;base64,xxx


class PackageScanIn(BaseModel):
    token: str | None = None  # QR del paquete (firmado con sal propia)
    code: str | None = None  # código corto digitado


def decodificar_foto(data_uri: str) -> tuple[bytes, str]:
    """Valida que sea una imagen real, quita EXIF (GPS, dispositivo) y reescala a JPEG.

    La re-codificación con Pillow es la barrera de verdad: aunque el cliente
    comprima, aquí se normaliza el tamaño y se elimina cualquier metadato.
    """
    from PIL import Image

    try:
        encabezado, b64 = data_uri.split(",", 1)
    except ValueError:
        raise ValueError("Formato de foto no válido")
    mime = encabezado[5:encabezado.find(";")] if encabezado.startswith("data:") and ";" in encabezado else "image/jpeg"
    if mime not in FOTO_MIMES:
        raise ValueError("Tipo de imagen no permitido")
    try:
        crudo = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Foto corrupta")
    if not crudo:
        raise ValueError("Foto vacía")
    if len(crudo) > FOTO_MAX_BYTES:
        raise ValueError("Foto demasiado grande")
    try:
        img = Image.open(io.BytesIO(crudo))
        img.load()
    except Exception:
        raise ValueError("El archivo no es una imagen válida")
    if img.format not in ("JPEG", "PNG", "WEBP"):
        raise ValueError("Tipo de imagen no permitido")

    img = img.convert("RGB")
    if max(img.size) > 1200:
        img.thumbnail((1200, 1200))
    salida = io.BytesIO()
    img.save(salida, "JPEG", quality=85)
    return salida.getvalue(), "image/jpeg"


def package_dict(p: Package, include_photo: bool = False, include_cedula: bool = False) -> dict:
    d = {
        "id": p.id,
        "uuid": p.uuid,
        "short_code": p.short_code,
        "description": p.description,
        "status": p.status,
        "tercero": p.tercero,
        "nombre_tercero": p.nombre_tercero,
        "tercero_nombres": p.tercero_nombres,
        "tercero_apellidos": p.tercero_apellidos,
        "tercero_celular": p.tercero_celular,
        "cedula_tercero": p.cedula_tercero,
        "tower": p.tower,
        "apartment": p.apartment,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "delivered_at": p.delivered_at.isoformat() if p.delivered_at else None,
        "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
        "resuelta_porteria": p.resuelta_porteria,
        "resuelta_residente": p.resuelta_residente,
        "resuelta_at": p.resuelta_at.isoformat() if p.resuelta_at else None,
        "photo_delete_after": p.photo_delete_after.isoformat() if p.photo_delete_after else None,
    }
    if include_photo and p.photo:
        d["photo_data_uri"] = f"data:{p.photo_mime};base64," + base64.b64encode(p.photo).decode()
    if include_cedula and p.foto_cedula:
        d["cedula_data_uri"] = "data:image/jpeg;base64," + base64.b64encode(p.foto_cedula).decode()
    return d


def asignar_codigos_faltantes(db: Session) -> int:
    """Asigna código corto a paquetes sin él (creados antes de que los tercero
    tuvieran QR de reclamo). Idempotente: los que ya tienen código no se tocan."""
    huerfanos = db.query(Package).filter(Package.short_code.is_(None)).all()
    for p in huerfanos:
        p.short_code = _codigo_unico(db, Package)
    if huerfanos:
        db.commit()
        log.info("codigos_asignados=%s", len(huerfanos))
    return len(huerfanos)


def auto_finalizar_visitas(db: Session) -> int:
    """Salida automática: una visita 'dentro' cuyo QR ya expiró se cierra sola.

    La hora de salida es la hora de expiración y queda la marca salida_auto
    para distinguirla de una salida marcada por el guarda.
    """
    vencidas = (
        db.query(Visit)
        .filter(Visit.status == "dentro", Visit.expires_at < utcnow())
        .all()
    )
    for v in vencidas:
        v.status = "finalizada"
        v.exit_at = v.expires_at
        v.salida_auto = True
    if vencidas:
        db.commit()
        log.info("salidas_automaticas=%s", len(vencidas))
    return len(vencidas)


def limpiar_fotos_vencidas(db: Session) -> int:
    """Borra las fotos cuyo plazo (30 días tras entrega) venció; el registro queda."""
    vencidos = (
        db.query(Package)
        .filter(
            Package.photo_delete_after.isnot(None),
            Package.photo_delete_after < utcnow(),
            Package.photo.isnot(None),
        )
        .all()
    )
    for p in vencidos:
        p.photo = None
        p.photo_mime = None
    if vencidos:
        db.commit()
    return len(vencidos)


@router.get("/packages/{package_uuid}/foto")
def foto_paquete(
    package_uuid: str,
    user: User = Depends(require_api("guarda", "admin")),
    db: Session = Depends(get_db),
):
    """La foto del paquete para cotejo. Se borra 30 días después de la entrega."""
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None:
        raise HTTPException(404, "Paquete no encontrado")
    if not pkg.photo:
        return HTMLResponse(
            content=(
                "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
                "<title>VIE — Imagen no disponible</title>"
                "<link rel='stylesheet' href='/static/style.css'></head>"
                "<body><main class='card narrow center'><h1>Imagen no disponible</h1>"
                "<p>La foto se borra 30 días después de la entrega para liberar espacio. "
                "El registro de la entrega permanece en el historial.</p>"
                "<p><a href='/'>Volver</a></p></main></body>"
            ),
            status_code=404,
        )
    return Response(content=pkg.photo, media_type=pkg.photo_mime or "image/jpeg")


# Torre y apto juntos: "T4 1005", "4 1005", "4-1005", "t4.1005". El apto siempre lleva dígitos.
TORRE_APTO_RE = re.compile(r"^(?:t([A-Za-z0-9]{1,3})|(\d{1,3}))[\s\-_.#]+([A-Za-z0-9]*\d[A-Za-z0-9]*)$", re.IGNORECASE)


@router.get("/residentes")
def buscar_residentes(
    q: str = "",
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.role == "residente", User.active.is_(True))
    q = q.strip()
    users = []
    if q:
        m = TORRE_APTO_RE.match(q)
        if m:
            # destino exacto: torre Y apartamento, nunca uno solo
            torre = (m.group(1) or m.group(2)).upper()
            apto = m.group(3)
            query = query.filter(func.upper(User.tower) == torre, User.apartment.ilike(apto))
            users = query.order_by(User.apartment, User.username).limit(10).all()
        else:
            # por nombre: cada palabra (con letras) debe aparecer en usuario, nombres o apellidos.
            # los números solos no buscan: apto o torre sin su par darían demasiados resultados
            tokens = [t for t in q.split() if not t.isdigit()]
            if tokens:
                for token in tokens:
                    like = f"%{token}%"
                    query = query.filter(
                        or_(
                            User.username.ilike(like),
                            User.nombres.ilike(like),
                            User.apellidos.ilike(like),
                        )
                    )
                users = query.order_by(User.tower, User.apartment, User.username).limit(10).all()
    return {
        "ok": True,
        "residentes": [
            {
                "id": u.id,
                "nombre": u.nombre_completo,
                "username": u.username,
                "tower": u.tower,
                "apartment": u.apartment,
            }
            for u in users
        ],
    }


@router.post("/packages")
def registrar_paquete(
    data: PackageIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    residente = db.get(User, data.resident_id)
    if residente is None or residente.role != "residente" or not residente.active:
        raise HTTPException(400, "Residente no válido")
    description = (data.description or "").strip() or None
    if description and len(description) > 200:
        raise HTTPException(400, "La descripción es demasiado larga")
    try:
        foto, mime = decodificar_foto(data.photo_b64)
    except ValueError as e:
        raise HTTPException(400, str(e))

    pkg = Package(
        uuid=str(uuid4()),
        short_code=_codigo_unico(db, Package),
        resident_id=residente.id,
        description=description,
        photo=foto,
        photo_mime=mime,
        tower=residente.tower,
        apartment=residente.apartment,
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return {"ok": True, "package": package_dict(pkg)}


@router.post("/packages/scan")
def escanear_paquete(
    request: Request,
    data: PackageScanIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    """Muestra el paquete con su foto; no marca nada hasta que el guarda confirme la entrega."""
    verificar_limite(request, "scan-pkg", 60, 600)
    registrar_intento(request, "scan-pkg")
    if data.code:
        pkg = db.query(Package).filter(Package.short_code == data.code.strip().upper()).first()
        if pkg is None:
            raise HTTPException(400, "Código de paquete no válido")
    else:
        if not data.token:
            raise HTTPException(400, "Falta el código o el QR del paquete")
        pkg_uuid = verify_package_token(data.token)
        if pkg_uuid is None:
            raise HTTPException(400, "QR de paquete inválido o alterado")
        pkg = db.query(Package).filter(Package.uuid == pkg_uuid).first()
        if pkg is None:
            raise HTTPException(400, "QR de paquete inválido o alterado")
    if pkg.status != "en_porteria":
        raise HTTPException(400, "Este paquete ya fue entregado o cancelado")
    if pkg.tercero:
        # el QR del tercero abre el reclamo con cédula: la foto ayuda a cotejar
        return {"ok": True, "package": package_dict(pkg, include_photo=True)}
    residente = db.get(User, pkg.resident_id)
    return {
        "ok": True,
        "package": package_dict(pkg, include_photo=True),
        "residente": {
            "nombre": residente.nombre_completo,
            "tower": residente.tower,
            "apartment": residente.apartment,
        },
    }


class PackageManualIn(BaseModel):
    nombres: str | None = None
    apellidos: str | None = None
    nombre: str | None = None  # compatibilidad: clientes antiguos
    celular: str | None = None  # opcional: celular de la etiqueta
    tower: str
    apartment: str
    description: str | None = None
    photo_b64: str


class EditarVisitaIn(BaseModel):
    visitor_nombres: str
    visitor_apellidos: str
    subject: str
    id_number: str | None = None
    visitor_role: str
    tower: str
    apartment: str
    visitor_celular: str | None = None  # opcional


class EditarPaqueteIn(BaseModel):
    nombres: str
    apellidos: str
    celular: str | None = None  # opcional
    tower: str
    apartment: str
    description: str | None = None


def _registrar_edicion(db: Session, entity_type: str, entity_uuid: str, editor: User, cambios: list[str]) -> None:
    """Guarda en el control de ediciones qué cambió, quién y cuándo."""
    if cambios:
        db.add(
            EditLog(
                entity_type=entity_type,
                entity_uuid=entity_uuid,
                editor_id=editor.id,
                cambios=" · ".join(cambios),
            )
        )


def _puede_editar(registrado_por: int | None, momento, user: User) -> bool:
    """El guarda edita solo lo suyo dentro del periodo de gracia; el admin, a voluntad."""
    if user.role == "admin":
        return True
    if registrado_por != user.id:
        return False
    return utcnow() - momento <= timedelta(minutes=MINUTOS_GRACIA_EDICION)


@router.patch("/visits/{visit_uuid}/editar")
def editar_visita(
    visit_uuid: str,
    data: EditarVisitaIn,
    user: User = Depends(require_api("guarda", "admin")),
    db: Session = Depends(get_db),
):
    """Edita una visita ingresada manualmente. El guarda solo lo suyo dentro de la
    hora de gracia; administración a voluntad. Toda edición queda registrada."""
    visit = db.query(Visit).filter(Visit.uuid == visit_uuid).first()
    if visit is None or not visit.manual:
        raise HTTPException(404, "Visita no encontrada o no editable (solo ingresos manuales)")
    momento = visit.entry_at or visit.created_at
    if not _puede_editar(visit.entry_guard_id or visit.resident_id, momento, user):
        if (visit.entry_guard_id or visit.resident_id) != user.id:
            raise HTTPException(403, "Solo quien registró la visita puede editarla (o administración)")
        raise HTTPException(400, "Pasó el periodo de gracia de 1 hora; pide a administración que la edite")

    completo, nombres, apellidos = resolver_nombre(data.visitor_nombres, data.visitor_apellidos)
    subject = data.subject.strip()
    tower = data.tower.strip().upper()
    apartment = data.apartment.strip()
    if not subject or not tower or not apartment:
        raise HTTPException(400, "Asunto, torre y apartamento son obligatorios")
    if len(subject) > 120 or len(tower) > 10 or len(apartment) > 10:
        raise HTTPException(400, "Campo demasiado largo")
    if data.visitor_role not in VISITOR_ROLES:
        raise HTTPException(400, "Rol de visitante no válido")
    id_number = (data.id_number or "").strip() or None
    celular = normalizar_celular(data.visitor_celular)

    cambios = []
    pares = (
        ("nombres", visit.visitor_nombres, nombres),
        ("apellidos", visit.visitor_apellidos, apellidos),
        ("asunto", visit.subject, subject),
        ("ID", visit.id_number, id_number),
        ("rol", visit.visitor_role, data.visitor_role),
        ("torre", visit.tower, tower),
        ("apto", visit.apartment, apartment),
        ("celular", visit.visitor_celular, celular),
    )
    for etiqueta, antes, despues in pares:
        if (antes or "") != (despues or ""):
            cambios.append(f"{etiqueta}: '{antes or ''}' → '{despues or ''}'")

    visit.visitor_nombres = nombres
    visit.visitor_apellidos = apellidos
    visit.visitor_name = completo
    visit.subject = subject
    visit.id_number = id_number
    visit.visitor_role = data.visitor_role
    visit.tower = tower
    visit.apartment = apartment
    visit.visitor_celular = celular
    _registrar_edicion(db, "visita", visit.uuid, user, cambios)
    db.commit()
    log.info("visita_editada uuid=%s por=%s campos=%s", visit.uuid, user.username, len(cambios))
    return {"ok": True, "message": "Visita actualizada", "visit": visit_dict(visit)}


@router.patch("/packages/{package_uuid}/editar")
def editar_paquete(
    package_uuid: str,
    data: EditarPaqueteIn,
    user: User = Depends(require_api("guarda", "admin")),
    db: Session = Depends(get_db),
):
    """Edita un paquete de tercero mientras sigue en portería. Solo cambia la
    información (nunca confirma la entrega). Mismas reglas de gracia."""
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None or not pkg.tercero:
        raise HTTPException(404, "Paquete no encontrado o no editable (solo terceros)")
    if pkg.status != "en_porteria":
        raise HTTPException(400, "El paquete ya fue entregado o cancelado: su información ya no se puede editar")
    if not _puede_editar(pkg.delivered_by or pkg.resident_id, pkg.created_at, user):
        if (pkg.delivered_by or pkg.resident_id) != user.id:
            raise HTTPException(403, "Solo quien registró el paquete puede editarlo (o administración)")
        raise HTTPException(400, "Pasó el periodo de gracia de 1 hora; pide a administración que lo edite")

    completo, nombres, apellidos = resolver_nombre(data.nombres, data.apellidos)
    tower = data.tower.strip().upper()
    apartment = data.apartment.strip()
    if not tower or not apartment:
        raise HTTPException(400, "Torre y apartamento son obligatorios")
    if len(tower) > 10 or len(apartment) > 10:
        raise HTTPException(400, "Torre o apartamento demasiado largos")
    description = (data.description or "").strip() or None
    if description and len(description) > 200:
        raise HTTPException(400, "La descripción es demasiado larga")
    celular = normalizar_celular(data.celular)

    cambios = []
    pares = (
        ("nombres", pkg.tercero_nombres, nombres),
        ("apellidos", pkg.tercero_apellidos, apellidos),
        ("celular", pkg.tercero_celular, celular),
        ("torre", pkg.tower, tower),
        ("apto", pkg.apartment, apartment),
        ("descripción", pkg.description, description),
    )
    for etiqueta, antes, despues in pares:
        if (antes or "") != (despues or ""):
            cambios.append(f"{etiqueta}: '{antes or ''}' → '{despues or ''}'")

    pkg.tercero_nombres = nombres
    pkg.tercero_apellidos = apellidos
    pkg.nombre_tercero = completo
    pkg.tercero_celular = celular
    pkg.tower = tower
    pkg.apartment = apartment
    pkg.description = description
    _registrar_edicion(db, "paquete", pkg.uuid, user, cambios)
    db.commit()
    log.info("paquete_editado uuid=%s por=%s campos=%s", pkg.uuid, user.username, len(cambios))
    return {"ok": True, "message": "Paquete actualizado", "package": package_dict(pkg)}


@router.post("/packages/manual")
def registrar_paquete_tercero(
    data: PackageManualIn,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    """Paquete para alguien sin cuenta: llega por transportadora. Se registran los nombres
    y apellidos del destinatario (dos campos, como en la etiqueta) y su destino
    (torre y apartamento de la etiqueta — obligatorios). Al reclamar se coteja el
    nombre con la cédula."""
    nombre, t_nombres, t_apellidos = resolver_nombre(data.nombres, data.apellidos, data.nombre)
    if len(nombre) > 120:
        raise HTTPException(400, "El nombre es demasiado largo")
    tower = data.tower.strip().upper()
    apartment = data.apartment.strip()
    if not tower or not apartment:
        raise HTTPException(400, "La torre y el apartamento del destinatario son obligatorios")
    if len(tower) > 10 or len(apartment) > 10:
        raise HTTPException(400, "Torre o apartamento demasiado largos")
    description = (data.description or "").strip() or None
    if description and len(description) > 200:
        raise HTTPException(400, "La descripción es demasiado larga")
    try:
        foto, mime = decodificar_foto(data.photo_b64)
    except ValueError as e:
        raise HTTPException(400, str(e))

    pkg = Package(
        uuid=str(uuid4()),
        short_code=_codigo_unico(db, Package),
        resident_id=guard.id,  # placeholder hasta que administración asigne un residente
        description=description,
        photo=foto,
        photo_mime=mime,
        tercero=True,
        nombre_tercero=nombre,
        tercero_nombres=t_nombres,
        tercero_apellidos=t_apellidos,
        tercero_celular=normalizar_celular(data.celular),
        tower=tower,
        apartment=apartment,
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    log.info("paquete_tercero_registrado nombre=%s por=%s", nombre, guard.username)
    token = sign_package(pkg.uuid)
    qr = qr_pase_data_uri(
        token,
        [f"Código: {pkg.short_code}", f"Paquete de: {nombre}", f"T{tower} · {apartment}"],
    )
    return {"ok": True, "token": token, "qr_data_uri": qr, "package": package_dict(pkg)}


@router.get("/packages/terceros")
def buscar_paquetes_terceros(
    q: str = "",
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    """Paquetes sin residente, en portería: buscar por nombre del destinatario."""
    query = db.query(Package).filter(Package.tercero.is_(True), Package.status == "en_porteria")
    q = q.strip()
    if q:
        query = query.filter(Package.nombre_tercero.ilike(f"%{q}%"))
    pkgs = query.order_by(Package.created_at.desc()).limit(10).all()
    return {"ok": True, "paquetes": [package_dict(p, include_photo=True) for p in pkgs]}


class AsignarIn(BaseModel):
    username: str


class EntregarIn(BaseModel):
    cedula: str | None = None  # para terceros: cédula de quien reclama (evidencia)


@router.post("/packages/{package_uuid}/asignar")
def asignar_paquete(
    package_uuid: str,
    data: AsignarIn,
    admin: User = Depends(require_api("admin")),
    db: Session = Depends(get_db),
):
    """Administración vincula el paquete con el residente nuevo.

    Si sigue en portería, gana QR y aparece en su app. Si ya se entregó,
    solo queda vinculado el registro para la trazabilidad del dueño real.
    """
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None:
        raise HTTPException(404, "Paquete no encontrado")
    if not pkg.tercero:
        raise HTTPException(400, "Este paquete ya tiene residente asignado")
    if pkg.status == "cancelado":
        raise HTTPException(400, "No se puede asignar un paquete cancelado")
    residente = (
        db.query(User)
        .filter(User.username == data.username.strip().lower(), User.role == "residente", User.active.is_(True))
        .first()
    )
    if residente is None:
        raise HTTPException(400, "Residente no encontrado o no válido")
    pkg.resident_id = residente.id
    pkg.tercero = False
    pkg.tower = residente.tower
    pkg.apartment = residente.apartment
    if pkg.status == "en_porteria":
        pkg.short_code = _codigo_unico(db, Package)
    db.commit()
    log.info(
        "paquete_asignado a=%s estado=%s por=%s",
        residente.username,
        pkg.status,
        admin.username,
    )
    return {"ok": True, "package": package_dict(pkg)}


@router.post("/packages/{package_uuid}/entregar")
def entregar_paquete(
    package_uuid: str,
    data: EntregarIn | None = None,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None:
        raise HTTPException(404, "Paquete no encontrado")
    if pkg.status != "en_porteria":
        raise HTTPException(400, "Este paquete ya fue entregado o cancelado")
    if pkg.tercero:
        # la cédula de quien reclama queda como evidencia; se coteja el nombre con la etiqueta
        cedula = (data.cedula or "").strip() if data else ""
        if not cedula:
            raise HTTPException(400, "Digita el número de cédula de quien reclama el paquete")
        if len(cedula) > 30:
            raise HTTPException(400, "Cédula demasiado larga")
        pkg.cedula_tercero = cedula
    pkg.status = "entregado"
    pkg.delivered_at = utcnow()
    pkg.delivered_by = guard.id
    pkg.photo_delete_after = utcnow() + timedelta(days=DIAS_FOTO_ENTREGADA)
    db.commit()
    log.info("paquete_entregado codigo=%s por=%s", pkg.short_code or pkg.nombre_tercero, guard.username)
    return {"ok": True, "package": package_dict(pkg)}


@router.post("/packages/{package_uuid}/cancelar")
def cancelar_paquete(
    package_uuid: str,
    guard: User = Depends(require_api("guarda")),
    db: Session = Depends(get_db),
):
    """Registro erróneo: cancela y borra la foto de inmediato."""
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None:
        raise HTTPException(404, "Paquete no encontrado")
    if pkg.status != "en_porteria":
        raise HTTPException(400, "Solo se puede cancelar un paquete en portería")
    pkg.status = "cancelado"
    pkg.photo = None
    pkg.photo_mime = None
    db.commit()
    log.info("paquete_cancelado codigo=%s por=%s", pkg.short_code, guard.username)
    return {"ok": True, "package": package_dict(pkg)}


@router.get("/packages/mine")
def mis_paquetes(user: User = Depends(require_api("residente")), db: Session = Depends(get_db)):
    pkgs = (
        db.query(Package)
        .filter(Package.resident_id == user.id)
        .order_by(Package.id.desc())
        .limit(20)
        .all()
    )
    out = []
    for p in pkgs:
        d = package_dict(p)
        if p.status == "en_porteria":
            if p.photo:
                d["photo_data_uri"] = f"data:{p.photo_mime};base64," + base64.b64encode(p.photo).decode()
            lineas = [f"Código: {p.short_code}"] if p.short_code else []
            lineas.append(f"Paquete de: {user.nombre_completo}")
            d["qr_data_uri"] = qr_pase_data_uri(sign_package(p.uuid), lineas)
        out.append(d)
    pendientes = sum(1 for p in pkgs if p.status == "en_porteria")
    return {"ok": True, "pendientes": pendientes, "packages": out}


@router.get("/packages/{package_uuid}/pass")
def paquete_pass(
    package_uuid: str,
    user: User = Depends(require_api("residente", "guarda", "admin")),
    db: Session = Depends(get_db),
):
    """QR de reclamo del paquete. El residente ve el suyo; el guarda y administración
    pueden re-mostrar el de cualquier paquete en portería (p. ej. perdido el WhatsApp)."""
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None:
        raise HTTPException(404, "Paquete no encontrado")
    if user.role == "residente" and pkg.resident_id != user.id:
        raise HTTPException(404, "Paquete no encontrado")
    if pkg.status != "en_porteria":
        raise HTTPException(400, "Este paquete ya fue entregado o cancelado")
    token = sign_package(pkg.uuid)
    lineas = []
    if pkg.short_code:
        lineas.append(f"Código: {pkg.short_code}")
    if pkg.tercero:
        lineas += [f"Paquete de: {pkg.nombre_tercero}", f"T{pkg.tower} · {pkg.apartment}"]
    else:
        residente = db.get(User, pkg.resident_id)
        lineas.append(f"Paquete de: {residente.nombre_completo if residente else '—'}")
    return {
        "ok": True,
        "token": token,
        "qr_data_uri": qr_pase_data_uri(token, lineas),
        "package": package_dict(pkg, include_photo=True),
    }


@router.post("/packages/{package_uuid}/confirmar")
def confirmar_paquete(
    package_uuid: str,
    user: User = Depends(require_api("residente")),
    db: Session = Depends(get_db),
):
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None or pkg.resident_id != user.id:
        raise HTTPException(404, "Paquete no encontrado")
    if pkg.status != "entregado":
        raise HTTPException(400, "Solo se puede confirmar un paquete entregado")
    pkg.status = "confirmado"
    pkg.confirmed_at = utcnow()
    db.commit()
    return {"ok": True, "package": package_dict(pkg)}


@router.post("/packages/{package_uuid}/disputar")
def disputar_paquete(
    package_uuid: str,
    user: User = Depends(require_api("residente")),
    db: Session = Depends(get_db),
):
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None or pkg.resident_id != user.id:
        raise HTTPException(404, "Paquete no encontrado")
    if pkg.status != "entregado":
        raise HTTPException(400, "Solo se puede disputar un paquete entregado")
    pkg.status = "disputa"
    db.commit()
    log.info("paquete_disputado uuid=%s por=%s", pkg.uuid, user.username)
    return {"ok": True, "package": package_dict(pkg)}


@router.post("/packages/{package_uuid}/resolver")
def resolver_disputa(
    package_uuid: str,
    user: User = Depends(require_api("residente", "guarda", "admin")),
    db: Session = Depends(get_db),
):
    """Resolución de una disputa a dos partes: portería (guarda o admin) y residente
    deben aceptar. Cuando ambos confirman, el paquete queda como recibido."""
    pkg = db.query(Package).filter(Package.uuid == package_uuid).first()
    if pkg is None:
        raise HTTPException(404, "Paquete no encontrado")
    if pkg.status != "disputa":
        raise HTTPException(400, "Solo un paquete en disputa se puede resolver")

    if user.role == "residente":
        if pkg.resident_id != user.id:
            raise HTTPException(403, "Solo el residente del paquete puede resolver su disputa")
        if pkg.resuelta_residente:
            raise HTTPException(400, "Ya confirmaste la resolución; falta la otra parte")
        pkg.resuelta_residente = True
        lado = "residente"
    else:
        if pkg.resuelta_porteria:
            raise HTTPException(400, "Portería ya confirmó la resolución; falta el residente")
        pkg.resuelta_porteria = True
        lado = "portería"

    _registrar_edicion(db, "paquete", pkg.uuid, user, [f"disputa: aceptada por {lado} ({user.username})"])
    ambos = pkg.resuelta_porteria and pkg.resuelta_residente
    if ambos:
        pkg.status = "confirmado"
        pkg.confirmed_at = utcnow()
        pkg.resuelta_at = utcnow()
        log.info("disputa_resuelta uuid=%s por=%s", pkg.uuid, user.username)
    db.commit()
    return {"ok": True, "resuelta": ambos, "package": package_dict(pkg)}


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
    log.info("cuenta_%s username=%s por=%s", "activada" if user.active else "desactivada", user.username, admin.username)
    return {"ok": True, "active": user.active}
