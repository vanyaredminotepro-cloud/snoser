from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Iterable, Optional


def _load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_dotenv_if_present(paths: Optional[Iterable[Path]] = None) -> None:
    candidates = list(paths or [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ])
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        _load_dotenv_file(resolved)

def _first_present_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _optional_env_int(*names: str) -> Optional[int]:
    raw = _first_present_env(*names)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        names_str = ", ".join(names)
        raise RuntimeError(f"Environment variable {names_str} must be an integer") from exc


def _optional_env_bool(*names: str, default: bool = False) -> bool:
    raw = _first_present_env(*names)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    names_str = ", ".join(names)
    raise RuntimeError(f"Environment variable {names_str} must be a boolean (true/false, 1/0)")


def _optional_env_float(*names: str) -> Optional[float]:
    raw = _first_present_env(*names)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        names_str = ", ".join(names)
        raise RuntimeError(f"Environment variable {names_str} must be a float") from exc


def _optional_env_json(*names: str) -> Optional[dict]:
    raw = _first_present_env(*names)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        names_str = ", ".join(names)
        raise RuntimeError(f"Environment variable {names_str} must contain valid JSON object") from exc
    if not isinstance(payload, dict):
        names_str = ", ".join(names)
        raise RuntimeError(f"Environment variable {names_str} must contain JSON object")
    return payload


def _optional_env_list(*names: str) -> list[str]:
    raw = _first_present_env(*names)
    if raw is None:
        return []
    chunks = [part.strip() for part in raw.replace("\n", ",").split(",")]
    return [c for c in chunks if c]


@dataclass(slots=True)
class Config:
    api_id: Optional[int] = field(default_factory=lambda: _optional_env_int("TG_API_ID", "API_ID"))
    api_hash: Optional[str] = field(default_factory=lambda: _first_present_env("TG_API_HASH", "API_HASH"))
    bot_token: Optional[str] = field(default_factory=lambda: _first_present_env("TG_BOT_TOKEN", "BOT_TOKEN"))

    admin_id: int = field(default_factory=lambda: _optional_env_int("ADMIN_ID") or 5006629901)
    admin_username: str = field(default_factory=lambda: _first_present_env("ADMIN_USERNAME") or "@supermegaluti")
    bot_locale: str = field(default_factory=lambda: (_first_present_env("BOT_LOCALE") or "ru").lower())

    target_channel: str = field(default_factory=lambda: _first_present_env("TARGET_CHANNEL") or "@novostnikobosslandia")
    publish_delay_seconds: float = field(default_factory=lambda: float(_first_present_env("PUBLISH_DELAY_SECONDS") or "0.0"))
    queue_ingest_delay_min: float = field(default_factory=lambda: _optional_env_float("QUEUE_INGEST_DELAY_MIN") or 2.0)
    queue_ingest_delay_max: float = field(default_factory=lambda: _optional_env_float("QUEUE_INGEST_DELAY_MAX") or 5.0)
    queue_publish_delay_min: float = field(default_factory=lambda: _optional_env_float("QUEUE_PUBLISH_DELAY_MIN") or 3.0)
    queue_publish_delay_max: float = field(default_factory=lambda: _optional_env_float("QUEUE_PUBLISH_DELAY_MAX") or 9.0)
    long_pause_chance: float = field(default_factory=lambda: _optional_env_float("LONG_PAUSE_CHANCE") or 0.20)
    long_pause_min: float = field(default_factory=lambda: _optional_env_float("LONG_PAUSE_MIN") or 15.0)
    long_pause_max: float = field(default_factory=lambda: _optional_env_float("LONG_PAUSE_MAX") or 20.0)
    daily_post_limit: int = field(default_factory=lambda: _optional_env_int("DAILY_POST_LIMIT") or 30)

    session_name: str = field(default_factory=lambda: _first_present_env("SESSION_NAME") or "news_userbot")
    sqlite_path: Path = field(default_factory=lambda: Path(_first_present_env("SQLITE_PATH") or "app/storage/bot_data.sqlite3"))
    logs_dir: Path = field(default_factory=lambda: Path(_first_present_env("LOGS_DIR") or "logs"))
    emoji_storage_path: Path = Path("app/storage/emojis.json")
    port: int = field(default_factory=lambda: _optional_env_int("PORT") or 8080)
    healthcheck_enabled: bool = field(default_factory=lambda: _optional_env_bool("HEALTHCHECK_ENABLED", default=True))
    web_dashboard_url: str = field(default_factory=lambda: _first_present_env("WEB_DASHBOARD_URL") or "https://islam.net")
    webhook_port: int = field(default_factory=lambda: _optional_env_int("WEBHOOK_PORT") or 8090)
    bot_webhook_secret: str = field(default_factory=lambda: _first_present_env("BOT_WEBHOOK_SECRET") or "dev-secret")
    tg_api_host: str = field(default_factory=lambda: _first_present_env("TG_API_HOST") or "")
    tg_api_port: int = field(default_factory=lambda: _optional_env_int("TG_API_PORT") or 443)
    proxy: dict = field(
        default_factory=lambda: _optional_env_json("TG_PROXY_JSON")
        or {}
    )
    proxy_fallback_links: list[str] = field(
        default_factory=lambda: _optional_env_list("TG_PROXY_LINKS")
        or [
            "https://t.me/proxy?server=65.109.213.227&port=65535&secret=EERighJJvXrFGRMCIMJdCQRueWVrdGFuZXQuY29tZmFyYWthdi5jb212YW4ubmFqdmEuY29tAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "https://t.me/proxy?server=65.109.210.202&port=8443&secret=EERighJJvXrFGRMCIMJdCQRueWVrdGFuZXQuY29tZmFyYWthdi5jb212YW4ubmFqdmEuY29tAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "https://t.me/proxy?server=tggo.store&port=443&secret=7uzWmAwONp7D1ujd83Bwkr50Z2dvLnN0b3Jl",
            "https://t.me/proxy?server=tg.proxywing.net&port=443&secret=dd398e9112420ca2ad72bac8bfd851ff42",
            "https://t.me/proxy?server=exact.begoodtunnel.su&port=443&secret=eed802c58b0133cc8db3c6880bab5308c165786163742e6265676f6f6474756e6e656c2e7375",
        ]
    )
    antiflood_window_sec: int = 1
    antiflood_max_messages: int = 5
    antiflood_window: int = 10
    antiflood_max_actions: int = 5
    antiflood_ban_duration: int = 300
    scheduler_poll_seconds: int = 5
    rss_poll_seconds: int = 45
    war_digest_threshold: int = 4
    map_request_cooldown_minutes: int = 30

    source_channels: dict[str, str] = field(
        default_factory=lambda: {
            "Антония": "antoniats",
            "Вилония": "Viloniarp",
            "ТНР": "NARallies",
            "ОСР": "OSRres",
            "Олбония": "olbonia",
            "Северландия": "severlandia",
            "Обоссляндия": "obosslandia",
            "Зитор": "Zitorchik",
            "Сэрландия": "NewSerland",
            "ДШРГ Торнадо": "DSHRGTornado",
            'ЧВК "Компф"': "PMC_Kompf",
            'Орден "ГНЕВ"': "gnevto",
            "Лорд-протекторат": "Lord_Protektorat",
            "ФШП": "pexicoRP",
            "Белоярск": "BEIOYRSK",
            "Аль-Нуурия": "djdjsjsjjiw",
            "Крелония": "+KYJZpV6_i0dlYmQy",
        }
    )

    rss_feeds: dict[str, str] = field(default_factory=dict)

    premium_emoji_ids: dict[str, str] = field(
        default_factory=lambda: {
            "DEFAULT": "5210956306952758910",      # 👀
            "IMPORTANT": "5274099962655816924",    # ❗️
            "ECONOMY": "5244837092042750681",      # 📈
            "DIPLOMACY": "5467538555158943525",    # 💭
            "WARNING": "5447644880824181073",      # ⚠️
            "MAP": "5447410659077661506",          # 🌐
        }
    )


    emoji_packs: dict[str, str] = field(
        default_factory=lambda: {
            # По умолчанию используем только подтверждённый пак.
            "news_emoji": "https://t.me/addemoji/NewsEmoji",
        }
    )

    custom_emoji_catalog: dict[str, str] = field(
        default_factory=lambda: {
            "EYES": "5210956306952758910",         # 👀
            "SMILE": "5461117441612462242",        # 🙂
            "LIGHTNING": "5456140674028019486",    # ⚡️
            "COMET": "5224607267797606837",        # ☄️
            "WARNING": "5447644880824181073",      # ⚠️
            "STOP": "5260293700088511294",         # ⛔️
            "NO_ENTRY": "5240241223632954241",     # 🚫
            "IMPORTANT": "5274099962655816924",    # ❗️
            "QUESTION": "5436113877181941026",     # ❓
            "MAP": "5447410659077661506",          # 🌐
            "SPEECH": "5443038326535759644",       # 💬
            "THOUGHT": "5467538555158943525",      # 💭
            "UP": "5449683594425410231",           # 🔼
            "DOWN": "5447183459602669338",         # 🔽
            "CHART_UP": "5244837092042750681",     # 📈
            "CHART_DOWN": "5246762912428603768",   # 📉
            "MONEY": "5409048419211682843",        # 💵
            "FIRE": "5424972470023104089",         # 🔥
            "EXPLOSION": "5276032951342088188",    # 💥
            "SEARCH": "5231012545799666522",       # 🔍
            "SHIELD": "5251203410396458957",       # 🛡
            "STAR": "5438496463044752972",         # ⭐️
            "CROWN": "5217822164362739968",        # 👑
        }
    )

    country_hashtags: dict[str, list[str]] = field(
        default_factory=lambda: {
            'Орден "ГНЕВ"': ["#GNEV"],
            "Обоссляндия": ["#OBS"],
            "Олбония": ["#OB"],
            "ОВС": ["#OVS"],
            "Аборигены": ["#ABR"],
            "ЧВК Пиран": ["#PIR"],
            "Кермания": ["#KK8", "#КК8"],
            "Новрания": ["#NOV", "#TNR"],
            "Коробочкия": ["#KRB"],
            "Северландия": ["#SV"],
            "Зитор": ["#ZT"],
            "СВРО": ["#SVR"],
            "ФШП": ["#FHP"],
            "ONV": ["#ONV"],
            "ОСР": ["#OSR"],
            "Пандекстан": ["#PNX"],
            "Мерцорленд": ["#MR"],
            "Каризайн": ["#KRZ"],
            "Смертоградск": ["#SMR"],
            "Север": ["#SEV"],
            "ПНТВ": ["#PNTV"],
            "Казербия": ["#KZR"],
            "OV": ["#OV"],
            "Гниляндия": ["#GNL"],
            "Вилония": ["#VL"],
            "Антония": ["#AN"],
            "ТНР": ["#TNR"],
            "Крелония": ["#KRL"],
            "Сэрландия": ["#RK"],
            "ДШРГ Торнадо": ["#TRD"],
            "Лорд-протекторат": ["#LPR"],
            "Белоярск": ["#BYR"],
            "Аль-Нуурия": ["#AL"],
            'ЧВК "Компф"': ["#KMPF"],
            "Лекси": ["#LKS"],
            "Лютый": ["#LT"],
            "РКА": ["#RKA"],
            "Искандер": ["#ISK"],
            "MANUAL": ["#RP"],
        }
    )

    country_aliases: dict[str, list[str]] = field(
        default_factory=lambda: {
            "Обоссляндия": ["обоссляндия", "обоссландия", "обоссландия"],
            "Олбония": ["олбони", "олбония", "королевство олбония"],
            "Вилония": ["вилония"],
            "ТНР": ["тнр"],
            "ДШРГ Торнадо": ["дшрг торнадо", "торнадо"],
            "Новрания": ["новрания"],
            "ОСР": ["оср"],
            "Пандекстан": ["пандекстан", "пандекстане"],
            "Мерцорленд": ["мерцорленд", "мерцорленде"],
            "Каризайн": ["каризайн", "каризайна"],
            "Смертоградск": ["смертоградск", "смертоградска"],
            'Орден "ГНЕВ"': ["гнев", "орден гнев"],
            "Северландия": ["северландия"],
            "Антония": ["антония", "антонская русь"],
            "Зитор": ["зитор"],
            "СВРО": ["свро"],
            "ФШП": ["фшп", "пехико"],
        }
    )



    def require_runtime_credentials(self) -> tuple[int, str, str]:
        missing: list[str] = []
        if self.api_id is None:
            missing.append("TG_API_ID (or API_ID)")
        if not self.api_hash:
            missing.append("TG_API_HASH (or API_HASH)")
        if not self.bot_token:
            missing.append("TG_BOT_TOKEN (or BOT_TOKEN)")

        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(
                "Telegram credentials are not configured. "
                f"Set environment variables: {joined}."
            )

        return self.api_id, self.api_hash, self.bot_token

    manual_country_authors: dict[str, list[int]] = field(
        default_factory=lambda: {
            "Обоссляндия": [5006629901],
            "Северландия": [7804994596],
            "Вилония": [5242248591, 7106809999, 851502775],
            "Олбония": [6222070752],
            "Аль-Нуурия": [5293616282],
            "Гниляндия": [6719511126, 5287169312],
            "Антония": [1135569287, 5666194662],
            "ТНР": [6763233916],
            "Новрания": [6763233916],
            "Крелония": [5862738376],
            "Зитор": [6364324300],
            'Орден "ГНЕВ"': [8318664912],
        }
    )

    initial_country_stats: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "Триединая Русь": {"army": 420, "budget": 116_000, "citizens": 1800, "life_level": 62},
            "Ось-Возмездия": {"army": 350, "budget": 105_000, "citizens": 1400, "life_level": 58},
            "Обоссляндия": {"army": 180, "budget": 140_000, "citizens": 2200, "life_level": 66},
            "ТНР": {"army": 175, "budget": 110_000, "citizens": 1200, "life_level": 57},
            "Вилония": {"army": 172, "budget": 87_000, "citizens": 1150, "life_level": 55},
            "Северландия": {"army": 150, "budget": 100_000, "citizens": 1000, "life_level": 56},
            "Зитор": {"army": 137, "budget": 93_000, "citizens": 790, "life_level": 54},
            "Аль-Нуурия": {"army": 90, "budget": 80_000, "citizens": 400, "life_level": 50},
            "Белоярск": {"army": 58, "budget": 65_000, "citizens": 280, "life_level": 49},
        }
    )

    initial_military_factories: dict[str, int] = field(
        default_factory=lambda: {
            # Сводка из присланного RP-дампа 29.05.2026: построенные/запущенные/начатые военные заводы.
            "Обоссляндия": 5,
            "Олбония": 2,
            "Северландия": 4,
            "Зитор": 7,
            "Новрания": 2,
            'Орден "ГНЕВ"': 3,
            "Ось-Возмездия": 3,
            "Вилония": 7,
            "Аль-Нуурия": 2,
            "Пандекстан": 4,
            "Гниляндия": 1,
            "ОСР": 2,
            "ДШРГ Торнадо": 1,
            "Смертоградск": 1,
            "Антония": 2,
            "ТНР": 1,
        }
    )

    initial_economic_resources: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            # oil/metal/grain условные игровые очки ресурсов, выведенные из новостей о производстве/агро/заводах.
            "Обоссляндия": {"oil": 20, "metal": 85, "grain": 35},
            "Олбония": {"oil": 10, "metal": 45, "grain": 20},
            "Северландия": {"oil": 15, "metal": 70, "grain": 30},
            "Зитор": {"oil": 20, "metal": 95, "grain": 80},
            "Новрания": {"oil": 10, "metal": 60, "grain": 25},
            'Орден "ГНЕВ"': {"oil": 5, "metal": 95, "grain": 10},
            "Ось-Возмездия": {"oil": 10, "metal": 90, "grain": 15},
            "Вилония": {"oil": 25, "metal": 95, "grain": 45},
            "Аль-Нуурия": {"oil": 25, "metal": 45, "grain": 55},
            "Пандекстан": {"oil": 25, "metal": 70, "grain": 85},
            "Мерцорленд": {"oil": 20, "metal": 45, "grain": 70},
            "Гниляндия": {"oil": 5, "metal": 35, "grain": 15},
            "ОСР": {"oil": 10, "metal": 65, "grain": 25},
            "ДШРГ Торнадо": {"oil": 5, "metal": 40, "grain": 5},
            "Смертоградск": {"oil": 5, "metal": 45, "grain": 10},
            "Антония": {"oil": 20, "metal": 45, "grain": 45},
            "ТНР": {"oil": 10, "metal": 25, "grain": 35},
        }
    )

    initial_country_extra_metrics: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "Обоссляндия": {"territories_month": 12, "alliances": 3, "treaties": 2, "stability_index": 92, "quality_percent": 94},
            "Триединая Русь": {"territories_month": 8, "alliances": 4, "treaties": 2, "stability_index": 78, "quality_percent": 85},
            "Ось-Возмездия": {"territories_month": 2, "alliances": 5, "treaties": 1, "stability_index": 55, "quality_percent": 60},
            "ТНР": {"territories_month": 3, "alliances": 2, "treaties": 1, "stability_index": 75, "quality_percent": 89},
            "Вилония": {"territories_month": 6, "alliances": 3, "treaties": 1, "stability_index": 48, "quality_percent": 65},
            "Северландия": {"territories_month": 5, "alliances": 2, "treaties": 1, "stability_index": 70, "quality_percent": 82},
            "Зитор": {"territories_month": 4, "alliances": 1, "treaties": 1, "stability_index": 68, "quality_percent": 80},
            "Аль-Нуурия": {"territories_month": 2, "alliances": 1, "treaties": 0, "stability_index": 65, "quality_percent": 78},
            "Белоярск": {"territories_month": 1, "alliances": 0, "treaties": 0, "stability_index": 60, "quality_percent": 75},
        }
    )
    mobilization_profiles: dict[str, dict[str, object]] = field(
        default_factory=lambda: {
            "conscription": {
                "label": "Призывы",
                "min_gain": 2,
                "max_gain": 5,
                "requirements": {"factories": 0, "war_status": []},
                "effects": {"budget_pct": 0.0, "life_pct": 0.0, "risk_delta": 0},
                "penalty": {"mode": "warn"},
            },
            "voluntary": {
                "label": "Добровольная",
                "min_gain": 5,
                "max_gain": 10,
                "requirements": {"factories": 1, "war_status": []},
                "effects": {"budget_pct": 0.0, "life_pct": 0.05, "risk_delta": 0},
                "penalty": {"mode": "block", "days": 3},
            },
            "partial": {
                "label": "Частичная",
                "min_gain": 10,
                "max_gain": 20,
                "requirements": {"factories": 1, "war_status": ["threat", "martial_law", "war", "total_war"]},
                "effects": {"budget_pct": -0.05, "life_pct": 0.0, "risk_delta": 0},
                "penalty": {"mode": "budget_pct", "value": -0.10},
            },
            "normal": {
                "label": "Обычная",
                "min_gain": 15,
                "max_gain": 30,
                "requirements": {"factories": 1, "war_status": ["martial_law", "war", "total_war"]},
                "effects": {"budget_pct": -0.10, "life_pct": -0.05, "risk_delta": 0},
                "penalty": {"mode": "warn_demob", "demob_pct": 0.10},
            },
            "aggressive": {
                "label": "Агрессивная",
                "min_gain": 25,
                "max_gain": 50,
                "requirements": {"factories": 2, "war_status": ["war", "total_war"]},
                "effects": {"budget_pct": -0.20, "life_pct": -0.10, "risk_delta": 5},
                "penalty": {"mode": "warn_demob", "demob_pct": 0.20},
            },
            "total": {
                "label": "Всеобщая",
                "min_gain": 40,
                "max_gain": 80,
                "requirements": {"factories": 2, "war_status": ["total_war", "war"]},
                "effects": {"budget_pct": -0.30, "life_pct": -0.20, "risk_delta": 15},
                "penalty": {"mode": "hard"},
            },
        }
    )

    def __post_init__(self) -> None:
        if self.queue_ingest_delay_min < 0 or self.queue_ingest_delay_max < 0:
            raise RuntimeError("QUEUE_INGEST_DELAY_* must be >= 0")
        if self.queue_publish_delay_min < 0 or self.queue_publish_delay_max < 0:
            raise RuntimeError("QUEUE_PUBLISH_DELAY_* must be >= 0")
        if self.long_pause_min < 0 or self.long_pause_max < 0:
            raise RuntimeError("LONG_PAUSE_* must be >= 0")
        if not (0.0 <= self.long_pause_chance <= 1.0):
            raise RuntimeError("LONG_PAUSE_CHANCE must be between 0 and 1")
        if self.daily_post_limit <= 0:
            raise RuntimeError("DAILY_POST_LIMIT must be > 0")


_load_dotenv_if_present()

config = Config()
