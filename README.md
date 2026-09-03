# VIE — Vigilancia de Ingresos y Egresos

> **El control de acceso de tu edificio, en un escaneo.**
> App gratuita y open source para que el residente genere un pase QR de un solo uso, lo comparta por cualquier canal y el guarda valide el ingreso en segundos.

Ver [pitch.md](pitch.md) para la idea completa, objetivos e impacto.

## Cómo funciona

La app se organiza en **páginas por sección** con una barra de navegación inferior en el celular:

- **Guarda · Ingresos**: escáner de entrada/salida, entrada manual, ingresos del día
- **Guarda · Paquetes**: pendientes por entregar, registro (con o sin QR), entrega por código/cédula, entregados del día
- **Admin · Inicio**: métricas del día
- **Admin · Cuentas**: crear cuentas (una a una o importando un CSV), asignar claves, activar/desactivar
- **Admin · Historial**: selector de tipo (Ingresos / Paquetes / Ambos) con filtros que se adaptan (fecha, estado, texto, torre), exportación a Excel por tipo y rango de fechas, y asignación de paquetes de no registrados — incluso después de entregados

1. **Residente**: crea una visita (nombre, asunto, ID opcional, rol) y recibe un **QR de un solo uso** para compartir por WhatsApp — imagen y texto — junto con un **código corto de 6 caracteres**.
2. **Guarda**: escanea el QR en portería (o digita el código corto) → registra la **entrada**. Un segundo escaneo opcional marca la **salida** y calcula la duración de la visita.
3. **Administración**: supervisa todo desde el historial con trazabilidad completa.

### Paquetes

1. Llega un paquete → el **guarda** lo registra con una **foto** (comprimida en el navegador) y lo asigna al residente. Para encontrarlo busca por nombre o apellido; si va por destino, **torre y apartamento juntos**: `T4 1005`, `4 1005`, `4-1005` o `T4.1005` — torre sola o apto solo no arroja resultados (serían demasiados).
2. El residente ve el aviso en su app: foto, descripción, código corto y **QR para reclamarlo**.
3. En portería el residente muestra el QR → el guarda **ve la foto** → busca el paquete → **"Marcar entregado"**.
4. El residente **confirma la recepción** (o marca "No lo recibí" → queda en disputa para administración).
5. Las fotos de paquetes entregados se **borran solas 30 días después** de la entrega; las de paquetes pendientes se conservan hasta entregarse. Los registros completos quedan en el historial y en el Excel.

### Paquetes para alguien NO registrado

Cuando el paquete llega por transportadora para una persona sin cuenta (lo más probable: un residente nuevo), el guarda marca **"El destinatario NO está registrado"** al registrarlo:

1. Digita el **nombre del destinatario** y su **torre y apartamento** (obligatorios — vienen en la etiqueta del paquete), y toma la **foto del paquete**. No se pide cédula al registrar — quien trajo el paquete es la transportadora
2. El paquete **no tiene QR**: la llave es el nombre. En "Entregar paquete → No registrado" el guarda busca por nombre
3. Al reclamar, la persona presenta su **cédula física**: el guarda coteja que el nombre coincida con el registrado, **digita el número de cédula** (queda como evidencia de quién reclamó) y marca la entrega
4. Administración recibe la **alerta** ("paquetes sin residente" en el dashboard): registra al residente nuevo en "Nueva cuenta" y pulsa **"Asignar a residente"** → el paquete gana un QR y el residente lo ve en su app
5. Si nunca se asigna, el paquete se entrega con la cédula y queda en el historial
6. La foto del paquete se borra sola 30 días después de la entrega; el número de cédula queda en el registro como evidencia

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
.venv\Scripts\python seed_admin.py --usuario admin --clave una-clave-segura --nombres "María" --apellidos "Pérez"

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
.venv\Scripts\python seed_admin.py --usuario admin --clave una-clave-segura --nombres "María" --apellidos "Pérez"
```

### Importar usuarios por CSV

Administración → "Importar usuarios desde CSV". Hay un archivo de ejemplo listo para copiar en la propia app: `/static/ejemplo_usuarios.csv`.

**Formato**: la primera fila debe ser exactamente el encabezado, en este orden:

| Columna | Obligatoria | Reglas |
|---|---|---|
| `nombres` | Sí | Nombres de pila |
| `apellidos` | Sí | Apellidos |
| `usuario` | Sí | Mínimo 3 caracteres, sin espacios; se guarda en minúsculas; no puede repetirse |
| `clave` | Sí | Mínimo 6 caracteres. El usuario puede cambiarla después en "Mi clave" |
| `rol` | Sí | `residente`, `guarda` o `admin` |
| `torre` | Solo residentes | Número o letra de la torre (vacía para guarda/admin) |
| `apartamento` | Solo residentes | Ej: `502` (vacío para guarda/admin) |

Ejemplo completo:

```csv
nombres,apellidos,usuario,clave,rol,torre,apartamento
Camila,Rojas,camilar,clave123,residente,3,301
Pedro,Gómez,pgomez,clave456,guarda,,
Laura,Restrepo,lrestrepo,clave789,residente,5,1204
```

**Reglas y consejos**

- Se toleran espacios alrededor de los valores, pero lo limpio es no ponerlos.
- Codificación UTF-8. Desde Excel: "Guardar como → **CSV UTF-8 (delimitado por comas)**". Ojo: en Excel en español NO uses "CSV (delimitado por punto y coma)" — el importador espera comas (también acepta el CSV clásico de Windows, codificación cp1252).
- Las líneas vacías se ignoran. No agregues columnas extra ni cambies el orden.
- Un residente sin torre y apartamento se rechaza; guarda y admin las dejan vacías.
- Si una fila falla (usuario repetido, rol inválido, clave corta...), el resto se importa igual y al final se listan los errores con su número de línea.

Listo: entra a `https://vie-XXXX.onrender.com` con esa cuenta y crea los residentes y guardas desde la pantalla de administración.

## Seguridad

- Claves con bcrypt (mínimo 8), sesiones firmadas con expiración, autorización por rol y por propietario
- QR firmados con HMAC (sal separada por dominio), un solo uso, vigencia en base de datos
- Limitador de fuerza bruta, cabeceras de seguridad (CSP, HSTS...), fotos validadas y sin EXIF en el servidor
- Eventos de seguridad en el log; dependencias vigiladas con Dependabot

Auditoría completa y mapeo a SOC 2 / Ley 1581 en [auditoria_seguridad.md](auditoria_seguridad.md). Cómo reportar una vulnerabilidad: [SECURITY.md](SECURITY.md).

## Tests

```powershell
.venv\Scripts\python -m pytest
```

## Licencia

[MIT](LICENSE) — úsalo, adáptalo y mejóralo. Hecho con el corazón, para los que cuidan la puerta.
