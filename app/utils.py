from datetime import datetime, timezone


def utcnow() -> datetime:
    """Hora UTC naive: un solo reloj para toda la app."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_duration(delta) -> str:
    """Duración legible: '2h 15min' o '40min'."""
    total_min = max(int(delta.total_seconds() // 60), 0)
    h, m = divmod(total_min, 60)
    return f"{h}h {m}min" if h else f"{m}min"
