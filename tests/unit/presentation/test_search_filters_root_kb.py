"""Smoke-тесты filters_root_kb: лейблы фильтров в человеческом виде, без счётчиков «(0)»."""

from __future__ import annotations

from app.presentation.bot.keyboards.search_filters import filters_root_kb


def _flatten(kb: object) -> list[str]:
    out: list[str] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append(btn.text)
    return out


def test_root_kb_shows_human_labels_when_empty() -> None:
    kb = filters_root_kb(
        fandom_label="🎭 Любой фандом",
        age_label="🔞 Любой возраст",
        tag_label="🏷 Без тегов",
        sort="relevance",
    )
    texts = _flatten(kb)
    assert "✏️ Запрос: (—)" in texts
    assert "🎭 Любой фандом" in texts
    assert "🔞 Любой возраст" in texts
    assert "🏷 Без тегов" in texts
    assert any("Показать" in t for t in texts)
    assert any("Сбросить" in t for t in texts)


def test_root_kb_shortens_long_query() -> None:
    kb = filters_root_kb(
        fandom_label="🎭 Любой фандом",
        age_label="🔞 Любой возраст",
        tag_label="🏷 Без тегов",
        sort="relevance",
        query="очень длинный запрос для проверки урезания",
    )
    texts = _flatten(kb)
    q_btn = next(t for t in texts if t.startswith("✏️ "))
    assert "…" in q_btn


def test_root_kb_renders_provided_labels() -> None:
    kb = filters_root_kb(
        fandom_label="🎭 Гарри Поттер",
        age_label="🔞 R",
        tag_label="🏷 Выбрано: 3",
        sort="newest",
        query="магия",
    )
    texts = _flatten(kb)
    assert "✏️ магия" in texts
    assert "🎭 Гарри Поттер" in texts
    assert "🔞 R" in texts
    assert "🏷 Выбрано: 3" in texts
    assert any("Новые" in t for t in texts)
