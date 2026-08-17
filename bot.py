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
from aiogram.types import BotCommand, BotCommandScopeDefault, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("WARLORD_DB_PATH", ROOT / "warlord.sqlite3"))
TECHS_PATH = Path(os.getenv("WARLORD_TECHS_PATH", ROOT / "techs.json"))
BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com/index.html")
CARD_CHAT_ID = int(os.getenv("CARD_CHAT_ID", os.getenv("TARGET_CHAT_ID", "0")) or 0)
CARD_TOPIC_ID = int(os.getenv("CARD_TOPIC_ID", os.getenv("TARGET_TOPIC_ID", "0")) or 0) or None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
CARD_INTERVAL_SECONDS = int(os.getenv("CARD_INTERVAL_SECONDS", str(2 * 60 * 60)))
ADMIN_IDS = {int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "")))}

TAX_LEVELS = {"low": ("Пониженный", 0.5), "medium": ("Средний", 1.0), "high": ("Повышенный", 1.5), "extreme": ("Чрезмерный", 2.0)}
SETTLEMENT_CAPACITY = {"Деревня": 30, "Село": 50, "Посёлок": 70, "ПГТ": 40, "Город": 120, "Столица": 200}
FORBIDDEN_PATTERNS = {
    "танк": "Танки запрещены Tech Ban.", "бмп": "БМП запрещены Tech Ban.", "гусенич": "Тяжёлая гусеничная бронетехника запрещена Tech Ban.",
    "рсзо": "РСЗО запрещены Tech Ban.", "самолет": "Пилотируемая авиация запрещена Tech Ban.", "самолёт": "Пилотируемая авиация запрещена Tech Ban.",
    "вертолет": "Пилотируемая авиация запрещена Tech Ban.", "вертолёт": "Пилотируемая авиация запрещена Tech Ban.", "ядер": "Ядерное ОМП запрещено Tech Ban.",
    "химическ": "Химическое ОМП запрещено Tech Ban.", "крейсер": "Крупные корабли запрещены Tech Ban.", "эсмин": "Крупные корабли запрещены Tech Ban."
}
NON_RP_ROOTS = ("нонрп", "нерп", "мета", "ooc", "админ", "правил", "мем", "рофл", "irl")
PG_ROOTS = ("мгновенно", "без потерь", "неуязв", "бесконеч", "миллион", "телепорт", "из воздуха")
RULES_CONTEXT = """
Экономика WARLORD RP: доход в день = 1000 + фабрики*500 + порты*300 + налог*население. Расход в день = солдаты*5 + граждане*2 + R&D.
Стройка: максимум 1 здание + 2 НП/дороги одновременно. Исследования: максимум 2 одновременно.
Tech Ban: танки, БМП, тяжёлая гусеничная бронетехника, РСЗО, пилотируемая авиация, ядерное/химическое ОМП массового поражения, крупные корабли.
ОЯТ доступно только Паониции country_code=paonitsiya.
Ответ всегда по шаблону: 🎯 Название\n• Цена/Условие: ...\n• Время/Лимит: ...\n• Примечание: ...
""".strip()

router = Router(name="warlord_autonomy")
logger = logging.getLogger("warlord")


@dataclass(frozen=True, slots=True)
class Tech:
    id: str
    title: str
    hours: int
    cost: int
    daily_upkeep: int
    requires: tuple[str, ...]
    building_required: str | None
    exclusive_country_code: str | None


class TechCatalog:
    def __init__(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.denial = str(payload["exclusive_denial"])
        self.techs: dict[str, Tech] = {}
        for branch in payload["branches"]:
            exclusive = branch.get("exclusive_country_code")
            for item in branch["techs"]:
                tier = payload["tiers"].get(item["tier"], {})
                self.techs[item["id"]] = Tech(
                    id=item["id"], title=item["title"], hours=int(item.get("hours", tier.get("hours", 0))),
                    cost=int(item.get("cost", tier.get("cost", 0))), daily_upkeep=int(item.get("daily_upkeep", tier.get("daily_upkeep", 0))),
                    requires=tuple(item.get("requires") or ()), building_required=item.get("building_required"), exclusive_country_code=exclusive,
                )

    def get(self, tech_id: str) -> Tech | None:
        return self.techs.get(tech_id)

    def find(self, text: str) -> Tech | None:
        low = normalize_text(text)
        for tech in self.techs.values():
            if normalize_text(tech.id) in low or normalize_text(tech.title) in low:
                return tech
        return None


class WarlordDB:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS countries(
                code TEXT PRIMARY KEY,title TEXT NOT NULL,ruler_id INTEGER NOT NULL DEFAULT 0,ruler_username TEXT NOT NULL DEFAULT '',party TEXT NOT NULL DEFAULT '-',ideology TEXT NOT NULL DEFAULT '-',
                channel_id INTEGER,channel_username TEXT NOT NULL DEFAULT '',has_channel_avatar INTEGER NOT NULL DEFAULT 0,flag_file_id TEXT NOT NULL DEFAULT '',card_message_id INTEGER,
                budget INTEGER NOT NULL DEFAULT 50000,citizens INTEGER NOT NULL DEFAULT 100,soldiers INTEGER NOT NULL DEFAULT 20,tax_level TEXT NOT NULL DEFAULT 'medium',
                stability INTEGER NOT NULL DEFAULT 60,war_support INTEGER NOT NULL DEFAULT 40,happiness INTEGER NOT NULL DEFAULT 55,last_card_ts INTEGER NOT NULL DEFAULT 0)""")
            await db.execute("CREATE TABLE IF NOT EXISTS buildings(country_code TEXT NOT NULL,name TEXT NOT NULL,count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(country_code,name))")
            await db.execute("CREATE TABLE IF NOT EXISTS settlements(country_code TEXT NOT NULL,name TEXT NOT NULL,count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(country_code,name))")
            await db.execute("CREATE TABLE IF NOT EXISTS registered_channels(chat_id INTEGER PRIMARY KEY,country_code TEXT NOT NULL)")
            await db.execute("CREATE TABLE IF NOT EXISTS completed_techs(country_code TEXT NOT NULL,tech_id TEXT NOT NULL,completed_at INTEGER NOT NULL,PRIMARY KEY(country_code,tech_id))")
            await db.execute("CREATE TABLE IF NOT EXISTS research_projects(id INTEGER PRIMARY KEY AUTOINCREMENT,country_code TEXT NOT NULL,tech_id TEXT NOT NULL,started_at INTEGER NOT NULL,complete_at INTEGER NOT NULL,remaining_seconds INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'ACTIVE')")
            await db.execute("CREATE TABLE IF NOT EXISTS news_events(id INTEGER PRIMARY KEY AUTOINCREMENT,country_code TEXT NOT NULL,chat_id INTEGER NOT NULL,message_id INTEGER NOT NULL,text TEXT NOT NULL,line_count INTEGER NOT NULL,violation TEXT NOT NULL DEFAULT '',created_at INTEGER NOT NULL,processed_card INTEGER NOT NULL DEFAULT 0)")
            await db.commit()

    async def register_country(self, code: str, title: str, ruler_id: int, username: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO countries(code,title,ruler_id,ruler_username) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET title=excluded.title,ruler_id=excluded.ruler_id,ruler_username=excluded.ruler_username", (code, title, ruler_id, username))
            await db.execute("INSERT OR IGNORE INTO settlements(country_code,name,count) VALUES(?,?,1)", (code, "Столица"))
            await db.commit()

    async def bind_channel(self, chat_id: int, code: str, username: str, has_avatar: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO registered_channels(chat_id,country_code) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET country_code=excluded.country_code", (chat_id, code))
            await db.execute("UPDATE countries SET channel_id=?,channel_username=?,has_channel_avatar=? WHERE code=?", (chat_id, username, int(has_avatar), code))
            await db.commit()

    async def country_by_channel(self, chat_id: int) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute("SELECT country_code FROM registered_channels WHERE chat_id=?", (chat_id,))).fetchone()
        return str(row[0]) if row else None

    async def countries(self) -> list[sqlite3.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return await (await db.execute("SELECT * FROM countries ORDER BY title")).fetchall()

    async def country(self, code: str) -> sqlite3.Row | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return await (await db.execute("SELECT * FROM countries WHERE code=?", (code,))).fetchone()

    async def counts(self, table: str, code: str) -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(f"SELECT name,count FROM {table} WHERE country_code=?", (code,))).fetchall()
        return {str(name): int(count) for name, count in rows}

    async def completed(self, code: str) -> set[str]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute("SELECT tech_id FROM completed_techs WHERE country_code=?", (code,))).fetchall()
        return {str(r[0]) for r in rows}

    async def active_research(self, code: str) -> list[sqlite3.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return await (await db.execute("SELECT * FROM research_projects WHERE country_code=? AND status IN ('ACTIVE','PAUSED') ORDER BY id", (code,))).fetchall()

    async def start_research(self, code: str, tech: Tech) -> tuple[bool, str]:
        country = await self.country(code)
        if not country:
            return False, "Страна не зарегистрирована."
        if tech.exclusive_country_code and tech.exclusive_country_code != code:
            return False, "⚠️ Данная технология является закрытой национальной разработкой Паониции!"
        active = await self.active_research(code)
        if sum(1 for r in active if r["status"] == "ACTIVE") >= 2:
            return False, "Лимит исследований: максимум 2 одновременно."
        done = await self.completed(code)
        missing = [r for r in tech.requires if r not in done]
        if missing:
            return False, "Не выполнены компоненты: " + ", ".join(missing)
        if int(country["budget"]) < tech.cost:
            return False, "Недостаточно ВР в казне."
        buildings = await self.counts("buildings", code)
        if tech.building_required and buildings.get(tech.building_required, 0) <= 0:
            return False, f"Требуется здание: {tech.building_required}."
        now = int(time.time())
        duration = int(tech.hours * 3600 * (0.8 if buildings.get("Исследовательский центр", 0) > 0 else 1.0))
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE countries SET budget=budget-? WHERE code=?", (tech.cost, code))
            if duration <= 0:
                await db.execute("INSERT OR IGNORE INTO completed_techs(country_code,tech_id,completed_at) VALUES(?,?,?)", (code, tech.id, now))
            else:
                await db.execute("INSERT INTO research_projects(country_code,tech_id,started_at,complete_at,remaining_seconds,status) VALUES(?,?,?,?,?,'ACTIVE')", (code, tech.id, now, now + duration, duration))
            await db.commit()
        return True, f"🔬 Исследование принято: {tech.title}. Цена: {tech.cost} ВР. Время: {max(0, duration // 3600)}ч. R&D: -{tech.daily_upkeep} ВР/день."

    async def remember_news(self, code: str, chat_id: int, message_id: int, text: str, violation: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO news_events(country_code,chat_id,message_id,text,line_count,violation,created_at) VALUES(?,?,?,?,?,?,?)", (code, chat_id, message_id, text[:3500], max(1, len([x for x in text.splitlines() if x.strip()])), violation, int(time.time())))
            await db.commit()

    async def recent_news(self, code: str) -> list[sqlite3.Row]:
        since = int(time.time()) - CARD_INTERVAL_SECONDS
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return await (await db.execute("SELECT * FROM news_events WHERE country_code=? AND created_at>=? ORDER BY id DESC LIMIT 20", (code, since))).fetchall()

    async def recalc_country(self, code: str, catalog: TechCatalog) -> dict[str, Any]:
        c = await self.country(code)
        if not c:
            return {}
        buildings = await self.counts("buildings", code)
        settlements = await self.counts("settlements", code)
        active = await self.active_research(code)
        research_upkeep = sum((catalog.get(r["tech_id"]).daily_upkeep if catalog.get(r["tech_id"]) else 0) for r in active if r["status"] == "ACTIVE")
        tax_label, tax_mult = TAX_LEVELS.get(c["tax_level"], TAX_LEVELS["medium"])
        income = int(1000 + buildings.get("Фабрика", 0) * 500 + buildings.get("Порт", 0) * 300 + tax_mult * int(c["citizens"]))
        expense = int(c["soldiers"]) * 5 + int(c["citizens"]) * 2 + research_upkeep
        budget_delta = income - expense
        events = await self.recent_news(code)
        rp_events = [e for e in events if not e["violation"] and int(e["line_count"]) > 1]
        one_line_spam = [e for e in events if int(e["line_count"]) <= 1]
        violations = [e["violation"] for e in events if e["violation"]]
        citizen_delta = min(15, len(rp_events) * 3)
        happiness_delta = min(4, len(rp_events)) - min(6, len(violations) * 2) - (2 if c["tax_level"] == "extreme" else 0)
        stability_delta = min(3, len(rp_events)) - min(8, len(violations) * 3) - (3 if c["tax_level"] == "extreme" else 0)
        war_support_delta = min(4, sum(1 for e in rp_events if any(w in normalize_text(e["text"]) for w in ("оборон", "мобилизац", "патрул"))))
        paused = []
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE countries SET budget=budget+?,citizens=citizens+?,happiness=MAX(0,MIN(100,happiness+?)),stability=MAX(0,MIN(100,stability+?)),war_support=MAX(0,MIN(100,war_support+?)),last_card_ts=? WHERE code=?", (budget_delta, citizen_delta, happiness_delta, stability_delta, war_support_delta, now, code))
            updated = await (await db.execute("SELECT budget FROM countries WHERE code=?", (code,))).fetchone()
            if updated and int(updated[0]) < 0:
                rows = await (await db.execute("SELECT id,tech_id,complete_at FROM research_projects WHERE country_code=? AND status='ACTIVE'", (code,))).fetchall()
                for pid, tech_id, complete_at in rows:
                    await db.execute("UPDATE research_projects SET status='PAUSED',remaining_seconds=? WHERE id=?", (max(1, int(complete_at) - now), pid))
                    paused.append(str(tech_id))
            due = await (await db.execute("SELECT id,tech_id FROM research_projects WHERE country_code=? AND status='ACTIVE' AND complete_at<=?", (code, now))).fetchall()
            for pid, tech_id in due:
                await db.execute("UPDATE research_projects SET status='DONE' WHERE id=?", (pid,))
                await db.execute("INSERT OR IGNORE INTO completed_techs(country_code,tech_id,completed_at) VALUES(?,?,?)", (code, tech_id, now))
            await db.commit()
        new_c = await self.country(code)
        return {"old": c, "new": new_c, "buildings": buildings, "settlements": settlements, "active": active, "events": events, "violations": violations, "one_line_spam": one_line_spam, "income": income, "expense": expense, "research_upkeep": research_upkeep, "deltas": {"citizens": citizen_delta, "budget": budget_delta, "happiness": happiness_delta, "stability": stability_delta, "war_support": war_support_delta}, "paused": paused, "tax_label": tax_label}

    async def save_card_id(self, code: str, message_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE countries SET card_message_id=? WHERE code=?", (message_id, code))
            await db.commit()


def normalize_text(text: str) -> str:
    return text.lower().replace("ё", "е")


def normalize_country_code(text: str) -> str:
    cleaned = re.sub(r"[^a-zа-я0-9_-]+", "_", normalize_text(text)).strip("_")
    return {"паониция": "paonitsiya", "paonitsiya": "paonitsiya"}.get(cleaned, cleaned)


def find_violation(text: str) -> str:
    low = normalize_text(text)
    for key, reason in FORBIDDEN_PATTERNS.items():
        if key in low:
            return reason
    if any(x in low for x in NON_RP_ROOTS):
        return "Нон-РП/OOC/метагейминг."
    if any(x in low for x in PG_ROOTS):
        return "PG/нереалистичное преимущество."
    return ""


def fmt_delta(value: int) -> str:
    return f" ({value:+d})" if value else ""


def fmt_list(items: dict[str, int]) -> str:
    return ", ".join(f"{k}×{v}" for k, v in items.items() if v > 0) or "-"


def consultation_template(title: str, price: str, limit: str, note: str) -> str:
    return f"🎯 {title}\n• Цена/Условие: {price}\n• Время/Лимит: {limit}\n• Примечание: {note}"


async def consult(question: str, catalog: TechCatalog) -> str:
    violation = find_violation(question)
    if violation and any(k in normalize_text(question) for k in FORBIDDEN_PATTERNS):
        return consultation_template("Tech Ban", "Запрещено", "Постоянный запрет", violation)
    tech = catalog.find(question)
    if tech:
        req = ", ".join(tech.requires) or "нет"
        building = f"; здание: {tech.building_required}" if tech.building_required else ""
        if tech.exclusive_country_code:
            building += "; только Паониция"
        return consultation_template(tech.title, f"{tech.cost} ВР; R&D -{tech.daily_upkeep} ВР/день", f"{tech.hours}ч; максимум 2 исследования", f"Требования: {req}{building}.")
    low = normalize_text(question)
    local = {
        "фабрик": consultation_template("Фабрика", "15 000 ВР", "6ч; максимум 1 здание одновременно", "+500 ВР/день."),
        "порт": consultation_template("Порт", "35 000 ВР; только море", "12ч; максимум 1 здание одновременно", "+300 ВР/день."),
        "налог": consultation_template("Налоги", "Пониженный 0.5 / Средний 1.0 / Повышенный 1.5 / Чрезмерный 2.0", "Меняется решением страны", "Чрезмерный налог повышает риск восстаний."),
        "строй": consultation_template("Лимит стройки", "По цене объекта", "Максимум 1 здание + 2 НП/дороги одновременно", "НП и дороги считаются отдельно от здания."),
        "исслед": consultation_template("Лимит исследований", "По цене компонента + ежедневный R&D", "Максимум 2 исследования одновременно", "При казне <0 активные R&D замораживаются."),
        "оят": consultation_template("ОЯТ", "Только Паониция", "Ветка вырезается из DOM для остальных", "⚠️ Данная технология является закрытой национальной разработкой Паониции!"),
    }
    for key, answer in local.items():
        if key in low:
            return answer
    if OPENAI_API_KEY:
        payload = json.dumps({"model": OPENAI_MODEL, "messages": [{"role": "system", "content": RULES_CONTEXT}, {"role": "user", "content": question}], "temperature": 0.1, "max_tokens": 220}).encode("utf-8")
        req = urlrequest.Request("https://api.openai.com/v1/chat/completions", data=payload, headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}, method="POST")
        data = await asyncio.to_thread(lambda: json.loads(urlrequest.urlopen(req, timeout=20).read().decode("utf-8")))
        return str(data["choices"][0]["message"]["content"]).strip()
    return consultation_template("Правило WARLORD RP", "По регламенту экономики и Tech Ban", "Лимиты: 1 здание + 2 НП/дороги; 2 исследования", "PG, Нон-РП, метагейминг и однострочный спам не дают бонусов.")


def render_card(data: dict[str, Any], catalog: TechCatalog) -> str:
    c, n, d = data["old"], data["new"], data["deltas"]
    capacity = sum(SETTLEMENT_CAPACITY.get(k, 0) * v for k, v in data["settlements"].items()) or 200
    active_lines = []
    now = int(time.time())
    for r in data["active"]:
        tech = catalog.get(r["tech_id"])
        if tech:
            left = max(0, int(r["complete_at"]) - now) // 3600 if r["status"] == "ACTIVE" else max(0, int(r["remaining_seconds"])) // 3600
            active_lines.append(f"{html.escape(tech.title)} ({r['status']}, {left}ч, -{tech.daily_upkeep} ВР/день)")
    summaries = [e["text"].strip().splitlines()[0][:180] for e in data["events"] if not e["violation"] and int(e["line_count"]) > 1]
    if not summaries:
        summaries = ["За период значимых RP-событий не зафиксировано."]
    notices: list[str] = []
    if not n["flag_file_id"]:
        mention = f"@{n['ruler_username']}" if n["ruler_username"] else f"правитель ID {n['ruler_id']}"
        if n["channel_id"] and int(n["has_channel_avatar"]):
            notices.append(f"⚠️ {mention}, для твоей страны {n['title']} не прикреплена фотография флага. Отправь изображение/картинку флага или дай согласие использовать аватарку твоего канала!")
        else:
            notices.append(f"⚠️ {mention}, для твоей страны {n['title']} не прикреплена фотография флага. Пожалуйста, пришли изображение/картинку флага!")
    if data["paused"]:
        notices.append("⛔ R&D заморожено из-за отрицательной казны: " + ", ".join(data["paused"]))
    if data["violations"]:
        notices.append("⛔ Санкции/нарушения: " + "; ".join(sorted(set(data["violations"]))))
    if data["one_line_spam"]:
        notices.append(f"⚠️ Однострочный спам не дал бонусов: {len(data['one_line_spam'])} пост(ов).")
    if not notices:
        notices.append("Нарушений не выявлено")
    return (
        f"[Фото флага отсутствует]\n" if not n["flag_file_id"] else "[🖼 Фотография флага прикрепится медиа-файлом к посту]\n"
    ) + (
        f"ГОСУДАРСТВО: <b>{html.escape(n['title'])}</b>\n"
        f"👑 Правитель: {html.escape(n['ruler_username'] or str(n['ruler_id']) or '-')}\n"
        f"🏛 Партия: {html.escape(n['party'])} | 👁 Идеология: {html.escape(n['ideology'])}\n\n"
        "📊 <b>ГОСУДАРСТВЕННЫЕ ПОКАЗАТЕЛИ:</b>\n"
        f"👥 Население: {n['citizens']}{fmt_delta(d['citizens'])} (Вместимость: {capacity})\n"
        f"💰 Казна: {n['budget']} вирт-руб.{fmt_delta(d['budget'])} <i>(Доход: +{data['income']} / Расход: -{data['expense']} / R&amp;D: -{data['research_upkeep']})</i>\n"
        f"🪖 Армия: {n['soldiers']} солдат\n"
        f"📊 Налоги: {data['tax_label']}\n\n"
        "🏭 <b>ИНФРАСТРУКТУРА И ЭКОНОМИКА:</b>\n"
        f"• Населённые пункты: {html.escape(fmt_list(data['settlements']))}\n"
        f"• Промышленность: {html.escape(fmt_list(data['buildings']))}\n"
        f"• Исследования: {'; '.join(active_lines) if active_lines else 'Нет'}\n\n"
        "⚖️ <b>ОБЩЕСТВЕННОЕ СОСТОЯНИЕ:</b>\n"
        f"📉 Стабильность: {n['stability']}%{fmt_delta(d['stability'])}\n"
        f"⚔️ Поддержка войны: {n['war_support']}%{fmt_delta(d['war_support'])}\n"
        f"😊 Счастье народа: {n['happiness']}%{fmt_delta(d['happiness'])}\n\n"
        "📝 <b>ИТОГИ ЗА 2 ЧАСА:</b>\n• " + "\n• ".join(html.escape(s) for s in summaries[:4]) + "\n\n"
        "⚠️ <b>УВЕДОМЛЕНИЯ И АВТО-ЗАПРОСЫ:</b>\n" + "\n".join(html.escape(x) for x in notices)
    )


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Опубликовать новость", callback_data="publish_news")]])


async def setup_bot(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command="bot", description="Консультант WARLORD RP"), BotCommand(command="register", description="Регистрация страны")], BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🔬 Древо Исследований", web_app=WebAppInfo(url=MINI_APP_URL)))


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("Меню доступно через кнопку Telegram WebApp.", reply_markup=main_keyboard())


@router.message(Command("bot"))
async def bot_consultant(message: Message, catalog: TechCatalog) -> None:
    question = (message.text or "").partition(" ")[2].strip() or "правила"
    await message.answer(html.escape(await consult(question, catalog)), parse_mode="HTML")


@router.message(Command("register"))
async def register(message: Message, db: WarlordDB) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /register paonitsiya Паониция")
        return
    await db.register_country(normalize_country_code(parts[1]), parts[2].strip(), message.from_user.id, message.from_user.username or "")
    await message.answer("✅ Страна зарегистрирована.", reply_markup=main_keyboard())


@router.message(Command("bind_channel"))
async def bind_channel(message: Message, db: WarlordDB) -> None:
    if ADMIN_IDS and message.from_user.id not in ADMIN_IDS:
        return
    code = normalize_country_code((message.text or "").partition(" ")[2].strip())
    if not code:
        await message.answer("Формат: /bind_channel country_code")
        return
    chat = await message.bot.get_chat(message.chat.id)
    has_avatar = bool(getattr(chat, "photo", None))
    await db.bind_channel(message.chat.id, code, getattr(chat, "username", None) or "", has_avatar)
    await message.answer("✅ Канал привязан к стране.")


@router.message(F.web_app_data)
async def web_app_payload(message: Message, db: WarlordDB, catalog: TechCatalog) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.answer("⛔ Некорректные данные WebApp.")
        return
    if payload.get("type") == "research_start":
        code = normalize_country_code(str(payload.get("country_code") or ""))
        tech = catalog.get(str(payload.get("tech_id") or ""))
        if not tech:
            await message.answer("⛔ Технология не найдена.")
            return
        ok, text = await db.start_research(code, tech)
        await message.answer(text if ok else "⛔ " + text)
        return
    await message.answer("✅ Синхронизация принята.")


@router.callback_query(F.data == "publish_news")
async def publish_news_button(callback) -> None:
    await callback.answer()
    await callback.message.answer("📢 Отправь новость в зарегистрированный Telegram-канал страны. Незарегистрированные каналы бот молча игнорирует.")


@router.channel_post()
async def silent_listener(message: Message, db: WarlordDB) -> None:
    code = await db.country_by_channel(message.chat.id)
    if not code:
        return
    text = (message.text or message.caption or "").strip()
    if not text:
        return
    violation = find_violation(text)
    await db.remember_news(code, message.chat.id, message.message_id, text, violation)


@router.message(F.text)
async def passive_consultant(message: Message, catalog: TechCatalog) -> None:
    text = (message.text or "").strip()
    if message.chat.type == "private" and not text.startswith("/"):
        await message.answer(html.escape(await consult(text, catalog)), parse_mode="HTML")


async def card_loop(db: WarlordDB, catalog: TechCatalog, bot: Bot) -> None:
    while True:
        try:
            if CARD_CHAT_ID:
                for country in await db.countries():
                    data = await db.recalc_country(country["code"], catalog)
                    if not data:
                        continue
                    text = render_card(data, catalog)
                    msg_id = data["new"]["card_message_id"]
                    if msg_id:
                        try:
                            await bot.edit_message_text(text, CARD_CHAT_ID, int(msg_id), parse_mode="HTML", link_preview_options=None)
                            continue
                        except Exception:
                            logger.exception("card edit failed; posting a new card")
                    sent = await bot.send_message(CARD_CHAT_ID, text, parse_mode="HTML", message_thread_id=CARD_TOPIC_ID)
                    await db.save_card_id(country["code"], sent.message_id)
        except Exception:
            logger.exception("card loop failed")
        await asyncio.sleep(CARD_INTERVAL_SECONDS)


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
    task = asyncio.create_task(card_loop(db, catalog, bot))
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
