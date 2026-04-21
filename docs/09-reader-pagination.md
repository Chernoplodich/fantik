# 09 · Читалка и пагинатор

## Цели

- Читатель получает текст главы **в точности в том форматировании, в котором его написал автор** — bold, italic, spoiler, code, blockquote, ссылки, custom emoji.
- Навигация между страницами и главами — через `editMessageText`, без засорения чата.
- Сохранение прогресса, чтобы пользователь вернулся и продолжил с того же места.
- Страница помещается в лимит 4096 символов Telegram, с запасом под заголовок.

## Ключевая особенность: UTF-16

Telegram считает `offset` и `length` в **MessageEntity** в UTF-16 code units, **а не** в Unicode code points. Разница существенна для эмодзи и символов за пределами BMP:

- `"a"` — 1 code point, 1 UTF-16 unit.
- `"ñ"` — 1 code point, 1 UTF-16 unit.
- `"😀"` — 1 code point, **2 UTF-16 units** (surrogate pair).
- `"👨‍👩‍👧"` — несколько code points и ещё больше UTF-16 units (ZWJ-последовательность).

В Python строка — UTF-8 внутри, но индексация — по code points. Поэтому **все операции с offset/length должны проходить через явный пересчёт**:

```python
def char_to_utf16(s: str, idx: int) -> int:
    """Переводит позицию в Python-строке (code points) в UTF-16 units."""
    return len(s[:idx].encode('utf-16-le')) // 2

def utf16_to_char(s: str, utf16_idx: int) -> int:
    """Обратная операция."""
    # Двигаемся по строке, считая utf16 units на каждом code point.
    units = 0
    for i, ch in enumerate(s):
        if units >= utf16_idx:
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
    return len(s)
```

Утилиты — в `infrastructure/telegram/entity_utils.py`. Покрыты юнит-тестами с различными символами (кириллица, emoji, ZWJ).

## Лимит страницы

Лимит Telegram `sendMessage` / `editMessageText` — **4096 UTF-16 units**. Наш лимит страницы — **3900 units** (запас на заголовок и навигационный хвост).

Заголовок страницы (помимо текста): `Глава 3 · 2/8`. Entities для него не нужны — pure ASCII + unicode glyph.

## Алгоритм паджинации (`ChapterPaginator`)

Вход: `text: str`, `entities: list[MessageEntity]` (оба по главе целиком).

Выход: `pages: list[Page]`, где `Page = {text: str, entities: list[MessageEntity]}` — offsets в каждой странице пересчитаны от её начала.

### Высокоуровневый алгоритм

```
1. Построить список возможных «точек реза» (cut points) в тексте:
   - \n\n (абзац, приоритет 100)
   - \n   (строка, приоритет 50)
   - ". " / "! " / "? " (конец предложения, приоритет 20)
   - " "  (пробел, приоритет 1)
2. Фильтровать точки: оставить только те, что НЕ попадают внутрь entity.
   (Позиция i попадает внутрь entity e если e.offset < i_utf16 < e.offset + e.length)
3. Жадно набирать страницы:
   curr_start = 0
   while curr_start < len_utf16:
     max_end = curr_start + PAGE_LIMIT
     # найти самый большой cut в диапазоне [curr_start, max_end]
     # с максимальным приоритетом, предпочитая ближе к max_end
     cut = best_cut_in(curr_start, max_end)
     if cut is None:
        # ни одной разрешённой точки в диапазоне —
        # вынуждены резать посреди entity → сплит entity
        cut = max_end
     pages.append( slice(curr_start, cut) )
     curr_start = cut (пропуская пробелы/переносы в начале следующей)
4. Для каждой страницы — пересчитать entities:
   - оставить только те, что пересекаются с диапазоном [page_start, page_end]
   - для пересекающих — обрезать offset/length к странице
   - если entity выходит за границу — дублировать: на текущей странице — до границы, на следующей — от границы
```

### Сплит entities

```python
def split_entities_for_page(
    entities: list[MessageEntity],
    page_start_u16: int,
    page_end_u16: int,
) -> list[MessageEntity]:
    out = []
    for e in entities:
        e_start = e.offset
        e_end = e.offset + e.length
        # отсечь entities, целиком вне страницы
        if e_end <= page_start_u16 or e_start >= page_end_u16:
            continue
        new_start = max(e_start, page_start_u16) - page_start_u16
        new_end = min(e_end, page_end_u16) - page_start_u16
        if new_end <= new_start:
            continue
        new_e = e.model_copy()
        new_e.offset = new_start
        new_e.length = new_end - new_start
        out.append(new_e)
    return out
```

### Custom emoji

Важно: `messageEntityCustomEmoji` обязан **полностью** обрамлять свой placeholder-эмодзи. Если разрез попадает внутри такой entity — **никогда** не сплитим её, ищем другую точку реза.

Защита: `entity_validator.py` при публикации отказывает, если `custom_emoji` имеет `length != len_utf16(placeholder)` — такого в нормальной отправке не бывает, но на всякий случай.

## Хранение страниц

После публикации/правки главы задача `repaginate_chapter(chapter_id)` в воркере:

1. Удаляет существующие страницы: `DELETE FROM chapter_pages WHERE chapter_id = ?`.
2. Запускает `ChapterPaginator.paginate(text, entities)`.
3. Вставляет `chapter_pages`.

Процесс идемпотентен; можно перезапускать.

Пока задача не отработала — читалка fallback'нётся на «вычислить страницу по запросу» (медленнее, но работает).

```python
async def get_page(chapter_id: int, page_no: int) -> Page:
    # 1. Redis
    cached = await redis.get(f"fic:_:ch:{chapter_id}:p:{page_no}")
    if cached:
        return deserialize(cached)
    # 2. chapter_pages
    row = await chapter_pages_repo.get(chapter_id, page_no)
    if row:
        await redis.setex(key, 3600, serialize(row))
        return row
    # 3. lazy — пагинируем в рантайме
    chapter = await chapters_repo.get(chapter_id)
    pages = paginate(chapter.text, chapter.entities)
    # сохраняем все pages (идемпотентно, ON CONFLICT DO NOTHING)
    await chapter_pages_repo.save_bulk(chapter_id, pages)
    return pages[page_no - 1]
```

## Кэш Redis

Ключ: `fic:<fic_id>:ch:<ch_id>:p:<page_no>` (или `ch:<ch_id>:p:<p>` — fic_id избыточен).

Значение — msgpack-сериализация `{text, entities}`.

TTL: 1 час.

Предпрефетч: при открытии страницы N — асинхронный prefetch страницы N+1 (warm cache для «Дальше»).

## Чтение: user flow

См. [`05-user-flows.md#5-чтение`](05-user-flows.md#5-чтение).

### Формат сообщения чтения

```
<b>Глава 3 · "Тишина"</b>
<i>Страница 2 из 8</i>

<текст страницы с entities>
```

Префикс — это **не часть** entity-массива главы. Его entities мы добавляем отдельно (`bold`, `italic`) и сдвигаем offset'ы страницы на длину префикса.

```python
def build_message(page: Page, fic: Fanfic, chapter: Chapter) -> tuple[str, list[MessageEntity]]:
    prefix = f"Глава {chapter.number} · «{chapter.title}»\nСтраница {page.page_no} из {chapter.pages_count}\n\n"
    prefix_u16 = utf16_length(prefix)
    prefix_entities = [
        MessageEntity(type="bold", offset=0, length=utf16_length(f"Глава {chapter.number} · «{chapter.title}»")),
        MessageEntity(type="italic", offset=utf16_length(f"Глава {chapter.number} · «{chapter.title}»\n"), length=utf16_length(f"Страница {page.page_no} из {chapter.pages_count}")),
    ]
    shifted = [e.model_copy(update={"offset": e.offset + prefix_u16}) for e in page.entities]
    return prefix + page.text, prefix_entities + shifted
```

## Клавиатура чтения

```python
def reader_kb(fic_id: int, ch_no: int, page_no: int, total_pages: int, is_bookmarked: bool, is_liked: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    # Нав по страницам
    if page_no > 1:
        b.button(text="◀ Назад", callback_data=ReadNav(fic_id=fic_id, ch=ch_no, p=page_no-1, a="prev").pack())
    b.button(text=f"📄 {page_no}/{total_pages}", callback_data="noop")
    if page_no < total_pages:
        b.button(text="Дальше ▶", callback_data=ReadNav(fic_id=fic_id, ch=ch_no, p=page_no+1, a="next").pack())
    b.adjust(3)
    # Глава нав
    b.row(
        InlineKeyboardButton(text="⏮ Глава", callback_data=ReadNav(fic_id=fic_id, ch=ch_no-1, p=1, a="chapter").pack()) if ch_no > 1 else InlineKeyboardButton(text=" ", callback_data="noop"),
        InlineKeyboardButton(text="📖 Оглавление", callback_data=ReadNav(fic_id=fic_id, ch=ch_no, p=page_no, a="toc").pack()),
        InlineKeyboardButton(text="Глава ⏭", callback_data=ReadNav(fic_id=fic_id, ch=ch_no+1, p=1, a="chapter").pack()) if ch_no < total_chapters else InlineKeyboardButton(text=" ", callback_data="noop"),
    )
    # Действия
    b.row(
        InlineKeyboardButton(text="📑" if is_bookmarked else "📖", callback_data=ReadNav(..., a="bookmark").pack()),
        InlineKeyboardButton(text="❤️" if is_liked else "🤍", callback_data=ReadNav(..., a="like").pack()),
        InlineKeyboardButton(text="⚠️", callback_data=ReadNav(..., a="report").pack()),
    )
    return b.as_markup()
```

## Прогресс чтения

При переходе на страницу — throttled-запись:

```python
async def save_progress_throttled(user_id, fic_id, chapter_id, page_no):
    key = f"progress_throttle:{user_id}:{fic_id}"
    # SET NX EX 5 — пишем, если последняя запись была >= 5 сек назад
    if await redis.set(key, "1", nx=True, ex=5):
        await progress_repo.upsert(user_id, fic_id, chapter_id, page_no)
    else:
        # ставим pending задачу на 5 сек — чтобы последняя страница обязательно записалась
        await scheduled_updates.set(user_id, fic_id, chapter_id, page_no, delay=5)
```

В «Моей полке»:
```sql
SELECT f.*, rp.chapter_id, rp.page_no
FROM reading_progress rp
JOIN fanfics f ON f.id = rp.fic_id
WHERE rp.user_id = :uid
ORDER BY rp.updated_at DESC
LIMIT 20;
```

Вариант пустого прогресса — при первом открытии фика `[Читать с начала]` (глава 1, стр 1); если есть прогресс — `[Продолжить с главы X, стр Y]`.

## Отметка «прочитано до конца»

На последней странице последней главы пользователь видит кнопку `[✓ Дочитано]`. При нажатии:

```python
async def mark_completed(user_id, fic_id):
    async with uow:
        chapter = await chapters_repo.last_chapter(fic_id)
        await reads_completed_repo.upsert(user_id, chapter.id)
        await fanfics_repo.increment_reads_completed(fic_id)  # atomic UPDATE ... SET reads_completed_count = reads_completed_count + 1 WHERE ...
        # для аналитики
        events.publish(FicCompleted(user_id, fic_id))
```

Если нажатия нет, но был переход на последнюю страницу — тоже фиксируем `reads_completed(user_id, chapter_id)`. Инкремент `fanfics.reads_completed_count` — только при нажатии кнопки (или при фактическом просмотре последней страницы больше 30 секунд — опционально).

## Обложка

При открытии карточки фика:

```python
await bot.send_photo(
    chat_id=user_id,
    photo=fic.cover_file_id,
    caption=build_fic_caption(fic),
    caption_entities=fic.summary_entities,
    reply_markup=open_fic_kb(fic),
)
```

Далее навигация — `edit_message_text` к этому же сообщению? **Нет**: нельзя `editMessageText` у фото-сообщения. Варианты:

- **Вариант A (по умолчанию)**: удалить сообщение-обложку, отправить новое текстовое сообщение первой страницы. Навигация далее — через `edit_message_text` у него.
- **Вариант B**: карточку обложки не удалять, отправлять новое сообщение — страница чтения. «Вернуться к карточке» — отдельная кнопка.
- **Вариант C**: совмещать обложку и текст через `sendPhoto(caption=...)`, навигация — `edit_message_caption` (лимит caption 1024 — не подходит для длинного текста).

Выбираем **A**: минимум мусора, один активный «читающий экран».

Если фика нет обложки — сразу текстовая карточка `sendMessage`, навигация через `edit`.

## Обработка «message is not modified»

Telegram возвращает ошибку, если `editMessageText` вызвали с тем же текстом+клавиатурой. У нас такое может случиться при двойном кликe «Дальше» — игнорируем эту ошибку в middleware.

## Edge cases

- **Глава удалена во время чтения**: при запросе page возвращаем 404-like поведение, бот показывает «Эта глава больше недоступна. Вернуться к фику?» с кнопкой.
- **Фик архивирован**: аналогично. Deep-link на архивный фик → «Работа снята с публикации».
- **Custom emoji у пользователя без premium**: рендерится fallback-текстом — штатное поведение Telegram. Ничего не делаем.
- **Слишком большая entity (покрывает всю главу)**: форсим разрез и дублируем. В крайнем случае — пишем warning в логи и показываем пользователю.
- **Спойлеры**: type=`spoiler` — сохраняем; клиенты Telegram показывают скрытый блок.

## Тесты

- Property-based: hypothesis генерирует текст с случайными entities, проверяем инварианты:
  - Склейка страниц + их entities == исходный текст + исходные entities (после normalization).
  - Каждая страница ≤ 3900 UTF-16 units.
  - Entities каждой страницы не выходят за её границы.
- Снапшот-тесты на известные сложные случаи (русский + emoji + spoiler + code block).
- Perf: паджинатор должен обрабатывать главу 100_000 units < 50 мс на M2.

## Метрики

- `pagination_pages_total{chapter_id_bucket}` — счётчик.
- `pagination_duration_seconds` — histogram.
- `reader_page_cache_hit_total` / `reader_page_cache_miss_total`.
- `reader_edit_message_errors_total{error}`.
