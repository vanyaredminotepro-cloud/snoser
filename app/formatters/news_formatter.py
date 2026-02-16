import re


class NewsEmoji:
    default = "📰"
    economy = "💰"
    infrastructure = "🏗️"
    diplomacy = "🤝"
    reforms = "📜"


class NewsFormatter:
    country_emoji = {
        "Антония": "🟣",
        "Вилония": "🟦",
        "ТНР": "🟥",
        "Олбония": "🟩",
        "Северландия": "❄️",
        "Обоссляндия": "🔥",
        "Зитор": "⚙️",
        "Сэрландия": "🛡️",
        'ЧВК "Компф"': "🦅",
        'Орден "ГНЕВ"': "💢",
        "Лорд-протекторат": "👑",
        "ФШП": "🌴",
        "Белоярск": "🏔️",
        "Аль-Нуурия": "🌙",
        "Крелония": "🌊",
        "MANUAL": "📝",
    }

    def pick_emoji(self, text: str) -> str:
        low = text.lower()
        if any(w in low for w in ["эконом", "торгов", "сделк", "бюджет", "инвест"]):
            return NewsEmoji.economy
        if any(w in low for w in ["дорог", "строй", "инфраструкт", "завод", "фабрик", "проект"]):
            return NewsEmoji.infrastructure
        if any(w in low for w in ["диплом", "союз", "договор", "встреч", "саммит", "переговор"]):
            return NewsEmoji.diplomacy
        if any(w in low for w in ["закон", "указ", "реформ", "постановлен"]):
            return NewsEmoji.reforms
        return NewsEmoji.default

    @staticmethod
    def _cleanup_text(raw_text: str) -> str:
        text = raw_text.strip()
        text = re.sub(r"(?i)\b(важное|срочно)\s*:\s*", "", text)
        text = re.sub(r"#\w+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def rewrite(self, country: str, text: str) -> str:
        rewritten = re.sub(r"\bмы\s+([а-яa-z]+)", f"{country} \\1", text, flags=re.IGNORECASE)
        return rewritten

    @staticmethod
    def _strip_country_prefix(country: str, text: str) -> str:
        pattern = rf"^\s*[⚡️🔥📢📰]*\s*{re.escape(country)}\b[:\-\s]*"
        return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    def format_news(self, country: str, hashtag: str, text: str) -> str:
        """Formats Telegram news according to compact visual style requested by operator.

        Input:
        - country: country display name
        - hashtag: short hashtag like #OBS
        - text: source news text
        """
        cleaned = self._cleanup_text(text)
        cleaned = self._strip_country_prefix(country, cleaned)
        country_emoji = self.country_emoji.get(country, "📰")
        news_emoji = self.pick_emoji(cleaned)

        if len(cleaned) > 320:
            main = cleaned[:200].rsplit(" ", 1)[0].strip()
            details = cleaned[len(main):].strip(" .")
            return (
                f"{country_emoji} **НОВОСТЬ**\n\n"
                f"> {news_emoji} **{country}** *{main}*\n\n"
                f"ℹ️ ***Подробности:*** *{details}*\n\n"
                f"{hashtag} #Новости"
            )

        return (
            f"{country_emoji} **НОВОСТЬ**\n\n"
            f"{news_emoji} **{country}** *{cleaned}*\n\n"
            f"{hashtag} #Новости"
        )



def format_news_text(country: str, news_text: str, short_tag: str) -> str:
    """Utility function requested by user: returns formatted Telegram-ready text."""
    formatter = NewsFormatter()
    hashtag = short_tag if short_tag.startswith("#") else f"#{short_tag}"
    rewritten = formatter.rewrite(country, news_text)
    return formatter.format_news(country=country, hashtag=hashtag, text=rewritten)
