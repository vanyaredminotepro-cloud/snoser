import asyncio
import json
import logging
import sys
import time
from contextlib import suppress
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot import AppRuntime
from app.config import config
from app.core.logging_setup import setup_logging
from app.core.services import NewsService
from app.storage.database import Database


def _http_response(status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> bytes:
    status_text = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 405: "Method Not Allowed"}.get(status, "OK")
    return (
        f"HTTP/1.1 {status} {status_text}\r\n".encode("utf-8")
        + f"Content-Type: {content_type}\r\n".encode("utf-8")
        + f"Content-Length: {len(body)}\r\n".encode("utf-8")
        + b"Connection: close\r\n\r\n"
        + body
    )


async def _control_server(port: int, db: Database) -> asyncio.AbstractServer:
    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        raw = await reader.read(16384)
        text = raw.decode("utf-8", errors="ignore")
        head, _, body_raw = text.partition("\r\n\r\n")
        request_line = head.splitlines()[0] if head else ""
        parts = request_line.split(" ")
        method = parts[0] if len(parts) > 0 else ""
        path = parts[1] if len(parts) > 1 else "/"
        headers: dict[str, str] = {}
        for line in head.splitlines()[1:]:
            if ":" in line:
                k, v = line.split(":", maxsplit=1)
                headers[k.strip().lower()] = v.strip()

        response = _http_response(404, json.dumps({"error": "not found"}).encode("utf-8"))
        if method == "GET" and path == "/health":
            response = _http_response(200, b"ok", content_type="text/plain; charset=utf-8")
        elif method == "POST" and path == "/webhook/resource/claim":
            if config.webhook_secret and headers.get("x-webhook-secret", "") != config.webhook_secret:
                response = _http_response(401, json.dumps({"error": "invalid webhook secret"}).encode("utf-8"))
            else:
                try:
                    payload = json.loads(body_raw or "{}")
                except json.JSONDecodeError:
                    payload = {}
                point_id = str(payload.get("point_id") or "").strip()
                country = str(payload.get("country") or "").strip()
                user_id = int(payload.get("user_id") or 0)
                frame_ok = bool(payload.get("frame_ok", True))
                if not point_id or not country or not user_id:
                    response = _http_response(400, json.dumps({"error": "point_id, country, user_id are required"}).encode("utf-8"))
                elif not frame_ok:
                    response = _http_response(400, json.dumps({"error": "frame verification failed"}).encode("utf-8"))
                else:
                    event = {"point_id": point_id, "country": country, "user_id": user_id, "frame_ok": frame_ok, "ts": int(time.time())}
                    await db.set_state("webhook:last_resource_claim", json.dumps(event, ensure_ascii=False))
                    total = int(await db.get_state("metric:webhook_resource_claim_total", "0") or "0") + 1
                    await db.set_state("metric:webhook_resource_claim_total", str(total))
                    response = _http_response(200, json.dumps({"success": True, "event": event, "total_claims": total}, ensure_ascii=False).encode("utf-8"))
        elif path in {"/health", "/webhook/resource/claim"}:
            response = _http_response(405, json.dumps({"error": "method not allowed"}).encode("utf-8"))

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
    control_server: asyncio.AbstractServer | None = None

    db = Database(str(config.sqlite_path))
    await db.init()
    seeded = await db.seed_country_leaders(config.manual_country_authors)
    logger.info("Country leaders seeded from config: %s", seeded)
    stats_seeded = await db.seed_country_stats(config.initial_country_stats)
    logger.info("Country stats seeded from config: %s", stats_seeded)
    extras_seeded = await db.seed_country_extra_metrics(config.initial_country_extra_metrics)
    logger.info("Country extra metrics seeded from config: %s", extras_seeded)
    if config.healthcheck_enabled:
        control_server = await _control_server(config.port, db)
        logger.info("Control server enabled on 0.0.0.0:%s (GET /health, POST /webhook/resource/claim)", config.port)

    try:
        runtime = AppRuntime()
    except RuntimeError as exc:
        logger.error(str(exc))
        logger.error("Configure environment variables (or .env) and restart the bot.")
        return

    service = NewsService(runtime.bot, db)
    await service.load_dynamic_config()
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
