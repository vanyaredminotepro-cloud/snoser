import re
from aiogram.types import MessageEntity


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



    def _starts_with_country(self, text: str, country: str, aliases: list[str] | None = None) -> bool:
        probe_text = self._normalize(text)
        probes = [country] + (aliases or [])
        return any(probe_text.startswith(self._normalize(name)) for name in probes if name)

    def _emoji_label(self, paragraph: str) -> str:
        low = paragraph.lower()
        label = "default"
        for candidate, tokens in self.emoji_rules.items():
            if any(token in low for token in tokens):
                label = candidate
                break
        return label

    def _emoji_char_and_id(self, paragraph: str, premium_emoji_ids: dict[str, str] | None) -> tuple[str, str | None]:
        label = self._emoji_label(paragraph)
        custom_id = (premium_emoji_ids or {}).get(label.upper()) or (premium_emoji_ids or {}).get("DEFAULT")
        fallback = self.paragraph_emoji_fallback[label]
        return fallback, custom_id

    @staticmethod
    def _remove_water(text: str) -> str:
        patterns = [
            r"(?i)\bкак известно\b",
            r"(?i)\bследует отметить\b",
            r"(?i)\bпо предварительным данным\b",
            r"(?i)\bв рамках\b",
            r"(?i)\bв свою очередь\b",
            r"(?i)\bна данный момент\b",
            r"(?i)\bсудя по всему\b",
        ]
        compact = text
        for ptn in patterns:
            compact = re.sub(ptn, "", compact)
        compact = re.sub(r"\s{2,}", " ", compact)
        return compact.strip(" ,")

    def _split_paragraphs(self, text: str) -> list[str]:
        base = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
        return base if base else ([text.strip()] if text.strip() else [])

    def _compress(self, text: str, limit: int = 1200) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact

        sentence_cut = compact[:limit]
        sentence_boundary = max(sentence_cut.rfind(". "), sentence_cut.rfind("! "), sentence_cut.rfind("? "))
        if sentence_boundary >= int(limit * 0.5):
            return f"{sentence_cut[:sentence_boundary + 1].strip()}…"

        word_cut = sentence_cut.rsplit(" ", 1)[0].strip()
        return f"{(word_cut or sentence_cut).strip()}…"

    def _smart_summary(self, text: str, limit: int = 260) -> str:
        cleaned = self._remove_water(re.sub(r"\s+", " ", text).strip())
        if len(cleaned) <= limit:
            return cleaned

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
        if not sentences:
            return self._compress(cleaned, limit)

        first = sentences[0]
        scored: list[tuple[int, str]] = []
        for sentence in sentences[1:]:
            score = 0
            if re.search(r"\d", sentence):
                score += 2
            if any(k in sentence.lower() for k in ["погиб", "ранен", "подпис", "встрет", "бюджет", "санкц", "договор", "чс", "атака"]):
                score += 2
            if len(sentence) > 40:
                score += 1
            scored.append((score, sentence))

        best = max(scored, key=lambda x: x[0])[1] if scored else ""
        summary = first if not best else f"{first} {best}"
        return self._compress(summary, limit)

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
    ) -> tuple[str, list[MessageEntity]]:
        cleaned = self._remove_water(self._cleanup_text(text))
        concise = self._compress(cleaned)
        paragraphs = self._split_paragraphs(concise)

        entities: list[MessageEntity] = []
        parts: list[str] = []
        summary = self._smart_summary(cleaned)
        if summary and len(cleaned) > 320:
            summary_line = f"❝ {summary} ❞"
            start = self._utf16_len("")
            entities.append(MessageEntity(type="bold", offset=start, length=self._utf16_len(summary_line)))
            entities.append(MessageEntity(type="italic", offset=start, length=self._utf16_len(summary_line)))
            parts.append(summary_line)

        aliases = (country_aliases or {}).get(country, [])

        for i, paragraph in enumerate(paragraphs):
            emoji_char, emoji_id = self._emoji_char_and_id(paragraph, premium_emoji_ids)

            if i == 0 and not self._starts_with_country(paragraph, country, aliases):
                line = f"{emoji_char} {country} — {paragraph}".strip()
            else:
                line = f"{emoji_char} {paragraph}".strip()

            part_start_units = self._utf16_len("\n\n".join(parts) + ("\n\n" if parts else ""))
            line_units = self._utf16_len(line)

            if emoji_id:
                entities.append(
                    MessageEntity(
                        type="custom_emoji",
                        offset=part_start_units,
                        length=self._utf16_len(emoji_char),
                        custom_emoji_id=emoji_id,
                    )
                )

            body_prefix = f"{emoji_char} "
            body_start = part_start_units + self._utf16_len(body_prefix)
            body_len = line_units - self._utf16_len(body_prefix)
            if body_len > 0:
                entities.append(MessageEntity(type="italic", offset=body_start, length=body_len))

            if i == 0:
                country_prefix = f"{emoji_char} "
                country_start = part_start_units + self._utf16_len(country_prefix)
                country_len = self._utf16_len(country)
                if country_len > 0:
                    entities.append(MessageEntity(type="bold", offset=country_start, length=country_len))

            parts.append(line)

        body_text = "\n\n".join(parts)
        if parts:
            entities.append(MessageEntity(type="blockquote", offset=0, length=self._utf16_len(parts[0])))

        hashtags = self._build_hashtags(country, cleaned, country_hashtags, country_aliases)
        full_text = body_text + f"\n\n{hashtags}"
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
