from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Config:
    api_id: int = 23695534
    api_hash: str = "08f5b069bb4fd8505b98a6b57f857868"
    bot_token: str = "8559159012:AAEz0BgKDRgRYFfCcXDf5VNrpS2uVp-mwCo"

    admin_id: int = 5006629901
    admin_username: str = "@supermegaluti"

    target_channel: str = "@novostnikobosslandia"
    publish_delay_seconds: float = 0.0

    session_name: str = "news_userbot"
    sqlite_path: Path = Path("app/storage/bot_data.sqlite3")
    logs_dir: Path = Path("logs")
    emoji_storage_path: Path = Path("app/storage/emojis.json")

    antiflood_window_sec: int = 20
    antiflood_max_messages: int = 5
    scheduler_poll_seconds: int = 5
    rss_poll_seconds: int = 45
    war_digest_threshold: int = 4
    map_request_cooldown_minutes: int = 30

    source_channels: dict[str, str] = field(
        default_factory=lambda: {
            "Антония": "antoniats",
            "Вилония": "Viloniarp",
            "ТНР": "NARallies",
            "Олбония": "olbonia",
            "Северландия": "severlandia",
            "Обоссляндия": "obosslandia",
            "Зитор": "Zitorchik",
            "Сэрландия": "NewSerland",
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
            "flaerium": "https://t.me/addemoji/Flaerium",
            "premium_flowers": "https://t.me/addemoji/FlowersPremium",
            "animals": "https://t.me/addemoji/PremiumAnimals",
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
            "ЧВК Пиран": ["#PIRAN"],
            "Кермания": ["#KK8"],
            "Новрания": ["#NOV"],
            "Коробочкия": ["#KRB"],
            "Северландия": ["#SV"],
            "Зитор": ["#ZT"],
            "СВРО": ["#SVR"],
            "ФШП": ["#FHP"],
            "ONV": ["#ONV"],
            "Казербия": ["#KZR"],
            "OV": ["#OV"],
            "Гниляндия": ["#GNL"],
            "Вилония": ["#VL"],
            "Антония": ["#AN"],
            "ТНР": ["#TNR"],
            "Крелония": ["#KRL"],
            "Сэрландия": ["#SRL"],
            "Лорд-протекторат": ["#LPR"],
            "Белоярск": ["#BYR"],
            "Аль-Нуурия": ["#ANR"],
            'ЧВК "Компф"': ["#KMPF"],
            "Лекси": ["#LKS"],
            "Лютый": ["#LT"],
            "MANUAL": ["#RP"],
        }
    )

    country_aliases: dict[str, list[str]] = field(
        default_factory=lambda: {
            "Обоссляндия": ["обоссляндия", "обоссландия", "обоссландия"],
            "Олбония": ["олбони", "олбония", "королевство олбония"],
            "Вилония": ["вилония"],
            "ТНР": ["тнр"],
            "Новрания": ["новрания"],
            'Орден "ГНЕВ"': ["гнев", "орден гнев"],
            "Северландия": ["северландия"],
            "Антония": ["антония", "антонская русь"],
            "Зитор": ["зитор"],
            "СВРО": ["свро"],
            "ФШП": ["фшп", "пехико"],
        }
    )

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


config = Config()
