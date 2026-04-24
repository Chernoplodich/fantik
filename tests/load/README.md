# Load tests

3 сценария для проверки SLA из [`docs/11`](../../docs/11-scalability-performance.md) и [`docs/15`](../../docs/15-testing.md):

| Сценарий | Цель | SLA | Команда |
|---|---|---|---|
| [`load_start.py`](load_start.py) | 1000 `/start` / 60s | p95 < 200 мс, err < 0.5% | `make load-start` |
| [`load_reading.py`](load_reading.py) | 500 юзеров × 10 мин листают | p95 read_page < 150 мс, err < 0.5% | `make load-reading` |
| [`load_broadcast.py`](load_broadcast.py) | рассылка на 50 000 | sent ≥ 99%, status=finished | `make load-broadcast` |

## Как это работает

Все сценарии — **синтетика без реального Telegram**. Бот запускается с
`TG_API_BASE=http://fake-tg:9999`, все исходящие API-вызовы упираются в
[`fake_tg_server.py`](fake_tg_server.py), который отвечает каноническим
`{ok: true}`.

Входящие апдейты locust гонит в webhook-эндпоинт бота — как будто это
Telegram. Путь берём из env переменных `BOT_TOKEN` + `WEBHOOK_PATH`,
так как webhook URL = `<base>/<path>/<sha256(token)[:32]>`.

## Подготовка среды

```bash
# 1. Поднять стек с loadtest-profile:
docker compose --profile loadtest up -d postgres redis meilisearch migrate fake-tg

# 2. Поднять бота с fake-TG:
TG_API_BASE=http://fake-tg:9999 docker compose up -d bot worker worker-broadcast scheduler

# 3. (для load-reading) seed-данные: 100 фиков × 10 глав × 100k симв.
#    Пример минимального seed'а — см. scripts/seed_load.py (добавить при
#    первом прогоне).
```

## Запуск

```bash
make load-start         # ожидание ≈ 1-2 мин, печатает Locust CSV
make load-reading       # ≈ 10 мин
make load-broadcast     # до 1 часа
```

Makefile таргеты exit=1 если SLA нарушено (assert внутри `@events.quitting`).

## Важно

- Локально запускай **только против dev-стека с fake-tg**. Load-тесты против
  реального `api.telegram.org` приведут к немедленному баку бота по rate-limit
  или к нарушению ToS.
- Выключи Sentry перед load-прогоном — иначе сэмплером засоришь dsn. Делается
  `SENTRY_DSN=""` в env.
- `TG_API_BASE` внутри бота читается при старте. Если забыл — бот попытается
  ходить на `api.telegram.org` и локуст провалит по таймауту на outgoing.

## После прогона

1. CSV-отчёт locust лежит в `tests/load/out/*.csv` — p95, p99 по операциям.
2. Grafana → Fantik dashboards — смотри, какие handlers медленнее всего.
3. Если SLA нарушено — включить `log_min_duration_statement=200ms` в PG,
   повторить прогон, собрать топ медленных SQL, писать индекс-миграцию
   (0010, Этап 7 §3.4 плана).
