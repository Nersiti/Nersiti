#!/usr/bin/env bash
# Горячий бэкап SQLite-базы (безопасен при работающем боте). Хранит 14 дней.
# cron: 0 4 * * * cd /path/to/Nersiti && bash deploy/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M)
python3 - "$STAMP" <<'PY'
import sqlite3, sys
src = sqlite3.connect("data/bot.db")
dst = sqlite3.connect(f"backups/bot-{sys.argv[1]}.db")
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
gzip -f "backups/bot-${STAMP}.db"
find backups -name "bot-*.db.gz" -mtime +14 -delete
echo "backup: backups/bot-${STAMP}.db.gz"
