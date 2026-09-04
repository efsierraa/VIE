# Política de seguridad (un edificio)

Operador: la administración del edificio. VIE es la herramienta.

1. Solo `main` en producción. Cambios por PR con CI verde (pytest + pip-audit informativo).
2. Secretos solo en variables de entorno (`VIE_SECRET`, `VIE_DATABASE_URL`). Nunca en el repo ni en respaldos subidos a Git.
3. Acceso mínimo por rol: residente ve lo suyo, guarda opera portería, admin gestiona. Sin IDOR.
4. Admin exige 2FA TOTP. Sin excepciones en producción.
5. HTTPS siempre (Render). Cookies Secure + HttpOnly + SameSite=Lax. Sesión 12 h.
6. Logs semanales: el admin revisa `login_fallido`, `2fa_fallido`, `clave_*`, `2fa_reiniciado` en Render (retención 7 días).
7. Incidentes: ver `respuesta-incidentes.md`. Vulnerabilidades: `SECURITY.md`.
