"""Limitador de intentos en memoria: frena fuerza bruta sin depender de nada externo.

Suficiente para una instancia (el despliegue gratuito es una sola). Si algún día
hay varias instancias, cambiar por Redis o similar.
"""
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

HABILITADO = os.environ.get("VIE_RATE_LIMIT", "1") == "1"

_intentos: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _clave(request: Request, nombre: str) -> str:
    ip = request.client.host if request.client else "desconocida"
    return f"{ip}:{nombre}"


def verificar_limite(request: Request, nombre: str, max_intentos: int, ventana_seg: int) -> None:
    """Lanza 429 si ya se superó el máximo de intentos en la ventana."""
    if not HABILITADO:
        return
    k = _clave(request, nombre)
    ahora = time.time()
    with _lock:
        dq = _intentos.get(k)
        if dq is None:
            return
        while dq and dq[0] < ahora - ventana_seg:
            dq.popleft()
        if not dq:
            _intentos.pop(k, None)
            return
        if len(dq) >= max_intentos:
            raise HTTPException(429, "Demasiados intentos; espera unos minutos")


def registrar_intento(request: Request, nombre: str) -> None:
    """Suma un intento (para fallos de login/clave o cada escaneo)."""
    if not HABILITADO:
        return
    k = _clave(request, nombre)
    ahora = time.time()
    with _lock:
        dq = _intentos[k]
        while dq and dq[0] < ahora - 3600:
            dq.popleft()
        dq.append(ahora)
