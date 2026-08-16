from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonWebApp, Message, WebAppInfo

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("WARLORD_DB_PATH", ROOT / "warlord.sqlite3"))
TECHS_PATH = Path(os.getenv("WARLORD_TECHS_PATH", ROOT / "techs.json"))
BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "")))}
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com/index.html")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
ECONOMY_TICK_SECONDS = int(os.getenv("ECONOMY_TICK_SECONDS", "3600"))

RULES_TEXT = """
WARLORD RP: отвечай кратко и авторитетно. Разрешены только RP-действия с логикой, сроками, ценой и доказательствами.
Экономика: доход=1000+фабрики*500+порты*300+налог*население. Расход=солдаты*5+граждане*2.
Стройка: максимум 1 здание + 2 НП/дороги одновременно. Исследования: максимум 2 одновременно.
Tech ban: запрещены танки, БМП, тяжёлая гусеничная бронетехника, РСЗО, пилотируемая авиация, ядерное/химическое ОМП, крейсеры и эсминцы.
ОЯТ: доступно только Паониции, country_code=paonitsiya. Отказ: ⚠️ Данная технология является закрытой национальной разработкой Паониции!
Флот: только малый/средний класс, патрульные катера, десантные катера, баржи, ударные катера береговой охраны.
""".strip()

TECH_BAN_PATTERNS = {
    "танк": "Танки запрещены Tech Ban.",
    "бмп": "БМП запрещены Tech Ban.",
    "рсзо": "РСЗО запрещены Tech Ban.",
    "самолет": "Пилотируемая авиация запрещена Tech Ban.",
    "вертолет": "Пилотируемая авиация запрещена Tech Ban.",
    "ядер": "ОМП запрещено Tech Ban.",
    "химическ": "Химическое ОМП запрещено Tech Ban.",
    "крейсер": "Крупные корабли запрещены Tech Ban.",
    "эсмин": "Крупные корабли запрещены Tech Ban.",
}

TAX_MULTIPLIERS = {"low": 0.5, "medium": 1.0, "high": 1.5, "extreme": 2.0}
router = Router(name="warlord_minimal")
logger = logging.getLogger("warlord")


@dataclass(frozen=True, slots=True)
class Tech:
    id: str
    title: str
    tier: str
    hours: int
    cost: int
    branch_id: str
    branch_title: str
    requires: tuple[str, ...]
    building_required: str | None
    exclusive_country_code: str | None


class TechCatalog:
    def __init__(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.denial = str(payload["exclusive_denial"])
        self.tiers = payload["tiers"]
        self.techs: dict[str, Tech] = {}
        for branch in payload["branches"]:
            exclusive = branch.get("exclusive_country_code")
            for item in branch["techs"]:
                tier = self.tiers[item["tier"]]
                self.techs[item["id"]] = Tech(
                    id=item["id"],
                    title=item["title"],
                    tier=tier["label"],
                    hours=int(tier["hours"]),
                    cost=int(tier["cost"]),
                    branch_id=branch["id"],
                    branch_title=branch["title"],
                    requires=tuple(item.get("requires") or ()),
                    building_required=item.get("building_required"),
                    exclusive_country_code=exclusive,
                )

    def get(self, tech_id: str) -> Tech | None:
        return self.techs.get(tech_id)

    def can_research(self, tech: Tech, country_code: str) -> tuple[bool, str]:
        if tech.exclusive_country_code and tech.exclusive_country_code != country_code:
            return False, self.denial
        return True, "OK"


class WarlordDB:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS countries(code TEXT PRIMARY KEY,title TEXT NOT NULL,ruler_id INTEGER NOT NULL DEFAULT 0,budget INTEGER NOT NULL DEFAULT 50000,citizens INTEGER NOT NULL DEFAULT 100,soldiers INTEGER NOT NULL DEFAULT 20,factories INTEGER NOT NULL DEFAULT 0,ports INTEGER NOT NULL DEFAULT 0,tax_level TEXT NOT NULL DEFAULT 'medium',stability INTEGER NOT NULL DEFAULT 60,happiness INTEGER NOT NULL DEFAULT 55,last_tick INTEGER NOT NULL DEFAULT 0)")
            await db.execute("CREATE TABLE IF NOT EXISTS channel_bindings(chat_id INTEGER PRIMARY KEY,country_code TEXT NOT NULL)")
            await db.execute("CREATE TABLE IF NOT EXISTS completed_techs(country_code TEXT NOT NULL,tech_id TEXT NOT NULL,completed_at INTEGER NOT NULL,PRIMARY KEY(country_code,tech_id))")
            await db.execute("CREATE TABLE IF NOT EXISTS research_projects(id INTEGER PRIMARY KEY AUTOINCREMENT,country_code TEXT NOT NULL,tech_id TEXT NOT NULL,started_at INTEGER NOT NULL,complete_at INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'active')")
            await db.execute("CREATE TABLE IF NOT EXISTS economy_ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,country_code TEXT NOT NULL,delta INTEGER NOT NULL,reason TEXT NOT NULL,created_at INTEGER NOT NULL)")
            await db.commit()

    async def wipe(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            for table in ("countries", "channel_bindings", "completed_techs", "research_projects", "economy_ledger"):
                await db.execute(f"DELETE FROM {table}")
            await db.commit()

    async def bind_country(self, user_id: int, code: str, title: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO countries(code,title,ruler_id) VALUES(?,?,?) ON CONFLICT(code) DO UPDATE SET title=excluded.title,ruler_id=excluded.ruler_id", (code, title, user_id))
            await db.commit()

    async def bind_channel(self, chat_id: int, country_code: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO channel_bindings(chat_id,country_code) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET country_code=excluded.country_code", (chat_id, country_code))
            await db.commit()

    async def country_by_channel(self, chat_id: int) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute("SELECT country_code FROM channel_bindings WHERE chat_id=?", (chat_id,))).fetchone()
        return str(row[0]) if row else None

    async def get_country(self, code: str) -> sqlite3.Row | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return await (await db.execute("SELECT * FROM countries WHERE code=?", (code,))).fetchone()

    async def completed(self, code: str) -> set[str]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute("SELECT tech_id FROM completed_techs WHERE country_code=?", (code,))).fetchall()
        return {str(r[0]) for r in rows}

    async def active_count(self, code: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute("SELECT COUNT(*) FROM research_projects WHERE country_code=? AND status='active'", (code,))).fetchone()
        return int(row[0])

    async def start_research(self, code: str, tech: Tech) -> tuple[bool, str]:
        country = await self.get_country(code)
        if not country:
            return False, "Страна не зарегистрирована. Используй /register код Название."
        if int(country["budget"]) < tech.cost:
            return False, "Недостаточно средств в казне."
        if await self.active_count(code) >= 2:
            return False, "Лимит: максимум 2 исследования одновременно."
        completed = await self.completed(code)
        missing = [r for r in tech.requires if r not in completed]
        if missing:
            return False, "Не выполнены требования: " + ", ".join(missing)
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE countries SET budget=budget-? WHERE code=?", (tech.cost, code))
            await db.execute("INSERT INTO research_projects(country_code,tech_id,started_at,complete_at) VALUES(?,?,?,?)", (code, tech.id, now, now + tech.hours * 3600))
            await db.execute("INSERT INTO economy_ledger(country_code,delta,reason,created_at) VALUES(?,?,?,?)", (code, -tech.cost, f"research:{tech.id}", now))
            await db.commit()
        return True, f"🔬 Исследование начато: {tech.title}. Срок: {tech.hours}ч. Стоимость: {tech.cost} руб."

    async def complete_due_research(self) -> list[tuple[str, str]]:
        now = int(time.time())
        done: list[tuple[str, str]] = []
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute("SELECT id,country_code,tech_id FROM research_projects WHERE status='active' AND complete_at<=?", (now,))).fetchall()
            for project_id, code, tech_id in rows:
                await db.execute("UPDATE research_projects SET status='done' WHERE id=?", (project_id,))
                await db.execute("INSERT OR IGNORE INTO completed_techs(country_code,tech_id,completed_at) VALUES(?,?,?)", (code, tech_id, now))
                done.append((str(code), str(tech_id)))
            await db.commit()
        return done

    async def economy_tick(self) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute("SELECT code,budget,citizens,soldiers,factories,ports,tax_level,last_tick,stability FROM countries")).fetchall()
            for code, budget, citizens, soldiers, factories, ports, tax_level, last_tick, stability in rows:
                if now - int(last_tick or 0) < ECONOMY_TICK_SECONDS:
                    continue
                multiplier = TAX_MULTIPLIERS.get(str(tax_level), 1.0)
                income = int(1000 + int(factories) * 500 + int(ports) * 300 + multiplier * int(citizens))
                expense = int(soldiers) * 5 + int(citizens) * 2
                delta = income - expense
                new_stability = max(0, min(100, int(stability) - (2 if str(tax_level) == "extreme" else 0)))
                await db.execute("UPDATE countries SET budget=MAX(0,budget+?),stability=?,last_tick=? WHERE code=?", (delta, new_stability, now, code))
                await db.execute("INSERT INTO economy_ledger(country_code,delta,reason,created_at) VALUES(?,?,?,?)", (code, delta, "economy_tick", now))
            await db.commit()


def normalize_country_code(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Zа-яА-Я0-9_-]+", "_", value.strip().lower()).strip("_")
    aliases = {"паониция": "paonitsiya", "paonitsiya": "paonitsiya"}
    return aliases.get(cleaned, cleaned)


def detect_tech_ban(text: str) -> str | None:
    low = text.lower().replace("ё", "е")
    for needle, reason in TECH_BAN_PATTERNS.items():
        if needle in low:
            return "⛔ " + reason
    return None


async def ask_llm(question: str) -> str:
    guard = detect_tech_ban(question)
    if guard:
        return guard
    prompt = f"{RULES_TEXT}\n\nВопрос игрока: {question}\nОтветь по-русски, максимум 5 строк, без приветствий."
    if OPENAI_API_KEY:
        payload = json.dumps({"model": OPENAI_MODEL, "messages": [{"role": "system", "content": RULES_TEXT}, {"role": "user", "content": question}], "temperature": 0.2, "max_tokens": 260}).encode()
        req = urlrequest.Request("https://api.openai.com/v1/chat/completions", data=payload, headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}, method="POST")
        data = await asyncio.to_thread(lambda: json.loads(urlrequest.urlopen(req, timeout=25).read().decode()))
        return str(data["choices"][0]["message"]["content"]).strip()
    if GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 260}}).encode()
        req = urlrequest.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        data = await asyncio.to_thread(lambda: json.loads(urlrequest.urlopen(req, timeout=25).read().decode()))
        return str(data["candidates"][0]["content"]["parts"][0]["text"]).strip()
    return local_consultant(question)


def local_consultant(question: str) -> str:
    low = question.lower()
    if "оят" in low or "ядер" in low:
        return "☢️ ОЯТ доступно только Паониции (`country_code=paonitsiya`). Для остальных: ⚠️ Данная технология является закрытой национальной разработкой Паониции!"
    if "фабрик" in low:
        return "🎯 Фабрика\n• Цена/Условие: 15 000 вирт-руб.\n• Время/Лимит: 6ч; общий лимит стройки 1 здание + 2 НП/дороги.\n• Примечание: даёт +500/день."
    if "порт" in low:
        return "🎯 Порт\n• Цена/Условие: 35 000 вирт-руб.; только море.\n• Время/Лимит: 12ч.\n• Примечание: даёт +300/день."
    if "исслед" in low:
        return "🎯 Исследования\n• Цена/Условие: 1к/3к/7к/15к/30к по классу.\n• Время/Лимит: 6ч/12ч/24ч/48ч/72ч; максимум 2 одновременно.\n• Примечание: тяжёлые требуют здания."
    return "🎯 Правило\n• Цена/Условие: действует регламент WARLORD RP.\n• Время/Лимит: смотри лимиты стройки и исследований.\n• Примечание: запрещены PG, ресурсы из воздуха и Tech Ban."


async def setup_bot(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command="ask", description="Задать вопрос ИИ-консультанту"), BotCommand(command="rp_wipe", description="Новый сезон: очистить БД")], BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🔬 Древо Исследований", web_app=WebAppInfo(url=MINI_APP_URL)))


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("🔬 Древо исследований открывается через кнопку меню Telegram.\nНапиши вопрос в ЛС или используй /ask вопрос.")


@router.message(Command("ask"))
async def ask_command(message: Message) -> None:
    question = message.text.partition(" ")[2].strip() if message.text else ""
    if not question:
        await message.answer("Формат: /ask сколько стоит фабрика?")
        return
    await message.answer(html.escape(await ask_llm(question)), parse_mode="HTML")


@router.message(Command("rp_wipe"))
async def rp_wipe(message: Message, db: WarlordDB) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Недостаточно прав.")
        return
    await db.wipe()
    await message.answer("🧹 База WARLORD RP очищена. Новый сезон готов.")


@router.message(Command("register"))
async def register_country(message: Message, db: WarlordDB) -> None:
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Формат: /register код Название страны")
        return
    code = normalize_country_code(args[1])
    await db.bind_country(message.from_user.id, code, args[2].strip())
    await message.answer(f"✅ Страна зарегистрирована: {html.escape(args[2])} (`{code}`).", parse_mode="HTML")


@router.message(Command("bind_channel"))
async def bind_channel(message: Message, db: WarlordDB) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Формат: /bind_channel код_страны")
        return
    await db.bind_channel(message.chat.id, normalize_country_code(args[1]))
    await message.answer("✅ Канал привязан.")


@router.message(F.web_app_data)
async def web_app_data(message: Message, db: WarlordDB, catalog: TechCatalog) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.answer("⛔ Некорректные данные Mini App.")
        return
    if payload.get("type") == "research_start":
        code = normalize_country_code(str(payload.get("country_code") or ""))
        tech = catalog.get(str(payload.get("tech_id") or ""))
        if not tech:
            await message.answer("⛔ Технология не найдена.")
            return
        allowed, reason = catalog.can_research(tech, code)
        if not allowed:
            await message.answer(reason)
            return
        ok, text = await db.start_research(code, tech)
        await message.answer(text if ok else "⛔ " + text)
        return
    await message.answer("✅ Синхронизация принята.")


@router.channel_post()
async def channel_post(message: Message, db: WarlordDB) -> None:
    if not await db.country_by_channel(message.chat.id):
        return
    reason = detect_tech_ban(message.text or message.caption or "")
    if reason:
        logger.warning("Blocked channel post %s: %s", message.message_id, reason)


@router.message(F.chat.type == "private")
async def private_consultant(message: Message) -> None:
    if not message.text or message.text.startswith("/"):
        return
    await message.answer(html.escape(await ask_llm(message.text)), parse_mode="HTML")


async def scheduler(db: WarlordDB, catalog: TechCatalog, bot: Bot) -> None:
    while True:
        try:
            await db.economy_tick()
            for code, tech_id in await db.complete_due_research():
                tech = catalog.get(tech_id)
                logger.info("Research completed: %s %s", code, tech_id)
                if ADMIN_IDS and tech:
                    await bot.send_message(next(iter(ADMIN_IDS)), f"🔬 {code}: исследование завершено — {tech.title}.")
        except Exception:
            logger.exception("scheduler failed")
        await asyncio.sleep(30)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN/BOT_TOKEN is required")
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = WarlordDB(DB_PATH)
    await db.init()
    catalog = TechCatalog(TECHS_PATH)
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(db=db, catalog=catalog)
    dp.include_router(router)
    await setup_bot(bot)
    task = asyncio.create_task(scheduler(db, catalog, bot))
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
