import asyncio
import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.services import NewsService
from app.storage.database import Database


class DummyBot:
    async def send_message(self, *args, **kwargs):
        return None


async def _mk_service(tmp_path: Path) -> tuple[NewsService, Database]:
    db = Database(str(tmp_path / "mob.sqlite3"))
    await db.init()
    svc = NewsService(DummyBot(), db)
    return svc, db


def test_mobilization_requirements_block_partial_without_factory(tmp_path: Path):
    async def _run():
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1000, "life_level": 60}})
        await db.set_country_war_status("Вилония", "threat")
        ok, msg = await svc.attempt_mobilization("Вилония", "partial")
        assert not ok
        assert "Требуется военных заводов" in msg

    asyncio.run(_run())


def test_mobilization_penalty_demob_on_limit_overflow(tmp_path: Path):
    async def _run():
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1000, "life_level": 60}})
        await db.set_country_war_status("Вилония", "martial_law")
        await db.set_military_factories("Вилония", 1)
        week = svc._week_key_utc()
        await db.update_country_mobilization("Вилония", "normal", 30, 30, week, 0)

        ok, msg = await svc.attempt_mobilization("Вилония", "normal")
        assert not ok
        assert "демобилизация" in msg.lower()
        stats = await db.get_country_stats("Вилония")
        assert stats is not None
        assert stats[1] < 100

    asyncio.run(_run())


def test_mobilization_effects_change_stats(tmp_path: Path):
    async def _run():
        random.seed(42)
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1000, "life_level": 60}})
        await db.set_country_war_status("Вилония", "war")
        await db.set_military_factories("Вилония", 2)

        ok, msg = await svc.attempt_mobilization("Вилония", "aggressive")
        assert ok, msg
        stats = await db.get_country_stats("Вилония")
        assert stats is not None
        budget, army, _, life = stats
        war_status, risk = await db.get_country_war_and_risk("Вилония")
        assert war_status == "war"
        assert army > 100
        assert budget < 100000
        assert life < 60
        assert risk >= 5

    asyncio.run(_run())


def test_admin_is_not_blocked_by_antiflood(tmp_path: Path):
    async def _run():
        svc, _ = await _mk_service(tmp_path)
        ok_msg, _ = await svc.check_antiflood(5006629901)
        ok_cb, _ = await svc.check_user_access(5006629901, is_callback=True)
        assert ok_msg is True
        assert ok_cb is True

    asyncio.run(_run())
