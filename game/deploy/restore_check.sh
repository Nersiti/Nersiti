#!/usr/bin/env bash
# Proves the latest backup can be restored: loads it into a scratch database,
# counts players and drops the scratch database. Run weekly or after changes:
#   ./deploy/restore_check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

env_get() { grep -E "^$1=" .env | tail -n 1 | cut -d= -f2-; }
DB_USER="$(env_get POSTGRES_USER)"
CHECK_DB="restore_check"

LATEST="$(ls -1t backups/*.dump 2>/dev/null | head -n 1 || true)"
if [ -z "$LATEST" ]; then
  echo "No backups found in backups/" >&2
  exit 1
fi

psql_admin() { docker compose exec -T postgres psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 "$@"; }

psql_admin -c "DROP DATABASE IF EXISTS $CHECK_DB" -c "CREATE DATABASE $CHECK_DB" > /dev/null
docker compose exec -T postgres pg_restore -U "$DB_USER" -d "$CHECK_DB" --no-owner < "$LATEST"
USERS="$(docker compose exec -T postgres psql -U "$DB_USER" -d "$CHECK_DB" -Atc 'SELECT count(*) FROM users')"
SECTORS="$(docker compose exec -T postgres psql -U "$DB_USER" -d "$CHECK_DB" -Atc 'SELECT count(*) FROM sectors')"
psql_admin -c "DROP DATABASE $CHECK_DB" > /dev/null

echo "restore ok from $LATEST: users=$USERS sectors=$SECTORS"
