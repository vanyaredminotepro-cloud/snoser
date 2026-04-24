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


def test_auth_register_login_and_role_change(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    seed(str(db))
    resources = tmp_path / "resources.json"
    territories = tmp_path / "territories.json"
    resources.write_text(json.dumps({"points": []}, ensure_ascii=False), encoding="utf-8")
    territories.write_text(json.dumps({"regions": []}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(web_app, "RESOURCES_PATH", resources)
    monkeypatch.setattr(web_app, "TERRITORIES_PATH", territories)
    monkeypatch.setattr(web_app, "SUPREME_TG_ID", 999)
    monkeypatch.setattr(web_app, "SUPREME_PASSWORD", "sup-pass")

    app = web_app.create_app(str(db))
    client = app.test_client()

    reg = client.post("/api/auth/register", json={"telegram_id": 111, "password": "secret12", "twofa_pin": "1234"})
    assert reg.status_code == 200

    login = client.post("/api/auth/login", json={"telegram_id": 111, "password": "secret12"})
    assert login.status_code == 200
    pre = login.get_json()
    assert pre["requires_2fa"] is True
    verify = client.post("/api/auth/verify_2fa", json={"pre_token": pre["pre_token"], "twofa_pin": "1234"})
    token = verify.get_json()["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200

    sup_login = client.post("/api/auth/login", json={"telegram_id": 999, "password": "sup-pass"})
    sup_token = sup_login.get_json()["token"]
    promote = client.post(
        "/api/admin/users/role",
        json={"telegram_id": 111, "role": "admin"},
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert promote.status_code == 200


def test_admin_territories_import(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    seed(str(db))
    resources = tmp_path / "resources.json"
    territories = tmp_path / "territories.json"
    resources.write_text(json.dumps({"points": []}, ensure_ascii=False), encoding="utf-8")
    territories.write_text(json.dumps({"regions": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(web_app, "RESOURCES_PATH", resources)
    monkeypatch.setattr(web_app, "TERRITORIES_PATH", territories)

    app = web_app.create_app(str(db))
    client = app.test_client()
    resp = client.post(
        "/api/admin/territories/import",
        json={"viewBox": "0 0 1000 1000", "regions": [{"id": "r1", "polygon": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]}]},
    )
    assert resp.status_code == 200
    saved = json.loads(territories.read_text(encoding="utf-8"))
    assert saved["viewBox"] == "0 0 1000 1000"
    assert saved["regions"][0]["id"] == "r1"


def test_auth_logout_and_admin_list_users(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    seed(str(db))
    resources = tmp_path / "resources.json"
    territories = tmp_path / "territories.json"
    resources.write_text(json.dumps({"points": []}, ensure_ascii=False), encoding="utf-8")
    territories.write_text(json.dumps({"regions": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(web_app, "RESOURCES_PATH", resources)
    monkeypatch.setattr(web_app, "TERRITORIES_PATH", territories)
    monkeypatch.setattr(web_app, "SUPREME_TG_ID", 42)
    monkeypatch.setattr(web_app, "SUPREME_PASSWORD", "sup-pass")

    app = web_app.create_app(str(db))
    client = app.test_client()

    login = client.post("/api/auth/login", json={"telegram_id": 42, "password": "sup-pass"}).get_json()
    token = login["token"]
    users = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert users.status_code == 200
    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401


def test_login_rate_limit(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    seed(str(db))
    resources = tmp_path / "resources.json"
    territories = tmp_path / "territories.json"
    resources.write_text(json.dumps({"points": []}, ensure_ascii=False), encoding="utf-8")
    territories.write_text(json.dumps({"regions": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(web_app, "RESOURCES_PATH", resources)
    monkeypatch.setattr(web_app, "TERRITORIES_PATH", territories)

    app = web_app.create_app(str(db))
    client = app.test_client()
    for _ in range(5):
        resp = client.post("/api/auth/login", json={"telegram_id": 777, "password": "bad-pass"})
        assert resp.status_code == 401
    blocked = client.post("/api/auth/login", json={"telegram_id": 777, "password": "bad-pass"})
    assert blocked.status_code == 429
