import html
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
    def _split_country_and_body(country: str, text: str) -> tuple[str, str]:
        pattern = rf"^\s*{re.escape(country)}\b[:\-\s]*"
        body = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        if body:
            return country, body
        return country, text

    def format_news(self, country: str, hashtag: str, text: str) -> str:
        cleaned = self._cleanup_text(text)
        emoji = self.pick_emoji(cleaned, country)

        country_title, body_text = self._split_country_and_body(country, cleaned)
        safe_country = html.escape(country_title)
        safe_body = html.escape(body_text)

        if len(cleaned) > 420:
            main_raw = body_text[:240].rsplit(" ", 1)[0].strip()
            details_raw = body_text[len(main_raw):].strip(" .")
            main = html.escape(main_raw)
            details = html.escape(details_raw)
            return (
                f"{emoji}<b>НОВОСТЬ</b>\n\n"
                f"<blockquote>{emoji} <b>{safe_country}</b> <i>{main}</i></blockquote>\n\n"
                f"ℹ️ <b><i>Подробности:</i></b> <i>{details}</i>\n\n"
                f"{hashtag} #Новости"
            )

        return (
            f"{emoji}<b>НОВОСТЬ</b>\n\n"
            f"<blockquote>{emoji} <b>{safe_country}</b> <i>{safe_body}</i></blockquote>\n\n"
            f"{hashtag} #Новости"
        )



def format_news_text(country: str, news_text: str, short_tag: str) -> str:
    formatter = NewsFormatter()
    hashtag = short_tag if short_tag.startswith("#") else f"#{short_tag}"
    rewritten = formatter.rewrite(country, news_text)
    return formatter.format_news(country=country, hashtag=hashtag, text=rewritten)
