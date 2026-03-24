import re
from dataclasses import dataclass


@dataclass(slots=True)
class FilterResult:
    allowed: bool
    reason: str
    details: str = ""


class RPFilter:
    military_roots = {
        "войн", "атак", "штурм", "фронт", "войск", "укреп", "удар", "операци", "наступ", "обстрел", "боев", "воен",
        "мобилизац", "контрнаступ", "спецназ", "границ", "патрул", "дрон", "миномет", "снайпер", "рэб",
    }

    direct_war_action_roots = {
        "атак", "штурм", "наступ", "обстрел", "подрыв", "зачист", "уничтож", "бомб", "высадк", "боестолк", "удар",
    }

    operation_without_war_roots = {
        "мобилизац", "подготов", "оборон", "перегруп", "эвакуац", "ультимат", "учени", "готовност", "патрул",
        "постро", "завод", "училищ", "ремонт", "модернизац", "логист",
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
        "правител", "назнач", "избран", "официал", "лидер", "глав", "администрац",
        "мобилизац", "оборон", "училищ", "готовност", "патрул", "спецназ",
    }

    action_roots = {
        "начал", "начина", "провод", "запуска", "сообщ", "объяв", "ввод", "созда", "откры", "усили", "расшир",
    }

    real_world_roots = {"росси", "украин", "нато", "сша", "евросоюз", "пути", "байден", "ww2"}

    banned_alliance_tokens = {
        "penis", "p.e.n.i.s", "п.ен.и.с", "пенис", "хуй", "еб", "нахуй", "пизд", "пидор",
    }

    @staticmethod
    def _words(text: str) -> list[str]:
        return re.findall(r"[\w-]+", text.lower(), flags=re.UNICODE)

    @staticmethod
    def _contains_root(words: list[str], roots: set[str]) -> bool:
        return any(any(word.startswith(root) for root in roots) for word in words)

    @staticmethod
    def _sentence_count(text: str) -> int:
        chunks = [x for x in re.split(r"[.!?]+", text) if x.strip()]
        return len(chunks)

    @staticmethod
    def _max_army_size(text: str) -> int:
        values = [int(v) for v in re.findall(r"\b(\d{2,5})\b", text)]
        return max(values) if values else 0

    @staticmethod
    def _contains_banned_alliance_name(low: str) -> bool:
        normalized = re.sub(r"[^a-zа-я0-9]+", "", low)
        for token in RPFilter.banned_alliance_tokens:
            compact = token.replace(".", "")
            if len(compact) <= 2:
                continue
            if "." in token:
                if compact in normalized:
                    return True
                continue
            if re.search(rf"(?i)(?<!\w){re.escape(token)}(?!\w)", low):
                return True
        return False

    @staticmethod
    def _extract_declared_country_terms(low: str) -> list[str]:
        return re.findall(r"(?:республика|королевство|государство|страна)\s+([а-яa-zё\-]{4,})", low)

    def check(self, text: str, known_countries: set[str] | None = None) -> FilterResult:
        low = text.lower()
        words = self._words(low)

        if self._contains_banned_alliance_name(low):
            return FilterResult(False, "BANNED_ALLIANCE_NAME", "обнаружено запрещённое/маскируемое название")

        if any(phrase in low for phrase in self.ooc_phrases) or self._contains_root(words, self.ooc_roots):
            return FilterResult(False, "OOC_META_CONTENT", "обнаружены OOC/meta маркеры")

        if self._contains_root(words, self.real_world_roots):
            return FilterResult(False, "REAL_WORLD_CONTENT", "обнаружены упоминания реального мира")

        if known_countries:
            declared_terms = self._extract_declared_country_terms(low)
            for declared in declared_terms:
                if declared not in known_countries:
                    return FilterResult(False, "UNKNOWN_COUNTRY_MENTIONED", f"неизвестная страна: {declared}")

        if len(words) < 3:
            return FilterResult(False, "TOO_SHORT_OR_NO_RP_EVENT", "слишком короткий текст без RP-контекста")

        if self._contains_root(words, self.military_roots):
            max_army = self._max_army_size(low)
            if max_army > 200:
                return FilterResult(False, "ARMY_LIMIT_EXCEEDED_200", "численность армии выше допустимой")
            if max_army and max_army < 50:
                return FilterResult(False, "ARMY_UNREALISTIC_TOO_SMALL", "нереалистично малая численность армии")
            if self._contains_root(words, self.operation_without_war_roots):
                return FilterResult(True, "MILITARY_OPERATION_AUTOPUBLISH")
            if self._contains_root(words, self.direct_war_action_roots):
                return FilterResult(True, "MILITARY_REVIEW_REQUIRED")
            return FilterResult(True, "MILITARY_REVIEW_REQUIRED")

        if self._contains_root(words, self.action_roots) and self._sentence_count(low) >= 1:
            return FilterResult(True, "ALLOWED")

        if not self._contains_root(words, self.allow_roots):
            return FilterResult(False, "NOT_RP_NEWS_ALLOWLIST", "нет RP-действия/контекста")

        return FilterResult(True, "ALLOWED")
