from __future__ import annotations

import json
import os
import sqlite3
import hashlib
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

DB_PATH = os.environ.get("DB_PATH", "app/storage/bot_data.sqlite3")
API_TOKEN = os.environ.get("WEB_API_TOKEN", "").strip()
BOT_WEBHOOK_URL = os.environ.get("BOT_WEBHOOK_URL", "http://127.0.0.1:8090/webhook/resource/claim").strip()
BOT_RESEARCH_WEBHOOK_URL = os.environ.get("BOT_RESEARCH_WEBHOOK_URL", "http://127.0.0.1:8090/webhook/research/start").strip()
BOT_WEBHOOK_SECRET = os.environ.get("BOT_WEBHOOK_SECRET", "dev-secret").strip()
SESSION_TTL_HOURS = int(os.environ.get("WEB_SESSION_TTL_HOURS", "24"))
SUPREME_TG_ID = int(os.environ.get("WEB_SUPREME_TELEGRAM_ID", "5006629901"))
SUPREME_PASSWORD = os.environ.get("WEB_SUPREME_PASSWORD", "change-me-now")

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


def _hash_password(password: str, salt: str) -> str:
    raw = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return raw.hex()


def _issue_token() -> str:
    return secrets.token_urlsafe(32)


def _session_user(conn: sqlite3.Connection) -> sqlite3.Row | None:
    auth = request.headers.get("Authorization", "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    row = conn.execute(
        """
        SELECT u.id, u.telegram_id, u.role, u.active
        FROM web_sessions s
        JOIN web_users u ON u.id = s.user_id
        WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
        """,
        (token,),
    ).fetchone()
    if row is None or int(row["active"]) != 1:
        return None
    return row


def _session_token() -> str | None:
    auth = request.headers.get("Authorization", "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    return token or None


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


def _country_id_for_name(conn: sqlite3.Connection, country: str) -> int:
    rows = conn.execute("SELECT country FROM country_stats ORDER BY country").fetchall()
    for idx, row in enumerate(rows, start=1):
        if str(row["country"]) == country:
            return idx
    return 0


def _post_json_webhook(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
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


def _forward_claim_to_bot(payload: dict) -> tuple[int, dict]:
    return _post_json_webhook(BOT_WEBHOOK_URL, payload)


def _forward_research_to_bot(payload: dict) -> tuple[int, dict]:
    return _post_json_webhook(BOT_RESEARCH_WEBHOOK_URL, payload)


def ensure_schema(path: str) -> None:
    with _db(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS active_research (id INTEGER PRIMARY KEY AUTOINCREMENT, country_id INTEGER NOT NULL DEFAULT 0, country TEXT NOT NULL DEFAULT '', tech_id TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, duration_days INTEGER NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, start_message_id INTEGER, effects TEXT, status TEXT NOT NULL DEFAULT 'active')")
        conn.execute("CREATE TABLE IF NOT EXISTS country_tech (country TEXT NOT NULL, tech_id TEXT NOT NULL, unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (country, tech_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS country_units (country TEXT NOT NULL, unit_type TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (country, unit_type))")
        try:
            conn.execute("ALTER TABLE active_research ADD COLUMN country_id INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE active_research ADD COLUMN country TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'player',
                twofa_pin_hash TEXT NOT NULL DEFAULT '',
                twofa_pin_salt TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        admin = conn.execute("SELECT id FROM web_users WHERE telegram_id = ?", (SUPREME_TG_ID,)).fetchone()
        if admin is None:
            salt = secrets.token_hex(8)
            conn.execute(
                "INSERT INTO web_users (telegram_id, password_hash, password_salt, role, active) VALUES (?, ?, ?, 'supreme', 1)",
                (SUPREME_TG_ID, _hash_password(SUPREME_PASSWORD, salt), salt),
            )
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
            country_id = _country_id_for_name(conn, country)
            cur = conn.execute(
                "INSERT INTO active_research (country_id, country, tech_id, name, category, duration_days, start_date, end_date, effects, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
                (country_id, country, tech_id, str(tech["name"]), str(tech["category"]), int(tech["duration"]), start_dt.isoformat(), end_dt.isoformat(), json.dumps(tech.get("effects", {}), ensure_ascii=False)),
            )
            research_id = int(cur.lastrowid or 0)
            conn.commit()
        hook_status, hook_body = _forward_research_to_bot({
            "research_id": research_id,
            "country": country,
            "tech_id": tech_id,
            "name": str(tech["name"]),
            "category": str(tech["category"]),
            "duration_days": int(tech["duration"]),
            "cost": int(tech["cost"]),
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
        })
        return jsonify({"success": True, "end_date": end_dt.isoformat(), "news_status": hook_status, "news_result": hook_body})

    @app.post("/api/auth/register")
    def api_auth_register():
        payload = request.get_json(silent=True) or {}
        tg_id = int(payload.get("telegram_id") or 0)
        password = str(payload.get("password") or "")
        twofa_pin = str(payload.get("twofa_pin") or "")
        if tg_id <= 0 or len(password) < 6:
            return jsonify({"error": "telegram_id and password(>=6) are required"}), 400
        with _db(app.config["DB_PATH"]) as conn:
            exists = conn.execute("SELECT id FROM web_users WHERE telegram_id = ?", (tg_id,)).fetchone()
            if exists is not None:
                return jsonify({"error": "user already exists"}), 409
            salt = secrets.token_hex(8)
            twofa_salt = secrets.token_hex(8) if twofa_pin else ""
            conn.execute(
                """
                INSERT INTO web_users (telegram_id, password_hash, password_salt, role, twofa_pin_hash, twofa_pin_salt, active)
                VALUES (?, ?, ?, 'player', ?, ?, 1)
                """,
                (tg_id, _hash_password(password, salt), salt, _hash_password(twofa_pin, twofa_salt) if twofa_pin else "", twofa_salt),
            )
            conn.commit()
        return jsonify({"success": True})

    @app.post("/api/auth/login")
    def api_auth_login():
        payload = request.get_json(silent=True) or {}
        tg_id = int(payload.get("telegram_id") or 0)
        password = str(payload.get("password") or "")
        with _db(app.config["DB_PATH"]) as conn:
            blocked = conn.execute(
                """
                SELECT COUNT(*) FROM web_login_attempts
                WHERE telegram_id = ? AND success = 0 AND created_at >= datetime('now','-15 minutes')
                """,
                (tg_id,),
            ).fetchone()
            if int(blocked[0] or 0) >= 5:
                return jsonify({"error": "too many attempts, try later"}), 429
            row = conn.execute(
                "SELECT id, password_hash, password_salt, twofa_pin_hash, active FROM web_users WHERE telegram_id = ?",
                (tg_id,),
            ).fetchone()
            if row is None or int(row["active"]) != 1:
                conn.execute("INSERT INTO web_login_attempts (telegram_id, success) VALUES (?, 0)", (tg_id,))
                conn.commit()
                return jsonify({"error": "invalid credentials"}), 401
            if _hash_password(password, str(row["password_salt"])) != str(row["password_hash"]):
                conn.execute("INSERT INTO web_login_attempts (telegram_id, success) VALUES (?, 0)", (tg_id,))
                conn.commit()
                return jsonify({"error": "invalid credentials"}), 401
            if str(row["twofa_pin_hash"]):
                pre_token = _issue_token()
                exp = datetime.now(timezone.utc) + timedelta(minutes=10)
                conn.execute("INSERT OR REPLACE INTO web_sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (f"pre:{pre_token}", int(row["id"]), exp.isoformat()))
                conn.execute("INSERT INTO web_login_attempts (telegram_id, success) VALUES (?, 1)", (tg_id,))
                conn.commit()
                return jsonify({"success": True, "requires_2fa": True, "pre_token": pre_token})
            token = _issue_token()
            exp = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
            conn.execute("INSERT OR REPLACE INTO web_sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, int(row["id"]), exp.isoformat()))
            conn.execute("INSERT INTO web_login_attempts (telegram_id, success) VALUES (?, 1)", (tg_id,))
            conn.commit()
        return jsonify({"success": True, "token": token, "requires_2fa": False})

    @app.post("/api/auth/verify_2fa")
    def api_auth_verify_2fa():
        payload = request.get_json(silent=True) or {}
        pre_token = str(payload.get("pre_token") or "").strip()
        twofa_pin = str(payload.get("twofa_pin") or "").strip()
        if not pre_token or not twofa_pin:
            return jsonify({"error": "pre_token and twofa_pin required"}), 400
        with _db(app.config["DB_PATH"]) as conn:
            sess = conn.execute("SELECT user_id FROM web_sessions WHERE token = ? AND expires_at > CURRENT_TIMESTAMP", (f"pre:{pre_token}",)).fetchone()
            if sess is None:
                return jsonify({"error": "pre-session expired"}), 401
            user = conn.execute("SELECT twofa_pin_hash, twofa_pin_salt FROM web_users WHERE id = ?", (int(sess["user_id"]),)).fetchone()
            if user is None or not str(user["twofa_pin_hash"]):
                return jsonify({"error": "2fa is not enabled"}), 400
            if _hash_password(twofa_pin, str(user["twofa_pin_salt"])) != str(user["twofa_pin_hash"]):
                return jsonify({"error": "invalid 2fa pin"}), 401
            token = _issue_token()
            exp = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
            conn.execute("DELETE FROM web_sessions WHERE token = ?", (f"pre:{pre_token}",))
            conn.execute("INSERT OR REPLACE INTO web_sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, int(sess["user_id"]), exp.isoformat()))
            conn.commit()
        return jsonify({"success": True, "token": token})

    @app.get("/api/auth/me")
    def api_auth_me():
        with _db(app.config["DB_PATH"]) as conn:
            user = _session_user(conn)
            if user is None:
                return jsonify({"error": "unauthorized"}), 401
            return jsonify({"telegram_id": int(user["telegram_id"]), "role": str(user["role"])})

    @app.post("/api/auth/logout")
    def api_auth_logout():
        token = _session_token()
        if not token:
            return jsonify({"error": "unauthorized"}), 401
        with _db(app.config["DB_PATH"]) as conn:
            conn.execute("DELETE FROM web_sessions WHERE token = ?", (token,))
            conn.commit()
        return jsonify({"success": True})

    @app.get("/api/admin/users")
    def api_admin_users():
        with _db(app.config["DB_PATH"]) as conn:
            actor = _session_user(conn)
            if actor is None or str(actor["role"]) not in {"supreme", "admin"}:
                return jsonify({"error": "forbidden"}), 403
            rows = conn.execute(
                "SELECT telegram_id, role, active, created_at FROM web_users ORDER BY id ASC LIMIT 200"
            ).fetchall()
            return jsonify([dict(r) for r in rows])

    @app.post("/api/admin/users/role")
    def api_admin_users_role():
        with _db(app.config["DB_PATH"]) as conn:
            actor = _session_user(conn)
            if actor is None or str(actor["role"]) != "supreme":
                return jsonify({"error": "forbidden"}), 403
            payload = request.get_json(silent=True) or {}
            tg_id = int(payload.get("telegram_id") or 0)
            role = str(payload.get("role") or "player")
            if tg_id <= 0 or role not in {"player", "moderator", "admin", "supreme"}:
                return jsonify({"error": "invalid payload"}), 400
            conn.execute("UPDATE web_users SET role = ? WHERE telegram_id = ?", (role, tg_id))
            conn.commit()
        return jsonify({"success": True})

    @app.post("/api/admin/users/ban")
    def api_admin_users_ban():
        with _db(app.config["DB_PATH"]) as conn:
            actor = _session_user(conn)
            if actor is None or str(actor["role"]) not in {"supreme", "admin"}:
                return jsonify({"error": "forbidden"}), 403
            payload = request.get_json(silent=True) or {}
            tg_id = int(payload.get("telegram_id") or 0)
            active = 0 if bool(payload.get("ban", True)) else 1
            if tg_id <= 0:
                return jsonify({"error": "telegram_id required"}), 400
            conn.execute("UPDATE web_users SET active = ? WHERE telegram_id = ?", (active, tg_id))
            conn.commit()
        return jsonify({"success": True})

    @app.post("/api/admin/territories/import")
    def api_admin_territories_import():
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        regions = payload.get("regions")
        if not isinstance(regions, list):
            return jsonify({"error": "regions must be a list"}), 400
        normalized = []
        for item in regions:
            if not isinstance(item, dict):
                continue
            poly = item.get("polygon")
            if isinstance(poly, list):
                item["polygon"] = [
                    {"x": float(p.get("x", 0)), "y": float(p.get("y", 0))}
                    for p in poly
                    if isinstance(p, dict)
                ]
            normalized.append(item)
        out = {"regions": normalized}
        if isinstance(payload.get("viewBox"), str):
            out["viewBox"] = payload["viewBox"]
        if isinstance(payload.get("base_image"), str):
            out["base_image"] = payload["base_image"]
        _save_json(TERRITORIES_PATH, out)
        return jsonify({"success": True, "regions": len(normalized)})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "5000")), debug=False)
