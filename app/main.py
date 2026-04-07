import asyncio
import logging
import sys
from contextlib import suppress
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot import AppRuntime
from app.config import config
from app.core.logging_setup import setup_logging
from app.core.services import NewsService
from app.storage.database import Database


async def _healthcheck_server(port: int) -> asyncio.AbstractServer:
    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with suppress(Exception):
            await reader.read(1024)
        payload = b"ok"
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n\r\n"
            + payload
        )
        writer.write(response)
        with suppress(Exception):
            await writer.drain()
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    return await asyncio.start_server(_handle, host="0.0.0.0", port=port)


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Booting Telegram RP news bot...")
    config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    health_server: asyncio.AbstractServer | None = None
    if config.healthcheck_enabled:
        health_server = await _healthcheck_server(config.port)
        logger.info("Healthcheck endpoint enabled on 0.0.0.0:%s", config.port)

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
    try:
        await runtime.run(service)
    finally:
        if health_server is not None:
            health_server.close()
            await health_server.wait_closed()
            logger.info("Healthcheck endpoint stopped")


def run() -> None:
    if sys.platform != "win32":
        import uvloop

        uvloop.install()
    asyncio.run(main())


if __name__ == "__main__":
    run()
