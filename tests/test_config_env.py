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
