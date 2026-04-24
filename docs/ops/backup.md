# Backup & Recovery

Практика бэкапа/восстановления Fantik, соответствующая [`docs/12`](../12-security-privacy.md#backup) и [`docs/16`](../16-roadmap.md) «Этап 7».

## Что бэкапим

| Источник | Чем | Частота | Где хранится | Retention |
|---|---|---|---|---|
| PostgreSQL | `pg_dump -Fc` + gzip | ежедневно 03:00 UTC | отдельный VPS / S3-совместимое | 30 дней |
| Meilisearch | не бэкапим (source of truth — PG) | — | — | — |
| Redis | RDB snapshot (AOF всегда on) | 15 мин через redis сам | локальный volume | последние 2 снэпа |

Redis — это кэш. Потеря = прогрев. Critical state живёт в PG.

## Скрипты

- [`scripts/backup_pg.sh`](../../scripts/backup_pg.sh) — ежедневный дамп.
- [`scripts/restore_drill.sh`](../../scripts/restore_drill.sh) — тест восстановления в staging.

## Установка cron на host

```
# /etc/cron.d/fantik-backup
0 3 * * * fantik cd /opt/fantik && \
  PGHOST=pg-prod PGUSER=fantik PGDATABASE=fantik PGPASSWORD=... \
  BACKUP_DIR=/var/backups/fantik RETENTION_DAYS=30 \
  /opt/fantik/scripts/backup_pg.sh >> /var/log/fantik-backup.log 2>&1
```

Права на `/var/backups/fantik` — 0700 для user `fantik` (дампы содержат PII согласно docs/12).

Пароль PG в cron-энве — ни в коем случае не в `-p/--password` аргументе (засветится в `ps`). Используй `.pgpass`:

```
# /home/fantik/.pgpass  (chmod 600)
pg-prod:5432:fantik:fantik:<пароль>
```

## Offsite-копирование

`pg-fantik-*.dump.gz` должен лежать не на том же диске, что и БД. Варианты:

1. **S3-совместимое хранилище** (рекомендовано):
   ```
   rclone copy /var/backups/fantik s3-backup:fantik-pg-backups --min-age 10m
   ```
   Добавить вторую cron-строку после `backup_pg.sh`.

2. **rsync на второй VPS**:
   ```
   rsync -az --delete /var/backups/fantik/ backup-vps:/var/backups/fantik/
   ```

## Ежемесячный recovery drill

Цель: убедиться, что дамп реально разворачивается.

```bash
# на админ-машине
STAGING_PGHOST=pg-staging STAGING_PGUSER=fantik_stg \
STAGING_PGDATABASE=fantik_stg STAGING_BOT_URL=http://staging-bot.local:8080 \
  ./scripts/restore_drill.sh /var/backups/fantik/pg-fantik-$(date -u +%Y%m%d)-030000.dump.gz
```

Финальная строка должна быть `[drill] OK`. Записать результат в changelog (`docs/ops/drills.log` — необязательно, но помогает).

Если drill падает:

| Ошибка | Причина | Фикс |
|---|---|---|
| `pg_restore: error: ... no matching tables` | дамп побит | взять более ранний дамп, срочно разобраться почему pg_dump отдал мусор |
| `relation "X" already exists` | dropdb не сработал | проверь `STAGING_PGDATABASE`, чтобы не дропать прод |
| `alembic: target database is not up to date` | schema drift между прод и кодом | поднять up_to_date в соответствующей миграции |

## Восстановление в прод

Только при реальной аварии. Пошагово:

1. Остановить входящий трафик: `docker compose stop bot`.
2. Остановить воркеры: `docker compose stop worker worker-broadcast scheduler`.
3. Снять текущий (битый) PG: `docker compose stop postgres`.
4. Сохранить его volume на всякий случай: `docker volume create postgres_data_broken && docker run --rm -v postgres_data:/src -v postgres_data_broken:/dst alpine cp -a /src/. /dst/`.
5. Очистить и развернуть: `docker volume rm postgres_data && docker compose up -d postgres`, дождаться healthy.
6. `gunzip -c dump.gz | pg_restore --no-owner -d fantik -h localhost -U fantik`.
7. `docker compose up -d migrate` → должно быть no-op.
8. Поднять сервисы обратно: `docker compose up -d bot worker worker-broadcast scheduler`.
9. `make smoke` — должно быть OK.
10. Написать в чат админов: время начала, время окончания, объём потерянных данных (≥ разница между `now()` и `MAX(created_at)` в критичных таблицах).

Документировать в `docs/ops/incidents/YYYY-MM-DD.md` — хронология, причина, превентивные меры.
