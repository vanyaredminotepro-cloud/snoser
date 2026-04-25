from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from playwright.async_api import BrowserContext, Page, TimeoutError, async_playwright

# ======================================================================
# TikTok Bot: автопостинг + сбор статистики + Telegram-панель управления
# ======================================================================

DEFAULT_DESCRIPTION = """Телеграм канал РП проекта: @perehodnikrp"""
MANDATORY_HASHTAG = "#обоссляндия"
DEFAULT_HASHTAG_POOL = [
    "#обосляндия",
    "#страйкбол",
    "#рек",
    "#рекомендации",
    "#rec",
    "#recomendation",
    "#war",
    "#землянка",
    "#fyp",
    "#elbruso",
]

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "землянка": ("землянка", "бункер", "окоп"),
    "мобилизация": ("мобилизация", "призыв", "резерв"),
    "бот": ("бот", "automation", "script"),
    "карта": ("карта", "map", "территория"),
    "исследования": ("исследования", "research", "эксперимент"),
}


@dataclass(slots=True)
class TikTokConfig:
    # Обязательно через переменные окружения
    tg_bot_token: str = os.getenv("TG_BOT_TOKEN", "")
    tiktok_login: str = os.getenv("TIKTOK_LOGIN", "")
    tiktok_password: str = os.getenv("TIKTOK_PASSWORD", "")

    # Опциональные переменные
    tiktok_profile_url: str = os.getenv("TIKTOK_PROFILE_URL", "")
    tiktok_session_path: Path = Path(os.getenv("TIKTOK_SESSION_PATH", "app/storage/tiktok_auth.json"))
    sqlite_path: Path = Path(os.getenv("TIKTOK_SQLITE_PATH", "app/storage/tiktok_stats.sqlite3"))
    queue_dir: Path = Path(os.getenv("TIKTOK_QUEUE_DIR", "tiktok_queue"))
    state_file: Path = Path(os.getenv("TIKTOK_STATE_FILE", "app/storage/tiktok_runtime_settings.json"))

    headless: bool = os.getenv("TIKTOK_HEADLESS", "1") == "1"


class TikTokStatsDB:
    """SQLite-хранилище статистики, логов публикаций и runtime-настроек."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tiktok_stats (
                    date TEXT PRIMARY KEY,
                    followers INTEGER NOT NULL,
                    views_per_day INTEGER NOT NULL,
                    er REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tiktok_videos (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    views INTEGER NOT NULL,
                    likes INTEGER NOT NULL,
                    comments INTEGER NOT NULL,
                    reposts INTEGER NOT NULL,
                    saves INTEGER NOT NULL,
                    description TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tiktok_topics (
                    topic TEXT PRIMARY KEY,
                    avg_views REAL NOT NULL,
                    avg_engagement REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tiktok_publish_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    video_url TEXT,
                    error_text TEXT
                );
                """
            )

    def upsert_video(self, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tiktok_videos (
                    id, date, topic, views, likes, comments, reposts, saves, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    date=excluded.date,
                    topic=excluded.topic,
                    views=excluded.views,
                    likes=excluded.likes,
                    comments=excluded.comments,
                    reposts=excluded.reposts,
                    saves=excluded.saves,
                    description=excluded.description
                """,
                (
                    payload["id"],
                    payload["date"],
                    payload["topic"],
                    payload["views"],
                    payload["likes"],
                    payload["comments"],
                    payload["reposts"],
                    payload["saves"],
                    payload["description"],
                ),
            )

    def upsert_daily_stats(self, day: date, followers: int, views_per_day: int, er: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tiktok_stats (date, followers, views_per_day, er)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    followers=excluded.followers,
                    views_per_day=excluded.views_per_day,
                    er=excluded.er
                """,
                (day.isoformat(), followers, views_per_day, er),
            )

    def rebuild_topics_stats(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM tiktok_topics")
            rows = conn.execute(
                """
                SELECT
                    topic,
                    AVG(views) AS avg_views,
                    AVG(CASE WHEN views > 0 THEN (likes + comments + reposts + saves) * 100.0 / views ELSE 0 END) AS avg_engagement
                FROM tiktok_videos
                GROUP BY topic
                """
            ).fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO tiktok_topics (topic, avg_views, avg_engagement) VALUES (?, ?, ?)",
                    (row["topic"], float(row["avg_views"] or 0), float(row["avg_engagement"] or 0)),
                )

    def log_publish_result(self, file_path: Path, status: str, video_url: str | None = None, error_text: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tiktok_publish_log (created_at, file_path, status, video_url, error_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (datetime.now(UTC).isoformat(), str(file_path), status, video_url, error_text),
            )

    def get_followers_snapshots(self, today: date) -> dict[str, int]:
        week_day = today - timedelta(days=7)
        month_day = today - timedelta(days=30)
        with self._connect() as conn:
            today_row = conn.execute("SELECT followers FROM tiktok_stats WHERE date=?", (today.isoformat(),)).fetchone()
            week_row = conn.execute(
                "SELECT followers FROM tiktok_stats WHERE date<=? ORDER BY date DESC LIMIT 1", (week_day.isoformat(),)
            ).fetchone()
            month_row = conn.execute(
                "SELECT followers FROM tiktok_stats WHERE date<=? ORDER BY date DESC LIMIT 1", (month_day.isoformat(),)
            ).fetchone()
            return {
                "today": int(today_row["followers"] if today_row else 0),
                "week_ago": int(week_row["followers"] if week_row else 0),
                "month_ago": int(month_row["followers"] if month_row else 0),
            }

    def get_top_topics(self, limit: int = 3) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT topic, avg_views, avg_engagement FROM tiktok_topics ORDER BY avg_engagement DESC, avg_views DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def get_queue_stats(self) -> dict[str, int]:
        with self._connect() as conn:
            ok = conn.execute("SELECT COUNT(*) AS c FROM tiktok_publish_log WHERE status='success'").fetchone()["c"]
            err = conn.execute("SELECT COUNT(*) AS c FROM tiktok_publish_log WHERE status='error'").fetchone()["c"]
            return {"success": int(ok), "error": int(err)}


class RuntimeSettings:
    """Изменяемые через Telegram настройки: описание, хештеги, расписание, папки."""

    def __init__(self, cfg: TikTokConfig) -> None:
        self.cfg = cfg
        self.cfg.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state: dict[str, Any] = {
            "description": DEFAULT_DESCRIPTION,
            "hashtags": DEFAULT_HASHTAG_POOL,
            "post_hours_utc": [10, 18],
            "queue_dir": str(cfg.queue_dir),
            "bot_enabled": True,
        }
        self.load()

    def load(self) -> None:
        if self.cfg.state_file.exists():
            try:
                self.state.update(json.loads(self.cfg.state_file.read_text(encoding="utf-8")))
            except Exception:
                logging.getLogger("tiktok_automation").warning("Не удалось прочитать runtime settings, применяю defaults")

    def save(self) -> None:
        self.cfg.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def queue_dir(self) -> Path:
        return Path(self.state.get("queue_dir") or str(self.cfg.queue_dir))

    @property
    def hashtags(self) -> list[str]:
        tags = self.state.get("hashtags") or DEFAULT_HASHTAG_POOL
        return [str(t).strip() for t in tags if str(t).strip()]

    @property
    def description(self) -> str:
        return str(self.state.get("description") or DEFAULT_DESCRIPTION)

    @property
    def post_hours_utc(self) -> list[int]:
        hours = self.state.get("post_hours_utc") or [10, 18]
        result = [int(h) for h in hours if 0 <= int(h) <= 23]
        return result[:2] if result else [10, 18]

    @property
    def bot_enabled(self) -> bool:
        return bool(self.state.get("bot_enabled", True))


class TikTokPublisher:
    """Публикация видео в TikTok через Playwright."""

    def __init__(self, cfg: TikTokConfig, runtime: RuntimeSettings, db: TikTokStatsDB, logger: logging.Logger) -> None:
        self.cfg = cfg
        self.runtime = runtime
        self.db = db
        self.logger = logger

    def build_description(self) -> str:
        random_tags = random.sample(self.runtime.hashtags, k=min(5, len(self.runtime.hashtags)))
        hashtags = " ".join([MANDATORY_HASHTAG, *random_tags])
        return f"{self.runtime.description.strip()}\n\n{hashtags}"

    def list_queue_videos(self) -> list[Path]:
        queue_dir = self.runtime.queue_dir
        queue_dir.mkdir(parents=True, exist_ok=True)
        return sorted(
            [f for f in queue_dir.iterdir() if f.is_file() and f.suffix.lower() == ".mp4"],
            key=lambda x: x.name,
        )

    async def _human_delay(self, low: float = 0.7, high: float = 2.1) -> None:
        await asyncio.sleep(random.uniform(low, high))

    async def _open_context(self) -> tuple[Any, BrowserContext]:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=self.cfg.headless)
        if self.cfg.tiktok_session_path.exists():
            context = await browser.new_context(storage_state=str(self.cfg.tiktok_session_path))
        else:
            context = await browser.new_context()
        return playwright, context

    async def _login_if_needed(self, page: Page) -> None:
        await page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")
        await self._human_delay()
        if self.cfg.tiktok_login and self.cfg.tiktok_password:
            # Селекторы TikTok могут изменяться, при необходимости обновите.
            await page.fill('input[name="username"]', self.cfg.tiktok_login)
            await self._human_delay()
            await page.fill('input[type="password"]', self.cfg.tiktok_password)
            await self._human_delay()
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)

    async def publish_one(self, video_path: Path) -> tuple[bool, str]:
        description = self.build_description()
        playwright = None
        context = None
        try:
            playwright, context = await self._open_context()
            page = await context.new_page()
            await self._login_if_needed(page)

            await page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded")
            await self._human_delay(1.0, 3.0)

            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(str(video_path))
            await page.wait_for_timeout(5000)

            caption_input = page.locator('div[role="textbox"]')
            await caption_input.click()
            await caption_input.fill(description)
            await self._human_delay(1.0, 2.0)

            publish_button = page.locator('button:has-text("Post")')
            await publish_button.click()
            await page.wait_for_timeout(7000)

            url = page.url
            self.db.log_publish_result(video_path, status="success", video_url=url)
            video_path.rename(video_path.with_suffix(".posted"))
            await context.storage_state(path=str(self.cfg.tiktok_session_path))
            return True, url
        except TimeoutError as exc:
            self.db.log_publish_result(video_path, status="error", error_text=f"TimeoutError: {exc}")
            self.logger.exception("Таймаут публикации %s", video_path)
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            self.db.log_publish_result(video_path, status="error", error_text=str(exc))
            self.logger.exception("Ошибка публикации %s", video_path)
            return False, str(exc)
        finally:
            if context:
                await context.close()
            if playwright:
                await playwright.stop()

    async def publish_next(self) -> tuple[bool, str]:
        queue = self.list_queue_videos()
        if not queue:
            return False, "Очередь пуста"
        return await self.publish_one(queue[0])

    async def publish_all(self) -> list[tuple[Path, bool, str]]:
        results: list[tuple[Path, bool, str]] = []
        for path in self.list_queue_videos():
            ok, info = await self.publish_one(path)
            results.append((path, ok, info))
        return results


class TikTokStatsCollector:
    """Парсинг публичной страницы TikTok (SIGI_STATE) для статистики."""

    PROFILE_SIGI_RE = re.compile(r'<script id="SIGI_STATE" type="application/json">(.*?)</script>')

    def __init__(self, cfg: TikTokConfig, db: TikTokStatsDB, logger: logging.Logger) -> None:
        self.cfg = cfg
        self.db = db
        self.logger = logger

    @staticmethod
    def detect_topic(description: str) -> str:
        lower = description.lower()
        for topic, words in TOPIC_KEYWORDS.items():
            if any(w in lower for w in words):
                return topic
        return "исследования"

    @staticmethod
    def calc_er(views: int, likes: int, comments: int, reposts: int, saves: int) -> float:
        return ((likes + comments + reposts + saves) / views * 100.0) if views > 0 else 0.0

    async def collect(self) -> None:
        if not self.cfg.tiktok_profile_url:
            self.logger.warning("TIKTOK_PROFILE_URL не задан, сбор статистики пропущен")
            return

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(self.cfg.tiktok_profile_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3500)
            html = await page.content()

            m = self.PROFILE_SIGI_RE.search(html)
            if not m:
                self.logger.warning("SIGI_STATE не найден")
                return

            state = json.loads(m.group(1))
            users = list((state.get("UserModule", {}).get("users", {}) or {}).values())
            first = users[0] if users else {}
            followers = int(first.get("stats", {}).get("followerCount", 0))

            item_module = state.get("ItemModule", {}) or {}
            ers: list[float] = []
            total_views = 0

            for video_id, video in item_module.items():
                vstats = video.get("stats", {})
                desc = str(video.get("desc", ""))

                views = int(vstats.get("playCount", 0))
                likes = int(vstats.get("diggCount", 0))
                comments = int(vstats.get("commentCount", 0))
                reposts = int(vstats.get("shareCount", 0))
                saves = int(vstats.get("collectCount", 0))

                topic = self.detect_topic(desc)
                er = self.calc_er(views, likes, comments, reposts, saves)
                ers.append(er)
                total_views += views

                create_ts = int(video.get("createTime", 0) or 0)
                dt = datetime.fromtimestamp(create_ts, tz=UTC) if create_ts else datetime.now(UTC)

                self.db.upsert_video(
                    {
                        "id": str(video_id),
                        "date": dt.isoformat(),
                        "topic": topic,
                        "views": views,
                        "likes": likes,
                        "comments": comments,
                        "reposts": reposts,
                        "saves": saves,
                        "description": desc,
                    }
                )

            avg_er = float(sum(ers) / len(ers)) if ers else 0.0
            self.db.upsert_daily_stats(date.today(), followers, total_views, avg_er)
            self.db.rebuild_topics_stats()
            self.logger.info("Статистика обновлена: followers=%s videos=%s", followers, len(item_module))
        except Exception:  # noqa: BLE001
            self.logger.exception("Ошибка сбора статистики")
        finally:
            await context.close()
            await browser.close()
            await playwright.stop()


class TikTokAutomationApp:
    """Главный оркестратор: scheduler + Telegram control panel."""

    def __init__(self, cfg: TikTokConfig) -> None:
        if not cfg.tg_bot_token:
            raise RuntimeError("Нужно задать TG_BOT_TOKEN")
        if not cfg.tiktok_login or not cfg.tiktok_password:
            raise RuntimeError("Нужно задать TIKTOK_LOGIN и TIKTOK_PASSWORD")

        self.cfg = cfg
        self.logger = logging.getLogger("tiktok_automation")

        self.db = TikTokStatsDB(cfg.sqlite_path)
        self.runtime = RuntimeSettings(cfg)
        self.publisher = TikTokPublisher(cfg, self.runtime, self.db, self.logger)
        self.collector = TikTokStatsCollector(cfg, self.db, self.logger)

        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.bot = Bot(token=cfg.tg_bot_token)
        self.dp = Dispatcher()

        # Простейшее хранение состояния диалога по пользователю
        self.await_video_from: set[int] = set()
        self.await_description_from: set[int] = set()
        self.await_hashtags_from: set[int] = set()
        self.await_schedule_from: set[int] = set()
        self.await_queue_path_from: set[int] = set()

        self._register_handlers()

    # ---------- UI ----------
    def main_menu(self) -> Any:
        kb = InlineKeyboardBuilder()
        kb.button(text="📊 СТАТИСТИКА", callback_data="menu_stats")
        kb.button(text="📤 ЗАГРУЗИТЬ ВИДЕО", callback_data="menu_upload")
        kb.button(text="▶️ ВЫЛОЖИТЬ ВСЕ ВИДЕО", callback_data="menu_publish_all")
        kb.button(text="⚙️ НАСТРОЙКИ", callback_data="menu_settings")
        kb.button(text="🚀 СТАТУС БОТА", callback_data="menu_status")
        kb.button(text="❌ ОСТАНОВИТЬ БОТА", callback_data="menu_stop")
        kb.adjust(1)
        return kb.as_markup()

    def settings_menu(self) -> Any:
        kb = InlineKeyboardBuilder()
        kb.button(text="✏️ Править описание", callback_data="settings_desc")
        kb.button(text="🏷️ Править хештеги", callback_data="settings_tags")
        kb.button(text="⏰ Изменить расписание", callback_data="settings_schedule")
        kb.button(text="📂 Указать папки", callback_data="settings_paths")
        kb.button(text="⬅️ Назад", callback_data="menu_back")
        kb.adjust(1)
        return kb.as_markup()

    def _register_handlers(self) -> None:
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_stats, Command("stats"))
        self.dp.callback_query.register(self.on_menu_click)
        self.dp.message.register(self.on_video_message, F.video)
        self.dp.message.register(self.on_text_message, F.text)

    # ---------- Reports ----------
    def build_stats_report(self) -> str:
        today = date.today()
        snap = self.db.get_followers_snapshots(today)
        top = self.db.get_top_topics(3)
        qstats = self.db.get_queue_stats()

        week_delta = snap["today"] - snap["week_ago"]
        month_delta = snap["today"] - snap["month_ago"]
        top_text = "\n".join(
            f"• {row['topic']}: avg_views={row['avg_views']:.0f}, avg_ER={row['avg_engagement']:.2f}%" for row in top
        ) or "• Нет данных"

        return (
            "📊 TikTok /stats\n\n"
            f"Подписчики: {snap['today']}\n"
            f"Изменение за 7 дней: {week_delta:+d}\n"
            f"Изменение за 30 дней: {month_delta:+d}\n"
            f"Опубликовано успешно: {qstats['success']}\n"
            f"Ошибок публикации: {qstats['error']}\n\n"
            f"Топ тем:\n{top_text}"
        )

    def build_status_report(self) -> str:
        queue_count = len(self.publisher.list_queue_videos())
        jobs = self.scheduler.get_jobs()
        next_run = min((j.next_run_time for j in jobs if j.next_run_time), default=None)
        next_run_text = next_run.isoformat() if next_run else "нет"

        return (
            "🚀 Статус бота\n\n"
            f"Состояние: {'работает' if self.runtime.bot_enabled else 'остановлен'}\n"
            f"Очередь видео: {queue_count}\n"
            f"Следующая публикация: {next_run_text}\n"
            f"Папка очереди: {self.runtime.queue_dir}"
        )

    # ---------- Scheduler ----------
    async def scheduled_publish(self) -> None:
        if not self.runtime.bot_enabled:
            self.logger.info("Публикация пропущена: бот остановлен")
            return
        ok, info = await self.publisher.publish_next()
        self.logger.info("scheduled publish: %s | %s", ok, info)

    async def scheduled_stats(self) -> None:
        if not self.runtime.bot_enabled:
            return
        await self.collector.collect()

    def configure_scheduler(self) -> None:
        for h in self.runtime.post_hours_utc:
            self.scheduler.add_job(self.scheduled_publish, "cron", hour=h, minute=0, id=f"post_{h}", replace_existing=True)
        self.scheduler.add_job(self.scheduled_stats, "interval", hours=6, id="collect_stats", replace_existing=True)

    def reload_schedule(self) -> None:
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith("post_"):
                self.scheduler.remove_job(job.id)
        for h in self.runtime.post_hours_utc:
            self.scheduler.add_job(self.scheduled_publish, "cron", hour=h, minute=0, id=f"post_{h}", replace_existing=True)

    # ---------- Handlers ----------
    async def cmd_start(self, message: Message) -> None:
        await message.answer("Панель TikTok-бота", reply_markup=self.main_menu())

    async def cmd_stats(self, message: Message) -> None:
        await message.answer(self.build_stats_report())

    async def on_menu_click(self, call: CallbackQuery) -> None:
        if not call.message:
            return

        data = call.data or ""
        uid = call.from_user.id

        if data == "menu_stats":
            await call.message.answer(self.build_stats_report(), reply_markup=self.main_menu())
        elif data == "menu_upload":
            self.await_video_from.add(uid)
            await call.message.answer("Отправь MP4 (до 50 МБ).", reply_markup=self.main_menu())
        elif data == "menu_publish_all":
            await call.message.answer("Начинаю принудительную публикацию очереди...")
            results = await self.publisher.publish_all()
            if not results:
                await call.message.answer("Очередь пуста.", reply_markup=self.main_menu())
            else:
                ok = sum(1 for _, flag, _ in results if flag)
                fail = len(results) - ok
                await call.message.answer(f"Готово. Успех: {ok}, ошибок: {fail}", reply_markup=self.main_menu())
        elif data == "menu_settings":
            await call.message.answer("⚙️ Настройки", reply_markup=self.settings_menu())
        elif data == "menu_status":
            await call.message.answer(self.build_status_report(), reply_markup=self.main_menu())
        elif data == "menu_stop":
            self.runtime.state["bot_enabled"] = False
            self.runtime.save()
            await call.message.answer("❌ Бот остановлен. Планировщик останется активным, но задачи будут пропускаться.", reply_markup=self.main_menu())
        elif data == "menu_back":
            await call.message.answer("Главное меню", reply_markup=self.main_menu())
        elif data == "settings_desc":
            self.await_description_from.add(uid)
            await call.message.answer("Отправь новый текст описания.")
        elif data == "settings_tags":
            self.await_hashtags_from.add(uid)
            await call.message.answer("Отправь хештеги через пробел (без #обоссляндия, он добавляется автоматически).")
        elif data == "settings_schedule":
            self.await_schedule_from.add(uid)
            await call.message.answer("Отправь 2 часа UTC через запятую, например: 10,18")
        elif data == "settings_paths":
            self.await_queue_path_from.add(uid)
            await call.message.answer("Отправь путь до папки очереди (пример: tiktok_queue)")

        await call.answer()

    async def on_video_message(self, message: Message) -> None:
        if not message.from_user:
            return
        uid = message.from_user.id
        if uid not in self.await_video_from:
            return
        if not message.video:
            return

        video = message.video
        if video.file_size and video.file_size > 50 * 1024 * 1024:
            await message.answer("❌ Файл больше 50 МБ. Отправь видео меньше 50 МБ.")
            return

        # Telegram часто присылает mime_type='video/mp4', но дополнительно проверяем имя.
        if video.mime_type and "mp4" not in video.mime_type.lower():
            await message.answer("❌ Нужен именно MP4.")
            return

        self.runtime.queue_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{video.file_unique_id}.mp4"
        destination = self.runtime.queue_dir / safe_name

        file = await self.bot.get_file(video.file_id)
        await self.bot.download_file(file.file_path, destination=str(destination))
        self.await_video_from.discard(uid)

        await message.answer(
            "✅ Видео принято. Будет опубликовано в соответствии с расписанием (или сейчас, если выбран ручной режим).",
            reply_markup=self.main_menu(),
        )

    async def on_text_message(self, message: Message) -> None:
        if not message.from_user or not message.text:
            return
        uid = message.from_user.id
        text = message.text.strip()

        if uid in self.await_description_from:
            self.runtime.state["description"] = text
            self.runtime.save()
            self.await_description_from.discard(uid)
            await message.answer("✅ Описание обновлено.", reply_markup=self.settings_menu())
            return

        if uid in self.await_hashtags_from:
            tags = [t if t.startswith("#") else f"#{t}" for t in text.split() if t]
            tags = [t for t in tags if t.lower() != MANDATORY_HASHTAG]
            if len(tags) < 5:
                await message.answer("❌ Нужно минимум 5 хештегов.")
                return
            self.runtime.state["hashtags"] = tags
            self.runtime.save()
            self.await_hashtags_from.discard(uid)
            await message.answer("✅ Хештеги обновлены.", reply_markup=self.settings_menu())
            return

        if uid in self.await_schedule_from:
            try:
                parts = [int(x.strip()) for x in text.split(",") if x.strip()]
                if len(parts) != 2 or any(h < 0 or h > 23 for h in parts):
                    raise ValueError
                self.runtime.state["post_hours_utc"] = parts
                self.runtime.save()
                self.reload_schedule()
                self.await_schedule_from.discard(uid)
                await message.answer(f"✅ Расписание обновлено: {parts[0]}:00 и {parts[1]}:00 UTC", reply_markup=self.settings_menu())
            except ValueError:
                await message.answer("❌ Неверный формат. Пример: 10,18")
            return

        if uid in self.await_queue_path_from:
            new_dir = Path(text)
            new_dir.mkdir(parents=True, exist_ok=True)
            self.runtime.state["queue_dir"] = str(new_dir)
            self.runtime.save()
            self.await_queue_path_from.discard(uid)
            await message.answer(f"✅ Папка очереди обновлена: {new_dir}", reply_markup=self.settings_menu())
            return

    # ---------- Lifecycle ----------
    async def start(self) -> None:
        self.db.init()
        self.configure_scheduler()
        self.scheduler.start()
        self.logger.info("TikTok automation запущен")
        await self.dp.start_polling(self.bot)


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


async def main() -> None:
    setup_logging()
    cfg = TikTokConfig()
    app = TikTokAutomationApp(cfg)
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
