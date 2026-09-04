# Respuesta a incidentes

1. Contén: desactiva la cuenta afectada, rota `VIE_SECRET` si hay fuga de firmas/sesiones, redeploya.
2. Evalúa: qué datos (nombres, cédulas de reclamo, fotos), cuántos afectados, ventana de tiempo. Usa logs + EditLog + historial.
3. Avisa: a los afectados y al consejo en máximo 72 h si hay datos personales. Reporte privado primero (`SECURITY.md`), nunca issue público.
4. Recupera: restaura desde Neon PITR o respaldo lógico (`docs/runbook-respaldos.md`). Verifica login + historial.
5. Aprende: post-mortem de 1 página (causa, fix, cómo evitar). Guarda en `docs/soc2/postmortem-YYYY-MM-DD.md`.
