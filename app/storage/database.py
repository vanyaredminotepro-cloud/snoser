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
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    publish_at_ts INTEGER NOT NULL,
                    source_country TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_violations (
                    user_id INTEGER PRIMARY KEY,
                    strikes INTEGER NOT NULL DEFAULT 0,
                    blocked_until_ts INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_leaders (
                    country TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'runtime',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (country, user_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS registration_applications (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    reg_type TEXT NOT NULL,
                    form_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_stats (
                    country TEXT PRIMARY KEY,
                    budget INTEGER NOT NULL DEFAULT 100000,
                    army INTEGER NOT NULL DEFAULT 1000,
                    life_level INTEGER NOT NULL DEFAULT 50,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def is_duplicate(self, content_hash: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT 1 FROM processed_posts WHERE content_hash = ?", (content_hash,))
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
            await db.execute("INSERT OR REPLACE INTO moderation_queue (token, payload) VALUES (?, ?)", (token, payload))
            await db.commit()

    async def pop_moderation_payload(self, token: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT payload FROM moderation_queue WHERE token = ?", (token,))
            row = await cursor.fetchone()
            await db.execute("DELETE FROM moderation_queue WHERE token = ?", (token,))
            await db.commit()
        return row[0] if row else None

    async def add_scheduled_post(self, publish_at_ts: int, source_country: str, text: str, created_by: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO scheduled_posts (publish_at_ts, source_country, text, created_by) VALUES (?, ?, ?, ?)",
                (publish_at_ts, source_country, text, created_by),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_due_scheduled_posts(self, now_ts: int) -> list[tuple[int, str, str]]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT id, source_country, text FROM scheduled_posts WHERE publish_at_ts <= ? ORDER BY publish_at_ts ASC",
                (now_ts,),
            )
            rows = await cursor.fetchall()
            await db.execute("DELETE FROM scheduled_posts WHERE publish_at_ts <= ?", (now_ts,))
            await db.commit()
        return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]

    async def add_strike(self, user_id: int, blocked_until_ts: int = 0) -> tuple[int, int]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO user_violations (user_id, strikes, blocked_until_ts) VALUES (?, 1, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET strikes = strikes + 1, blocked_until_ts = excluded.blocked_until_ts",
                (user_id, blocked_until_ts),
            )
            cursor = await db.execute("SELECT strikes, blocked_until_ts FROM user_violations WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            await db.commit()
        return int(row[0]), int(row[1])

    async def is_user_blocked(self, user_id: int, now_ts: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT blocked_until_ts FROM user_violations WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        return bool(row and int(row[0]) > now_ts)


    async def add_country_leader(self, country: str, user_id: int, source: str = "runtime") -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_leaders (country, user_id, source) VALUES (?, ?, ?)",
                (country, user_id, source),
            )
            await db.commit()

    async def seed_country_leaders(self, mapping: dict[str, list[int]]) -> int:
        inserted = 0
        async with aiosqlite.connect(self.path) as db:
            for country, ids in mapping.items():
                for user_id in ids:
                    cursor = await db.execute(
                        "INSERT OR IGNORE INTO country_leaders (country, user_id, source) VALUES (?, ?, 'config')",
                        (country, int(user_id)),
                    )
                    inserted += cursor.rowcount or 0
            await db.commit()
        return inserted


    async def store_registration_application(self, token: str, user_id: int, reg_type: str, form_text: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO registration_applications (token, user_id, reg_type, form_text, status) VALUES (?, ?, ?, ?, 'pending')",
                (token, user_id, reg_type, form_text),
            )
            await db.commit()

    async def get_registration_application(self, token: str) -> tuple[int, str, str, str] | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT user_id, reg_type, form_text, status FROM registration_applications WHERE token = ?",
                (token,),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return int(row[0]), str(row[1]), str(row[2]), str(row[3])

    async def set_registration_application_status(self, token: str, status: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE registration_applications SET status = ? WHERE token = ?", (status, token))
            await db.commit()

    async def get_user_violation(self, user_id: int) -> tuple[int, int] | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT strikes, blocked_until_ts FROM user_violations WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        if not row:
            return None
        return int(row[0]), int(row[1])

    async def is_country_leader(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT 1 FROM country_leaders WHERE user_id = ? LIMIT 1", (user_id,))
            row = await cursor.fetchone()
        return row is not None

    async def has_approved_registration(self, user_id: int, reg_type: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM registration_applications WHERE user_id = ? AND reg_type = ? AND status = 'approved' LIMIT 1",
                (user_id, reg_type),
            )
            row = await cursor.fetchone()
        return row is not None

    async def news_stats(self) -> tuple[int, int, int, int]:
        async with aiosqlite.connect(self.path) as db:
            total = await (await db.execute("SELECT COUNT(*) FROM processed_posts")).fetchone()
            day = await (await db.execute("SELECT COUNT(*) FROM processed_posts WHERE created_at >= datetime('now','-1 day')")).fetchone()
            week = await (await db.execute("SELECT COUNT(*) FROM processed_posts WHERE created_at >= datetime('now','-7 day')")).fetchone()
            month = await (await db.execute("SELECT COUNT(*) FROM processed_posts WHERE created_at >= datetime('now','-30 day')")).fetchone()
        return int(day[0]), int(week[0]), int(month[0]), int(total[0])

    async def apply_country_stats_delta(self, country: str, budget_delta: int = 0, army_delta: int = 0, life_delta: int = 0) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_stats (country) VALUES (?)",
                (country,),
            )
            await db.execute(
                "UPDATE country_stats SET "
                "budget = MAX(0, budget + ?), "
                "army = MAX(0, army + ?), "
                "life_level = MIN(100, MAX(0, life_level + ?)), "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE country = ?",
                (budget_delta, army_delta, life_delta, country),
            )
            await db.commit()

    async def get_country_stats(self, country: str) -> tuple[int, int, int] | None:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute(
                "SELECT budget, army, life_level FROM country_stats WHERE country = ?",
                (country,),
            )).fetchone()
        if not row:
            return None
        return int(row[0]), int(row[1]), int(row[2])

    async def list_country_stats(self) -> list[tuple[str, int, int, int]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                "SELECT country, budget, army, life_level FROM country_stats ORDER BY budget DESC, army DESC"
            )).fetchall()
        return [(str(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in rows]
