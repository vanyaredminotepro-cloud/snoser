import re
from dataclasses import dataclass


@dataclass(slots=True)
class FilterResult:
    allowed: bool
    reason: str


class RPFilter:
    war_roots = {
        "войн", "атак", "штурм", "фронт", "войск", "укреп", "удар", "операци", "наступ", "обстрел", "боев", "воен",
        "мобилизац", "контрнаступ",
    }

    war_allowed_roots = {
        "мобилизац", "подготов", "оборон", "контрнаступ", "перегруп", "сводк", "эвакуац",
    }

    ooc_roots = {
        "админ", "рендер", "правил", "механик", "оос", "ooc", "нерп", "нонрп", "мета",
        "irl", "чат", "обсуждени", "флуд", "мем", "рофл", "опрос", "анкет",
    }

    ooc_phrases = {"не рп", "в реале", "по факту", "в жизни"}

    allow_roots = {
        "стро", "завод", "фабрик", "инфраструкт", "дорог", "логист", "торгов", "сделк", "дипломат",
        "договор", "союз", "реформ", "развит", "территор", "колонизац", "открыт", "исследован",
        "технолог", "проект", "инициатив", "медицин", "образован", "культур", "указ", "закон",
        "политик", "эконом", "промышлен", "госпрограмм", "встреч", "переговор", "саммит", "корол", "визит", "делегац",
        "мобилизац", "контрнаступ", "оборон",
    }

    real_world_roots = {"росси", "украин", "нато", "сша", "евросоюз", "пути", "байден", "ww2"}

    @staticmethod
    def _words(text: str) -> list[str]:
        return re.findall(r"[\w-]+", text.lower(), flags=re.UNICODE)

    @staticmethod
    def _contains_root(words: list[str], roots: set[str]) -> bool:
        return any(any(word.startswith(root) for root in roots) for word in words)

    @staticmethod
    def _max_army_size(text: str) -> int:
        values = [int(v) for v in re.findall(r"\b(\d{2,5})\b", text)]
        return max(values) if values else 0

    def check(self, text: str) -> FilterResult:
        low = text.lower()
        words = self._words(low)

        if any(phrase in low for phrase in self.ooc_phrases) or self._contains_root(words, self.ooc_roots):
            return FilterResult(False, "OOC_META_CONTENT")

        if self._contains_root(words, self.real_world_roots):
            return FilterResult(False, "REAL_WORLD_CONTENT")

        if len(words) < 4:
            return FilterResult(False, "TOO_SHORT_OR_NO_RP_EVENT")

        if self._contains_root(words, self.war_roots):
            max_army = self._max_army_size(low)
            if max_army > 200:
                return FilterResult(False, "ARMY_LIMIT_EXCEEDED_200")
            if max_army and max_army < 50:
                return FilterResult(False, "ARMY_UNREALISTIC_TOO_SMALL")
            if not self._contains_root(words, self.war_allowed_roots):
                return FilterResult(False, "WAR_WITHOUT_RP_PROCESS")
            return FilterResult(True, "ALLOWED_WAR_RULES_OK")

        if not self._contains_root(words, self.allow_roots):
            return FilterResult(False, "NOT_RP_NEWS_ALLOWLIST")

        return FilterResult(True, "ALLOWED")
