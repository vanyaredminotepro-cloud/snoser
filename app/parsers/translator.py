import asyncio
import logging

from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)


class AutoTranslator:
    async def to_russian(self, text: str) -> str:
        if not text.strip():
            return text
        return await asyncio.to_thread(self._translate_sync, text)

    def _translate_sync(self, text: str) -> str:
        try:
            return GoogleTranslator(source="auto", target="ru").translate(text)
        except Exception as exc:
            logger.warning("Translation failed, fallback to original: %s", exc)
            return text
