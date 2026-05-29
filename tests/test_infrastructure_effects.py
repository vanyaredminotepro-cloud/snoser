import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.models import IncomingPost
from app.core.services import NewsService
from app.storage.database import Database


class DummyBot:
    async def send_message(self, *args, **kwargs):
        return None


def test_factory_news_adds_military_factories_and_resources(tmp_path: Path):
    async def _run() -> None:
        db = Database(str(tmp_path / "infra.sqlite3"))
        await db.init()
        svc = NewsService(DummyBot(), db)
        post = IncomingPost(
            source_country="Обоссляндия",
            source_channel="manual_admin",
            message_id=1,
            text="Обоссляндия построила 2 военных завода, 3 пункта снабжения и улучшила дороги #OBS",
            has_media=False,
        )

        await svc._apply_country_stats_effect(post)

        assert await db.get_military_factories("Обоссляндия") == 2
        oil, metal, grain = await db.get_country_resources("Обоссляндия")
        assert oil == 0
        assert metal > 0
        assert grain > 0

    asyncio.run(_run())


def test_config_seeds_factories_and_resources(tmp_path: Path):
    async def _run() -> None:
        db = Database(str(tmp_path / "seed.sqlite3"))
        await db.init()
        await db.set_military_factories("Вилония", 1)
        await db.seed_military_factories({"Вилония": 7})
        await db.seed_economic_resources({"Вилония": {"oil": 25, "metal": 95, "grain": 45}})

        assert await db.get_military_factories("Вилония") == 7
        assert await db.get_country_resources("Вилония") == (25, 95, 45)

    asyncio.run(_run())
