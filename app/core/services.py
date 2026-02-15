import asyncio
import json
import logging
import uuid

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

from app.config import config
from app.core.models import IncomingPost
from app.filters.rp_filter import RPFilter
from app.formatters.news_formatter import NewsFormatter
from app.moderation.keyboards import moderation_keyboard
from app.parsers.translator import AutoTranslator
from app.storage.database import Database
from app.utils.text_tools import content_hash, strip_hashtags

logger = logging.getLogger(__name__)


class NewsService:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.rp_filter = RPFilter()
        self.formatter = NewsFormatter()
        self.translator = AutoTranslator()
        self.queue: asyncio.Queue[IncomingPost] = asyncio.Queue(maxsize=2000)

    async def is_paused(self) -> bool:
        return await self.db.get_state("paused", "0") == "1"

    async def set_paused(self, paused: bool) -> None:
        await self.db.set_state("paused", "1" if paused else "0")

    async def enqueue(self, post: IncomingPost) -> None:
        await self.queue.put(post)

    async def worker(self) -> None:
        while True:
            post = await self.queue.get()
            try:
                await self.process_post(post)
            except Exception:
                logger.exception("Unhandled error on post processing")
            finally:
                self.queue.task_done()

    async def process_post(self, post: IncomingPost) -> None:
        if await self.is_paused():
            logger.info("Paused; skip post %s/%s", post.source_channel, post.message_id)
            return

        source_text = (post.text or "").strip()
        if not source_text:
            logger.info("Empty message skip: %s/%s", post.source_channel, post.message_id)
            return

        hash_value = content_hash(f"{post.source_channel}:{strip_hashtags(source_text)}")
        if await self.db.is_duplicate(hash_value):
            logger.info("Duplicate skip: %s", hash_value)
            return

        translated = await self.translator.to_russian(source_text)
        filter_result = self.rp_filter.check(translated)

        if not filter_result.allowed:
            logger.info(
                "Blocked by RP filter %s: %s/%s",
                filter_result.reason,
                post.source_channel,
                post.message_id,
            )
            if post.has_media:
                await self.send_to_moderation(post, translated, filter_result.reason)
            return

        hashtag = config.country_hashtags.get(post.source_country, "")
        if not hashtag:
            await self.bot.send_message(
                config.admin_id,
                f"Нет хештега для страны {post.source_country}. Нужна ручная проверка.",
            )
            await self.send_to_moderation(post, translated, "MISSING_HASHTAG")
            return

        rewritten = self.formatter.rewrite(post.source_country, translated)
        formatted = self.formatter.format_news(post.source_country, hashtag, rewritten)

        if post.has_media:
            await self.send_to_moderation(post, formatted, "MEDIA_REQUIRES_MANUAL_REVIEW")
            return

        if config.publish_delay_seconds > 0:
            await asyncio.sleep(min(config.publish_delay_seconds, 3.0))

        await self.publish_and_mark(post, formatted, hash_value)

    async def publish_and_mark(self, post: IncomingPost, formatted: str, hash_value: str) -> None:
        try:
            await self.bot.send_message(
                chat_id=config.target_channel,
                text=formatted,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
            await self.db.mark_processed(post.source_channel, post.message_id, hash_value)
            logger.info("Published %s/%s", post.source_channel, post.message_id)
        except TelegramBadRequest:
            logger.exception("Publish failed")

    async def send_to_moderation(self, post: IncomingPost, text: str, reason: str) -> None:
        token = uuid.uuid4().hex
        payload = {
            "source_country": post.source_country,
            "source_channel": post.source_channel,
            "message_id": post.message_id,
            "formatted_text": text,
            "has_media": post.has_media,
        }
        await self.db.store_moderation_payload(token, json.dumps(payload, ensure_ascii=False))

        await self.bot.send_message(
            config.admin_id,
            (
                "Пост отправлен на модерацию\n"
                f"Причина: {reason}\n"
                f"Источник: {post.source_country} ({post.source_channel})\n"
                f"ID: {post.message_id}\n\n"
                f"Текст:\n{text[:3000]}"
            ),
            reply_markup=moderation_keyboard(token),
        )
