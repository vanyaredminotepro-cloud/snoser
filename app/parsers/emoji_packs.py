import json
import logging
from pathlib import Path

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import StickersetInvalidError
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputStickerSetShortName

logger = logging.getLogger(__name__)


class EmojiPackLoader:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path

    @staticmethod
    def _extract_pack_name(pack_input: str) -> str:
        raw = (pack_input or "").strip()
        if "addemoji/" in raw:
            return raw.split("addemoji/")[-1].split("?")[0]
        return raw.replace("@", "")

    async def load_pack(self, client: TelegramClient, pack_ref: str) -> dict[str, int]:
        short_name = self._extract_pack_name(pack_ref)
        if not short_name:
            return {}

        try:
            sticker_set = await client(GetStickerSetRequest(stickerset=InputStickerSetShortName(short_name), hash=0))
            out: dict[str, int] = {}
            for doc in sticker_set.documents:
                alt_value = None
                for attr in getattr(doc, "attributes", []) or []:
                    if hasattr(attr, "alt") and getattr(attr, "alt", None):
                        alt_value = str(attr.alt)
                        break
                key = alt_value or str(getattr(doc, "id", ""))
                if key:
                    out[key] = int(doc.id)
            logger.info("Loaded emoji pack %s: %s items", short_name, len(out))
            return out
        except StickersetInvalidError:
            logger.warning("Emoji pack is invalid or inaccessible and will be skipped: %s", short_name)
            return {}
        except Exception:
            logger.exception("Failed to load emoji pack: %s", short_name)
            return {}

    async def load_all(self, client: TelegramClient, packs: dict[str, str]) -> dict[str, int]:
        merged: dict[str, int] = {}
        for alias, ref in packs.items():
            pack_items = await self.load_pack(client, ref)
            for k, v in pack_items.items():
                merged[f"{alias}:{k}"] = v
        self._save_cache(merged)
        return merged

    def _save_cache(self, data: dict[str, int]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_cache(self) -> dict[str, int]:
        if not self.storage_path.exists():
            return {}
        try:
            return {k: int(v) for k, v in json.loads(self.storage_path.read_text(encoding="utf-8")).items()}
        except Exception:
            logger.exception("Failed to read emoji cache")
            return {}
