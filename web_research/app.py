from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from web_research.config import settings

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

TECH_TREE: dict[str, dict[str, Any]] = {
    "drone_recon": {"name": "🛸 Разведывательный беспилотник", "category": "drones", "description": "Маленький дрон для разведки местности", "duration": 1, "cost": 3000, "requirements": []},
    "drone_strike": {"name": "💥 Ударный беспилотник", "category": "drones", "description": "Боевой дрон с точечными ударами", "duration": 2, "cost": 8000, "requirements": ["drone_recon"]},
    "rocket_short": {"name": "🎯 Тактическая ракета", "category": "rockets", "description": "Ракета для прифронтовых целей", "duration": 2, "cost": 10000, "requirements": []},
    "rocket_medium": {"name": "💀 Баллистическая ракета", "category": "rockets", "description": "Стратегическая ракета средней дальности", "duration": 4, "cost": 25000, "requirements": ["rocket_short"], "factories": 2},
    "air_recon": {"name": "✈️ Лёгкий разведывательный самолёт", "category": "aviation", "description": "Разведка и патрулирование", "duration": 2, "cost": 6000, "requirements": []},
    "air_drone_carrier": {"name": "🚀 Носитель беспилотников", "category": "aviation", "description": "Самолёт для управления БПЛА", "duration": 3, "cost": 15000, "requirements": ["air_recon", "drone_strike"]},
    "boat_patrol": {"name": "🚤 Патрульный катер", "category": "navy", "description": "Катер для речного и прибрежного патруля", "duration": 2, "cost": 5000, "requirements": []},
    "boat_missile": {"name": "⚡ Ракетный катер", "category": "navy", "description": "Катер с ракетным вооружением", "duration": 3, "cost": 12000, "requirements": ["boat_patrol", "rocket_short"]},
    "landing_craft": {"name": "⛴️ Десантный катер", "category": "navy", "description": "Высадка лёгкой техники", "duration": 2, "cost": 8000, "requirements": ["boat_patrol"]},
    "armor_light": {"name": "🛡️ Лёгкий бронеавтомобиль", "category": "armor", "description": "Бронемашина для разведки", "duration": 2, "cost": 7000, "requirements": []},
    "tech_radar": {"name": "📡 Современная радиолокация", "category": "technology", "description": "Улучшенная система обнаружения целей", "duration": 3, "cost": 12000, "requirements": ["drone_recon"]},
    "tech_cyber": {"name": "🛡️ Киберзащита", "category": "technology", "description": "Защита от информационных атак", "duration": 3, "cost": 10000, "requirements": []},
    "tech_factory": {"name": "🏭 Военное производство", "category": "technology", "description": "Ускорение развития промышленности", "duration": 4, "cost": 20000, "requirements": [], "factories": 1},
}

CATEGORY_NAMES = {
    "drones": "🛸 Дроны",
    "rockets": "💥 Ракеты",
    "aviation": "✈️ Авиация",
    "navy": "🚤 Флот",
    "armor": "🛡️ Бронетехника",
    "technology": "📡 Технологии",
}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def authorize() -> bool:
    if not settings.api_key:
        return True
    return request.headers.get("X-API-Key", "") == settings.api_key


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)).fetchone()
    return bool(row)


def ensure_schema() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_research (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country_id INTEGER NOT NULL,
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS country_tech (
                country_id INTEGER NOT NULL,
                tech_id TEXT NOT NULL,
                unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (country_id, tech_id)
            )
            """
        )
        conn.execute(
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
            conn.execute("ALTER TABLE active_research ADD COLUMN start_message_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE active_research ADD COLUMN effects TEXT NOT NULL DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def fetch_countries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if table_exists(conn, "countries"):
        rows = conn.execute(
            "SELECT id, name, army, budget, citizens, life_quality, risk_index FROM countries ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    rows = conn.execute(
        "SELECT rowid as id, country as name, army, budget, citizens, life_level as life_quality, risk_index FROM country_stats ORDER BY country"
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_country(conn: sqlite3.Connection, country_id: int) -> dict[str, Any] | None:
    if table_exists(conn, "countries"):
        row = conn.execute(
            "SELECT id, name, army, budget, citizens, life_quality, risk_index FROM countries WHERE id = ?",
            (country_id,),
        ).fetchone()
        return dict(row) if row else None

    rows = fetch_countries(conn)
    for row in rows:
        if int(row["id"]) == int(country_id):
            return row
    return None


def deduct_budget(conn: sqlite3.Connection, country_id: int, new_budget: int) -> None:
    if table_exists(conn, "countries"):
        conn.execute("UPDATE countries SET budget = ? WHERE id = ?", (new_budget, country_id))
        return

    name_row = resolve_country(conn, country_id)
    if not name_row:
        return
    conn.execute("UPDATE country_stats SET budget = ? WHERE country = ?", (new_budget, name_row["name"]))


@app.get("/")
def index():
    return render_template("index.html", categories=CATEGORY_NAMES)


@app.get("/api/countries")
def api_countries():
    with get_db() as conn:
        return jsonify(fetch_countries(conn))


@app.get("/api/country_tech/<int:country_id>")
def api_country_tech(country_id: int):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT tech_id, unlocked_at FROM country_tech WHERE country_id = ? ORDER BY unlocked_at DESC",
            (country_id,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/research/history/<int:country_id>")
def api_research_history(country_id: int):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, tech_id, action, details_json, created_at FROM research_logs WHERE country_id = ? ORDER BY id DESC LIMIT 100",
            (country_id,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/tech_tree")
def api_tech_tree():
    country_id = request.args.get("country_id", type=int)
    if country_id is None:
        return jsonify(TECH_TREE)

    with get_db() as conn:
        country = resolve_country(conn, country_id)
        country_budget = int(country["budget"]) if country else 0
        factories = 0
        try:
            if table_exists(conn, "military_factories") and country:
                row_f = conn.execute(
                    "SELECT factories_count FROM military_factories WHERE country = ?",
                    (country["name"],),
                ).fetchone()
                factories = int(row_f[0]) if row_f else 0
        except Exception:
            factories = 0
        opened = {
            row[0]
            for row in conn.execute(
                "SELECT tech_id FROM country_tech WHERE country_id = ?",
                (country_id,),
            ).fetchall()
        }

    enriched: dict[str, Any] = {}
    for tech_id, tech in TECH_TREE.items():
        req = list(tech.get("requirements", []))
        missing = [item for item in req if item not in opened]
        has_budget = country_budget >= int(tech.get("cost", 0))
        needed_factories = int(tech.get("factories", 0) or 0)
        has_factories = factories >= needed_factories
        enriched[tech_id] = {
            **tech,
            "status": {
                "opened": tech_id in opened,
                "available": (not missing) and has_budget and has_factories,
                "missing_requirements": missing,
                "has_budget": has_budget,
                "has_factories": has_factories,
                "needed_factories": needed_factories,
            },
        }
    return jsonify(enriched)


@app.get("/api/research/active")
def api_research_active():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT ar.id, ar.country_id, ar.tech_id, ar.name, ar.category, ar.start_date, ar.end_date,
                   c.name as country_name
            FROM active_research ar
            LEFT JOIN countries c ON c.id = ar.country_id
            WHERE ar.status = 'active'
            ORDER BY ar.end_date ASC
            """
        ).fetchall() if table_exists(conn, "countries") else conn.execute(
            """
            SELECT id, country_id, tech_id, name, category, start_date, end_date, '' as country_name
            FROM active_research
            WHERE status = 'active'
            ORDER BY end_date ASC
            """
        ).fetchall()

    items: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for row in rows:
        data = dict(row)
        start = datetime.fromisoformat(data["start_date"])
        end = datetime.fromisoformat(data["end_date"])
        total = max(1.0, (end - start).total_seconds())
        done = min(total, max(0.0, (now - start).total_seconds()))
        data["progress_percent"] = round((done / total) * 100, 2)
        items.append(data)
    return jsonify(items)


@app.post("/api/research/start")
def api_research_start():
    if not authorize():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    country_id = int(data.get("country_id", 0) or 0)
    tech_id = str(data.get("tech_id", "")).strip()
    if country_id <= 0 or not tech_id:
        return jsonify({"error": "country_id and tech_id are required"}), 400

    tech = TECH_TREE.get(tech_id)
    if tech is None:
        return jsonify({"error": "Technology not found"}), 404

    with get_db() as conn:
        country = resolve_country(conn, country_id)
        if country is None:
            return jsonify({"error": "Country not found"}), 404

        already = conn.execute(
            "SELECT 1 FROM country_tech WHERE country_id = ? AND tech_id = ?",
            (country_id, tech_id),
        ).fetchone()
        if already:
            return jsonify({"error": "Already researched"}), 400

        req = list(tech.get("requirements", []))
        if req:
            have = {
                row[0]
                for row in conn.execute(
                    "SELECT tech_id FROM country_tech WHERE country_id = ?",
                    (country_id,),
                ).fetchall()
            }
            missing = [item for item in req if item not in have]
            if missing:
                return jsonify({"error": "Requirements not met", "missing": missing}), 400

        budget = int(country["budget"])
        cost = int(tech["cost"])
        if budget < cost:
            return jsonify({"error": "Not enough budget"}), 400

        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=int(tech["duration"]))

        deduct_budget(conn, country_id, budget - cost)
        conn.execute(
            """
            INSERT INTO active_research (country_id, tech_id, name, category, duration_days, start_date, end_date, effects, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                country_id,
                tech_id,
                tech["name"],
                tech["category"],
                int(tech["duration"]),
                start_date.isoformat(),
                end_date.isoformat(),
                json.dumps({"from_web": True}, ensure_ascii=False),
            ),
        )
        conn.execute(
            "INSERT INTO research_logs (country_id, tech_id, action, details_json) VALUES (?, ?, 'started', ?)",
            (country_id, tech_id, json.dumps({"cost": cost}, ensure_ascii=False)),
        )
        conn.commit()

    return jsonify({"ok": True, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()})


@app.post("/api/admin/research/<int:research_id>/cancel")
def api_cancel_research(research_id: int):
    if not authorize():
        return jsonify({"error": "Unauthorized"}), 401
    with get_db() as conn:
        row = conn.execute(
            "SELECT country_id, tech_id FROM active_research WHERE id = ? AND status = 'active'",
            (research_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "Active research not found"}), 404
        conn.execute("UPDATE active_research SET status = 'cancelled' WHERE id = ?", (research_id,))
        conn.execute(
            "INSERT INTO research_logs (country_id, tech_id, action, details_json) VALUES (?, ?, 'cancelled', ?)",
            (int(row["country_id"]), str(row["tech_id"]), json.dumps({"by": "admin"}, ensure_ascii=False)),
        )
        conn.commit()
    return jsonify({"ok": True})


ensure_schema()

if __name__ == "__main__":
    app.run(host=settings.host, port=settings.port, debug=False)
