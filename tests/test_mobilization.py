import asyncio
import json
import random
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.services import NewsService
from app.core.models import IncomingPost
from app.storage.database import Database


class DummyBot:
    async def send_message(self, *args, **kwargs):
        return None


async def _mk_service(tmp_path: Path) -> tuple[NewsService, Database]:
    db = Database(str(tmp_path / "mob.sqlite3"))
    await db.init()
    svc = NewsService(DummyBot(), db)
    return svc, db


async def _seed_mob_signal(db: Database, country: str, *, age_hours: int = 1) -> None:
    await db.set_state(
        f"mob_signal:{country}",
        json.dumps(
            {
                "country": country,
                "channel": "oboss_news",
                "message_id": 55,
                "ts": int(time.time()) - age_hours * 3600,
            },
            ensure_ascii=False,
        ),
    )


def test_mobilization_requirements_block_partial_without_factory(tmp_path: Path):
    async def _run():
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Тестландия": {"budget": 100000, "army": 100, "citizens": 1000, "life_level": 60}})
        await db.set_country_war_status("Тестландия", "threat")
        ok, msg = await svc.attempt_mobilization("Тестландия", "partial")
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


def test_stale_news_is_not_recent(tmp_path: Path):
    async def _run():
        svc, _ = await _mk_service(tmp_path)
        post = IncomingPost(
            source_country="Вилония",
            source_channel="test",
            message_id=1,
            text="test",
            has_media=False,
            published_ts=1,
        )
        assert svc._is_recent_news(post, max_hours=48) is False

    asyncio.run(_run())


def test_day4_sync_from_recent_mobilization_news(tmp_path: Path):
    async def _run():
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1000, "life_level": 60}})
        await db.set_country_war_status("Вилония", "peace")
        await _seed_mob_signal(db, "Вилония")
        ok, _ = await svc.start_mobilization("Вилония", "conscription", 5)
        assert ok
        post = IncomingPost(
            source_country="Вилония",
            source_channel="test",
            message_id=2,
            text="В стране продолжается мобилизация и призыв.",
            has_media=False,
            published_ts=int(time.time()) - (48 * 3600),
        )
        await svc._sync_mobilization_day4_from_news(post, post.text)
        raw = await db.get_state("mobplan:Вилония", "")
        assert "\"gained\": 3" in raw

    asyncio.run(_run())


def test_start_mobilization_generates_signal_and_news_without_manual_post(tmp_path: Path):
    async def _run():
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1000, "life_level": 60}})
        await db.set_country_war_status("Вилония", "peace")
        ok, msg = await svc.start_mobilization("Вилония", "conscription", 5)
        assert ok
        assert "Новость о мобилизации" in msg
        assert "Скорость" in msg
        criteria_ok, criteria_msg = await svc.check_mobilization_news_criteria("Вилония")
        assert criteria_ok
        assert "кнопкой мобилизации" in criteria_msg

    asyncio.run(_run())


def test_mobilization_amount_is_capped_by_population(tmp_path: Path):
    async def _run():
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Малолюдия": {"budget": 100000, "army": 10, "citizens": 100, "life_level": 50}})
        await db.set_country_war_status("Малолюдия", "peace")
        ok, msg = await svc.start_mobilization("Малолюдия", "conscription", 500)
        assert not ok
        assert "Слишком много" in msg

    asyncio.run(_run())


def test_force_stop_blocks_restart_in_same_week(tmp_path: Path):
    async def _run():
        svc, db = await _mk_service(tmp_path)
        await db.seed_country_stats({"Вилония": {"budget": 100000, "army": 100, "citizens": 1000, "life_level": 60}})
        await db.set_country_war_status("Вилония", "peace")
        await _seed_mob_signal(db, "Вилония", age_hours=1)
        ok, _ = await svc.start_mobilization("Вилония", "conscription", 5)
        assert ok
        stop_ok, _ = await svc.force_finish_mobilization("Вилония", "тест", 1)
        assert stop_ok
        ok2, msg2 = await svc.start_mobilization("Вилония", "conscription", 5)
        assert not ok2
        assert "Повторный запуск запрещён" in msg2

    asyncio.run(_run())
