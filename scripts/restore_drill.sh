#!/usr/bin/env bash
# Recovery drill (docs/12 §Backup, docs/16 Этап 7).
#
# Восстанавливает последний PG-дамп в staging-БД, прогоняет `alembic upgrade
# head` (no-op на свежей схеме) и запускает smoke.sh против staging-бота.
# Запуск из раннера/админ-машины:
#   scripts/restore_drill.sh /var/backups/fantik/pg-fantik-20260501-030000.dump.gz
set -euo pipefail

DUMP="${1:-}"
if [[ -z "$DUMP" ]]; then
  echo "usage: $0 <path-to-dump.gz>" >&2
  exit 2
fi
if [[ ! -f "$DUMP" ]]; then
  echo "dump not found: $DUMP" >&2
  exit 2
fi

: "${STAGING_PGHOST:?STAGING_PGHOST not set}"
: "${STAGING_PGPORT:=5432}"
: "${STAGING_PGUSER:?STAGING_PGUSER not set}"
: "${STAGING_PGDATABASE:?STAGING_PGDATABASE not set}"
: "${STAGING_BOT_URL:=http://staging.fantik.local:8080}"

echo "[drill] target: ${STAGING_PGHOST}:${STAGING_PGPORT}/${STAGING_PGDATABASE}"

# 1. Дропаем и создаём пустую БД.
psql -h "$STAGING_PGHOST" -p "$STAGING_PGPORT" -U "$STAGING_PGUSER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"${STAGING_PGDATABASE}\";"
psql -h "$STAGING_PGHOST" -p "$STAGING_PGPORT" -U "$STAGING_PGUSER" -d postgres \
  -c "CREATE DATABASE \"${STAGING_PGDATABASE}\";"

# 2. Restore из дампа.
echo "[drill] restoring $DUMP"
gunzip -c "$DUMP" | pg_restore --no-owner --clean --if-exists -h "$STAGING_PGHOST" \
  -p "$STAGING_PGPORT" -U "$STAGING_PGUSER" -d "$STAGING_PGDATABASE"

# 3. Alembic upgrade head — no-op если дамп свежий.
echo "[drill] alembic upgrade head"
POSTGRES_HOST="$STAGING_PGHOST" POSTGRES_PORT="$STAGING_PGPORT" \
POSTGRES_USER="$STAGING_PGUSER" POSTGRES_DB="$STAGING_PGDATABASE" \
  uv run alembic upgrade head

# 4. Smoke: бот должен подняться против восстановленной БД.
echo "[drill] smoke against $STAGING_BOT_URL"
BOT_URL="$STAGING_BOT_URL" bash scripts/smoke.sh

echo "[drill] OK — dump is restorable, schema migrates cleanly, bot healthy."
