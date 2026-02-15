import asyncio

import uvloop

from app.bot import AppRuntime
from app.config import config
from app.core.logging_setup import setup_logging
from app.core.services import NewsService
from app.storage.database import Database


async def main() -> None:
    setup_logging()
    config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(str(config.sqlite_path))
    await db.init()

    runtime = AppRuntime()
    service = NewsService(runtime.bot, db)

    await runtime.run(service)


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
