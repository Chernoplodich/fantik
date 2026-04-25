"""Регрессия: пользователь не должен залипать в FSM-state'ах поиска.

1. `cmd_start` сбрасывает FSM (any state) — после `/start` юзер всегда
   получает чистый контекст. Иначе после нажатия «🔍 Найти» state
   `entering_fandom_search` остаётся в Redis и следующее сообщение
   попадает в обработчик поиска фандомов.
2. Текстовые handler'ы поиска (browse / author_create / author_manage)
   игнорируют сообщения, начинающиеся с `/` (команды), и сбрасывают state —
   страховка на случай, если cmd_start не успел сработать первым.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.presentation.bot.fsm.states.create_fanfic import CreateFanficStates
from app.presentation.bot.fsm.states.search import SearchFiltersFSM

from ._flow_helpers import make_message, make_state, unwrap


@pytest.mark.asyncio
class TestSearchTextHandlersIgnoreCommands:
    async def test_q_handler_ignores_slash_command_and_clears_state(self) -> None:
        from app.presentation.bot.routers import browse as br

        on_query_text = unwrap(br.on_query_text)
        state = make_state()
        await state.set_state(SearchFiltersFSM.entering_query)
        await state.update_data(s_q="старое")
        msg = make_message(text="/start")

        ref = AsyncMock()
        search_uc = AsyncMock()
        await on_query_text(msg, state, ref, search_uc)

        assert await state.get_state() is None  # state.clear()
        msg.answer.assert_not_awaited()  # ничего не пишем — пусть cmd_start ответит
        search_uc.assert_not_awaited()

    async def test_fandom_search_ignores_slash_command(self) -> None:
        from app.presentation.bot.routers import browse as br

        on_fandom_search_text = unwrap(br.on_fandom_search_text)
        state = make_state()
        await state.set_state(SearchFiltersFSM.entering_fandom_search)
        msg = make_message(text="/start")

        # reference не должен вызываться — handler должен выйти раньше.
        ref = AsyncMock()
        await on_fandom_search_text(msg, state, ref)

        assert await state.get_state() is None
        ref.search_fandoms.assert_not_awaited()
        msg.answer.assert_not_awaited()

    async def test_author_create_fandom_search_ignores_slash(self) -> None:
        from app.presentation.bot.routers import author_create as ac

        on_search = unwrap(ac.on_fandom_search_text)
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_fandom_search)
        msg = make_message(text="/help")

        ref = AsyncMock()
        await on_search(msg, state, ref)

        assert await state.get_state() is None
        ref.search_fandoms.assert_not_awaited()

    async def test_author_create_propose_name_ignores_slash(self) -> None:
        from app.presentation.bot.routers import author_create as ac

        state = make_state()
        await state.set_state(CreateFanficStates.waiting_fandom_proposal_name)
        msg = make_message(text="/start")

        await ac.on_fandom_propose_name(msg, state)

        assert await state.get_state() is None
        msg.answer.assert_not_awaited()


@pytest.mark.asyncio
class TestSearchHandlerErrorRecovery:
    """Если SQL/connection падает — handler даёт понятное сообщение, а не
    `Exception → errors_router → "что-то пошло не так"`. Без этой защиты
    любая ошибка БД выглядит для пользователя как баг бота."""

    async def test_search_handler_reports_friendly_error_on_exception(self) -> None:
        from app.presentation.bot.routers import browse as br

        on_fandom_search_text = unwrap(br.on_fandom_search_text)
        state = make_state()
        await state.set_state(SearchFiltersFSM.entering_fandom_search)
        msg = make_message(text="наруто")

        ref = AsyncMock()
        ref.search_fandoms.side_effect = RuntimeError("boom")

        await on_fandom_search_text(msg, state, ref)

        # Пользователь видит человеческое сообщение, не SQL-стек.
        msg.answer.assert_awaited()
        sent_text = msg.answer.call_args.args[0] if msg.answer.call_args.args else ""
        assert "Не получилось" in sent_text or "ошибка" in sent_text.lower()
