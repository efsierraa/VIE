# Entrega de paquetes verificada por QR

## La idea

El QR de reclamo de un paquete lleva el **uuid firmado con HMAC** (`sign_package` en
`app/security.py`): solo el servidor puede generarlo y nadie puede alterarlo. Si la
entrega se marca tras escanear ese reclamo firmado en portería, queda la evidencia
de que **el reclamo se presentó** (lo presenta el residente, dueño del QR). Ante una
disputa "no lo recibí", esa evidencia **exonera al celador**: la responsabilidad de
custodiar y presentar su QR es del residente.

El QR no prueba quién sostenía el teléfono; prueba que el reclamo firmado se usó en
portería — la misma lógica del pase de visita de un solo uso.

## Método de entrega registrado (`packages.metodo_entrega`)

| Método | Cuándo | Evidencia |
|---|---|---|
| `qr` | Se escaneó el reclamo firmado (residente o no registrado) | Verificación criptográfica server-side: `verify_package_token(token) == uuid` al entregar |
| `codigo` | Se digitó el código corto de un paquete de residente | El código se imprime en la tabla de pendientes: no prueba que el residente estuviera |
| `busqueda` | No registrado hallado por búsqueda de nombre | Se compensa con la **cédula** de quien reclama |
| `NULL` | Entregas anteriores al registro de métodos | Sin exoneración documentada |

Un token alterado o de otro paquete → **400 y no se entrega**.

## Regla de exoneración

Cuando una disputa se resuelve y el paquete tiene `metodo_entrega = "qr"`:

- El **control de ediciones** registra "entrega verificada por QR (responsabilidad
  del residente)" — permanente y visible en el historial admin.
- El alerta de resolución lo menciona al celador.

## Quién puede ver el QR de reclamo

- **Residente**: solo el de sus paquetes.
- **Guarda**: solo el de **no registrados** (lo necesita para reenviarles el reclamo
  por WhatsApp). El QR de un paquete de residente no lo puede generar quien lo
  entrega — si no, la evidencia no valdría nada.
- **Administración**: todos (soporte cuando el residente pierde el WhatsApp).
- Endpoint: `/api/packages/{uuid}/pass` (`paquete_pass` en `app/routers/api.py`).

## Dónde se ve el método

- Chip junto al estado en "Entregados hoy" (portería) e historial admin
  (`QR` / `código` / `búsqueda`).
- Hoja **Paquetes** del exportador de Excel, columna "Método".
- Log JSON al entregar y al resolver disputa.

## Entregas antiguas

Las entregas previas a esta funcionalidad tienen `metodo_entrega = NULL` y se
muestran sin chip: no tienen exoneración documentada. La regla de
autoconfirmación (`docs/paquetes-confirmacion.md`) sigue aplicando igual.
