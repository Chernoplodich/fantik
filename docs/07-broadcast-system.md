# 07 · Система рассылок

Ключевая админская фича. Архитектурно отделена от основного worker'а, чтобы гигантские рассылки не блокировали обычные уведомления.

## Принципы

1. **Не парсим и не пересобираем сообщение.** Telegram уже умеет идеально копировать через `copyMessage` — воспроизводит текст, форматирование (entities), медиа, custom/animated emoji. Мы лишь даём команду «скопируй это сообщение вон тому пользователю».
2. **Шаблон — реальное сообщение в чате админа с ботом.** Админ пишет/пересылает его в бот; бот запоминает `source_chat_id + source_message_id`.
3. **Клавиатура (inline-кнопки) задаётся отдельно** — её нельзя извлечь из forwarded/input-сообщения. Админ собирает через wizard или вводит JSON.
4. **Rate-limit через глобальный token-bucket в Redis** на 25 msg/s (запас от лимита 30).
5. **Идемпотентность** — задача `deliver_one(broadcast_id, user_id)` проверяет статус по `broadcast_deliveries.status` перед отправкой: если уже `sent` или `blocked` — no-op.

## Flow целиком

```mermaid
sequenceDiagram
    participant A as Admin
    participant B as Bot
    participant DB as PostgreSQL
    participant S as Scheduler
    participant WB as Worker-Broadcast
    participant TG as Telegram Bot API
    participant U as Users

    A->>B: /broadcast → FSM.waiting_source
    A->>B: пересылает/пишет шаблон
    B->>DB: broadcasts INSERT (status='draft', source_*, keyboard=null, segment=null, scheduled=null)
    B->>A: copyMessage(превью из шаблона)
    B->>A: "Добавить кнопки?"
    A->>B: wizard: [текст] [url]
    B->>DB: UPDATE broadcasts SET keyboard=...
    B->>A: "Выбор сегмента"
    A->>B: выбор пресета
    B->>DB: UPDATE broadcasts SET segment_spec=...
    B->>A: "Когда?" [Сразу] [Отложенно]
    A->>B: Отложенно → дата/время/таймзона
    B->>DB: UPDATE broadcasts SET scheduled_at=..., status='scheduled'
    Note over S: scheduler tick (каждую минуту)
    S->>DB: SELECT id FROM broadcasts WHERE status='scheduled' AND scheduled_at <= now() FOR UPDATE SKIP LOCKED
    S->>DB: UPDATE status='running', started_at=now()
    S->>WB: enqueue run_broadcast(id)
    WB->>DB: resolve segment → SELECT user_ids (cursor, batches of 1000)
    loop for each batch
        WB->>DB: INSERT broadcast_deliveries (broadcast_id, user_id, status='pending') ON CONFLICT DO NOTHING
        WB->>WB: schedule deliver_one(broadcast_id, user_id) × N
    end
    WB->>DB: stats.total = count
    par Massive parallel
        loop N параллельных воркеров
            WB->>WB: acquire global rate token (25 msg/s)
            WB->>TG: copyMessage(chat_id=user, from_chat=admin, msg_id=source, reply_markup=kb)
            alt OK
                WB->>DB: broadcast_deliveries.status='sent', sent_at=now()
            else 429 retry_after=N
                WB->>WB: sleep(N+jitter); retry (не увеличивая attempts)
            else 403 blocked
                WB->>DB: broadcast_deliveries.status='blocked'
            else other
                WB->>DB: attempts += 1; ≤ 3 — requeue; > 3 — status='failed'
            end
        end
    end
    WB->>DB: UPDATE broadcasts SET status='finished', finished_at, stats={total,sent,failed,blocked}
    WB->>A: notification "Рассылка #X завершена: sent=Y, failed=Z, blocked=W"
```

## FSM админа

```python
# presentation/bot/fsm/states/broadcast.py
class BroadcastFlow(StatesGroup):
    waiting_source = State()
    waiting_keyboard = State()
    waiting_segment = State()
    waiting_schedule = State()
    confirm = State()
```

FSM хранится в Redis (standard aiogram RedisStorage).

## Приём шаблона

```python
@router.message(BroadcastFlow.waiting_source, F.chat.type == "private")
@inject
async def on_source_message(message: Message, state: FSMContext, uc: CreateBroadcastDraftUseCase):
    result = await uc(CreateBroadcastDraftCommand(
        created_by=message.from_user.id,
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
    ))
    await state.update_data(broadcast_id=result.id)

    # превью: бот сам себе копирует шаблон — админ видит как будет у читателя
    await bot.copy_message(
        chat_id=message.chat.id,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await message.answer("Добавить inline-кнопки? [Да] [Нет]")
    await state.set_state(BroadcastFlow.waiting_keyboard)
```

Проверки:
- Не принимаем сервисные сообщения, `forwardedMediaGroup` (медиа-группы копируются только через `copy_messages` — делаем заметку, MVP ограничиваемся одиночными сообщениями).
- Сохраняем `source_chat_id` — это чат `admin ↔ bot`.

## Wizard клавиатуры

Формат ввода:

```
Читать фик | https://t.me/fantik_bot?start=fic_42
Подписаться | https://t.me/channel
```

Каждая строка — кнопка (текст + `|` + url). Пустая строка — разделитель строк в клавиатуре. Бот парсит, валидирует URL (https://, tg://), сохраняет в `keyboard` как `InlineKeyboardMarkup.model_dump()`.

Альтернативно — пошаговый wizard с кнопками `[+ Кнопка]` `[+ Новый ряд]` `[Готово]`.

## Сегменты

Пресеты в inline-меню:

- **Все пользователи** (`{"kind":"all"}`)
- **Активные за N дней** (N: 1/7/30) — `last_seen_at > now() - Nd`
- **Авторы** — `author_nick IS NOT NULL AND EXISTS published fanfics`
- **Подписчики автора X**
- **Пришедшие по UTM `<code>`**
- **Комбинация** — AND/OR через админский JSON editor (v2)

Резолвер:

```python
# application/broadcasts/enumerate_recipients.py
class EnumerateRecipientsUseCase:
    async def __call__(self, broadcast_id: int) -> AsyncIterator[list[int]]:
        spec = await repo.get_segment_spec(broadcast_id)
        where, params = segment_to_sql(spec)
        async for batch in session.stream_scalars(
            select(User.id).where(where).where(User.banned_at.is_(None))
            .order_by(User.id).execution_options(yield_per=1000),
            params,
        ).partitions(1000):
            yield list(batch)
```

SQL-билдер `segment_to_sql`:

```python
def segment_to_sql(spec: dict) -> tuple[ClauseElement, dict]:
    kind = spec["kind"]
    if kind == "all":
        return User.id.is_not(None), {}
    if kind == "active_since_days":
        return User.last_seen_at > text("now() - make_interval(days => :d)"), {"d": spec["value"]}
    if kind == "authors":
        return User.author_nick.is_not(None), {}
    if kind == "subscribers_of":
        return User.id.in_(select(Subscription.subscriber_id).where(Subscription.author_id == spec["author_id"])), {}
    if kind == "utm":
        return User.utm_source_code_id == select(TrackingCode.id).where(TrackingCode.code == spec["code"]).scalar_subquery(), {}
    if kind == "and":
        clauses, all_params = zip(*[segment_to_sql(x) for x in spec["items"]])
        p = {}
        for d in all_params: p.update(d)
        return and_(*clauses), p
    ...
```

## Rate limiter

Глобальный token bucket в Redis с lua-скриптом:

```lua
-- KEYS[1] = bucket key
-- ARGV[1] = rate (tokens/sec)
-- ARGV[2] = capacity
-- ARGV[3] = now (ms)
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1]) or tonumber(ARGV[2])
local ts = tonumber(data[2]) or tonumber(ARGV[3])
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
tokens = math.min(capacity, tokens + (now - ts) / 1000 * rate)
if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
  redis.call('PEXPIRE', KEYS[1], 60000)
  return 1
else
  local wait_ms = math.ceil((1 - tokens) * 1000 / rate)
  redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
  redis.call('PEXPIRE', KEYS[1], 60000)
  return -wait_ms
end
```

Python-клиент acquire:

```python
async def acquire(self, key: str, rate: float, capacity: int) -> None:
    while True:
        result = await self._script(
            keys=[key], args=[str(rate), str(capacity), str(int(time.time()*1000))]
        )
        if result == 1:
            return
        await asyncio.sleep(-result / 1000)
```

`worker-broadcast` вызывает `await bucket.acquire("broadcast:global", 25, 25)` перед каждым `copy_message`.

## Доставка одной копии

```python
# infrastructure/tasks/broadcast.py
@broker.task(retry_on_error=False)
async def deliver_one(broadcast_id: int, user_id: int) -> None:
    async with uow:
        delivery = await deliveries.get_for_update(broadcast_id, user_id)
        if delivery.status in ("sent", "blocked"):
            return
        broadcast = await broadcasts.get(broadcast_id)
        user = await users.get(user_id)
        kb = build_keyboard(broadcast.keyboard) if broadcast.keyboard else None

        await bucket.acquire("broadcast:global", 25.0, 25)
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=broadcast.source_chat_id,
                message_id=broadcast.source_message_id,
                reply_markup=kb,
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.1)
            raise RetryImmediate()  # кастомная ошибка, requeue без инкремента
        except TelegramForbiddenError:
            delivery.mark_blocked()
        except TelegramBadRequest as e:
            delivery.mark_failed(str(e))
            if delivery.attempts < 3:
                raise Retry(delay_seconds=2 ** delivery.attempts)
        else:
            delivery.mark_sent()
        await deliveries.save(delivery)
        await uow.commit()
```

## Отмена и редактирование

- **Отмена `scheduled`**: status = `cancelled` — scheduler не возьмёт.
- **Отмена `running`**: status = `cancelled`. `deliver_one` в начале проверяет статус — если cancelled, no-op. Уже отправленные — не отозвать (Telegram так не умеет через copyMessage; только для пересылок у админа есть deleteMessage — не распространено в broadcast).
- **Правка шаблона после отправки**: нельзя. Создаётся новая рассылка.

## Повторная отправка

На экране рассылки `finished` кнопка `[Повторить для упавших]` — создаёт новую `broadcast` с `segment_spec = {"kind":"retry","parent_broadcast_id":X}`. Резолвер:
```sql
SELECT user_id FROM broadcast_deliveries
WHERE broadcast_id = :parent AND status IN ('failed','pending')
```

## Массовые эмодзи и премиум

- `copyMessage` **сохраняет custom emoji (MessageEntity `custom_emoji`)** — проверено в Bot API 7+. Если получатель не premium — эмодзи рендерится как fallback-текст, это штатное поведение TG.
- Ничего специального со стороны бота делать не нужно.

## Отчёт

После `finished` админ получает:

```
Рассылка #123 завершена.

Всего: 10 240
Отправлено: 9 812
Заблокировано: 321
Ошибки: 107
Длительность: 7 мин 4 сек
Средняя скорость: 24.1 msg/s

[Повторить для упавших] [Скачать CSV] [Подробно]
```

«Подробно» — распределение ошибок по кодам (`chat not found`, `too many requests`, etc.).

## Переключение в paid broadcast (1000 msg/s)

Если критично ускорить — в админке флаг `allow_paid_broadcast=True`. Task устанавливает параметр в `copyMessage`, снимает локальный rate-limit до 1000/s. Стоимость — 0.1 Stars за сообщение — показывается админу до подтверждения.

## Безопасность

- Только `admin` может создавать рассылки.
- В превью всегда показываем `кол-во получателей` перед запуском.
- Аудит: `broadcast.create/schedule/launch/cancel` → `audit_log`.
- Лимит: не более N активных рассылок в момент времени (N = 3 по умолчанию).

## Тесты

- Unit: `segment_to_sql` на всех пресетах → снапшот SQL.
- Integration: testcontainers, прогон 1000 получателей → проверяем таблицу `broadcast_deliveries`.
- E2E: фейковый Bot API (aioresponses), проверяем, что `copyMessage` вызван столько раз, сколько получателей.
- Load: 100_000 получателей, замер p95 latency и общего времени (ожидаем ≈ 4000 сек при 25 msg/s).
