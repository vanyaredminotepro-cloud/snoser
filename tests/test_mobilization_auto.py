import asyncio
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.services import NewsService
from app.storage.database import Database


class DummyBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, *args, **kwargs):
        self.messages.append((chat_id, text))
        return None


async def _mk_service(tmp_path: Path):
    db = Database(str(tmp_path / "auto_mob.sqlite3"))
    await db.init()
    bot = DummyBot()
    svc = NewsService(bot, db)
    return svc, db, bot


def test_start_mobilization_auto_creates_attempt_and_news(tmp_path: Path):
    async def _run():
        svc, db, bot = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1200, "life_level": 60}})
        await db.set_country_war_status("Вилония", "peace")
        ok, msg = await svc.start_mobilization_auto("Вилония", "conscription")
        assert ok, msg
        active = await db.get_active_mobilization_attempt("Вилония")
        assert active is not None
        assert bot.messages, "expected auto news message"

    asyncio.run(_run())


def test_stop_mobilization_sets_cooldown(tmp_path: Path):
    async def _run():
        svc, db, _ = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1200, "life_level": 60}})
        await db.set_country_war_status("Вилония", "peace")
        ok, _ = await svc.start_mobilization_auto("Вилония", "conscription")
        assert ok
        ok_stop, _ = await svc.stop_mobilization_early("Вилония", 1)
        assert ok_stop
        cooldown = int(await db.get_state("mob:cooldown:Вилония", "0") or "0")
        assert cooldown > int(time.time())

    asyncio.run(_run())
