# Seguridad de VIE

## Reportar una vulnerabilidad

Si encuentras una falla de seguridad, **no abras un issue público**. Usa el reporte privado de GitHub (pestaña *Security* → *Report a vulnerability*) del repositorio, o escribe directamente al mantenedor.

Respondemos en un máximo de 7 días y publicamos el fix junto con un aviso.

## Versiones con soporte

| Versión | Soporte |
|---|---|
| `main` (última en producción) | Sí |
| Versiones anteriores | No |

## Controles implementados (resumen)

- Claves con **bcrypt**; mínimo 8 caracteres; cambio de clave por el usuario y reasignación por administración
- Sesiones firmadas (HttpOnly, SameSite=Lax, Secure en producción, expiran a las 12 h)
- Autorización por rol y por propietario del recurso (sin IDOR conocidos)
- Códigos QR firmados con HMAC y sal por dominio (visita ≠ paquete), de un solo uso, con vigencia controlada en la base de datos
- Limitador de intentos contra fuerza bruta en login, escaneos y cambios de clave
- Fotos de paquetes validadas y re-codificadas en el servidor (sin EXIF/GPS, reescalado forzado)
- Cabeceras de seguridad (CSP, nosniff, X-Frame-Options, Referrer-Policy, HSTS en producción)
- Eventos de seguridad en el log JSON (logins, 2FA, cambios de clave, altas/bajas, reinicios 2FA, entregas)
- Segundo factor TOTP obligatorio para administración (con códigos de respaldo de un solo uso); reinicio por otro admin con motivo auditado
- Retención: fotos 30 días post-entrega; visitas finalizadas/canceladas 12 meses (`VIE_RETENTION_MONTHS`)
- Salud pública `/health` + `X-Request-Id`; HTTPS obligatorio en producción; tráfico a la base cifrado

Guía 2FA admin: [docs/2fa-admin.md](docs/2fa-admin.md). Políticas base (un edificio): [docs/soc2/](docs/soc2/). Respaldos: [docs/runbook-respaldos.md](docs/runbook-respaldos.md).

Detalle completo en [auditoria_seguridad.md](auditoria_seguridad.md).
