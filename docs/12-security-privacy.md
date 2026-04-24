# 12 · Безопасность и приватность

## Секреты

- `BOT_TOKEN`, `POSTGRES_DSN`, `REDIS_URL`, `MEILI_MASTER_KEY`, `SENTRY_DSN` — только через ENV.
- `.env` в `.gitignore`; `.env.example` в репо с «безопасными» значениями-плейсхолдерами.
- Production secrets — в secrets manager VPS-провайдера или Docker swarm secrets / k8s secret.
- Ротация `BOT_TOKEN`: выпускается новый у BotFather, меняется в env, перезапускается bot и все воркеры (таск `copy_message` требует того же токена, что и шаблон).

## RBAC

Middleware `role`:

```python
class RoleMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = event.from_user.id
        cached = await redis.get(f"user_role:{uid}")
        if cached is None:
            role = await users_repo.get_role(uid) or "user"
            await redis.setex(f"user_role:{uid}", 60, role)
        else:
            role = cached.decode()
        data["role"] = role
        return await handler(event, data)
```

Фильтры:

```python
class IsModerator(Filter):
    async def __call__(self, event, role: str = "user") -> bool:
        return role in ("moderator", "admin")

class IsAdmin(Filter):
    async def __call__(self, event, role: str = "user") -> bool:
        return role == "admin"
```

Применение: `router.message(IsModerator())` или в роутерах админки общий фильтр на весь Router.

Инвалидация: use case `ChangeRole` делает `redis.delete(f"user_role:{uid}")`.

## Бан-чек

Middleware `banned`:

```python
class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = event.from_user.id
        cached = await redis.get(f"user_banned:{uid}")
        if cached is None:
            banned_at, reason = await users_repo.get_ban(uid)
            if banned_at:
                await redis.setex(f"user_banned:{uid}", 60, f"1|{reason}")
                await event.answer(f"Доступ ограничен. Причина: {reason}")
                return  # отменяем дальнейшую обработку
            else:
                await redis.setex(f"user_banned:{uid}", 60, "0|")
        else:
            val = cached.decode()
            if val.startswith("1|"):
                await event.answer(f"Доступ ограничен. Причина: {val[2:]}")
                return
        return await handler(event, data)
```

Порядок middleware: `LoggingMiddleware` → `UserUpsertMiddleware` → `BanCheckMiddleware` → `ThrottleMiddleware` → `RoleMiddleware` → `MetricsMiddleware` → handler.

## Валидация пользовательского ввода

### Entities

При сохранении главы/фика `entity_validator.validate(text, entities)`:

1. Все `offset + length ≤ utf16_length(text)`.
2. Запрещённые URL-схемы:
   - `javascript:`, `data:`, `file:`, `about:` — отказ.
   - Разрешены `https://`, `http://` (с warning, если не https), `tg://`.
3. `text_mention` — опционально разрешены, но в MVP **запрещены** (сложно контролировать); только `mention` для `@username`.
4. `custom_emoji` — только корректно обрамлённые (`length == utf16_length(placeholder_emoji)`). Placeholder должен быть ровно одним emoji.
5. Суммарное количество entities ≤ 1000 на главу (страхует от спама).

### Лимиты контента

- Title фика: 1–128 символов.
- Summary: 1–2000 символов.
- Chapter title: 1–128.
- Chapter text: 1–100 000 UTF-16 units.
- Количество глав на фик: до 200.
- Количество тегов на фик: до 30 (5 persona + 5 warning + 20 freeform/theme).
- Обложка: только фото (JPEG/PNG), ≤ 5 МБ. Реализовано в [`src/app/infrastructure/telegram/cover_validator.py`](../src/app/infrastructure/telegram/cover_validator.py): загружаем первые байты из Telegram через `bot.download`, проверяем magic bytes (`\xFF\xD8\xFF` для JPEG, `\x89PNG\r\n\x1a\n` для PNG) и размер. Вызывается из FSM обложек в [`author_create.py`](../src/app/presentation/bot/routers/author_create.py) и [`author_manage.py`](../src/app/presentation/bot/routers/author_manage.py) перед сохранением `cover_file_id`.

### Нормализация тегов

- Trim, collapse spaces, lowercase slug, max 32 символа.
- Запрещённые паттерны: URL-like, тг-ссылки, `@username`-чистые.
- Defamation-слова — минимальный блэклист в конфиге; при попадании — тег отмечается как «требует модерации».

## Антиспам

- Лимит создания фиков: **3 новых работы в сутки** на юзера.
- Лимит отправок на модерацию: **10 за час** (защита от флуда очереди).
- Лимит глав за раз (добавления): **20 в сутки**.
- Лимит жалоб: **20 в сутки**.
- Лимит сообщений в бот (любых): **30/мин** (throttle) + **500/сутки** (Redis-счётчик).

Счётчики в Redis через `INCR` + `EXPIRE`.

## PII и хранение данных

- Храним: `tg_id`, `username`, `first_name`, `last_name`, `language_code`, `timezone`, `author_nick`.
- **Не храним**: телефон, реальное имя, email (Telegram их и не отдаёт без отдельных запросов).
- Логи: без текста сообщений, без `first_name`/`last_name` (только `user_id` и `update_id`).
- Audit log: с `user_id` для целей безопасности и разрешения споров.

## Право на удаление

Команда `/delete_me` реализована в [`src/app/application/users/delete_user.py`](../src/app/application/users/delete_user.py) + [`src/app/presentation/bot/routers/profile.py`](../src/app/presentation/bot/routers/profile.py) (FSM `DeleteMeFlow`).

1. Показывает предупреждение: что будет удалено, что — анонимизировано.
2. Подтверждение.
3. `DeleteUserUseCase` (одна транзакция):
   - `author_nick` → `deleted_<sha256(tg_id)[:8]>`.
   - `username`, `first_name`, `last_name` → NULL.
   - `utm_source_code_id` → NULL.
   - Все работы со статусом IN (`draft`, `rejected`, `revising`) — DELETE (каскадно на chapters/pages/versions).
   - Опубликованные работы — НЕ удаляются. В каталоге/reader/inline-search подпись автора подменяется на `«Удалённый пользователь»` через [`src/app/presentation/bot/display.py`](../src/app/presentation/bot/display.py) (`display_author_nick`).
   - `bookmarks`, `likes`, `reading_progress`, `reads_completed`, `subscriptions` (обе стороны), `reports`, `notifications` — DELETE.
   - `tracking_events.user_id` → NULL (события остаются для статистики).
   - `audit_log` — сохраняется + запись `action='user.self_deleted'`.
4. `banned_at = now()`, `banned_reason = "self_deleted"` — предохраняет от повторной регистрации под тем же `tg_id`.

Повторный вызов use-case идемпотентен: на уже помеченном `banned_reason='self_deleted'` — no-op.

## Ban и восстановление

- Бан: `banned_at = now()`, `banned_reason` заполняется, middleware ловит.
- Разбан: `banned_at = NULL`, `banned_reason = NULL`.
- Авто-бан: не делаем — только ручной через админа.

## Защита от утечек через Telegram

- `text_mention` — не разрешаем (может раскрыть чужих tg_id).
- Ответы пользователю с данными другого пользователя: только `author_nick`, не `tg_id`/`username`.
- Deep-links: не генерируем токенов с секретами в payload — это публично.

## Защита от повторов (replay)

- Callback data содержит `fic_id`/`chapter_id`/`page_no` — ничего секретного.
- На действии, меняющем состояние (like, bookmark, report): идемпотентность на уровне БД (UNIQUE constraint → ON CONFLICT DO NOTHING для like/bookmark).

## Защита от race conditions

- Модерация: `FOR UPDATE SKIP LOCKED` (см. [`06-admin-and-moderation.md`](06-admin-and-moderation.md)).
- Автор: `fanfics.get_for_update(fic_id)` в use case, чтобы две одновременных правки не разъехались.
- Счётчики лайков: атомарный `UPDATE ... SET count = count + 1`.
- Delivery рассылки: `PRIMARY KEY (broadcast_id, user_id)` + `ON CONFLICT DO NOTHING` — один пользователь не получит дубль.

## Защита webhook-endpoint

Если включен webhook-режим:

- URL не содержит токена прямо; вместо него — `sha256(token)` как сегмент пути: `/webhook/<sha256>`.
- Проверка заголовка `X-Telegram-Bot-Api-Secret-Token` (совпадает с установленным при `setWebhook`).
- Nginx ограничивает body до 1 МБ, таймаут 30 сек.

## HTTPS / TLS

- Webhook требует HTTPS от Telegram (Let's Encrypt через `certbot` или `acme.sh`).
- Внутренний HTTP между контейнерами в Compose — plain (не наружу).

## Лог-санитизация

- `structlog` процессор, который рубит поля `text`, `message`, `first_name`, `last_name` в логах (либо хэширует через SHA-256 с солью).
- Исключение — уровень DEBUG в dev, но в prod `LOG_LEVEL=INFO`.

## Sensitive в Sentry

- `Sentry.init(send_default_pii=False)`.
- `before_send` hook убирает поля пользователя (кроме `user_id`).

## Уязвимости по шкале OWASP

| Риск | Mitigation |
|---|---|
| SQL Injection | SQLAlchemy с параметрами, ORM; нет raw conв с f-string'ами (кроме одного контроллируемого `segment_to_sql`) |
| XSS | Неактуально (нет HTML-UI). В текстах — показ через `entities` без parse_mode |
| SSRF | Нет fetch по URL от пользователя (QuickChart если используем — только исходящие на whitelisted домен) |
| Denial of Service | Throttle per-user, лимиты на объём контента, graceful rate-limit error |
| Broken Auth | Telegram берёт на себя auth; наш RBAC опирается на TG user_id |
| Sensitive Data Exposure | см. PII выше |
| Server-Side Request Forgery | Прямых внешних запросов от юзера нет |
| CSRF | Неактуально (нет браузерных сессий) |
| Dependency vulnerabilities | `uv pip audit` / `dependabot` / `trivy` в CI |
| Logging injection | structlog → JSON → безопасно |

## Аудит

Каждое security-значимое действие — в `audit_log`:

- изменение ролей
- бан/разбан
- удаление пользователя
- отказы модерации (связь с жалобами)
- массовые действия (merge tags, broadcast launch)

Аудит не очищается автоматически; архивация после 2 лет — `detach partition → s3 → drop partition` (по необходимости).

## Обновления

- Все зависимости закреплены в `uv.lock`.
- Еженедельный автоматический PR с обновлениями (Renovate/Dependabot).
- Критические CVE в используемых библиотеках — алерт в Slack/Telegram (через GH Security Advisories).

## Backup

- PG: `pg_dump` ежедневно, хранение 30 дней. Хранилище — отдельное VPS / S3-совместимое.
- Meilisearch: dump раз в 2 дня (если нужно; PG всё равно source of truth).
- Redis: RDB snapshot каждые 15 минут; считается как cache, потеря некритична.
- Восстановление: проверяется ежемесячно (recovery drill) — restore в staging, прогон smoke-тестов.
