"""TOTP (RFC 6238) con la librería estándar: sin dependencias nuevas.

Obligatorio para admin (SOC2 CC6.1); opcional para guarda/residente.
Ventana ±1 paso (30s) para tolerar desfase de reloj.
Códigos de respaldo: 8 de un solo uso, hash SHA-256.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

PASO = 30
DIGITOS = 6
VENTANA = 1


def generar_secreto() -> str:
    """Secreto base32 de 160 bits para el QR de aprovisionamiento."""
    return base64.b32encode(secrets.token_bytes(20)).decode()


def _codigo(secreto: str, contador: int) -> str:
    clave = base64.b32decode(secreto.upper())
    msg = struct.pack(">Q", contador)
    digest = hmac.new(clave, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    num = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(num % (10**DIGITOS)).zfill(DIGITOS)


def verificar(secreto: str, codigo: str, ahora: float | None = None) -> bool:
    """Acepta el paso actual ± VENTANA. Comparación en tiempo constante."""
    codigo = (codigo or "").strip().replace(" ", "")
    if not codigo.isdigit() or len(codigo) != DIGITOS:
        return False
    t = int((ahora if ahora is not None else time.time()) // PASO)
    for delta in range(-VENTANA, VENTANA + 1):
        if hmac.compare_digest(_codigo(secreto, t + delta), codigo):
            return True
    return False


def uri_aprovisionamiento(secreto: str, usuario: str, emisor: str = "VIE") -> str:
    return (
        f"otpauth://totp/{quote(emisor)}:{quote(usuario)}"
        f"?secret={secreto}&issuer={quote(emisor)}&algorithm=SHA1&digits=6&period=30"
    )


def generar_respaldo(n: int = 8) -> list[str]:
    """Códigos de respaldo legibles: 8 grupos de 4+4 caracteres."""
    out = []
    alfabeto = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    for _ in range(n):
        out.append(
            "".join(secrets.choice(alfabeto) for _ in range(4))
            + "-"
            + "".join(secrets.choice(alfabeto) for _ in range(4))
        )
    return out


def hash_respaldo(codigo: str) -> str:
    normal = codigo.strip().upper().replace(" ", "")
    return hashlib.sha256(normal.encode()).hexdigest()
