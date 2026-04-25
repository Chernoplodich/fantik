"""CallbackData админской панели фандомов (двухступенчатая навигация).

Заменяет legacy `FandomAdminCD(prefix="fd")` на единый класс с короткими полями.
Лимит callback_data — 64 байта; самый длинный код категории `originals` (9 chars).
Worst-case `fa:rename:originals:0:9999999` ≈ 31 байт — укладываемся.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class FdAdmCD(CallbackData, prefix="fa"):
    """Callback админ-фандомов.

    Поля сокращены, чтобы не бить лимит 64 байта:
    - `a` — действие;
    - `cat` — код категории (anime/books/films/...);
    - `fid` — fandom_id;
    - `pg` — страница в категории.

    Возможные значения `a`:
    - `root`        — список категорий;
    - `cat`         — список фандомов внутри категории (нужен `cat`, опц. `pg`);
    - `open`        — карточка фандома (нужны `fid`, `cat` для возврата);
    - `toggle`      — toggle active (нужны `fid`, `cat`);
    - `rename`      — старт FSM переименования (нужны `fid`, `cat`);
    - `aliases`     — старт FSM правки aliases (нужны `fid`, `cat`);
    - `search`      — старт FSM поиска (без аргументов);
    - `new`         — старт FSM создания (picker категорий);
    - `new_in`      — старт FSM создания с preset категорией (нужен `cat`);
    - `noop`        — заглушка для неактивных кнопок.
    """

    a: str
    cat: str = ""
    fid: int = 0
    pg: int = 0
