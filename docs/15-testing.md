# 15 · Тестирование

## Пирамида

```
       ┌───────┐
       │  E2E  │        ~5%     полный прогон через fake bot
       ├───────┤
       │  Int  │        ~25%    use case + реальные PG/Redis/Meili (testcontainers)
       ├───────┤
       │ Unit  │        ~70%    domain + application (чистые, быстрые)
       └───────┘
```

## Unit-тесты

### Что

- Все сервисы в `domain/` (`ChapterPaginator`, `EntityValidator`, `TagNormalizer`, `SegmentResolver`).
- Use case'ы с мок-репозиториями.
- Утилиты в `infrastructure/telegram/entity_utils.py` (UTF-16 math).

### Инструменты

- `pytest`, `pytest-asyncio`, `hypothesis` (property-based для пагинатора).

### Пример

```python
# tests/unit/domain/fanfics/test_paginator.py
def test_paginator_respects_utf16_limit():
    text = "а" * 5000   # 5000 UTF-16 units
    entities = []
    pages = paginate(text, entities, max_units=3900)
    assert len(pages) == 2
    for p in pages:
        assert utf16_length(p.text) <= 3900
```

### Property-based пример

```python
from hypothesis import given, strategies as st

@given(
    text=st.text(min_size=1, max_size=20000),
    seed_entities=st.lists(st.integers(min_value=0, max_value=10), min_size=0, max_size=50),
)
def test_pagination_invariants(text, seed_entities):
    entities = random_valid_entities(text, seed_entities)
    pages = paginate(text, entities, max_units=3900)
    # Все страницы в лимите
    for p in pages:
        assert utf16_length(p.text) <= 3900
    # Склейка == оригинал
    joined = "".join(p.text for p in pages)
    assert joined == text  # допускаем нормализацию пробелов на границах, если определена
```

## Integration-тесты

### Что

- Репозитории (реальный PG).
- Use case'ы от DTO до commit (проверка SQL, транзакций, событий).
- Meilisearch-индексатор.
- TaskIQ-задачи в in-memory брокере.

### Инструменты

- `testcontainers[postgres,redis,meilisearch]`.
- `pytest_asyncio` фикстуры сессии.
- `alembic upgrade head` перед тестами в свежую БД.

### Конфиг фикстур

```python
# tests/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from testcontainers.meilisearch import MeilisearchContainer

@pytest.fixture(scope="session")
def pg():
    with PostgresContainer("postgres:16-alpine") as c:
        yield c.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")

@pytest.fixture(scope="session")
def redis():
    with RedisContainer("redis:7-alpine") as c:
        yield f"redis://{c.get_container_host_ip()}:{c.get_exposed_port(6379)}"

@pytest.fixture(scope="session")
def meili():
    with MeilisearchContainer("getmeili/meilisearch:v1.8", master_key="testkey") as c:
        yield c.get_url(), "testkey"

@pytest.fixture(scope="session", autouse=True)
async def migrations(pg):
    os.environ["POSTGRES_DSN"] = pg
    from alembic import command
    from alembic.config import Config
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", pg)
    command.upgrade(cfg, "head")

@pytest.fixture
async def session(pg):
    engine = create_async_engine(pg)
    async with AsyncSession(engine) as s:
        yield s
        await s.rollback()
```

### Пример

```python
# tests/integration/fanfics/test_submit_for_review.py
async def test_submit_for_review_moves_status_and_enqueues(session):
    user = await make_user(session, author_nick="bob")
    fic = await make_draft(session, author=user, chapters_count=2)
    repo = SAFanficRepository(session)
    mod = SAModerationRepository(session)
    uc = SubmitForReviewUseCase(uow=FakeUoW(session), fics=repo, mod=mod)

    result = await uc(SubmitForReviewCommand(fic_id=fic.id, author_id=user.id))

    updated = await repo.get(fic.id)
    assert updated.status == "pending"
    queue_item = await mod.get(result.queue_id)
    assert queue_item.kind == "fic_first_publish"
```

## E2E-тесты

### Что

Сценарии бота целиком: отправляем фейковый `Update`, ждём ответа, проверяем, что вызвались нужные Bot API методы.

### Инструменты

- `aiogram-tests` (community) или свой простой mock:
  - `FakeBot` — имитирует `sendMessage`, `copyMessage`, `editMessageText` через асинхронные методы, записывает вызовы.
  - Dispatcher работает реально; передаём `FakeBot` в контекст.
- PG/Redis/Meili — также через testcontainers.

### Пример

```python
# tests/e2e/test_start_flow.py
async def test_start_with_utm_creates_event(dispatcher, fake_bot, session, redis):
    update = make_text_update("/start abc12345", user_id=777)
    await dispatcher.feed_update(fake_bot, update)

    # проверки
    user = await session.scalar(select(User).where(User.id == 777))
    assert user is not None

    evt = await session.execute(
        select(TrackingEvent).where(TrackingEvent.user_id == 777)
    )
    assert len(evt.all()) >= 1

    # что отправил бот
    sent = fake_bot.captured("send_message")
    assert any("Добро пожаловать" in c["text"] for c in sent)
```

## Сценарии чтения

Отдельный набор E2E-тестов на читалку:

- Открыть фик → принять обложку → нажать «Читать» → получить первую страницу.
- Листание вперёд/назад.
- «Глава назад», «Глава вперёд».
- Закладка, лайк.
- Жалоба.
- Последняя страница → кнопка «Дочитано».

## Сценарии модерации

- Автор отправляет → модератор видит в очереди → принимает → автор получает уведомление → фик в индексе.
- Автор отправляет → модератор отклоняет с причиной → автор получает причины + кнопку «Доработать» → правит → снова отправляет → одобряется.

## Тесты рассылок

Сценарии:

- Шаблон с текстом + entities → `copy_message` вызван для каждого получателя с правильными параметрами.
- Шаблон с фото → аналогично.
- Клавиатура добавлена → `reply_markup` соответствует.
- Сегмент «активные за 7 дней» → получают только они.
- Error `403 blocked` → delivery со статусом `blocked`, retry не делается.
- Error `429 retry_after=5` → повтор, delivery eventually `sent`.

## Тесты поиска

- Индексация фика после approve → ищется по title, author_nick, tags.
- Фильтр по фандому.
- Multi-tag AND.
- Fallback на PG FTS при Meili down.

## Нагрузочное

`tests/load/` — Locust-сценарии:

```python
# tests/load/locustfile.py
from locust import task, FastHttpUser, constant

class ReaderUser(FastHttpUser):
    wait_time = constant(2)

    @task(5)
    def read_page(self):
        # эмулируем callback_query через webhook /bot{TOKEN}
        ...

    @task(1)
    def open_fic(self):
        ...
```

Запуск локально: `uv run locust -f tests/load/locustfile.py --headless -u 500 -r 50 -t 10m`.

Цели:
- p95 `/start`: < 200 мс.
- p95 read_page: < 150 мс.
- Error rate: < 0.5%.
- CPU бота: < 70%.

## Моки Telegram API

- `respx` / `aioresponses` — мокаем HTTP-вызовы aiohttp.
- Используем в unit и integration тестах там, где не нужна полная проверка.
- В E2E — `FakeBot` с записью вызовов.

## Тестовые данные

- `tests/factories/` — `factory_boy`-фабрики для `User`, `Fanfic`, `Chapter`, `TrackingCode`.
- Seed-фикстуры: 3 фандома, 4 возрастных рейтинга, 10 причин отказа — автоматически применяются в тестовой БД через Alembic.

## Покрытие

- Целевое: **80%+ на domain и application**, **60%+ на infrastructure**.
- CI: `pytest --cov=src --cov-fail-under=75`.
- Codecov публикует отчёт на PR.

## Правила написания тестов

- Один test = одно ожидание (`assert`). Если нужно много — вынести в отдельные тесты.
- Говорящие имена: `test_submit_for_review_creates_moderation_queue_item_when_fic_has_chapters`.
- AAA: Arrange, Act, Assert.
- Нет тестов на приватные методы — через публичный API.
- Нет flaky — асинхронные проверки через `wait_for(predicate, timeout=3.0)`.

## Непрерывная надёжность

- **Мутационное тестирование** `mutmut` — раз в неделю в CI (nightly), чтобы убедиться, что тесты ловят изменения.
- **Fuzz-тест на паджинатор** — `hypothesis` runs extended в nightly.

## Как не писать

- Не тестируем SQLAlchemy (он уже протестирован).
- Не тестируем aiogram internals.
- Не дублируем тесты unit + integration на один и тот же сценарий.
- Не делаем «проверочный» тест «if не упало — успех» — явные assert'ы.

## Команды

```bash
# все тесты
uv run pytest

# только unit (быстро, без контейнеров)
uv run pytest tests/unit

# конкретный файл
uv run pytest tests/unit/domain/fanfics/test_paginator.py -v

# с покрытием
uv run pytest --cov=src --cov-report=html
```
