# 08 · Поиск

## Технология

**Meilisearch** — выбран из-за:

- Русская токенизация и стемминг (Charabia) из коробки.
- Typo-tolerance (перенастраиваемый порог).
- Фасеты (`facetDistribution`), фильтры, сортировки — декларативно.
- Sub-50ms latency.
- Простая операционка (один бинарь, volume, master key).

## Индекс `fanfics`

Один основной индекс. В него попадают **только** работы со статусом `approved` (либо `approved + hidden` для NSFW c взрослым gating — в MVP пусть все approved в одном индексе).

### Схема документа

```json
{
  "id": 42,
  "title": "Тень директора",
  "summary": "АУ, в которой Снейп...",
  "author_nick": "mark_the_writer",
  "fandom_id": 1,
  "fandom_name": "Гарри Поттер",
  "fandom_aliases": ["HP", "Потериана"],
  "age_rating": "R",
  "age_rating_order": 4,
  "tags": ["AU", "Ангст", "Хэд-канон"],
  "characters": ["Северус Снейп", "Гарри Поттер"],
  "warnings": ["Смерть персонажа"],
  "chapters_count": 12,
  "chars_count": 85000,
  "likes_count": 124,
  "views_count": 4521,
  "reads_completed_count": 38,
  "first_published_at": 1735689600,
  "updated_at": 1745012345,
  "chapters_text_excerpt": "... первые 3 главы, порезанные до 20k символов для контекста поиска ..."
}
```

### Настройки индекса

```json
{
  "searchableAttributes": [
    "title",
    "author_nick",
    "summary",
    "tags",
    "characters",
    "fandom_name",
    "fandom_aliases",
    "chapters_text_excerpt"
  ],
  "filterableAttributes": [
    "fandom_id",
    "age_rating",
    "age_rating_order",
    "tags",
    "characters",
    "warnings",
    "likes_count",
    "chars_count",
    "chapters_count"
  ],
  "sortableAttributes": [
    "first_published_at",
    "updated_at",
    "likes_count",
    "views_count",
    "reads_completed_count",
    "chars_count"
  ],
  "rankingRules": [
    "words",
    "typo",
    "proximity",
    "attribute",
    "sort",
    "exactness",
    "likes_count:desc"
  ],
  "typoTolerance": {
    "enabled": true,
    "minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 8},
    "disableOnAttributes": ["author_nick"]
  },
  "stopWords": ["и", "в", "на", "не", "что", "как", "the", "a", "of"],
  "synonyms": {
    "хп": ["гарри поттер", "поттер"],
    "марвел": ["marvel"],
    "нс17": ["nc-17", "nc17"]
  },
  "faceting": {"maxValuesPerFacet": 200},
  "pagination": {"maxTotalHits": 5000},
  "searchCutoffMs": 150
}
```

Настройки применяются при старте бота воркером `settings_bootstrap` — идемпотентно, сравнивает текущие и применяет diff.

### Почему `fandom_aliases` в searchable
Пользователь пишет «HP» — мы должны найти «Гарри Поттер». Synonyms решают популярные кейсы; aliases в документе — всё остальное.

### `chapters_text_excerpt`
Брать не весь текст всех глав — индекс вырастет непропорционально, а смысла поиска по телу главы среди фанфиков обычно нет. Склейка: `join(chapter.text[:5000] for first 3 chapters)`, обрезанная до 20 000 символов. Это позволит искать по цитатам первых глав.

## API поиска

```python
# application/search/search.py
@dataclass
class SearchQuery:
    q: str = ""
    fandoms: list[int] = field(default_factory=list)
    age_ratings: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    sort: Literal["relevance", "newest", "updated", "top", "longest"] = "relevance"
    limit: int = 10
    offset: int = 0

@dataclass
class SearchResult:
    hits: list[FanficCard]
    total: int
    facets: dict[str, dict[str, int]]

class SearchUseCase:
    async def __call__(self, q: SearchQuery) -> SearchResult:
        meili_query = {
            "q": q.q,
            "limit": q.limit,
            "offset": q.offset,
            "filter": self._build_filter(q),
            "sort": self._build_sort(q),
            "facets": ["fandom_name", "age_rating", "tags"],
        }
        resp = await self._meili.index("fanfics").search(**meili_query)
        return SearchResult(...)
```

### Построение фильтра

```python
def _build_filter(q: SearchQuery) -> list:
    clauses = []
    if q.fandoms:
        clauses.append(f"fandom_id IN [{','.join(map(str, q.fandoms))}]")
    if q.age_ratings:
        clauses.append(f"age_rating IN [{','.join(repr(r) for r in q.age_ratings)}]")
    if q.tags:
        # AND по всем выбранным тегам
        clauses.extend([f"tags = {tag!r}" for tag in q.tags])
    return clauses
```

### Сортировки

- `relevance` — без sort-override, работает `rankingRules`.
- `newest` — `["first_published_at:desc"]`.
- `updated` — `["updated_at:desc"]`.
- `top` — `["likes_count:desc"]`.
- `longest` — `["chars_count:desc"]`.

## Синхронизация индекса

### Событийная модель

Доменные события → TaskIQ-задача:

| Event | Action |
|---|---|
| `FanficApproved` | `index_fanfic(fic_id)` |
| `FanficEditApproved` | `index_fanfic(fic_id)` |
| `FanficArchived` | `delete_from_index(fic_id)` |
| `ChapterApproved` | `index_fanfic(fic_id)` (пересбор excerpt) |
| `LikeToggled` | `index_fanfic(fic_id)` (debounced: не чаще раза в минуту на один fic_id через Redis-lock) |
| `TagsMerged` | batch `reindex_fanfics_with_tag(source_tag_id)` |
| `FandomUpdated` | batch `reindex_fanfics_of_fandom(fandom_id)` |

### Задача `index_fanfic`

```python
@broker.task
async def index_fanfic(fic_id: int) -> None:
    async with uow:
        fic = await fanfics.get_with_relations(fic_id)
        if fic is None or fic.status != "approved":
            await meili.index("fanfics").delete_document(fic_id)
            return
        doc = {
            "id": fic.id,
            "title": fic.title,
            "summary": fic.summary,
            "author_nick": fic.author.author_nick,
            "fandom_id": fic.fandom_id,
            "fandom_name": fic.fandom.name,
            "fandom_aliases": fic.fandom.aliases,
            "age_rating": fic.age_rating.code,
            "age_rating_order": fic.age_rating.sort_order,
            "tags": [t.name for t in fic.tags if t.kind == "freeform" or t.kind == "theme"],
            "characters": [t.name for t in fic.tags if t.kind == "character"],
            "warnings": [t.name for t in fic.tags if t.kind == "warning"],
            "chapters_count": fic.chapters_count,
            "chars_count": fic.chars_count,
            "likes_count": fic.likes_count,
            "views_count": fic.views_count,
            "reads_completed_count": fic.reads_completed_count,
            "first_published_at": int(fic.first_published_at.timestamp()),
            "updated_at": int(fic.updated_at.timestamp()),
            "chapters_text_excerpt": build_excerpt(fic.chapters),
        }
        await meili.index("fanfics").add_documents([doc], primary_key="id")
```

### Батчинг

При массовом переиндексе (merge тегов, смена имени фандома) — собираем в пачки по 1000 документов, `add_documents` — Meili обрабатывает задачи атомарно.

### Debounce лайков

`LikeToggled` может происходить часто. В Redis ключ `debounce:index:fic:{id}` с TTL 60 сек. Если ключ есть — задача не планируется; при первом лайке за минуту — планируем и ставим ключ.

## Инлайн-поиск (`@bot <query>`)

```python
@router.inline_query()
@inject
async def inline_search(iq: InlineQuery, uc: SearchUseCase, cache: ICache):
    query = iq.query.strip()
    if not query:
        results = await _popular_fic_cards()  # топ-10 из кэша
    else:
        ck = f"inline:{normalize(query)}"
        cached = await cache.get(ck)
        if cached is None:
            r = await uc(SearchQuery(q=query, limit=20))
            cached = [_to_inline_result(h) for h in r.hits]
            await cache.setex(ck, 60, cached)
        results = cached
    await iq.answer(results, cache_time=60, is_personal=False)
```

`_to_inline_result`:
- `InlineQueryResultArticle` с `thumb_url` (обложка, если `cover_file_id` кэширован в Telegraph/CDN — иначе без) или без.
- `input_message_content` — `InputTextMessageContent` с карточкой фика + кнопка `[Читать]` через `reply_markup=InlineKeyboardMarkup(...)` deep-link `t.me/<bot>?start=fic_<id>`.

## PostgreSQL FTS (fallback)

Когда Meili недоступен (`HEALTHCHECK` не проходит — circuit breaker открыт) — переключаемся на PG:

```sql
SELECT f.id, ts_rank(ch.tsv_text, query) + ts_rank(f.title || ' ' || f.summary, query) AS rank
FROM fanfics f
JOIN chapters ch ON ch.fic_id = f.id
, plainto_tsquery('russian', :q) query
WHERE f.status = 'approved'
  AND (ch.tsv_text @@ query OR to_tsvector('russian', f.title || ' ' || f.summary) @@ query)
ORDER BY rank DESC
LIMIT :limit OFFSET :offset;
```

Fallback:
- Только базовый поиск, без фасетов (фасеты — отдельными запросами по нормализованным таблицам, если нужно).
- Нечёткость — `pg_trgm` на `fanfics.title`.
- Режим деградации: показать пользователю баннер «Поиск временно работает в упрощённом режиме» — опционально.

Health-check Meili `/health` каждые 5 сек в фоне; при 3 подряд fail → circuit open на 60 сек.

## Автодополнение (suggest)

При наборе фильтров — автодополнение тегов, фандомов, персонажей. Источник — таблица `tags` (usage_count DESC LIMIT 10 WHERE name ILIKE '%prefix%') + `fandoms` (aliases).

```sql
SELECT name FROM tags
WHERE kind = :kind
  AND merged_into_id IS NULL
  AND (slug ILIKE :p OR name ILIKE :p)
ORDER BY usage_count DESC
LIMIT 10;
```

Кэшируется в Redis на 5 минут по ключу `suggest:{kind}:{prefix}`.

## Пагинация каталогов (без поиска)

Для чистого браузинга «новое»/«топ»/«по фандому X» используем PG-запросы через партиальные индексы:

```sql
-- top за всё время
SELECT id, title, author_nick, likes_count
FROM fanfics
WHERE status='approved'
ORDER BY likes_count DESC, id DESC
LIMIT :lim OFFSET :off;
```

Для стабильной пагинации при append'ах — курсор через `(likes_count, id)`:

```sql
WHERE (likes_count, id) < (:last_likes, :last_id)
```

## Обновление схемы индекса

Меняются `filterableAttributes` — вся перестройка. Меняем:
1. В настройках индекса.
2. Полный reindex: задача `full_reindex` — бежит по всем approved фикам, собирает doc, пушит в Meili порциями.

Для нулевого downtime — использовать alias: основной индекс `fanfics`, новый `fanfics_v2`; после заполнения — swap. В MVP без alias'ов (Meili поддерживает алиасы начиная с 1.6).

## Метрики

- `meili_search_duration_seconds` histogram.
- `meili_index_tasks_total{status}` counter.
- `search_cache_hit_total` / `search_cache_miss_total`.
- `search_fallback_used_total` — когда использован PG FTS.

## Эксплуатация

- `MEILI_MASTER_KEY` — в env, не в конфиге.
- API-ключи с ограничениями: бот использует ключ с правами на `fanfics` read+write; инлайн-поиск — read-only ключ.
- Дамп/restore Meilisearch: `curl /dumps` → файл в `meili_data/dumps`, перенос. Полное удаление индекса восстанавливается `full_reindex` из PostgreSQL — PG остаётся source of truth.
