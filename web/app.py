from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

DB_PATH = os.environ.get("DB_PATH", "app/storage/bot_data.sqlite3")
API_TOKEN = os.environ.get("WEB_API_TOKEN", "").strip()
BOT_WEBHOOK_URL = os.environ.get("BOT_WEBHOOK_URL", "http://127.0.0.1:8090/webhook/resource/claim").strip()
BOT_WEBHOOK_SECRET = os.environ.get("BOT_WEBHOOK_SECRET", "dev-secret").strip()

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "web" / "data"
RESOURCES_PATH = DATA_DIR / "resources.json"
TERRITORIES_PATH = DATA_DIR / "territories.json"

TECH_TREE: dict[str, dict[str, Any]] = {
    "drone_recon": {"name": "🛸 Разведывательный беспилотник", "category": "drones", "description": "Маленький дрон для разведки местности", "duration": 1, "cost": 3000, "requirements": {}, "effects": {"unlock_unit": "recon_drone"}},
    "drone_strike": {"name": "💥 Ударный беспилотник", "category": "drones", "description": "Боевой дрон с возможностью точечных ударов", "duration": 2, "cost": 8000, "requirements": {"tech": ["drone_recon"]}, "effects": {"unlock_unit": "strike_drone"}},
    "rocket_short": {"name": "🎯 Тактическая ракета (малая дальность)", "category": "rockets", "description": "Ракета для ударов по прифронтовым целям", "duration": 2, "cost": 10000, "requirements": {}, "effects": {"unlock_unit": "short_rocket"}},
}


def _db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _authorized() -> bool:
    if not API_TOKEN:
        return True
    return request.headers.get("X-API-Key", "").strip() == API_TOKEN


def _load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _forward_claim_to_bot(payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        BOT_WEBHOOK_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Secret": BOT_WEBHOOK_SECRET,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw or "{}")
        except Exception:
            data = {"error": raw or "webhook error"}
        return int(exc.code), data
    except Exception as exc:
        return 502, {"error": f"webhook unreachable: {exc}"}


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

    @app.get("/api/resources")
    def api_resources():
        return jsonify(_load_json(RESOURCES_PATH, {"points": []}))

    @app.get("/api/territories")
    def api_territories():
        return jsonify(_load_json(TERRITORIES_PATH, {"regions": []}))

    @app.post("/api/admin/resource")
    def api_admin_resource():
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action") or "update")
        point_id = str(payload.get("id") or "").strip()
        resources = _load_json(RESOURCES_PATH, {"points": []})
        points = resources.get("points") if isinstance(resources.get("points"), list) else []

        if action == "add":
            points.append(payload)
        else:
            target = next((x for x in points if str(x.get("id")) == point_id), None)
            if target is None:
                return jsonify({"error": "point not found"}), 404
            target.update(payload)

        resources["points"] = points
        _save_json(RESOURCES_PATH, resources)
        return jsonify({"success": True})

    @app.post("/api/admin/territory")
    def api_admin_territory():
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        region_id = str(payload.get("id") or "").strip()
        territories = _load_json(TERRITORIES_PATH, {"regions": []})
        regions = territories.get("regions") if isinstance(territories.get("regions"), list) else []
        target = next((x for x in regions if str(x.get("id")) == region_id), None)
        if target is None:
            return jsonify({"error": "region not found"}), 404
        target.update(payload)
        territories["regions"] = regions
        _save_json(TERRITORIES_PATH, territories)
        return jsonify({"success": True})

    @app.post("/api/resource/claim")
    def api_resource_claim():
        payload = request.get_json(silent=True) or {}
        point_id = str(payload.get("point_id") or "").strip()
        country = str(payload.get("country") or "").strip()
        user_id = payload.get("user_id")
        if not point_id or not country or user_id is None:
            return jsonify({"error": "point_id, country, user_id are required"}), 400

        status, bot_response = _forward_claim_to_bot(payload)
        if status >= 400:
            return jsonify({"error": "bot webhook failed", "details": bot_response}), status
        return jsonify({"success": True, "result": bot_response})

    @app.get("/api/tech_tree")
    def api_tech_tree():
        country = str(request.args.get("country") or "").strip()
        if not country:
            return jsonify(TECH_TREE)
        with _db(app.config["DB_PATH"]) as conn:
            unlocked = {r[0] for r in conn.execute("SELECT tech_id FROM country_tech WHERE country = ?", (country,)).fetchall()}
        out: dict[str, dict[str, Any]] = {}
        for tech_id, tech in TECH_TREE.items():
            req = tech.get("requirements", {})
            req_tech = list(req.get("tech", []))
            missing = [t for t in req_tech if t not in unlocked]
            out[tech_id] = {**tech, "status": {"unlocked": tech_id in unlocked, "can_start": not missing, "missing_tech": missing}}
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
