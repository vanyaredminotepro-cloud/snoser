import importlib
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

config_module = importlib.import_module("app.config")
Config = config_module.Config


def test_config_reads_runtime_overrides(monkeypatch):
    monkeypatch.setenv("ADMIN_ID", "123")
    monkeypatch.setenv("ADMIN_USERNAME", "@admin")
    monkeypatch.setenv("TARGET_CHANNEL", "@chan")
    monkeypatch.setenv("SESSION_NAME", "session_test")
    monkeypatch.setenv("SQLITE_PATH", "tmp/test.sqlite3")
    monkeypatch.setenv("LOGS_DIR", "tmp/logs")
    monkeypatch.setenv("PUBLISH_DELAY_SECONDS", "1.5")
    monkeypatch.setenv("QUEUE_INGEST_DELAY_MIN", "2")
    monkeypatch.setenv("QUEUE_INGEST_DELAY_MAX", "5")
    monkeypatch.setenv("QUEUE_PUBLISH_DELAY_MIN", "3")
    monkeypatch.setenv("QUEUE_PUBLISH_DELAY_MAX", "9")
    monkeypatch.setenv("LONG_PAUSE_CHANCE", "0.2")
    monkeypatch.setenv("LONG_PAUSE_MIN", "15")
    monkeypatch.setenv("LONG_PAUSE_MAX", "20")
    monkeypatch.setenv("DAILY_POST_LIMIT", "30")
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("HEALTHCHECK_ENABLED", "false")

    cfg = Config()

    assert cfg.admin_id == 123
    assert cfg.admin_username == "@admin"
    assert cfg.target_channel == "@chan"
    assert cfg.session_name == "session_test"
    assert str(cfg.sqlite_path) == "tmp/test.sqlite3"
    assert str(cfg.logs_dir) == "tmp/logs"
    assert cfg.publish_delay_seconds == 1.5
    assert cfg.queue_ingest_delay_min == 2
    assert cfg.queue_ingest_delay_max == 5
    assert cfg.queue_publish_delay_min == 3
    assert cfg.queue_publish_delay_max == 9
    assert cfg.long_pause_chance == 0.2
    assert cfg.long_pause_min == 15
    assert cfg.long_pause_max == 20
    assert cfg.daily_post_limit == 30
    assert cfg.port == 9090
    assert cfg.healthcheck_enabled is False


def test_config_bool_parser_rejects_invalid(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_ENABLED", "sometimes")

    try:
        Config()
    except RuntimeError as exc:
        assert "HEALTHCHECK_ENABLED" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for invalid boolean")


def test_config_rejects_invalid_long_pause_chance(monkeypatch):
    monkeypatch.setenv("LONG_PAUSE_CHANCE", "1.5")
    try:
        Config()
    except RuntimeError as exc:
        assert "LONG_PAUSE_CHANCE" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for invalid long pause chance")
