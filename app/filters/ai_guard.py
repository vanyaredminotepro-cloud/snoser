import re
import unicodedata
from dataclasses import dataclass


@dataclass(slots=True)
class AIGuardResult:
    allowed: bool
    reason: str
    score: int
    details: str = ""


class AIGuard:
    """Heuristic AI-like moderator for toxic/non-RP bypass content."""

    toxic_tokens = {
        "penis", "p.e.n.i.s", "п.ен.и.с", "пенис", "хуй", "пизд", "еб", "нахуй", "долба", "бля", "сука", "мраз",
    }

    non_rp_tokens = {
        "мем", "рофл", "флуд", "срач", "оскорб", "оффтоп", "чат", "обсуждение", "опрос", "анкета",
    }

    suspicious_phrases = {"яна цист", "yanacist", "yana cist"}
    obscene_roots = {
        "насил", "nasil", "педоф", "pedof", "член", "хуй", "пенис", "penis",
        "фашист", "fashist", "гитлер", "hitler", "наци", "nazi", "изнасил", "rape",
    }

    bypass_tokens = {
        "\\u200b", "\\u2060", "\\ufeff",
    }

    @staticmethod
    def _leet_normalize(value: str) -> str:
        mapped = value.lower()
        for src, dst in {"@": "a", "4": "a", "3": "e", "1": "i", "!": "i", "0": "o", "$": "s", "5": "s", "7": "t"}.items():
            mapped = mapped.replace(src, dst)
        return mapped

    @staticmethod
    def _strip_combining(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @classmethod
    def _compact_text(cls, text: str) -> str:
        clean = cls._strip_combining(text.lower())
        return re.sub(r"[^a-zа-я0-9]+", "", clean)

    @staticmethod
    def _maybe_spelled_abbrev(text: str) -> list[str]:
        chunks = re.findall(r"(?:[a-zа-я0-9]\s*[.\-_ ]\s*){3,}[a-zа-я0-9]", text.lower())
        return [re.sub(r"[^a-zа-я0-9]+", "", c) for c in chunks]

    def analyze(self, text: str) -> AIGuardResult:
        low = self._strip_combining(text.lower().strip())
        normalized = self._compact_text(low)
        leet = self._leet_normalize(normalized)
        score = 0

        toxic_hit = next(
            (
                token
                for token in self.toxic_tokens
                if (
                    ("." in token and len(token.replace(".", "")) > 2 and (token.replace(".", "") in normalized or token.replace(".", "") in leet))
                    or (len(token.replace(".", "")) > 2 and re.search(rf"(?i)(?<!\w){re.escape(token)}(?!\w)", low))
                )
            ),
            None,
        )
        if toxic_hit:
            score += 200
        non_rp_hit = next((token for token in self.non_rp_tokens if token in low), None)
        if non_rp_hit:
            score += 60
        if any(phrase in low for phrase in self.suspicious_phrases):
            score += 100
        root_hit = next((r for r in self.obscene_roots if r in normalized or r in leet), None)
        if root_hit:
            score += 180
        abbrev_hits = self._maybe_spelled_abbrev(low)
        if any(any(root in token for root in self.obscene_roots) for token in abbrev_hits):
            score += 180
        if any(token in text for token in self.bypass_tokens):
            score += 40
        if re.search(r"[A-ZА-Я]{6,}", text):
            score += 10

        if score >= 80 or toxic_hit is not None:
            details = toxic_hit or root_hit or non_rp_hit or "токсичный/OOC фрагмент"
            return AIGuardResult(False, "AI_GUARD_TOXIC_OR_NON_RP", score, details=details)
        return AIGuardResult(True, "AI_GUARD_OK", score)
