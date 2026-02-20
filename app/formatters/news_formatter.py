import html
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
        if custom_id:
            return f'<tg-emoji emoji-id="{custom_id}"></tg-emoji>'
        return self.paragraph_emoji_fallback[label]

    def _split_paragraphs(self, text: str) -> list[str]:
        base = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        return base if base else ([text.strip()] if text.strip() else [])

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

        if "теракт" in low and "#Теракт" not in tags:
            tags.append("#Теракт")
        if any(k in low for k in ["болез", "вирус", "mks20", "mks40"]):
            if "mks20" in low and "#MKS20" not in tags:
                tags.append("#MKS20")
            if "mks40" in low and "#MKS40" not in tags:
                tags.append("#MKS40")

        if not tags:
            tags.append("#РП")

        return " ".join(dict.fromkeys(tags))

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
            safe = html.escape(paragraph_body)
            if i == 0:
                numbered = re.match(r"^\s*(\d+\.[^\n]+)\s*(.*)$", paragraph_body, flags=re.S)
                if numbered:
                    lead = html.escape(numbered.group(1).strip())
                    rest = html.escape(numbered.group(2).strip())
                    safe = f"<u><b>{lead}</b></u>\n<i>{rest}</i>"
                    rendered_parts.append(f"<blockquote>{emoji} <b>{html.escape(country_title)}</b> {safe}</blockquote>")
                else:
                    rendered_parts.append(f"<blockquote>{emoji} <b>{html.escape(country_title)}</b> <i>{safe}</i></blockquote>")
            else:
                rendered_parts.append(f"{emoji} <i>{safe}</i>")

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
