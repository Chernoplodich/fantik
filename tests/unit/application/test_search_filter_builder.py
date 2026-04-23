"""Unit: build_filter / build_sort для Meili-запросов."""

from __future__ import annotations

from app.application.search.dto import SearchCommand
from app.application.search.filter_builder import build_facets, build_filter, build_sort


class TestBuildFilter:
    def test_empty(self) -> None:
        assert build_filter(SearchCommand()) == []

    def test_single_fandom(self) -> None:
        assert build_filter(SearchCommand(fandoms=[1])) == ["fandom_id IN [1]"]

    def test_multiple_fandoms(self) -> None:
        assert build_filter(SearchCommand(fandoms=[1, 2, 3])) == ["fandom_id IN [1,2,3]"]

    def test_age_ratings(self) -> None:
        clauses = build_filter(SearchCommand(age_ratings=["R", "NC-17"]))
        assert clauses == ["age_rating IN ['R','NC-17']"]

    def test_tags_are_anded(self) -> None:
        # Каждый тег — отдельный clause, между ними AND (поведение Meili filter).
        clauses = build_filter(SearchCommand(tags=["AU", "Ангст"]))
        assert clauses == ["tags = 'AU'", "tags = 'Ангст'"]

    def test_quote_escaping(self) -> None:
        clauses = build_filter(SearchCommand(tags=["O'Brien"]))
        assert clauses == ["tags = 'O\\'Brien'"]

    def test_combo(self) -> None:
        cmd = SearchCommand(fandoms=[7], age_ratings=["R"], tags=["AU"])
        clauses = build_filter(cmd)
        assert "fandom_id IN [7]" in clauses
        assert "age_rating IN ['R']" in clauses
        assert "tags = 'AU'" in clauses


class TestBuildSort:
    def test_relevance_none(self) -> None:
        assert build_sort(SearchCommand(sort="relevance")) is None

    def test_newest(self) -> None:
        assert build_sort(SearchCommand(sort="newest")) == ["first_published_at:desc"]

    def test_updated(self) -> None:
        assert build_sort(SearchCommand(sort="updated")) == ["updated_at:desc"]

    def test_top(self) -> None:
        assert build_sort(SearchCommand(sort="top")) == ["likes_count:desc"]

    def test_longest(self) -> None:
        assert build_sort(SearchCommand(sort="longest")) == ["chars_count:desc"]


class TestBuildFacets:
    def test_default_set(self) -> None:
        assert "fandom_name" in build_facets()
        assert "age_rating" in build_facets()
        assert "tags" in build_facets()
