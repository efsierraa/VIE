# Control de accesos (un edificio)

- Alta: admin crea la cuenta (una a una o CSV). Revisa torre/apto en residentes.
- Clave inicial: admin la asigna (`Clave`). El usuario la cambia en Mi perfil. Mínimo 8.
- 2FA: admin lo activa en su primer login. Pérdida de teléfono: otro admin usa **Cuentas → 2FA** con motivo. Queda en log y EditLog.
- Baja/cambio de turno: admin desactiva (`Desactivar`) el mismo día. Las sesiones mueren al desactivar (`active=false`).
- Revisión trimestral: exporta cuentas, desactiva inactivos, confirma guardas vigentes. Anota fecha y quién en el historial de cambios de este archivo.
- Prohibido compartir usuarios. Un usuario = una persona.
