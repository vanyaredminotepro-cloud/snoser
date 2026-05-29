import asyncio
import json
import logging
import sys
from contextlib import suppress
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot import AppRuntime
from app.config import config
from app.core.logging_setup import setup_logging
from app.core.services import NewsService
from app.storage.database import Database

ROOT_DIR = Path(__file__).resolve().parents[1]
RESOURCES_PATH = ROOT_DIR / "web" / "data" / "resources.json"
TERRITORIES_PATH = ROOT_DIR / "web" / "data" / "territories.json"


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


def _apply_resource_claim(payload: dict) -> dict:
    point_id = str(payload.get("point_id") or "").strip()
    country = str(payload.get("country") or "").strip()
    frame_ok = bool(payload.get("frame_ok", True))
    if not point_id or not country:
        return {"error": "point_id and country are required", "status": 400}
    if not frame_ok:
        return {"error": "frame validation failed", "status": 409}

    resources = _load_json(RESOURCES_PATH, {"points": []})
    territories = _load_json(TERRITORIES_PATH, {"regions": []})

    points = resources.get("points") if isinstance(resources.get("points"), list) else []
    regions = territories.get("regions") if isinstance(territories.get("regions"), list) else []

    target_point = next((p for p in points if str(p.get("id")) == point_id), None)
    if target_point is None:
        return {"error": "point not found", "status": 404}

    current_amount = int(target_point.get("amount", 0))
    mine_amount = min(10, max(0, current_amount))
    target_point["amount"] = max(0, current_amount - mine_amount)
    target_point["owner"] = country

    region_id = str(target_point.get("region_id") or "").strip()
    if region_id:
        for region in regions:
            if str(region.get("id")) == region_id:
                region["owner"] = country
                break

    _save_json(RESOURCES_PATH, resources)
    _save_json(TERRITORIES_PATH, territories)
    return {
        "status": 200,
        "result": {
            "point_id": point_id,
            "owner": country,
            "delta": mine_amount,
            "amount": target_point["amount"],
            "region_id": region_id,
        },
    }


async def _control_server(port: int, db: Database, service: NewsService | None = None) -> asyncio.AbstractServer:
    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        body_bytes = b""
        status = 200
        payload: dict | str = {"ok": True}

        try:
            raw = await reader.read(1024 * 1024)
            header_blob, _, body_bytes = raw.partition(b"\r\n\r\n")
            lines = header_blob.decode("utf-8", errors="ignore").split("\r\n")
            request_line = lines[0] if lines else ""
            method, path, _ = (request_line.split(" ") + ["", ""])[:3]
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            if method == "GET" and path == "/health":
                payload = "ok"
            elif method == "POST" and path == "/webhook/resource/claim":
                secret = headers.get("x-webhook-secret", "")
                if config.bot_webhook_secret and secret != config.bot_webhook_secret:
                    status = 401
                    payload = {"error": "invalid secret"}
                else:
                    event = json.loads(body_bytes.decode("utf-8") or "{}")
                    result = _apply_resource_claim(event)
                    status = int(result.get("status", 200))
                    payload = result.get("result") or {"error": result.get("error", "unknown")}
                    await db.set_state("webhook:last_resource_claim", json.dumps(event, ensure_ascii=False))
                    count = int(await db.get_state("metric:webhook_resource_claim_total", "0") or "0")
                    await db.set_state("metric:webhook_resource_claim_total", str(count + 1))
            elif method == "POST" and path == "/webhook/research/start":
                secret = headers.get("x-webhook-secret", "")
                if config.bot_webhook_secret and secret != config.bot_webhook_secret:
                    status = 401
                    payload = {"error": "invalid secret"}
                elif service is None:
                    status = 503
                    payload = {"error": "bot service is not ready"}
                else:
                    event = json.loads(body_bytes.decode("utf-8") or "{}")
                    country = str(event.get("country") or "").strip()
                    name = str(event.get("name") or event.get("tech_id") or "исследование").strip()
                    duration_days = int(event.get("duration_days") or 0)
                    end_date = str(event.get("end_date") or "")
                    if not country or not name:
                        status = 400
                        payload = {"error": "country and name are required"}
                    else:
                        text = (
                            f"🔬 <b>{country} начинает исследование</b>\n"
                            f"Тема: <b>{name}</b>\n"
                            f"Длительность: <b>{duration_days} дн.</b>\n"
                            f"Завершение: <b>{end_date}</b>"
                        )
                        if service.user_client:
                            await service._send_with_retry(lambda: service._send_to_target_channel(text, parse_mode="html"))
                        else:
                            await service.bot.send_message(config.target_channel, text, parse_mode="HTML")
                        await db.set_state("webhook:last_research_start", json.dumps(event, ensure_ascii=False))
                        count = int(await db.get_state("metric:webhook_research_start_total", "0") or "0")
                        await db.set_state("metric:webhook_research_start_total", str(count + 1))
                        payload = {"ok": True, "country": country, "name": name}
            else:
                status = 404
                payload = {"error": "not found"}
        except Exception as exc:
            status = 500
            payload = {"error": str(exc)}

        if isinstance(payload, str):
            body = payload.encode("utf-8")
            content_type = b"text/plain; charset=utf-8"
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = b"application/json; charset=utf-8"

        response = (
            f"HTTP/1.1 {status} {'OK' if status < 400 else 'ERROR'}\r\n".encode("utf-8")
            + b"Content-Type: "
            + content_type
            + b"\r\nContent-Length: "
            + str(len(body)).encode("utf-8")
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        writer.write(response)
        with suppress(Exception):
            await writer.drain()
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    return await asyncio.start_server(_handle, host="0.0.0.0", port=port)


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Booting Telegram RP news bot...")
    config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(str(config.sqlite_path))
    await db.init()

    control_server: asyncio.AbstractServer | None = None

    seeded = await db.seed_country_leaders(config.manual_country_authors)
    logger.info("Country leaders seeded from config: %s", seeded)
    stats_seeded = await db.seed_country_stats(config.initial_country_stats)
    logger.info("Country stats seeded from config: %s", stats_seeded)
    extras_seeded = await db.seed_country_extra_metrics(config.initial_country_extra_metrics)
    logger.info("Country extra metrics seeded from config: %s", extras_seeded)
    factory_seeded = await db.seed_military_factories(config.initial_military_factories)
    logger.info("Military factories seeded from config: %s", factory_seeded)
    resources_seeded = await db.seed_economic_resources(config.initial_economic_resources)
    logger.info("Economic resources seeded from config: %s", resources_seeded)

    try:
        runtime = AppRuntime()
    except RuntimeError as exc:
        logger.error(str(exc))
        logger.error("Configure environment variables (or .env) and restart the bot.")
        return

    service = NewsService(runtime.bot, db)
    await service.load_dynamic_config()
    if config.healthcheck_enabled:
        control_server = await _control_server(config.webhook_port, db, service)
        logger.info("Control server enabled on 0.0.0.0:%s", config.webhook_port)
    try:
        await runtime.run(service)
    finally:
        if control_server is not None:
            control_server.close()
            await control_server.wait_closed()
            logger.info("Control server stopped")


def run() -> None:
    if sys.platform != "win32":
        import uvloop

        uvloop.install()
    asyncio.run(main())


if __name__ == "__main__":
    run()
