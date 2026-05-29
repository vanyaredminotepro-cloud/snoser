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
                    source_country TEXT NOT NULL DEFAULT 'MANUAL',
                    message_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            try:
                await db.execute("ALTER TABLE processed_posts ADD COLUMN source_country TEXT NOT NULL DEFAULT 'MANUAL'")
            except aiosqlite.OperationalError:
                pass
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
                    citizens INTEGER NOT NULL DEFAULT 100,
                    life_level INTEGER NOT NULL DEFAULT 50,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_territory_progress (
                    country TEXT PRIMARY KEY,
                    territories_month INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_diplomacy_stats (
                    country TEXT PRIMARY KEY,
                    alliances INTEGER NOT NULL DEFAULT 0,
                    treaties INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_stability_stats (
                    country TEXT PRIMARY KEY,
                    stability_index INTEGER NOT NULL DEFAULT 50,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_news_quality (
                    country TEXT PRIMARY KEY,
                    autopassed INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS monthly_awards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month_key TEXT NOT NULL,
                    award_name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS diplomatic_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country_a TEXT NOT NULL,
                    country_b TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(country_a, country_b, relation_type)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS technology_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country TEXT NOT NULL,
                    tech_name TEXT NOT NULL,
                    started_at INTEGER NOT NULL,
                    complete_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'in_progress'
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS crisis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country TEXT NOT NULL,
                    crisis_type TEXT NOT NULL,
                    effect_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS economic_resources (
                    country TEXT PRIMARY KEY,
                    oil INTEGER NOT NULL DEFAULT 0,
                    metal INTEGER NOT NULL DEFAULT 0,
                    grain INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_missions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day_key TEXT NOT NULL,
                    mission_text TEXT NOT NULL,
                    reward_budget INTEGER NOT NULL DEFAULT 0,
                    reward_life INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_warnings (
                    country TEXT PRIMARY KEY,
                    warnings INTEGER NOT NULL DEFAULT 0,
                    last_reason TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS antiflood_bans (
                    user_id INTEGER PRIMARY KEY,
                    banned_until INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_posts (
                    queue_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_bans (
                    user_id INTEGER PRIMARY KEY,
                    banned_at INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    banned_by INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS military_factories (
                    country TEXT PRIMARY KEY,
                    factories_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_mobilization (
                    country TEXT PRIMARY KEY,
                    mobilization_type TEXT NOT NULL DEFAULT 'conscription',
                    last_mobilization_date INTEGER NOT NULL DEFAULT 0,
                    mobilization_amount INTEGER NOT NULL DEFAULT 0,
                    weekly_limit INTEGER NOT NULL DEFAULT 0,
                    last_mobilization_week TEXT NOT NULL DEFAULT ''
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS mobilization_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country TEXT NOT NULL,
                    mobilization_type TEXT NOT NULL,
                    soldiers_gained INTEGER NOT NULL DEFAULT 0,
                    budget_change INTEGER NOT NULL DEFAULT 0,
                    life_change INTEGER NOT NULL DEFAULT 0,
                    risk_change INTEGER NOT NULL DEFAULT 0,
                    penalized INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS mobilization_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country TEXT NOT NULL,
                    mobilization_type TEXT NOT NULL,
                    requested_amount INTEGER NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL DEFAULT 0,
                    details TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS active_research (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country_id INTEGER NOT NULL DEFAULT 0,
                    country TEXT NOT NULL DEFAULT '',
                    tech_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    start_message_id INTEGER,
                    effects TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_tech (
                    country_id INTEGER NOT NULL,
                    tech_id TEXT NOT NULL,
                    unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (country_id, tech_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS country_units (
                    country_id INTEGER NOT NULL,
                    unit_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (country_id, unit_type)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS research_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country_id INTEGER NOT NULL,
                    tech_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            try:
                await db.execute("ALTER TABLE active_research ADD COLUMN country TEXT NOT NULL DEFAULT ''")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE active_research ADD COLUMN start_message_id INTEGER")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE active_research ADD COLUMN effects TEXT NOT NULL DEFAULT '{}'")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE country_stats ADD COLUMN citizens INTEGER NOT NULL DEFAULT 100")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE country_stats ADD COLUMN war_status TEXT NOT NULL DEFAULT 'peace'")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE country_stats ADD COLUMN risk_index INTEGER NOT NULL DEFAULT 0")
            except aiosqlite.OperationalError:
                pass
            await db.commit()

    async def save_pending_post(self, queue_key: str, payload_json: str, now_ts: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO pending_posts (queue_key, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(queue_key) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at",
                (queue_key, payload_json, now_ts, now_ts),
            )
            await db.commit()

    async def delete_pending_post(self, queue_key: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM pending_posts WHERE queue_key = ?", (queue_key,))
            await db.commit()

    async def list_pending_posts(self, limit: int = 500) -> list[tuple[str, str]]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT queue_key, payload_json FROM pending_posts ORDER BY created_at ASC LIMIT ?",
                (int(limit),),
            )
            rows = await cursor.fetchall()
        return [(str(r[0]), str(r[1])) for r in rows]

    async def is_duplicate(self, content_hash: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT 1 FROM processed_posts WHERE content_hash = ?", (content_hash,))
            row = await cursor.fetchone()
        return row is not None

    async def mark_processed(self, source_chat: str, source_country: str, message_id: int, content_hash: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO processed_posts (source_chat, source_country, message_id, content_hash) VALUES (?, ?, ?, ?)",
                (source_chat, source_country, message_id, content_hash),
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

    async def list_state_prefix(self, prefix: str) -> list[tuple[str, str]]:
        like = f"{prefix}%"
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute("SELECT key, value FROM app_state WHERE key LIKE ?", (like,))).fetchall()
        return [(str(r[0]), str(r[1])) for r in rows]

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

    async def has_any_approved_registration(self, user_id: int, reg_types: tuple[str, ...]) -> bool:
        if not reg_types:
            return False
        placeholders = ",".join(["?"] * len(reg_types))
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                f"SELECT 1 FROM registration_applications WHERE user_id = ? AND reg_type IN ({placeholders}) AND status = 'approved' LIMIT 1",
                (user_id, *reg_types),
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

    async def apply_country_stats_delta(
        self,
        country: str,
        budget_delta: int = 0,
        army_delta: int = 0,
        life_delta: int = 0,
        citizens_delta: int = 0,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_stats (country) VALUES (?)",
                (country,),
            )
            await db.execute(
                "UPDATE country_stats SET "
                "budget = MAX(0, budget + ?), "
                "army = MAX(0, army + ?), "
                "citizens = MAX(0, citizens + ?), "
                "life_level = MIN(100, MAX(0, life_level + ?)), "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE country = ?",
                (budget_delta, army_delta, citizens_delta, life_delta, country),
            )
            await db.commit()

    async def get_country_stats(self, country: str) -> tuple[int, int, int, int] | None:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute(
                "SELECT budget, army, citizens, life_level FROM country_stats WHERE country = ?",
                (country,),
            )).fetchone()
        if not row:
            return None
        return int(row[0]), int(row[1]), int(row[2]), int(row[3])

    async def get_country_war_and_risk(self, country: str) -> tuple[str, int]:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute(
                "SELECT war_status, risk_index FROM country_stats WHERE country = ?",
                (country,),
            )).fetchone()
        if not row:
            return "peace", 0
        return str(row[0] or "peace"), int(row[1] or 0)

    async def set_country_war_status(self, country: str, war_status: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR IGNORE INTO country_stats (country) VALUES (?)", (country,))
            await db.execute("UPDATE country_stats SET war_status = ?, updated_at = CURRENT_TIMESTAMP WHERE country = ?", (war_status, country))
            await db.commit()

    async def list_country_stats(self) -> list[tuple[str, int, int, int, int]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                "SELECT country, budget, army, citizens, life_level FROM country_stats ORDER BY budget DESC, army DESC"
            )).fetchall()
        return [(str(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4])) for r in rows]

    async def get_military_factories(self, country: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute(
                "SELECT factories_count FROM military_factories WHERE country = ?",
                (country,),
            )).fetchone()
        return int(row[0]) if row else 0

    async def set_military_factories(self, country: str, count: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO military_factories (country, factories_count) VALUES (?, ?) "
                "ON CONFLICT(country) DO UPDATE SET factories_count = excluded.factories_count",
                (country, max(0, int(count))),
            )
            await db.commit()

    async def add_military_factories(self, country: str, delta: int) -> int:
        delta = int(delta)
        if delta == 0:
            return await self.get_military_factories(country)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO military_factories (country, factories_count) VALUES (?, 0)",
                (country,),
            )
            await db.execute(
                "UPDATE military_factories SET factories_count = MAX(0, factories_count + ?) WHERE country = ?",
                (delta, country),
            )
            row = await (await db.execute(
                "SELECT factories_count FROM military_factories WHERE country = ?",
                (country,),
            )).fetchone()
            await db.commit()
        return int(row[0]) if row else 0

    async def seed_military_factories(self, mapping: dict[str, int]) -> int:
        inserted = 0
        async with aiosqlite.connect(self.path) as db:
            for country, count in mapping.items():
                desired = max(0, int(count))
                cursor = await db.execute(
                    "INSERT INTO military_factories (country, factories_count) VALUES (?, ?) "
                    "ON CONFLICT(country) DO UPDATE SET factories_count = MAX(factories_count, excluded.factories_count)",
                    (country, desired),
                )
                inserted += cursor.rowcount or 0
            await db.commit()
        return inserted

    async def get_country_mobilization(self, country: str) -> tuple[str, int, int, str]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_mobilization (country) VALUES (?)",
                (country,),
            )
            row = await (await db.execute(
                "SELECT mobilization_type, mobilization_amount, weekly_limit, last_mobilization_week "
                "FROM country_mobilization WHERE country = ?",
                (country,),
            )).fetchone()
            await db.commit()
        return str(row[0]), int(row[1]), int(row[2]), str(row[3] or "")

    async def update_country_mobilization(
        self,
        country: str,
        mobilization_type: str,
        mobilization_amount: int,
        weekly_limit: int,
        week_key: str,
        ts: int,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO country_mobilization (country, mobilization_type, mobilization_amount, weekly_limit, last_mobilization_week, last_mobilization_date) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(country) DO UPDATE SET "
                "mobilization_type = excluded.mobilization_type, "
                "mobilization_amount = excluded.mobilization_amount, "
                "weekly_limit = excluded.weekly_limit, "
                "last_mobilization_week = excluded.last_mobilization_week, "
                "last_mobilization_date = excluded.last_mobilization_date",
                (country, mobilization_type, mobilization_amount, weekly_limit, week_key, ts),
            )
            await db.commit()

    async def apply_country_multipliers(self, country: str, budget_pct: float = 0.0, life_pct: float = 0.0, risk_delta: int = 0) -> tuple[int, int, int]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR IGNORE INTO country_stats (country) VALUES (?)", (country,))
            row = await (await db.execute(
                "SELECT budget, life_level, risk_index FROM country_stats WHERE country = ?",
                (country,),
            )).fetchone()
            budget = int(row[0] or 0)
            life = int(row[1] or 0)
            risk = int(row[2] or 0)
            new_budget = max(0, int(round(budget * (1.0 + budget_pct))))
            new_life = min(100, max(0, int(round(life * (1.0 + life_pct)))))
            new_risk = min(100, max(0, risk + int(risk_delta)))
            await db.execute(
                "UPDATE country_stats SET budget = ?, life_level = ?, risk_index = ?, updated_at = CURRENT_TIMESTAMP WHERE country = ?",
                (new_budget, new_life, new_risk, country),
            )
            await db.commit()
        return new_budget - budget, new_life - life, new_risk - risk

    async def add_mobilization_log(
        self,
        country: str,
        mobilization_type: str,
        soldiers_gained: int,
        budget_change: int,
        life_change: int,
        risk_change: int,
        penalized: bool = False,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO mobilization_logs (country, mobilization_type, soldiers_gained, budget_change, life_change, risk_change, penalized) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (country, mobilization_type, soldiers_gained, budget_change, life_change, risk_change, 1 if penalized else 0),
            )
            await db.commit()

    async def aggregate_mobilization_logs(self, from_ts: int, to_ts: int) -> list[tuple[str, int, int, int, int]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                "SELECT country, SUM(soldiers_gained), SUM(budget_change), SUM(life_change), SUM(risk_change) "
                "FROM mobilization_logs "
                "WHERE strftime('%s', created_at) >= ? AND strftime('%s', created_at) < ? "
                "GROUP BY country ORDER BY country ASC",
                (int(from_ts), int(to_ts)),
            )).fetchall()
        return [
            (str(r[0]), int(r[1] or 0), int(r[2] or 0), int(r[3] or 0), int(r[4] or 0))
            for r in rows
        ]

    async def add_mobilization_attempt(
        self,
        country: str,
        mobilization_type: str,
        requested_amount: int,
        success: bool,
        details: str,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO mobilization_attempts (country, mobilization_type, requested_amount, success, details) VALUES (?, ?, ?, ?, ?)",
                (country, mobilization_type, int(requested_amount), 1 if success else 0, details[:500]),
            )
            await db.commit()

    async def seed_country_stats(self, mapping: dict[str, dict[str, int]]) -> int:
        inserted = 0
        async with aiosqlite.connect(self.path) as db:
            for country, payload in mapping.items():
                cursor = await db.execute(
                    """
                    INSERT OR IGNORE INTO country_stats (country, budget, army, citizens, life_level)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        country,
                        int(payload.get("budget", 100_000)),
                        int(payload.get("army", 100)),
                        int(payload.get("citizens", 100)),
                        int(payload.get("life_level", 50)),
                    ),
                )
                inserted += cursor.rowcount or 0
            await db.commit()
        return inserted

    async def get_country_population(self, country: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute("SELECT citizens FROM country_stats WHERE country = ?", (country,))).fetchone()
        return int(row[0]) if row else 100

    async def seed_country_extra_metrics(self, mapping: dict[str, dict[str, int]]) -> int:
        inserted = 0
        async with aiosqlite.connect(self.path) as db:
            for country, payload in mapping.items():
                terr = int(payload.get("territories_month", 0))
                alliances = int(payload.get("alliances", 0))
                treaties = int(payload.get("treaties", 0))
                stability = int(payload.get("stability_index", 50))
                quality = max(0, min(100, int(payload.get("quality_percent", 70))))
                cursor = await db.execute(
                    "INSERT OR IGNORE INTO country_territory_progress (country, territories_month) VALUES (?, ?)",
                    (country, terr),
                )
                inserted += cursor.rowcount or 0
                await db.execute(
                    "INSERT OR IGNORE INTO country_diplomacy_stats (country, alliances, treaties) VALUES (?, ?, ?)",
                    (country, alliances, treaties),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO country_stability_stats (country, stability_index) VALUES (?, ?)",
                    (country, stability),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO country_news_quality (country, autopassed, total) VALUES (?, ?, ?)",
                    (country, quality, 100),
                )
            await db.commit()
        return inserted

    async def increment_news_quality(self, country: str, autopassed_delta: int, total_delta: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_news_quality (country, autopassed, total) VALUES (?, 0, 0)",
                (country,),
            )
            await db.execute(
                "UPDATE country_news_quality SET autopassed = MAX(0, autopassed + ?), total = MAX(0, total + ?), updated_at = CURRENT_TIMESTAMP WHERE country = ?",
                (autopassed_delta, total_delta, country),
            )
            await db.commit()

    async def list_country_extra_metrics(self) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        async with aiosqlite.connect(self.path) as db:
            terr_rows = await (await db.execute("SELECT country, territories_month FROM country_territory_progress")).fetchall()
            dip_rows = await (await db.execute("SELECT country, alliances, treaties FROM country_diplomacy_stats")).fetchall()
            stab_rows = await (await db.execute("SELECT country, stability_index FROM country_stability_stats")).fetchall()
            q_rows = await (await db.execute("SELECT country, autopassed, total FROM country_news_quality")).fetchall()
        for c, v in terr_rows:
            result.setdefault(str(c), {})["territories_month"] = int(v)
        for c, a, t in dip_rows:
            data = result.setdefault(str(c), {})
            data["alliances"] = int(a)
            data["treaties"] = int(t)
        for c, s in stab_rows:
            result.setdefault(str(c), {})["stability_index"] = int(s)
        for c, a, t in q_rows:
            data = result.setdefault(str(c), {})
            data["quality_percent"] = int((int(a) / int(t)) * 100) if int(t) > 0 else 0
        return result

    async def monthly_country_post_counts(self, month_key: str) -> list[tuple[str, int]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                """
                SELECT source_country, COUNT(*) as cnt
                FROM processed_posts
                WHERE strftime('%Y-%m', created_at) = ?
                GROUP BY source_country
                ORDER BY cnt DESC
                """,
                (month_key,),
            )).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    async def add_monthly_award(self, month_key: str, award_name: str, country: str, value: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO monthly_awards (month_key, award_name, country, value) VALUES (?, ?, ?, ?)",
                (month_key, award_name, country, value),
            )
            await db.commit()

    async def add_or_update_relation(self, country_a: str, country_b: str, relation_type: str) -> None:
        left, right = sorted([country_a, country_b])
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO diplomatic_relations (country_a, country_b, relation_type) VALUES (?, ?, ?)",
                (left, right, relation_type),
            )
            await db.commit()

    async def adjust_diplomacy_counter(self, country: str, alliances_delta: int = 0, treaties_delta: int = 0) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_diplomacy_stats (country, alliances, treaties) VALUES (?, 0, 0)",
                (country,),
            )
            await db.execute(
                "UPDATE country_diplomacy_stats SET alliances = MAX(0, alliances + ?), treaties = MAX(0, treaties + ?), updated_at = CURRENT_TIMESTAMP WHERE country = ?",
                (alliances_delta, treaties_delta, country),
            )
            await db.commit()

    async def start_technology_project(self, country: str, tech_name: str, started_at: int, complete_at: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO technology_projects (country, tech_name, started_at, complete_at, status) VALUES (?, ?, ?, ?, 'in_progress')",
                (country, tech_name, started_at, complete_at),
            )
            await db.commit()

    async def due_technology_projects(self, now_ts: int) -> list[tuple[int, str, str]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                "SELECT id, country, tech_name FROM technology_projects WHERE status = 'in_progress' AND complete_at <= ?",
                (now_ts,),
            )).fetchall()
            await db.execute(
                "UPDATE technology_projects SET status = 'done' WHERE status = 'in_progress' AND complete_at <= ?",
                (now_ts,),
            )
            await db.commit()
        return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]

    async def log_crisis(self, country: str, crisis_type: str, effect_json: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO crisis_history (country, crisis_type, effect_json) VALUES (?, ?, ?)",
                (country, crisis_type, effect_json),
            )
            await db.commit()

    async def upsert_resources(self, country: str, oil: int, metal: int, grain: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO economic_resources (country, oil, metal, grain, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(country) DO UPDATE SET oil = excluded.oil, metal = excluded.metal, grain = excluded.grain, updated_at = CURRENT_TIMESTAMP
                """,
                (country, oil, metal, grain),
            )
            await db.commit()

    async def add_resources_delta(self, country: str, oil_delta: int = 0, metal_delta: int = 0, grain_delta: int = 0) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO economic_resources (country, oil, metal, grain) VALUES (?, 0, 0, 0)",
                (country,),
            )
            await db.execute(
                "UPDATE economic_resources SET "
                "oil = MAX(0, oil + ?), "
                "metal = MAX(0, metal + ?), "
                "grain = MAX(0, grain + ?), "
                "updated_at = CURRENT_TIMESTAMP WHERE country = ?",
                (int(oil_delta), int(metal_delta), int(grain_delta), country),
            )
            await db.commit()

    async def seed_economic_resources(self, mapping: dict[str, dict[str, int]]) -> int:
        inserted = 0
        async with aiosqlite.connect(self.path) as db:
            for country, payload in mapping.items():
                cursor = await db.execute(
                    "INSERT INTO economic_resources (country, oil, metal, grain) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(country) DO UPDATE SET "
                    "oil = MAX(oil, excluded.oil), "
                    "metal = MAX(metal, excluded.metal), "
                    "grain = MAX(grain, excluded.grain), "
                    "updated_at = CURRENT_TIMESTAMP",
                    (
                        country,
                        max(0, int(payload.get("oil", 0))),
                        max(0, int(payload.get("metal", 0))),
                        max(0, int(payload.get("grain", 0))),
                    ),
                )
                inserted += cursor.rowcount or 0
            await db.commit()
        return inserted

    async def get_country_resources(self, country: str) -> tuple[int, int, int]:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute(
                "SELECT oil, metal, grain FROM economic_resources WHERE country = ?",
                (country,),
            )).fetchone()
        if not row:
            return 0, 0, 0
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    async def set_daily_missions(self, day_key: str, missions: list[tuple[str, int, int]]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM daily_missions WHERE day_key = ?", (day_key,))
            for text, reward_budget, reward_life in missions:
                await db.execute(
                    "INSERT INTO daily_missions (day_key, mission_text, reward_budget, reward_life) VALUES (?, ?, ?, ?)",
                    (day_key, text, reward_budget, reward_life),
                )
            await db.commit()

    async def add_country_warning(self, country: str, reason: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_warnings (country, warnings, last_reason) VALUES (?, 0, '')",
                (country,),
            )
            await db.execute(
                "UPDATE country_warnings SET warnings = warnings + 1, last_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE country = ?",
                (reason[:300], country),
            )
            row = await (await db.execute("SELECT warnings FROM country_warnings WHERE country = ?", (country,))).fetchone()
            await db.commit()
        return int(row[0]) if row else 0

    async def set_antiflood_ban(self, user_id: int, banned_until: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO antiflood_bans (user_id, banned_until) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET banned_until = excluded.banned_until",
                (user_id, banned_until),
            )
            await db.commit()

    async def get_antiflood_ban(self, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute("SELECT banned_until FROM antiflood_bans WHERE user_id = ?", (user_id,))).fetchone()
        return int(row[0]) if row else 0

    async def clear_antiflood_ban(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM antiflood_bans WHERE user_id = ?", (user_id,))
            await db.commit()

    async def ban_user(self, user_id: int, banned_by: int, reason: str = "") -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO user_bans (user_id, banned_at, reason, banned_by) VALUES (?, strftime('%s','now'), ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET banned_at = excluded.banned_at, reason = excluded.reason, banned_by = excluded.banned_by",
                (user_id, reason[:300], banned_by),
            )
            await db.commit()

    async def unban_user(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM user_bans WHERE user_id = ?", (user_id,))
            await db.commit()

    async def is_user_banned(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute("SELECT 1 FROM user_bans WHERE user_id = ? LIMIT 1", (user_id,))).fetchone()
        return row is not None

    async def list_user_bans(self, limit: int = 30) -> list[tuple[int, int, str, int]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                "SELECT user_id, banned_at, reason, banned_by FROM user_bans ORDER BY banned_at DESC LIMIT ?",
                (limit,),
            )).fetchall()
        return [(int(r[0]), int(r[1]), str(r[2]), int(r[3])) for r in rows]

    async def due_active_research(self, now_iso: str) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                """
                SELECT id, country_id, country, tech_id, name, category, duration_days, start_date, end_date, start_message_id, effects
                FROM active_research
                WHERE status = 'active' AND end_date <= ?
                ORDER BY end_date ASC
                """,
                (now_iso,),
            )).fetchall()
        return [
            {
                "id": int(r[0]),
                "country_id": int(r[1]),
                "country": str(r[2] or ""),
                "tech_id": str(r[3]),
                "name": str(r[4]),
                "category": str(r[5]),
                "duration_days": int(r[6]),
                "start_date": str(r[7]),
                "end_date": str(r[8]),
                "start_message_id": int(r[9]) if r[9] is not None else None,
                "effects": str(r[10] or "{}"),
            }
            for r in rows
        ]

    async def complete_active_research(self, research_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE active_research SET status = 'completed' WHERE id = ?", (research_id,))
            await db.commit()

    async def cancel_active_research(self, research_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE active_research SET status = 'cancelled' WHERE id = ? AND status = 'active'",
                (research_id,),
            )
            await db.commit()
            return int(cur.rowcount or 0) > 0

    async def add_country_tech(self, country_id: int, tech_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO country_tech (country_id, tech_id) VALUES (?, ?)",
                (country_id, tech_id),
            )
            await db.commit()

    async def add_country_unit(self, country_id: int, unit_type: str, qty: int = 1) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO country_units (country_id, unit_type, quantity) VALUES (?, ?, ?)
                ON CONFLICT(country_id, unit_type) DO UPDATE SET quantity = quantity + excluded.quantity
                """,
                (country_id, unit_type, max(1, int(qty))),
            )
            await db.commit()

    async def add_research_log(self, country_id: int, tech_id: str, action: str, details_json: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO research_logs (country_id, tech_id, action, details_json) VALUES (?, ?, ?, ?)",
                (country_id, tech_id, action, details_json),
            )
            await db.commit()

    async def list_research_logs(self, country_id: int, limit: int = 50) -> list[tuple[int, str, str, str]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                "SELECT id, tech_id, action, details_json FROM research_logs WHERE country_id = ? ORDER BY id DESC LIMIT ?",
                (country_id, limit),
            )).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]

    async def country_name_by_id(self, country_id: int) -> str:
        async with aiosqlite.connect(self.path) as db:
            try:
                row = await (await db.execute(
                    "SELECT name FROM countries WHERE id = ?",
                    (country_id,),
                )).fetchone()
                if row:
                    return str(row[0])
            except aiosqlite.OperationalError:
                pass
            rows = await (await db.execute(
                "SELECT country FROM country_stats ORDER BY country"
            )).fetchall()
        idx = max(0, country_id - 1)
        if idx < len(rows):
            return str(rows[idx][0])
        return f"Country#{country_id}"
