import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import web.app as web_app


def seed(path: str):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE country_stats (country TEXT PRIMARY KEY, budget INTEGER, army INTEGER, citizens INTEGER, life_level INTEGER, risk_index INTEGER, war_status TEXT, updated_at TEXT)")
    conn.execute("CREATE TABLE military_factories (country TEXT PRIMARY KEY, factories_count INTEGER)")
    conn.execute("INSERT INTO country_stats (country,budget,army,citizens,life_level,risk_index,war_status) VALUES ('Обоссляндия',50000,100,900,55,5,'peace')")
    conn.execute("INSERT INTO military_factories (country,factories_count) VALUES ('Обоссляндия',2)")
    conn.commit()
    conn.close()


def test_resource_claim_updates_json(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    seed(str(db))
    resources = tmp_path / "resources.json"
    territories = tmp_path / "territories.json"
    resources.write_text(json.dumps({"points": [{"id": "stone_1", "name": "n", "x": 1, "y": 1, "type": "камень", "icon": "🪨", "amount": 100, "owner": "Обоссляндия", "can_mine": True, "region_id": "r1"}]}, ensure_ascii=False), encoding="utf-8")
    territories.write_text(json.dumps({"regions": [{"id": "r1", "name": "R", "color": "#111", "owner": "Обоссляндия", "capital": {"x": 1, "y": 1}, "points": []}]}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(web_app, "RESOURCES_PATH", resources)
    monkeypatch.setattr(web_app, "TERRITORIES_PATH", territories)
    monkeypatch.setattr(web_app, "_forward_resource_claim", lambda payload: ({"success": True}, 200))

    app = web_app.create_app(str(db))
    c = app.test_client()
    resp = c.post("/api/resource/claim", json={"point_id": "stone_1", "action": "mine", "country": "Обоссляндия", "user_id": 1, "click_x": 10, "click_y": 20, "frame_ok": True})
    assert resp.status_code == 200
    data = json.loads(resources.read_text(encoding="utf-8"))
    assert data["points"][0]["amount"] == 90
