from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    db_path: str = os.environ.get("DB_PATH", "app/storage/bot_data.sqlite3")
    api_key: str = os.environ.get("WEB_API_TOKEN", "")
    host: str = os.environ.get("WEB_HOST", "0.0.0.0")
    port: int = int(os.environ.get("WEB_PORT", "5000"))


settings = Settings()
