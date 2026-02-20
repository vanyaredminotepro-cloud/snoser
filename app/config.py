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
            "DEFAULT": "5210956306952758910",
            "IMPORTANT": "5274099962655816924",
            "ECONOMY": "5456140674028019486",
            "DIPLOMACY": "5467538555158943525",
            "WARNING": "5447644880824181073",
            "MAP": "5447410659077661506",
        }
    )

    country_hashtags: dict[str, list[str]] = field(
        default_factory=lambda: {
            'Орден "ГНЕВ"': ["#GNEV"],
            "Обоссляндия": ["#ОБСС", "#ОБС"],
            "Олбония": ["#OB", "#ОБ"],
            "ОВС": ["#ОВС"],
            "Аборигены": ["#АБР"],
            "ЧВК Пиран": ["#Пиран", "#ЧВКПиран"],
            "Кермания": ["#КК8"],
            "Новрания": ["#NOV"],
            "Коробочкия": ["#КРБ", "#KRB"],
            "Северландия": ["#СВ", "#SV"],
            "Зитор": ["#ЗТ", "#ZT"],
            "СВРО": ["#СВРО", "#SVR"],
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
            "Лекси": ["#Leksy", "#LKS"],
            "Лютый": ["#LT"],
            "MANUAL": ["#РП"],
        }
    )

    country_aliases: dict[str, list[str]] = field(
        default_factory=lambda: {
            "Обоссляндия": ["обоссляндия", "обоссландия", "обоссландия"],
            "Олбония": ["олбони", "олбония", "королевство олбония"],
            "Вилония": ["вилония"],
            "ТНР": ["тнр"],
            'Орден "ГНЕВ"': ["гнев", "орден гнев"],
            "Северландия": ["северландия"],
            "Антония": ["антония", "антонская русь"],
            "Зитор": ["зитор"],
            "СВРО": ["свро"],
            "ФШП": ["фшп", "пехико"],
        }
    )



config = Config()
