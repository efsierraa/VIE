import os

import bcrypt
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

SESSION_COOKIE = "vie_session"
SESSION_MAX_AGE = 12 * 3600  # 12 horas
_serializer = URLSafeTimedSerializer(os.environ.get("VIE_SECRET", "dev-secret-change-me"), salt="vie-session-v1")

# Pre-autenticación 2FA: corta (5 min), no autoriza nada por sí sola
PRE2FA_COOKIE = "vie_pre2fa"
PRE2FA_MAX_AGE = 5 * 60
_pre2fa = URLSafeTimedSerializer(os.environ.get("VIE_SECRET", "dev-secret-change-me"), salt="vie-pre2fa-v1")


def enforce_admin_2fa() -> bool:
    """VIE_ENFORCE_ADMIN_2FA=0 lo desactiva (útil en tests). Por defecto exigido."""
    return os.environ.get("VIE_ENFORCE_ADMIN_2FA", "1") == "1"


def create_pre2fa(response, user_id: int) -> None:
    response.set_cookie(
        PRE2FA_COOKIE,
        _pre2fa.dumps({"uid": user_id}),
        max_age=PRE2FA_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("VIE_COOKIE_SECURE") == "1",
    )


def read_pre2fa(request: Request) -> int | None:
    token = request.cookies.get(PRE2FA_COOKIE)
    if not token:
        return None
    try:
        return int(_pre2fa.loads(token, max_age=PRE2FA_MAX_AGE).get("uid"))
    except (BadSignature, (TypeError, ValueError)):
        return None


def clear_pre2fa(response) -> None:
    response.delete_cookie(PRE2FA_COOKIE)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), password_hash.encode())
    except ValueError:
        return False


def create_session(response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        _serializer.dumps({"uid": user_id}),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("VIE_COOKIE_SECURE") == "1",
    )


def destroy_session(response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def current_user_or_none(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    user = db.get(User, data.get("uid"))
    return user if user and user.active else None


def require_api(*roles):
    """Dependencia para endpoints JSON: 401 sin sesión, 403 sin el rol."""

    def dep(request: Request, db: Session = Depends(get_db)) -> User:
        user = current_user_or_none(request, db)
        if user is None:
            raise HTTPException(status_code=401, detail="No autenticado")
        if roles and user.role not in roles:
            raise HTTPException(status_code=403, detail="No autorizado")
        return user

    return dep


class LoginRequired(Exception):
    pass


class PageForbidden(Exception):
    def __init__(self, user: User):
        self.user = user


def require_page(*roles):
    """Dependencia para páginas HTML: redirige a /login o muestra 403."""

    def dep(request: Request, db: Session = Depends(get_db)) -> User:
        user = current_user_or_none(request, db)
        if user is None:
            raise LoginRequired
        if roles and user.role not in roles:
            raise PageForbidden(user)
        return user

    return dep
