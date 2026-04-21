# 05 · Пользовательские сценарии

Диаграммы в Mermaid. Номера у сценариев — ссылочные (используются в `15-testing.md`).

## 1. Онбординг

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant DB as PostgreSQL
    participant T as Tracking

    U->>B: /start ref_abc123
    B->>DB: users.upsert(tg_id)
    alt first time
        B->>T: tracking_events('start', code=abc123, user)
        B->>U: Приветствие + правила + кнопка "Согласен"
    else returning
        B->>U: Главное меню
    end
    U->>B: tap "Согласен"
    B->>DB: users.agreed_at = now()
    B->>T: tracking_events('register')
    B->>U: Главное меню (каталог / мои / стать автором)
```

**Детали**:
- `/start` без параметра — обычный онбординг.
- `/start <code>` — парсим `code` (8 символов base62), валидируем по `tracking_codes`, пишем `tracking_events`. Если юзер новый — сохраняем `users.utm_source_code_id`.
- «Согласие с правилами» фиксируется в `users.agreed_at` (колонка добавится при необходимости — сейчас можно просто ставить наличие записи).
- Если юзер забанен (`banned_at IS NOT NULL`) — показываем только сообщение «Доступ ограничен» с причиной.

---

## 2. Становление автором (установка ника)

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant UC as SetAuthorNickUseCase
    participant DB as PostgreSQL

    U->>B: menu "Стать автором"
    B->>U: "Введи ник (2-32, a-z0-9_-)"
    U->>B: "mark_the_writer"
    B->>UC: SetAuthorNick(user_id, "mark_the_writer")
    UC->>DB: UPDATE users SET author_nick=? WHERE id=? AND author_nick IS NULL
    alt unique OK
        UC-->>B: ok
        B->>U: "Ник закреплён. Теперь можно создавать фики."
    else taken
        UC-->>B: NickTakenError
        B->>U: "Ник занят, предложи другой"
    end
```

- Ник менять после установки — нельзя без обращения к модератору (политика доверия к имени автора). Если потребуется — команда `/change_nick` с подтверждением модератора.
- UNIQUE на `LOWER(author_nick)` — защита от обхода регистром.

---

## 3. Создание фанфика и глав (FSM)

```mermaid
stateDiagram-v2
    [*] --> Title
    Title --> Summary: текст
    Summary --> Fandom: текст или пропуск
    Fandom --> AgeRating: выбор из inline
    AgeRating --> Tags: выбор из inline
    Tags --> Cover: ввод тегов/пропуск
    Cover --> Review: фото/пропуск
    Review --> AddChapter: "Добавить главу"
    AddChapter --> ChapterTitle
    ChapterTitle --> ChapterText
    ChapterText --> ChapterReview
    ChapterReview --> AddChapter: "Ещё главу"
    ChapterReview --> Submit: "На модерацию"
    Submit --> [*]
```

**Ключевой момент** — приём текста с форматированием:

```python
# psevdokod в author_create.py
@router.message(CreateFanfic.chapter_text)
async def on_chapter_text(message: Message, state: FSMContext, use_case: AddChapterDraftUseCase):
    cmd = AddChapterDraftCommand(
        fic_id=...,
        number=...,
        title=...,
        text=message.text or message.caption or "",
        entities=[e.model_dump() for e in (message.entities or message.caption_entities or [])],
    )
    await use_case(cmd)
```

Валидация:
- `len(text)` в UTF-16 units ≤ 100_000.
- Entities: нет `url` с `javascript:`/`data:`; `text_mention` — только на существующих юзеров (опционально: блокируем вовсе, оставляя `mention`).
- Custom emoji — разрешены.
- Лимит глав на фик — 200.

При «Сохранить черновик» — фик остаётся в `draft`, главы тоже `draft`. Возврат возможен через «Мои черновики» в профиле.

---

## 4. Публикация и модерация

```mermaid
sequenceDiagram
    participant A as Author
    participant B as Bot
    participant UC as SubmitForReview
    participant DB as PostgreSQL
    participant Q as moderation_queue
    participant M as Moderator

    A->>B: "На модерацию"
    B->>UC: SubmitForReview(fic_id)
    UC->>DB: UPDATE fanfics SET status='pending'
    UC->>Q: INSERT moderation_queue(kind='fic_first_publish')
    UC-->>B: ok
    B->>A: "Отправлено. Среднее время — X мин."
    Note right of M: асинхронно
    M->>B: menu "Очередь модерации"
    B->>Q: SELECT FOR UPDATE SKIP LOCKED LIMIT 1
    Q-->>B: case
    B->>M: карточка фика + кнопки
    alt Approve
        M->>B: "Одобрить"
        B->>DB: fanfics.status='approved', mq.decision='approved'
        B->>A: notification "Работа одобрена!"
        B--)Indexer: event FanficApproved → index в Meili
    else Reject
        M->>B: выбор причин + комментарий
        B->>DB: fanfics.status='rejected', mq.decision='rejected', reason_ids, comment
        B->>A: notification "Отказ: <причины> <комментарий> [Доработать]"
    end
```

### Повторная отправка после отказа

```mermaid
sequenceDiagram
    participant A as Author
    participant B as Bot

    A->>B: tap "Доработать" (из уведомления об отказе)
    B->>A: показать причины отказа + комментарий модератора целиком
    B->>A: открыть FSM EditFanfic (выбор что править: summary/title/глава N)
    A->>B: правки
    A->>B: "Отправить на повторную модерацию"
    B->>DB: status='pending', mq INSERT kind='fic_edit'
    B->>A: "Отправлено."
```

---

## 5. Чтение

```mermaid
sequenceDiagram
    participant U as Reader
    participant B as Bot
    participant R as Repo
    participant Cache as Redis

    U->>B: tap "Читать" на карточке фика
    B->>R: fanfic.get(fic_id)
    B->>R: chapters.list_by_fic(fic_id)
    B->>U: sendPhoto(cover, caption=title+summary, keyboard=[Начать читать])

    U->>B: "Начать читать" → first_chapter=1, page=1
    B->>Cache: GET fic:{id}:ch:1:p:1
    alt cache hit
        Cache-->>B: text + entities
    else miss
        B->>R: chapter_pages.get(chapter_id=1, page_no=1)
        alt pages exist
            R-->>B: text + entities
        else not paginated yet
            B->>B: PaginateChapterUseCase → build pages → save to DB
            R-->>B: page1
        end
        B->>Cache: SETEX 3600
    end
    B->>U: editMessageText(text, entities, reply_markup=nav)
    B->>R: save_progress (throttled)

    U->>B: "▶" (callback)
    B->>Cache: GET fic:{id}:ch:1:p:2
    B->>U: editMessageText ...
```

### Клавиатура читалки

```
[ ◀ Назад ] [ Глава 1 · 2/7 ] [ Дальше ▶ ]
[ 📑 Закладка ] [ ❤️ Лайк ] [ ⚠️ Жалоба ]
[ 📖 Оглавление ]
```

Callback data — компактные `CallbackData` классы:
```python
class ReadNav(CallbackData, prefix="r"):
    fic_id: int
    chapter_no: int
    page_no: int
    action: Literal["next","prev","chapter","toc","bookmark","like","report"]
```

### Edge cases

- Последняя страница последней главы → запись в `reads_completed(user_id, chapter_id)`; если это была последняя глава фика — increment `fanfics.reads_completed_count`.
- «Дальше» на последней странице главы — переход на первую страницу следующей главы.
- «Дальше» на последней странице фика — показать «Читать завершён! [Лайк] [Поделиться] [К автору]».

---

## 6. Поиск и фильтры

### 6a. Через меню

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant M as Meilisearch

    U->>B: "Каталог → Фильтры"
    B->>U: inline-меню: [Фандом] [Возраст] [Теги] [Сортировка]
    U->>B: выбор множественно (мультиселект через callback toggle)
    U->>B: "Показать"
    B->>M: search(q="", filter="status='approved' AND fandom_id IN [...] AND age_rating IN [...]", facets=[fandom_name,age_rating,tags], sort=["likes_count:desc"], limit=10, offset=0)
    M-->>B: hits + facetDistribution
    B->>U: список карточек + кнопки пагинации
    U->>B: "▶" страницу
    B->>M: offset += 10
```

### 6b. Через инлайн-режим

```mermaid
sequenceDiagram
    participant U as User
    participant TG as Telegram
    participant B as Bot
    participant M as Meilisearch
    participant C as Redis

    U->>TG: @fantik_bot Гарри Поттер romance
    TG->>B: inline_query
    B->>C: cached inline?
    alt hit
        C-->>B: результаты
    else miss
        B->>M: search
        M-->>B: hits
        B->>C: SETEX 60
    end
    B->>TG: answerInlineQuery(results, cache_time=60)
    TG->>U: карусель результатов
    U->>TG: tap result → возвращает пользователю ссылку/карточку в чат
```

---

## 7. Подписка на автора

```mermaid
sequenceDiagram
    participant U as Reader
    participant B as Bot
    participant UC as Subscribe
    participant DB as PostgreSQL

    U->>B: открыт фик → tap "Подписаться на автора"
    B->>UC: Subscribe(subscriber_id, author_id)
    UC->>DB: INSERT subscriptions ON CONFLICT DO NOTHING
    UC-->>B: ok
    B->>U: "Подписался!"
```

### Уведомление о новой главе/работе

```mermaid
sequenceDiagram
    participant DB as PostgreSQL
    participant W as Worker
    participant BAPI as Telegram Bot API

    Note over DB: FanficApproved / ChapterPublished event
    DB->>W: TaskIQ task notify_subscribers(author_id, fic_id, chapter_id?)
    W->>DB: SELECT subscriber_id FROM subscriptions WHERE author_id=?
    loop batch 100
        W->>BAPI: sendMessage(...) с кнопкой "Читать"
    end
```

Частота: без rate-limit глобально (новая работа — редкое событие), но с локальным throttle 25 msg/s для защиты от hit лимита TG.

---

## 8. Жалоба

```mermaid
sequenceDiagram
    participant U as Reader
    participant B as Bot
    participant M as Moderator

    U->>B: tap "⚠️ Жалоба" на странице чтения / карточке фика
    B->>U: выбор причины (inline-меню) + опц. комментарий
    U->>B: отправка
    B->>DB: INSERT reports(status='open')
    B->>U: "Жалоба принята, разберёмся"
    Note right of M: асинхронно
    M->>B: "Жалобы" → список open
    M->>B: решение: Dismiss / Action (удалить, бан, ...)
    B->>DB: reports.status, audit_log
    B->>U: notification о результате (опц.)
```

---

## 9. Админская статистика

```mermaid
sequenceDiagram
    participant A as Admin
    participant B as Bot
    participant V as MaterializedViews / Redis

    A->>B: /admin → "Статистика"
    B->>V: SELECT FROM mv_daily_activity ORDER BY day DESC LIMIT 30
    V-->>B: rows
    B->>A: таблица + ссылка "График"
    A->>B: tap "График"
    B->>B: render PNG (matplotlib / quickchart.io)
    B->>A: sendPhoto(chart.png)
```

Доступные дашборды:
- Ежедневная активность (starts, regs, first_read, first_publish) за 30/90 дней.
- Retention cohort (DAU, W1, W2, M1).
- Воронка по UTM-коду.
- Топ фандомов / авторов.
- Нагрузка модераторов.

---

## 10. Админские рассылки

См. подробный флоу в [`07-broadcast-system.md`](07-broadcast-system.md). Здесь — короткий user-level:

1. `/admin → Рассылки → Новая`.
2. Бот просит отправить/переслать сообщение-шаблон.
3. Бот сохраняет `source_message_id`, показывает превью через `copyMessage` обратно админу.
4. Админ добавляет inline-кнопки (wizard).
5. Админ выбирает сегмент из пресетов или описательно.
6. Админ выбирает время (сразу / отложенно).
7. Бот показывает финальное превью: «будет отправлено N пользователям, старт в HH:MM UTC+3. Запустить?»
8. Запуск → scheduler/worker.

---

## 11. Деплинки внутри бота (ссылки на фик)

Генерация: `t.me/<bot>?start=fic_<id>`. При получении — `/start fic_42` — бот открывает карточку фика 42.

Кейсы использования:
- Поделиться фиком другу.
- Внутренняя кнопка «Поделиться» в карточке фика — копирует ссылку.

Валидация — формат `fic_<int>`.
