import asyncio
import calendar
import json
import logging
import random
import re
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

from app.config import config
from app.core.models import IncomingPost
from app.filters.ai_guard import AIGuard
from app.filters.rp_filter import RPFilter
from app.formatters.news_formatter import NewsFormatter
from app.moderation.keyboards import moderation_keyboard
from app.parsers.emoji_packs import EmojiPackLoader
from app.parsers.rss_parser import RSSParser
from app.parsers.translator import AutoTranslator
from app.storage.database import Database
from app.utils.text_tools import autocorrect_news_text, content_hash, strip_emojis, strip_hashtags

logger = logging.getLogger(__name__)


class NewsService:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.user_client: TelegramClient | None = None
        self.rp_filter = RPFilter()
        self.ai_guard = AIGuard()
        self.formatter = NewsFormatter()
        self.translator = AutoTranslator()
        self.rss = RSSParser()
        self.emoji_loader = EmojiPackLoader(config.emoji_storage_path)
        self.pack_emoji_cache: dict[str, int] = self.emoji_loader.read_cache()
        self.queue: asyncio.Queue[IncomingPost] = asyncio.Queue(maxsize=3000)
        self.user_windows: dict[int, deque[int]] = {}
        self.action_windows: dict[int, deque[int]] = {}

    def attach_user_client(self, client: TelegramClient) -> None:
        self.user_client = client

    async def load_dynamic_config(self) -> None:
        raw_tags = await self.db.get_state("cfg:country_hashtags", "")
        raw_sources = await self.db.get_state("cfg:source_channels", "")
        try:
            if raw_tags:
                loaded_tags = json.loads(raw_tags)
                if isinstance(loaded_tags, dict):
                    for key, value in loaded_tags.items():
                        if isinstance(key, str) and isinstance(value, list):
                            config.country_hashtags[key] = [str(v).upper() if str(v).startswith("#") else f"#{str(v).upper()}" for v in value]
        except Exception:
            logger.exception("Failed to load dynamic hashtags config")

        try:
            if raw_sources:
                loaded_sources = json.loads(raw_sources)
                if isinstance(loaded_sources, dict):
                    for key, value in loaded_sources.items():
                        if isinstance(key, str) and isinstance(value, str):
                            config.source_channels[key] = value
        except Exception:
            logger.exception("Failed to load dynamic source-channels config")

    @staticmethod
    def _known_country_terms() -> set[str]:
        terms: set[str] = set()
        for country in config.country_hashtags.keys():
            terms.add(country.lower())
        for country in config.source_channels.keys():
            terms.add(country.lower())
        for aliases in config.country_aliases.values():
            for alias in aliases:
                terms.add(alias.lower())
        return terms

    @staticmethod
    def _known_country_hashtags() -> set[str]:
        tags: set[str] = set()
        for values in config.country_hashtags.values():
            for tag in values:
                normalized = str(tag).strip().upper()
                if not normalized.startswith("#"):
                    normalized = f"#{normalized}"
                tags.add(normalized)
        tags.add("#RP")
        return tags

    @staticmethod
    def _reject_reason_text(reason: str) -> str:
        mapping = {
            "WAR_ACTIONS_BLOCKED": "Обнаружены прямые военные действия (атака/обстрел/штурм).",
            "UNKNOWN_COUNTRY_MENTIONED": "Упомянута неизвестная RP-страна.",
            "NOT_RP_NEWS_ALLOWLIST": "Текст не похож на RP-новость по правилам.",
            "OOC_META_CONTENT": "Обнаружен OOC/meta контент.",
            "REAL_WORLD_CONTENT": "Обнаружены упоминания реального мира.",
            "BANNED_ALLIANCE_NAME": "Обнаружено запрещённое название/маскировка.",
            "WAR_WITHOUT_RP_PROCESS": "Военная тематика без допустимого RP-процесса.",
            "TOO_SHORT_OR_NO_RP_EVENT": "Слишком короткий текст без RP-события.",
            "MILITARY_REVIEW_REQUIRED": "Военная новость отправлена на модерацию.",
            "UNKNOWN_COUNTRY_HASHTAG": "Указан хештег страны, которой нет в системе.",
            "ARMY_LIMIT_EXCEEDED_200": "Численность армии превышает допустимый лимит (до 200).",
            "ARMY_UNREALISTIC_TOO_SMALL": "Численность армии ниже допустимого минимума (от 50).",
            "FORBIDDEN_WEAPON_TYPE": "Обнаружен запрещённый тип оружия/технологии по правилам РП.",
            "FORBIDDEN_HEAVY_EQUIPMENT": "Обнаружена запрещённая тяжёлая техника/авиация/корабли.",
            "FORBIDDEN_STRUCTURE_OR_ABUSE": "Обнаружены запрещённые действия (доксинг/угрозы/вне-системные структуры).",
            "WAR_WITHOUT_EVIDENCE": "Военные действия без подтверждающих кадров/видео запрещены.",
        }
        return mapping.get(reason, f"Новость не прошла фильтр: {reason}.")

    @staticmethod
    def _extract_special_markers(text: str) -> str:
        markers = {
            "#РП": "👑",
            "#НРП": "⭐️",
            "#НОВЫЕВВЕДЕНИЯ": "🔄",
            "#КАРТА": "🌐",
            "#MAP": "🌐",
            "#NAMEMAP": "❓",
            "#ALMAP": "👀",
            "#ТЕРАКТ": "⚠️",
            "#MKS20": "❄️",
            "#MKS40": "⚠️",
        }
        normalized_markers = {k.upper(): v for k, v in markers.items()}
        cleaned = text
        for marker, emoji in normalized_markers.items():
            pattern = re.compile(rf"(?i)(?<!\w){re.escape(marker)}(?!\w)(?:[,.;:!?])?")
            if pattern.search(cleaned):
                cleaned = pattern.sub("", cleaned)
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"([,.;:!?]){2,}", r"\1", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" \n\t,;.")
        return cleaned

    def _render_post(self, post: IncomingPost, text: str) -> tuple[str, list]:
        rewritten = self.formatter.rewrite(post.source_country, text)
        return self.formatter.format_news_entities(
            country=post.source_country,
            text=rewritten,
            country_hashtags=config.country_hashtags,
            premium_emoji_ids=config.premium_emoji_ids,
            country_aliases=config.country_aliases,
        )

    @staticmethod
    def _mentioned_countries(text: str, source_country: str) -> list[str]:
        low = text.lower()
        out: list[str] = []
        for country, aliases in config.country_aliases.items():
            if country == source_country:
                continue
            probes = [country.lower(), *(a.lower() for a in aliases)]
            if any(p in low for p in probes):
                out.append(country)
        return out

    async def _apply_diplomacy_and_tech(self, post: IncomingPost, text: str) -> None:
        upper = text.upper()
        mentions = self._mentioned_countries(text, post.source_country)
        if any(tag in upper for tag in ["#СОЮЗ", "#ALLIANCE"]):
            for country in mentions[:3]:
                await self.db.add_or_update_relation(post.source_country, country, "alliance")
                await self.db.adjust_diplomacy_counter(post.source_country, alliances_delta=1)
        if any(tag in upper for tag in ["#ДОГОВОР", "#PACT", "#НЕНАПАДЕНИЕ"]):
            for country in mentions[:3]:
                await self.db.add_or_update_relation(post.source_country, country, "treaty")
                await self.db.adjust_diplomacy_counter(post.source_country, treaties_delta=1)
        if any(tag in upper for tag in ["#ТЕХНОЛОГИЯ", "#ИССЛЕДОВАНИЕ", "#РАЗРАБОТКА"]):
            tech_name = re.sub(r"#\w+", "", text).strip()[:80] or "Неуточнённый проект"
            now_ts = int(time.time())
            await self.db.start_technology_project(post.source_country, tech_name, now_ts, now_ts + (3 * 24 * 3600))

    @staticmethod
    def _source_link(post: IncomingPost) -> str | None:
        channel = (post.source_channel or "").lstrip("@")
        if channel and channel.replace("_", "").isalnum() and post.message_id:
            return f"https://t.me/{channel}/{post.message_id}"
        return None

    @staticmethod
    def _country_genitive(country: str) -> str:
        if country.endswith("ия"):
            return f"{country[:-2]}ии"
        if country.endswith("а"):
            return f"{country[:-1]}ы"
        return f"{country}а"

    @staticmethod
    def _power_score(budget: int, army: int, citizens: int, life_level: int) -> int:
        return int((army * 2) + (budget // 1000) + (citizens // 20) + (life_level * 3))

    @staticmethod
    def _derive_country_stat_deltas(text: str, population: int = 100) -> tuple[int, int, int, int]:
        low = text.lower()
        budget_delta = 0
        army_delta = 0
        life_delta = 0
        citizens_delta = 0

        if any(k in low for k in ["реформ", "инвест", "завод", "производств", "эконом"]):
            budget_delta += 5000
            life_delta += 1
            citizens_delta += 20

        if any(k in low for k in ["учен", "трениров", "мобилизац", "призыв"]):
            values = [int(v) for v in re.findall(r"\b(\d{1,5})\b", low)]
            mobilization_cap = max(15, min(200, population // 20))
            if values:
                army_delta += min(max(values[0], 10), mobilization_cap)
            else:
                army_delta += mobilization_cap
            budget_delta -= 1000

        if any(k in low for k in ["обстрел", "штурм", "теракт", "кризис", "потер"]):
            budget_delta -= 3000
            life_delta -= 2
            citizens_delta -= 30

        if any(k in low for k in ["медицин", "школ", "университет", "соцпрограмм", "уровень жизни"]):
            life_delta += 2
            citizens_delta += 35

        return budget_delta, army_delta, life_delta, citizens_delta

    async def _apply_country_stats_effect(self, post: IncomingPost) -> None:
        if not post.source_country or post.source_country == "MANUAL":
            return
        population = await self.db.get_country_population(post.source_country)
        budget_delta, army_delta, life_delta, citizens_delta = self._derive_country_stat_deltas(post.text or "", population=population)
        if budget_delta == 0 and army_delta == 0 and life_delta == 0 and citizens_delta == 0:
            return
        await self.db.apply_country_stats_delta(
            post.source_country,
            budget_delta=budget_delta,
            army_delta=army_delta,
            life_delta=life_delta,
            citizens_delta=citizens_delta,
        )

    async def render_country_stats_card(self, country: str) -> str:
        rows = await self.db.list_country_stats()
        if not rows:
            return "Статистика стран пока пуста."

        by_army = sorted(rows, key=lambda r: r[2], reverse=True)
        by_budget = sorted(rows, key=lambda r: r[1], reverse=True)
        by_citizens = sorted(rows, key=lambda r: r[3], reverse=True)
        by_power = sorted(rows, key=lambda r: self._power_score(r[1], r[2], r[3], r[4]), reverse=True)

        target = next((r for r in rows if r[0].lower() == country.lower()), None)
        if not target:
            return "Для вашей страны пока нет данных в статистике."

        c_name, budget, army, citizens, life = target
        rank_army = next((idx + 1 for idx, row in enumerate(by_army) if row[0] == c_name), 0)
        rank_budget = next((idx + 1 for idx, row in enumerate(by_budget) if row[0] == c_name), 0)
        rank_citizens = next((idx + 1 for idx, row in enumerate(by_citizens) if row[0] == c_name), 0)
        rank_power = next((idx + 1 for idx, row in enumerate(by_power) if row[0] == c_name), 0)
        power = self._power_score(budget, army, citizens, life)
        gen = self._country_genitive(c_name)

        return (
            "<blockquote>"
            f"<tg-emoji emoji-id=\"{config.premium_emoji_ids.get('MAP', '')}\"></tg-emoji> "
            f"<b><i>Статистика {gen}</i></b>\n"
            f"<tg-emoji emoji-id=\"{config.premium_emoji_ids.get('WARNING', '')}\"></tg-emoji> "
            f"<b>Мощь:</b> <i>{power}</i> (место #{rank_power})\n"
            f"<tg-emoji emoji-id=\"{config.premium_emoji_ids.get('ECONOMY', '')}\"></tg-emoji> "
            f"<b>Бюджет:</b> <i>{budget:,}</i> (место #{rank_budget})\n"
            f"<tg-emoji emoji-id=\"{config.premium_emoji_ids.get('IMPORTANT', '')}\"></tg-emoji> "
            f"<b>Армия:</b> <i>{army}</i> (место #{rank_army})\n"
            f"<tg-emoji emoji-id=\"{config.premium_emoji_ids.get('DIPLOMACY', '')}\"></tg-emoji> "
            f"<b>Граждане:</b> <i>{citizens}</i> (место #{rank_citizens})\n"
            f"<b>Уровень жизни:</b> <i>{life}</i>/100"
            "</blockquote>"
        )

    async def render_global_stats(self) -> str:
        rows = await self.db.list_country_stats()
        if not rows:
            return "Статистика пока не заполнена."
        extra = await self.db.list_country_extra_metrics()

        def medal(i: int) -> str:
            return "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i + 1}."

        by_army = sorted(rows, key=lambda r: r[2], reverse=True)[:9]
        by_budget = sorted(rows, key=lambda r: r[1], reverse=True)[:9]
        by_citizens = sorted(rows, key=lambda r: r[3], reverse=True)[:9]
        by_power = sorted(rows, key=lambda r: self._power_score(r[1], r[2], r[3], r[4]), reverse=True)[:9]
        by_efficiency = sorted(rows, key=lambda r: (r[2] / max(r[3], 1)) * 1000, reverse=True)[:9]
        by_econ_eff = sorted(rows, key=lambda r: r[1] / max(r[3], 1), reverse=True)[:9]

        terr_rows = sorted(
            [(country, extra.get(country, {}).get("territories_month", 0)) for country, *_ in rows],
            key=lambda x: x[1],
            reverse=True,
        )[:9]
        dip_rows = sorted(
            [(country, extra.get(country, {}).get("alliances", 0) + extra.get(country, {}).get("treaties", 0)) for country, *_ in rows],
            key=lambda x: x[1],
            reverse=True,
        )[:9]
        stab_rows = sorted(
            [(country, extra.get(country, {}).get("stability_index", 50)) for country, *_ in rows],
            key=lambda x: x[1],
            reverse=True,
        )[:9]
        quality_rows = sorted(
            [(country, extra.get(country, {}).get("quality_percent", 0)) for country, *_ in rows],
            key=lambda x: x[1],
            reverse=True,
        )[:9]

        army_lines = [f"{medal(i)} <b>{country}</b> — <i>{army} ч.</i>" for i, (country, _, army, _, _) in enumerate(by_army)]
        budget_lines = [f"{medal(i)} <b>{country}</b> — <i>{budget:,} вирт-руб.</i>" for i, (country, budget, _, _, _) in enumerate(by_budget)]
        citizen_lines = [f"{medal(i)} <b>{country}</b> — <i>{citizens} ч.</i>" for i, (country, _, _, citizens, _) in enumerate(by_citizens)]
        power_lines = [f"{medal(i)} <b>{country}</b> — <i>{self._power_score(budget, army, citizens, life)}</i>" for i, (country, budget, army, citizens, life) in enumerate(by_power)]
        military_eff_lines = [f"{medal(i)} <b>{country}</b> — <i>{((army / max(citizens,1))*1000):.1f} солд./1000</i>" for i, (country, _, army, citizens, _) in enumerate(by_efficiency)]
        econ_eff_lines = [f"{medal(i)} <b>{country}</b> — <i>{(budget / max(citizens,1)):.1f} на гражданина</i>" for i, (country, budget, _, citizens, _) in enumerate(by_econ_eff)]
        terr_lines = [f"{medal(i)} <b>{country}</b> — <i>{value}</i>" for i, (country, value) in enumerate(terr_rows)]
        dip_lines = [f"{medal(i)} <b>{country}</b> — <i>{value}</i>" for i, (country, value) in enumerate(dip_rows)]
        stab_lines = [f"{medal(i)} <b>{country}</b> — <i>{value}</i>" for i, (country, value) in enumerate(stab_rows)]
        quality_lines = [f"{medal(i)} <b>{country}</b> — <i>{value}%</i>" for i, (country, value) in enumerate(quality_rows)]

        return (
            "<blockquote>"
            "<b>🏆 Индекс мощи</b>\n"
            + "\n".join(power_lines)
            + "\n\n<b>📊 Статистика армий в РП</b>\n"
            + "\n".join(army_lines)
            + "\n\n<b>🕯 Статистика бюджетов в РП</b>\n"
            + "\n".join(budget_lines)
            + "\n\n<b>📈 Статистика граждан в РП</b>\n"
            + "\n".join(citizen_lines)
            + "\n\n<b>⚔️ Военная эффективность</b>\n"
            + "\n".join(military_eff_lines)
            + "\n\n<b>💰 Экономическая эффективность</b>\n"
            + "\n".join(econ_eff_lines)
            + "\n\n<b>🗺 Территориальный прогресс (месяц)</b>\n"
            + "\n".join(terr_lines)
            + "\n\n<b>🤝 Дипломатический рейтинг</b>\n"
            + "\n".join(dip_lines)
            + "\n\n<b>🛡 Индекс стабильности</b>\n"
            + "\n".join(stab_lines)
            + "\n\n<b>✅ РП-качество новостей</b>\n"
            + "\n".join(quality_lines)
            + "\n\n#RP"
            "</blockquote>"
        )

    async def publish_monthly_digest_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        if now.day != 1:
            return
        prev_month_last_day = now.replace(day=1) - timedelta(days=1)
        month_key = prev_month_last_day.strftime("%Y-%m")
        sent_key = f"monthly_digest_sent:{month_key}"
        if await self.db.get_state(sent_key, "0") == "1":
            return

        rows = await self.db.monthly_country_post_counts(month_key)
        if not rows:
            await self.db.set_state(sent_key, "1")
            return

        month_name = calendar.month_name[int(month_key.split("-")[1])]
        lines = [f"<b>🗓 Итоги {month_name} {month_key.split('-')[0]}: активность стран</b>"]
        for idx, (country, cnt) in enumerate(rows[:15], start=1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            lines.append(f"{medal} <b>{country}</b> — <i>{cnt} новостей</i>")

        winner_country, winner_cnt = rows[0]
        lines.append("\n<b>🏆 Награды месяца</b>")
        lines.append(f"• <b>Страна месяца:</b> {winner_country}")
        lines.append(f"• <b>Самая активная редакция:</b> {winner_cnt} новостей")
        await self.db.add_monthly_award(month_key, "Страна месяца", winner_country, str(winner_cnt))
        await self.db.add_monthly_award(month_key, "Самая активная редакция", winner_country, str(winner_cnt))

        message = "<blockquote>" + "\n".join(lines) + "\n\n#RP #ИтогиМесяца</blockquote>"
        try:
            if self.user_client:
                await self.user_client.send_message(config.target_channel, message, parse_mode="html")
            else:
                await self.bot.send_message(config.target_channel, message, parse_mode="HTML")
            await self.db.set_state(sent_key, "1")
        except Exception:
            logger.exception("Failed to publish monthly digest")

        return

    def _summarize_if_huge(self, post: IncomingPost, text: str) -> str:
        if len(text) <= 900:
            return text
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = " ".join(sentences[:2]).strip() or text[:400]
        link = self._source_link(post)
        if link:
            return f"{summary}\n\nПолная новость: {link}"
        return summary

    async def refresh_emoji_packs(self) -> int:
        if not self.user_client:
            return len(self.pack_emoji_cache)
        loaded = await self.emoji_loader.load_all(self.user_client, config.emoji_packs)
        self.pack_emoji_cache = loaded

        symbol_to_key = {
            "👀": "DEFAULT",
            "❗️": "IMPORTANT",
            "⚡️": "ECONOMY",
            "💭": "DIPLOMACY",
            "⚠️": "WARNING",
            "🌐": "MAP",
            "📈": "ECONOMY",
        }
        for packed_name, doc_id in loaded.items():
            _, _, symbol = packed_name.partition(":")
            key = symbol_to_key.get(symbol)
            if key:
                config.premium_emoji_ids[key] = str(doc_id)

        return len(loaded)

    async def is_paused(self) -> bool:
        return await self.db.get_state("paused", "0") == "1"

    async def set_paused(self, paused: bool) -> None:
        await self.db.set_state("paused", "1" if paused else "0")

    async def enqueue(self, post: IncomingPost) -> None:
        ingest_min = min(config.queue_ingest_delay_min, config.queue_ingest_delay_max)
        ingest_max = max(config.queue_ingest_delay_min, config.queue_ingest_delay_max)
        await asyncio.sleep(random.uniform(ingest_min, ingest_max))
        await self.queue.put(post)

    @staticmethod
    def _daily_limit_key() -> str:
        return f"publish_count:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    async def _is_daily_limit_reached(self) -> bool:
        current = int(await self.db.get_state(self._daily_limit_key(), "0") or "0")
        return current >= max(1, config.daily_post_limit)

    async def _increment_daily_count(self) -> None:
        key = self._daily_limit_key()
        current = int(await self.db.get_state(key, "0") or "0")
        await self.db.set_state(key, str(current + 1))

    async def _wait_human_publish_delay(self) -> None:
        delay_min = min(config.queue_publish_delay_min, config.queue_publish_delay_max)
        delay_max = max(config.queue_publish_delay_min, config.queue_publish_delay_max)
        await asyncio.sleep(random.uniform(delay_min, delay_max))
        if random.random() < max(0.0, min(1.0, config.long_pause_chance)):
            lp_min = min(config.long_pause_min, config.long_pause_max)
            lp_max = max(config.long_pause_min, config.long_pause_max)
            await asyncio.sleep(random.uniform(lp_min, lp_max))

    @staticmethod
    def _humanize_text_variation(text: str) -> str:
        out = text
        if random.random() < 0.20 and ". " in out and "\n\n" not in out:
            first, rest = out.split(". ", 1)
            out = f"{first}.\n\n{rest}"
        if random.random() < 0.15 and "\n\n#" in out:
            out = out.replace("\n\n#", "\n#", 1)
        return out

    async def _send_with_retry(self, sender) -> None:
        retries_left = 5
        while True:
            try:
                await sender()
                return
            except TelegramRetryAfter as exc:
                wait_s = max(1, int(getattr(exc, "retry_after", 3)))
                logger.warning("TelegramRetryAfter: wait %ss", wait_s)
                await asyncio.sleep(wait_s)
            except FloodWaitError as exc:
                wait_s = max(1, int(getattr(exc, "seconds", 3)))
                logger.warning("FloodWaitError: wait %ss", wait_s)
                await asyncio.sleep(wait_s)
            except (TelegramBadRequest, RPCError):
                if retries_left <= 0:
                    raise
                retries_left -= 1
                backoff = random.uniform(4.0, 10.0)
                logger.exception("Telegram publish error, retry in %.1fs (left=%s)", backoff, retries_left)
                await asyncio.sleep(backoff)

    async def check_antiflood(self, user_id: int) -> tuple[bool, str]:
        now = int(time.time())
        if await self.db.is_user_blocked(user_id, now):
            return False, "Вы были заблокированы за спам. Чтобы вас разблокировали, обратитесь к @supermegaluti"

        window = self.user_windows.setdefault(user_id, deque())
        while window and now - window[0] > config.antiflood_window_sec:
            window.popleft()
        window.append(now)

        if len(window) > config.antiflood_max_messages:
            strikes, _ = await self.db.add_strike(user_id, blocked_until_ts=now + 600)
            if strikes >= 3:
                await self.db.add_strike(user_id, blocked_until_ts=2_147_483_647)
                return False, "Вы были заблокированы за спам. Чтобы вас разблокировали, обратитесь к @supermegaluti"
            return False, "Вы получили мут на 10 минут по причине: флуд командами. Ваши команды не будут приниматься в течение мута."
        return True, "OK"

    async def check_user_access(self, user_id: int, *, is_callback: bool = False) -> tuple[bool, str]:
        now = int(time.time())
        if await self.db.is_user_banned(user_id):
            return False, "Вы забанены. Если считаете это ошибкой, обратитесь к админу."

        banned_until = await self.db.get_antiflood_ban(user_id)
        if banned_until > now:
            return False, f"Вы временно заблокированы за флуд. Обратитесь к {config.admin_username} для разбана."

        window = self.action_windows.setdefault(user_id, deque())
        while window and now - window[0] > max(1, config.antiflood_window):
            window.popleft()
        window.append(now)
        if len(window) > max(1, config.antiflood_max_actions):
            until = now + max(30, config.antiflood_ban_duration)
            await self.db.set_antiflood_ban(user_id, until)
            return False, f"Вы временно заблокированы за флуд и попытку прекращения работы бота. Обратитесь к {config.admin_username} для разбана."
        return True, "OK"

    async def worker(self) -> None:
        while True:
            post = await self.queue.get()
            try:
                await self.process_post(post)
            except Exception:
                logger.exception("Unhandled error on post processing")
            finally:
                self.queue.task_done()

    async def scheduler_worker(self) -> None:
        while True:
            try:
                due = await self.db.get_due_scheduled_posts(int(time.time()))
                await self.publish_monthly_digest_if_due()
                await self.run_daily_economy_cycle_if_due()
                await self.run_weekly_crisis_cycle_if_due()
                await self.publish_daily_missions_if_due()
                await self.publish_completed_technologies()
                for post_id, source_country, text in due:
                    fake_id = int(time.time()) + post_id
                    await self.enqueue(
                        IncomingPost(
                            source_country=source_country,
                            source_channel="scheduled",
                            message_id=fake_id,
                            text=text,
                            has_media=False,
                        )
                    )
                    logger.info("Scheduled post queued id=%s", post_id)
            except Exception:
                logger.exception("Scheduler worker failed")
            await asyncio.sleep(max(1, config.scheduler_poll_seconds))

    async def run_daily_economy_cycle_if_due(self) -> None:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state_key = f"economy_cycle:{day_key}"
        if await self.db.get_state(state_key, "0") == "1":
            return
        rows = await self.db.list_country_stats()
        extra = await self.db.list_country_extra_metrics()
        for country, budget, _, citizens, _ in rows:
            territories = extra.get(country, {}).get("territories_month", 0)
            income = (territories * 400) + max(0, citizens // 15)
            oil = max(1, territories // 2)
            metal = max(1, territories // 3)
            grain = max(1, citizens // 120)
            await self.db.apply_country_stats_delta(country, budget_delta=income)
            await self.db.upsert_resources(country, oil, metal, grain)
        await self.db.set_state(state_key, "1")

    async def run_weekly_crisis_cycle_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        week_key = now.strftime("%G-W%V")
        state_key = f"crisis_cycle:{week_key}"
        if await self.db.get_state(state_key, "0") == "1":
            return
        rows = await self.db.list_country_stats()
        extra = await self.db.list_country_extra_metrics()
        for country, budget, army, citizens, life in rows:
            stability = extra.get(country, {}).get("stability_index", 50)
            army_pressure = 20 if army > 300 and citizens < 800 else 0
            risk = min(95, max(0, (100 - stability) + army_pressure + (25 if life < 30 else 0)))
            if risk < 70:
                continue
            if life < 30:
                delta_citizens = -max(20, citizens // 10)
                await self.db.apply_country_stats_delta(country, citizens_delta=delta_citizens, life_delta=-2)
                await self.db.log_crisis(country, "mass_emigration", json.dumps({"citizens_delta": delta_citizens}))
            elif army > 300 and citizens < 800:
                await self.db.apply_country_stats_delta(country, army_delta=-max(20, army // 10), budget_delta=-5000, life_delta=-3)
                await self.db.log_crisis(country, "military_coup", json.dumps({"army_penalty": True}))
            else:
                await self.db.apply_country_stats_delta(country, budget_delta=-(budget // 5), life_delta=-2)
                await self.db.log_crisis(country, "economic_collapse", json.dumps({"budget_penalty_pct": 20}))
        await self.db.set_state(state_key, "1")

    async def publish_daily_missions_if_due(self) -> None:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state_key = f"daily_missions:{day_key}"
        if await self.db.get_state(state_key, "0") == "1":
            return
        mission_pool = [
            ("Снять кадр строительства инфраструктуры", 2500, 1),
            ("Опубликовать новость о дипломатических переговорах", 2000, 1),
            ("Провести мобилизационный отчёт по правилам RP", 1500, 0),
            ("Опубликовать экономический отчёт с цифрами", 1800, 1),
            ("Сделать разведсводку с подтверждением", 2200, 1),
        ]
        missions = random.sample(mission_pool, k=3)
        await self.db.set_daily_missions(day_key, missions)
        await self.db.set_state(state_key, "1")

    async def publish_completed_technologies(self) -> None:
        due = await self.db.due_technology_projects(int(time.time()))
        if not due:
            return
        for _, country, tech_name in due:
            await self.db.apply_country_stats_delta(country, life_delta=1, budget_delta=3000)
            text = (
                "<blockquote>"
                f"<b>🔬 Технология завершена:</b> <i>{country}</i>\n"
                f"Проект: <b>{tech_name}</b>\n"
                "Бонус: +3000 к бюджету и +1 к уровню жизни."
                "</blockquote>"
            )
            if self.user_client:
                await self.user_client.send_message(config.target_channel, text, parse_mode="html")
            else:
                await self.bot.send_message(config.target_channel, text, parse_mode="HTML")

    async def rss_worker(self) -> None:
        if not config.rss_feeds:
            return

        while True:
            try:
                for key, url in config.rss_feeds.items():
                    seen_key = f"rss_seen:{key}"
                    seen = await self.db.get_state(seen_key, "")
                    items = await self.rss.fetch(key, url)
                    for item in reversed(items):
                        marker = content_hash(f"{item.title}|{item.link}")
                        if marker == seen:
                            continue
                        text = f"{item.title}\n\n{item.summary}\n{item.link}".strip()
                        await self.enqueue(
                            IncomingPost(
                                source_country="MANUAL",
                                source_channel=f"rss:{key}",
                                message_id=int(time.time()),
                                text=text,
                                has_media=False,
                            )
                        )
                        await self.db.set_state(seen_key, marker)
                        break
            except Exception:
                logger.exception("RSS worker failed")
            await asyncio.sleep(max(10, config.rss_poll_seconds))

    async def process_post(self, post: IncomingPost) -> None:
        if await self.is_paused():
            logger.info("Paused; skip post %s/%s", post.source_channel, post.message_id)
            return
        if await self._is_daily_limit_reached():
            logger.info("Daily limit reached (%s), ignore %s/%s", config.daily_post_limit, post.source_channel, post.message_id)
            return

        source_text = (post.text or "").strip()
        if not source_text and not post.has_media:
            logger.info("Empty message skip: %s/%s", post.source_channel, post.message_id)
            return

        hash_value = content_hash(f"{post.source_channel}:{post.source_country}:{strip_hashtags(source_text)}")
        if await self.db.is_duplicate(hash_value):
            logger.info("Duplicate skip: %s", hash_value)
            return

        translated = await self.translator.to_russian(source_text) if source_text else ""
        corrected = autocorrect_news_text(strip_emojis(translated or source_text))
        corrected = self._summarize_if_huge(post, corrected)
        corrected = self._extract_special_markers(corrected)
        corrected = self._humanize_text_variation(corrected)

        ai_result = self.ai_guard.analyze(corrected)
        if not ai_result.allowed:
            logger.info("Blocked by AI guard %s (score=%s): %s/%s", ai_result.reason, ai_result.score, post.source_channel, post.message_id)
            if post.source_country and post.source_country != "MANUAL":
                warn_count = await self.db.add_country_warning(post.source_country, ai_result.details or ai_result.reason)
                await self.bot.send_message(
                    config.admin_id,
                    f"⚠️ Варн стране {post.source_country}: #{warn_count}\nПричина: {ai_result.details or ai_result.reason}",
                )
            if post.submitted_by_user_id:
                await self.bot.send_message(
                    post.submitted_by_user_id,
                    "Новость не выложена: обнаружен токсичный/OOC контент. "
                    f"Проблемный фрагмент: {ai_result.details or 'не определён'}. "
                    "Отредактируйте текст по правилам и отправьте заново.",
                )
            if post.has_media:
                await self.send_to_moderation(post, corrected or "[MEDIA]", ai_result.reason, raw_text=corrected)
            return

        filter_result = self.rp_filter.check(
            corrected or "media news",
            known_countries=self._known_country_terms(),
            known_hashtags=self._known_country_hashtags(),
        )

        if not filter_result.allowed:
            logger.info("Blocked by RP filter %s: %s/%s", filter_result.reason, post.source_channel, post.message_id)
            if post.submitted_by_user_id:
                await self.bot.send_message(
                    post.submitted_by_user_id,
                    f"Новость не выложена. Причина: {self._reject_reason_text(filter_result.reason)}\n"
                    f"Где ошибка: {filter_result.details or 'проверьте формулировку новости'}\n"
                    "Проверьте формулировки, исправьте ошибки и опубликуйте снова.",
                )
            if post.has_media:
                await self.send_to_moderation(post, corrected or "[MEDIA]", filter_result.reason, raw_text=corrected)
            return

        await self._apply_diplomacy_and_tech(post, corrected)
        formatted, entities = self._render_post(post, corrected)

        if filter_result.reason == "MILITARY_REVIEW_REQUIRED":
            await self.send_to_moderation(
                post,
                formatted,
                "MILITARY_REQUIRES_ADMIN_CLASSIFICATION",
                review_mode="war",
                raw_text=corrected,
                suggestion="Уточните формулировки: цель, действия, участники и результат. При необходимости нажмите «Поправить».",
            )
            return

        if post.has_media:
            await self.send_to_moderation(
                post,
                formatted,
                "MEDIA_REQUIRES_ADMIN_APPROVAL",
                raw_text=corrected,
                suggestion="Проверьте соответствие RP и подпись к медиа. Если нужно — нажмите «Поправить».",
            )
            return

        await self.publish_and_mark(post, formatted, entities, hash_value, auto_passed=True)

    async def publish_and_mark(
        self,
        post: IncomingPost,
        formatted: str,
        entities: list | None,
        hash_value: str,
        auto_passed: bool = False,
    ) -> None:
        try:
            await self._wait_human_publish_delay()
            if config.publish_delay_seconds > 0:
                await asyncio.sleep(min(config.publish_delay_seconds, 3.0))
            if self.user_client:
                await self._send_with_retry(
                    lambda: self.user_client.send_message(config.target_channel, formatted, formatting_entities=entities or [])
                )
            else:
                await self._send_with_retry(
                    lambda: self.bot.send_message(chat_id=config.target_channel, text=formatted)
                )
            await self.db.mark_processed(post.source_channel, post.source_country, post.message_id, hash_value)
            await self._increment_daily_count()
            await self.db.increment_news_quality(post.source_country, 1 if auto_passed else 0, 1)
            await self._apply_country_stats_effect(post)
            logger.info("Published %s/%s", post.source_channel, post.message_id)
        except (TelegramBadRequest, RPCError):
            logger.exception("Publish failed")

    async def publish_media_and_mark(self, post: IncomingPost, caption: str, hash_value: str, auto_passed: bool = False) -> None:
        try:
            await self._wait_human_publish_delay()
            if self.user_client and post.media_file_id:
                await self._send_with_retry(
                    lambda: self.user_client.send_file(config.target_channel, file=post.media_file_id, caption=caption[:1024])
                )
            elif post.media_type == "photo" and post.media_file_id:
                await self._send_with_retry(
                    lambda: self.bot.send_photo(config.target_channel, post.media_file_id, caption=caption[:1024])
                )
            elif post.media_type == "video" and post.media_file_id:
                await self._send_with_retry(
                    lambda: self.bot.send_video(config.target_channel, post.media_file_id, caption=caption[:1024])
                )
            elif post.media_type == "animation" and post.media_file_id:
                await self._send_with_retry(
                    lambda: self.bot.send_animation(config.target_channel, post.media_file_id, caption=caption[:1024])
                )
            else:
                await self.publish_and_mark(post, caption, None, hash_value, auto_passed=auto_passed)
                return

            await self.db.mark_processed(post.source_channel, post.source_country, post.message_id, hash_value)
            await self._increment_daily_count()
            await self.db.increment_news_quality(post.source_country, 1 if auto_passed else 0, 1)
            await self._apply_country_stats_effect(post)
            logger.info("Published media %s/%s", post.source_channel, post.message_id)
        except (TelegramBadRequest, RPCError):
            logger.exception("Media publish failed")

    async def send_to_moderation(
        self,
        post: IncomingPost,
        text: str,
        reason: str,
        review_mode: str = "default",
        raw_text: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        token = uuid.uuid4().hex
        payload = {
            "source_country": post.source_country,
            "source_channel": post.source_channel,
            "message_id": post.message_id,
            "formatted_text": text,
            "raw_text": raw_text or post.text,
            "has_media": post.has_media,
            "media_file_id": post.media_file_id,
            "media_type": post.media_type,
            "submitted_by_user_id": post.submitted_by_user_id,
            "review_mode": review_mode,
            "hash_value": content_hash(f"{post.source_channel}:{post.message_id}:{text}"),
        }
        await self.db.store_moderation_payload(token, json.dumps(payload, ensure_ascii=False))

        msg_text = (
            "Пост отправлен на модерацию\n"
            f"Причина: {reason}\n"
            f"Источник: {post.source_country} ({post.source_channel})\n"
            f"ID: {post.message_id}\n\n"
            f"Рекомендация ИИ: {suggestion or 'Проверьте RP-логику, корректность формулировок и хештег.'}\n\n"
            f"Текст:\n{text[:3000]}"
        )

        reply_markup = moderation_keyboard(token, review_mode=review_mode)
        if post.has_media and post.media_file_id:
            if post.media_type == "photo":
                await self.bot.send_photo(config.admin_id, post.media_file_id, caption=msg_text[:1024], reply_markup=reply_markup)
            elif post.media_type == "video":
                await self.bot.send_video(config.admin_id, post.media_file_id, caption=msg_text[:1024], reply_markup=reply_markup)
            elif post.media_type == "animation":
                await self.bot.send_animation(config.admin_id, post.media_file_id, caption=msg_text[:1024], reply_markup=reply_markup)
            else:
                await self.bot.send_message(config.admin_id, msg_text, reply_markup=reply_markup)
        else:
            await self.bot.send_message(config.admin_id, msg_text, reply_markup=reply_markup)

    async def cleanup_runtime_files(self) -> None:
        logs = list(Path(config.logs_dir).glob("*.log.*"))
        for p in logs:
            if p.stat().st_size > 1_000_000:
                p.unlink(missing_ok=True)
