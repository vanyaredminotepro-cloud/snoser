from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request

DB_PATH = os.environ.get("DB_PATH", "app/storage/bot_data.sqlite3")
API_TOKEN = os.environ.get("WEB_API_TOKEN", "").strip()
BOT_WEBHOOK_URL = os.environ.get("BOT_WEBHOOK_URL", "").strip() or "http://127.0.0.1:8080/webhook/resource/claim"
BOT_WEBHOOK_SECRET = os.environ.get("BOT_WEBHOOK_SECRET", "").strip()
TELEGRAM_ADMIN_ID = os.environ.get("WEB_ADMIN_TELEGRAM_ID", "").strip()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RESOURCES_PATH = DATA_DIR / "resources.json"
TERRITORIES_PATH = DATA_DIR / "territories.json"

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


RESOURCE_ICONS: dict[str, str] = {
    "дерево": "🪵", "камень": "🪨", "уголь": "⚫", "железо": "⛓️", "медь": "🟠", "алюминий": "⚪", "золото": "🥇", "серебро": "🥈", "нефть": "🛢️", "газ": "💨", "вода": "💧", "еда": "🍖", "медикаменты": "💊", "химикаты": "🧪", "электроника": "🔌", "ткань": "🧵", "стройматериалы": "🧱",
    "корова": "🐄", "свинья": "🐖", "курица": "🐔", "рыба": "🐟", "олень": "🦌", "заяц": "🐇", "обезьяна": "🐒",
}


def _db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _authorized() -> bool:
    if not API_TOKEN:
        return True
    return request.headers.get("X-API-Key", "").strip() == API_TOKEN


def _admin_authorized() -> bool:
    if not TELEGRAM_ADMIN_ID:
        return _authorized()
    return request.headers.get("X-Telegram-ID", "").strip() == TELEGRAM_ADMIN_ID


def _forward_resource_claim(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if BOT_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = BOT_WEBHOOK_SECRET
    req = Request(BOT_WEBHOOK_URL, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="ignore") or "{}"
            parsed = json.loads(raw)
            return (parsed if isinstance(parsed, dict) else {"success": True}), int(resp.status or 200)
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="ignore")
        return {"error": f"Webhook returned HTTP {exc.code}", "details": text[:300]}, int(exc.code)
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": f"Webhook is unavailable: {exc}"}, 502


def _load_json(path: Path, default_payload: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return default_payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else default_payload
    except Exception:
        return default_payload


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_resources() -> dict[str, Any]:
    return {
        "points": [
            {"id": "stone_1", "name": "Каменоломня-1", "x": 380, "y": 430, "type": "камень", "icon": "🪨", "amount": 500, "owner": "Обоссляндия", "can_mine": True, "region_id": "region_1"},
            {"id": "cow_1", "name": "Пастбище-1", "x": 690, "y": 730, "type": "корова", "icon": "🐄", "amount": 60, "owner": "Вилония", "can_mine": True, "region_id": "region_2"},
        ]
    }


def _default_territories() -> dict[str, Any]:
    return {
        "regions": [
            {"id": "region_1", "name": "Северный лес", "color": "#ff000080", "owner": "Обоссляндия", "capital": {"x": 430, "y": 300}, "points": [[320, 200], [560, 230], [590, 380], [410, 520], [300, 420]]},
            {"id": "region_2", "name": "Южный берег", "color": "#0033ff80", "owner": "Вилония", "capital": {"x": 670, "y": 780}, "points": [[540, 560], [840, 580], [870, 900], [550, 910], [500, 700]]},
        ]
    }


def ensure_schema(path: str) -> None:
    with _db(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS active_research (id INTEGER PRIMARY KEY AUTOINCREMENT, country TEXT NOT NULL, tech_id TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, duration_days INTEGER NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, start_message_id INTEGER, effects TEXT, status TEXT NOT NULL DEFAULT 'active')")
        conn.execute("CREATE TABLE IF NOT EXISTS country_tech (country TEXT NOT NULL, tech_id TEXT NOT NULL, unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (country, tech_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS country_units (country TEXT NOT NULL, unit_type TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (country, unit_type))")
        conn.execute("CREATE TABLE IF NOT EXISTS web_users (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id TEXT UNIQUE NOT NULL, role TEXT NOT NULL DEFAULT 'user', password_hash TEXT NOT NULL DEFAULT '', pin_hash TEXT NOT NULL DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1)")
        conn.execute("CREATE TABLE IF NOT EXISTS web_login_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT NOT NULL, timestamp INTEGER NOT NULL, success INTEGER NOT NULL DEFAULT 0)")
        conn.commit()


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["DB_PATH"] = db_path or DB_PATH
    ensure_schema(app.config["DB_PATH"])

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/admin")
    def admin():
        return render_template("admin.html")

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

    @app.get("/api/research/active/<country>")
    def api_research_active_country(country: str):
        now = datetime.now(timezone.utc)
        with _db(app.config["DB_PATH"]) as conn:
            rows = conn.execute(
                "SELECT id, country, tech_id, name, category, duration_days, start_date, end_date FROM active_research WHERE status = 'active' AND country = ? ORDER BY end_date ASC",
                (country,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                start = datetime.fromisoformat(str(item["start_date"]))
                end = datetime.fromisoformat(str(item["end_date"]))
                full = max(1.0, (end - start).total_seconds())
                done = min(full, max(0.0, (now - start).total_seconds()))
                item["progress"] = round((done / full) * 100, 2)
            except Exception:
                item["progress"] = 0.0
            out.append(item)
        return jsonify(out)

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

    @app.get("/api/resources")
    def api_resources():
        return jsonify(_load_json(RESOURCES_PATH, _default_resources()))

    @app.get("/api/territories")
    def api_territories():
        return jsonify(_load_json(TERRITORIES_PATH, _default_territories()))

    @app.post("/api/resource/claim")
    def api_resource_claim():
        payload = request.get_json(silent=True) or {}
        point_id = str(payload.get("point_id") or "").strip()
        action = str(payload.get("action") or "mine").strip() or "mine"
        country = str(payload.get("country") or "").strip()
        user_id = int(payload.get("user_id") or 0)
        click_x = int(payload.get("click_x") or 0)
        click_y = int(payload.get("click_y") or 0)
        frame_ok = bool(payload.get("frame_ok", True))
        if not point_id or not country or not user_id:
            return jsonify({"error": "point_id, country, user_id are required"}), 400

        # 1) Отправляем событие в бот webhook API.
        webhook_payload = {
            "point_id": point_id,
            "action": action,
            "country": country,
            "user_id": user_id,
            "click_x": click_x,
            "click_y": click_y,
            "frame_ok": frame_ok,
        }
        webhook_response, webhook_status = _forward_resource_claim(webhook_payload)
        if webhook_status >= 400:
            return jsonify(webhook_response), webhook_status

        # 2) Локально обновляем карту (фронт получает уже актуальные JSON-данные).
        resources = _load_json(RESOURCES_PATH, _default_resources())
        points = list(resources.get("points", []))
        target = next((p for p in points if str(p.get("id")) == point_id), None)
        if target is None:
            return jsonify({"error": "Resource point not found"}), 404
        target["owner"] = country
        if action == "mine" and bool(target.get("can_mine", True)):
            target["amount"] = max(0, int(target.get("amount", 0)) - 10)
        _save_json(RESOURCES_PATH, {"points": points})

        # 3) При колонизации меняем владельца территории и цвет региона.
        territories = _load_json(TERRITORIES_PATH, _default_territories())
        if action == "colonize":
            region_id = str(target.get("region_id") or "")
            for region in territories.get("regions", []):
                if str(region.get("id")) == region_id:
                    region["owner"] = country
                    region["color"] = str(payload.get("new_color") or region.get("color") or "#ffffff80")
        _save_json(TERRITORIES_PATH, territories)

        return jsonify({"success": True, "point": target, "webhook": webhook_response})

    @app.post("/api/admin/resource")
    def api_admin_resource_update():
        if not _admin_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action") or "").strip()
        resources = _load_json(RESOURCES_PATH, _default_resources())
        points = list(resources.get("points", []))

        if action == "add":
            point = dict(payload.get("point") or {})
            point.setdefault("name", point.get("id") or "Новая точка")
            point.setdefault("icon", RESOURCE_ICONS.get(str(point.get("type", "")).lower(), "📦"))
            points.append(point)
        else:
            point_id = str(payload.get("id") or "").strip()
            target = next((p for p in points if str(p.get("id")) == point_id), None)
            if target is None:
                return jsonify({"error": "Point not found"}), 404
            if "owner" in payload:
                target["owner"] = payload["owner"]
            if "amount" in payload:
                target["amount"] = int(payload["amount"])
            if "can_mine" in payload:
                target["can_mine"] = bool(payload["can_mine"])
            if "type" in payload:
                target["type"] = payload["type"]
                target["icon"] = RESOURCE_ICONS.get(str(payload["type"]).lower(), target.get("icon", "📦"))
        _save_json(RESOURCES_PATH, {"points": points})
        return jsonify({"success": True, "points": points})

    @app.post("/api/admin/territory")
    def api_admin_territory_update():
        if not _admin_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        region_id = str(payload.get("id") or "").strip()
        owner = str(payload.get("owner") or "").strip()
        color = str(payload.get("color") or "").strip()
        territories = _load_json(TERRITORIES_PATH, _default_territories())
        target = next((r for r in territories.get("regions", []) if str(r.get("id")) == region_id), None)
        if target is None:
            return jsonify({"error": "Region not found"}), 404
        if owner:
            target["owner"] = owner
        if color:
            target["color"] = color
        _save_json(TERRITORIES_PATH, territories)
        return jsonify({"success": True, "regions": territories.get("regions", [])})

    @app.get("/api/admin/users")
    def api_admin_users():
        if not _admin_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        with _db(app.config["DB_PATH"]) as conn:
            rows = conn.execute(
                "SELECT id, telegram_id, role, is_active FROM web_users ORDER BY id ASC"
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "5000")), debug=False)
