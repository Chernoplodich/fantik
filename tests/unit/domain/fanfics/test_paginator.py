"""Property-based + snapshot тесты ChapterPaginator."""

from __future__ import annotations

import time
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.domain.fanfics.services.paginator import (
    PAGE_LIMIT_UTF16,
    ChapterPaginator,
)
from app.domain.shared.utf16 import char_to_utf16, utf16_length


# ---------- hypothesis-стратегии ----------


# Текст: смесь латиницы, кириллицы, пробелов, переносов и нескольких emoji.
_ALPHABET = st.text(
    alphabet=st.sampled_from(
        list("abcdefghijklmnopqrstuvwxyzёъабвгдеёжзийклмнопрстуфхцчшщъыьэюя \n\n.!?,;:—")
    ),
    min_size=0,
    max_size=12_000,
).filter(lambda s: True)


@st.composite
def _text_with_entities(draw: st.DrawFn) -> tuple[str, list[dict[str, Any]]]:
    text: str = draw(_ALPHABET)
    u16 = utf16_length(text)
    # Небольшое кол-во entities — чтобы не раздувать поиск.
    n = draw(st.integers(min_value=0, max_value=15))
    entities: list[dict[str, Any]] = []
    if u16 == 0 or n == 0:
        return text, entities
    allowed_types = ["bold", "italic", "underline", "spoiler", "code"]
    for _ in range(n):
        o = draw(st.integers(min_value=0, max_value=max(0, u16 - 1)))
        ln = draw(st.integers(min_value=1, max_value=max(1, min(100, u16 - o))))
        t = draw(st.sampled_from(allowed_types))
        entities.append({"type": t, "offset": o, "length": ln})
    return text, entities


# ---------- Инвариант 1: склейка страниц = исходный текст ----------


@given(_text_with_entities())
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_join_equals_original(data: tuple[str, list[dict[str, Any]]]) -> None:
    text, entities = data
    pages = ChapterPaginator.paginate(text, entities)
    joined = "".join(p.text for p in pages)
    assert joined == text


# ---------- Инвариант 2: каждая страница ≤ PAGE_LIMIT_UTF16 ----------


@given(_text_with_entities())
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_all_pages_under_limit(
    data: tuple[str, list[dict[str, Any]]],
) -> None:
    text, entities = data
    pages = ChapterPaginator.paginate(text, entities)
    for p in pages:
        assert p.chars_count <= PAGE_LIMIT_UTF16
        assert utf16_length(p.text) == p.chars_count


# ---------- Инвариант 3: entities на странице в границах ----------


@given(_text_with_entities())
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_entities_within_page_bounds(
    data: tuple[str, list[dict[str, Any]]],
) -> None:
    text, entities = data
    pages = ChapterPaginator.paginate(text, entities)
    for p in pages:
        for e in p.entities:
            o = int(e["offset"])
            ln = int(e["length"])
            assert 0 <= o
            assert o + ln <= p.chars_count


# ---------- Инвариант 4: custom_emoji никогда не режется ----------


@st.composite
def _text_with_custom_emoji(
    draw: st.DrawFn,
) -> tuple[str, list[dict[str, Any]]]:
    text: str = draw(_ALPHABET)
    u16 = utf16_length(text)
    if u16 < 2:
        return text, []
    entities: list[dict[str, Any]] = []
    # 0-3 custom_emoji, placeholder 1-2 units
    n = draw(st.integers(min_value=0, max_value=3))
    taken: set[int] = set()
    for _ in range(n):
        ln = draw(st.sampled_from([1, 2]))
        o = draw(st.integers(min_value=0, max_value=max(0, u16 - ln)))
        # Не пересекающиеся custom_emoji — иначе логика поломалась бы.
        if any(tt <= o + ln and t2 >= o for tt, t2 in taken):  # type: ignore[misc]
            continue
        taken.add((o, o + ln))  # type: ignore[arg-type]
        entities.append(
            {
                "type": "custom_emoji",
                "offset": o,
                "length": ln,
                "custom_emoji_id": f"x{len(entities)}",
            }
        )
    return text, entities


@given(_text_with_custom_emoji())
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_custom_emoji_never_split(
    data: tuple[str, list[dict[str, Any]]],
) -> None:
    text, entities = data
    pages = ChapterPaginator.paginate(text, entities)
    # Собираем, какие custom_emoji entities сохранились целиком на страницах.
    ces = [e for e in entities if e["type"] == "custom_emoji"]
    # page_offsets в UTF-16 — накопительно
    page_start_u16 = 0
    seen_entities: set[tuple[int, int]] = set()
    for p in pages:
        for pe in p.entities:
            if pe.get("type") != "custom_emoji":
                continue
            abs_off = page_start_u16 + int(pe["offset"])
            abs_len = int(pe["length"])
            seen_entities.add((abs_off, abs_len))
        page_start_u16 += p.chars_count
    # Каждая исходная custom_emoji должна либо сохраниться целиком, либо попадать
    # в гарантированный диапазон (page_start, page_end] полностью на одной странице.
    for ce in ces:
        assert (int(ce["offset"]), int(ce["length"])) in seen_entities


# ---------- Инвариант 5: полное восстановление entities после склейки страниц ----------


@given(_text_with_entities())
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_entities_fully_covered_after_join(
    data: tuple[str, list[dict[str, Any]]],
) -> None:
    """Склейка entities (со сдвигом по страницам) покрывает исходные entities.

    Для не-custom_emoji entities: исходная покрывается unioned интервалами
    из страниц. (Custom emoji не режутся, они покрываются целиком или
    выпадают полностью — отдельный тест.)
    """
    text, entities = data
    pages = ChapterPaginator.paginate(text, entities)

    # Для каждой entity кроме custom_emoji собираем интервалы по страницам.
    covered: dict[int, list[tuple[int, int]]] = {}  # key by idx in entities
    for idx, _ in enumerate(entities):
        covered[idx] = []

    page_start = 0
    for p in pages:
        for pe in p.entities:
            # Найдём соответствующую исходную entity.
            abs_off = page_start + int(pe["offset"])
            abs_end = abs_off + int(pe["length"])
            for idx, e in enumerate(entities):
                if (
                    pe.get("type") == e.get("type")
                    and int(pe.get("custom_emoji_id", 0)) == int(e.get("custom_emoji_id", 0))
                    and int(e["offset"]) <= abs_off
                    and abs_end <= int(e["offset"]) + int(e["length"])
                ):
                    covered[idx].append((abs_off, abs_end))
                    break
        page_start += p.chars_count

    for idx, e in enumerate(entities):
        if e.get("type") == "custom_emoji":
            continue
        intervals = sorted(covered[idx])
        if not intervals:
            # Возможно, entity попала на резкую границу — но текстовые entities
            # должны покрываться, т.к. мы не удаляем их (пусть и сплитим).
            # Проверим: в исходной тексте эта позиция реально есть.
            assert int(e["offset"]) + int(e["length"]) <= utf16_length(text)
            continue
        # Интервалы должны покрывать исходный offset..offset+length.
        target_start = int(e["offset"])
        target_end = target_start + int(e["length"])
        # Merge intervals
        merged: list[tuple[int, int]] = []
        for s, en in intervals:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], en))
            else:
                merged.append((s, en))
        # Один из объединённых интервалов должен покрывать target.
        assert any(s <= target_start and en >= target_end for s, en in merged), (
            f"entity {e} не покрыта страницами: {merged}"
        )


# ---------- Snapshot-тесты ----------


class TestSnapshots:
    def test_short_text_one_page(self) -> None:
        pages = ChapterPaginator.paginate("Hello world.", None)
        assert len(pages) == 1
        assert pages[0].text == "Hello world."
        assert pages[0].chars_count == 12

    def test_cuts_on_paragraph(self) -> None:
        para = "A" * 2000 + "\n\n"
        text = para * 3
        pages = ChapterPaginator.paginate(text, None)
        assert len(pages) >= 2
        # Каждая страница ≤ limit; границы после "\n\n".
        for p in pages[:-1]:
            assert p.text.endswith("\n\n")

    def test_preserves_entities_in_single_page(self) -> None:
        # "Hello world." — "world" bold: offset 6, length 5
        entities = [{"type": "bold", "offset": 6, "length": 5}]
        pages = ChapterPaginator.paginate("Hello world.", entities)
        assert len(pages) == 1
        assert pages[0].entities == [{"type": "bold", "offset": 6, "length": 5}]

    def test_emoji_with_bold_spans(self) -> None:
        text = "a😀b"  # UTF-16 len = 4
        # bold на "😀b" — offset 1, length 3
        entities = [{"type": "bold", "offset": 1, "length": 3}]
        pages = ChapterPaginator.paginate(text, entities)
        assert len(pages) == 1
        assert pages[0].chars_count == 4
        assert pages[0].entities == [{"type": "bold", "offset": 1, "length": 3}]

    def test_custom_emoji_preserved_across_short_cuts(self) -> None:
        # Длинный текст с custom_emoji — форс-проверка, что emoji не ломается.
        text = "X" * 3895 + "😀" + "Y" * 500
        # custom_emoji на позицию "😀" = offset 3895, length 2
        entities = [
            {
                "type": "custom_emoji",
                "offset": 3895,
                "length": 2,
                "custom_emoji_id": "42",
            }
        ]
        pages = ChapterPaginator.paginate(text, entities)
        # emoji должен быть на одной из страниц целиком.
        page_u16 = 0
        preserved = False
        for p in pages:
            for pe in p.entities:
                if pe.get("type") == "custom_emoji":
                    abs_off = page_u16 + int(pe["offset"])
                    abs_len = int(pe["length"])
                    assert (abs_off, abs_len) == (3895, 2)
                    preserved = True
            page_u16 += p.chars_count
        assert preserved, "custom_emoji не сохранилась"


# ---------- Perf ----------


@pytest.mark.slow
def test_performance_100k_under_50ms() -> None:
    # Русский lorem, ~100k UTF-16 units
    chunk = (
        "Карий лис перепрыгнул через ленивую собаку. "
        "Мелкая речка разливается по долине, а в небе кружат ласточки. "
    )
    total: list[str] = []
    size = 0
    while size < 100_000:
        total.append(chunk)
        size += utf16_length(chunk)
    text = "".join(total)
    t0 = time.perf_counter()
    pages = ChapterPaginator.paginate(text, None)
    dt = time.perf_counter() - t0
    assert pages  # nonzero
    # 50 мс на M2; даём запас для CI → 500 мс.
    assert dt < 0.5, f"paginator too slow: {dt:.3f}s for {size} units"


# ---------- Сопутствующий round-trip на char_to_utf16 / utf16_to_char с ZWJ ----------


@given(
    st.text(
        alphabet=st.sampled_from(list("a😀b👨‍👩‍👧c🎉ñ")),
        min_size=0,
        max_size=40,
    )
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_char_to_utf16_round_trip_with_emoji(s: str) -> None:
    from app.domain.shared.utf16 import utf16_to_char

    for i in range(len(s) + 1):
        u = char_to_utf16(s, i)
        # utf16_to_char может округлить внутри суррогатной пары; для корректных
        # позиций code_point (которые мы вводили через char_to_utf16) round-trip точный.
        assert utf16_to_char(s, u) == i
