from dataclasses import dataclass


@dataclass(slots=True)
class FilterResult:
    allowed: bool
    reason: str


class RPFilter:
    war_words = {
        "войн", "бо", "атак", "штурм", "фронт", "войск", "укреп", "удар", "блокпост", "база",
        "операци", "military", "army", "battle",
    }

    ooc_words = {
        "админ", "рендер", "правил", "механик", "оос", "ooc", "нерп", "нонрп", "не рп", "мета",
        "irl", "в реале", "по факту", "чат", "обсуждени", "флуд", "мем", "рофл", "опрос", "бан",
        "кик", "набор", "анкета", "биограф",
    }

    allow_words = {
        "стро", "завод", "фабрик", "инфраструкт", "дорог", "логист", "торгов", "сделк", "дипломат",
        "договор", "союз", "реформ", "развит", "территор", "колонизац", "открыт", "исследован",
        "технолог", "проект", "инициатив", "медицин", "образован", "культур", "указ", "закон",
        "политик", "эконом", "промышлен", "госпрограмм",
    }

    real_world_words = {
        "росси", "украин", "нато", "сша", "евросоюз", "пути", "байден", "реальн", "ww2",
    }

    def check(self, text: str) -> FilterResult:
        low = text.lower()

        if any(token in low for token in self.war_words):
            return FilterResult(False, "WAR_CONTENT")

        if any(token in low for token in self.ooc_words):
            return FilterResult(False, "OOC_META_CONTENT")

        if any(token in low for token in self.real_world_words):
            return FilterResult(False, "REAL_WORLD_CONTENT")

        if len(low.split()) < 5:
            return FilterResult(False, "TOO_SHORT_OR_NO_RP_EVENT")

        if not any(token in low for token in self.allow_words):
            return FilterResult(False, "NOT_RP_NEWS_ALLOWLIST")

        return FilterResult(True, "ALLOWED")
