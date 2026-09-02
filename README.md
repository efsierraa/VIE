# VIE — Vigilancia de Ingresos y Egresos

> **El control de acceso de tu edificio, en un escaneo.**
> App gratuita y open source para que el residente genere un pase QR de un solo uso, lo comparta por cualquier canal y el guarda valide el ingreso en segundos.

Ver [pitch.md](pitch.md) para la idea completa, objetivos e impacto.

## Cómo funciona

1. **Residente**: crea una visita (nombre, asunto, ID opcional, rol) y recibe un **QR de un solo uso** para compartir por WhatsApp — imagen y texto — junto con un **código corto de 6 caracteres**.
2. **Guarda**: escanea el QR en portería (o digita el código corto) → registra la **entrada**. Un segundo escaneo opcional marca la **salida** y calcula la duración de la visita.
3. **Administración**: crea las cuentas y supervisa el **historial completo** de ingresos con filtros.

Si la app falla, el guarda registra a mano (entrada manual) o se vuelve al método de siempre: llamar y anotar.

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

El repo incluye [`render.yaml`](render.yaml): Render lee ese archivo y crea el servicio solo. La base de datos va en **Neon** (Postgres gratuito permanente).

### Paso 1 — Base de datos en Neon

1. Crea cuenta en [neon.tech](https://neon.tech) (gratis, sin tarjeta)
2. Crea un proyecto y copia el **connection string** (se ve así: `postgresql://usuario:clave@ep-xxx.aws.neon.tech/neondb?sslmode=require`)

### Paso 2 — Crear el servicio en Render

1. Entra a [dashboard.render.com](https://dashboard.render.com) con tu cuenta de GitHub
2. **New + → Blueprint** → selecciona el repo `efsierraa/VIE`
3. Render leerá `render.yaml` y pedirá el valor de `VIE_DATABASE_URL` → pega la URL de Neon
4. **Apply** → primera compilación (~2 min). HTTPS incluido, así que la cámara del guarda funciona.

También puedes usar el botón: [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/efsierraa/VIE)

### Paso 3 — Crear el administrador

Desde tu PC, apuntando a la base de producción:

```powershell
$env:VIE_DATABASE_URL = "postgresql://...neon.tech/neondb?sslmode=require"
.venv\Scripts\python seed_admin.py --usuario admin --clave una-clave-segura --nombre "Administración"
```

Listo: entra a `https://vie-XXXX.onrender.com` con esa cuenta y crea los residentes y guardas desde la pantalla de administración.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

## Licencia

[MIT](LICENSE) — úsalo, adáptalo y mejóralo. Hecho con el corazón, para los que cuidan la puerta.
