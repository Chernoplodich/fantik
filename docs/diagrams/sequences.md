# Ключевые sequence-диаграммы

Все — в Mermaid; дублируют/углубляют сценарии из [`../05-user-flows.md`](../05-user-flows.md) и [`../07-broadcast-system.md`](../07-broadcast-system.md).

## 1. Публикация → модерация → индексация

```mermaid
sequenceDiagram
    autonumber
    actor A as Author
    participant B as Bot
    participant UC as SubmitForReview
    participant PG as PostgreSQL
    participant OUT as outbox
    participant OD as OutboxDispatcher
    participant Q as TaskIQ
    actor M as Moderator
    participant UC2 as Approve
    participant W as Worker
    participant MS as Meilisearch

    A->>B: callback "Отправить на модерацию"
    B->>UC: SubmitForReviewCommand(fic_id)
    UC->>PG: UPDATE fanfics SET status='pending'
    UC->>PG: INSERT moderation_queue(...)
    UC->>OUT: INSERT outbox(FanficSubmitted)
    UC-->>B: ok
    B-->>A: "Отправлено"
    OD->>OUT: SELECT unpublished
    OD->>Q: publish notify_moderators
    Q->>W: deliver task
    W->>M: sendMessage "В очередь добавлена работа #N"

    M->>B: /mod → pick next
    B->>PG: FOR UPDATE SKIP LOCKED ...
    PG-->>B: case
    B-->>M: карточка + кнопки
    M->>B: "Одобрить"
    B->>UC2: ApproveCommand(mq_id, fic_id)
    UC2->>PG: UPDATE moderation_queue, UPDATE fanfics status='approved'
    UC2->>OUT: INSERT outbox(FanficApproved)
    UC2-->>B: ok
    B-->>M: "Одобрено"
    OD->>Q: publish index_fanfic, notify_author, notify_subscribers
    W->>MS: upsert document
    W->>A: sendMessage "Твоя работа одобрена!"
```

---

## 2. Чтение страницы

```mermaid
sequenceDiagram
    autonumber
    actor U as Reader
    participant B as Bot
    participant R as Redis
    participant PG as chapter_pages
    participant UC as Paginator

    U->>B: callback "▶ next page"
    B->>R: GET fic:_:ch:X:p:Y
    alt cache hit
        R-->>B: page
    else miss
        B->>PG: SELECT text,entities WHERE chapter_id=X AND page_no=Y
        alt exists
            PG-->>B: page
            B->>R: SETEX 3600
        else not yet paginated
            B->>UC: paginate(chapter.text, entities)
            UC-->>B: pages[]
            B->>PG: INSERT chapter_pages ON CONFLICT DO NOTHING
            B->>R: SETEX 3600
        end
    end
    B->>U: editMessageText(page.text, entities, keyboard)
    B-->>B: prefetch page Y+1 (fire-and-forget)
    B->>R: SET progress_throttle:U:fic NX EX 5
    alt lock acquired
        B->>PG: upsert reading_progress
    else
        B-->>B: skip (throttled)
    end
```

---

## 3. Рассылка

```mermaid
sequenceDiagram
    autonumber
    actor Adm as Admin
    participant B as Bot
    participant FSM as FSM
    participant PG as PostgreSQL
    participant S as Scheduler
    participant WB as worker-broadcast
    participant RL as RateLimiter (Redis)
    participant TG as Telegram

    Adm->>B: /broadcast
    B->>FSM: set state waiting_source
    Adm->>B: forwards template message
    B->>PG: INSERT broadcasts (source_chat, source_msg, status='draft')
    B->>TG: copyMessage back to admin (preview)
    Adm->>B: + inline keyboard
    B->>PG: UPDATE broadcasts SET keyboard=...
    Adm->>B: + segment (e.g. active_7d)
    B->>PG: UPDATE broadcasts SET segment_spec=...
    Adm->>B: + scheduled_at (tomorrow 10:00)
    B->>PG: UPDATE broadcasts SET scheduled_at=..., status='scheduled'

    Note over S: cron tick каждую минуту
    S->>PG: SELECT due scheduled FOR UPDATE SKIP LOCKED
    S->>PG: UPDATE status='running'
    S->>WB: enqueue run_broadcast(id)

    WB->>PG: stream user_ids in batches of 1000
    WB->>PG: INSERT broadcast_deliveries ON CONFLICT DO NOTHING
    WB->>WB: schedule deliver_one(bc_id, user_id) × N

    loop каждый deliver_one
        WB->>RL: acquire "broadcast:global" 25/s
        RL-->>WB: ok
        WB->>TG: copyMessage(user_id, source_chat, source_msg, kb)
        alt sent
            TG-->>WB: message_id
            WB->>PG: UPDATE delivery SET status='sent'
        else 429
            TG-->>WB: retry_after=5
            WB->>WB: sleep 5s; retry (без attempt++)
        else 403 blocked
            TG-->>WB: Forbidden
            WB->>PG: UPDATE delivery SET status='blocked'
        else error
            WB->>PG: attempts++ ≤3 requeue; >3 failed
        end
    end

    WB->>PG: UPDATE broadcasts status='finished', stats={...}
    WB->>TG: sendMessage to admin "Рассылка завершена: ..."
```

---

## 4. Отказ и повторная отправка

```mermaid
sequenceDiagram
    autonumber
    actor A as Author
    actor M as Moderator
    participant B as Bot
    participant PG as PostgreSQL

    M->>B: "Отклонить"
    B->>M: выбор причин (multi) + комментарий
    M->>B: ✅ подтвердить
    B->>PG: UPDATE moderation_queue SET decision='rejected', reason_ids=[..], comment=..
    B->>PG: UPDATE fanfics SET status='rejected'
    B->>A: notification "Отказ. Причины: ... [Доработать]"

    A->>B: tap "Доработать"
    B->>PG: UPDATE fanfics SET status='revising'
    B->>A: открыть FSM EditFanfic (выбор что править)
    A->>B: правки
    A->>B: "Отправить повторно"
    B->>PG: UPDATE fanfics SET status='pending'
    B->>PG: INSERT moderation_queue(kind='fic_edit')
    B->>A: "Отправлено. Среднее время — N мин."
```

---

## 5. Поиск с фасетами

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Bot
    participant MS as Meilisearch

    U->>B: "Каталог → Фильтры"
    B->>U: меню: [Фандом] [Возраст] [Теги] [Сорт]
    U->>B: выбор (multi через callback toggles)
    U->>B: "Показать"
    B->>MS: search(q="", filter="status='approved' AND fandom_id IN [1,3]", facets=[...], sort=[likes_count:desc], limit=10, offset=0)
    MS-->>B: {hits, facetDistribution, estimatedTotalHits}
    B->>U: карточки + фасеты (кнопки с кол-вами) + пагинация
    U->>B: "Добавить тег Ангст"
    B->>MS: search(filter="... AND tags='Ангст'")
    MS-->>B: обновлённые результаты + обновлённые facetDistribution
```

---

## 6. Онбординг с UTM и deep-link на фик

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant TG as Telegram
    participant B as Bot
    participant PG as PostgreSQL

    U->>TG: clicks t.me/fantik_bot?start=fic_42
    TG->>B: /start fic_42
    B->>PG: upsert user
    B->>B: parse payload → special="fic_42"
    B->>PG: SELECT fanfic 42
    alt approved
        PG-->>B: fic
        B->>U: sendPhoto(cover, caption=title+summary, [Читать][Подписаться])
        B->>PG: tracking_events('custom', payload={deeplink:'fic', id:42})
    else not available
        B->>U: "Работа недоступна"
    end
```

---

## 7. Жалоба

```mermaid
sequenceDiagram
    autonumber
    actor U as Reader
    actor M as Moderator
    participant B as Bot
    participant PG as PostgreSQL

    U->>B: "⚠️ Жалоба" на странице
    B->>U: меню причин + опц. коммент
    U->>B: отправка
    B->>PG: INSERT reports(status='open')
    B->>U: "Жалоба принята"
    M->>B: /mod → "Жалобы"
    B->>PG: SELECT open reports
    B->>M: список + карточка
    M->>B: "Удалить работу"
    B->>PG: UPDATE fanfics SET status='archived'; UPDATE reports SET status='actioned'
    B->>U: notify "По твоей жалобе приняли меры"
    B->>Author: notify "Работа снята с публикации: <причина>"
```
