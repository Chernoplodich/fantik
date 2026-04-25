"""Fake Telegram Bot API (aiohttp) для нагрузочных тестов.

Идея: бот запускается с `TG_API_BASE=http://fake-tg:9999`, все исходящие
API-вызовы уходят сюда. Этот сервер отвечает каноническим `{"ok": true,
"result": {...}}` на все методы без бизнес-логики — нам важна пропускная
способность нашего кода, а не Telegram.

Запуск:
    python -m tests.load.fake_tg_server
или через compose:
    docker compose --profile loadtest up fake-tg
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from aiohttp import web

log = logging.getLogger(__name__)


def _ok(result: Any = True) -> web.Response:
    return web.json_response({"ok": True, "result": result})


async def _handle(request: web.Request) -> web.Response:
    method = request.match_info["method"]
    # Для getMe — бот проверяет ответ при setWebhook и для username.
    if method == "getMe":
        return _ok(
            {
                "id": 1_111_111_111,
                "is_bot": True,
                "first_name": "FantikLoadBot",
                "username": "fantik_load_bot",
                "can_join_groups": True,
                "can_read_all_group_messages": False,
                "supports_inline_queries": True,
            }
        )
    if method == "getFile":
        # Отдаём имитацию пути; реальный download сыграет чуть ниже.
        return _ok(
            {"file_id": "fake", "file_unique_id": "fake", "file_size": 512, "file_path": "fake.png"}
        )
    if method in {
        "sendMessage",
        "editMessageText",
        "editMessageReplyMarkup",
        "sendPhoto",
        "copyMessage",
        "deleteMessage",
        "answerCallbackQuery",
        "answerInlineQuery",
        "setWebhook",
        "deleteWebhook",
        "setMyCommands",
        "setMyDescription",
        "setMyShortDescription",
    }:
        # Возвращаем валидный Message-like. Минимальный набор полей.
        return _ok(
            {
                "message_id": 1,
                "date": 0,
                "chat": {"id": 1, "type": "private"},
            }
        )
    # Для неизвестного метода — успех, чтобы не валить load-тест из-за
    # незначимого side-effect'а.
    log.debug("fake_tg_unknown_method", extra={"method": method})
    return _ok(True)


async def _file_download(request: web.Request) -> web.Response:
    # Заглушка скачивания файлов: 1x1 PNG.
    _png_1x1 = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
        b"\x89\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return web.Response(body=_png_1x1, content_type="image/png")


def build_app() -> web.Application:
    app = web.Application(client_max_size=10 * 1024 * 1024)
    app.router.add_route("*", "/bot{token}/{method}", _handle)
    app.router.add_get("/file/bot{token}/{path:.*}", _file_download)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("FAKE_TG_HOST", "0.0.0.0")  # noqa: S104 — specifically binds all ifaces
    port = int(os.environ.get("FAKE_TG_PORT", "9999"))
    web.run_app(build_app(), host=host, port=port, access_log=None, loop=asyncio.new_event_loop())


if __name__ == "__main__":
    main()
