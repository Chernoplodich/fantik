# 10 · Трекинг и аналитика

## Модель источников

У бота Telegram нет HTTP-Referer — когда пользователь кликает на `t.me/<bot>?start=<code>` из рекламы, канала, блога, единственный способ узнать источник — параметр `start`.

Ограничения Telegram:
- payload в `start` — до 64 символов.
- допустимые: `A-Za-z0-9_-` (URL-safe; `=` и `&` нельзя).

## Формат кода

- Короткий, человекочитаемый: **8 символов base62** (`A-Za-z0-9`).
- Генерируется через `secrets.token_urlsafe(6)[:8]` с проверкой уникальности.
- Админ задаёт читаемое имя и описание: «TG-канал X», «Реклама Яндекс Директ».

Итоговая ссылка: `https://t.me/fantik_bot?start=x7kqA9pT`.

## Жизненный цикл

### Создание кода

```
/admin → Трекинг → Новый код
```

FSM:
1. Имя.
2. Описание (опц).
3. Генерация кода (или ввод вручную, если свободен).
4. Подтверждение + выдача полной ссылки.

Код сохраняется в `tracking_codes`.

### Регистрация события `start`

Хэндлер `/start`:

```python
@router.message(CommandStart(deep_link=True))
@inject
async def start_with_payload(
    message: Message,
    command: CommandObject,
    uc_register: RegisterUserUseCase,
    uc_track: RecordEventUseCase,
):
    payload = command.args or ""
    code, special = parse_payload(payload)  # "x7kqA9pT" | "fic_42" | ""

    is_new = await uc_register(message.from_user, utm_code=code)
    if code:
        await uc_track(TrackEvent(code=code, user_id=message.from_user.id, event='start', new_user=is_new))

    if special and special.startswith("fic_"):
        # deep-link на конкретный фик
        await open_fic(int(special[4:]), message)
    else:
        await show_main_menu(message)
```

`parse_payload` различает:
- 8-символьный base62 → трекинг-код.
- `fic_<id>` → deep-link на фик.
- Иначе → игнор.

## Конверсионные события

В доменных событиях при соответствующих изменениях публикуем `tracking_events`:

| Triggering event | event_type | Когда |
|---|---|---|
| `UserRegistered` | `register` | после первого `/start` + согласия с правилами |
| `ChapterOpened` (первый раз у юзера) | `first_read` | при первой записи `reading_progress` |
| `FanficSubmitted` (первый раз у юзера) | `first_publish` | первая отправка на модерацию |
| custom | `custom` | бизнес-события (подписка, лайк первого фика — если захотим) |

Механика: use case `RecordEventUseCase` записывает в `tracking_events` с `code_id` = `users.utm_source_code_id` (атрибуция «last-touch» у нас сливается с «first-touch», т.к. `utm_source_code_id` фиксируется при первом `/start` и не меняется).

## Атрибуция: first-touch vs multi-touch

В MVP — **first-touch**: `users.utm_source_code_id` проставляется при первом заходе с кодом, не перезаписывается последующими.

Если пришёл без кода, а потом кликнул на другую ссылку — `users.utm_source_code_id` останется NULL (органика). Решение можно поменять:
- **last-touch**: каждый `/start` с кодом перезаписывает `users.utm_source_code_id`.
- **multi-touch**: храним массив посещений в отдельной таблице `user_code_visits(user_id, code_id, visited_at)`, атрибуция на уровне отчёта.

В MVP фиксируем first-touch; multi-touch — как точка расширения (одна новая таблица).

## Воронка по коду

```sql
SELECT
  c.code,
  c.name,
  count(DISTINCT user_id) FILTER (WHERE event_type='start') AS starts,
  count(DISTINCT user_id) FILTER (WHERE event_type='register') AS registers,
  count(DISTINCT user_id) FILTER (WHERE event_type='first_read') AS first_reads,
  count(DISTINCT user_id) FILTER (WHERE event_type='first_publish') AS first_publishes
FROM tracking_events e
JOIN tracking_codes c ON c.id = e.code_id
WHERE c.code = :code
  AND e.created_at > now() - interval '30 days'
GROUP BY c.code, c.name;
```

Визуализация в боте:

```
Код: x7kqA9pT — «TG-канал X»

Воронка (30 дней):
  starts:          1 024
  registers:         842  (82.2%)
  first_reads:       512  (50.0%)
  first_publishes:    17  ( 1.7%)

Конверсия start→register: 82.2%
Активация: 60.8% (first_read / register)
```

## Аналитика бота в целом

### Метрики retention

```sql
-- cohort: пользователи, зарегистрировавшиеся в день X
-- retention: сколько из них вернулись (last_seen_at) в день X+N
WITH cohorts AS (
  SELECT id, date_trunc('day', created_at)::date AS cohort_day
  FROM users
  WHERE created_at > now() - interval '60 days'
)
SELECT
  cohort_day,
  count(*) AS size,
  count(*) FILTER (WHERE u.last_seen_at >= cohort_day + interval '1 day')  AS d1,
  count(*) FILTER (WHERE u.last_seen_at >= cohort_day + interval '7 days') AS d7,
  count(*) FILTER (WHERE u.last_seen_at >= cohort_day + interval '30 days') AS d30
FROM cohorts c
JOIN users u ON u.id = c.id
GROUP BY cohort_day
ORDER BY cohort_day;
```

### DAU/WAU/MAU

Через materialized view `mv_daily_activity` (см. [`03-data-model.md`](03-data-model.md)) + счёт уникальных `user_id`:

```sql
SELECT
  count(DISTINCT user_id) FILTER (WHERE created_at > now() - interval '1 day') AS dau,
  count(DISTINCT user_id) FILTER (WHERE created_at > now() - interval '7 days') AS wau,
  count(DISTINCT user_id) FILTER (WHERE created_at > now() - interval '30 days') AS mau
FROM tracking_events
WHERE event_type IN ('start','first_read','first_publish');
```

### Топ фандомов

```sql
SELECT fd.name, count(*) AS new_fics
FROM fanfics f
JOIN fandoms fd ON fd.id = f.fandom_id
WHERE f.status='approved' AND f.first_published_at > now() - interval '7 days'
GROUP BY fd.name
ORDER BY new_fics DESC
LIMIT 10;
```

Заливается в `mv_top_fandoms_7d`.

### Топ авторов

По likes_count suммарно + reads_completed — суррогатная оценка качества.

### Нагрузка на модераторов

```sql
SELECT u.id, u.first_name, u.username,
  count(*) FILTER (WHERE mq.decided_at > now() - interval '7 days') AS decisions_7d,
  avg(extract(epoch FROM mq.decided_at - mq.submitted_at)) FILTER (WHERE mq.decided_at > now() - interval '7 days') AS avg_latency_seconds
FROM users u
JOIN moderation_queue mq ON mq.decided_by = u.id
WHERE u.role = 'moderator'
GROUP BY u.id, u.first_name, u.username
ORDER BY decisions_7d DESC;
```

## Рендер графиков

Опции:

- **QuickChart.io** (https://quickchart.io/chart?c=...) — бесплатный сервис рендера Chart.js графиков в PNG через URL. Бот формирует URL и делает `sendPhoto(url)`.
- **matplotlib** локально — полный контроль; чуть больше кода. Предпочитаем matplotlib, если хотим независимость от внешнего сервиса.

Выбираем matplotlib (без внешних зависимостей в проде):

```python
import io
import matplotlib.pyplot as plt

async def render_funnel_png(rows: list[dict]) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["starts", "registers", "first_reads", "first_publishes"]
    values = [rows[-1][k] for k in labels]
    ax.bar(labels, values)
    ax.set_title("Воронка")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
```

`bot.send_photo(chat_id, BufferedInputFile(png, "funnel.png"))`.

## Команды админа

```
/admin stats today          # сегодня (DAU, starts, regs)
/admin stats week           # неделя
/admin stats utm <code>     # воронка по коду
/admin stats moderators     # нагрузка
/admin stats authors        # топ авторов
/admin stats fandoms        # топ фандомов
/admin cohort               # retention
```

Все — в том же боте через inline-кнопки + отправка PNG.

## Экспорт

Опционально: команда `/admin export tracking --since=YYYY-MM-DD --format=csv` — формирует CSV в памяти и отправляет документом. Размер файла — ограничен 50 МБ (Telegram file upload limit). Для большего — split'ить по дням.

## Обновление агрегатов

Scheduler-задача `refresh_materialized_views` раз в 10 минут:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_activity;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_top_fandoms_7d;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_author_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_moderator_load;
```

## Сохранение PII

- `tracking_events` не содержит текстов сообщений, только `user_id` + `event_type` + `payload`.
- `payload` — JSON с метаданными (например, `{"fic_id": 42}` для `first_read`).
- По запросу юзера на удаление данных (см. [`12-security-privacy.md`](12-security-privacy.md)) — `user_id` в `tracking_events` заменяется на NULL или запись анонимизируется пакетно.

## Точки расширения

- **GA4 / Яндекс.Метрика server-to-server** — класс `IAnalyticsSink` реализуется и для них; событие дублируется.
- **Multi-touch** — отдельная таблица `user_code_visits`, отчёты другие.
- **A/B-тесты** — `ab_variants` таблица, добавляется в `tracking_events.payload`.
- **Продуктовые события** (`liked_first_fic`, `subscribed_to_author`, ...) — добавляем в `tracking_event_type` или идём в отдельную таблицу `product_events`.
