# 06 · Администрирование и модерация

## Роли и права

| Право | user | moderator | admin |
|---|:-:|:-:|:-:|
| Читать / лайк / закладка | ✅ | ✅ | ✅ |
| Задать `author_nick`, создавать фики | ✅ | ✅ | ✅ |
| Брать из очереди модерации, approve/reject | — | ✅ | ✅ |
| Обрабатывать жалобы | — | ✅ | ✅ |
| Смотреть статистику | — | Только свою нагрузку | Всё |
| Рассылки | — | — | ✅ |
| Tracking-коды | — | — | ✅ |
| Управление справочниками (фандомы, причины отказа, теги-merge) | — | Предлагать merge | ✅ |
| Банить/разбанивать пользователей | — | — | ✅ |
| Управление ролями | — | — | ✅ |

Права проверяются в middleware `role` + в фильтре `IsModerator`/`IsAdmin` на роутерах админских команд.

## Ролевой кэш

Middleware `role.py`:
- Читает роль из Redis `user_role:{tg_id}` (TTL 60 сек).
- Если нет — `SELECT role FROM users`, кладёт в Redis.
- При изменении роли use case `ChangeRole` инвалидирует ключ.

Так на hot-path не ходим в БД за ролью каждый апдейт.

---

## Очередь модерации

### Принцип

`moderation_queue` — FIFO с distributed locks на уровне строки через `FOR UPDATE SKIP LOCKED`. Никаких Redis-lock'ов — базе достаточно.

### Забор следующего задания

```python
# application/moderation/pick_next.py
async def pick_next(moderator_id: int, uow: IUnitOfWork) -> Optional[ModerationCase]:
    async with uow:
        row = await uow.session.execute(text("""
            WITH next AS (
              SELECT id FROM moderation_queue
              WHERE decision IS NULL
                AND (locked_until IS NULL OR locked_until < now())
              ORDER BY submitted_at
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE moderation_queue
            SET locked_by = :mod_id,
                locked_until = now() + interval '15 minutes'
            WHERE id IN (SELECT id FROM next)
            RETURNING *
        """), {"mod_id": moderator_id})
        case = row.one_or_none()
        await uow.commit()
        return map_to_domain(case)
```

### Возврат протухших локов

Задача `release_stale_mq_locks` в scheduler каждую минуту:
```sql
UPDATE moderation_queue
SET locked_by = NULL, locked_until = NULL
WHERE decision IS NULL
  AND locked_until < now();
```

Безопасность: если модератор возьмёт задание повторно после протухания и примет решение — сработает `UPDATE ... WHERE decision IS NULL` — не перезапишет чужое решение.

---

## Карточка задания

Что видит модератор:

1. Шапка: «Задание #42. Тип: первая публикация. Автор: @ник_в_боте (tg-юзер, зарегистрирован N дней назад).»
2. Тело фика:
   - Обложка (если есть).
   - Title + Summary (с entities, рендерим как есть).
   - Фандом, возрастной рейтинг, теги.
3. Главы (список номер + заголовок + длина). Под каждой — кнопка «Читать главу» (бот отправляет отдельным сообщением копию содержимого для модератора, также с entities).
4. Кнопки решения: `[✅ Одобрить]  [❌ Отклонить]  [⏸ Снять лок]`.

### Одобрение

Один клик. Модератор может дописать комментарий (необязательно). Всё фиксируется в `moderation_queue.decision` + `audit_log`.

### Отклонение

FSM `ModerationReject`:

1. Показать список причин из `moderation_reasons` — multi-select через inline-toggle.
2. Попросить ввести комментарий (опц., до 2000 символов, с entities).
3. Предпросмотр сообщения, которое получит автор.
4. Подтверждение `[✅ Отклонить]`.

Автору уходит уведомление:

```
Твоя работа «<title>» отклонена модератором.

Причины:
• <title причины 1>
  <description причины 1>
• <title причины 2>
  <description причины 2>

Комментарий модератора:
<comment с entities>

[Доработать и отправить повторно]
```

Кнопка `Доработать` → callback → открытие FSM `ReviseAfterRejection`, статус фика → `revising`.

### Отклонение главы (а не всего фика)

Когда в очередь попадает `kind='chapter_edit'` или `chapter_add` — модератор видит только одну главу. При отклонении фик остаётся `approved` (другие главы — доступны читателям), но конкретная глава получает `status='rejected'`, автор может её доработать.

---

## Политика правок

- Любая правка title/summary/глав фика: фик → `pending` целиком, новая запись в `moderation_queue` с kind='fic_edit'. Предыдущая approved-версия остаётся доступной читателям до нового approve (не snapshot'им в рантайме — хранится через `fanfic_versions` только для аудита).
- Добавление новой главы к опубликованной работе: работа остаётся `approved`, но новая глава — `pending`, читателям не видна до approve.

**Исключение (опционально, на усмотрение админа)**: минорные правки (опечатки в рамках N символов изменений) без смены статуса — в MVP не делаем. Если захотим — добавим политику на основе `difflib.unified_diff` процентного изменения.

---

## SLA и метрики

Метрики (Prometheus):

- `moderation_queue_depth{kind}` — gauge, обновляется воркером каждые 30 сек.
- `moderation_lock_age_seconds{moderator_id}` — gauge.
- `moderation_decisions_total{decision, moderator_id}` — counter.
- `moderation_decision_latency_seconds` — histogram (от submit до decide).

Алерты (минимум):
- Очередь > 50 заданий более часа.
- Лок открыт > 20 минут.
- Среднее decision latency > 24 часов за день.

Дашборд (в боте):
- Админ видит общую сводку: средний waittime, процент approved, распределение причин отказа (топ-5), нагрузка по модераторам (кол-во решений в неделю).

---

## Справочник причин отказа

Редактируется admin'ом:

```
/admin → Справочники → Причины отказа
```

CRUD с code (uniq), title (для кнопки), description (для автора), active, sort_order.

Базовый сид:

| code | title | description |
|---|---|---|
| RATING_MISMATCH | Неверный возрастной рейтинг | Контент не соответствует заявленному рейтингу. Повысь рейтинг или убери сцены. |
| PLAGIARISM | Плагиат | Текст частично/полностью скопирован из другого источника. |
| LOW_QUALITY | Низкое качество | Много орфографических/пунктуационных ошибок, текст сложно читать. |
| NO_FANDOM | Не фанфик | Это оригинальное произведение, фанфиков-платформа только для работ по существующим вселенным. |
| INVALID_FORMAT | Проблемы с форматированием | Пустые строки, битые спойлеры, перепутано форматирование. |
| WRONG_TAGS | Неверные теги | Теги не соответствуют содержимому. |
| RULES_VIOLATION | Нарушение правил | См. /rules — укажи пункт в комментарии. |

---

## Управление тегами (merge)

Модератор видит предложенных «кандидатов на merge» (теги, которые отличаются регистром/пробелами/латиница-кириллица). Выбирает canonical и sources. Use case `MergeTags`:

```sql
BEGIN;
UPDATE fanfic_tags SET tag_id = :canonical WHERE tag_id IN (:sources);
UPDATE tags SET merged_into_id = :canonical WHERE id IN (:sources);
UPDATE tags SET usage_count = usage_count + (
  SELECT COALESCE(SUM(usage_count), 0) FROM tags WHERE id IN (:sources)
) WHERE id = :canonical;
UPDATE tags SET usage_count = 0 WHERE id IN (:sources);
COMMIT;
```

Поиск по merged-тегу автоматически редиректит на canonical (проверяется в `application/search` до вызова Meili).

---

## Управление пользователями

Admin интерфейс в боте:

- `/admin user <tg_id|@nick|author_nick>` — карточка пользователя: роль, регистрация, last_seen, кол-во фиков, last_actions.
- Кнопки: `[Изменить роль]` (выбор user/moderator/admin), `[Бан]` (с причиной), `[Разбан]`, `[Удалить все черновики]`.
- Бан: ставит `banned_at`, `banned_reason`. Middleware на каждом апдейте первым делом проверяет `banned_at` — если не null, отвечает «Доступ ограничен» и блокирует дальнейшие хендлеры.

---

## Аудит

Каждое админ/moderator-действие пишется в `audit_log`:

```python
async def log(actor_id, action, target_type, target_id, payload):
    await session.execute(insert(AuditLog).values(
        actor_id=actor_id, action=action,
        target_type=target_type, target_id=target_id,
        payload=payload,
    ))
```

Действия:
- `fic.approve`, `fic.reject`, `fic.archive`
- `chapter.approve`, `chapter.reject`
- `broadcast.create`, `broadcast.schedule`, `broadcast.launch`, `broadcast.cancel`
- `user.role_change`, `user.ban`, `user.unban`
- `tag.merge`, `tag.create`
- `reason.create`, `reason.update`, `reason.deactivate`
- `fandom.create`, `fandom.update`

Админ может посмотреть свой журнал и журнал конкретного модератора через `/admin audit --actor=<id>`.

---

## Защита от злоупотреблений

- **Автор не может видеть, какой модератор отклонил** (показываем только роль «модератор», не имя) — защита от давления.
- **Модератор не может менять своё же решение** после `decided_at` — только админ через `fic.undo_decision` (новая запись в queue).
- **Модератор не может модерить собственные работы** — проверка в pick_next: `WHERE submitted_by != :mod_id`.
- **Лимит «rejected» на одного автора**: если > 5 отклонений за неделю — автотриггер уведомления админу (не автобан, решение за человеком).

---

## Команды для админа/модератора (bot commands)

| Команда | Роль | Что делает |
|---|---|---|
| `/mod` | moderator | Открыть очередь модерации |
| `/mod_stats` | moderator | Своя статистика за неделю |
| `/admin` | admin | Админ-меню |
| `/broadcast` | admin | Быстрый старт создания рассылки |
| `/user <query>` | admin | Карточка пользователя |
| `/fic <id>` | admin | Карточка фика с действиями |
| `/audit <?actor>` | admin | Последние 50 записей аудита |

Регистрируются через `setMyCommands` с `scope=chat_administrators`/`chat_member` для разделения видимости (modeator видит `/mod`, admin — `/admin`).
