import re
from dataclasses import dataclass


@dataclass(slots=True)
class FilterResult:
    allowed: bool
    reason: str
    details: str = ""


class RPFilter:
    hashtag_translit_map = str.maketrans({
        "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E", "Ж": "ZH", "З": "Z", "И": "I", "Й": "Y",
        "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U", "Ф": "F",
        "Х": "H", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SCH", "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "YU", "Я": "YA",
        "І": "I", "Ї": "I", "Ґ": "G",
    })

    military_roots = {
        "войн", "атак", "штурм", "фронт", "войск", "укреп", "удар", "операци", "наступ", "обстрел", "боев", "воен",
        "мобилизац", "контрнаступ", "спецназ", "границ", "патрул", "дрон", "миномет", "снайпер", "рэб",
    }

    direct_war_action_roots = {
        "атак", "штурм", "наступ", "обстрел", "подрыв", "зачист", "уничтож", "бомб", "высадк", "боестолк", "удар",
    }
    evidence_roots = {"кадр", "видео", "съемк", "сним", "пруф"}

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
        "ракет", "автомат", "винтовк", "пистолет", "гранат", "нож", "автомобил", "мотоцикл", "грузовик", "автобус", "колонн",
    }

    action_roots = {
        "начал", "начина", "провод", "запуска", "сообщ", "объяв", "ввод", "созда", "откры", "усили", "расшир", "купил", "выехал", "готов",
    }

    real_world_roots = {"росси", "украин", "нато", "сша", "евросоюз", "пути", "байден", "ww2"}
    forbidden_heavy_equipment_roots = {
        "танк", "бтр", "бронетранспортер", "бронемаш", "самолет", "вертолет", "истреб", "бомбардиров",
        "линкор", "авианос", "крейсер", "эсмин", "подводн", "подлод",
    }
    forbidden_weapon_roots = {
        "ядер", "атомн", "химическ", "биолог", "газов", "лазер", "робот", "излучен", "плазм", "антиграв", "космическ", "силов",
    }
    forbidden_structure_roots = {
        "докс", "доксинг", "угроз", "свой чат", "своя валюта", "своя карта", "мультиаккаунт", "фальсификац",
    }

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

    @staticmethod
    def _extract_hashtags(text: str) -> set[str]:
        return {f"#{m.upper()}" for m in re.findall(r"#([A-Za-zА-Яа-я0-9_]{2,})", text)}

    @classmethod
    def _latinize_hashtag(cls, tag: str) -> str:
        if not tag:
            return tag
        normalized = tag.upper()
        if not normalized.startswith("#"):
            normalized = f"#{normalized}"
        return f"#{normalized[1:].translate(cls.hashtag_translit_map)}"

    @classmethod
    def _hashtag_variants(cls, tag: str) -> set[str]:
        normalized = tag.upper() if tag.startswith("#") else f"#{tag.upper()}"
        return {normalized, cls._latinize_hashtag(normalized)}

    @staticmethod
    def _extract_army_values(text: str) -> list[int]:
        values = [int(v) for v in re.findall(r"\b(\d{1,5})\s*(?:солдат|бойц|военн\w*)", text.lower())]
        return values

    def check(
        self,
        text: str,
        known_countries: set[str] | None = None,
        known_hashtags: set[str] | None = None,
    ) -> FilterResult:
        low = text.lower()
        words = self._words(low)
        rules_discussion = any(k in low for k in ["почему запрещ", "почему запрет", "обсужд", "правил", "разрешен", "запрещен"])

        if self._contains_banned_alliance_name(low):
            return FilterResult(False, "BANNED_ALLIANCE_NAME", "обнаружено запрещённое/маскируемое название")

        if (any(phrase in low for phrase in self.ooc_phrases) or self._contains_root(words, self.ooc_roots)) and not rules_discussion:
            return FilterResult(False, "OOC_META_CONTENT", "обнаружены OOC/meta маркеры")

        if not rules_discussion and self._contains_root(words, self.forbidden_heavy_equipment_roots):
            return FilterResult(False, "FORBIDDEN_HEAVY_EQUIPMENT", "обнаружены запрещённые тяжёлые системы (танки/авиация/корабли)")

        if not rules_discussion and self._contains_root(words, self.forbidden_weapon_roots):
            return FilterResult(False, "FORBIDDEN_WEAPON_TYPE", "обнаружено запрещённое оружие/технология")

        if any(token in low for token in self.forbidden_structure_roots):
            return FilterResult(False, "FORBIDDEN_STRUCTURE_OR_ABUSE", "обнаружены запрещённые действия/структуры")

        if self._contains_root(words, self.real_world_roots):
            return FilterResult(False, "REAL_WORLD_CONTENT", "обнаружены упоминания реального мира")

        if known_countries:
            declared_terms = self._extract_declared_country_terms(low)
            for declared in declared_terms:
                if declared not in known_countries:
                    return FilterResult(False, "UNKNOWN_COUNTRY_MENTIONED", f"неизвестная страна: {declared}")

        if known_hashtags:
            incoming_tags = self._extract_hashtags(text)
            normalized_known: set[str] = set()
            for tag in known_hashtags:
                normalized_known |= self._hashtag_variants(tag)

            unknown_tags = []
            for tag in incoming_tags:
                if len(tag) < 3:
                    continue
                if self._hashtag_variants(tag).isdisjoint(normalized_known):
                    unknown_tags.append(tag)
            if unknown_tags:
                return FilterResult(False, "UNKNOWN_COUNTRY_HASHTAG", f"неизвестные хештеги: {', '.join(sorted(unknown_tags)[:3])}")

        if rules_discussion:
            return FilterResult(True, "ALLOWED_RULES_DISCUSSION")

        if len(words) < 3:
            short_allow_roots = {"ракет", "автомат", "винтовк", "пистолет", "гранат", "нож", "автомобил", "мотоцикл", "грузовик", "автобус", "колонн"}
            if self._contains_root(words, short_allow_roots):
                return FilterResult(True, "ALLOWED")
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
                has_evidence = self._contains_root(words, self.evidence_roots)
                negated_evidence = bool(re.search(r"без\s+(?:кадр\w*|видео|съемк\w*)", low))
                if not has_evidence or negated_evidence:
                    return FilterResult(False, "WAR_WITHOUT_EVIDENCE", "для военных действий нужны кадры/видео")
                return FilterResult(True, "MILITARY_REVIEW_REQUIRED")
            return FilterResult(True, "MILITARY_REVIEW_REQUIRED")

        explicit_army_values = self._extract_army_values(text)
        if explicit_army_values:
            max_explicit = max(explicit_army_values)
            min_explicit = min(explicit_army_values)
            if max_explicit > 200:
                return FilterResult(False, "ARMY_LIMIT_EXCEEDED_200", "численность армии выше допустимой (50..200)")
            if min_explicit < 50:
                return FilterResult(False, "ARMY_UNREALISTIC_TOO_SMALL", "нереалистично малая численность армии (50..200)")

        if self._contains_root(words, self.action_roots) and self._sentence_count(low) >= 1:
            return FilterResult(True, "ALLOWED")

        if not self._contains_root(words, self.allow_roots):
            return FilterResult(False, "NOT_RP_NEWS_ALLOWLIST", "нет RP-действия/контекста")

        return FilterResult(True, "ALLOWED")
