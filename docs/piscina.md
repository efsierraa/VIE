# Piscina: entradas y salidas con acompañante

Rol `piscina` (guarda de piscina). Registra quién está dentro del área, con una
regla que sostiene todo el flujo: **un adulto residente entra solo; los niños
nunca entran ni salen solos**, siempre ligados a su acompañante.

## Reglas de negocio

- **Entra un adulto residente.** Solo residentes activos con torre y apartamento
  (`_residente_piscina` en `app/routers/api.py`). El invitado no es un residente
  dentro: es una fila aparte ligada a un residente *padrino*.
- **Los niños entran con un adulto.** Cada niño se registra con **nombres y
  apellidos** (y edad opcional, 0-17) y queda ligado a la fila del adulto con
  `acompanante_acceso_id`. Varios niños por adulto, hasta `MAX_NINOS_PISCINA`
  (10 por registro).
- **Los niños salen con su adulto.** Al marcar la salida del acompañante salen
  también sus niños en un solo movimiento.
- **Invitados.** Un invitado adulto (con nombres y apellidos) queda ligado a un
  residente **padrino** (`resident_id`), puede traer sus propios niños y su
  destino es la residencia del padrino. El padrino puede estar dentro o no: el
  invitado no lo representa.
- **Una sola entrada por persona.** No se ingresa a alguien que ya está dentro:
  adulto, niño (mismo nombre con su acompañante) o invitado (mismo nombre
  completo). El niño tampoco se duplica dentro del mismo grupo.

## Salida

- El **niño no puede salir solo**: `POST /piscina/salida/{fila_id}` sobre una
  fila de niño responde **400** ("usa su salida en grupo").
- La salida de un adulto o invitado cierra su grupo: la fila propia **más sus
  niños abiertos** (`acompanante_acceso_id == fila.id`), todos con la misma hora
  y el mismo guarda de salida.
- Invitado y residente son independientes: el invitado sale con sus niños sin
  tocar la fila del padrino, y viceversa.

## Validaciones

- Nombres y apellidos obligatorios (adulto/invitado y niños); largo máximo por
  campo. La edad del niño, si se digita, debe estar entre 0 y 17.
- No se ingresa a quien ya está dentro (ver arriba).
- El acompañante/padrino debe ser un residente activo con torre y apartamento.
- Ingresos concurrentes del mismo residente se serializan con `FOR UPDATE`, así
  un doble toque no crea filas duplicadas.

## Páginas y endpoints

| Ruta | Qué hace |
|---|---|
| `GET /piscina` | Página del rol: **"En la piscina ahora"** (con buscador y paginación) más **Ingresos de hoy** |
| `POST /piscina/ingreso` | Entrada de un adulto residente (`resident_id`) |
| `POST /piscina/ingreso-nino` | Entrada de uno o varios niños con su acompañante (`acompanante_id`, `ninos[]`). Si el adulto no estaba dentro, lo crea y lo vincula |
| `POST /piscina/ingreso-invitado` | Entrada de invitado (`nombres`, `apellidos`, `padrino_id`, `ninos[]` opcional) |
| `POST /piscina/salida/{fila_id}` | Salida individual (adulto/invitado) o del grupo con sus niños |
| `GET /api/residentes?q=` | Buscador de residentes para armar el flujo (nombre o destino `T4 1005`); disponible para guarda, piscina y admin |

Todos los endpoints de escritura exigen rol `piscina` o `admin`. La página exige
el permiso `piscina` (`require_page` / `require_api` en `app/auth.py`).

## Buscador de "En la piscina ahora"

- **Destino exacto**: torre y apartamento juntos (`T4 1005`, `4-1005`, `T4.1005`).
  Torre sola o apto solo no busca (darían demasiados resultados).
- **Nombre**: cada palabra con letras debe aparecer en el nombre del residente,
  el del niño o el del invitado. Los números sueltos no buscan.
- En la lista, cada adulto/invitado con niños muestra **"Salir con N"**; los
  niños no muestran botón de salida.

## Supervisión admin

En **Admin → Historial → Piscina** (`tipo=piscina`) administración ve todas las
filas con filtros de **fecha**, **texto** y **torre/apto**:

| Columna | Contenido |
|---|---|
| Persona | Residente, niño o invitado |
| Tipo | Adulto / Niño / Invitado (chip) |
| Vínculo | "con {acompañante}" o "invitado de {padrino}" |
| Destino | Torre y apartamento (foto del destino al entrar) |
| Entrada / Salida | Hora local (Bogotá) |
| Duración | Calculada cuando ya salió |

La **exportación a Excel** (`/admin/exportar?piscina=1`) agrega una hoja
**Piscina** con las mismas columnas más "Registró" (quién registró la entrada).
El dashboard admin muestra el contador de personas actualmente en piscina.

## Creación de cuentas del rol

El rol `piscina` se crea desde **Administración → Cuentas** o importando CSV.
Como no habita una unidad, se crea **sin torre ni apartamento** (solo residentes
los requieren; ver `_crear_usuario`). El CSV de ejemplo ya incluye un usuario
piscina (`app/static/ejemplo_usuarios.csv`) y el formato está en el README.

## Relación con otras reglas

- El destino que se guarda es una **foto** de torre/apartamento al entrar: si el
  residente cambia de unidad, los registros viejos no se alteran.
- Para el alcance de autorización del rol y el mapeo SOC 2 / Ley 1581, ver
  `auditoria_seguridad.md`.
- Pruebas: `tests/test_piscina.py`.
