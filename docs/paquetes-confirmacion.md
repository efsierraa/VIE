# Paquetes: confirmación de recepción

Flujo de estados de un paquete: `en_porteria` → `entregado` → `confirmado`
(o `disputa`, resuelta a dos partes, o `cancelado` en portería).

## Regla de autoconfirmación (30 días)

- Cuando el guarda marca un paquete como **entregado**, el residente debe
  **confirmar la recepción** en su app.
- Si el residente no confirma ni disputa en **30 días**, el paquete se
  **confirma automáticamente**: `status = confirmado`, `confirmed_at` = momento
  de la autoconfirmación.
- Solo aplica a paquetes en estado `entregado`: los paquetes en `disputa`,
  `en_porteria` y `cancelado` nunca se autoconfirman.
- Constante: `DIAS_AUTOCONFIRMACION` en `app/models.py`.

## Cuándo corre

Al arrancar la app (lifespan, junto con los demás barridos automáticos de
`app/main.py`).

## Recordatorio en tiempo real (residente)

- El banner de `/residente` se **calcula al cargar la página** con lo que hay
  hoy en la base de datos (`texto_recordatorio_paquetes` en `app/routers/api.py`):
  cuántos paquetes `entregado` sin confirmar tiene el residente y **cuántos
  días quedan** para la autoconfirmación (según la entrega más antigua).
- No hay horarios ni tabla de avisos: si entra hoy, ve el estado de hoy.
- El residente puede **cerrarlo con la ✕** de la esquina superior derecha, pero
  el cierre es **momentáneo**: mientras haya paquetes sin confirmar, el letrero
  vuelve con cada carga de la página (F5) y desaparece solo cuando ya no
  quedan paquetes por confirmar.

## Inspección por administración

- **Dashboard admin**: tarjeta "**entregados sin confirmar**" con enlace
  directo al filtro del historial.
- **Historial admin**: filtro `Estado = entregado` (`/admin/historial?tipo=paquetes&estado=entregado`);
  cada fila muestra "**hace N días sin confirmar (auto a 30)**".
- La exportación a Excel usa los mismos filtros, así que el reporte de
  "entregados sin confirmar" se puede descargar desde el mismo filtro.

## Relación con otras reglas

- La **foto** del paquete entregado se borra 30 días después de la entrega
  (`DIAS_FOTO_ENTREGADA`); la autoconfirmación no la acelera ni la evita.
- Una **disputa** detiene el reloj: sale del estado `entregado` y solo vuelve
  a `confirmado` cuando ambas partes (portería y residente) resuelven.
