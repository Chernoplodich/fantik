"""Pure-функции: SearchCommand → Meili filter/sort/facets.

Вынесено отдельно для юнит-тестов без I/O.
"""

from __future__ import annotations

from app.application.search.dto import SearchCommand

FACETS: tuple[str, ...] = ("fandom_name", "age_rating", "tags")


def _escape(value: str) -> str:
    """Экранирование одинарных кавычек для Meili filter-DSL."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_filter(cmd: SearchCommand) -> list[str]:
    """Построить список clause'ов (AND между собой).

    Пустые списки не добавляют ничего.
    """
    clauses: list[str] = []

    if cmd.fandoms:
        ids = ",".join(str(int(f)) for f in cmd.fandoms)
        clauses.append(f"fandom_id IN [{ids}]")

    if cmd.age_ratings:
        vals = ",".join(f"'{_escape(str(r))}'" for r in cmd.age_ratings)
        clauses.append(f"age_rating IN [{vals}]")

    # AND по всем выбранным тегам — фик должен содержать каждый выбранный.
    for t in cmd.tags:
        clauses.append(f"tags = '{_escape(str(t))}'")

    return clauses


def build_sort(cmd: SearchCommand) -> list[str] | None:
    """`None` для `relevance` — даёт работать rankingRules."""
    match cmd.sort:
        case "relevance":
            return None
        case "newest":
            return ["first_published_at:desc"]
        case "updated":
            return ["updated_at:desc"]
        case "top":
            return ["likes_count:desc"]
        case "longest":
            return ["chars_count:desc"]
    return None


def build_facets() -> list[str]:
    return list(FACETS)
