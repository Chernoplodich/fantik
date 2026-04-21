# 03 · Модель данных (PostgreSQL)

> Все таблицы в схеме `public`. Первичные ключи: `BIGSERIAL` по умолчанию, `BIGINT` для telegram id. Timestamptz везде в UTC. Удаление — soft where nontrivial (флаги / статусы), hard — где можно.

## Условные обозначения

- `PK` — primary key
- `FK → table.col` — foreign key
- `UQ` — unique
- `IX` — индекс
- `PIX` — частичный индекс
- `GIN` — GIN-индекс (для массивов, jsonb, tsvector)
- `BRIN` — BRIN-индекс (для time-series)

---

## Пользователи и роли

### `users`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGINT PK | = Telegram user id (избегаем суррогата — TG id уникален) |
| `username` | TEXT NULL | Telegram @username (может меняться) |
| `first_name` | TEXT NULL | Кэш для отображения, обновляется при каждом апдейте |
| `last_name` | TEXT NULL | — |
| `language_code` | TEXT NULL | из апдейта |
| `timezone` | TEXT NOT NULL DEFAULT 'Europe/Moscow' | для отложенных рассылок и отображения дат |
| `role` | `user_role` ENUM('user','moderator','admin') NOT NULL DEFAULT 'user' | |
| `author_nick` | TEXT NULL UQ | Уникальный ник автора (задаётся при первой публикации). Case-insensitive UNIQUE через `LOWER(author_nick)` |
| `utm_source_code_id` | BIGINT FK → tracking_codes.id NULL | Источник первого `/start` |
| `banned_at` | timestamptz NULL | |
| `banned_reason` | TEXT NULL | |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |
| `last_seen_at` | timestamptz NOT NULL DEFAULT now() | Обновляется middleware не чаще 1 раза в минуту |

Индексы:
- `UQ` на `LOWER(author_nick)` через `CREATE UNIQUE INDEX ... ON users (LOWER(author_nick)) WHERE author_nick IS NOT NULL`.
- `IX (role) WHERE role != 'user'` — быстро найти модераторов/админов.
- `IX (last_seen_at)` — для сегмента «активные за N дней».
- `IX (utm_source_code_id)` — для отчёта по UTM.

---

## Трекинг

### `tracking_codes`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `code` | TEXT NOT NULL UQ | base62, 8 символов, URL-safe |
| `name` | TEXT NOT NULL | Человеческое имя: «Реклама в канале X» |
| `description` | TEXT NULL | |
| `created_by` | BIGINT FK → users.id NOT NULL | admin |
| `active` | BOOLEAN NOT NULL DEFAULT TRUE | |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

### `tracking_events` (партиционирована по месяцам)
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL | (part of PK for partitioned tables: `(id, created_at)`) |
| `code_id` | BIGINT FK → tracking_codes.id | Может быть NULL для органики |
| `user_id` | BIGINT FK → users.id | |
| `event_type` | `tracking_event_type` ENUM('start','register','first_read','first_publish','custom') NOT NULL | |
| `payload` | JSONB NULL | Для custom-событий (например id фика) |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Индексы:
- `BRIN (created_at)` — время-серийные данные.
- `IX (code_id, event_type, created_at)` — воронки по коду.
- `IX (user_id)` — чтобы быстро по юзеру.

Партиционирование: `PARTITION BY RANGE (created_at)`, месячные партиции, автосоздание через cron-задачу (в scheduler).

---

## Справочники

### `fandoms`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `slug` | TEXT NOT NULL UQ | `harry-potter`, `marvel` |
| `name` | TEXT NOT NULL | «Гарри Поттер» |
| `category` | TEXT NOT NULL | books / movies / games / series / anime / …  |
| `aliases` | TEXT[] NOT NULL DEFAULT '{}' | `['HP', 'Hogwarts', 'Поттериана']` |
| `active` | BOOLEAN NOT NULL DEFAULT TRUE | |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Индексы:
- `GIN (aliases)` — для поиска синонимов.
- `IX (category)`.

### `age_ratings`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | SMALLSERIAL PK | |
| `code` | TEXT NOT NULL UQ | `G`, `PG`, `PG-13`, `R`, `NC-17` |
| `name` | TEXT NOT NULL | Человеческое имя |
| `description` | TEXT NOT NULL | |
| `min_age` | SMALLINT NOT NULL | Для возрастного gating |
| `sort_order` | SMALLINT NOT NULL | |

Заполняется сидом при миграции; редактировать запрещено.

### `tags`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `name` | TEXT NOT NULL | В том виде, в котором автор ввёл (норм. через trim+single-space+lower) |
| `slug` | TEXT NOT NULL UQ | `lower(name).replace(' ', '-').replace(...)` |
| `kind` | `tag_kind` ENUM('character','theme','warning','freeform') NOT NULL | |
| `usage_count` | INTEGER NOT NULL DEFAULT 0 | Для популярности и автокомплита |
| `merged_into_id` | BIGINT FK → tags.id NULL | Если тег «слит» модератором в канонический |
| `approved_at` | timestamptz NULL | NULL = ожидает модерации алиасом (опционально) |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Индексы:
- `IX (kind, usage_count DESC)` — популярные теги по категории для подсказок.
- `IX (slug)` UQ уже есть.
- `IX (merged_into_id) WHERE merged_into_id IS NOT NULL`.

Политика: при публикации свободный тег матчится по `slug`; если не найден — создаётся. Модератор потом может `MERGE`: у всех `fanfic_tags` ссылается на `canonical`, `merged_into_id` ставится у дубликата.

---

## Фанфики

### `fanfics`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `author_id` | BIGINT FK → users.id NOT NULL | |
| `title` | TEXT NOT NULL | Макс. 128 символов |
| `summary` | TEXT NOT NULL | Макс. 2000 символов |
| `summary_entities` | JSONB NOT NULL DEFAULT '[]' | MessageEntities для summary |
| `cover_file_id` | TEXT NULL | Telegram file_id (переменчив, но живёт долго; делаем refresh-by-resend при необходимости) |
| `cover_file_unique_id` | TEXT NULL | Стабильный идентификатор для дедупликации |
| `fandom_id` | BIGINT FK → fandoms.id NOT NULL | |
| `age_rating_id` | SMALLINT FK → age_ratings.id NOT NULL | |
| `status` | `fic_status` ENUM('draft','pending','approved','rejected','revising','archived') NOT NULL DEFAULT 'draft' | |
| `current_version_id` | BIGINT FK → fanfic_versions.id NULL | Последняя опубликованная версия |
| `chapters_count` | INTEGER NOT NULL DEFAULT 0 | Кэш |
| `chars_count` | INTEGER NOT NULL DEFAULT 0 | Кэш суммы `chapters.chars_count` |
| `views_count` | BIGINT NOT NULL DEFAULT 0 | Увеличивается денормализовано |
| `likes_count` | INTEGER NOT NULL DEFAULT 0 | Счётчик лайков |
| `reads_completed_count` | INTEGER NOT NULL DEFAULT 0 | Сколько юзеров дочитали всю работу (последняя глава → последняя страница) |
| `first_published_at` | timestamptz NULL | Установлено при первом `approved` |
| `last_edit_at` | timestamptz NULL | При любой правке |
| `deleted_at` | timestamptz NULL | soft-delete |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |
| `updated_at` | timestamptz NOT NULL DEFAULT now() | авто-триггер |

Индексы:
- `IX (author_id, status, updated_at DESC)` — «мои фики» автора + сортировка.
- `PIX (status) WHERE status = 'pending'` — очередь модерации (fast scan).
- `PIX (status, first_published_at DESC) WHERE status = 'approved'` — лента «новое».
- `PIX (status, likes_count DESC) WHERE status = 'approved'` — лента «топ».
- `IX (fandom_id, status) WHERE status = 'approved'` — браузинг по фандому.
- `IX (age_rating_id) WHERE status = 'approved'`.
- Covering-index по (status='approved', updated_at desc) INCLUDE (id, title, likes_count) — для пагинации без heap-lookup.

### `fanfic_tags` (m:n)
| `fic_id` BIGINT FK → fanfics.id | `tag_id` BIGINT FK → tags.id | PK (fic_id, tag_id) |

- `IX (tag_id, fic_id)` — для «фики по тегу».

### `fanfic_versions`
Снимок метаданных + списка глав при переиздании.

| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `fic_id` | BIGINT FK → fanfics.id | |
| `version_no` | INTEGER NOT NULL | incrementing |
| `title` | TEXT NOT NULL | |
| `summary` | TEXT NOT NULL | |
| `summary_entities` | JSONB NOT NULL | |
| `snapshot_chapters` | JSONB NOT NULL | Массив {chapter_id, title, chars_count, text_hash} для аудита |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

UQ (fic_id, version_no).

### `chapters`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `fic_id` | BIGINT FK → fanfics.id NOT NULL | |
| `number` | INTEGER NOT NULL | Порядковый номер главы |
| `title` | TEXT NOT NULL | |
| `text` | TEXT NOT NULL | Plain text UTF-8 |
| `entities` | JSONB NOT NULL DEFAULT '[]' | MessageEntity[] |
| `chars_count` | INTEGER NOT NULL | UTF-16 units (для точного лимита) |
| `status` | `fic_status` NOT NULL DEFAULT 'draft' | Глава может быть в `pending`, даже если фик `approved` (когда автор добавил новую главу) |
| `tsv_title` | tsvector GENERATED ALWAYS AS (to_tsvector('russian', coalesce(title,''))) STORED | |
| `tsv_text` | tsvector GENERATED ALWAYS AS (to_tsvector('russian', text)) STORED | Резерв для FTS |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |
| `updated_at` | timestamptz NOT NULL DEFAULT now() | |

UQ (fic_id, number).

Индексы:
- `IX (fic_id, number)` — ordered read.
- `GIN (tsv_text)` — резервный FTS.
- `GIN (tsv_title)` — для поиска по заголовкам.
- `PIX (status) WHERE status = 'pending'` — очередь по главам.

### `chapter_pages` (материализованные страницы)
Рассчитываются воркером `repaginate_chapter` после каждого изменения.

| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `chapter_id` | BIGINT FK → chapters.id ON DELETE CASCADE | |
| `page_no` | INTEGER NOT NULL | 1..N |
| `text` | TEXT NOT NULL | Порция текста, ≤ 3900 UTF-16 units |
| `entities` | JSONB NOT NULL | MessageEntity[] с offset, пересчитанным относительно начала страницы |
| `chars_count` | INTEGER NOT NULL | |

UQ (chapter_id, page_no).

Индексы:
- `IX (chapter_id, page_no)` — чтение.

---

## Модерация

### `moderation_queue`
Элемент очереди на модерацию: либо весь фик (при первой публикации), либо отдельная глава (при добавлении/правке).

| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `fic_id` | BIGINT FK → fanfics.id NOT NULL | |
| `chapter_id` | BIGINT FK → chapters.id NULL | Если NULL — модерация всего фика |
| `kind` | `mq_kind` ENUM('fic_first_publish','fic_edit','chapter_add','chapter_edit') NOT NULL | |
| `submitted_by` | BIGINT FK → users.id NOT NULL | автор |
| `submitted_at` | timestamptz NOT NULL DEFAULT now() | |
| `locked_by` | BIGINT FK → users.id NULL | moderator id |
| `locked_until` | timestamptz NULL | lock timeout 15 мин; при истечении освобождается |
| `decision` | `mq_decision` ENUM('approved','rejected') NULL | |
| `decision_reason_ids` | BIGINT[] NOT NULL DEFAULT '{}' | Выбранные причины из справочника |
| `decision_comment` | TEXT NULL | Свободный текст от модератора |
| `decision_comment_entities` | JSONB NOT NULL DEFAULT '[]' | |
| `decided_by` | BIGINT FK → users.id NULL | |
| `decided_at` | timestamptz NULL | |

Индексы:
- `PIX (submitted_at) WHERE decision IS NULL AND (locked_until IS NULL OR locked_until < now())` — очередь для забора.
- `IX (locked_by, decided_at DESC)` — отчёт по модератору.
- `IX (fic_id, submitted_at DESC)` — история по работе.

Забор задания:
```sql
WITH next AS (
  SELECT id FROM moderation_queue
  WHERE decision IS NULL
    AND (locked_until IS NULL OR locked_until < now())
  ORDER BY submitted_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE moderation_queue
SET locked_by = $moderator_id, locked_until = now() + interval '15 minutes'
WHERE id IN (SELECT id FROM next)
RETURNING *;
```

### `moderation_reasons`
Справочник готовых причин отказа.

| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `code` | TEXT NOT NULL UQ | `NSFW_NO_RATING`, `PLAGIARISM`, `LOW_QUALITY` и т.д. |
| `title` | TEXT NOT NULL | Короткое имя для кнопки |
| `description` | TEXT NOT NULL | Пояснение, которое видит автор при отказе |
| `active` | BOOLEAN NOT NULL DEFAULT TRUE | |
| `sort_order` | INTEGER NOT NULL DEFAULT 0 | |

Редактируется admin'ом.

---

## Социальные функции

### `bookmarks`
| `user_id` BIGINT FK → users.id | `fic_id` BIGINT FK → fanfics.id | `created_at` timestamptz NOT NULL DEFAULT now() | PK (user_id, fic_id) |

Индексы:
- `IX (fic_id)` — обратный reference.

### `likes`
| `user_id` BIGINT FK → users.id | `fic_id` BIGINT FK → fanfics.id | `created_at` timestamptz NOT NULL DEFAULT now() | PK (user_id, fic_id) |

Индексы:
- `IX (fic_id)`.

Триггеры: при INSERT/DELETE — обновлять `fanfics.likes_count` (atomic `+=1 / -=1`).

### `reads_completed`
Факт прочтения главы до конца (последняя страница просмотрена).

| `user_id` BIGINT | `chapter_id` BIGINT FK → chapters.id | `completed_at` timestamptz NOT NULL DEFAULT now() | PK (user_id, chapter_id) |

Когда пользователь закончил **последнюю** главу фика — увеличиваем `fanfics.reads_completed_count`.

### `reading_progress`
| `user_id` BIGINT FK → users.id | `fic_id` BIGINT FK → fanfics.id | `chapter_id` BIGINT FK → chapters.id | `page_no` INTEGER | `updated_at` timestamptz | PK (user_id, fic_id) |

Индексы:
- `IX (user_id, updated_at DESC)` — «продолжить чтение» с сортировкой по свежести.

### `subscriptions` (подписка читателя на автора)
| `subscriber_id` BIGINT FK → users.id | `author_id` BIGINT FK → users.id | `created_at` timestamptz NOT NULL | PK (subscriber_id, author_id) |

- `IX (author_id)` — fanout уведомлений.

### `reports` (жалобы читателей)
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `reporter_id` | BIGINT FK → users.id | |
| `target_type` | `report_target` ENUM('fanfic','chapter','user','comment') | |
| `target_id` | BIGINT | Референс зависит от target_type, без FK (денормализация) |
| `reason_code` | TEXT NULL | Из справочника или custom |
| `text` | TEXT NULL | |
| `text_entities` | JSONB NOT NULL DEFAULT '[]' | |
| `status` | `report_status` ENUM('open','dismissed','actioned') NOT NULL DEFAULT 'open' | |
| `handled_by` | BIGINT FK → users.id NULL | |
| `handled_at` | timestamptz NULL | |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Индексы:
- `PIX (target_type, target_id, status) WHERE status='open'`.

---

## Рассылки

### `broadcasts`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `created_by` | BIGINT FK → users.id | admin |
| `source_chat_id` | BIGINT NOT NULL | chat_id админа, где лежит шаблон |
| `source_message_id` | BIGINT NOT NULL | |
| `keyboard` | JSONB NULL | InlineKeyboardMarkup (массив массивов InlineKeyboardButton) |
| `segment_spec` | JSONB NOT NULL | `{"kind":"all"}` / `{"kind":"active_since_days","value":7}` / `{"kind":"utm","code":"abc123"}` / `{"kind":"authors"}` / `{"kind":"subscribers_of","author_id":42}` / `{"kind":"and","items":[...]}`|
| `scheduled_at` | timestamptz NULL | NULL = сразу |
| `status` | `bc_status` ENUM('draft','scheduled','running','finished','cancelled','failed') NOT NULL DEFAULT 'draft' | |
| `stats` | JSONB NOT NULL DEFAULT '{}' | `{total, sent, failed, blocked}` |
| `started_at` | timestamptz NULL | |
| `finished_at` | timestamptz NULL | |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Индексы:
- `IX (status, scheduled_at)` — для scheduler.

### `broadcast_deliveries` (партиционирована по `broadcast_id` hash на 16)
| Колонка | Тип | Комментарий |
|---|---|---|
| `broadcast_id` | BIGINT FK → broadcasts.id | |
| `user_id` | BIGINT FK → users.id | |
| `status` | `bcd_status` ENUM('pending','sent','failed','blocked') NOT NULL DEFAULT 'pending' | |
| `attempts` | SMALLINT NOT NULL DEFAULT 0 | |
| `error_code` | TEXT NULL | |
| `sent_at` | timestamptz NULL | |

PK (broadcast_id, user_id).

Индексы:
- `IX (broadcast_id, status)` — прогресс.
- `PIX (status) WHERE status='pending'` — что ещё слать.

Партиционирование по hash: `PARTITION BY HASH (broadcast_id)`, 16 партиций. Равномерно распределяет объёмы больших рассылок.

---

## Уведомления

### `notifications`
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `user_id` | BIGINT FK → users.id | Получатель |
| `kind` | TEXT NOT NULL | `moderation_decision`, `new_chapter_from_author`, `report_processed`, `custom` |
| `payload` | JSONB NOT NULL | |
| `sent_at` | timestamptz NULL | Когда фактически отправлено через sendMessage |
| `read_at` | timestamptz NULL | Когда юзер подтвердил (если применимо) |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Индексы:
- `PIX (user_id, sent_at) WHERE sent_at IS NULL` — очередь на отправку.
- `IX (created_at)`.

В MVP уведомления отправляются сразу в worker'е без выделенной очереди (пишем в `notifications`, тут же планируем задачу `deliver_notification`). При росте — вынести в отдельный воркер.

---

## Аудит

### `audit_log` (партиционирована по месяцам)
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL | |
| `actor_id` | BIGINT FK → users.id NULL | NULL для системных действий |
| `action` | TEXT NOT NULL | `fic.approve`, `fic.reject`, `broadcast.start`, `user.ban`, `tag.merge`, … |
| `target_type` | TEXT NULL | `fanfic`, `chapter`, `user`, … |
| `target_id` | BIGINT NULL | |
| `payload` | JSONB NOT NULL DEFAULT '{}' | Before/after, причины |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |

Индексы:
- `BRIN (created_at)`.
- `IX (actor_id, created_at DESC)`.
- `IX (target_type, target_id, created_at DESC)`.

---

## Вспомогательные

### `outbox` (гарантированная публикация событий)
| Колонка | Тип | Комментарий |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `event_type` | TEXT NOT NULL | |
| `payload` | JSONB NOT NULL | |
| `created_at` | timestamptz NOT NULL DEFAULT now() | |
| `published_at` | timestamptz NULL | |

Воркер `outbox_dispatcher` каждые 1-2 секунды читает `WHERE published_at IS NULL ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 100`, публикует в TaskIQ, ставит `published_at`.

Индексы:
- `PIX (id) WHERE published_at IS NULL`.

### `rate_limit_state` (опционально; чаще храним в Redis)
Резервный лог для recovery, если Redis упал. В MVP не обязательна.

---

## Перечисления (ENUM)

Создать миграцией через `sqlalchemy.Enum(..., name="...", create_type=True)` или CREATE TYPE:

- `user_role` (user, moderator, admin)
- `fic_status` (draft, pending, approved, rejected, revising, archived)
- `tag_kind` (character, theme, warning, freeform)
- `tracking_event_type` (start, register, first_read, first_publish, custom)
- `mq_kind` (fic_first_publish, fic_edit, chapter_add, chapter_edit)
- `mq_decision` (approved, rejected)
- `bc_status` (draft, scheduled, running, finished, cancelled, failed)
- `bcd_status` (pending, sent, failed, blocked)
- `report_target` (fanfic, chapter, user, comment)
- `report_status` (open, dismissed, actioned)

---

## Материализованные представления (для статистики)

### `mv_daily_activity`
```sql
CREATE MATERIALIZED VIEW mv_daily_activity AS
SELECT
  date_trunc('day', created_at AT TIME ZONE 'UTC')::date AS day,
  count(*) FILTER (WHERE event_type = 'start') AS starts,
  count(*) FILTER (WHERE event_type = 'register') AS registers,
  count(*) FILTER (WHERE event_type = 'first_read') AS first_reads,
  count(*) FILTER (WHERE event_type = 'first_publish') AS first_publishes
FROM tracking_events
GROUP BY 1
WITH DATA;
```

Обновление — `REFRESH MATERIALIZED VIEW CONCURRENTLY` раз в 10 минут через scheduler.

Аналогично:
- `mv_top_fandoms_7d` — топ фандомов за 7 дней.
- `mv_author_stats` — агрегаты по автору.
- `mv_moderator_load` — кол-во решений по модератору за день.

---

## Миграция схемы (Alembic план)

**Migration 0001_init**: ENUMы, таблицы `users`, `tracking_codes`, `tracking_events` (с партиционированием), `fandoms`, `age_ratings`, `tags` + сиды фандомов-топа и возрастных рейтингов.

**Migration 0002_fanfics**: `fanfics`, `fanfic_tags`, `fanfic_versions`, `chapters`, `chapter_pages`.

**Migration 0003_moderation**: `moderation_queue`, `moderation_reasons` + сиды причин.

**Migration 0004_social**: `bookmarks`, `likes`, `reads_completed`, `reading_progress`, `subscriptions`, `reports`.

**Migration 0005_broadcasts**: `broadcasts`, `broadcast_deliveries` (partitioned).

**Migration 0006_audit_outbox`: `audit_log` (partitioned), `outbox`, `notifications`.

**Migration 0007_views**: материализованные представления.

**Migration 0008_triggers**: триггеры `updated_at`, счётчики.

---

## Триггеры

1. **`updated_at`-trigger** на `users`, `fanfics`, `chapters` — `BEFORE UPDATE` set `updated_at = now()`.
2. **Счётчики**: `likes` INSERT/DELETE → `fanfics.likes_count += / -=`. `chapters` INSERT/DELETE → `fanfics.chapters_count += / -=`. (Можно оставить на application-слое — обсудимо; триггер даёт consistency.)
3. **tsvector**: генерируется через `GENERATED ALWAYS AS ... STORED` — триггер не нужен.

---

## Производительность и масштабирование

- `BIGINT` PK везде, где возможен взрывной рост (`fanfics`, `tracking_events`, `audit_log`, `broadcast_deliveries`).
- Партиционирование больших таблиц: `tracking_events` (месяц), `audit_log` (месяц), `broadcast_deliveries` (hash).
- Частичные индексы на «горячие» сабсеты (`status='pending'`, `status='approved'`) — меньше и быстрее.
- Covering-индексы для read-heavy путей (каталоги).
- BRIN на time-series — компактно, дёшево.
- GIN только там, где реально нужен (массивы, jsonb, tsvector).
- VACUUM/ANALYZE — штатный autovacuum достаточен для MVP; под ростом настроить per-table `fillfactor` и параметры autovacuum.
- Read-replica — после ~100k пользователей: всю статистику и отчёты переносим туда.

---

## Диаграмма ERD

См. [`diagrams/erd.md`](diagrams/erd.md).
