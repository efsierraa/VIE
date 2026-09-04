# Proveedores (Render + Neon, plan gratis)

| Proveedor | Uso | Riesgo | Mitigación |
|---|---|---|---|
| Render | Hosting + HTTPS | Caída, logs 7 días | Redeploy desde Git, `/health`, revisión semanal |
| Neon | Postgres + PITR | Borrado, región | Respaldo lógico + prueba trimestral |
| GitHub | Código + CI + Dependabot | Acceso | Solo admins del repo hacen merge, Dependabot semanal |

Revisión anual: confirma planes, regiones y contactos. Si pasas a multi-edificio o datos sensibles extra, reevalúa planes pagos.
