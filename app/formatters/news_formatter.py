import re


class NewsFormatter:
    paragraph_emoji_fallback = {
        "important": "❗️",
        "economy": "📈",
        "diplomacy": "💭",
        "warning": "⚠️",
        "map": "🌐",
        "default": "📰",
    }

    emoji_rules = {
        "economy": ["эконом", "бюджет", "инвест", "вкладывает", "финанс", "промышлен"],
        "diplomacy": ["сотруднич", "встреч", "переговор", "договор", "союз", "визит"],
        "warning": ["теракт", "болезн", "вирус", "mks20", "mks40", "чс", "угроз"],
        "map": ["карта", "map", "границ", "территор"],
        "important": ["срочно", "важно", "экстренно", "‼"],
    }

    mdv2_special = r"_*[]()~`>#+-=|{}.!"

    @classmethod
    def _escape_mdv2(cls, text: str) -> str:
        out = text
        for ch in cls.mdv2_special:
            out = out.replace(ch, f"\\{ch}")
        return out

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

    def _emoji_for_paragraph(self, paragraph: str, premium_emoji_ids: dict[str, str] | None) -> str:
        low = paragraph.lower()
        label = "default"
        for candidate, tokens in self.emoji_rules.items():
            if any(token in low for token in tokens):
                label = candidate
                break

        custom_id = (premium_emoji_ids or {}).get(label.upper()) or (premium_emoji_ids or {}).get("DEFAULT")
        fallback = self.paragraph_emoji_fallback[label]
        if custom_id:
            return f"![](tg://emoji?id={custom_id})"
        return self._escape_mdv2(fallback)

    def _split_paragraphs(self, text: str) -> list[str]:
        base = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        return base if base else ([text.strip()] if text.strip() else [])

    def _compress(self, text: str, limit: int = 700) -> str:
        if len(text) <= limit:
            return text
        cut = text[:limit].rsplit(" ", 1)[0].strip()
        return f"{cut}…"

    @staticmethod
    def _escape_tag(tag: str) -> str:
        return tag.replace("-", "\\-")

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

        return " ".join(self._escape_tag(t) for t in dict.fromkeys(tags))

    def format_news(
        self,
        country: str,
        text: str,
        country_hashtags: dict[str, list[str]],
        premium_emoji_ids: dict[str, str] | None = None,
        country_aliases: dict[str, list[str]] | None = None,
    ) -> str:
        cleaned = self._compress(self._cleanup_text(text))
        paragraphs = self._split_paragraphs(cleaned)

        rendered_parts: list[str] = []
        aliases = (country_aliases or {}).get(country, [])
        for i, paragraph in enumerate(paragraphs):
            country_title, paragraph_body = self._split_country_and_body(country, paragraph, aliases if i == 0 else None)
            emoji = self._emoji_for_paragraph(paragraph, premium_emoji_ids)
            body = self._escape_mdv2(paragraph_body)
            title = self._escape_mdv2(country_title)
            if i == 0:
                numbered = re.match(r"^\s*(\d+\.[^\n]+)\s*(.*)$", paragraph_body, flags=re.S)
                if numbered:
                    lead = self._escape_mdv2(numbered.group(1).strip())
                    rest = self._escape_mdv2(numbered.group(2).strip())
                    rendered_parts.append(f"> {emoji} *{title}* *__{lead}__*\n> _{rest}_")
                else:
                    rendered_parts.append(f"> {emoji} *{title}* _{body}_")
            else:
                rendered_parts.append(f"{emoji} _{body}_")

        hashtags = self._build_hashtags(country, cleaned, country_hashtags, country_aliases)
        return "\n\n".join(rendered_parts) + f"\n\n{hashtags}"



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
