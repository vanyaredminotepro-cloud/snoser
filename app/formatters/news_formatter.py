import html
import re


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
            return "🔼"
        if any(w in low for w in ["дорог", "строй", "инфраструкт", "завод", "фабрик", "проект"]):
            return "🏗️"
        if any(w in low for w in ["диплом", "союз", "договор", "встреч", "саммит", "переговор", "корол", "сотруднич"]):
            return "💭"
        if any(w in low for w in ["закон", "указ", "реформ", "постановлен"]):
            return "📜"
        return self.country_emoji.get(country, "💠")

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

    @staticmethod
    def _emoji_tag(emoji_symbol: str, custom_emoji_id: str | None) -> str:
        if custom_emoji_id:
            return f'<tg-emoji emoji-id="{custom_emoji_id}"></tg-emoji>'
        return emoji_symbol

    def _build_hashtags(
        self,
        source_country: str,
        text: str,
        country_hashtags: dict[str, str],
    ) -> str:
        tags: list[str] = []

        source_tag = country_hashtags.get(source_country)
        if source_tag:
            tags.append(source_tag)

        low = text.lower()
        for country, tag in country_hashtags.items():
            if country == source_country or country == "MANUAL":
                continue
            if country.lower() in low and tag not in tags:
                tags.append(tag)

        if not tags:
            tags.append("#NEWS")

        return " ".join(tags)

    def format_news(
        self,
        country: str,
        text: str,
        country_hashtags: dict[str, str],
        premium_emoji_ids: dict[str, str] | None = None,
    ) -> str:
        cleaned = self._cleanup_text(text)
        country_title, body_text = self._split_country_and_body(country, cleaned)

        emoji_symbol = self.pick_emoji(cleaned, country)
        custom_id = (premium_emoji_ids or {}).get(country)
        emoji = self._emoji_tag(emoji_symbol, custom_id)

        hashtags = self._build_hashtags(country, cleaned, country_hashtags)

        safe_country = html.escape(country_title)
        safe_body = html.escape(body_text)

        if len(body_text) > 420:
            main_raw = body_text[:240].rsplit(" ", 1)[0].strip()
            details_raw = body_text[len(main_raw):].strip(" .")
            main = html.escape(main_raw)
            details = html.escape(details_raw)
            return (
                f"<blockquote>{emoji} <b>{safe_country}</b> <i>{main}</i></blockquote>\n\n"
                f"ℹ️ <i>{details}</i>\n\n"
                f"{hashtags}"
            )

        return (
            f"<blockquote>{emoji} <b>{safe_country}</b> <i>{safe_body}</i></blockquote>\n\n"
            f"{hashtags}"
        )



def format_news_text(
    country: str,
    news_text: str,
    short_tag: str,
    country_hashtags: dict[str, str] | None = None,
) -> str:
    formatter = NewsFormatter()
    rewritten = formatter.rewrite(country, news_text)
    mapping = country_hashtags or {country: (short_tag if short_tag.startswith("#") else f"#{short_tag}")}
    return formatter.format_news(country=country, text=rewritten, country_hashtags=mapping)
