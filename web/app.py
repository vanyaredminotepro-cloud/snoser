from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Flask, jsonify, render_template, request

DB_PATH = os.environ.get("DB_PATH", "app/storage/bot_data.sqlite3")
API_TOKEN = os.environ.get("WEB_API_TOKEN", "").strip()

TECH_TREE: dict[str, dict[str, Any]] = {
    "drone_recon": {"name": "🛸 Разведывательный беспилотник", "category": "drones", "description": "Маленький дрон для разведки местности", "duration": 1, "cost": 3000, "requirements": {}, "effects": {"unlock_unit": "recon_drone"}},
    "drone_strike": {"name": "💥 Ударный беспилотник", "category": "drones", "description": "Боевой дрон с возможностью точечных ударов", "duration": 2, "cost": 8000, "requirements": {"tech": ["drone_recon"]}, "effects": {"unlock_unit": "strike_drone"}},
    "rocket_short": {"name": "🎯 Тактическая ракета (малая дальность)", "category": "rockets", "description": "Ракета для ударов по прифронтовым целям", "duration": 2, "cost": 10000, "requirements": {}, "effects": {"unlock_unit": "short_rocket"}},
    "rocket_medium": {"name": "💀 Баллистическая ракета (средняя дальность)", "category": "rockets", "description": "Стратегическое оружие для ударов в глубине территории", "duration": 4, "cost": 25000, "requirements": {"tech": ["rocket_short"], "factories": 2}, "effects": {"unlock_unit": "medium_rocket"}},
    "air_recon": {"name": "✈️ Лёгкий разведывательный самолёт", "category": "aviation", "description": "Винтовой самолёт для разведки", "duration": 2, "cost": 6000, "requirements": {}, "effects": {"unlock_unit": "recon_plane"}},
    "air_drone_carrier": {"name": "🚀 Носитель беспилотников", "category": "aviation", "description": "Самолёт для запуска и управления дронами", "duration": 3, "cost": 15000, "requirements": {"tech": ["air_recon", "drone_strike"]}, "effects": {"unlock_unit": "drone_carrier"}},
    "boat_patrol": {"name": "🚤 Патрульный катер", "category": "navy", "description": "Быстроходный катер для речных и прибрежных операций", "duration": 2, "cost": 5000, "requirements": {}, "effects": {"unlock_unit": "patrol_boat"}},
    "boat_missile": {"name": "⚡ Ракетный катер", "category": "navy", "description": "Катер с пусковыми установками для тактических ракет", "duration": 3, "cost": 12000, "requirements": {"tech": ["boat_patrol", "rocket_short"]}, "effects": {"unlock_unit": "missile_boat"}},
    "landing_craft": {"name": "⛴️ Десантный катер", "category": "navy", "description": "Катер для высадки лёгкой техники", "duration": 2, "cost": 8000, "requirements": {"tech": ["boat_patrol"]}, "effects": {"unlock_unit": "landing_craft"}},
    "armor_light": {"name": "🛡️ Лёгкий бронеавтомобиль", "category": "armor", "description": "Бронированная машина для разведки и патрулирования", "duration": 2, "cost": 7000, "requirements": {}, "effects": {"unlock_unit": "light_armor"}},
    "tech_radar": {"name": "📡 Современная радиолокация", "category": "technology", "description": "Улучшенная система обнаружения целей", "duration": 3, "cost": 12000, "requirements": {"tech": ["drone_recon"]}, "effects": {"army_bonus": 10}},
    "tech_cyber": {"name": "🛡️ Киберзащита", "category": "technology", "description": "Защита от информационных атак и шпионажа", "duration": 3, "cost": 10000, "requirements": {}, "effects": {"risk_reduction": 5}},
    "tech_factory": {"name": "🏭 Военное производство", "category": "technology", "description": "Ускоренное строительство военных заводов", "duration": 4, "cost": 20000, "requirements": {"factories": 1}, "effects": {"factory_speed": 25}},
}


def _db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _authorized() -> bool:
    if not API_TOKEN:
        return True
    return request.headers.get("X-API-Key", "").strip() == API_TOKEN


def ensure_schema(path: str) -> None:
    with _db(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS active_research (id INTEGER PRIMARY KEY AUTOINCREMENT, country TEXT NOT NULL, tech_id TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, duration_days INTEGER NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, start_message_id INTEGER, effects TEXT, status TEXT NOT NULL DEFAULT 'active')")
        conn.execute("CREATE TABLE IF NOT EXISTS country_tech (country TEXT NOT NULL, tech_id TEXT NOT NULL, unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (country, tech_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS country_units (country TEXT NOT NULL, unit_type TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (country, unit_type))")
        conn.commit()


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["DB_PATH"] = db_path or DB_PATH
    ensure_schema(app.config["DB_PATH"])

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/countries")
    def api_countries():
        with _db(app.config["DB_PATH"]) as conn:
            rows = conn.execute("SELECT country, army, budget, citizens, life_level, risk_index, war_status FROM country_stats ORDER BY country").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/tech_tree")
    def api_tech_tree():
        country = str(request.args.get("country") or "").strip()
        if not country:
            return jsonify(TECH_TREE)
        with _db(app.config["DB_PATH"]) as conn:
            unlocked = {r[0] for r in conn.execute("SELECT tech_id FROM country_tech WHERE country = ?", (country,)).fetchall()}
            row = conn.execute("SELECT factories_count FROM military_factories WHERE country = ?", (country,)).fetchone()
        factories = int(row[0]) if row else 0
        out: dict[str, dict[str, Any]] = {}
        for tech_id, tech in TECH_TREE.items():
            req = tech.get("requirements", {})
            req_tech = list(req.get("tech", []))
            req_fac = int(req.get("factories", 0))
            missing = [t for t in req_tech if t not in unlocked]
            out[tech_id] = {**tech, "status": {"unlocked": tech_id in unlocked, "can_start": not missing and factories >= req_fac, "missing_tech": missing, "missing_factories": max(0, req_fac - factories)}}
        return jsonify(out)

    @app.get("/api/research/active")
    def api_research_active():
        with _db(app.config["DB_PATH"]) as conn:
            rows = conn.execute("SELECT id, country, tech_id, name, category, duration_days, start_date, end_date FROM active_research WHERE status = 'active' ORDER BY end_date ASC").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/research/start")
    def api_research_start():
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        country = str(payload.get("country") or "").strip()
        tech_id = str(payload.get("tech_id") or "").strip()
        if not country or not tech_id:
            return jsonify({"error": "country and tech_id are required"}), 400
        tech = TECH_TREE.get(tech_id)
        if not tech:
            return jsonify({"error": "Technology not found"}), 404

        with _db(app.config["DB_PATH"]) as conn:
            row = conn.execute("SELECT budget FROM country_stats WHERE country = ?", (country,)).fetchone()
            if row is None:
                return jsonify({"error": "Country not found"}), 404
            budget = int(row[0])
            if budget < int(tech["cost"]):
                return jsonify({"error": "Not enough budget"}), 400
            existing = conn.execute("SELECT 1 FROM active_research WHERE country = ? AND tech_id = ? AND status = 'active'", (country, tech_id)).fetchone()
            if existing:
                return jsonify({"error": "Research already active"}), 400

            start_dt = datetime.now(timezone.utc)
            end_dt = start_dt + timedelta(days=int(tech["duration"]))
            conn.execute("UPDATE country_stats SET budget = ?, updated_at = CURRENT_TIMESTAMP WHERE country = ?", (budget - int(tech["cost"]), country))
            conn.execute(
                "INSERT INTO active_research (country, tech_id, name, category, duration_days, start_date, end_date, effects, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
                (country, tech_id, str(tech["name"]), str(tech["category"]), int(tech["duration"]), start_dt.isoformat(), end_dt.isoformat(), json.dumps(tech.get("effects", {}), ensure_ascii=False)),
            )
            conn.commit()
        return jsonify({"success": True, "end_date": end_dt.isoformat()})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "5000")), debug=False)
