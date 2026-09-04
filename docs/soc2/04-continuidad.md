# Continuidad (un edificio)

- Si VIE cae: el guarda registra a mano o llama y anota (método de siempre). Ningún ingreso queda bloqueado por la app.
- RTO: redeploy desde Git en Render (~minutos). RPO: PITR de Neon + respaldo lógico trimestral verificado.
- Salud: `/health` (app + DB) para uptime externo. Si `/health` da 503, revisa Neon antes que Render.
- Prueba trimestral: restauración en `neondb_test` + evidencia en `docs/respaldos-evidencia.md`.
