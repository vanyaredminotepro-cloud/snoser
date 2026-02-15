import aiosqlite


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_chat TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS moderation_queue (
                    token TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def is_duplicate(self, content_hash: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM processed_posts WHERE content_hash = ?", (content_hash,)
            )
            row = await cursor.fetchone()
        return row is not None

    async def mark_processed(self, source_chat: str, message_id: int, content_hash: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO processed_posts (source_chat, message_id, content_hash) VALUES (?, ?, ?)",
                (source_chat, message_id, content_hash),
            )
            await db.commit()

    async def set_state(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO app_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()

    async def get_state(self, key: str, default: str = "") -> str:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT value FROM app_state WHERE key = ?", (key,))
            row = await cursor.fetchone()
        return row[0] if row else default

    async def store_moderation_payload(self, token: str, payload: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO moderation_queue (token, payload) VALUES (?, ?)",
                (token, payload),
            )
            await db.commit()

    async def pop_moderation_payload(self, token: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT payload FROM moderation_queue WHERE token = ?", (token,)
            )
            row = await cursor.fetchone()
            await db.execute("DELETE FROM moderation_queue WHERE token = ?", (token,))
            await db.commit()
        return row[0] if row else None
