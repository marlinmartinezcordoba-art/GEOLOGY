#!/usr/bin/env bash
# Copia de seguridad de ARCA: la base de datos (pg_dump) y, si el almacén es local, sus archivos.
# Con almacén S3, los archivos se protegen en el proveedor: versionado del bucket + replicación a otra región
# (y Object Lock si el contrato lo pide). Programe este script a diario (cron o el programador del servidor).
# Uso: ./copia_seguridad.sh /ruta/de/copias   (conserva DIAS_RETENCION días, 30 por defecto)
set -euo pipefail
cd "$(dirname "$0")"
destino="${1:?Indique la carpeta de las copias}"
dias="${DIAS_RETENCION:-30}"
marca="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$destino"
set -a; . ./.env; set +a

docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-arca}" -d "${POSTGRES_DB:-arca}" -Fc > "$destino/arca-bd-$marca.dump"
if [ "${ARCA_ALMACEN_PROVEEDOR:-local}" = "local" ]; then
  docker compose run --rm --no-deps -T --entrypoint tar api -C /datos -czf - almacen > "$destino/arca-almacen-$marca.tar.gz"
fi
( cd "$destino" && sha256sum arca-*-"$marca"* > "arca-$marca.sha256" )
find "$destino" -name 'arca-*' -type f -mtime +"$dias" -delete
echo "Copia lista en $destino ($marca). Los archivos del almacén van cifrados: la llave se guarda aparte."
