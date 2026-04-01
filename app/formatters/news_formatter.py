import hashlib
import re

from telethon.tl.types import MessageEntityBlockquote, MessageEntityBold, MessageEntityCustomEmoji, MessageEntityItalic


class NewsFormatter:
    hashtag_translit_map = str.maketrans({
        "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E", "Ж": "ZH", "З": "Z", "И": "I", "Й": "Y",
        "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U", "Ф": "F",
        "Х": "H", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SCH", "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "YU", "Я": "YA",
        "І": "I", "Ї": "I", "Ґ": "G",
    })

    paragraph_emoji_fallback = {
        "important": "❗️",
        "economy": "📈",
        "diplomacy": "💭",
        "warning": "⚠️",
        "map": "🌐",
        "default": "👀",
    }
    _default_emoji_cursor = 0
    default_emoji_cycle = [
        "👀", "💭", "📈", "⚠️", "🌐", "❗️", "🛰️", "🏛️", "🧭", "🗞️", "📌", "🕰️", "🧱", "📣", "🛡️", "⚡", "✅", "📊", "📢",
        "🔔", "🚨", "📰", "🗳️", "🧪", "🏗️", "🧰", "🔬", "💡", "🧩", "🔗", "🪙", "🏦", "💹", "📉", "💼", "🛠️", "🚧", "🪖",
        "🧨", "🚀", "✈️", "🚁", "🛳️", "🗺️", "📍", "🧮", "📚", "🎯", "🧠", "📝", "🔍", "🔒", "🔓", "🪪", "🧾", "📦", "📨",
        "📬", "⏱️", "⌛", "🧬", "⚙️", "🧫", "🏥", "🏫", "🏭", "🌉", "🛣️", "🏘️", "🌆", "🌍", "🌎", "🌏", "🤝", "🕊️", "🎖️",
        "🏅", "🥇", "🔰", "🛟", "🧯", "🪫", "🔋", "💬", "🗣️", "🫡", "🧑‍💼", "🫱🏻‍🫲🏼", "📎", "🧷", "🧸", "🎙️", "📡",
        "📻", "📺", "🧿", "🪄", "🪧", "🪤", "🪜", "🧱", "🪵", "🪨", "⚖️", "🏛️", "🏴‍☠️", "🏳️", "🏳️‍🌈", "🏴", "🎛️", "🎚️",
        "🎞️", "🎬", "🧭", "📠", "☎️", "📞", "🗄️", "🗃️", "🗂️", "📁", "📂", "🧠", "🫀", "🫁", "🩺", "💊", "💉", "🩹",
        "🧴", "🧼", "🧹", "🧺", "🧻", "🪣", "🧰", "🔧", "🔨", "⚒️", "🪓", "⛏️", "🔩", "⚙️", "🧲", "🪫", "🔋", "💾",
        "💿", "📀", "🧮", "🛰️", "🌩️", "☀️", "🌤️", "🌧️", "⛈️", "❄️", "🔥", "🌪️", "🌊", "🧱", "🛡️", "🗝️", "🔐", "🧯",
        "🪖", "🛰️", "🛜", "🖥️", "⌨️", "🖱️", "🧑‍🔬", "🧑‍🚒", "🧑‍⚖️", "🧑‍🏫", "🧑‍🏭", "🧑‍🔧", "🧑‍🚀", "🧑‍✈️", "🧑‍⚕️",
    ]
    emoji_variants = {
        "important": [
            "❗️", "🚨", "📢", "📣", "🛎️", "🔔", "⚡", "🧨", "✅", "🎯", "📌", "📰", "🧷", "🧿", "🧭", "🗞️", "📍", "🚩",
            "📯", "🪧", "🔰", "🏁", "🏳️", "🏴",
        ],
        "economy": [
            "📈", "💰", "🏦", "⚙️", "🧾", "💹", "🪙", "🏭", "📊", "💼", "🧮", "📉", "💳", "💸", "💱", "🏗️", "🛠️", "📦",
            "🧱", "🧰", "🏬", "🏢", "🏘️", "🚚", "🛳️", "✈️",
        ],
        "diplomacy": [
            "💭", "🤝", "🕊️", "🗣️", "📜", "🏛️", "🪪", "🫱🏻‍🫲🏼", "💬", "🎙️", "📨", "📬", "🧑‍⚖️", "⚖️", "📘", "🧾",
            "🏳️", "🏴", "🪧", "🗳️", "🧑‍💼", "🧑‍🏫",
        ],
        "warning": [
            "⚠️", "🛑", "🚫", "☣️", "❌", "⛔", "🧯", "🚨", "⚡", "🪖", "🛡️", "📣", "🔔", "📢", "🔥", "💥", "🧨", "🛰️",
            "🧱", "🛜", "🩺", "🌪️", "🌊", "❄️", "⛈️",
        ],
        "map": [
            "🌐", "🗺️", "📍", "🧭", "🛰️", "🛣️", "🏞️", "🧱", "🌍", "🌎", "🌏", "📡", "🏘️", "🌉", "🏔️", "🏜️", "🏝️", "🛤️",
            "✈️", "🚁", "🛳️", "🚆", "🚧", "🛜",
        ],
        "default": default_emoji_cycle,
    }
    emoji_to_key = {
        "👀": "DEFAULT",
        "🗞️": "DEFAULT",
        "📰": "DEFAULT",
        "📌": "DEFAULT",
        "🧠": "DEFAULT",
        "🧾": "DEFAULT",
        "📝": "DEFAULT",
        "🔍": "DEFAULT",
        "💭": "DIPLOMACY",
        "🤝": "DIPLOMACY",
        "🕊️": "DIPLOMACY",
        "🗣️": "DIPLOMACY",
        "📜": "DIPLOMACY",
        "🏛️": "DIPLOMACY",
        "🫱🏻‍🫲🏼": "DIPLOMACY",
        "💬": "DIPLOMACY",
        "🎙️": "DIPLOMACY",
        "📨": "DIPLOMACY",
        "📬": "DIPLOMACY",
        "🗳️": "DIPLOMACY",
        "⚖️": "DIPLOMACY",
        "📈": "ECONOMY",
        "💰": "ECONOMY",
        "🏦": "ECONOMY",
        "🪙": "ECONOMY",
        "💹": "ECONOMY",
        "📊": "ECONOMY",
        "📉": "ECONOMY",
        "💼": "ECONOMY",
        "🏭": "ECONOMY",
        "💳": "ECONOMY",
        "💸": "ECONOMY",
        "💱": "ECONOMY",
        "🧮": "ECONOMY",
        "⚠️": "WARNING",
        "⚡": "WARNING",
        "⚡️": "WARNING",
        "🚨": "WARNING",
        "🛑": "WARNING",
        "🚫": "WARNING",
        "☣️": "WARNING",
        "❌": "WARNING",
        "⛔": "WARNING",
        "🧯": "WARNING",
        "🪖": "WARNING",
        "🛡️": "WARNING",
        "🔥": "WARNING",
        "💥": "WARNING",
        "🧨": "WARNING",
        "🌪️": "WARNING",
        "🌊": "WARNING",
        "❄️": "WARNING",
        "⛈️": "WARNING",
        "🌐": "MAP",
        "🗺️": "MAP",
        "📍": "MAP",
        "🧭": "MAP",
        "🛰️": "MAP",
        "🌍": "MAP",
        "🌎": "MAP",
        "🌏": "MAP",
        "📡": "MAP",
        "🏔️": "MAP",
        "🏜️": "MAP",
        "🏝️": "MAP",
        "🛤️": "MAP",
        "🚁": "MAP",
        "🛳️": "MAP",
        "🚆": "MAP",
        "🚧": "MAP",
        "❗️": "IMPORTANT",
        "❕": "IMPORTANT",
        "‼️": "IMPORTANT",
        "📢": "IMPORTANT",
        "📣": "IMPORTANT",
        "🔔": "IMPORTANT",
        "🚩": "IMPORTANT",
        "📯": "IMPORTANT",
        "🔰": "IMPORTANT",
        "🏁": "IMPORTANT",
        "✅": "IMPORTANT",
        "🎯": "IMPORTANT",
    }
    for _label, _emojis in emoji_variants.items():
        _semantic_key = "DEFAULT" if _label == "default" else _label.upper()
        for _emoji in _emojis:
            emoji_to_key.setdefault(_emoji, _semantic_key)


    emoji_rules = {
        "economy": [
            "эконом", "бюджет", "инвест", "вкладывает", "финанс", "промышлен", "фабрик", "завод", "налог", "рынок", "бирж",
            "акци", "кредит", "дотац", "субсид", "тариф", "логист", "контракт", "поставк", "добыч", "ресурс", "энергет",
            "банков", "прибыл", "убыт", "капитал", "инфляц", "монетар", "бизнес", "предприяти", "цех", "стройк", "инфраструкт",
            "порт", "транспорт", "сырь", "импорт", "экспорт", "торгов", "грант", "фонд", "производ", "модернизац", "технопарк",
        ],
        "diplomacy": [
            "сотруднич", "встреч", "переговор", "договор", "союз", "визит", "протокол", "дипломат", "меморандум", "нота",
            "консуль", "посоль", "делегац", "саммит", "коммюник", "ратифиц", "коалиц", "партнер", "миротвор", "урегулир",
            "арбитраж", "медиац", "диалог", "форум", "конференц", "конвенц", "декларац", "межгосудар", "межправительств",
            "резолюц", "мандат", "мисси", "альянс", "пакт", "ненападен", "координац", "взаимопомощ", "граница согласован",
        ],
        "warning": [
            "теракт", "болезн", "вирус", "mks20", "mks40", "чс", "угроз", "санкц", "обстрел", "штурм", "кризис", "эвакуац",
            "ракет", "пехот", "перебазир", "аванпост", "комплекс", "гарнизон", "артиллери", "дивизион", "удар", "взрыв",
            "подрыв", "диверс", "дрон", "беспилот", "тревог", "карантин", "блокад", "штаб", "комендант", "кибератак",
            "инцидент", "потер", "разрушен", "перехват", "минирован", "наступлен", "контрнаступлен", "прорыв", "осада",
            "катастроф", "шторм", "наводнен", "пожар", "лавин", "эпидем", "паник", "терак", "ранен", "жертв",
        ],
        "map": [
            "карта", "map", "границ", "территор", "колонизац", "захват", "регион", "маршрут", "сектор", "квадрат", "зона",
            "координат", "географ", "рубеж", "плацдарм", "узел", "коридор", "погран", "берег", "акватор", "провинц", "округ",
            "район", "трасс", "магистрал", "топограф", "дислокац", "локац", "периметр", "фронт", "позици", "дистанц",
        ],
        "important": [
            "срочно", "важно", "экстренно", "‼", "официально", "подтверждено", "подтверждаем", "внимание", "немедлен",
            "безотлагат", "приоритет", "критич", "ключев", "главн", "опубликован указ", "обязательно", "объявлено",
            "неотложн", "принято решение", "вступает в силу", "немедленно", "с сегодняшнего дня", "с текущего момента",
        ],
    }
    verb_replacements = {
        "начинаем": "начинает",
        "готовим": "готовит",
        "планируем": "планирует",
        "объявляем": "объявляет",
        "сообщаем": "сообщает",
        "заявляем": "заявляет",
        "продолжаем": "продолжает",
        "завершаем": "завершает",
        "приступаем": "приступает",
        "усиливаем": "усиливает",
        "запускаем": "запускает",
        "проводим": "проводит",
        "вводим": "вводит",
        "выпускаем": "выпускает",
        "разрабатываем": "разрабатывает",
        "подписываем": "подписывает",
        "перебазируем": "перебазирует",
        "размещаем": "размещает",
        "переносим": "переносит",
        "строим": "строит",
        "открываем": "открывает",
        "обновляем": "обновляет",
        "модернизируем": "модернизирует",
        "укрепляем": "укрепляет",
        "формируем": "формирует",
        "перевооружаем": "перевооружает",
        "утверждаем": "утверждает",
        "назначаем": "назначает",
        "реформируем": "реформирует",
        "финансируем": "финансирует",
        "инвестируем": "инвестирует",
        "тестируем": "тестирует",
        "испытываем": "испытывает",
        "публикуем": "публикует",
        "фиксируем": "фиксирует",
        "контролируем": "контролирует",
        "координируем": "координирует",
        "направляем": "направляет",
        "расширяем": "расширяет",
        "согласовываем": "согласовывает",
        "подтверждаем": "подтверждает",
        "закупаем": "закупает",
        "поставляем": "поставляет",
        "передаем": "передает",
        "обеспечиваем": "обеспечивает",
        "увеличиваем": "увеличивает",
        "снижаем": "снижает",
        "повышаем": "повышает",
        "оптимизируем": "оптимизирует",
        "автоматизируем": "автоматизирует",
        "цифровизируем": "цифровизирует",
        "кооперируемся": "кооперируется",
        "восстанавливаем": "восстанавливает",
        "ликвидируем": "ликвидирует",
        "локализуем": "локализует",
        "эвакуируем": "эвакуирует",
        "блокируем": "блокирует",
        "патрулируем": "патрулирует",
        "охраняем": "охраняет",
        "доставляем": "доставляет",
        "организуем": "организует",
        "переоснащаем": "переоснащает",
        "снабжаем": "снабжает",
        "стабилизируем": "стабилизирует",
        "докладываем": "докладывает",
        "отчитываемся": "отчитывается",
        "проверяем": "проверяет",
        "верифицируем": "верифицирует",
        "запрещаем": "запрещает",
        "разрешаем": "разрешает",
        "созываем": "созывает",
        "встречаемся": "встречается",
        "согласуем": "согласует",
        "реализуем": "реализует",
        "выполняем": "выполняет",
        "внедряем": "внедряет",
        "трансформируем": "трансформирует",
        "пересматриваем": "пересматривает",
        "уточняем": "уточняет",
        "регламентируем": "регламентирует",
        "координируем": "координирует",
        "переходим": "переходит",
        "возобновляем": "возобновляет",
        "прекращаем": "прекращает",
        "замораживаем": "замораживает",
        "размораживаем": "размораживает",
        "поддерживаем": "поддерживает",
        "инициируем": "инициирует",
        "учреждаем": "учреждает",
        "созываем": "созывает",
        "ратифицируем": "ратифицирует",
        "денонсируем": "денонсирует",
        "гармонизируем": "гармонизирует",
        "кодифицируем": "кодифицирует",
        "стандартизируем": "стандартизирует",
        "нормируем": "нормирует",
        "калибруем": "калибрует",
        "перераспределяем": "перераспределяет",
        "компенсируем": "компенсирует",
        "страхуем": "страхует",
        "гарантируем": "гарантирует",
        "утепляем": "утепляет",
        "ремонтируем": "ремонтирует",
        "реставрируем": "реставрирует",
        "достраиваем": "достраивает",
        "запечатываем": "запечатывает",
        "распечатываем": "распечатывает",
        "транспортируем": "транспортирует",
        "маркируем": "маркирует",
        "переименовываем": "переименовывает",
        "утончняем": "уточняет",
        "объединяем": "объединяет",
        "разделяем": "разделяет",
        "создаем": "создает",
        "закрепляем": "закрепляет",
        "подготавливаем": "подготавливает",
        "активируем": "активирует",
        "деактивируем": "деактивирует",
        "погашаем": "погашает",
        "начисляем": "начисляет",
        "рефинансируем": "рефинансирует",
        "рассчитываем": "рассчитывает",
        "инвентаризируем": "инвентаризирует",
        "оцифровываем": "оцифровывает",
        "архивируем": "архивирует",
        "публикуем": "публикует",
        "обнародуем": "обнародует",
        "анонсируем": "анонсирует",
        "презентуем": "презентует",
        "обучаем": "обучает",
        "аттестуем": "аттестует",
        "сертифицируем": "сертифицирует",
        "лицензируем": "лицензирует",
    }
    signature_patterns = [
        re.compile(r"^\s*[—-]\s*(командован|пресс-служб).*$", re.IGNORECASE),
        re.compile(r"^\s*с уважением.*$", re.IGNORECASE),
        re.compile(r"^\s*©.*$", re.IGNORECASE),
        re.compile(r"^\s*#\w+.*$", re.IGNORECASE),
    ]
    emoji_strip_re = re.compile(
        "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]+",
        flags=re.UNICODE,
    )

    @staticmethod
    def _utf16_len(value: str) -> int:
        return len(value.encode("utf-16-le")) // 2

    def _cleanup_text(self, raw_text: str) -> tuple[str, list[str]]:
        tags = [f"#{tag.upper()}" for tag in re.findall(r"#([A-Za-zА-Яа-я0-9_]+)", raw_text)]
        text = self.emoji_strip_re.sub("", raw_text).strip()
        text = re.sub(r"(?i)\b(важное|срочно)\s*:\s*", "", text)
        lines = [ln.rstrip() for ln in text.splitlines()]
        filtered: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if any(p.match(stripped) for p in self.signature_patterns):
                continue
            stripped = re.sub(r"^[—-]+\s*", "", stripped)
            stripped = re.sub(r"\s+[—-]\s+(командован|пресс-служб).*$", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s+[—-]\s+(?=(командован|пресс-служб).*)$", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s+[—-]\s+", " ", stripped)
            stripped = re.sub(r"#\w+", "", stripped)
            stripped = re.sub(r"^[^\w#А-Яа-яЁё]+", "", stripped)
            if not stripped.strip():
                continue
            filtered.append(stripped)
        text = "\n".join(filtered)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(^|\n)\s*[—-]+\s*", r"\1", text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        return text, list(dict.fromkeys(tags))

    def rewrite(self, country: str, text: str) -> str:
        out = text
        country_prep = self._country_prepositional(country)
        out = re.sub(r"(?i)\bв\s+нашей\s+стране\b", f"в {country_prep}", out)
        out = re.sub(r"(?i)\bв\s+нашем\s+государстве\b", f"в {country_prep}", out)
        out = re.sub(r"(?i)\bв\s+нашей\s+республике\b", f"в {country_prep}", out)
        out = re.sub(r"(?i)\bнаша\s+страна\b", country, out)
        out = re.sub(r"(?i)\bнаше\s+государство\b", country, out)

        if out.strip().lower().startswith("мы "):
            return out
        if out.lower().startswith(country.lower()):
            return out
        return re.sub(r"\bмы\s+([а-яa-z]+)", f"{country} \\1", out, flags=re.IGNORECASE)

    @staticmethod
    def _country_prepositional(country: str) -> str:
        low = country.lower()
        if low.endswith("ия"):
            return f"{country[:-2]}ии"
        if low.endswith("а"):
            return f"{country[:-1]}е"
        if low.endswith("я"):
            return f"{country[:-1]}е"
        if low.endswith("ь"):
            return f"{country[:-1]}и"
        return country

    @staticmethod
    def _normalize(s: str) -> str:
        return s.lower().replace("ё", "е").strip()

    def _split_country_and_body(self, country: str, text: str, aliases: list[str] | None = None) -> tuple[str, str]:
        names = [country] + (aliases or [])
        body = text.strip()
        for name in names:
            n = re.escape(name)
            body = re.sub(rf"^\s*{n}\b[:\-\s]*", "", body, flags=re.IGNORECASE)
        return (country, body) if body else (country, text.strip())

    def _body_mentions_country(self, body: str, country: str, aliases: list[str] | None = None) -> bool:
        low_body = self._normalize(body)
        probes: set[str] = {self._normalize(country)}
        for alias in aliases or []:
            probes.add(self._normalize(alias))

        country_low = self._normalize(country)
        if len(country_low) > 4:
            probes.add(country_low[:-1])
            probes.add(country_low[:-2])
            if country_low.endswith("ия"):
                probes.add(f"{country_low[:-2]}ии")
                probes.add(f"{country_low[:-2]}ию")

        for probe in probes:
            if len(probe) >= 4 and probe in low_body:
                return True
        return False

    def _contains_country_reference(self, text: str, country: str, aliases: list[str] | None = None) -> bool:
        low = self._normalize(text)
        probes = [country, *(aliases or [])]
        for probe in probes:
            p = self._normalize(probe)
            if not p:
                continue
            if p in low:
                return True
            if p.endswith(("ия", "а", "я", "ь")):
                stem = p[:-1]
                if len(stem) >= 4 and stem in low:
                    return True
        return False

    def _normalize_sentence_case(self, text: str) -> str:
        if not text:
            return text
        parts = re.split(r"([.!?]\s+)", text)
        out: list[str] = []
        for part in parts:
            if not part:
                continue
            if re.fullmatch(r"[.!?]\s+", part):
                out.append(part)
                continue
            tokens = part.split()
            if not tokens:
                out.append(part)
                continue
            normalized = []
            for idx, tok in enumerate(tokens):
                if tok.startswith("#") or tok.isupper():
                    normalized.append(tok)
                    continue
                if idx == 0:
                    normalized.append(tok[:1].upper() + tok[1:].lower())
                else:
                    normalized.append(tok.lower())
            out.append(" ".join(normalized))
        return "".join(out).strip()

    def _subjectify_if_possible(self, country: str, text: str, aliases: list[str] | None = None) -> tuple[str, str]:
        compact = text.strip()
        if not compact or compact.lower().startswith("мы "):
            return country, compact
        verb_pattern = "|".join(map(re.escape, self.verb_replacements.keys()))
        m = re.match(rf"^([^.!?\n]{{2,80}}?)\s+({verb_pattern})\b(.*)$", compact, flags=re.IGNORECASE)
        if not m:
            return self._split_country_and_body(country, compact, aliases)
        subject_raw = m.group(1).strip(" ,:;")
        verb_raw = m.group(2).lower()
        rest = m.group(3).strip()
        if subject_raw.lower() in {"мы", "я"}:
            return country, compact
        if len(subject_raw.split()) > 8:
            return self._split_country_and_body(country, compact, aliases)
        verb = self.verb_replacements.get(verb_raw, verb_raw)
        body = f"{verb} {rest}".strip()
        body = self._normalize_sentence_case(body)
        return subject_raw, body

    @staticmethod
    def _is_feminine_subject(subject: str) -> bool:
        low = subject.strip().lower()
        return low.endswith(("ия", "а", "я", "ь"))

    def _normalize_official_body(self, subject: str, body: str) -> str:
        compact = body.strip()
        if not compact:
            return compact

        feminine = self._is_feminine_subject(subject)
        created_form = "создала" if feminine else "создал"

        if re.search(r"(?i)\bофициально\b", compact):
            compact = re.sub(r"(?i)^мы\s+(?=официально\s+созд)", "", compact).strip()
            compact = re.sub(r"(?i)\bсоздали\b", created_form, compact, count=1)
            compact = re.sub(r"(?i)\bсозда[её]м\b", created_form, compact, count=1)
            compact = re.sub(r"(?i)\bсоздает\b", created_form, compact, count=1)
        else:
            compact = re.sub(r"(?i)\bсоздали\b", "создает", compact, count=1)
            compact = re.sub(r"(?i)\bсозда[её]м\b", "создает", compact, count=1)

        return self._normalize_sentence_case(compact)

    def _emoji_label(self, paragraph: str) -> str:
        low = paragraph.lower()
        for candidate, tokens in self.emoji_rules.items():
            if any(token in low for token in tokens):
                return candidate
        return "default"

    @staticmethod
    def _stable_pick(items: list[str], seed: str) -> str:
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % len(items)
        return items[idx]

    def _emoji_char_and_id(self, paragraph: str, premium_emoji_ids: dict[str, str] | None) -> tuple[str, int | None]:
        label = self._emoji_label(paragraph)
        variants = self.emoji_variants.get(label, [self.paragraph_emoji_fallback[label]])
        if label == "default" and variants:
            non_eye = [e for e in variants if e != "👀"] or variants
            idx = NewsFormatter._default_emoji_cursor % len(non_eye)
            fallback = non_eye[idx]
            NewsFormatter._default_emoji_cursor += 1
        else:
            fallback = self._stable_pick(variants, paragraph)
        emoji_key = self.emoji_to_key.get(fallback, label.upper())
        custom_id_raw = (premium_emoji_ids or {}).get(emoji_key) or (premium_emoji_ids or {}).get("DEFAULT")
        return fallback, int(custom_id_raw) if custom_id_raw else None

    @staticmethod
    def _split_headline_details(text: str) -> tuple[str, str]:
        chunks = [c.strip() for c in re.split(r"\n\n+", text) if c.strip()]
        if len(chunks) >= 2:
            return chunks[0], " ".join(chunks[1:]).strip()
        one = chunks[0] if chunks else text.strip()
        sentence = re.split(r"(?<=[.!?])\s+", one, maxsplit=1)
        if len(sentence) == 2:
            return sentence[0].strip(), sentence[1].strip()
        return one, ""

    def _compress(self, text: str, limit: int = 700) -> str:
        if len(text) <= limit:
            return text
        cut = text[:limit].rsplit(" ", 1)[0].strip()
        return f"{cut}…"

    def _build_hashtags(
        self,
        source_country: str,
        text: str,
        tags_map: dict[str, list[str]],
        aliases_map: dict[str, list[str]] | None = None,
    ) -> str:
        low = self._normalize(text)
        tags: list[str] = []
        if source_country in tags_map and tags_map[source_country]:
            tags.append(tags_map[source_country][0])

        aliases_map = aliases_map or {}
        for country, ctags in tags_map.items():
            if country == source_country:
                continue
            probes = [country] + aliases_map.get(country, [])
            if any(self._normalize(p) in low for p in probes):
                for tag in ctags:
                    if tag not in tags:
                        tags.append(tag)

        if "теракт" in low and "#TERROR" not in tags:
            tags.append("#TERROR")
        if any(k in low for k in ["болез", "вирус", "mks20", "mks40"]):
            if "mks20" in low and "#MKS20" not in tags:
                tags.append("#MKS20")
            if "mks40" in low and "#MKS40" not in tags:
                tags.append("#MKS40")

        if not tags:
            tags.append("#RP")

        return " ".join(dict.fromkeys(tags))

    @classmethod
    def _latinize_hashtag(cls, tag: str) -> str:
        normalized = tag.strip().upper()
        if not normalized:
            return normalized
        if not normalized.startswith("#"):
            normalized = f"#{normalized}"
        return f"#{normalized[1:].translate(cls.hashtag_translit_map)}"

    @classmethod
    def _canonical_hashtag_map(cls, tags_map: dict[str, list[str]]) -> dict[str, str]:
        out: dict[str, str] = {}
        for values in tags_map.values():
            if not values:
                continue
            canonical = str(values[0]).strip().upper()
            if not canonical.startswith("#"):
                canonical = f"#{canonical}"
            out[canonical] = canonical
            out[cls._latinize_hashtag(canonical)] = canonical
            for raw in values[1:]:
                alias = str(raw).strip().upper()
                if not alias:
                    continue
                if not alias.startswith("#"):
                    alias = f"#{alias}"
                out[alias] = canonical
                out[cls._latinize_hashtag(alias)] = canonical
        return out

    @classmethod
    def _canonicalize_explicit_tags(cls, tags: list[str], tags_map: dict[str, list[str]]) -> list[str]:
        aliases = cls._canonical_hashtag_map(tags_map)
        normalized: list[str] = []
        for raw in tags:
            tag = raw.strip().upper()
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = f"#{tag}"
            canonical = aliases.get(tag) or aliases.get(cls._latinize_hashtag(tag)) or cls._latinize_hashtag(tag)
            normalized.append(canonical)
        return list(dict.fromkeys(normalized))

    def format_news_entities(
        self,
        country: str,
        text: str,
        country_hashtags: dict[str, list[str]],
        premium_emoji_ids: dict[str, str] | None = None,
        country_aliases: dict[str, list[str]] | None = None,
    ) -> tuple[str, list]:
        cleaned, explicit_tags = self._cleanup_text(text)
        explicit_tags = self._canonicalize_explicit_tags(explicit_tags, country_hashtags)
        cleaned = self._compress(cleaned)
        aliases = (country_aliases or {}).get(country, [])
        subject, body = self._subjectify_if_possible(country, cleaned, aliases)
        body = self._normalize_official_body(subject, body)
        if self._body_mentions_country(body, country, aliases):
            subject = ""
        headline, details = self._split_headline_details(body)
        include_subject = not self._contains_country_reference(body, country, aliases)
        visible_subject = subject if include_subject else ""

        emoji_char, emoji_id = self._emoji_char_and_id(headline, premium_emoji_ids)

        prefix = f"{emoji_char} {visible_subject}".strip()
        lines = [f"{prefix} {headline}".strip()]
        if details:
            lines.append(details.strip())

        hashtags = self._build_hashtags(country, cleaned, country_hashtags, country_aliases)
        if explicit_tags:
            hashtags = " ".join(dict.fromkeys(explicit_tags + hashtags.split()))
        full_text = "\n\n".join(lines) + f"\n\n{hashtags}"

        entities: list = []
        # line 1 entities
        l1 = lines[0]

        # quote-style rendering for the headline line
        entities.append(MessageEntityBlockquote(offset=0, length=self._utf16_len(l1)))
        if emoji_id is not None:
            entities.append(MessageEntityCustomEmoji(offset=0, length=self._utf16_len(emoji_char), document_id=emoji_id))

        country_start = self._utf16_len(f"{emoji_char} ")
        country_len = self._utf16_len(visible_subject)
        if country_len > 0:
            entities.append(MessageEntityBold(offset=country_start, length=country_len))

        body_start = self._utf16_len(f"{prefix} ")
        body_len = self._utf16_len(l1) - body_start
        if body_len > 0:
            entities.append(MessageEntityItalic(offset=body_start, length=body_len))

        if details:
            prefix_units = self._utf16_len(l1 + "\n\n")
            detail_len = self._utf16_len(details)
            entities.append(MessageEntityBold(offset=prefix_units, length=detail_len))
            entities.append(MessageEntityItalic(offset=prefix_units, length=detail_len))

        return full_text, entities

    def format_news(
        self,
        country: str,
        text: str,
        country_hashtags: dict[str, list[str]],
        premium_emoji_ids: dict[str, str] | None = None,
        country_aliases: dict[str, list[str]] | None = None,
    ) -> str:
        rendered, _ = self.format_news_entities(
            country=country,
            text=text,
            country_hashtags=country_hashtags,
            premium_emoji_ids=premium_emoji_ids,
            country_aliases=country_aliases,
        )
        return rendered


def format_news_text(
    country: str,
    news_text: str,
    short_tag: str,
    country_hashtags: dict[str, list[str]] | None = None,
) -> str:
    formatter = NewsFormatter()
    rewritten = formatter.rewrite(country, news_text)
    mapping = country_hashtags or {country: [short_tag if short_tag.startswith("#") else f"#{short_tag}"]}
    return formatter.format_news(country=country, text=rewritten, country_hashtags=mapping)
