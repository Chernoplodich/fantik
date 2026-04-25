"""fandoms taxonomy expand: pg_trgm + категории + seed ~160 популярных фандомов.

Что делает:
- Включает расширение pg_trgm и создаёт GIN индекс на name (для быстрого ILIKE/тригграмм).
- Переименовывает категорию "movies" в "films" (точечно по slug, чтобы не задеть лишнего).
- Поправляет ошибки в существующем seed: stranger-things/sherlock-bbc/supernatural/doctor-who
  становятся series; запись со slug 'genshin-anime' (на самом деле Demon Slayer) переименована
  в slug 'demon-slayer' с правильным name/aliases.
- Заливает ~155 новых фандомов через ON CONFLICT (slug) DO NOTHING.

Revision ID: 0010_fandoms_taxonomy_expand
Revises: 0009_user_bot_block
Create Date: 2026-04-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_fandoms_taxonomy_expand"
down_revision: str | None = "0009_user_bot_block"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------- 11 категорий по образцу ficbook ----------
# anime — Аниме и манга
# books — Книги
# films — Фильмы
# series — Сериалы
# cartoons — Мультфильмы
# comics — Комиксы
# games — Видеоигры
# musicals — Мюзиклы и театр
# rpf — Известные люди
# originals — Ориджиналы
# other — Другое

# ---------- Существующие фиксапы ----------

# Перевод movies → films для записей, оставшихся в категории фильмов.
_MOVIES_TO_FILMS_SLUGS = ["marvel", "star-wars", "dc"]

# Эти были в movies, но фактически — сериалы.
_TO_SERIES_SLUGS = ["stranger-things", "sherlock-bbc", "supernatural", "doctor-who"]

# Запись со slug 'genshin-anime' содержит Demon Slayer (опечатка в seed 0004).
# Переименуем её правильно (slug→demon-slayer, name+aliases).


# ---------- ~155 новых фандомов ----------

NEW_FANDOMS: list[dict[str, object]] = [
    # ===== anime (~40) =====
    {"slug": "bleach", "name": "Bleach", "category": "anime", "aliases": ["Bleach", "Блич", "Куросаки Ичиго"]},
    {"slug": "death-note", "name": "Тетрадь смерти", "category": "anime", "aliases": ["Death Note", "Лайт Ягами", "Кира", "L"]},
    {"slug": "fullmetal-alchemist", "name": "Стальной алхимик (Fullmetal Alchemist)", "category": "anime", "aliases": ["FMA", "Brotherhood", "Эдвард Элрик", "Эд"]},
    {"slug": "tokyo-ghoul", "name": "Токийский гуль", "category": "anime", "aliases": ["Tokyo Ghoul", "Канеки"]},
    {"slug": "my-hero-academia", "name": "Моя геройская академия", "category": "anime", "aliases": ["MHA", "BNHA", "Деку", "Мидория"]},
    {"slug": "mob-psycho-100", "name": "Mob Psycho 100", "category": "anime", "aliases": ["Mob Psycho", "Моб"]},
    {"slug": "one-punch-man", "name": "One Punch Man", "category": "anime", "aliases": ["OPM", "Сайтама"]},
    {"slug": "jojo", "name": "JoJo's Bizarre Adventure", "category": "anime", "aliases": ["JoJo", "ДжоДжо", "ДжоДжо", "Джотаро"]},
    {"slug": "steins-gate", "name": "Steins;Gate", "category": "anime", "aliases": ["Штейнс гейт", "Окабе"]},
    {"slug": "code-geass", "name": "Code Geass", "category": "anime", "aliases": ["Код Гиас", "Лелуш"]},
    {"slug": "evangelion", "name": "Евангелион", "category": "anime", "aliases": ["Evangelion", "EVA", "NGE", "Синдзи"]},
    {"slug": "sailor-moon", "name": "Sailor Moon", "category": "anime", "aliases": ["Сейлор Мун", "Усаги"]},
    {"slug": "inuyasha", "name": "Инуяся", "category": "anime", "aliases": ["Inuyasha"]},
    {"slug": "yu-gi-oh", "name": "Yu-Gi-Oh!", "category": "anime", "aliases": ["Югио", "Yu Gi Oh"]},
    {"slug": "ouran-host-club", "name": "Школьный клуб Оранской старшей школы", "category": "anime", "aliases": ["Ouran HSHC", "Ouran"]},
    {"slug": "free-iwatobi", "name": "Free! Iwatobi Swim Club", "category": "anime", "aliases": ["Free!", "Free", "Хару"]},
    {"slug": "yuri-on-ice", "name": "Юри на льду", "category": "anime", "aliases": ["Yuri on Ice", "YOI"]},
    {"slug": "fairy-tail", "name": "Хвост феи (Fairy Tail)", "category": "anime", "aliases": ["Fairy Tail", "Нацу"]},
    {"slug": "soul-eater", "name": "Пожиратель душ (Soul Eater)", "category": "anime", "aliases": ["Soul Eater"]},
    {"slug": "cowboy-bebop", "name": "Cowboy Bebop", "category": "anime", "aliases": ["Ковбой Бибоп", "Спайк"]},
    {"slug": "vinland-saga", "name": "Сага о Винланде", "category": "anime", "aliases": ["Vinland Saga", "Торфинн"]},
    {"slug": "re-zero", "name": "Re:Zero", "category": "anime", "aliases": ["Re Zero", "Субару", "Эмилия"]},
    {"slug": "sword-art-online", "name": "Sword Art Online", "category": "anime", "aliases": ["SAO", "Кирито", "Асуна"]},
    {"slug": "black-butler", "name": "Тёмный дворецкий", "category": "anime", "aliases": ["Black Butler", "Kuroshitsuji", "Себастьян"]},
    {"slug": "ghibli", "name": "Студия Ghibli", "category": "anime", "aliases": ["Ghibli", "Миядзаки", "Тоторо"]},
    {"slug": "dragon-ball", "name": "Dragon Ball", "category": "anime", "aliases": ["DBZ", "Гоку"]},
    {"slug": "bungou-stray-dogs", "name": "Великий из бродячих псов", "category": "anime", "aliases": ["Bungou Stray Dogs", "BSD", "Дазай"]},
    {"slug": "chainsaw-man", "name": "Человек-бензопила", "category": "anime", "aliases": ["Chainsaw Man", "Дэндзи"]},
    {"slug": "spy-x-family", "name": "Spy × Family", "category": "anime", "aliases": ["Spy x Family", "Аня", "Лойд", "Йор"]},
    {"slug": "mushoku-tensei", "name": "Реинкарнация безработного", "category": "anime", "aliases": ["Mushoku Tensei", "Рудеус"]},
    {"slug": "mo-dao-zu-shi", "name": "Магистр дьявольского культа", "category": "anime", "aliases": ["MDZS", "Mo Dao Zu Shi", "Усянь"]},
    {"slug": "tian-guan-ci-fu", "name": "Благословение небожителей", "category": "anime", "aliases": ["TGCF", "Heaven Officials Blessing", "Се Лянь"]},
    {"slug": "ranma", "name": "Ранма ½", "category": "anime", "aliases": ["Ranma 1/2", "Ranma"]},
    {"slug": "berserk", "name": "Берсерк", "category": "anime", "aliases": ["Berserk", "Гатс"]},
    {"slug": "made-in-abyss", "name": "Созданный в бездне", "category": "anime", "aliases": ["Made in Abyss", "Рико"]},
    {"slug": "monster-anime", "name": "Монстр (Monster)", "category": "anime", "aliases": ["Monster", "Тенма", "Йохан"]},
    {"slug": "haikyuu-extra", "name": "Magi: The Labyrinth of Magic", "category": "anime", "aliases": ["Magi", "Маги"]},
    {"slug": "dr-stone", "name": "Dr. Stone", "category": "anime", "aliases": ["Dr Stone", "Сэнку"]},
    {"slug": "noragami", "name": "Бездомный бог (Noragami)", "category": "anime", "aliases": ["Noragami", "Ято"]},
    {"slug": "hells-paradise", "name": "Адский рай (Jigokuraku)", "category": "anime", "aliases": ["Hells Paradise", "Jigokuraku", "Габимару"]},

    # ===== books (~25) =====
    {"slug": "twilight", "name": "Сумерки", "category": "books", "aliases": ["Twilight", "Каллены", "Эдвард", "Белла"]},
    {"slug": "narnia", "name": "Хроники Нарнии", "category": "books", "aliases": ["Narnia", "Льюис"]},
    {"slug": "his-dark-materials", "name": "Тёмные начала (His Dark Materials)", "category": "books", "aliases": ["HDM", "Лира"]},
    {"slug": "inheritance-cycle", "name": "Эрагон (Inheritance Cycle)", "category": "books", "aliases": ["Eragon", "Эрагон"]},
    {"slug": "mortal-engines", "name": "Хроники хищных городов", "category": "books", "aliases": ["Mortal Engines", "Reeve"]},
    {"slug": "maze-runner", "name": "Бегущий в лабиринте", "category": "books", "aliases": ["Maze Runner", "Томас"]},
    {"slug": "divergent", "name": "Дивергент", "category": "books", "aliases": ["Divergent", "Трис"]},
    {"slug": "throne-of-glass", "name": "Стеклянный трон", "category": "books", "aliases": ["Throne of Glass", "ToG", "Селена"]},
    {"slug": "six-of-crows", "name": "Шестёрка воронов", "category": "books", "aliases": ["Six of Crows", "Каз"]},
    {"slug": "acotar", "name": "Королевство шипов и роз", "category": "books", "aliases": ["ACOTAR", "Маас", "Maas"]},
    {"slug": "stormlight-archive", "name": "Архив Буресвета", "category": "books", "aliases": ["Stormlight", "Сандерсон", "Каладин"]},
    {"slug": "wheel-of-time", "name": "Колесо Времени", "category": "books", "aliases": ["WoT", "Wheel of Time", "Джордан"]},
    {"slug": "foundation", "name": "Основание (Foundation)", "category": "books", "aliases": ["Foundation", "Азимов"]},
    {"slug": "enders-game", "name": "Игра Эндера", "category": "books", "aliases": ["Enders Game", "Эндер"]},
    {"slug": "vampire-academy", "name": "Академия вампиров", "category": "books", "aliases": ["Vampire Academy", "VA", "Роуз"]},
    {"slug": "mistborn", "name": "Mistborn (Рождённый туманом)", "category": "books", "aliases": ["Mistborn", "Сандерсон", "Вин"]},
    {"slug": "mortal-instruments", "name": "Орудия смерти (TMI)", "category": "books", "aliases": ["TMI", "Mortal Instruments", "Шэдоухантеры", "Клэри"]},
    {"slug": "shantaram", "name": "Шантарам", "category": "books", "aliases": ["Shantaram", "Робертс"]},
    {"slug": "metro-2033", "name": "Метро 2033", "category": "books", "aliases": ["Metro 2033", "Глуховский"]},
    {"slug": "dozory", "name": "Дозоры", "category": "books", "aliases": ["Лукьяненко", "Ночной Дозор"]},
    {"slug": "artemis-fowl", "name": "Артемис Фаул", "category": "books", "aliases": ["Artemis Fowl"]},
    {"slug": "echo-labyrinths", "name": "Лабиринты Ехо", "category": "books", "aliases": ["Макс Фрай", "Ехо"]},
    {"slug": "dark-tower", "name": "Тёмная башня", "category": "books", "aliases": ["Dark Tower", "Кинг", "Роланд"]},
    {"slug": "master-margarita", "name": "Мастер и Маргарита", "category": "books", "aliases": ["Булгаков", "Воланд"]},
    {"slug": "good-omens", "name": "Благие знамения", "category": "books", "aliases": ["Good Omens", "Кроули", "Азирафаэль"]},

    # ===== films (~12) =====
    {"slug": "potc", "name": "Пираты Карибского моря", "category": "films", "aliases": ["PotC", "Pirates of the Caribbean", "Воробей"]},
    {"slug": "indiana-jones", "name": "Индиана Джонс", "category": "films", "aliases": ["Indiana Jones"]},
    {"slug": "mad-max", "name": "Безумный Макс", "category": "films", "aliases": ["Mad Max", "Фуриоса"]},
    {"slug": "matrix", "name": "Матрица", "category": "films", "aliases": ["The Matrix", "Нео"]},
    {"slug": "inception", "name": "Начало (Inception)", "category": "films", "aliases": ["Inception", "Кобб"]},
    {"slug": "interstellar", "name": "Интерстеллар", "category": "films", "aliases": ["Interstellar", "Куп"]},
    {"slug": "avatar-cameron", "name": "Аватар (Кэмерон)", "category": "films", "aliases": ["Avatar", "Пандора", "Нави"]},
    {"slug": "john-wick", "name": "Джон Уик", "category": "films", "aliases": ["John Wick"]},
    {"slug": "fast-furious", "name": "Форсаж", "category": "films", "aliases": ["Fast and Furious", "Доминик Торетто"]},
    {"slug": "james-bond", "name": "Джеймс Бонд (007)", "category": "films", "aliases": ["James Bond", "007"]},
    {"slug": "tarantino-films", "name": "Фильмы Тарантино", "category": "films", "aliases": ["Tarantino", "Тарантино", "Pulp Fiction"]},
    {"slug": "tim-burton-films", "name": "Фильмы Тима Бёртона", "category": "films", "aliases": ["Tim Burton", "Бёртон"]},

    # ===== series (~22) =====
    {"slug": "got", "name": "Игра престолов / Дом Дракона", "category": "series", "aliases": ["GoT", "HotD", "Game of Thrones", "Таргариены", "Старки"]},
    {"slug": "walking-dead", "name": "Ходячие мертвецы", "category": "series", "aliases": ["TWD", "Walking Dead"]},
    {"slug": "vampire-diaries", "name": "Дневники вампира", "category": "series", "aliases": ["TVD", "Vampire Diaries", "Деймон", "Стефан"]},
    {"slug": "teen-wolf", "name": "Волчонок", "category": "series", "aliases": ["Teen Wolf", "Стайлз"]},
    {"slug": "lucifer", "name": "Люцифер", "category": "series", "aliases": ["Lucifer", "Decker"]},
    {"slug": "house-md", "name": "Доктор Хаус", "category": "series", "aliases": ["House MD", "Хаус"]},
    {"slug": "friends", "name": "Друзья (Friends)", "category": "series", "aliases": ["Friends", "Чендлер", "Росс"]},
    {"slug": "breaking-bad", "name": "Во все тяжкие", "category": "series", "aliases": ["Breaking Bad", "Уолтер Уайт", "Хайзенберг"]},
    {"slug": "better-call-saul", "name": "Лучше звоните Солу", "category": "series", "aliases": ["BCS", "Better Call Saul"]},
    {"slug": "dark-series", "name": "Тьма (Dark)", "category": "series", "aliases": ["Dark", "Йонас"]},
    {"slug": "mr-robot", "name": "Мистер Робот", "category": "series", "aliases": ["Mr Robot", "Эллиот"]},
    {"slug": "squid-game", "name": "Игра в кальмара", "category": "series", "aliases": ["Squid Game"]},
    {"slug": "peaky-blinders", "name": "Острые козырьки", "category": "series", "aliases": ["Peaky Blinders", "Шелби", "Томас Шелби"]},
    {"slug": "outlander", "name": "Чужестранка", "category": "series", "aliases": ["Outlander", "Джейми"]},
    {"slug": "bridgerton", "name": "Бриджертоны", "category": "series", "aliases": ["Bridgerton"]},
    {"slug": "wednesday", "name": "Уэнсдей (Wednesday)", "category": "series", "aliases": ["Wednesday", "Аддамс"]},
    {"slug": "witcher-netflix", "name": "Ведьмак (Netflix)", "category": "series", "aliases": ["The Witcher Netflix"]},
    {"slug": "the-boys", "name": "Пацаны (The Boys)", "category": "series", "aliases": ["The Boys", "Хоумлендер"]},
    {"slug": "loki-mcu", "name": "Локи (сериал)", "category": "series", "aliases": ["Loki", "Локи"]},
    {"slug": "wandavision", "name": "ВандаВижн", "category": "series", "aliases": ["WandaVision"]},
    {"slug": "heartstopper", "name": "Хартстоппер (Heartstopper)", "category": "series", "aliases": ["Heartstopper"]},
    {"slug": "young-royals", "name": "Молодые монархи (Young Royals)", "category": "series", "aliases": ["Young Royals"]},

    # ===== cartoons (~14) =====
    {"slug": "avatar-tla", "name": "Аватар: Легенда об Аанге", "category": "cartoons", "aliases": ["ATLA", "Avatar TLA", "Аватар", "Аанг"]},
    {"slug": "korra", "name": "Легенда о Корре", "category": "cartoons", "aliases": ["Korra", "Корра"]},
    {"slug": "rwby", "name": "RWBY", "category": "cartoons", "aliases": ["RWBY"]},
    {"slug": "steven-universe", "name": "Вселенная Стивена", "category": "cartoons", "aliases": ["Steven Universe"]},
    {"slug": "adventure-time", "name": "Время приключений", "category": "cartoons", "aliases": ["Adventure Time"]},
    {"slug": "gravity-falls", "name": "Гравити Фолз", "category": "cartoons", "aliases": ["Gravity Falls", "Диппер", "Мейбл"]},
    {"slug": "rick-and-morty", "name": "Рик и Морти", "category": "cartoons", "aliases": ["Rick and Morty"]},
    {"slug": "bojack-horseman", "name": "Конь БоДжек", "category": "cartoons", "aliases": ["BoJack Horseman"]},
    {"slug": "owl-house", "name": "Дом совы", "category": "cartoons", "aliases": ["Owl House", "Луз"]},
    {"slug": "she-ra", "name": "Ши-Ра и принцессы власти", "category": "cartoons", "aliases": ["She-Ra", "Адора", "Катра"]},
    {"slug": "hazbin-hotel", "name": "Hazbin Hotel", "category": "cartoons", "aliases": ["Hazbin Hotel", "Чарли"]},
    {"slug": "helluva-boss", "name": "Helluva Boss", "category": "cartoons", "aliases": ["Helluva Boss"]},
    {"slug": "encanto", "name": "Энканто", "category": "cartoons", "aliases": ["Encanto", "Мирабель"]},
    {"slug": "frozen", "name": "Холодное сердце", "category": "cartoons", "aliases": ["Frozen", "Эльза", "Анна"]},

    # ===== comics (~9) =====
    {"slug": "batman-comics", "name": "Бэтмен (комиксы)", "category": "comics", "aliases": ["Batman", "Брюс Уэйн"]},
    {"slug": "superman-comics", "name": "Супермен (комиксы)", "category": "comics", "aliases": ["Superman", "Кларк Кент"]},
    {"slug": "spider-man-comics", "name": "Человек-паук (комиксы)", "category": "comics", "aliases": ["Spider-Man", "Питер Паркер"]},
    {"slug": "x-men", "name": "Люди Икс", "category": "comics", "aliases": ["X-Men", "Росомаха"]},
    {"slug": "avengers-comics", "name": "Мстители (комиксы)", "category": "comics", "aliases": ["Avengers"]},
    {"slug": "watchmen", "name": "Хранители (Watchmen)", "category": "comics", "aliases": ["Watchmen", "Роршах"]},
    {"slug": "sandman", "name": "Песочный человек (Sandman)", "category": "comics", "aliases": ["Sandman", "Гейман"]},
    {"slug": "saga-comics", "name": "Сага (Saga)", "category": "comics", "aliases": ["Saga", "Воэн"]},
    {"slug": "invincible", "name": "Неуязвимый (Invincible)", "category": "comics", "aliases": ["Invincible", "Марк Грейсон"]},

    # ===== games (~22) =====
    {"slug": "dragon-age", "name": "Dragon Age", "category": "games", "aliases": ["Dragon Age", "Тедас"]},
    {"slug": "fallout", "name": "Fallout", "category": "games", "aliases": ["Fallout", "Пустошь"]},
    {"slug": "cyberpunk-2077", "name": "Cyberpunk 2077", "category": "games", "aliases": ["Cyberpunk", "Найт-Сити", "Ви"]},
    {"slug": "detroit-become-human", "name": "Detroit: Become Human", "category": "games", "aliases": ["Detroit", "Коннор"]},
    {"slug": "life-is-strange", "name": "Life is Strange", "category": "games", "aliases": ["LiS", "Макс", "Хлоя"]},
    {"slug": "dark-souls", "name": "Dark Souls", "category": "games", "aliases": ["Dark Souls", "Лордран"]},
    {"slug": "elden-ring", "name": "Elden Ring", "category": "games", "aliases": ["Elden Ring", "Меж", "Танущий"]},
    {"slug": "bloodborne", "name": "Bloodborne", "category": "games", "aliases": ["Bloodborne", "Ярнам"]},
    {"slug": "persona-5", "name": "Persona 5", "category": "games", "aliases": ["Persona 5", "P5"]},
    {"slug": "resident-evil", "name": "Resident Evil", "category": "games", "aliases": ["Resident Evil", "Леон"]},
    {"slug": "silent-hill", "name": "Silent Hill", "category": "games", "aliases": ["Silent Hill"]},
    {"slug": "bioshock", "name": "Bioshock", "category": "games", "aliases": ["Bioshock", "Восторг"]},
    {"slug": "portal", "name": "Portal", "category": "games", "aliases": ["Portal", "GLaDOS", "Шелл"]},
    {"slug": "half-life", "name": "Half-Life", "category": "games", "aliases": ["Half Life", "Гордон"]},
    {"slug": "overwatch", "name": "Overwatch", "category": "games", "aliases": ["Overwatch", "OW"]},
    {"slug": "league-of-legends", "name": "League of Legends", "category": "games", "aliases": ["LoL", "League"]},
    {"slug": "valorant", "name": "Valorant", "category": "games", "aliases": ["Valorant"]},
    {"slug": "apex-legends", "name": "Apex Legends", "category": "games", "aliases": ["Apex"]},
    {"slug": "hollow-knight", "name": "Hollow Knight", "category": "games", "aliases": ["Hollow Knight", "Халлоунест"]},
    {"slug": "honkai-star-rail", "name": "Honkai: Star Rail", "category": "games", "aliases": ["HSR", "Honkai Star Rail"]},
    {"slug": "final-fantasy", "name": "Final Fantasy", "category": "games", "aliases": ["FF", "Final Fantasy"]},
    {"slug": "stardew-valley", "name": "Stardew Valley", "category": "games", "aliases": ["Stardew"]},

    # ===== musicals (~3) =====
    {"slug": "hamilton-musical", "name": "Гамильтон (мюзикл)", "category": "musicals", "aliases": ["Hamilton", "Лин-Мануэль"]},
    {"slug": "phantom-of-the-opera", "name": "Призрак Оперы (мюзикл)", "category": "musicals", "aliases": ["Phantom of the Opera"]},
    {"slug": "les-miserables", "name": "Отверженные (мюзикл)", "category": "musicals", "aliases": ["Les Mis", "Les Miserables"]},

    # ===== rpf (~3) =====
    {"slug": "kpop-rpf", "name": "K-pop (RPF)", "category": "rpf", "aliases": ["BTS", "K-pop", "BlackPink", "Stray Kids"]},
    {"slug": "football-rpf", "name": "Футбол (RPF)", "category": "rpf", "aliases": ["RPS Football", "RPF"]},
    {"slug": "hollywood-rpf", "name": "Голливуд (RPF)", "category": "rpf", "aliases": ["Hollywood RPF", "Actors RPF"]},

    # ===== originals (~3) =====
    {"slug": "originals-fantasy", "name": "Ориджиналы — фэнтези", "category": "originals", "aliases": ["OC fantasy", "Original fantasy"]},
    {"slug": "originals-romance", "name": "Ориджиналы — романтика", "category": "originals", "aliases": ["OC romance"]},
    {"slug": "originals-scifi", "name": "Ориджиналы — фантастика", "category": "originals", "aliases": ["Sci-Fi original", "OC scifi"]},
]


def upgrade() -> None:
    bind = op.get_bind()

    # 1) pg_trgm + GIN индекс на name (для быстрых ILIKE и trigram-сравнений).
    # На managed PG (RDS/Cloud SQL) CREATE EXTENSION может требовать superuser.
    # Если право недоступно — расширение не создастся, и индекс ниже тоже упадёт.
    # Это не блокер: ILIKE работает и без gin_trgm_ops, просто медленнее на больших
    # объёмах. Поэтому ловим ошибку и продолжаем — миграция всё равно успешна.
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_fandoms_name_trgm "
            "ON fandoms USING gin (name gin_trgm_ops);"
        )
    except Exception:  # noqa: BLE001 — extension может быть запрещена в managed-БД
        pass

    # 2) movies → films (точечно).
    bind.execute(
        sa.text("UPDATE fandoms SET category='films' WHERE slug = ANY(:slugs)"),
        {"slugs": _MOVIES_TO_FILMS_SLUGS},
    )

    # 3) ошибочно помеченные movies → series.
    bind.execute(
        sa.text("UPDATE fandoms SET category='series' WHERE slug = ANY(:slugs)"),
        {"slugs": _TO_SERIES_SLUGS},
    )

    # 4) Опечатка в seed 0004: 'genshin-anime' это на самом деле Demon Slayer.
    #    Переименовываем slug + name + aliases. Делаем только если запись существует
    #    и при этом 'demon-slayer' свободен (на случай повторного отката/наката).
    bind.execute(
        sa.text(
            """
            UPDATE fandoms
            SET slug='demon-slayer',
                name='Истребитель демонов (Kimetsu no Yaiba)',
                aliases = ARRAY['Demon Slayer','Kimetsu no Yaiba','Kimetsu','Танджиро','Незуко']
            WHERE slug='genshin-anime'
              AND NOT EXISTS (SELECT 1 FROM fandoms WHERE slug='demon-slayer')
            """
        )
    )

    # 5) Заливаем новые фандомы (идемпотентно).
    for f in NEW_FANDOMS:
        bind.execute(
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
    bind = op.get_bind()

    # Удаляем только то, что добавила эта миграция (идентифицируем по slug).
    slugs = [f["slug"] for f in NEW_FANDOMS]
    bind.execute(
        sa.text("DELETE FROM fandoms WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )

    # Откат опечатки: если есть demon-slayer и нет genshin-anime — вернём.
    bind.execute(
        sa.text(
            """
            UPDATE fandoms
            SET slug='genshin-anime',
                name='Demon Slayer (Kimetsu no Yaiba)',
                aliases = ARRAY['Demon Slayer','Kimetsu','Танджиро']
            WHERE slug='demon-slayer'
              AND NOT EXISTS (SELECT 1 FROM fandoms WHERE slug='genshin-anime')
            """
        )
    )

    # Откатываем films→movies (для записей, которые мы переключили).
    bind.execute(
        sa.text("UPDATE fandoms SET category='movies' WHERE slug = ANY(:slugs)"),
        {"slugs": _MOVIES_TO_FILMS_SLUGS},
    )

    # Откатываем series→movies для затронутых.
    bind.execute(
        sa.text("UPDATE fandoms SET category='movies' WHERE slug = ANY(:slugs)"),
        {"slugs": _TO_SERIES_SLUGS},
    )

    op.execute("DROP INDEX IF EXISTS ix_fandoms_name_trgm;")
    # pg_trgm обычно не удаляем — extension может использоваться другими.
