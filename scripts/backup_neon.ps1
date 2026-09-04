<#.SYNOPSISIS
Respaldo lógico de Neon (Postgres) con pg_dump. Guarda .sql.gz con fecha.
Requiere: pg_dump en PATH y $env:VIE_DATABASE_URL con sslmode=require.
Evidencia SOC2/CC: guarda el archivo + anota la prueba trimestral en docs/respaldos-evidencia.md
#>
param([string]$Destino = ".\backups")
$ErrorActionPreference = "Stop"
if (-not $env:VIE_DATABASE_URL) { throw "Define VIE_DATABASE_URL antes (connection string de Neon)." }
New-Item -ItemType Directory -Path $Destino -Force | Out-Null
$fecha = Get-Date -Format "yyyyMMdd-HHmm"
$archivo = Join-Path $Destino "vie-$fecha.sql.gz"
# pg_dump a custom? No: texto + gzip para inspeccionar fácil
$tmp = Join-Path $Destino "vie-$fecha.sql"
& pg_dump $env:VIE_DATABASE_URL -f $tmp
Compress-Archive -Path $tmp -DestinationPath $archivo -Force
Remove-Item -LiteralPath $tmp
Write-Output "Respaldo: $archivo"
Write-Output "Restaura (prueba en BD vacía, NUNCA sobre producción sin ventana):"
Write-Output "  `$env:VIE_RESTORE_URL = 'postgresql://.../neondb_test?sslmode=require'"
Write-Output "  psql `$env:VIE_RESTORE_URL -f <descomprimido>.sql"
