"""TaskIQ-задачи уведомлений подписчикам.

Маршрут:
- `notify_new_chapter(author_id, fic_id, chapter_id)` — fanout-раздатчик.
- `notify_new_work(author_id, fic_id)` — fanout-раздатчик.
- `deliver_notification(user_id, notification_id, kind, payload_json)` — фактическая
  отправка одному получателю. 403 Forbidden — silent skip (юзер заблокировал бота).
- `notify_moderation_decision(user_id, report_id)` — уведомление репортеру об
  обработанной жалобе (dismiss/action). Читает `reports.*` и `notifications.*`.

Rate-limit: локальный на процесс через Redis-bucket `tb:notifications`
(25 msg/s, capacity 25). Не перекрывается с broadcast-лимитом.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from redis.asyncio import Redis

from app.application.reports.ports import IReportRepository
from app.application.shared.ports import UnitOfWork
from app.application.subscriptions.notify_subscribers import (
    NOTIF_KIND_NEW_CHAPTER,
    NOTIF_KIND_NEW_WORK,
    NotifySubscribersCommand,
    NotifySubscribersUseCase,
)
from app.application.subscriptions.ports import INotificationRepository
from app.core.logging import get_logger
from app.domain.shared.types import NotificationId, ReportId, UserId
from app.infrastructure.redis.token_bucket import TokenBucket
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broker

log = get_logger(__name__)

_NOTIF_BUCKET_KEY = "tb:notifications"
_NOTIF_RATE_PER_SEC = 25.0
_NOTIF_CAPACITY = 25

NOTIF_KIND_REPORT_PROCESSED = "report_processed"
NOTIF_KIND_FIC_ARCHIVED_BY_REPORT = "fic_archived_by_report"


# ---------- fanout раздатчики ----------


@broker.task(task_name="notify_new_chapter")
async def notify_new_chapter(author_id: int, fic_id: int, chapter_id: int) -> int:
    container = get_worker_container()
    async with container() as scope:
        uc = await scope.get(NotifySubscribersUseCase)
        result = await uc(
            NotifySubscribersCommand(
                author_id=int(author_id),
                fic_id=int(fic_id),
                chapter_id=int(chapter_id),
                kind=NOTIF_KIND_NEW_CHAPTER,
            )
        )
        return int(result.notifications_created)


@broker.task(task_name="notify_new_work")
async def notify_new_work(author_id: int, fic_id: int) -> int:
    container = get_worker_container()
    async with container() as scope:
        uc = await scope.get(NotifySubscribersUseCase)
        result = await uc(
            NotifySubscribersCommand(
                author_id=int(author_id),
                fic_id=int(fic_id),
                chapter_id=None,
                kind=NOTIF_KIND_NEW_WORK,
            )
        )
        return int(result.notifications_created)


# ---------- доставка одного сообщения ----------


@dataclass(frozen=True)
class _DeliveredText:
    text: str
    reply_markup: InlineKeyboardMarkup | None


def _build_delivery(kind: str, payload: dict[str, Any]) -> _DeliveredText:
    fic_id = int(payload.get("fic_id") or 0)
    fic_title = str(payload.get("fic_title") or "").strip() or "работа"

    if kind == NOTIF_KIND_NEW_CHAPTER:
        ch_number = payload.get("chapter_number")
        ch_title = str(payload.get("chapter_title") or "").strip()
        parts = [f"📖 Новая глава работы «{fic_title}»"]
        if ch_number is not None:
            if ch_title:
                parts.append(f"Глава {int(ch_number)}. {ch_title}")
            else:
                parts.append(f"Глава {int(ch_number)}")
        text = "\n\n".join(parts)
        kb = _read_button(fic_id) if fic_id else None
        return _DeliveredText(text=text, reply_markup=kb)

    if kind == NOTIF_KIND_NEW_WORK:
        text = f"✨ Новая работа от автора, на которого ты подписан(а): «{fic_title}»"
        kb = _read_button(fic_id) if fic_id else None
        return _DeliveredText(text=text, reply_markup=kb)

    if kind == NOTIF_KIND_REPORT_PROCESSED:
        decision = str(payload.get("decision") or "")
        if decision == "action":
            text = "Твоя жалоба рассмотрена: контент удалён или скрыт. Спасибо за сигнал."
        else:
            text = (
                "Твоя жалоба рассмотрена — модератор не нашёл нарушений. Если ты "
                "считаешь, что решение ошибочно, можешь отправить новую жалобу с "
                "более подробным описанием."
            )
        return _DeliveredText(text=text, reply_markup=None)

    if kind == NOTIF_KIND_FIC_ARCHIVED_BY_REPORT:
        reason_code = str(payload.get("reason_code") or "")
        reason_line = f"\nКатегория: {reason_code}" if reason_code else ""
        mod_comment = str(payload.get("moderator_comment") or "").strip()
        comment_line = f"\n\nКомментарий модератора: {mod_comment}" if mod_comment else ""
        text = (
            f"⚠️ Твоя работа «{fic_title}» скрыта после рассмотрения жалобы "
            f"модератором.{reason_line}{comment_line}\n\n"
            "Если это ошибка — напиши админу. Перед повторной публикацией "
            "проверь, что работа соответствует правилам /rules."
        )
        return _DeliveredText(text=text, reply_markup=None)

    # Неизвестный kind — кидаем минимум, чтобы не ронять job'у.
    return _DeliveredText(text=f"Уведомление: {fic_title}", reply_markup=None)


def _read_button(fic_id: int) -> InlineKeyboardMarkup:
    # Пока используем текстовый callback, как на карточке ленты. deep-link
    # через `fic_<id>` делает start-роутер; здесь кликом внутри бота достаточно
    # обычного callback_data — юзер уже в чате с ботом.
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Читать",
                    callback_data=f"rn:open:{fic_id}:0:0",
                )
            ]
        ]
    )


@broker.task(task_name="deliver_notification")
async def deliver_notification(
    user_id: int, notification_id: int, kind: str, payload_json: str
) -> bool:
    """Отправить уведомление одному пользователю.

    Возвращает True если отправили, False если silent-skip (403/unknown error).
    """
    payload: dict[str, Any] = json.loads(payload_json) if payload_json else {}
    delivery = _build_delivery(kind, payload)

    container = get_worker_container()
    async with container() as scope:
        bot = await scope.get(Bot)
        bucket = await scope.get(TokenBucket)
        notifs = await scope.get(INotificationRepository)
        uow = await scope.get(UnitOfWork)

        await bucket.acquire(_NOTIF_BUCKET_KEY, _NOTIF_RATE_PER_SEC, _NOTIF_CAPACITY)
        try:
            await bot.send_message(
                chat_id=int(user_id),
                text=delivery.text,
                reply_markup=delivery.reply_markup,
            )
        except TelegramForbiddenError:
            # Юзер заблокировал бота. Не retry, молча пропускаем.
            log.info(
                "notification_blocked",
                user_id=int(user_id),
                notification_id=int(notification_id),
                kind=kind,
            )
            return False
        except TelegramRetryAfter:
            # Поднимаем — TaskIQ сам retry-нёт (при настройке retry-middleware),
            # либо упадёт в dead-letter. В любом случае не дедлокать воркер sleep'ом.
            raise
        except TelegramAPIError as e:
            log.warning(
                "notification_failed",
                user_id=int(user_id),
                notification_id=int(notification_id),
                kind=kind,
                error=str(e),
            )
            return False

        async with uow:
            await notifs.mark_sent(
                notification_id=NotificationId(int(notification_id)),
                now=datetime.now(UTC),
            )
            await uow.commit()
    return True


# ---------- уведомление репортеру об обработке жалобы ----------


@broker.task(task_name="notify_moderation_decision")
async def notify_moderation_decision(user_id: int, report_id: int) -> bool:
    """Отправить репортеру уведомление об обработке его жалобы.

    Читает `report.id` → достаёт target_id / decision / notify_reporter;
    создаёт запись в `notifications` и сразу триггерит доставку.

    Возвращает True если уведомление было создано и отправлено; False если
    notify_reporter=False или отправка не удалась.
    """
    container = get_worker_container()
    async with container() as scope:
        reports = await scope.get(IReportRepository)
        notifs = await scope.get(INotificationRepository)
        uow = await scope.get(UnitOfWork)

        async with uow:
            report = await reports.get(ReportId(int(report_id)))
            if report is None or not report.notify_reporter:
                await uow.commit()
                return False

            payload: dict[str, Any] = {
                "report_id": int(report.id),
                "target_type": report.target_type.value,
                "target_id": int(report.target_id),
                "decision": report.status.value,  # 'dismissed' | 'actioned'
            }
            now = datetime.now(UTC)
            notif_id = await notifs.create(
                user_id=UserId(int(report.reporter_id)),
                kind=NOTIF_KIND_REPORT_PROCESSED,
                payload=payload,
                now=now,
            )
            await uow.commit()

    # Доставка — отдельной задачей (бенефит: общий token-bucket + единый трекинг).
    await deliver_notification.kiq(
        int(report.reporter_id),
        int(notif_id),
        NOTIF_KIND_REPORT_PROCESSED,
        json.dumps(payload, ensure_ascii=False),
    )
    return True


# ---------- уведомление автору о том, что его фик скрыт по жалобе ----------


@broker.task(task_name="notify_author_fic_archived")
async def notify_author_fic_archived(
    author_id: int,
    fic_id: int,
    fic_title: str,
    report_id: int,
    reason_code: str | None,
    moderator_comment: str | None,
) -> bool:
    """Создать и отправить уведомление автору архивированного фика.

    Вызывается outbox-диспетчером при событии `fanfic.archived_by_report`.
    """
    payload: dict[str, Any] = {
        "fic_id": int(fic_id),
        "fic_title": str(fic_title),
        "report_id": int(report_id),
        "reason_code": reason_code,
        "moderator_comment": moderator_comment,
    }
    container = get_worker_container()
    async with container() as scope:
        notifs = await scope.get(INotificationRepository)
        uow = await scope.get(UnitOfWork)
        async with uow:
            notif_id = await notifs.create(
                user_id=UserId(int(author_id)),
                kind=NOTIF_KIND_FIC_ARCHIVED_BY_REPORT,
                payload=payload,
                now=datetime.now(UTC),
            )
            await uow.commit()
    await deliver_notification.kiq(
        int(author_id),
        int(notif_id),
        NOTIF_KIND_FIC_ARCHIVED_BY_REPORT,
        json.dumps(payload, ensure_ascii=False),
    )
    return True
