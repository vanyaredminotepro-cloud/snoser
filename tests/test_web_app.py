import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.app import create_app


def seed(path: str):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE country_stats (country TEXT PRIMARY KEY, budget INTEGER, army INTEGER, citizens INTEGER, life_level INTEGER, risk_index INTEGER, war_status TEXT, updated_at TEXT)")
    conn.execute("CREATE TABLE military_factories (country TEXT PRIMARY KEY, factories_count INTEGER)")
    conn.execute("INSERT INTO country_stats (country,budget,army,citizens,life_level,risk_index,war_status) VALUES ('Вилония',50000,100,900,55,5,'peace')")
    conn.execute("INSERT INTO military_factories (country,factories_count) VALUES ('Вилония',2)")
    conn.commit()
    conn.close()


def test_research_start(tmp_path):
    db = tmp_path / "db.sqlite3"
    seed(str(db))
    app = create_app(str(db))
    c = app.test_client()
    res = c.post('/api/research/start', json={'country': 'Вилония', 'tech_id': 'drone_recon'})
    assert res.status_code == 200
    active = c.get('/api/research/active').get_json()
    assert len(active) == 1
