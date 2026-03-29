import hashlib
import re

from telethon.tl.types import MessageEntityBlockquote, MessageEntityBold, MessageEntityCustomEmoji, MessageEntityItalic


class NewsFormatter:
    paragraph_emoji_fallback = {
        "important": "❗️",
        "economy": "📈",
        "diplomacy": "💭",
        "warning": "⚠️",
        "map": "🌐",
        "default": "👀",
    }
    default_emoji_cycle = ["👀", "💭", "📈", "⚠️", "🌐", "❗️", "🛰️", "🏛️", "🧭", "🗞️"]
    emoji_variants = {
        "important": ["❗️", "🚨", "📢"],
        "economy": ["📈", "💰", "🏦", "⚙️"],
        "diplomacy": ["💭", "🤝", "🕊️", "🗣️"],
        "warning": ["⚠️", "🛑", "🚫", "☣️"],
        "map": ["🌐", "🗺️", "📍", "🧭"],
        "default": default_emoji_cycle,
    }
    emoji_to_key = {
        "👀": "DEFAULT",
        "💭": "DIPLOMACY",
        "📈": "ECONOMY",
        "⚠️": "WARNING",
        "🌐": "MAP",
        "❗️": "IMPORTANT",
    }


    emoji_rules = {
        "economy": ["эконом", "бюджет", "инвест", "вкладывает", "финанс", "промышлен", "фабрик", "завод"],
        "diplomacy": ["сотруднич", "встреч", "переговор", "договор", "союз", "визит"],
        "warning": ["теракт", "болезн", "вирус", "mks20", "mks40", "чс", "угроз", "санкц", "обстрел", "штурм"],
        "map": ["карта", "map", "границ", "территор", "колонизац", "захват"],
        "important": ["срочно", "важно", "экстренно", "‼"],
    }

    @staticmethod
    def _utf16_len(value: str) -> int:
        return len(value.encode("utf-16-le")) // 2

    @staticmethod
    def _cleanup_text(raw_text: str) -> str:
        text = raw_text.strip()
        text = re.sub(r"(?i)\b(важное|срочно)\s*:\s*", "", text)
        text = re.sub(r"#\w+", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        return text

    def rewrite(self, country: str, text: str) -> str:
        if text.lower().startswith(country.lower()):
            return text
        return re.sub(r"\bмы\s+([а-яa-z]+)", f"{country} \\1", text, flags=re.IGNORECASE)

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

    def format_news_entities(
        self,
        country: str,
        text: str,
        country_hashtags: dict[str, list[str]],
        premium_emoji_ids: dict[str, str] | None = None,
        country_aliases: dict[str, list[str]] | None = None,
    ) -> tuple[str, list]:
        cleaned = self._compress(self._cleanup_text(text))
        aliases = (country_aliases or {}).get(country, [])
        _, body = self._split_country_and_body(country, cleaned, aliases)
        headline, details = self._split_headline_details(body)

        emoji_char, emoji_id = self._emoji_char_and_id(headline, premium_emoji_ids)

        lines = [f"{emoji_char}{country} {headline}".strip()]
        if details:
            lines.append(details.strip())

        hashtags = self._build_hashtags(country, cleaned, country_hashtags, country_aliases)
        full_text = "\n\n".join(lines) + f"\n\n{hashtags}"

        entities: list = []
        # line 1 entities
        l1 = lines[0]

        # quote-style rendering for the headline line
        entities.append(MessageEntityBlockquote(offset=0, length=self._utf16_len(l1)))
        if emoji_id is not None:
            entities.append(MessageEntityCustomEmoji(offset=0, length=self._utf16_len(emoji_char), document_id=emoji_id))

        country_start = self._utf16_len(emoji_char)
        country_len = self._utf16_len(country)
        if country_len > 0:
            entities.append(MessageEntityBold(offset=country_start, length=country_len))

        body_start = self._utf16_len(f"{emoji_char}{country} ")
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
