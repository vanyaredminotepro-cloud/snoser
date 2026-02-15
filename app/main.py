import asyncio
import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot import AppRuntime
from app.config import config
from app.core.logging_setup import setup_logging
from app.core.services import NewsService
from app.storage.database import Database


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Booting Telegram RP news bot...")
    config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(str(config.sqlite_path))
    await db.init()

    runtime = AppRuntime()
    service = NewsService(runtime.bot, db)

    await runtime.run(service)


def run() -> None:
    if sys.platform != "win32":
        import uvloop

        uvloop.install()
    asyncio.run(main())


if __name__ == "__main__":
    run()
