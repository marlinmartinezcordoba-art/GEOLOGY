#!/usr/bin/env bash
# Restaura una copia de ARCA en un servidor nuevo. Pruébelo al menos una vez por trimestre en un servidor aparte.
# Uso: ./restaurar.sh /ruta/de/copias 20261115T020000Z
set -euo pipefail
cd "$(dirname "$0")"
origen="${1:?Carpeta de las copias}"; marca="${2:?Marca de la copia (aaaammddThhmmssZ)}"
( cd "$origen" && sha256sum -c "arca-$marca.sha256" )   # la copia está íntegra
set -a; . ./.env; set +a
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U "${POSTGRES_USER:-arca}" -d "${POSTGRES_DB:-arca}" --clean --if-exists < "$origen/arca-bd-$marca.dump"
if [ -f "$origen/arca-almacen-$marca.tar.gz" ]; then
  docker compose run --rm --no-deps -T --entrypoint tar api -C /datos -xzf - < "$origen/arca-almacen-$marca.tar.gz"
fi
docker compose up -d
echo "Restaurada la copia $marca. Verifique /estado y la cadena de auditoría (Auditoría → Verificar)."
