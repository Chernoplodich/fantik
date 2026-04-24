# On-call Runbook

Каждая алерт-карточка ведёт сюда по якорю. Держи коротко: проверить, снять, эскалировать.

## BotHighErrorRate

**Что**: `rate(bot_handler_errors_total[5m]) / rate(bot_updates_total[5m]) > 10%` ≥ 5 мин.

**Диагностика**:
1. `make logs-bot | grep handler_unhandled_error` — видно тип ошибки и handler.
2. Sentry → проект fantik-bot, фильтр env=prod — группа за последние 15 мин.
3. Prometheus: `topk(5, sum by (error_type) (rate(bot_handler_errors_total[5m])))`.

**Частые причины**:
- Массовый `TelegramRetryAfter` (TG 429): проверь `rate(bot_tg_api_calls_total{result="error"}[1m])`, снизь `MAX_USER_UPDATES_PER_MIN`.
- Падение БД: `/readyz` вернёт `pg=false` → см. PG-FullDisk / PG-Down.
- Баг в свежем релизе: откатись (`docker compose up -d bot` с предыдущим image-tag).

## ModerationQueueTooDeep

**Что**: `sum(moderation_queue_depth) > 50` ≥ 60 мин.

**Действия**:
1. Написать в чат модераторов с прямой ссылкой на `/mod`.
2. Если модераторы недоступны — временно поднять лимит `MAX_FICS_PER_DAY` вниз, чтобы снизить входной поток.
3. После разгребания — проверить, что `ix_moderation_queue_open` используется (`EXPLAIN` на `pick_next`).

## TGApiBadResponses

**Что**: `rate(bot_tg_api_calls_total{result="error"}[5m]) > 1 rps` ≥ 5 мин.

**Действия**:
1. Grafana → Fantik TG API → панель «Errors by method» — какой method течёт.
2. `429 Too Many Requests`: скорее всего `broadcast`, проверь bucket wait p95.
3. `401 Unauthorized`: токен отозван или ротация сломалась → см. **Token rotation**.
4. `403 Forbidden` при sendMessage: юзер заблокировал бота (ок, это не авария, если ратe низкий).

## BroadcastStalled

**Что**: `rate(broadcast_deliveries_total{status="sent"}[5m]) == 0` при очереди `> 0`.

**Действия**:
1. `docker compose ps worker-broadcast` — контейнер running? Если exited — `make logs worker-broadcast`, перезапусти: `docker compose up -d worker-broadcast`.
2. `finalize_broadcast` и `deliver_one` идемпотентны — при рестарте долив продолжится.
3. Если контейнер OK, но 0 отправок → Redis lock: `redis-cli GET broadcast:global:lock` (не должен существовать).
4. Проверь `allow_paid_broadcast`: если включили и лимит bucket = 1000 — TG всё равно отклонит >30/чат.

## OutboxLagHigh

**Что**: `outbox_oldest_pending_age_seconds > 300`.

**Действия**:
1. `make logs worker | grep outbox_dispatch_tick` — тик проходит? Если нет — scheduler жив?
2. `docker compose ps scheduler` — running?
3. `SELECT count(*) FROM outbox WHERE published_at IS NULL;` — сколько висит.
4. Если застряло в `_dispatch_one`: лог покажет `outbox_dispatch_failed` с ошибкой. Часто — Redis недоступен для kiq. Проверь Redis → `make logs | grep redis`.
5. Временный work-around: `UPDATE outbox SET published_at = now() WHERE event_type = 'report.created'` (safe, dispatcher их и так проигнорировал бы).

## WorkerQueueBacklog

**Что**: `max(worker_queue_depth) > 1000` ≥ 10 мин.

**Действия**:
1. Какая очередь? `worker_queue_depth{queue="fantik:tasks"}` vs `fantik:broadcast`.
2. `docker compose ps worker worker-broadcast` — не зависли ли consumers.
3. Перезапустить воркер — он пересоберёт connection pool.
4. Если backlog растёт непрерывно — нужно горизонтально масштабировать (увеличить replicas, добавить шардирование broadcast queue).

## Meilisearch недоступен

**Симптом**: поиск падает / `circuit_open` в логах.

**Автоматика**: circuit breaker ([src/app/infrastructure/search/indexer.py](../../src/app/infrastructure/search/indexer.py)) отпадает на PG FTS через 3 ошибки подряд на 60±10 секунд. Пользователь видит баннер «поиск в безопасном режиме».

**Что сделать вручную**:
1. `docker compose ps meilisearch` → restart.
2. Если БД индекса повреждена: `docker compose down meilisearch && rm -rf meili_data && docker compose up -d meilisearch`, затем `await broker.task('full_reindex').kiq()` — полный re-index из PG.

## PG full disk / PG down

**Симптом**: `/readyz` → `pg=false`.

**Действия**:
1. `df -h` на хосте PG — место есть?
2. `SELECT pg_size_pretty(pg_database_size('fantik'));` — какой размер.
3. Большие партиции: `tracking_events_YYYY_MM`, `audit_log_YYYY_MM`. Старые можно `DETACH PARTITION ... ; DROP TABLE ...` (docs/03 §Партиционирование).
4. `VACUUM (VERBOSE, ANALYZE) ...` на горячих таблицах.
5. Если unreachable вовсе — попытка recovery из бэкапа: `scripts/restore_drill.sh` против staging для проверки, затем — против prod (с пред-approval).

## Token rotation

**Когда**: `BOT_TOKEN` скомпрометирован или по плановому графику.

**Шаги**:
1. У @BotFather — `/revoke` старый, `/newtoken`.
2. Обнови `.env` на проде: `BOT_TOKEN=...`.
3. Разлогинь webhook, если был: `curl -X POST https://api.telegram.org/bot<old-token>/deleteWebhook` (или через нового бота `/setWebhook`).
4. Rolling restart:
   ```
   docker compose up -d bot
   docker compose up -d worker-broadcast   # copy_message требует тот же токен
   ```
5. Убедиться в `make logs-bot`: `webhook_set` / `bot_starting_polling`.
6. Smoke: `make smoke`.

## Plan recovery drill (ежемесячно)

1. Убедись, что свежий дамп есть: `ls -lt /var/backups/fantik/`.
2. На staging-машине: `STAGING_PGHOST=... STAGING_PGUSER=... STAGING_PGDATABASE=fantik_staging scripts/restore_drill.sh /var/backups/fantik/pg-...dump.gz`.
3. Drill должен закончиться `[drill] OK`. Если нет — разбирать: дамп битый или schema-drift.
4. Запись в аудит: дата, успех/неуспех, комментарий.

## Эскалация

1. Если алерт сохраняется > 30 мин и runbook не помог — `@owner` в приватном чате админов.
2. Если это утечка PII / compromised token / breach — немедленно отрубать бота (`docker compose stop bot worker-broadcast`), писать owner'у.
