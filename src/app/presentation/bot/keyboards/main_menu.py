"""Главное меню (inline)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.domain.users.value_objects import Role


def build_rules_accept_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Принимаю правила", callback_data="rules:accept")
    b.adjust(1)
    return b.as_markup()


def build_main_menu_kb(*, role: Role, is_author: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📚 Каталог", callback_data="menu:browse")
    b.button(text="📖 Моя полка", callback_data="menu:shelf")
    if is_author:
        b.button(text="✍️ Мои работы", callback_data="menu:my_works")
        b.button(text="➕ Новая работа", callback_data="menu:new_fic")
    else:
        b.button(text="✍️ Стать автором", callback_data="menu:become_author")
    b.button(text="👤 Профиль", callback_data="menu:profile")

    # mod+admin: считаем количество служебных кнопок и кладём их в один ряд.
    # Базовая раскладка: 2 каталог+полка, 2 авторские (или 1 «Стать автором»),
    # 1 профиль. Чтобы корректно работало для USER (без авторства) — учитываем
    # фактическое количество кнопок до служебных.
    sizes: list[int] = []
    sizes.append(2)  # каталог + полка
    if is_author:
        sizes.append(2)  # мои работы + новая работа
    else:
        sizes.append(1)  # «Стать автором»
    sizes.append(1)  # профиль

    extras = 0
    if role in (Role.MODERATOR, Role.ADMIN):
        b.button(text="🛡 Модерация", callback_data="menu:mod")
        extras += 1
    if role is Role.ADMIN:
        b.button(text="⚙️ Админ", callback_data="menu:admin")
        extras += 1
    if extras:
        sizes.append(extras)  # обе вместе одной строкой при ADMIN, одна — при MODERATOR
    b.adjust(*sizes)
    return b.as_markup()


def build_profile_kb(*, is_author: bool) -> InlineKeyboardMarkup:
    """Клавиатура карточки профиля. Без кнопки «Профиль» — она и так открыта."""
    b = InlineKeyboardBuilder()
    if not is_author:
        b.button(text="✍️ Стать автором", callback_data="menu:become_author")
    b.button(text="← Главное меню", callback_data="menu:back")
    b.adjust(1)
    return b.as_markup()
