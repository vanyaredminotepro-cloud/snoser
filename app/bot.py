import asyncio
import contextlib
import json
import logging
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from aiogram import Bot, Dispatcher
from telethon import TelegramClient, events
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate
from telethon.tl.types import Message

from app.config import config
from app.core.models import IncomingPost
from app.core.services import NewsService
from app.handlers.admin import bind_admin_handlers

logger = logging.getLogger(__name__)


def _extract_text(msg: Message) -> str:
    return (msg.message or msg.raw_text or "").strip()


def _extract_media_metadata(msg: Message) -> tuple[str | None, str | None]:
    if msg.photo:
        return str(msg.photo), "photo"
    if msg.video:
        return str(msg.video), "video"
    if msg.gif:
        return str(msg.gif), "animation"
    if msg.document:
        return str(msg.document), "document"
    return None, None


class AppRuntime:
    def __init__(self) -> None:
        api_id, api_hash, bot_token = config.require_runtime_credentials()
        self.bot = Bot(token=bot_token)
        self.dispatcher = Dispatcher()
        self._api_id = api_id
        self._api_hash = api_hash
        self._proxy_rotate_index = 0
        self.userbot = self._build_userbot()

    def _build_userbot(self) -> TelegramClient:
        proxy_payload = config.proxy or {}
        if proxy_payload.get("secret"):
            return TelegramClient(
                config.session_name,
                self._api_id,
                self._api_hash,
                connection=ConnectionTcpMTProxyRandomizedIntermediate,
                proxy=(
                    str(proxy_payload.get("server") or proxy_payload.get("addr")),
                    int(proxy_payload.get("port") or 443),
                    str(proxy_payload.get("secret")),
                ),
            )
        return TelegramClient(
            config.session_name,
            self._api_id,
            self._api_hash,
            proxy=config.proxy or None,
        )

    @staticmethod
    def _parse_proxy_link(link: str) -> dict | None:
        parsed = urlparse(link.strip())
        if parsed.netloc.lower() not in {"t.me", "telegram.me"} or parsed.path != "/proxy":
            return None
        params = parse_qs(parsed.query)
        server = (params.get("server") or [""])[0].strip()
        port_raw = (params.get("port") or [""])[0].strip()
        secret = (params.get("secret") or [""])[0].strip()
        if not server or not port_raw or not secret:
            return None
        try:
            port = int(port_raw)
        except ValueError:
            return None
        return {
            "proxy_type": "mtproto",
            "server": server,
            "port": port,
            "secret": secret,
        }

    @staticmethod
    def _is_connection_reset_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            "winerror 64" in text
            or "server closed the connection" in text
            or "connection closed" in text
            or "expected bytes" in text
            or "auth_key generation timeout" in text
        )

    @staticmethod
    def _should_override_dc() -> bool:
        host = (config.tg_api_host or "").strip().lower()
        if not host:
            return False
        if host == "web.telegram.org":
            logger.warning("Skipping TG_API_HOST=web.telegram.org override: this host is not valid for MTProto userbot.")
            return False
        return True

    def _drop_session_files(self) -> None:
        for candidate in [Path(f"{config.session_name}.session"), Path(f"{config.session_name}.session-journal")]:
            if candidate.exists():
                candidate.unlink(missing_ok=True)

    async def _refresh_proxy_config(self, service: NewsService) -> None:
        raw_proxy = await service.db.get_state("cfg:proxy", "")
        if not raw_proxy:
            return
        try:
            payload = json.loads(raw_proxy)
        except json.JSONDecodeError:
            logger.warning("Invalid cfg:proxy payload, keeping current proxy config")
            return
        if isinstance(payload, dict):
            config.proxy = payload

    async def _rotate_proxy(self, service: NewsService) -> None:
        links = config.proxy_fallback_links or []
        if not links:
            return
        attempts = len(links)
        for _ in range(attempts):
            link = links[self._proxy_rotate_index % len(links)]
            self._proxy_rotate_index += 1
            parsed = self._parse_proxy_link(link)
            if not parsed:
                continue
            config.proxy = parsed
            await service.db.set_state("cfg:proxy", json.dumps(parsed, ensure_ascii=False))
            logger.warning("Switched to fallback MTProto proxy: %s:%s", parsed.get("server"), parsed.get("port"))
            return

    async def run(self, service: NewsService) -> None:
        self.dispatcher.include_router(bind_admin_handlers(service))
        await service.recover_pending_posts()
        worker_task = asyncio.create_task(service.worker())
        scheduler_task = asyncio.create_task(service.scheduler_worker())
        rss_task = asyncio.create_task(service.rss_worker())

        source_by_username = {
            v.lower().lstrip("@"): k
            for k, v in config.source_channels.items()
            if not v.startswith("+")
        }
        invite_only_sources = {
            k: v for k, v in config.source_channels.items() if v.startswith("+")
        }

        if invite_only_sources:
            logger.warning(
                "Invite-only sources are skipped from Telethon chat filter until resolvable usernames/IDs are provided: %s",
                ", ".join(f"{country}:{handle}" for country, handle in invite_only_sources.items()),
            )

        async def handler(event: events.NewMessage.Event) -> None:
            text = _extract_text(event.message)
            if not text and not event.message.media:
                return

            channel = await event.get_chat()
            username = str(getattr(channel, "username", "") or "").lower()
            country = source_by_username.get(username)
            if not country:
                return

            title = getattr(channel, "title", None) or getattr(channel, "username", "unknown")
            media_file_id, media_type = _extract_media_metadata(event.message)
            post = IncomingPost(
                source_country=country,
                source_channel=str(getattr(channel, "username", title)),
                message_id=event.message.id,
                text=text,
                has_media=bool(event.message.media),
                media_file_id=media_file_id,
                media_type=media_type,
                submitted_by_user_id=None,
                published_ts=int(getattr(event.message, "date", None).timestamp()) if getattr(event.message, "date", None) else None,
            )
            await service.enqueue(post)

        try:
            retry_delays = [5, 10, 20, 40, 80]
            connected = False
            for attempt, delay in enumerate(retry_delays, start=1):
                await self._refresh_proxy_config(service)
                self.userbot = self._build_userbot()
                self.userbot.add_event_handler(handler, events.NewMessage)
                try:
                    logger.info("Starting userbot connection (attempt %s/5)...", attempt)
                    if self._should_override_dc():
                        self.userbot.session.set_dc(2, config.tg_api_host, config.tg_api_port)
                    await self.userbot.connect()
                    if not await self.userbot.is_user_authorized():
                        logger.warning("Telethon session is not authorized. Starting interactive login flow...")
                        try:
                            await self.userbot.start()
                        except (EOFError, OSError):
                            logger.error(
                                "Interactive login is unavailable in this environment. Run `python -m app.main` in a terminal and complete phone/code login once."
                            )
                            return
                    if not await self.userbot.is_user_authorized():
                        raise RuntimeError("Telethon session is still not authorized after login attempt.")
                    connected = True
                    break
                except Exception as exc:
                    logger.warning("Userbot connection attempt failed: %s", exc)
                    with contextlib.suppress(Exception):
                        await self.userbot.disconnect()
                    if self._is_connection_reset_error(exc):
                        self._drop_session_files()
                        await self._rotate_proxy(service)
                    if attempt < len(retry_delays):
                        await asyncio.sleep(delay)
            if not connected:
                logger.error("Userbot connection failed after 5 attempts.")
                return
            logger.info("Userbot authorized and connected")
            service.attach_user_client(self.userbot)
            loaded = await service.refresh_emoji_packs()
            logger.info("Loaded custom emoji pack cache: %s", loaded)
            await asyncio.gather(
                self.dispatcher.start_polling(self.bot),
                self.userbot.run_until_disconnected(),
            )
        finally:
            worker_task.cancel()
            scheduler_task.cancel()
            rss_task.cancel()
            await service.cleanup_runtime_files()
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
    seeded = await db.seed_country_leaders(config.manual_country_authors)
    logger.info("Country leaders seeded from config: %s", seeded)
    stats_seeded = await db.seed_country_stats(config.initial_country_stats)
    logger.info("Country stats seeded from config: %s", stats_seeded)
    extras_seeded = await db.seed_country_extra_metrics(config.initial_country_extra_metrics)
    logger.info("Country extra metrics seeded from config: %s", extras_seeded)

    try:
        runtime = AppRuntime()
    except RuntimeError as exc:
        logger.error(str(exc))
        logger.error("Configure environment variables (or .env) and restart the bot.")
        return

    service = NewsService(runtime.bot, db)
    await service.load_dynamic_config()
    await runtime.run(service)


if __name__ == "__main__":
    asyncio.run(run_from_script())
