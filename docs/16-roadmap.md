# 16 · Дорожная карта

Итеративная поставка от skeleton до production-ready. Оценки — в календарных неделях при full-time работе одного разработчика. Этапы можно частично параллелить (напр., этап 3 и 4).

## Этап 0. Подготовка (2–3 дня)

- [ ] `pyproject.toml` с зависимостями, `uv.lock`.
- [ ] Linters/формат (`ruff`, `mypy` strict), `pre-commit`, `import-linter`.
- [ ] `alembic.ini` + первая пустая ревизия.
- [ ] `docker/`, `docker-compose.yml`, `docker-compose.dev.yml`, `Makefile`.
- [ ] `.env.example`, `.dockerignore`, `.gitignore`.
- [ ] Скелет `src/app/` (core/, domain/, application/, infrastructure/, presentation/).
- [ ] `structlog` + `/healthz`.
- [ ] CI пайплайн (lint + test).
- [ ] README с командами `make up / test / migrate`.

**Deliverable**: `make up` поднимает PG/Redis/Meili/bot/worker/scheduler, бот отвечает на `/start` «Hello, Fantik».

---

## Этап 1. Skeleton + users + tracking (1–2 недели)

- [ ] Миграция 0001: ENUMы, `users`, `tracking_codes`, `tracking_events` (partitioned), `fandoms`, `age_ratings`, `tags` + сиды.
- [ ] DI-контейнер (dishka) + фабрика бота.
- [ ] Middleware: logging, user_upsert, ban_check, role, throttle, metrics.
- [ ] Роутеры: `start.py` (с UTM), `onboarding.py` (правила + подтверждение), `profile.py` (задать `author_nick`).
- [ ] Use cases: `RegisterUserUseCase`, `SetAuthorNickUseCase`, `RecordEventUseCase`.
- [ ] Main menu с inline-кнопками (заглушки для каталога/моих/автор/админ).
- [ ] `/admin` доступен только юзерам из `ADMIN_TG_IDS` (seed при первом запуске).
- [ ] Tests: unit + integration для users/tracking.

**Deliverable**: юзер регистрируется, может задать ник, `/start <code>` пишет события; админ видит пустое админ-меню.

---

## Этап 2. Авторство + модерация (2 недели)

- [ ] Миграции 0002–0003: `fanfics`, `fanfic_tags`, `fanfic_versions`, `chapters`, `chapter_pages`, `moderation_queue`, `moderation_reasons` + сиды причин.
- [ ] Domain: `Fanfic`, `Chapter`, `ModerationCase`; сервисы `EntityValidator`, `TagNormalizer`.
- [ ] FSM `CreateFanfic`, `AddChapter`, `EditFanfic`, `ReviseAfterRejection`.
- [ ] Use cases: `CreateDraft`, `AddChapter`, `UpdateChapter`, `SubmitForReview`, `CancelSubmission`, `Approve`, `Reject`, `PickNext`.
- [ ] Роутеры: `author_create.py`, `author_manage.py`, `moderation.py`.
- [ ] Админ-роутеры: `admin_fandoms.py`, `admin_tags.py` (merge), `admin_reasons.py`.
- [ ] Уведомления автору через `notifications` + inline-воркер.
- [ ] Аудит всех решений в `audit_log`.
- [ ] Tests: unit (валидатор, entity checks), integration (pick_next с SKIP LOCKED), E2E (подача и отказ).

**Deliverable**: автор создаёт фик + главы с форматированием, отправляет на модерацию, модератор одобряет/отклоняет с причинами, автор получает уведомление.

---

## Этап 3. Чтение (2 недели)

- [ ] `ChapterPaginator` (UTF-16 + entity split) с property-тестами.
- [ ] TaskIQ `repaginate_chapter`.
- [ ] Use cases: `OpenFanfic`, `PaginateChapter`, `ReadPage`, `SaveProgress`, `ToggleLike`, `ToggleBookmark`.
- [ ] Роутер `reader.py`: обложка, первая страница, навигация ◀▶, главы.
- [ ] Redis-кэш страниц, прогресс с throttle.
- [ ] Миграция `bookmarks`, `likes`, `reads_completed`, `reading_progress`.
- [ ] «Моя полка»: недавнее чтение, закладки, лайки.
- [ ] Tests: e2e-чтение, нагрузочные пагинатора.

**Deliverable**: читатель открывает любой approved фик, листает, кэш работает, прогресс сохраняется.

---

## Этап 4. Поиск и каталог (1–2 недели)

- [ ] Meilisearch adapter + settings_bootstrap (создать индекс при старте).
- [ ] TaskIQ `index_fanfic`, `delete_from_index`, `full_reindex`.
- [ ] Use cases: `Search`, `Suggest`.
- [ ] Роутер `browse.py`: меню фильтров (мультиселект), ленты «новое»/«топ»/«по фандому».
- [ ] Inline-режим `@bot <query>` через `/inline/search.py`.
- [ ] Fallback PG FTS при Meili-down.
- [ ] Tests: integration (Meili), проверка фасетов.

**Deliverable**: полноценный поиск с фильтрами и инлайн.

---

## Этап 5. Социалка (1 неделя)

- [ ] Миграция `subscriptions`, `reports`.
- [ ] Use cases: `Subscribe`, `Unsubscribe`, `NotifySubscribers`, `CreateReport`, `HandleReport`.
- [ ] Роутер `reports.py` (жалобы от читателей + обработка модераторами).
- [ ] Кнопка «Подписаться на автора» на карточке фика.
- [ ] Fanout-задача уведомлений о новой главе/работе (через worker).
- [ ] Tests.

**Deliverable**: подписки, уведомления, жалобы.

---

## Этап 6. Админские инструменты (2 недели)

- [ ] Миграции `broadcasts`, `broadcast_deliveries` (partitioned), `outbox`, `audit_log` (partitioned).
- [ ] Token-bucket Lua script в Redis.
- [ ] TaskIQ `run_broadcast`, `deliver_one`; scheduler для отложенных.
- [ ] FSM `BroadcastFlow` + роутер `admin_broadcast.py`.
- [ ] Wizard клавиатуры.
- [ ] Сегментер.
- [ ] Admin stats: запросы по `mv_*` + рендер PNG (matplotlib).
- [ ] Роутер `admin_stats.py`, `admin_tracking.py`.
- [ ] Tests: integration (testcontainers) + e2e рассылок.

**Deliverable**: админ создаёт трекинг-коды, видит воронки, делает богатые рассылки с сохранением форматирования.

---

## Этап 7. Hardening ✅

- [x] Полное покрытие метриками (Prometheus) — `src/app/core/metrics.py`, wiring в middleware/TG-session/TaskIQ/broadcast/moderation/search; периодический `metrics_refresh_tick` для Gauge'ей.
- [x] Sentry подключён во всех процессах — `src/app/core/sentry.py` + `init_sentry(component=…)` в bot/worker/worker-broadcast/scheduler, PII-scrubbing через `before_send`.
- [x] Alertmanager + Telegram-нотификации — `docker/prometheus/alerts.yml` (7 правил), `docker/alertmanager/alertmanager.yml.example` (Telegram receiver).
- [x] Нагрузочные тесты — `tests/load/` + `fake_tg_server.py` + locust-сценарии `load_start` / `load_reading` / `load_broadcast` + compose-profile `loadtest`.
- [x] Security-проход — `bandit` + `pip-audit` в CI lint job, `.github/dependabot.yml` weekly, `cover_validator.py` (magic bytes + 5 МБ), `DeleteUserUseCase` (`/delete_me`).
- [x] Recovery drill — `scripts/backup_pg.sh` + `scripts/restore_drill.sh` + `docs/ops/backup.md`.
- [x] Документация для операционки — `docs/ops/runbook.md` (per-alert actions, эскалация), `scripts/smoke.sh` + CI-job `smoke`.
- [ ] Feature flags — не реализовано, вынесено в пост-MVP (не блокирует production-readiness).

**Deliverable**: прод-готовый сервис.

---

## MVP-минимум (если нужно быстрее)

Если критично сжать сроки для первого запуска:

- Этап 0 + 1 + 2 + 3 + поиск без инлайн-режима (без `@bot`) + упрощённая админка (без рассылок).
- Срок: 5–6 недель.
- Отсутствующие фичи: рассылки (можно пока вручную через «Подписки»), статистика (только простой `/admin users_count`), подписки (заменяются проверкой новых работ).

Это позволит запустить beta раньше и собрать обратную связь, а рассылки/стата доделать после.

---

## Пост-MVP (будущее)

| Фича | Сложность | Описание |
|---|---|---|
| Mini App админка | Средняя | React/Svelte + FastAPI, всё через те же use case |
| Telegram Payments / Stars | Средняя | Подписка авторов за разное, донаты |
| Semantic search | Высокая | pgvector или Qdrant, эмбеддинги, гибридный retrieve |
| Комментарии к фикам | Высокая | Новые таблицы, moderation flow, fanout |
| Collaborative authors | Высокая | Многоавторские работы |
| Экспорт fb2/epub | Средняя | Генерация из chapters + entities |
| Импорт из Фикбука | Средняя | Парсер + маппинг в модель |
| Автомодерация (NLP) | Высокая | Фильтр очевидного спама/нсфв без метки |
| Push в каналы | Низкая | При новых топ-фиках — пост в канал |
| Чтение голосом (TTS) | Высокая | Генерация аудио-главы, кэш в object storage |

## Риски и их митигация

| Риск | Митигация |
|---|---|
| Telegram меняет Bot API | aiogram 3 обновляется; следим за changelog; CI на smoke-тестах |
| Рост объёма сверх ожиданий | Архитектура готова к масштабированию — см. [`11-scalability-performance.md`](11-scalability-performance.md) |
| Утечка `BOT_TOKEN` | Секреты в env, ротация, audit log |
| Недоступность Meilisearch | Fallback PG FTS, алерты, reindex из PG (source of truth) |
| Спам и злоупотребления | Throttle, лимиты, модерация |
| Юридические вопросы с фанфиками (авторские права) | Правила + модерация; disclaimer в онбординге; процесс takedown через жалобы |
| Потеря данных | Ежедневный `pg_dump`, recovery drill раз в месяц |

## Точки контроля с пользователем

После каждого этапа:

1. Демо ключевых фич (скринкаст в боте).
2. Проход checklist этапа.
3. Уточнение приоритетов следующего этапа (возможна переориентация на MVP-минимум, если нужно запускаться раньше).
