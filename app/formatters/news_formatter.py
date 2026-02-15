import re


class NewsEmoji:
    default = "📰"
    economy = "💰"
    infrastructure = "🏗️"
    diplomacy = "🤝"
    reforms = "📜"


class NewsFormatter:
    def pick_emoji(self, text: str) -> str:
        low = text.lower()
        if any(w in low for w in ["эконом", "торгов", "сделк"]):
            return NewsEmoji.economy
        if any(w in low for w in ["дорог", "строй", "инфраструкт", "завод", "фабрик"]):
            return NewsEmoji.infrastructure
        if any(w in low for w in ["диплом", "союз", "договор"]):
            return NewsEmoji.diplomacy
        if any(w in low for w in ["закон", "указ", "реформ"]):
            return NewsEmoji.reforms
        return NewsEmoji.default

    def rewrite(self, country: str, text: str) -> str:
        rewritten = re.sub(r"\bмы\s+([а-яa-z]+)", f"{country} \\1", text, flags=re.IGNORECASE)
        return rewritten

    def format_news(self, country: str, hashtag: str, text: str) -> str:
        cleaned = " ".join(text.split())
        emoji = self.pick_emoji(cleaned)
        short = cleaned[:200] + ("..." if len(cleaned) > 200 else "")
        return (
            f"👀 **{country.upper()}** *новость* {emoji}\n\n"
            f"✔️ *{short}*\n\n"
            f"***Важное:*** *{cleaned}*\n\n"
            f"{hashtag}"
        )
