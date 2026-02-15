import asyncio
import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from aiogram import Bot, Dispatcher
from telethon import TelegramClient, events
from telethon.tl.types import Message

from app.config import config
from app.core.models import IncomingPost
from app.core.services import NewsService
from app.handlers.admin import bind_admin_handlers

logger = logging.getLogger(__name__)


def _extract_text(msg: Message) -> str:
    return (msg.message or msg.raw_text or "").strip()


class AppRuntime:
    def __init__(self) -> None:
        self.bot = Bot(token=config.bot_token)
        self.dispatcher = Dispatcher()
        self.userbot = TelegramClient(config.session_name, config.api_id, config.api_hash)

    async def run(self, service: NewsService) -> None:
        self.dispatcher.include_router(bind_admin_handlers(service))
        worker_task = asyncio.create_task(service.worker())

        source_handles = [v for v in config.source_channels.values()]

        @self.userbot.on(events.NewMessage(chats=source_handles))
        async def handler(event: events.NewMessage.Event) -> None:
            text = _extract_text(event.message)
            if not text and not event.message.media:
                return

            channel = await event.get_chat()
            title = getattr(channel, "title", None) or getattr(channel, "username", "unknown")

            country = next((k for k, v in config.source_channels.items() if v.lower() in str(title).lower()), None)
            if country is None:
                country = next(
                    (
                        k
                        for k, v in config.source_channels.items()
                        if str(getattr(channel, "username", "")).lower() == v.lower().lstrip("@")
                    ),
                    "UNKNOWN",
                )

            post = IncomingPost(
                source_country=country,
                source_channel=str(getattr(channel, "username", title)),
                message_id=event.message.id,
                text=text,
                has_media=bool(event.message.media),
            )

            await service.enqueue(post)

        try:
            logger.info("Starting userbot connection...")
            await self.userbot.connect()
            if not await self.userbot.is_user_authorized():
                logger.error(
                    "Telethon session is not authorized. Run `python -m app.main` and complete phone/code login once, then restart."
                )
                return

            logger.info("Userbot authorized and connected")
            await asyncio.gather(
                self.dispatcher.start_polling(self.bot),
                self.userbot.run_until_disconnected(),
            )
        finally:
            worker_task.cancel()
            await self.bot.session.close()
            await self.userbot.disconnect()


async def run_from_script() -> None:
    from app.core.logging_setup import setup_logging
    from app.storage.database import Database

    setup_logging()
    logger.info("Starting bot runtime from app/bot.py")

    config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(str(config.sqlite_path))
    await db.init()

    runtime = AppRuntime()
    service = NewsService(runtime.bot, db)
    await runtime.run(service)


if __name__ == "__main__":
    asyncio.run(run_from_script())
