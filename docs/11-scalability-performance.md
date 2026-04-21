# 11 · Масштабируемость и производительность

## Этапы роста

### MVP (до 10 000 пользователей, ≤ 500 одновременных)
- 1 контейнер `bot` (polling).
- 1 контейнер `worker` (TaskIQ, 4 воркера).
- 1 контейнер `worker-broadcast` (4 воркера, общий bucket).
- 1 контейнер `scheduler`.
- PG, Redis, Meilisearch — по одному контейнеру.
- Всё на 1 VPS с 2 vCPU, 4 ГБ RAM.

### Средний рост (10k–100k)
- `bot` переключить на webhook (меньше лишнего трафика polling'а).
- `worker` реплицирован до 2–4 инстансов.
- `worker-broadcast` до 8 инстансов.
- PG — выделенный управляемый инстанс.
- Redis — выделенный.
- Meilisearch — отдельная машина или managed.
- VPS или две: bot+worker отдельно от stateful-сервисов.

### Крупный рост (100k+)
- Read-replica PG для отчётов/статистики.
- Кэш «горячих» фиков и страниц в Redis с агрессивной префетчкой.
- Meilisearch cloud (или шардинг при > 1M документов).
- Horizontal autoscaling воркеров по глубине очередей.
- Возможно — переезд на Kubernetes + HPA.

## Ключевые кэши (Redis)

| Ключ | Значение | TTL | Назначение |
|---|---|---|---|
| `user_role:{tg_id}` | `user`/`moderator`/`admin` | 60 сек | не ходить в PG за ролью каждый апдейт |
| `user_banned:{tg_id}` | `1`/`0` | 60 сек | быстрый бан-чек |
| `fic:{id}:meta` | JSON карточки (title, author, tags, ...) | 10 мин | каталог, карточки |
| `fic:ch:{chapter_id}:p:{page}` | msgpack(text, entities) | 1 час | страницы читалки |
| `catalog:new:{offset}` | JSON ids | 60 сек | пагинация «новое» |
| `inline:{hash(query)}` | JSON результатов | 60 сек | инлайн-поиск |
| `suggest:{kind}:{prefix}` | JSON вариантов | 5 мин | автодополнение фильтров |
| `broadcast:global` | bucket state | — | rate-limit рассылок |
| `throttle:{tg_id}` | bucket state | 60 сек | anti-flood |
| `progress_throttle:{uid}:{fic}` | `1` | 5 сек | troттлинг `reading_progress` upsert |
| `fsm:{tg_id}` | state + data | 1 час | стандартное aiogram RedisStorage |

Размер Redis: расчётно 200 МБ на 100k активных юзеров при TTL 1 час. При росте — увеличение памяти линейное, можно перейти на `maxmemory-policy allkeys-lru`.

## Паттерны оптимизации

### Anti-flood (throttle per user)

Middleware с token-bucket 30 апдейтов/мин на `from_user.id`:

```python
class ThrottleMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = event.from_user.id
        allowed = await bucket.acquire(f"throttle:{uid}", rate=0.5, capacity=30)
        if not allowed:
            # one-time warning per time-window
            seen = await redis.set(f"throttle_warn:{uid}", "1", nx=True, ex=60)
            if seen:
                await event.answer("Ты слишком быстро. Подожди минуту.")
            return  # drop update
        return await handler(event, data)
```

### Batched database writes

- `tracking_events` — можно буферизировать и писать пачками раз в 1 сек (TaskIQ tick-задача). Для MVP сразу INSERT — проще.
- `last_seen_at` — обновлять не чаще раза в минуту на юзера (Redis-лок `last_seen:{uid}` NX EX 60).

### Prefetch страниц

При рендере страницы N — асинхронно (без await) готовим N+1 в Redis:

```python
asyncio.create_task(warm_cache(chapter_id, page_no + 1))
```

### Денормализация счётчиков

`fanfics.likes_count`, `chapters_count`, `chars_count`, `reads_completed_count` — все поддерживаются **атомарными UPDATE** в той же транзакции, что и event:

```python
await session.execute(
    update(Fanfic)
    .where(Fanfic.id == fic_id)
    .values(likes_count=Fanfic.likes_count + 1)
)
```

Пересчёт «с нуля» — раз в сутки в scheduler (job `recompute_counters`), чтобы дрейф исключить.

### Партиционирование

- `tracking_events` — по месяцам, автосоздание партиций на 2 месяца вперёд (scheduler).
- `audit_log` — по месяцам.
- `broadcast_deliveries` — hash 16.

Автосоздание:

```sql
CREATE TABLE IF NOT EXISTS tracking_events_y2026m05 PARTITION OF tracking_events
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

Удаление старых — опционально по политике хранения (например, старше 2 лет — detach + archive).

### Индексы

(см. [`03-data-model.md`](03-data-model.md))

Правило: каждый часто использующийся WHERE/JOIN/ORDER BY имеет покрывающий индекс. EXPLAIN ANALYZE в CI для критичных запросов (смоук):

- Поиск в каталоге «новое».
- «Мои черновики».
- Очередь модерации (`pick_next`).
- Чтение `chapter_pages` по (chapter_id, page_no).
- Перечисление получателей рассылки по сегментам.

### Connection pooling

`asyncpg` + SQLAlchemy async pool:

- `pool_size=10, max_overflow=10, pool_timeout=30, pool_recycle=1800` — стартовые значения.
- На воркерах — пул меньше (`pool_size=5`) — т.к. много процессов × много коннектов > лимита PG.
- В проде — pgbouncer в transaction-mode при > 100 одновременных коннектов.

### Redis pool

`aioredis.Redis` connection pool на 50 коннектов, decode_responses=False (msgpack).

### Ленивые импорты

Большие подмодули (matplotlib для графиков) импортируются внутри функции-использования, чтобы не грузить при старте bot-процесса.

## Стратегии нагрузки

### Сценарий: массовая регистрация (новый источник трафика)

Ожидаемое: 10 000 `/start` за 10 минут.

- Пик — 16 RPS.
- `/start` хэндлер: upsert в `users` (1 SQL), `tracking_events` INSERT (1 SQL), `show_main_menu` (1 TG API call).
- На 1 bot-контейнере (asyncio) — укладываемся без напряга.
- PG: 32 RPS запросов — нормально.
- Метрика `bot_handler_duration_seconds{handler="start"}` p95 должна быть < 150 мс.

### Сценарий: большая рассылка

Ожидаемое: 100 000 получателей.

- Скорость — 25 msg/s → ~67 мин.
- Пара `worker-broadcast` по 4 воркера — достаточно, bottleneck — глобальный bucket.
- Увеличение пула воркеров не ускорит (bucket общий).
- Если срочно — `allow_paid_broadcast=True` + bucket 1000/s → ~100 сек.

### Сценарий: одновременное чтение

Ожидаемое: 1 000 юзеров одновременно листают разные фики.

- На пользователя: 1 callback_query + `editMessageText` + 1 cache lookup + 1 TG API call.
- 1 000 × 0.5 RPS (одно перелистывание в 2 сек) = 500 RPS.
- Redis: 500 GET / 500 SETEX — cruising speed.
- PG: только на cache miss — допустим 10% → 50 SELECT'ов/сек из `chapter_pages`.
- TG API: 500 calls/s — **может упереться в лимит 30 msg/s для одного чата**. Но тут 1000 разных чатов — лимит 30 msg/s global для бота тоже существует, но только для именно `sendMessage` **новым** чатам. `editMessageText` существующих сообщений лимит мягче (по слухам — до ~1000/sec). Если бот будет ловить `RetryAfter` — логируем и реагируем ретраем.

### Сценарий: большой фик (100k символов, 200 глав)

- Паджинация главы 1000 символов — < 5 мс.
- Паджинация главы 100k символов — < 50 мс (асинхронная, в воркере).
- Suma по фику: 200 глав × 50 мс = 10 сек на публикацию → фик идёт в approved, `repaginate_all_chapters` ставится в очередь и выполняется 10 сек в фоне.

## Нагрузочное тестирование

- **Locust** или **k6** — симуляция `/start`, чтения, поиска.
- Сценарии в `tests/load/`:
  - `load_start.py` — 1000 `/start` за 60 сек.
  - `load_reading.py` — 500 юзеров по 10 минут листают случайные фики.
  - `load_broadcast.py` — 50k получателей, проверяется конечное `stats`.
- Цели:
  - p95 `/start` < 200 мс.
  - p95 read-page < 150 мс.
  - Рассылка не замедляет обычные уведомления (`notification.delivery_latency_seconds` p95 < 2 сек во время пика).

## Горизонтальное масштабирование

### Bot

- **Polling** — **только один** инстанс. Telegram отдаёт getUpdates строго одному потребителю.
- **Webhook** — за Nginx, можно любое количество реплик. Для stateful работы (FSM) — FSM в Redis, OK.

### Worker

- Сколько угодно — TaskIQ сам распределяет.
- Идемпотентные задачи: `index_fanfic`, `deliver_one`, `notify_subscriber`.

### Worker-broadcast

- Сколько угодно — rate-limit в Redis общий.
- `deliver_one` идемпотентно по `broadcast_deliveries.status`.

### Scheduler

- **Один активный** (на lock в Redis `scheduler:leader:<name>` EX 30, продлевается каждые 10 сек). При падении — другой инстанс за 30 сек подхватит.

## Graceful shutdown

- SIGTERM: прекратить принимать новые апдейты/задачи, доделать текущие, закрыть коннекты.
- Контейнеры с `stop_grace_period: 60s` в Compose.

## Backpressure

- Если TaskIQ-очередь перегружена (> N задач) — bot отвечает «Сервис под нагрузкой, попробуй через минуту» и не ставит новые тяжёлые задачи. Метрика `taskiq_queue_depth{queue}`.

## Circuit breakers

- `aiobreaker`/собственная реализация для Meili и TG Bot API:
  - На Meili при 3 fail подряд → open на 60 сек → fallback PG FTS.
  - На TG API — аккуратнее: мы не можем не отвечать пользователю; на open — пробуем Bot API снова (retry-after).

## Checklist оптимизаций MVP

- [x] Индексы для hot-path запросов.
- [x] Партиционирование time-series.
- [x] Redis-кэш ролей и страниц.
- [x] Throttle per-user.
- [x] Throttle по прогрессу.
- [x] Денормализованные счётчики.
- [x] Материализованные страницы.
- [x] Event-driven индексация.
- [x] Выделенный worker-broadcast.
- [x] Token-bucket broadcast rate-limit.
- [x] Prefetch страниц при чтении.

## Что решаем позже

- Шардинг БД.
- CDN для обложек.
- Read-replicas.
- Kubernetes с HPA.

Архитектура не требует их сейчас; добавляются точечно, не переписывая код.
