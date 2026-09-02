# VIE — Vigilancia de Ingresos y Egresos

> **El control de acceso de tu edificio, en un escaneo.**
> App gratuita y open source para que el residente genere un pase QR de un solo uso, lo comparta por cualquier canal y el celador valide el ingreso en segundos.

Ver [pitch.md](pitch.md) para la idea completa, objetivos e impacto.

## Cómo funciona

1. **Residente**: crea una visita (nombre, asunto, ID opcional, rol) y recibe un **QR de un solo uso** — imagen y código de texto — para compartir por cualquier app.
2. **Celador**: escanea el QR en portería (o digita el código) → registra la **entrada**. Un segundo escaneo opcional marca la **salida** y calcula la duración de la visita.
3. **Administración**: crea las cuentas y supervisa el **historial completo** de ingresos con filtros.

Si la app falla, el celador registra a mano (entrada manual) o se vuelve al método de siempre: llamar y anotar.

## Stack

- **Backend**: Python + FastAPI, SQLAlchemy, SQLite (dev) / Postgres (prod)
- **Frontend**: Jinja2 + CSS propio, sin frameworks. PWA instalable en Android
- **QR**: firmado con HMAC (itsdangerous), uso único validado en el servidor
- **Tests**: pytest

## Desarrollo local

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# crear el primer administrador
.venv\Scripts\python seed_admin.py --usuario admin --clave una-clave-segura --nombre "Administración"

# levantar el servidor
.venv\Scripts\python -m uvicorn app.main:app --reload
```

Abrir http://127.0.0.1:8000

> La cámara del escáner solo funciona en `https://` o en `localhost`.

### Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `VIE_DATABASE_URL` | URL SQLAlchemy | `sqlite:///./vie.db` |
| `VIE_SECRET` | Secreto para firmar QR y sesiones | `dev-secret-change-me` (¡cámbialo!) |
| `VIE_COOKIE_SECURE` | `1` para cookies solo por HTTPS (producción) | `0` |

## Despliegue gratuito

1. Crear una base **Postgres gratuita** (Neon, Supabase o Render) → copiar la URL interna.
2. Crear un **Web Service** en Render/Railway/Fly conectado al repo:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Env vars: `VIE_DATABASE_URL`, `VIE_SECRET`, `VIE_COOKIE_SECURE=1`
3. Ejecutar `seed_admin.py` una vez con la URL de producción para crear el admin.

HTTPS queda incluido, así que la cámara del celador funciona.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

## Licencia

[MIT](LICENSE) — úsalo, adáptalo y mejóralo. Hecho con el corazón, para los que cuidan la puerta.
