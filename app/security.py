"""Firma y verificación del contenido del QR.

El QR no se cifra: lleva el uuid de la visita firmado con HMAC.
Cualquiera puede leerlo, nadie puede alterarlo. La vigencia y el
uso único se controlan en la base de datos, no en el papel del código.
"""
import os

from itsdangerous import BadSignature, TimestampSigner

SECRET = os.environ.get("VIE_SECRET", "dev-secret-change-me")
_signer = TimestampSigner(SECRET, salt="vie-qr-v1")
_pkg_signer = TimestampSigner(SECRET, salt="vie-pkg-v1")


def sign_visit(uuid: str) -> str:
    """Contenido del QR de visita (también el código de texto compartible)."""
    return _signer.sign(uuid.encode()).decode()


def verify_token(token: str) -> str | None:
    """Devuelve el uuid si la firma es válida; None si el QR está alterado."""
    try:
        return _signer.unsign(token.strip().encode()).decode()
    except BadSignature:
        return None


def sign_package(uuid: str) -> str:
    """Contenido del QR de paquete. Sal propia: un QR de visita no sirve como pase de paquete."""
    return _pkg_signer.sign(uuid.encode()).decode()


def verify_package_token(token: str) -> str | None:
    try:
        return _pkg_signer.unsign(token.strip().encode()).decode()
    except BadSignature:
        return None
