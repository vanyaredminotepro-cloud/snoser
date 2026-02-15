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

    country_hashtags: dict[str, str] = field(
        default_factory=lambda: {
            "Антония": "#Антония",
            "Вилония": "#Вилония",
            "ТНР": "#ТНР",
            "Олбония": "#Олбония",
            "Северландия": "#Северландия",
            "Обоссляндия": "#Обоссляндия",
            "Зитор": "#Зитор",
            "Сэрландия": "#Сэрландия",
            'ЧВК "Компф"': "#Компф",
            'Орден "ГНЕВ"': "#ГНЕВ",
            "Лорд-протекторат": "#ЛордПротекторат",
            "ФШП": "#ФШП",
            "Белоярск": "#Белоярск",
            "Аль-Нуурия": "#АльНуурия",
            "Крелония": "#Крелония",
        }
    )


config = Config()
