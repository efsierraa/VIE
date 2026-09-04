#!/usr/bin/env bash
# Respaldo lógico de Neon con pg_dump. Requiere VIE_DATABASE_URL.
set -euo pipefail
DESTINO="${1:-./backups}"
[ -n "${VIE_DATABASE_URL:-}" ] || { echo "Define VIE_DATABASE_URL antes." >&2; exit 1; }
mkdir -p "$DESTINO"
FECHA=$(date +%Y%m%d-%H%M)
ARCHIVO="$DESTINO/vie-$FECHA.sql.gz"
pg_dump "$VIE_DATABASE_URL" | gzip > "$ARCHIVO"
echo "Respaldo: $ARCHIVO"
echo "Restaura (prueba en BD vacía): psql \$VIE_RESTORE_URL < <(gunzip -c $ARCHIVO)"
