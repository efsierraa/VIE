# Respaldos Neon — runbook (un edificio, plan gratis)

Neon gratis incluye restauración puntual (PITR). Este runbook suma un respaldo lógico verificable para evidencia SOC2.

## Hacer un respaldo

```powershell
$env:VIE_DATABASE_URL = "postgresql://...neon.tech/neondb?sslmode=require"
.\scripts\backup_neon.ps1
```

Guarda el `.sql.gz` fuera del repo (disco admin + copia). Nombra con fecha. No subas respaldos a Git.

## Probar la restauración (cada trimestre)

1. Crea una rama de Neon o una BD `neondb_test` vacía. Copia su connection string a `VIE_RESTORE_URL`.
2. Restaura ahí, nunca sobre producción sin ventana acordada.
3. Levanta la app apuntando a la restaurada y verifica: login admin, historial, una foto de paquete.
4. Anota en `docs/respaldos-evidencia.md`: fecha, quién, tamaño, resultado, hallazgos.

## Qué cubre

- Caída lógica (borrado accidental, migración mala): respaldo lógico + PITR de Neon.
- Caída total: Render redeploya desde Git; la base se restaura desde el `.sql.gz` o PITR.
- Lo que no cubre el plan gratis: RPO/RTO formales, réplicas, logs >7 días. Suficiente para un edificio. Si pasas a multi-edificio, sube de plan.
