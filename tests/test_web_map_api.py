import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import web.app as web_app


def seed(path: str):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE country_stats (country TEXT PRIMARY KEY, budget INTEGER, army INTEGER, citizens INTEGER, life_level INTEGER, risk_index INTEGER, war_status TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO country_stats (country,budget,army,citizens,life_level,risk_index,war_status) VALUES ('Обоссляндия',50000,100,900,55,5,'peace')")
    conn.commit()
    conn.close()


def test_resources_and_admin_update(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    seed(str(db))

    resources = tmp_path / "resources.json"
    territories = tmp_path / "territories.json"
    resources.write_text(json.dumps({"points": [{"id": "stone_1", "amount": 100, "owner": "Обоссляндия"}]}, ensure_ascii=False), encoding="utf-8")
    territories.write_text(json.dumps({"regions": [{"id": "region_1", "owner": "Обоссляндия"}]}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(web_app, "RESOURCES_PATH", resources)
    monkeypatch.setattr(web_app, "TERRITORIES_PATH", territories)

    app = web_app.create_app(str(db))
    client = app.test_client()

    payload = client.get("/api/resources").get_json()
    assert payload["points"][0]["id"] == "stone_1"

    resp = client.post("/api/admin/resource", json={"id": "stone_1", "amount": 77})
    assert resp.status_code == 200
    updated = json.loads(resources.read_text(encoding="utf-8"))
    assert updated["points"][0]["amount"] == 77


def test_claim_forwards_to_bot(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    seed(str(db))

    resources = tmp_path / "resources.json"
    territories = tmp_path / "territories.json"
    resources.write_text(json.dumps({"points": []}, ensure_ascii=False), encoding="utf-8")
    territories.write_text(json.dumps({"regions": []}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(web_app, "RESOURCES_PATH", resources)
    monkeypatch.setattr(web_app, "TERRITORIES_PATH", territories)
    monkeypatch.setattr(web_app, "_forward_claim_to_bot", lambda payload: (200, {"ok": True, "point_id": payload["point_id"]}))

    app = web_app.create_app(str(db))
    client = app.test_client()
    resp = client.post("/api/resource/claim", json={"point_id": "stone_1", "country": "Обоссляндия", "user_id": 1})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["result"]["point_id"] == "stone_1"
