import re
from dataclasses import dataclass


@dataclass(slots=True)
class FilterResult:
    allowed: bool
    reason: str


class RPFilter:
    war_roots = {
        "войн", "атак", "штурм", "фронт", "войск", "укреп", "удар", "блокпост", "база",
        "операци", "наступ", "обстрел", "боев", "воен",
    }

    ooc_roots = {
        "админ", "рендер", "правил", "механик", "оос", "ooc", "нерп", "нонрп", "мета",
        "irl", "чат", "обсуждени", "флуд", "мем", "рофл", "опрос", "бан",
        "кик", "набор", "анкета", "биограф",
    }

    ooc_phrases = {
        "не рп", "в реале", "по факту", "в жизни",
    }

    allow_roots = {
        "стро", "завод", "фабрик", "инфраструкт", "дорог", "логист", "торгов", "сделк", "дипломат",
        "договор", "союз", "реформ", "развит", "территор", "колонизац", "открыт", "исследован",
        "технолог", "проект", "инициатив", "медицин", "образован", "культур", "указ", "закон",
        "политик", "эконом", "промышлен", "госпрограмм", "встреч", "переговор", "саммит",
        "корол", "визит", "делегац",
    }

    real_world_roots = {
        "росси", "украин", "нато", "сша", "евросоюз", "пути", "байден", "ww2",
    }

    @staticmethod
    def _words(text: str) -> list[str]:
        return re.findall(r"[\w-]+", text.lower(), flags=re.UNICODE)

    @staticmethod
    def _contains_root(words: list[str], roots: set[str]) -> bool:
        return any(any(word.startswith(root) for root in roots) for word in words)

    def check(self, text: str) -> FilterResult:
        low = text.lower()
        words = self._words(low)

        if self._contains_root(words, self.war_roots):
            return FilterResult(False, "WAR_CONTENT")

        if any(phrase in low for phrase in self.ooc_phrases) or self._contains_root(words, self.ooc_roots):
            return FilterResult(False, "OOC_META_CONTENT")

        if self._contains_root(words, self.real_world_roots):
            return FilterResult(False, "REAL_WORLD_CONTENT")

        if len(words) < 5:
            return FilterResult(False, "TOO_SHORT_OR_NO_RP_EVENT")

        if not self._contains_root(words, self.allow_roots):
            return FilterResult(False, "NOT_RP_NEWS_ALLOWLIST")

        return FilterResult(True, "ALLOWED")
