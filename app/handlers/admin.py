import json
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.config import config
from app.core.models import IncomingPost
from app.core.services import NewsService
from app.utils.text_tools import content_hash

logger = logging.getLogger(__name__)

router = Router(name="admin")


class WriteNewsState(StatesGroup):
    waiting_text = State()


def bind_admin_handlers(service: NewsService) -> Router:
    @router.message(Command("start"))
    async def start_cmd(message: Message) -> None:
        await message.answer("Бот активен. Используйте /status, /pause, /resume, /write_news")

    @router.message(Command("status"))
    async def status_cmd(message: Message) -> None:
        paused = await service.is_paused()
        await message.answer(
            f"Статус: {'PAUSED' if paused else 'RUNNING'}\n"
            f"Очередь: {service.queue.qsize()}\n"
            f"Target: {config.target_channel}"
        )

    @router.message(Command("pause"))
    async def pause_cmd(message: Message) -> None:
        if message.from_user and message.from_user.id != config.admin_id:
            await message.answer("Недостаточно прав")
            return
        await service.set_paused(True)
        await message.answer("Пауза включена")

    @router.message(Command("resume"))
    async def resume_cmd(message: Message) -> None:
        if message.from_user and message.from_user.id != config.admin_id:
            await message.answer("Недостаточно прав")
            return
        await service.set_paused(False)
        await message.answer("Пауза отключена")

    @router.message(Command("write_news"))
    async def write_news_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(WriteNewsState.waiting_text)
        await message.answer(
            "Отправьте новость в формате:\n"
            "👀 **СТРАНА** *новость*\n\n"
            "✔️ *краткая суть*\n\n"
            "#ХЕШТЕГ"
        )

    @router.message(WriteNewsState.waiting_text)
    async def write_news_flow(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("Пустой текст")
            return

        if "#" not in text:
            await message.answer("Ошибка: нет хештега страны")
            return

        rp_check = service.rp_filter.check(text)
        if not rp_check.allowed:
            await message.answer(f"Ошибка проверки: {rp_check.reason}")
            return

        post = IncomingPost(
            source_country="MANUAL",
            source_channel="manual_admin",
            message_id=message.message_id,
            text=text,
            has_media=False,
        )

        hash_value = content_hash(f"manual:{text}")
        await service.publish_and_mark(post, text, hash_value)
        await state.clear()
        await message.answer("Новость опубликована")

    @router.callback_query(F.data.startswith("mod:"))
    async def moderation_callback(callback: CallbackQuery) -> None:
        if callback.from_user.id != config.admin_id:
            await callback.answer("Недостаточно прав", show_alert=True)
            return

        _, action, token = callback.data.split(":", maxsplit=2)
        payload_raw = await service.db.pop_moderation_payload(token)
        if not payload_raw:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        payload = json.loads(payload_raw)
        hash_value = content_hash(f"{payload['source_channel']}:{payload['message_id']}:{payload['formatted_text']}")
        post = IncomingPost(
            source_country=payload["source_country"],
            source_channel=payload["source_channel"],
            message_id=payload["message_id"],
            text=payload["formatted_text"],
            has_media=payload["has_media"],
        )

        if action == "approve":
            await service.publish_and_mark(post, payload["formatted_text"], hash_value)
            await callback.message.answer("Одобрено и опубликовано")
        else:
            await service.db.mark_processed(post.source_channel, post.message_id, hash_value)
            await callback.message.answer("Отклонено")

        await callback.answer()

    return router
