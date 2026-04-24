#!/usr/bin/env bash
# Ежедневный pg_dump (docs/12 §Backup).
#
# Хранит custom-формат .dump.gz в $BACKUP_DIR, держит 30 поколений.
# Запуск — из host-crontab или CI runner'а, НЕ внутри compose:
#   0 3 * * *   /opt/fantik/scripts/backup_pg.sh >> /var/log/fantik-backup.log 2>&1
#
# Читает PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE из окружения либо через
# pg-совместимый .pgpass; пароль в CLI-аргументах принципиально не передаём.
set -euo pipefail

: "${PGHOST:=localhost}"
: "${PGPORT:=5432}"
: "${PGUSER:=fantik}"
: "${PGDATABASE:=fantik}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/fantik}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/pg-${PGDATABASE}-${STAMP}.dump.gz"

mkdir -p "$BACKUP_DIR"

echo "[backup] dumping to $OUT"
# -Fc: custom формат (быстрый restore, --jobs), --no-owner: чтобы restore
# проходил в staging под другим ролью.
pg_dump -Fc --no-owner -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
  | gzip -9 > "$OUT"

echo "[backup] ok: $(du -h "$OUT" | cut -f1)"

# Ротация: удаляем всё старше $RETENTION_DAYS дней.
find "$BACKUP_DIR" -name "pg-${PGDATABASE}-*.dump.gz" -type f -mtime +"${RETENTION_DAYS}" -print -delete
echo "[backup] retention: ${RETENTION_DAYS}d applied"
