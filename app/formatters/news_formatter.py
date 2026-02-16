import re


class PremiumNewsEmoji:
    default = "💠"
    economy = "🔼"
    infrastructure = "🏗️"
    diplomacy = "💭"
    reforms = "📜"


class NewsFormatter:
    country_emoji = {
        "Антония": "💭",
        "Вилония": "🔷",
        "ТНР": "🛡️",
        "Олбония": "👑",
        "Северландия": "❄️",
        "Обоссляндия": "🔥",
        "Зитор": "⚙️",
        "Сэрландия": "🏰",
        'ЧВК "Компф"': "🦅",
        'Орден "ГНЕВ"': "💢",
        "Лорд-протекторат": "👑",
        "ФШП": "🌴",
        "Белоярск": "🏔️",
        "Аль-Нуурия": "🌙",
        "Крелония": "🌊",
        "MANUAL": "📝",
    }

    def pick_emoji(self, text: str, country: str) -> str:
        low = text.lower()
        if any(w in low for w in ["эконом", "торгов", "сделк", "бюджет", "инвест", "вкладывает"]):
            return PremiumNewsEmoji.economy
        if any(w in low for w in ["дорог", "строй", "инфраструкт", "завод", "фабрик", "проект"]):
            return PremiumNewsEmoji.infrastructure
        if any(w in low for w in ["диплом", "союз", "договор", "встреч", "саммит", "переговор", "корол"]):
            return PremiumNewsEmoji.diplomacy
        if any(w in low for w in ["закон", "указ", "реформ", "постановлен"]):
            return PremiumNewsEmoji.reforms
        return self.country_emoji.get(country, PremiumNewsEmoji.default)

    @staticmethod
    def _cleanup_text(raw_text: str) -> str:
        text = raw_text.strip()
        text = re.sub(r"(?i)\b(важное|срочно)\s*:\s*", "", text)
        text = re.sub(r"#\w+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def rewrite(self, country: str, text: str) -> str:
        return re.sub(r"\bмы\s+([а-яa-z]+)", f"{country} \\1", text, flags=re.IGNORECASE)

    @staticmethod
    def _strip_country_prefix(country: str, text: str) -> str:
        pattern = rf"^\s*[⚡️🔥📢📰💭🔼🏗️📜💠]*\s*{re.escape(country)}\b[:\-\s]*"
        stripped = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        return stripped if stripped else text

    def format_news(self, country: str, hashtag: str, text: str) -> str:
        cleaned = self._cleanup_text(text)
        cleaned = self._strip_country_prefix(country, cleaned)
        emoji = self.pick_emoji(cleaned, country)

        if len(cleaned) > 420:
            main = cleaned[:240].rsplit(" ", 1)[0].strip()
            details = cleaned[len(main):].strip(" .")
            return f"{emoji}{main}\n\n▫️*{details}*\n\n{hashtag}"

        return f"{emoji}{cleaned}\n\n{hashtag}"



def format_news_text(country: str, news_text: str, short_tag: str) -> str:
    formatter = NewsFormatter()
    hashtag = short_tag if short_tag.startswith("#") else f"#{short_tag}"
    rewritten = formatter.rewrite(country, news_text)
    return formatter.format_news(country=country, hashtag=hashtag, text=rewritten)
