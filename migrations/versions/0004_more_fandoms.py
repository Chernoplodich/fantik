"""seed: расширить список фандомов (≈25 популярных из books/movies/games/anime/other).

ON CONFLICT (slug) DO NOTHING — безопасно перекатывать.

Revision ID: 0004_more_fandoms
Revises: 0003_moderation_audit
Create Date: 2026-04-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_more_fandoms"
down_revision: str | None = "0003_moderation_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FANDOMS: list[dict[str, object]] = [
    # books
    {"slug": "asoiaf", "name": "Песнь льда и пламени / Игра престолов", "category": "books",
     "aliases": ["GoT", "Game of Thrones", "ASOIAF", "Мартин"]},
    {"slug": "sherlock-holmes", "name": "Шерлок Холмс", "category": "books",
     "aliases": ["Sherlock", "Holmes", "Дойл", "Бейкер-стрит"]},
    {"slug": "percy-jackson", "name": "Перси Джексон", "category": "books",
     "aliases": ["Percy Jackson", "Олимпийцы", "Риордан"]},
    {"slug": "hunger-games", "name": "Голодные игры", "category": "books",
     "aliases": ["Hunger Games", "Китнисс"]},
    {"slug": "discworld", "name": "Плоский мир", "category": "books",
     "aliases": ["Discworld", "Пратчетт"]},
    {"slug": "dune", "name": "Дюна", "category": "books",
     "aliases": ["Dune", "Атрейдесы", "Арракис"]},
    # movies / TV
    {"slug": "star-wars", "name": "Звёздные войны", "category": "movies",
     "aliases": ["Star Wars", "SW", "Джедаи"]},
    {"slug": "dc", "name": "DC Comics (фильмы/комиксы)", "category": "movies",
     "aliases": ["DCU", "Бэтмен", "Супермен"]},
    {"slug": "stranger-things", "name": "Очень странные дела", "category": "movies",
     "aliases": ["Stranger Things", "Хоукинс"]},
    {"slug": "supernatural", "name": "Сверхъестественное", "category": "movies",
     "aliases": ["Supernatural", "Винчестеры"]},
    {"slug": "sherlock-bbc", "name": "Шерлок (BBC)", "category": "movies",
     "aliases": ["BBC Sherlock", "Камбербэтч"]},
    {"slug": "doctor-who", "name": "Доктор Кто", "category": "movies",
     "aliases": ["Doctor Who", "Тардис"]},
    # games
    {"slug": "genshin", "name": "Genshin Impact", "category": "games",
     "aliases": ["Геншин", "Тейват"]},
    {"slug": "skyrim", "name": "The Elder Scrolls / Skyrim", "category": "games",
     "aliases": ["TES", "Skyrim", "Тамриэль"]},
    {"slug": "mass-effect", "name": "Mass Effect", "category": "games",
     "aliases": ["MassEffect", "Шепард", "Нормандия"]},
    {"slug": "undertale", "name": "Undertale / Deltarune", "category": "games",
     "aliases": ["Undertale", "Deltarune", "Санс"]},
    {"slug": "disco-elysium", "name": "Disco Elysium", "category": "games",
     "aliases": ["DE", "Гарри Дюбуа", "Ревашоль"]},
    {"slug": "baldurs-gate", "name": "Baldur's Gate 3", "category": "games",
     "aliases": ["BG3", "Baldurs Gate", "Фейрун"]},
    # anime / manga
    {"slug": "jujutsu-kaisen", "name": "Магическая битва (Jujutsu Kaisen)", "category": "anime",
     "aliases": ["JJK", "Jujutsu Kaisen", "Гёто"]},
    {"slug": "attack-on-titan", "name": "Атака титанов", "category": "anime",
     "aliases": ["AoT", "SnK", "Shingeki no Kyojin", "Эрен"]},
    {"slug": "one-piece", "name": "One Piece", "category": "anime",
     "aliases": ["One Piece", "Луффи"]},
    {"slug": "hunter-x-hunter", "name": "Hunter × Hunter", "category": "anime",
     "aliases": ["HxH", "Hunter x Hunter", "Гон"]},
    {"slug": "haikyuu", "name": "Волейбол!! (Haikyuu)", "category": "anime",
     "aliases": ["Haikyuu", "Хината"]},
    {"slug": "genshin-anime", "name": "Demon Slayer (Kimetsu no Yaiba)", "category": "anime",
     "aliases": ["Demon Slayer", "Kimetsu", "Танджиро"]},
    # other / original
    {"slug": "original", "name": "Оригинальная вселенная (only sandbox)", "category": "other",
     "aliases": ["OC", "Original", "Оригинал"]},
    {"slug": "crossover", "name": "Кроссовер / несколько вселенных", "category": "other",
     "aliases": ["Crossover", "XOver"]},
]


def upgrade() -> None:
    conn = op.get_bind()
    for f in FANDOMS:
        conn.execute(
            sa.text(
                "INSERT INTO fandoms (slug, name, category, aliases, active) "
                "VALUES (:slug, :name, :category, :aliases, TRUE) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {
                "slug": f["slug"],
                "name": f["name"],
                "category": f["category"],
                "aliases": list(f["aliases"]),  # type: ignore[arg-type]
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    for f in FANDOMS:
        conn.execute(sa.text("DELETE FROM fandoms WHERE slug = :slug"), {"slug": f["slug"]})
