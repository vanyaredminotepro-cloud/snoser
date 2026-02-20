import asyncio
import json
import logging
import re
import time
import uuid
from collections import deque
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from app.config import config
from app.core.models import IncomingPost
from app.filters.ai_guard import AIGuard
from app.filters.rp_filter import RPFilter
from app.formatters.news_formatter import NewsFormatter
from app.moderation.keyboards import moderation_keyboard
from app.parsers.rss_parser import RSSParser
from app.parsers.translator import AutoTranslator
from app.storage.database import Database
from app.utils.text_tools import content_hash, strip_hashtags

logger = logging.getLogger(__name__)


class NewsService:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.rp_filter = RPFilter()
        self.ai_guard = AIGuard()
        self.formatter = NewsFormatter()
        self.translator = AutoTranslator()
        self.rss = RSSParser()
        self.queue: asyncio.Queue[IncomingPost] = asyncio.Queue(maxsize=3000)
        self.user_windows: dict[int, deque[int]] = {}

    async def is_paused(self) -> bool:
        return await self.db.get_state("paused", "0") == "1"

    async def set_paused(self, paused: bool) -> None:
        await self.db.set_state("paused", "1" if paused else "0")

    async def enqueue(self, post: IncomingPost) -> None:
        await self.queue.put(post)

    async def check_antiflood(self, user_id: int) -> tuple[bool, str]:
        now = int(time.time())
        if await self.db.is_user_blocked(user_id, now):
            return False, "Вы временно заблокированы за флуд"

        window = self.user_windows.setdefault(user_id, deque())
        while window and now - window[0] > config.antiflood_window_sec:
            window.popleft()
        window.append(now)

        if len(window) > config.antiflood_max_messages:
            blocked_until = now + 300
            strikes, _ = await self.db.add_strike(user_id, blocked_until_ts=blocked_until)
            return False, f"Антифлуд: лимит превышен. Страйков: {strikes}. Блок на 5 минут"
        return True, "OK"

    async def worker(self) -> None:
        while True:
            post = await self.queue.get()
            try:
                await self.process_post(post)
            except Exception:
                logger.exception("Unhandled error on post processing")
            finally:
                self.queue.task_done()

    async def scheduler_worker(self) -> None:
        while True:
            try:
                due = await self.db.get_due_scheduled_posts(int(time.time()))
                for post_id, source_country, text in due:
                    fake_id = int(time.time()) + post_id
                    await self.enqueue(
                        IncomingPost(
                            source_country=source_country,
                            source_channel="scheduled",
                            message_id=fake_id,
                            text=text,
                            has_media=False,
                        )
                    )
                    logger.info("Scheduled post queued id=%s", post_id)
            except Exception:
                logger.exception("Scheduler worker failed")
            await asyncio.sleep(max(1, config.scheduler_poll_seconds))

    async def rss_worker(self) -> None:
        if not config.rss_feeds:
            return

        while True:
            try:
                for key, url in config.rss_feeds.items():
                    seen_key = f"rss_seen:{key}"
                    seen = await self.db.get_state(seen_key, "")
                    items = await self.rss.fetch(key, url)
                    for item in reversed(items):
                        marker = content_hash(f"{item.title}|{item.link}")
                        if marker == seen:
                            continue
                        text = f"{item.title}\n\n{item.summary}\n{item.link}".strip()
                        await self.enqueue(
                            IncomingPost(
                                source_country="MANUAL",
                                source_channel=f"rss:{key}",
                                message_id=int(time.time()),
                                text=text,
                                has_media=False,
                            )
                        )
                        await self.db.set_state(seen_key, marker)
                        break
            except Exception:
                logger.exception("RSS worker failed")
            await asyncio.sleep(max(10, config.rss_poll_seconds))

    async def process_post(self, post: IncomingPost) -> None:
        if await self.is_paused():
            logger.info("Paused; skip post %s/%s", post.source_channel, post.message_id)
            return

        source_text = (post.text or "").strip()
        if not source_text and not post.has_media:
            logger.info("Empty message skip: %s/%s", post.source_channel, post.message_id)
            return

        hash_value = content_hash(f"{post.source_channel}:{strip_hashtags(source_text)}")
        if await self.db.is_duplicate(hash_value):
            logger.info("Duplicate skip: %s", hash_value)
            return

        translated = await self.translator.to_russian(source_text) if source_text else ""

        ai_result = self.ai_guard.analyze(translated or source_text)
        if not ai_result.allowed:
            logger.info(
                "Blocked by AI guard %s (score=%s): %s/%s",
                ai_result.reason,
                ai_result.score,
                post.source_channel,
                post.message_id,
            )
            if post.has_media:
                await self.send_to_moderation(post, translated or "[MEDIA]", ai_result.reason)
            return

        filter_result = self.rp_filter.check(translated or "media news")

        if not filter_result.allowed:
            logger.info("Blocked by RP filter %s: %s/%s", filter_result.reason, post.source_channel, post.message_id)
            if post.has_media:
                await self.send_to_moderation(post, translated or "[MEDIA]", filter_result.reason)
            return

        if filter_result.reason.startswith("ALLOWED_WAR"):
            await self.register_war_event(translated)

        rewritten = self.formatter.rewrite(post.source_country, translated)
        formatted = self.formatter.format_news(
            country=post.source_country,
            text=rewritten,
            country_hashtags=config.country_hashtags,
            premium_emoji_ids=config.premium_emoji_ids,
            country_aliases=config.country_aliases,
        )

        if post.has_media:
            await self.send_to_moderation(post, formatted, "MEDIA_REQUIRES_ADMIN_APPROVAL")
            return

        if config.publish_delay_seconds > 0:
            await asyncio.sleep(min(config.publish_delay_seconds, 3.0))

        await self.publish_and_mark(post, formatted, hash_value)

    async def publish_and_mark(self, post: IncomingPost, formatted: str, hash_value: str) -> None:
        try:
            await self.bot.send_message(
                chat_id=config.target_channel,
                text=formatted,
                parse_mode="MarkdownV2",
                disable_web_page_preview=False,
            )
            await self.db.mark_processed(post.source_channel, post.message_id, hash_value)
            logger.info("Published %s/%s", post.source_channel, post.message_id)
        except TelegramBadRequest:
            logger.exception("Publish failed")

    async def publish_media_and_mark(self, post: IncomingPost, caption: str, hash_value: str) -> None:
        try:
            if post.media_type == "photo" and post.media_file_id:
                await self.bot.send_photo(config.target_channel, post.media_file_id, caption=caption[:1024], parse_mode="MarkdownV2")
            elif post.media_type == "video" and post.media_file_id:
                await self.bot.send_video(config.target_channel, post.media_file_id, caption=caption[:1024], parse_mode="MarkdownV2")
            elif post.media_type == "animation" and post.media_file_id:
                await self.bot.send_animation(config.target_channel, post.media_file_id, caption=caption[:1024], parse_mode="MarkdownV2")
            else:
                await self.publish_and_mark(post, caption, hash_value)
                return

            await self.db.mark_processed(post.source_channel, post.message_id, hash_value)
            logger.info("Published media %s/%s", post.source_channel, post.message_id)
        except TelegramBadRequest:
            logger.exception("Media publish failed")

    async def send_to_moderation(self, post: IncomingPost, text: str, reason: str) -> None:
        token = uuid.uuid4().hex
        payload = {
            "source_country": post.source_country,
            "source_channel": post.source_channel,
            "message_id": post.message_id,
            "formatted_text": text,
            "has_media": post.has_media,
            "media_file_id": post.media_file_id,
            "media_type": post.media_type,
        }
        await self.db.store_moderation_payload(token, json.dumps(payload, ensure_ascii=False))

        msg_text = (
            "Пост отправлен на модерацию\n"
            f"Причина: {reason}\n"
            f"Источник: {post.source_country} ({post.source_channel})\n"
            f"ID: {post.message_id}\n\n"
            f"Текст:\n{text[:3000]}"
        )

        if post.has_media and post.media_file_id:
            if post.media_type == "photo":
                await self.bot.send_photo(config.admin_id, post.media_file_id, caption=msg_text[:1024], reply_markup=moderation_keyboard(token))
            elif post.media_type == "video":
                await self.bot.send_video(config.admin_id, post.media_file_id, caption=msg_text[:1024], reply_markup=moderation_keyboard(token))
            elif post.media_type == "animation":
                await self.bot.send_animation(config.admin_id, post.media_file_id, caption=msg_text[:1024], reply_markup=moderation_keyboard(token))
            else:
                await self.bot.send_message(config.admin_id, msg_text, reply_markup=moderation_keyboard(token))
        else:
            await self.bot.send_message(config.admin_id, msg_text, reply_markup=moderation_keyboard(token))

    async def register_war_event(self, text: str) -> None:
        counter = int(await self.db.get_state("war_event_counter", "0")) + 1
        await self.db.set_state("war_event_counter", str(counter))
        await self.db.set_state(f"war_event_last:{counter}", text[:700])

        last_request = int(await self.db.get_state("map_request_last_ts", "0"))
        now = int(time.time())
        if counter >= config.war_digest_threshold and now - last_request >= config.map_request_cooldown_minutes * 60:
            await self.db.set_state("map_request_last_ts", str(now))
            await self.db.set_state("war_event_counter", "0")
            await self.bot.send_message(
                config.admin_id,
                "Накоплены военные события. Пришлите карту командой /submit_map с фото/файлом и подписью.",
            )

    async def publish_map_digest(self, file_id: str | None, media_type: str, comment: str) -> None:
        escaped = re.sub(r"([_\*\[\]\(\)~`>#+\-=|{}\.!])", r"\\\1", comment[:120])
        title = f"> *Сводка:* _{escaped}_"
        if media_type == "photo" and file_id:
            await self.bot.send_photo(config.target_channel, file_id, caption=title, parse_mode="MarkdownV2")
        elif media_type == "document" and file_id:
            await self.bot.send_document(config.target_channel, file_id, caption=title, parse_mode="MarkdownV2")
        else:
            await self.bot.send_message(config.target_channel, title, parse_mode="MarkdownV2")

    async def cleanup_runtime_files(self) -> None:
        logs = list(Path(config.logs_dir).glob("*.log.*"))
        for p in logs:
            if p.stat().st_size > 1_000_000:
                p.unlink(missing_ok=True)
