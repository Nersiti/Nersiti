#!/usr/bin/env bash
# Daily PostgreSQL backup (keeps the last BACKUP_KEEP dumps, 7 by default).
#
# Add to root's crontab on the VPS (crontab -e):
#   15 4 * * * cd /opt/game && ./deploy/backup.sh >> backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

# Read only the variables we need: .env values may contain spaces, so do not `source` it.
env_get() { grep -E "^$1=" .env | tail -n 1 | cut -d= -f2-; }
DB_USER="$(env_get POSTGRES_USER)"
DB_NAME="$(env_get POSTGRES_DB)"
KEEP="${BACKUP_KEEP:-7}"

mkdir -p backups
STAMP="$(date -u +%Y%m%d_%H%M)"
FILE="backups/${DB_NAME}_${STAMP}.dump"

docker compose exec -T postgres pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom > "$FILE.part"
mv "$FILE.part" "$FILE"
echo "$(date -u '+%F %T') backup ok: $FILE ($(du -h "$FILE" | cut -f1))"

# Rotate old dumps.
ls -1t backups/*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm --
