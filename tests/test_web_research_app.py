import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_research.app import app


def seed(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE countries (id INTEGER PRIMARY KEY, name TEXT, army INTEGER, budget INTEGER, citizens INTEGER, life_quality INTEGER, risk_index INTEGER)")
    conn.execute("CREATE TABLE active_research (id INTEGER PRIMARY KEY AUTOINCREMENT, country_id INTEGER, tech_id TEXT, name TEXT, category TEXT, duration_days INTEGER, start_date TEXT, end_date TEXT, status TEXT)")
    conn.execute("CREATE TABLE country_tech (country_id INTEGER, tech_id TEXT, unlocked_at TEXT, PRIMARY KEY(country_id, tech_id))")
    conn.execute("INSERT INTO countries (id, name, army, budget, citizens, life_quality, risk_index) VALUES (1, 'Вилония', 120, 60000, 900, 55, 10)")
    conn.commit()
    conn.close()


def test_api_research_start(tmp_path, monkeypatch):
    db = tmp_path / "wr.sqlite3"
    seed(db)
    monkeypatch.setenv("DB_PATH", str(db))

    from importlib import reload
    import web_research.config as cfg
    import web_research.app as mod

    reload(cfg)
    reload(mod)
    client = mod.app.test_client()

    res = client.post("/api/research/start", json={"country_id": 1, "tech_id": "drone_recon"})
    assert res.status_code == 200
    active = client.get("/api/research/active")
    assert len(active.get_json()) == 1
    history = client.get("/api/research/history/1")
    assert history.status_code == 200
    assert len(history.get_json()) >= 1
