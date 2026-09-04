# 2FA para administración — activar y usar

Admin exige segundo factor (TOTP, 6 dígitos cada 30 s). Sin él no entras a `/admin`.

## Primera vez (activar)

1. Ingresa usuario y clave en `/login`.
2. Verás **Activa tu segundo factor** con un QR y un secreto.
3. Abre tu app (Google Authenticator, Authy, 1Password, Bitwarden) → agrega cuenta → escanea el QR. Si no puedes escanear, digita el secreto a mano.
4. Digita el código de 6 dígitos que muestra la app → **Activar y entrar**.
5. Guarda los 8 códigos de respaldo que aparecen. Se muestran una sola vez. Cada uno sirve una vez.

Listo. Quedas dentro con sesión normal (12 h).

## Uso diario

1. Ingresa usuario y clave en `/login`.
2. Verás **Verificación en dos pasos**.
3. Digita el código actual de tu app (o un código de respaldo si perdiste el teléfono).
4. Entras a `/admin`.

Tienes 5 intentos cada 5 min. Al 6.º verás `429`. Espera y reintenta.

## Códigos de respaldo

- Formato: `XXXX-XXXX`. Sirven una vez cada uno.
- Quedan guardados con hash SHA-256. El servidor nunca los muestra de nuevo.
- Consulta cuántos te quedan: **Mi perfil → Verificación en dos pasos**.
- Regenera: misma sección → **Regenerar códigos**. Los viejos se invalidan.
- Si usas uno para entrar, se descuenta solo.

## Reconfigurar (cambiaste de teléfono)

1. Entra a **Mi perfil → Verificación en dos pasos**.
2. Pulsa **Activar / Reconfigurar** → escanea el QR nuevo → confirma con un código.
3. Recibes códigos de respaldo nuevos.

## Reglas

- Admin no puede desactivar el 2FA. La API `POST /api/me/2fa/disable` lo rechaza con `400`.
- Guarda y residente: opcional, mismo flujo desde **Mi perfil**.
- El secreto vive en `users.totp_secret`. Solo se crea al iniciar el setup. Se activa con `totp_enabled = true` tras verificar un código.
- Pre-sesión 2FA: cookie `vie_pre2fa`, 5 min, HttpOnly, SameSite=Lax. No autoriza nada. Solo te lleva a `/login/2fa` o `/login/2fa-setup`.
- Eventos en el log: `admin_sin_2fa_setup_requerido`, `setup_2fa_ok`, `login_2fa_ok`, `login_2fa_fallido`, `2fa_respaldo_regenerado`.

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| Código siempre inválido | Revisa la hora del teléfono (TOTP exige reloj exacto). Hay tolerancia ±30 s. Prueba el siguiente código. |
| Perdí el teléfono y no tengo respaldos | Pide a otro admin que en **Cuentas** pulse **2FA** en tu fila e indique el motivo. Queda en log (`2fa_reiniciado`) y en el control de ediciones (`/admin/historial`). En tu próximo login repites la activación. Vía API: `POST /api/users/{id}/2fa/reset {"motivo": "…"}`. |
| Veo `429 Demasiados intentos` | Espera 5 min. Son 5 intentos por ventana para `/login/2fa`. |
| QR no carga | Usa el secreto manual. Si persiste, revisa `/static` y CSP. |

## Desactivar en tests

Solo para tests: `VIE_ENFORCE_ADMIN_2FA=0`. En producción siempre `1` (valor por defecto).

## Probarlo

```powershell
.venv\Scripts\python -m pytest tests/test_2fa.py -v
```

Cubre: setup obligatorio en login admin, bloqueo sin código, login con TOTP válido, consumo de respaldo, admin no puede desactivar, guarda sí puede usarlo opcional.
