"""ChapterPaginator: режет главу на страницы ≤ PAGE_LIMIT_UTF16 UTF-16 units.

Алгоритм (см. docs/09-reader-pagination.md):
  1. Собрать допустимые точки реза в UTF-16 позициях с приоритетами:
       \\n\\n → 100, \\n → 50, ". "/"! "/"? " → 20, " " → 1.
  2. Исключить точки, попадающие ВНУТРЬ entity.
  3. Жадно набирать страницы: в окне (start, start+PAGE_LIMIT] берём максимальный
     приоритет, tie-break — ближе к правому краю.
  4. Если валидной точки в окне нет — вынужденный разрыв на границе окна,
     **но** если она внутри `custom_emoji` — сдвигаем к левой границе этой entity
     (custom_emoji целостны по требованию Telegram).
  5. Entities страницы — обрезаем/клонируем по границам страницы; custom_emoji
     целиком переносится на одну сторону (не дублируется).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.utf16 import char_to_utf16, utf16_length, utf16_to_char

PAGE_LIMIT_UTF16: int = 3900


@dataclass(frozen=True)
class Page:
    """Страница главы: текст + entities с offsets относительно начала страницы."""

    page_no: int
    text: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    chars_count: int = 0  # длина text в UTF-16 units


# Приоритеты точек реза.
_PRI_PARAGRAPH = 100
_PRI_LINEBREAK = 50
_PRI_SENTENCE = 20
_PRI_SPACE = 1


def _build_cut_points(text: str) -> list[tuple[int, int]]:
    """Вернуть список (u16_position, priority), отсортированный по позиции.

    Позиция — сразу ПОСЛЕ делимитера; текущая страница оканчивается на делимитер,
    следующая начинается с первого символа сразу за ним. Если одна позиция
    удовлетворяет нескольким правилам, берётся максимальный приоритет.
    """
    if not text:
        return []

    # word accumulate char-по-char, tracking u16 running position.
    u16 = 0
    # Для быстрого поиска приоритетов по позиции используем dict[pos → max_pri].
    by_pos: dict[int, int] = {}

    n = len(text)
    # Используем two-char окно: char at i и char at i-1 (для \n\n и ". ").
    for i in range(n):
        ch = text[i]
        # advance u16 by size of ch
        u16 += 2 if ord(ch) > 0xFFFF else 1

        # Позиция "после ch" — это u16 сейчас.
        pos = u16
        prev = text[i - 1] if i >= 1 else ""

        pri = 0
        if ch == "\n":
            # \n\n имеет приоритет 100, одиночный \n — 50.
            pri = _PRI_PARAGRAPH if prev == "\n" else _PRI_LINEBREAK
        elif ch == " " and prev in (".", "!", "?"):
            pri = _PRI_SENTENCE
        elif ch == " ":
            pri = _PRI_SPACE

        if pri:
            # Максимум, если несколько правил (например, "\n" после "\n" даст 100,
            # и первый "\n" отдельно — 50, на разных позициях).
            cur = by_pos.get(pos, 0)
            if pri > cur:
                by_pos[pos] = pri

    return sorted(by_pos.items())


def _sort_entities(entities: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Упорядочить entities по (offset, -length). Возвращает валидные копии."""
    if not entities:
        return []
    out: list[dict[str, Any]] = []
    for e in entities:
        t = e.get("type")
        o = e.get("offset")
        ln = e.get("length")
        if not isinstance(t, str) or not isinstance(o, int) or not isinstance(ln, int):
            continue
        if o < 0 or ln < 1:
            continue
        out.append(dict(e))
    out.sort(key=lambda x: (int(x["offset"]), -int(x["length"])))
    return out


def _position_inside_entity(pos: int, ent: dict[str, Any]) -> bool:
    """pos попадает СТРОГО внутрь entity (границы не считаются)."""
    o = int(ent["offset"])
    ln = int(ent["length"])
    return o < pos < o + ln


def _position_inside_any(pos: int, ents: list[dict[str, Any]]) -> bool:
    return any(_position_inside_entity(pos, e) for e in ents)


def _select_best_cut(cuts: list[tuple[int, int]], start: int, end_cap: int) -> int | None:
    """Найти наилучшую точку реза в диапазоне (start, end_cap].

    Критерии: максимальный priority, tie-break — ближе к end_cap (больший pos).
    """
    best_pos: int | None = None
    best_pri = 0
    for pos, pri in cuts:
        if pos <= start:
            continue
        if pos > end_cap:
            break
        if pri > best_pri or (pri == best_pri and (best_pos is None or pos > best_pos)):
            best_pri = pri
            best_pos = pos
    return best_pos


def _find_custom_emoji_covering(pos: int, ents: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Вернуть custom_emoji, внутрь которой строго попадает pos (иначе None)."""
    for e in ents:
        if e.get("type") != "custom_emoji":
            continue
        if _position_inside_entity(pos, e):
            return e
    return None


def _safeguard_cut(end_cap: int, start: int, ents: list[dict[str, Any]]) -> int:
    """Если end_cap внутри custom_emoji — сдвигаем влево к её offset.

    Повторяем: другое custom_emoji может идти встык. Если сдвиг уходит ≤ start,
    возвращаем end_cap (пожертвуем целостностью — патологический ввод).
    """
    end = end_cap
    for _ in range(8):
        ce = _find_custom_emoji_covering(end, ents)
        if ce is None:
            return end
        new_end = int(ce["offset"])
        if new_end <= start:
            return end_cap
        end = new_end
    return end


def _slice_entities_for_page(
    ents: list[dict[str, Any]],
    page_start_u16: int,
    page_end_u16: int,
) -> list[dict[str, Any]]:
    """Обрезать и клонировать entities под диапазон страницы.

    Для `custom_emoji`: если entity целиком внутри страницы — переносим как есть;
    если пересекает границу — не переносим (граница могла быть вынужденной).
    """
    out: list[dict[str, Any]] = []
    for e in ents:
        o = int(e["offset"])
        ln = int(e["length"])
        e_end = o + ln
        if e_end <= page_start_u16 or o >= page_end_u16:
            continue
        fully_inside = o >= page_start_u16 and e_end <= page_end_u16
        if e.get("type") == "custom_emoji" and not fully_inside:
            # Не копируем «поломанную» custom_emoji (не должно происходить в норме).
            continue
        new_offset = max(o, page_start_u16) - page_start_u16
        new_end = min(e_end, page_end_u16) - page_start_u16
        if new_end <= new_offset:
            continue
        new_e = dict(e)
        new_e["offset"] = new_offset
        new_e["length"] = new_end - new_offset
        out.append(new_e)
    return out


class ChapterPaginator:
    """Статический сервис пагинации главы."""

    @staticmethod
    def paginate(text: str, entities: list[dict[str, Any]] | None = None) -> list[Page]:
        """Разбить текст главы на страницы ≤ PAGE_LIMIT_UTF16 UTF-16 units."""
        text_u16 = utf16_length(text)
        if text_u16 == 0:
            return []

        ents = _sort_entities(entities)

        # Фильтруем точки реза, попадающие внутрь entity (любой, включая custom_emoji).
        raw_cuts = _build_cut_points(text)
        cuts: list[tuple[int, int]] = [
            (p, pr) for p, pr in raw_cuts if not _position_inside_any(p, ents)
        ]

        pages: list[Page] = []
        start = 0
        page_no = 1
        while start < text_u16:
            end_cap = min(start + PAGE_LIMIT_UTF16, text_u16)
            if end_cap >= text_u16:
                end = text_u16
            else:
                picked = _select_best_cut(cuts, start, end_cap)
                if picked is not None:
                    end = picked
                else:
                    # Вынужденный разрыв — охраняем целостность custom_emoji.
                    end = _safeguard_cut(end_cap, start, ents)

            # Защита от бесконечного цикла: если сейф сдвинул end до start.
            if end <= start:
                end = end_cap

            char_start = utf16_to_char(text, start)
            char_end = utf16_to_char(text, end)
            page_text = text[char_start:char_end]
            page_ents = _slice_entities_for_page(ents, start, end)
            page_u16 = end - start
            pages.append(
                Page(
                    page_no=page_no,
                    text=page_text,
                    entities=page_ents,
                    chars_count=page_u16,
                )
            )
            start = end
            page_no += 1

        return pages


def shift_entities(entities: list[dict[str, Any]], shift_u16: int) -> list[dict[str, Any]]:
    """Сдвинуть offset всех entities на shift_u16 (для префикса сообщения)."""
    out: list[dict[str, Any]] = []
    for e in entities:
        new_e = dict(e)
        new_e["offset"] = int(new_e["offset"]) + shift_u16
        out.append(new_e)
    return out


__all__ = [
    "PAGE_LIMIT_UTF16",
    "ChapterPaginator",
    "Page",
    "char_to_utf16",
    "shift_entities",
    "utf16_length",
    "utf16_to_char",
]
