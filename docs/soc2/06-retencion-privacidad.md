# Retención y privacidad (Ley 1581 + SOC2 CC)

- Responsable: el edificio. VIE es la herramienta (encargado técnico).
- Fotos de paquetes: se borran 30 días post-entrega (`photo_delete_after`). Automático al arrancar.
- Visitas finalizadas/canceladas: se purgan a los 12 meses (`VIE_RETENTION_MONTHS=12`, `POST /api/admin/retencion/ejecutar` para manual). Pendientes/dentro nunca se purgan.
- EditLog y conteos: se conservan como evidencia de auditoría.
- Cédula de reclamo: solo número, solo visible para guarda en entrega y admin en Excel. Sin fotos de cédulas.
- Minimización: ID de visitante opcional, visitantes sin cuenta, celular opcional.
- Pendiente del edificio (no del software): aviso de privacidad en portería y autorización de visitantes.
