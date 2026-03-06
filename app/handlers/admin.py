import json
import logging
import re
import time
from datetime import datetime

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


class ScheduleState(StatesGroup):
    waiting_payload = State()


class MapState(StatesGroup):
    waiting_media = State()


def _extract_media(message: Message) -> tuple[str | None, str | None]:
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.video:
        return message.video.file_id, "video"
    if message.animation:
        return message.animation.file_id, "animation"
    if message.document:
        return message.document.file_id, "document"
    return None, None


def _extract_hashtags(text: str) -> set[str]:
    return {f"#{m.upper()}" for m in re.findall(r"#([A-Za-zА-Яа-я0-9_]+)", text)}


def _detect_claimed_country(text: str) -> str:
    tags = _extract_hashtags(text)
    for country, country_tags in config.country_hashtags.items():
        upper_tags = {tag.upper() for tag in country_tags}
        if tags & upper_tags:
            return country
    return "MANUAL"


def _is_author_allowed_for_country(country: str, user_id: int) -> bool:
    allowed_ids = config.manual_country_authors.get(country)
    if not allowed_ids:
        return True
    return user_id in allowed_ids or user_id == config.admin_id


def bind_admin_handlers(service: NewsService) -> Router:
    @router.message(Command("start"))
    async def start_cmd(message: Message) -> None:
        await message.answer(
            "Бот активен.\n"
            "Команды: /status /pause /resume /write_news /schedule_news /submit_map /rss_add /rss_list /emoji_reload /emoji_list\n\n"
            "Для /write_news обязательно укажите хештег страны (например #OBS).\n"
            "Хештеги публикуются в английском формате.\n"
            "Новость не должна нарушать RP-правила, иначе будет отклонена."
        )

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
            "Отправьте текст/медиа новости.\n"
            "Требования:\n"
            "1) Обязательно добавьте хештег страны (#OBS / #OB / #VL и т.д.)\n"
            "2) Не нарушайте RP-правила\n"
            "3) Медиа всегда уходит на модерацию\n"
            "4) Нельзя отправлять новости от лица чужой страны"
        )

    @router.message(WriteNewsState.waiting_text)
    async def write_news_flow(message: Message, state: FSMContext) -> None:
        text = (message.caption or message.text or "").strip()
        if not text and not (message.photo or message.video or message.animation):
            await message.answer("Пустой текст")
            return

        if "#" not in text:
            await message.answer("Нужен хештег страны (пример: #OBS). Новость не принята.")
            return

        claimed_country = _detect_claimed_country(text)
        if claimed_country == "MANUAL":
            await message.answer("Не найден валидный хештег страны. Используйте английские теги (например #OBS, #OB, #VL).")
            return

        user_id = message.from_user.id if message.from_user else 0
        if not _is_author_allowed_for_country(claimed_country, user_id):
            await message.answer("Вы не можете публиковать новости от лица этой страны.")
            return

        file_id, media_type = _extract_media(message)
        post = IncomingPost(
            source_country=claimed_country,
            source_channel="manual_admin",
            message_id=message.message_id,
            text=text,
            has_media=bool(file_id),
            media_file_id=file_id,
            media_type=media_type,
        )
        await service.enqueue(post)
        await state.clear()
        await message.answer("Принято в очередь")

    @router.message(Command("schedule_news"))
    async def schedule_news_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(ScheduleState.waiting_payload)
        await message.answer("Формат: YYYY-mm-dd HH:MM | COUNTRY | TEXT")

    @router.message(ScheduleState.waiting_payload)
    async def schedule_news_flow(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        try:
            at_str, country, text = [x.strip() for x in raw.split("|", maxsplit=2)]
            ts = int(datetime.strptime(at_str, "%Y-%m-%d %H:%M").timestamp())
            post_id = await service.db.add_scheduled_post(ts, country, text, message.from_user.id if message.from_user else 0)
            await message.answer(f"Запланировано: id={post_id}")
            await state.clear()
        except Exception:
            await message.answer("Неверный формат. Пример: 2026-02-21 19:30 | Вилония | Текст")


    @router.message(Command("emoji_reload"))
    async def emoji_reload_cmd(message: Message) -> None:
        if message.from_user and message.from_user.id != config.admin_id:
            await message.answer("Недостаточно прав")
            return
        count = await service.refresh_emoji_packs()
        await message.answer(f"Emoji packs reloaded: {count}")

    @router.message(Command("emoji_list"))
    async def emoji_list_cmd(message: Message) -> None:
        if not service.pack_emoji_cache:
            await message.answer("Emoji cache пуст. Используйте /emoji_reload")
            return
        sample = list(service.pack_emoji_cache.items())[:50]
        lines = [f"{k} -> {v}" for k, v in sample]
        await message.answer("\n".join(lines))

    @router.message(Command("rss_add"))
    async def rss_add_cmd(message: Message) -> None:
        if not message.text:
            return
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Использование: /rss_add KEY https://feed.url")
            return
        key, url = parts[1], parts[2]
        config.rss_feeds[key] = url
        await message.answer(f"RSS добавлен: {key}")

    @router.message(Command("rss_list"))
    async def rss_list_cmd(message: Message) -> None:
        if not config.rss_feeds:
            await message.answer("RSS пуст")
            return
        lines = [f"{k}: {u}" for k, u in config.rss_feeds.items()]
        await message.answer("\n".join(lines))

    @router.message(Command("submit_map"))
    async def submit_map_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(MapState.waiting_media)
        await message.answer("Отправьте фото/файл карты и подпись комментария.")

    @router.message(MapState.waiting_media)
    async def submit_map_flow(message: Message, state: FSMContext) -> None:
        file_id, media_type = _extract_media(message)
        comment = (message.caption or message.text or "Военная сводка").strip()
        await service.publish_map_digest(file_id, media_type or "none", comment)
        await message.answer("Карта и сводка опубликованы")
        await state.clear()

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
            has_media=payload.get("has_media", False),
            media_file_id=payload.get("media_file_id"),
            media_type=payload.get("media_type"),
        )

        if action == "approve":
            if post.has_media:
                await service.publish_media_and_mark(post, payload["formatted_text"], hash_value)
            else:
                await service.publish_and_mark(post, payload["formatted_text"], None, hash_value)
            await callback.message.answer("Одобрено и опубликовано")
        else:
            await service.db.mark_processed(post.source_channel, post.message_id, hash_value)
            await callback.message.answer("Отклонено")

        await callback.answer()

    @router.message(F.from_user.as_("u"), F.text, ~F.text.startswith("/"))
    async def antiflood_guard(message: Message, u) -> None:  # type: ignore[no-redef]
        if not u:
            return
        ok, reason = await service.check_antiflood(u.id)
        if not ok:
            await message.answer(reason)

    return router
