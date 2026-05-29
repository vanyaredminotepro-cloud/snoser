import asyncio
import calendar
import json
import logging
import random
import re
import time
import uuid
from collections import deque
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from html import escape
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

RESEARCH_EFFECTS_DEFAULTS: dict[str, dict[str, object]] = {
    "drone_recon": {"unlock_unit": "recon_drone"},
    "drone_strike": {"unlock_unit": "strike_drone"},
    "rocket_short": {"unlock_unit": "short_rocket"},
    "rocket_medium": {"unlock_unit": "medium_rocket", "risk_delta": 3},
    "air_recon": {"unlock_unit": "recon_plane"},
    "air_drone_carrier": {"unlock_unit": "drone_carrier"},
    "boat_patrol": {"unlock_unit": "patrol_boat"},
    "boat_missile": {"unlock_unit": "missile_boat"},
    "landing_craft": {"unlock_unit": "landing_craft"},
    "armor_light": {"unlock_unit": "light_armor"},
    "tech_radar": {"army_pct": 0.05},
    "tech_cyber": {"risk_delta": -5},
    "tech_factory": {"budget_delta": 3000, "life_delta": 1},
}


class NewsService:
    MOB_SIGNAL_MAX_AGE_SECONDS = 23 * 24 * 3600

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
        self._queued_keys: set[str] = set()
        self.user_windows: dict[int, deque[int]] = {}
        self.action_windows: dict[int, deque[int]] = {}

    def attach_user_client(self, client: TelegramClient) -> None:
        self.user_client = client

    async def _send_to_target_channel(
        self,
        text: str,
        *,
        parse_mode: str = "html",
        formatting_entities: list | None = None,
        reply_to: int | None = None,
    ) -> bool:
        if not self.user_client:
            logger.warning("Target channel publish skipped: user session is not connected yet.")
            return False
        if formatting_entities is not None:
            await self.user_client.send_message(
                config.target_channel,
                text,
                formatting_entities=formatting_entities,
                reply_to=reply_to,
            )
        else:
            await self.user_client.send_message(
                config.target_channel,
                text,
                parse_mode=parse_mode,
                reply_to=reply_to,
            )
        return True

    async def load_dynamic_config(self) -> None:
        raw_tags = await self.db.get_state("cfg:country_hashtags", "")
        raw_sources = await self.db.get_state("cfg:source_channels", "")
        raw_proxy = await self.db.get_state("cfg:proxy", "")
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

        try:
            if raw_proxy:
                loaded_proxy = json.loads(raw_proxy)
                if isinstance(loaded_proxy, dict):
                    config.proxy = loaded_proxy
        except Exception:
            logger.exception("Failed to load dynamic proxy config")

    @staticmethod
    def _post_queue_key(post: IncomingPost) -> str:
        return f"{post.source_country}|{post.source_channel}|{post.message_id}"

    async def recover_pending_posts(self) -> int:
        recovered = 0
        for key, payload_json in await self.db.list_pending_posts(limit=2000):
            try:
                payload = json.loads(payload_json)
                post = IncomingPost(**payload)
                if key in self._queued_keys:
                    continue
                await self.queue.put(post)
                self._queued_keys.add(key)
                recovered += 1
            except Exception:
                logger.exception("Failed to recover pending post %s", key)
        if recovered:
            logger.info("Recovered %s pending posts from DB", recovered)
        return recovered

    async def _metric_inc(self, key: str, step: int = 1) -> None:
        metric_key = f"metric:{key}"
        cur = int(await self.db.get_state(metric_key, "0") or "0")
        await self.db.set_state(metric_key, str(cur + step))

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

    @staticmethod
    def _derive_infrastructure_effects(text: str) -> tuple[int, int, int, int]:
        low = text.lower()
        factory_delta = 0
        oil_delta = 0
        metal_delta = 0
        grain_delta = 0

        if any(k in low for k in ["завод", "фабрик", "цех", "производств"]):
            factory_numbers = [
                int(v)
                for v in re.findall(
                    r"\b(\d{1,2})\b[^\n.,;:]{0,40}(?:военн[^\n.,;:]{0,20})?(?:завод|фабрик|цех|производств)",
                    low,
                )
            ]
            nearby_count = max(factory_numbers, default=1)
            if any(k in low for k in ["военн", "оруж", "боеприп", "патрон", "брон", "дрон", "снаряж", "техник"]):
                factory_delta += min(max(nearby_count, 1), 8)
                metal_delta += 8 + factory_delta * 6
            else:
                metal_delta += 5

        if any(k in low for k in ["агро", "пищ", "сельск", "удобр", "зерн", "ферм"]):
            grain_delta += 10
        if any(k in low for k in ["аммиак", "топлив", "нефт", "фосфор", "химичес"]):
            oil_delta += 5
        if any(k in low for k in ["дорог", "снабж", "инфраструктур", "тцк", "полигон"]):
            metal_delta += 3
            grain_delta += 2

        return factory_delta, oil_delta, metal_delta, grain_delta

    async def _apply_country_stats_effect(self, post: IncomingPost) -> None:
        if not post.source_country or post.source_country == "MANUAL":
            return
        population = await self.db.get_country_population(post.source_country)
        budget_delta, army_delta, life_delta, citizens_delta = self._derive_country_stat_deltas(post.text or "", population=population)
        freshness = self._news_freshness_factor(post)
        budget_delta = int(round(budget_delta * freshness))
        army_delta = int(round(army_delta * freshness))
        life_delta = int(round(life_delta * freshness))
        citizens_delta = int(round(citizens_delta * freshness))
        factory_delta, oil_delta, metal_delta, grain_delta = self._derive_infrastructure_effects(post.text or "")
        factory_delta = int(round(factory_delta * freshness))
        oil_delta = int(round(oil_delta * freshness))
        metal_delta = int(round(metal_delta * freshness))
        grain_delta = int(round(grain_delta * freshness))
        if budget_delta != 0 or army_delta != 0 or life_delta != 0 or citizens_delta != 0:
            await self.db.apply_country_stats_delta(
                post.source_country,
                budget_delta=budget_delta,
                army_delta=army_delta,
                life_delta=life_delta,
                citizens_delta=citizens_delta,
            )
        if factory_delta:
            await self.db.add_military_factories(post.source_country, factory_delta)
        if oil_delta or metal_delta or grain_delta:
            await self.db.add_resources_delta(
                post.source_country,
                oil_delta=oil_delta,
                metal_delta=metal_delta,
                grain_delta=grain_delta,
            )

    @staticmethod
    def _news_freshness_factor(post: IncomingPost) -> float:
        if not post.published_ts:
            return 1.0
        age_hours = max(0, (int(time.time()) - int(post.published_ts)) / 3600.0)
        if age_hours <= 24:
            return 1.0
        if age_hours <= 72:
            return 0.6
        return 0.25

    @staticmethod
    def _is_recent_news(post: IncomingPost, max_hours: int = 120) -> bool:
        if not post.published_ts:
            return True
        age_hours = max(0, (int(time.time()) - int(post.published_ts)) / 3600.0)
        return age_hours <= max_hours

    @staticmethod
    def _news_age_hours(post: IncomingPost) -> float:
        if not post.published_ts:
            return 0.0
        return max(0.0, (int(time.time()) - int(post.published_ts)) / 3600.0)

    @staticmethod
    def _news_has_mobilization_signal(text: str) -> bool:
        low = text.lower()
        return any(
            probe in low
            for probe in (
                "мобилизац",
                "#мобилизация",
                "призыв",
                "добровол",
                "демобилизац",
                "военный набор",
                "частичн мобилизац",
                "общая мобилизац",
                "набор резерв",
                "сбор резервист",
            )
        )

    @staticmethod
    def _normalize_channel_name(raw_channel: str) -> str:
        return (raw_channel or "").strip().lstrip("@").lower()

    async def remember_mobilization_signal(self, post: IncomingPost, text: str) -> None:
        if not post.source_country or post.source_country == "MANUAL":
            return
        if not self._news_has_mobilization_signal(text):
            return
        payload = {
            "country": post.source_country,
            "channel": self._normalize_channel_name(post.source_channel),
            "message_id": int(post.message_id),
            "ts": int(time.time()),
        }
        await self.db.set_state(f"mob_signal:{post.source_country}", json.dumps(payload, ensure_ascii=False))
        raw = await self.db.get_state(f"mob_signal_history:{post.source_country}", "[]")
        try:
            history = json.loads(raw)
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
        history.insert(0, payload)
        await self.db.set_state(f"mob_signal_history:{post.source_country}", json.dumps(history[:25], ensure_ascii=False))

    async def check_mobilization_news_criteria(self, country: str) -> tuple[bool, str]:
        raw = await self.db.get_state(f"mob_signal:{country}", "")
        if not raw:
            return False, "Нет найденной новости о мобилизации для этой страны."
        try:
            payload = json.loads(raw)
        except Exception:
            return False, "Повреждены данные о последнем сигнале мобилизации."
        ts = int(payload.get("ts", 0))
        age = int(time.time()) - ts
        if age > self.MOB_SIGNAL_MAX_AGE_SECONDS:
            return False, "Последняя подходящая новость устарела (нужно не старше 23 дней)."
        if payload.get("generated"):
            return True, f"Подходит: создано кнопкой мобилизации, давность примерно {max(0, age // 3600)} ч."
        channel = self._normalize_channel_name(str(payload.get("channel", "")))
        return True, f"Подходит: @{channel}, сообщение={int(payload.get('message_id', 0))}, давность примерно {max(0, age // 3600)} ч."

    async def render_recent_mobilization_signals(self, country: str, limit: int = 3) -> str:
        raw = await self.db.get_state(f"mob_signal_history:{country}", "[]")
        try:
            history = json.loads(raw)
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
        if not history:
            return "Последние сигналы: нет."
        lines = ["Последние сигналы:"]
        for item in history[:max(1, limit)]:
            age = max(0, (int(time.time()) - int(item.get("ts", 0))) // 3600)
            if item.get("generated"):
                lines.append(f"• создано кнопкой мобилизации | примерно {age} ч назад")
            else:
                lines.append(
                    f"• @{self._normalize_channel_name(str(item.get('channel', '')))} | сообщение: {int(item.get('message_id', 0))} | примерно {age} ч назад"
                )
        return "\n".join(lines)

    @staticmethod
    def _seconds_until_week_end() -> int:
        now = datetime.now(timezone.utc)
        days_until_next_monday = (7 - now.weekday()) % 7 or 7
        week_end = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=days_until_next_monday)
        return max(1, int((week_end - now).total_seconds()))

    @staticmethod
    def _format_duration(seconds: int) -> str:
        d, rem = divmod(max(0, seconds), 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        return f"{d}д {h}ч {m}м {s}с"


    @staticmethod
    def _war_status_ru(status: str) -> str:
        return {
            "peace": "мир",
            "threat": "угроза",
            "martial_law": "военное положение",
            "war": "война",
            "total_war": "тотальная война",
        }.get(status, status or "мир")

    @classmethod
    def _war_statuses_ru(cls, statuses: list[str]) -> str:
        return ", ".join(cls._war_status_ru(s) for s in statuses) if statuses else "любой"

    async def _effective_military_factories(self, country: str) -> int:
        db_count = await self.db.get_military_factories(country)
        seed_count = int(config.initial_military_factories.get(country, 0))
        if seed_count > db_count:
            await self.db.set_military_factories(country, seed_count)
            return seed_count
        return db_count

    async def _remember_generated_mobilization_signal(self, country: str, mob_type: str) -> None:
        payload = {
            "country": country,
            "channel": "кнопка мобилизации",
            "message_id": 0,
            "mob_type": mob_type,
            "generated": True,
            "ts": int(time.time()),
        }
        await self.db.set_state(f"mob_signal:{country}", json.dumps(payload, ensure_ascii=False))
        raw = await self.db.get_state(f"mob_signal_history:{country}", "[]")
        try:
            history = json.loads(raw)
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
        history.insert(0, payload)
        await self.db.set_state(f"mob_signal_history:{country}", json.dumps(history[:25], ensure_ascii=False))

    @staticmethod
    def _clamp_int(value: int, min_value: int, max_value: int) -> int:
        return max(min_value, min(max_value, int(value)))

    def _mobilization_speed_profile(
        self,
        *,
        requested_amount: int,
        citizens: int,
        life_level: int,
        risk_index: int,
        war_status: str,
        factories: int,
        mob_type: str,
    ) -> dict[str, int | float | str]:
        profile = config.mobilization_profiles.get(mob_type, {})
        base_rate = max(1, requested_amount // 7)
        citizen_pressure = max(0.35, min(1.25, citizens / max(1, requested_amount * 18)))
        life_factor = max(0.45, min(1.35, life_level / 55.0))
        risk_factor = max(0.70, min(1.45, 1.0 + (risk_index / 180.0)))
        factory_factor = max(0.85, min(1.35, 1.0 + factories * 0.04))
        war_factor = {
            "peace": 0.75,
            "threat": 0.95,
            "martial_law": 1.15,
            "war": 1.30,
            "total_war": 1.45,
        }.get(war_status, 0.90)
        type_factor = {
            "conscription": 0.90,
            "voluntary": 0.75,
            "partial": 1.00,
            "normal": 1.10,
            "aggressive": 1.25,
            "total": 1.40,
        }.get(mob_type, 1.0)
        support = self._clamp_int(round((life_level * 0.55) + ((100 - risk_index) * 0.25) + (factories * 2) + (war_factor * 10)), 5, 100)
        multiplier = citizen_pressure * life_factor * risk_factor * factory_factor * war_factor * type_factor
        tick_rate = self._clamp_int(round(base_rate * multiplier), 1, max(1, requested_amount))
        if support < 35:
            tick_rate = max(1, int(tick_rate * 0.65))
        elif support > 70:
            tick_rate = max(1, int(tick_rate * 1.15))
        estimated_ticks = max(1, (requested_amount + tick_rate - 1) // tick_rate)
        tick_hours = 6
        estimated_hours = estimated_ticks * tick_hours
        return {
            "tick_rate": tick_rate,
            "support": support,
            "estimated_hours": estimated_hours,
            "citizen_pressure": round(citizen_pressure, 2),
            "life_factor": round(life_factor, 2),
            "risk_factor": round(risk_factor, 2),
            "factory_factor": round(factory_factor, 2),
            "war_factor": round(war_factor, 2),
            "type_factor": round(type_factor, 2),
            "label": str(profile.get("label", mob_type)),
        }

    async def _publish_mobilization_start_news(self, country: str, mob_type: str, requested_amount: int, finish_dt: datetime, speed: dict | None = None) -> bool:
        profile = config.mobilization_profiles.get(mob_type, {})
        speed = speed or {}
        text = (
            f"⚔️ <b>{country} начинает мобилизацию</b>\n"
            f"Тип: <b>{profile.get('label', mob_type)}</b>\n"
            f"Размер: <b>{requested_amount} человек</b>\n"
            f"Скорость: <b>{int(speed.get('tick_rate', 1))} человек за цикл</b>\n"
            f"Поддержка правительства: <b>{int(speed.get('support', 0))}%</b>\n"
            f"Будет длиться до: <b>{finish_dt.strftime('%d.%m.%Y %H:%M')} по UTC</b>"
        )
        try:
            if self.user_client:
                await self._send_with_retry(lambda: self._send_to_target_channel(text, parse_mode="html"))
            else:
                await self.bot.send_message(config.target_channel, text, parse_mode="HTML")
            return True
        except Exception:
            logger.exception("Failed to publish mobilization start news for %s", country)
            return False

    @staticmethod
    def _week_key_utc() -> str:
        return datetime.now(timezone.utc).strftime("%G-W%V")

    async def calculate_mobilization_gain(self, country: str, requested_type: str) -> tuple[int, int, int]:
        profile = config.mobilization_profiles[requested_type]
        min_gain = int(profile["min_gain"])
        max_gain = int(profile["max_gain"])
        _, used, weekly_limit, last_week = await self.db.get_country_mobilization(country)
        week_key = self._week_key_utc()

        if last_week != week_key:
            used = 0
            weekly_limit = random.randint(min_gain, max_gain)
        elif weekly_limit <= 0:
            weekly_limit = random.randint(min_gain, max_gain)

        remaining = max(0, weekly_limit - used)
        if remaining <= 0:
            return 0, used, weekly_limit

        gain = min(remaining, random.randint(min_gain, max_gain))
        return gain, used, weekly_limit

    async def apply_mobilization_effects(self, country: str, mob_type: str, soldiers_gained: int) -> tuple[int, int, int, int]:
        profile = config.mobilization_profiles[mob_type]
        effects = profile["effects"]
        await self.db.apply_country_stats_delta(country, army_delta=soldiers_gained)
        budget_change, life_change, risk_change = await self.db.apply_country_multipliers(
            country,
            budget_pct=float(effects["budget_pct"]),
            life_pct=float(effects["life_pct"]),
            risk_delta=int(effects["risk_delta"]),
        )
        return soldiers_gained, budget_change, life_change, risk_change

    async def attempt_mobilization(self, country: str, requested_type: str) -> tuple[bool, str]:
        if requested_type not in config.mobilization_profiles:
            return False, "Неизвестный тип мобилизации."

        profile = config.mobilization_profiles[requested_type]
        req = profile["requirements"]
        factories = await self._effective_military_factories(country)
        war_status, _ = await self.db.get_country_war_and_risk(country)

        min_factories = int(req["factories"])
        allowed_statuses = [str(s) for s in req["war_status"]]
        if factories < min_factories:
            return False, f"Требуется военных заводов: {min_factories}, сейчас: {factories}."
        if allowed_statuses and war_status not in allowed_statuses:
            return False, f"Требуется один из статусов: {self._war_statuses_ru(allowed_statuses)}. Сейчас: {self._war_status_ru(war_status)}."

        gained, used, weekly_limit = await self.calculate_mobilization_gain(country, requested_type)
        week_key = self._week_key_utc()
        if gained <= 0:
            penalty = profile["penalty"]
            penalty_msg = "Лимит недели исчерпан."
            if penalty["mode"] == "warn":
                warn_count = await self.db.add_country_warning(country, f"Mobilization overflow: {requested_type}")
                penalty_msg = f"Лимит недели исчерпан. Выдан варн #{warn_count}."
            elif penalty["mode"] == "block":
                block_until = int(time.time()) + int(penalty.get("days", 3)) * 86400
                await self.db.set_state(f"mob_block:{country}", str(block_until))
                penalty_msg = f"Лимит исчерпан. Мобилизация заблокирована на {penalty.get('days', 3)} дня."
            elif penalty["mode"] == "budget_pct":
                budget_change, _, _ = await self.db.apply_country_multipliers(country, budget_pct=float(penalty.get("value", -0.10)))
                penalty_msg = f"Лимит исчерпан. Применён бюджетный штраф: {budget_change}."
            elif penalty["mode"] == "warn_demob":
                warn_count = await self.db.add_country_warning(country, f"Mobilization overflow: {requested_type}")
                stats = await self.db.get_country_stats(country)
                army = stats[1] if stats else 0
                demob = -int(army * float(penalty.get("demob_pct", 0.10)))
                await self.db.apply_country_stats_delta(country, army_delta=demob)
                penalty_msg = f"Лимит исчерпан. Варн #{warn_count}, демобилизация {abs(demob)}."
            elif penalty["mode"] == "hard":
                warn_count = await self.db.add_country_warning(country, f"Mobilization overflow: {requested_type}")
                stats = await self.db.get_country_stats(country)
                army = stats[1] if stats else 0
                demob = -int(army * 0.30)
                budget_change, _, _ = await self.db.apply_country_multipliers(country, budget_pct=-0.50)
                await self.db.apply_country_stats_delta(country, army_delta=demob)
                penalty_msg = f"Лимит исчерпан. Варн #{warn_count}, бюджет {budget_change}, демобилизация {abs(demob)}."

            await self.db.add_mobilization_log(country, requested_type, 0, 0, 0, 0, penalized=True)
            return False, f"Ваша страна уже набрала максимум солдат на этой неделе. {penalty_msg}"

        soldiers, budget_change, life_change, risk_change = await self.apply_mobilization_effects(country, requested_type, gained)
        await self.db.update_country_mobilization(
            country=country,
            mobilization_type=requested_type,
            mobilization_amount=used + gained,
            weekly_limit=weekly_limit,
            week_key=week_key,
            ts=int(time.time()),
        )
        await self.db.add_mobilization_log(
            country=country,
            mobilization_type=requested_type,
            soldiers_gained=soldiers,
            budget_change=budget_change,
            life_change=life_change,
            risk_change=risk_change,
            penalized=False,
        )
        msg = (
            f"✅ Мобилизация: {profile['label']} ({requested_type})\n"
            f"Набрано: +{soldiers} солдат\n"
            f"Неделя: {used + gained}/{weekly_limit}\n"
            f"Бюджет: {budget_change:+d}, жизнь: {life_change:+d}, риск: {risk_change:+d}"
        )
        return True, msg

    async def render_mobilization_status(self, country: str) -> str:
        mob_type, used, weekly_limit, week_key = await self.db.get_country_mobilization(country)
        factories = await self._effective_military_factories(country)
        war_status, risk = await self.db.get_country_war_and_risk(country)
        plan_raw = await self.db.get_state(f"mobplan:{country}", "")
        active = False
        target = 0
        if plan_raw:
            try:
                plan = json.loads(plan_raw)
                active = bool(plan.get("active"))
                target = int(plan.get("target", 0))
            except Exception:
                pass
        lines = [
            f"<b>⚔️ Мобилизация: {country}</b>",
            f"Тип: <b>{config.mobilization_profiles.get(mob_type, {}).get('label', mob_type)}</b>",
            f"Лимит недели: <b>{used}/{weekly_limit if weekly_limit > 0 else 'не задан'}</b>",
            f"План недели: <b>{target if target > 0 else 'не выбран'}</b> ({'активен' if active else 'не активен'})",
            f"Неделя: <i>{week_key or self._week_key_utc()}</i>",
            f"Военные заводы: <b>{factories}</b>",
            f"Статус войны: <b>{self._war_status_ru(war_status)}</b>, риск: <b>{risk}</b>",
            "",
            "✅ Критерии: подтверждающая новость создаётся автоматически кнопкой мобилизации.",
            await self.render_recent_mobilization_signals(country),
            "",
            "<b>Доступные типы:</b>",
        ]
        for key, profile in config.mobilization_profiles.items():
            req = profile["requirements"]
            lines.append(
                f"• <b>{profile['label']}</b> — {profile['min_gain']}-{profile['max_gain']} в неделю, "
                f"военных заводов не меньше {req['factories']}, статусы: {self._war_statuses_ru([str(s) for s in req['war_status']])}"
            )
        return "\n".join(lines)

    async def start_mobilization(self, country: str, mob_type: str, requested_amount: int) -> tuple[bool, str]:
        if mob_type not in config.mobilization_profiles:
            return False, "Неизвестный тип мобилизации."
        profile = config.mobilization_profiles[mob_type]
        if requested_amount <= 0:
            return False, "Введите число больше нуля."

        req = profile["requirements"]
        factories = await self._effective_military_factories(country)
        war_status, _ = await self.db.get_country_war_and_risk(country)
        if factories < int(req["factories"]):
            return False, f"Нужно военных заводов: {req['factories']}, сейчас: {factories}."
        statuses = [str(s) for s in req["war_status"]]
        if statuses and war_status not in statuses:
            return False, f"Нужен статус: {self._war_statuses_ru(statuses)}. Сейчас: {self._war_status_ru(war_status)}."
        stats = await self.db.get_country_stats(country)
        _budget, _army, citizens, life_level = stats if stats else (0, 0, 100, 50)
        max_possible = max(1, int(citizens * 0.35))
        if requested_amount > max_possible:
            return False, f"Слишком много для текущего населения. Можно мобилизовать до {max_possible} человек (35% жителей: {citizens})."
        _war_status, risk_index = await self.db.get_country_war_and_risk(country)
        speed = self._mobilization_speed_profile(
            requested_amount=requested_amount,
            citizens=citizens,
            life_level=life_level,
            risk_index=risk_index,
            war_status=war_status,
            factories=factories,
            mob_type=mob_type,
        )
        week_key = self._week_key_utc()
        plan_key = f"mobplan:{country}"
        plan_raw = await self.db.get_state(plan_key, "")
        if plan_raw:
            try:
                plan = json.loads(plan_raw)
                if plan.get("active") and plan.get("week_key") == week_key:
                    return False, "Мобилизация уже запущена на эту неделю. Дождитесь завершения."
                if plan.get("stopped_week") == week_key:
                    return False, "На этой неделе мобилизация уже останавливалась. Повторный запуск запрещён."
            except Exception:
                pass

        payload = {
            "country": country,
            "mob_type": mob_type,
            "week_key": week_key,
            "target": int(requested_amount),
            "gained": 0,
            "active": True,
            "day4_synced": False,
            "started_ts": int(time.time()),
            "last_tick_ts": 0,
            "tick_rate": int(speed["tick_rate"]),
            "support": int(speed["support"]),
            "estimated_hours": int(speed["estimated_hours"]),
            "speed_factors": {
                "жители": speed["citizen_pressure"],
                "уровень_жизни": speed["life_factor"],
                "риск": speed["risk_factor"],
                "заводы": speed["factory_factor"],
                "положение": speed["war_factor"],
                "тип": speed["type_factor"],
            },
        }
        await self.db.set_state(plan_key, json.dumps(payload, ensure_ascii=False))
        await self.db.update_country_mobilization(country, mob_type, 0, requested_amount, week_key, int(time.time()))
        left = self._seconds_until_week_end()
        finish_dt = datetime.now(timezone.utc) + timedelta(seconds=left)
        await self._remember_generated_mobilization_signal(country, mob_type)
        announcement_sent = await self._publish_mobilization_start_news(country, mob_type, requested_amount, finish_dt, speed)
        await self.db.add_mobilization_attempt(country, mob_type, requested_amount, True, "start_ok_generated_news")
        return (
            True,
            f"✅ Запущена мобилизация: {profile['label']} на {requested_amount} человек в неделю.\n"
            f"📰 Новость о мобилизации: {'опубликована автоматически' if announcement_sent else 'создана, но не смогла отправиться в канал'}\n"
            f"⚙️ Скорость: {int(speed['tick_rate'])} человек за цикл; поддержка правительства: {int(speed['support'])}%\n"
            f"⏱ Прогноз набора: примерно {self._format_duration(int(speed['estimated_hours']) * 3600)}\n"
            f"⏱ Длительность до конца недели: {self._format_duration(left)}\n"
            f"📅 Завершится: {finish_dt.strftime('%d.%m.%Y %H:%M')} по UTC",
        )

    async def force_finish_mobilization(self, country: str, reason: str, actor_id: int) -> tuple[bool, str]:
        key = f"mobplan:{country}"
        raw = await self.db.get_state(key, "")
        if not raw:
            return False, "Активная мобилизация не найдена."
        try:
            plan = json.loads(raw)
        except Exception:
            return False, "Не удалось прочитать план мобилизации."
        if not plan.get("active"):
            return False, "Мобилизация уже завершена."
        plan["active"] = False
        plan["stopped_week"] = self._week_key_utc()
        plan["force_stopped_by"] = int(actor_id)
        plan["force_stop_reason"] = reason[:180]
        await self.db.set_state(key, json.dumps(plan, ensure_ascii=False))
        await self.db.add_mobilization_attempt(country, str(plan.get("mob_type", "unknown")), int(plan.get("target", 0)), True, f"forced_stop:{reason[:120]}")
        return True, "⛔️ Мобилизация принудительно остановлена."

    async def process_mobilization_plans(self) -> None:
        now_ts = int(time.time())
        week_key = self._week_key_utc()
        for key, raw in await self.db.list_state_prefix("mobplan:"):
            try:
                plan = json.loads(raw)
            except Exception:
                continue
            if not plan.get("active"):
                continue
            if plan.get("week_key") != week_key:
                plan["active"] = False
                plan["stopped_week"] = str(plan.get("week_key", week_key))
                await self.db.set_state(key, json.dumps(plan, ensure_ascii=False))
                continue
            if now_ts - int(plan.get("last_tick_ts", 0)) < 6 * 3600:
                continue

            country = str(plan["country"])
            mob_type = str(plan["mob_type"])
            target = int(plan["target"])
            gained = int(plan.get("gained", 0))
            remaining = max(0, target - gained)
            if remaining <= 0:
                plan["active"] = False
                plan["stopped_week"] = week_key
                await self.db.set_state(key, json.dumps(plan, ensure_ascii=False))
                continue
            soldiers_chunk = max(1, min(remaining, int(plan.get("tick_rate") or max(1, target // 7))))
            soldiers, budget_change, life_change, risk_change = await self.apply_mobilization_effects(country, mob_type, soldiers_chunk)
            new_gained = gained + soldiers
            plan["gained"] = new_gained
            plan["last_tick_ts"] = now_ts
            if new_gained >= target:
                plan["active"] = False
                plan["stopped_week"] = week_key
            await self.db.set_state(key, json.dumps(plan, ensure_ascii=False))
            await self.db.update_country_mobilization(country, mob_type, new_gained, target, week_key, now_ts)
            await self.db.add_mobilization_log(country, mob_type, soldiers, budget_change, life_change, risk_change, penalized=False)

    async def _sync_mobilization_day4_from_news(self, post: IncomingPost, text: str) -> None:
        if not post.source_country or post.source_country == "MANUAL":
            return
        if self._news_age_hours(post) > 96:
            return
        if not self._news_has_mobilization_signal(text):
            return

        plan_key = f"mobplan:{post.source_country}"
        raw = await self.db.get_state(plan_key, "")
        if not raw:
            return
        try:
            plan = json.loads(raw)
        except Exception:
            return
        if not plan.get("active") or plan.get("day4_synced"):
            return

        target = int(plan.get("target", 0))
        gained = int(plan.get("gained", 0))
        if target <= 0:
            return
        expected_day4 = max(1, int(round(target * 4 / 7)))
        if gained >= expected_day4:
            plan["day4_synced"] = True
            await self.db.set_state(plan_key, json.dumps(plan, ensure_ascii=False))
            return

        delta = expected_day4 - gained
        country = str(plan.get("country", post.source_country))
        mob_type = str(plan.get("mob_type", "conscription"))
        soldiers, budget_change, life_change, risk_change = await self.apply_mobilization_effects(country, mob_type, delta)
        plan["gained"] = gained + soldiers
        plan["day4_synced"] = True
        await self.db.set_state(plan_key, json.dumps(plan, ensure_ascii=False))
        await self.db.update_country_mobilization(
            country,
            mob_type,
            int(plan["gained"]),
            target,
            str(plan.get("week_key", self._week_key_utc())),
            int(time.time()),
        )
        await self.db.add_mobilization_log(country, mob_type, soldiers, budget_change, life_change, risk_change, penalized=False)

    async def publish_weekly_mobilization_summary_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        if now.weekday() != 6:
            return
        week_key = now.strftime("%G-W%V")
        state_key = f"mob_summary:{week_key}"
        if await self.db.get_state(state_key, "0") == "1":
            return

        monday = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=6)
        from_ts = int(monday.timestamp())
        to_ts = int((monday + timedelta(days=7)).timestamp())
        rows = await self.db.aggregate_mobilization_logs(from_ts, to_ts)
        if not rows:
            await self.db.set_state(state_key, "1")
            return

        def _fmt(v: int) -> str:
            if v == 0:
                return "не изменяется"
            return f"+{v}" if v > 0 else str(v)

        lines = ["<b>📊 Недельная мобилизационная сводка</b>"]
        for country, soldiers, budget_ch, life_ch, risk_ch in rows:
            lines.append(
                f"\n<b>{country}</b>\n"
                f"Солдаты: {_fmt(soldiers)} | Бюджет: {_fmt(budget_ch)} | "
                f"Жизнь: {_fmt(life_ch)} | Риск: {_fmt(risk_ch)}"
            )
        summary = "\n".join(lines)
        await self._send_to_target_channel(summary, parse_mode="html")
        await self.db.set_state(state_key, "1")

    async def publish_weekly_country_stats_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        if now.weekday() != 6:
            return
        week_key = now.strftime("%G-W%V")
        sent_key = f"weekly_country_stats_sent:{week_key}"
        if await self.db.get_state(sent_key, "0") == "1":
            return

        rows = await self.db.list_country_stats()
        if not rows:
            await self.db.set_state(sent_key, "1")
            return

        prev_key = f"weekly_country_stats_snapshot:{(now - timedelta(days=7)).strftime('%G-W%V')}"
        prev_raw = await self.db.get_state(prev_key, "{}")
        try:
            prev = json.loads(prev_raw)
        except Exception:
            prev = {}
        snapshot = {country: {"budget": b, "army": a, "citizens": c, "life": l} for country, b, a, c, l in rows}
        await self.db.set_state(f"weekly_country_stats_snapshot:{week_key}", json.dumps(snapshot, ensure_ascii=False))

        map_id = config.premium_emoji_ids.get("MAP", "")
        econ_id = config.premium_emoji_ids.get("ECONOMY", "")
        imp_id = config.premium_emoji_ids.get("IMPORTANT", "")
        dip_id = config.premium_emoji_ids.get("DIPLOMACY", "")
        warn_id = config.premium_emoji_ids.get("WARNING", "")

        def _delta(new_v: int, old_v: int | None) -> str:
            if old_v is None:
                return "новое"
            d = new_v - old_v
            if d == 0:
                return "не изменяется"
            return f"+{d}" if d > 0 else str(d)

        lines = [
            "<blockquote>",
            f"<tg-emoji emoji-id=\"{map_id}\"></tg-emoji> <b>Недельная сводка стран ({week_key})</b>",
            "</blockquote>",
        ]
        for country, budget, army, citizens, life in rows[:10]:
            old = prev.get(country, {})
            lines.append(
                f"\n<b>{country}</b>\n"
                f"<tg-emoji emoji-id=\"{econ_id}\"></tg-emoji> Бюджет: <b>{budget}</b> ({_delta(budget, old.get('budget'))})\n"
                f"<tg-emoji emoji-id=\"{imp_id}\"></tg-emoji> Армия: <b>{army}</b> ({_delta(army, old.get('army'))})\n"
                f"<tg-emoji emoji-id=\"{dip_id}\"></tg-emoji> Граждане: <b>{citizens}</b> ({_delta(citizens, old.get('citizens'))})\n"
                f"<tg-emoji emoji-id=\"{warn_id}\"></tg-emoji> Жизнь: <b>{life}</b> ({_delta(life, old.get('life'))})"
            )
        text = "\n".join(lines)
        await self._send_to_target_channel(text, parse_mode="html")
        await self.db.set_state(sent_key, "1")

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
            sent = await self._send_to_target_channel(message, parse_mode="html")
            if sent:
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
        key = self._post_queue_key(post)
        if key in self._queued_keys:
            return
        await self.db.save_pending_post(key, json.dumps(asdict(post), ensure_ascii=False), int(time.time()))
        if self.queue.full():
            logger.warning("Queue is full, keep post in pending storage: %s", key)
            await self._metric_inc("queue_overflow")
            return
        ingest_min = min(config.queue_ingest_delay_min, config.queue_ingest_delay_max)
        ingest_max = max(config.queue_ingest_delay_min, config.queue_ingest_delay_max)
        await asyncio.sleep(random.uniform(ingest_min, ingest_max))
        if self.queue.full():
            logger.warning("Queue became full after ingest delay, keep post in pending storage: %s", key)
            await self._metric_inc("queue_overflow")
            return
        await self.queue.put(post)
        self._queued_keys.add(key)

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
                await self._metric_inc("retry_after")
                await asyncio.sleep(wait_s)
            except FloodWaitError as exc:
                wait_s = max(1, int(getattr(exc, "seconds", 3)))
                logger.warning("FloodWaitError: wait %ss", wait_s)
                await self._metric_inc("flood_wait")
                await asyncio.sleep(wait_s)
            except (TelegramBadRequest, RPCError):
                if retries_left <= 0:
                    raise
                retries_left -= 1
                backoff = random.uniform(4.0, 10.0)
                logger.exception("Telegram publish error, retry in %.1fs (left=%s)", backoff, retries_left)
                await self._metric_inc("publish_retry")
                await asyncio.sleep(backoff)

    async def check_antiflood(self, user_id: int) -> tuple[bool, str]:
        if user_id == config.admin_id:
            return True, "OK"
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
        if user_id == config.admin_id:
            return True, "OK"
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
            key = self._post_queue_key(post)
            try:
                terminal_done = await self.process_post(post)
                if terminal_done:
                    await self.db.delete_pending_post(key)
            except Exception:
                logger.exception("Unhandled error on post processing")
            finally:
                self._queued_keys.discard(key)
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
                await self.process_mobilization_plans()
                await self.publish_weekly_mobilization_summary_if_due()
                await self.publish_weekly_country_stats_if_due()
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
            due = []
        for _, country, tech_name in due:
            await self.db.apply_country_stats_delta(country, life_delta=1, budget_delta=3000)
            text = (
                "<blockquote>"
                f"<b>🔬 Технология завершена:</b> <i>{country}</i>\n"
                f"Проект: <b>{tech_name}</b>\n"
                "Бонус: +3000 к бюджету и +1 к уровню жизни."
                "</blockquote>"
            )
            await self._send_to_target_channel(text, parse_mode="html")
        await self.process_completed_research()

    async def process_completed_research(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        due = await self.db.due_active_research(now_iso)
        if not due:
            return
        for item in due:
            country_id = int(item["country_id"])
            tech_id = str(item["tech_id"])
            country_name = str(item.get("country") or "") or await self.db.country_name_by_id(country_id)
            effects = RESEARCH_EFFECTS_DEFAULTS.get(tech_id, {}).copy()
            try:
                custom = json.loads(item.get("effects") or "{}")
                if isinstance(custom, dict):
                    effects.update(custom)
            except Exception:
                pass

            if effects.get("unlock_unit"):
                await self.db.add_country_unit(country_id, str(effects["unlock_unit"]), 1)
            await self.db.add_country_tech(country_id, tech_id)

            budget_delta = int(effects.get("budget_delta", 0) or 0)
            life_delta = int(effects.get("life_delta", 0) or 0)
            risk_delta = int(effects.get("risk_delta", 0) or 0)
            army_pct = float(effects.get("army_pct", 0.0) or 0.0)
            if army_pct:
                stats_rows = await self.db.list_country_stats()
                for c_name, _, army, _, _ in stats_rows:
                    if c_name == country_name:
                        await self.db.apply_country_stats_delta(
                            country_name,
                            army_delta=max(1, int(int(army) * army_pct)),
                            budget_delta=budget_delta,
                            life_delta=life_delta,
                            risk_delta=risk_delta,
                        )
                        break
            elif budget_delta or life_delta or risk_delta:
                await self.db.apply_country_stats_delta(
                    country_name,
                    budget_delta=budget_delta,
                    life_delta=life_delta,
                    risk_delta=risk_delta,
                )

            await self.db.complete_active_research(int(item["id"]))
            await self.db.add_research_log(
                country_id,
                tech_id,
                "completed",
                json.dumps({"effects": effects}, ensure_ascii=False),
            )

            text = (
                "<blockquote><b>🔬 ИССЛЕДОВАНИЕ ЗАВЕРШЕНО</b>\n"
                f"<i>{escape(country_name)}</i></blockquote>\n"
                f"<b>Технология:</b> {escape(item['name'])}\n"
                f"<b>Эффекты:</b> {escape(json.dumps(effects, ensure_ascii=False))}"
            )
            reply_to = item.get("start_message_id")
            await self._send_to_target_channel(
                text,
                parse_mode="html",
                reply_to=reply_to if reply_to else None,
            )

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

    async def process_post(self, post: IncomingPost) -> bool:
        if await self.is_paused():
            logger.info("Paused; skip post %s/%s", post.source_channel, post.message_id)
            return False
        if await self._is_daily_limit_reached():
            logger.info("Daily limit reached (%s), ignore %s/%s", config.daily_post_limit, post.source_channel, post.message_id)
            await self._metric_inc("daily_limit_hit")
            return True

        source_text = (post.text or "").strip()
        if not source_text and not post.has_media:
            logger.info("Empty message skip: %s/%s", post.source_channel, post.message_id)
            return True

        hash_value = content_hash(f"{post.source_channel}:{post.source_country}:{strip_hashtags(source_text)}")
        if await self.db.is_duplicate(hash_value):
            logger.info("Duplicate skip: %s", hash_value)
            return True

        translated = await self.translator.to_russian(source_text) if source_text else ""
        corrected = autocorrect_news_text(strip_emojis(translated or source_text))
        corrected = self._summarize_if_huge(post, corrected)
        corrected = self._extract_special_markers(corrected)
        corrected = self._humanize_text_variation(corrected)
        await self.remember_mobilization_signal(post, corrected)
        age_h = self._news_age_hours(post)
        if age_h > 168:
            corrected = f"Архивная новость (задержка публикации): {corrected}"
        await self._sync_mobilization_day4_from_news(post, corrected)

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
            return True

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
            return True

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
            return True

        if post.has_media:
            await self.send_to_moderation(
                post,
                formatted,
                "MEDIA_REQUIRES_ADMIN_APPROVAL",
                raw_text=corrected,
                suggestion="Проверьте соответствие RP и подпись к медиа. Если нужно — нажмите «Поправить».",
            )
            return True

        if self._is_research_post(corrected):
            research_html = self._render_research_html(post.source_country, corrected, formatted)
            published = await self.publish_and_mark(post, research_html, None, hash_value, auto_passed=True, html_mode=True)
        else:
            published = await self.publish_and_mark(post, formatted, entities, hash_value, auto_passed=True)
        return published

    @staticmethod
    def _is_research_post(text: str) -> bool:
        low = text.lower()
        return any(token in low for token in ["исследован", "#исследование", "#research", "лаборатор", "эксперимент", "научн"])

    @staticmethod
    def _render_research_html(country: str, raw_text: str, fallback_text: str) -> str:
        snippets = [s.strip() for s in re.split(r"\n{2,}", raw_text) if s.strip()]
        headline = escape(snippets[0] if snippets else fallback_text.splitlines()[0])
        body = escape(" ".join(snippets[1:]) if len(snippets) > 1 else raw_text)
        return (
            "<blockquote>"
            f"<b>🧪 Исследование · {escape(country)}</b>\n"
            f"<i>{headline}</i>"
            "</blockquote>\n\n"
            f"{body[:1200]}"
        )

    async def publish_and_mark(
        self,
        post: IncomingPost,
        formatted: str,
        entities: list | None,
        hash_value: str,
        auto_passed: bool = False,
        html_mode: bool = False,
    ) -> bool:
        try:
            await self._wait_human_publish_delay()
            if config.publish_delay_seconds > 0:
                await asyncio.sleep(min(config.publish_delay_seconds, 3.0))
            if self.user_client:
                if html_mode:
                    await self._send_with_retry(
                        lambda: self._send_to_target_channel(formatted, parse_mode="html")
                    )
                else:
                    await self._send_with_retry(
                        lambda: self._send_to_target_channel(formatted, formatting_entities=entities or [])
                    )
            else:
                logger.warning("Skipping publish %s/%s until user session connects.", post.source_channel, post.message_id)
                return False
            await self.db.mark_processed(post.source_channel, post.source_country, post.message_id, hash_value)
            await self._increment_daily_count()
            await self.db.increment_news_quality(post.source_country, 1 if auto_passed else 0, 1)
            await self._apply_country_stats_effect(post)
            await self._metric_inc("publish_ok")
            logger.info("Published %s/%s", post.source_channel, post.message_id)
            return True
        except (TelegramBadRequest, RPCError):
            logger.exception("Publish failed")
            await self._metric_inc("publish_failed")
            return False

    async def publish_media_and_mark(self, post: IncomingPost, caption: str, hash_value: str, auto_passed: bool = False) -> None:
        try:
            await self._wait_human_publish_delay()
            if self.user_client and post.media_file_id:
                await self._send_with_retry(
                    lambda: self.user_client.send_file(config.target_channel, file=post.media_file_id, caption=caption[:1024])
                )
            else:
                logger.warning("Skipping media publish %s/%s until user session connects.", post.source_channel, post.message_id)
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
            "published_ts": post.published_ts,
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
