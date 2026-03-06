import asyncio
import logging
import re

from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)


class AutoTranslator:
    @staticmethod
    def _is_mostly_cyrillic(text: str) -> bool:
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", text)
        if not letters:
            return True
        cyr = re.findall(r"[А-Яа-яЁё]", text)
        return (len(cyr) / len(letters)) >= 0.6

    async def to_russian(self, text: str) -> str:
        if not text.strip() or self._is_mostly_cyrillic(text):
            return text
        return await asyncio.to_thread(self._translate_sync, text)

    def _translate_sync(self, text: str) -> str:
        try:
            return GoogleTranslator(source="auto", target="ru").translate(text)
        except Exception as exc:
            logger.warning("Translation failed, fallback to original: %s", exc)
            return text
