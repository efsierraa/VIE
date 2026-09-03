# Auditoría de seguridad — VIE

**Fecha:** septiembre de 2026 · **Alcance:** código de `main` (commit `20d458a` y anteriores) + despliegue en Render/Neon
**Método:** revisión manual de código, pruebas automatizadas (pytest), mapeo a los Criterios de Confianza (TSC) de SOC 2, OWASP Top 10 y ASVS nivel 1-2.

---

## 1. Veredicto sobre SOC 2 (la respuesta honesta)

**SOC 2 no se "cumple" con código.** Es una auditoría de la **organización** que opera el servicio: políticas escritas, gente responsable, procesos repetibles, evidencia durante meses y un auditor externo (AICPA) que emite un dictamen Tipo I o Tipo II.

Lo que sí se puede —y es lo que hicimos— es auditar si el **software** implementa los controles técnicos que el criterio de **Seguridad** de SOC 2 (Common Criteria CC6-CC9) espera de una aplicación web. Conclusión:

> **VIE implementa hoy los controles técnicos esenciales del criterio de Seguridad** para una app de su tamaño. La conformidad formal SOC 2 exige una entidad operadora con gestión de riesgos documentada — algo que corresponde a quien despliegue y opere la app (una administración de edificio, una empresa de software), no al software libre en sí.

Para VIE el marco de referencia práctico es doble:

1. **OWASP ASVS nivel 1-2**: requisitos técnicos verificables en código (donde este trabajo se enfoca).
2. **Ley 1581/2012 (habeas data, Colombia)**: el edificio es el *responsable* del tratamiento de datos personales; VIE es la herramienta. Ver §7.

## 2. Controles verificados y vigentes (lo que ya cumplía)

| Control | Evidencia en el código | Criterio SOC 2 |
|---|---|---|
| Claves con hash bcrypt (nunca en texto plano) | `app/auth.py` | CC6.1 |
| Sesiones firmadas: HttpOnly, SameSite=Lax, Secure en producción, expiración 12 h | `app/auth.py` | CC6.1 |
| Autorización por rol (admin/guarda/residente) y por propietario del recurso — sin IDOR: residente solo accede a sus visitas/paquetes | `app/auth.py`, routers | CC6.2, CC6.3 |
| QR firmados con HMAC; **sal separada por dominio** (visita ≠ paquete); un solo uso verificado en BD; vigencia en BD, no en el papel | `app/security.py`, `api.py` | CC6.1, CC6.7 |
| Consultas parametrizadas con ORM (sin inyección SQL); SQL crudo solo en migraciones con cadenas fijas | `app/database.py`, `main.py` | CC7.1 |
| HTTPS obligatorio (Render) + cookies Secure en producción + TLS hacia la base (Neon `sslmode=require`) | `render.yaml`, `database.py` | CC6.6 |
| Datos mínimos: identificación del visitante opcional; visitantes no crean cuentas | `api.py` | C8.1 (privacidad) |
| Retención: fotos de paquetes entregados se borran a los 30 días (automático); registros sin datos sensibles permanecen auditables | `api.py::limpiar_fotos_vencidas` | C8.1 |
| Secretos por variables de entorno, nunca en el repo; `generateValue` en Render | `security.py`, `render.yaml` | CC6.1 |
| Plan de contingencia operativo si el servicio cae (método manual de siempre) | `pitch.md`, README | A1.3 (disponibilidad) |

## 3. Hallazgos corregidos en esta auditoría

| ID | Severidad | Hallazgo | Corrección aplicada |
|---|---|---|---|
| H1 | **Alta** | Sin límite de intentos: fuerza bruta posible sobre login, códigos cortos y cambio de clave | `app/limitador.py`: login 10 fallos/10 min (por IP), escaneos 120/10 min, paquetes 60/10 min, cambio de clave 10 fallos/10 min → HTTP 429. Test incluido |
| H2 | **Alta** | Fotos de paquetes sin validación de contenido real y **con EXIF intacto** (¡incluía GPS y datos del dispositivo!) | `decodificar_foto()` con Pillow: valida imagen real, **re-codifica a JPEG eliminando todo EXIF**, reescala a máx. 1200 px en el servidor (el cliente no es de confianza). Tests incluidos |
| H3 | Media | Sin cabeceras de seguridad (CSP, nosniff, frame-options...) | Middleware en `main.py`: CSP estricta, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy (cámara solo misma origen), HSTS en producción |
| H4 | Media | JavaScript inline en plantillas impedía una CSP sin `unsafe-inline` | Todo el JS movido a `/static/js/*.js` con `defer`; el CDN del escáner va con **SRI** (integridad verificada) |
| H5 | Media | Política de claves débil (mínimo 6) | Mínimo **8** en API, formularios y CSV; documentado |
| H6 | Media | Secreto por defecto (`dev-secret-change-me`) operaba en silencio si no se configuraba | Warning en el log al arrancar con el secreto por defecto |
| H7 | Media | Cero trazabilidad de eventos de seguridad | Logging estructurado: logins fallidos/exitosos, cambios y asignaciones de clave, altas/bajas de cuentas, importaciones CSV, entregas y cancelaciones de paquetes |

## 4. Riesgos aceptados con justificación

- **CSRF sin tokens**: los formularios con efectos usan JSON (no enviable cross-site sin CORS) y las cookies son SameSite=Lax. Aceptado para MVP; añadir tokens si algún día hay formularios POST con efectos que no sean JSON.
- **Códigos cortos adivinables**: 31^6 ≈ 887 millones de combinaciones + un solo uso + vigencia horaria + límite de 60 intentos/10 min por IP. Riesgo residual bajo para el contexto (portería de edificio).
- **Limitador en memoria**: se reinicia al redeploy. Suficiente con una instancia; con varias, migrar a Redis (documentado en el módulo).

## 5. Hallazgos pendientes (política, no código)

| Pendiente | Recomendación |
|---|---|
| Historial de visitas se conserva indefinido | Administración define retención (sugerido: 12-24 meses) y se añade purga automática |
| Backups: Neon gratuito incluye restauración puntual (PITR) | Probar una restauración real cada trimestre y documentarla |
| Dependencias | Dependabot semanal activado (`​.github/dependabot.yml`); añadir `pip-audit` a CI cuando exista |
| Cuentas inactivas | Revisión trimestral por administración (la app ya permite desactivar) |
| 2FA para administradores | Roadmap futuro |
| Monitoreo | Revisar los logs de Render semanalmente (7 días de retención en el plan gratis) |

## 6. Camino para formalizar SOC 2 (si algún día se exige)

1. Definir alcance (el servicio VIE + los procesos de quien lo opera)
2. Gap assessment contra el TSC con un auditor
3. Escribir y ejecutar políticas 3-6 meses (acceso, incidentes, continuidad, proveedores Render/Neon, desarrollo seguro)
4. Auditoría **Tipo I** (diseño) → 6+ meses de evidencia → **Tipo II** (operación)
5. Costo realista: decenas de miles de dólares — solo tiene sentido para un operador comercial, no para el proyecto comunitario

## 7. Habeas data (Ley 1581/2012, Colombia)

- **Responsable del tratamiento**: el edificio (administración/consejo) que decide implementar VIE. VIE es la herramienta (encargado técnico).
- **Datos tratados**: nombres y apellidos, usuario, clave (hasheada), cédula *opcional* del visitante, registro de entradas/salidas, fotos de paquetes.
- Medidas alineadas: minimización (id opcional, visitantes sin cuenta), EXIF/GPS eliminado de fotos, retención de fotos 30 días post-entrega, acceso restringido por rol, base de propiedad de la administración.
- **Dato personal — cédula en paquetes de no registrados**: el paquete llega por transportadora, así que al registrar solo se anota el nombre del destinatario (el de la etiqueta). Al reclamar, el guarda coteja el nombre con la cédula física que presenta la persona y registra el **número de cédula como evidencia** de quién reclamó. No se almacenan fotos de cédulas. El número solo es visible para guardas en la tarjeta de entrega y para administración en el Excel.
- **Pendiente del edificio**: aviso de privacidad en portería/recepción y autorización de tratamiento para visitantes (obligación legal del responsable, no del software).

## 8. Cómo verificar tú mismo

```powershell
.venv\Scripts\python -m pytest   # 39 pruebas, incluidas las de seguridad
```

Revisa `SECURITY.md` (reporte de vulnerabilidades), `app/limitador.py`, `decodificar_foto()` en `app/routers/api.py` y el middleware de cabeceras en `app/main.py`.
