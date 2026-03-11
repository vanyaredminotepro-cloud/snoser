import re
from dataclasses import dataclass


@dataclass(slots=True)
class AIGuardResult:
    allowed: bool
    reason: str
    score: int


class AIGuard:
    """Heuristic AI-like moderator for toxic/non-RP bypass content."""

    toxic_tokens = {
        "penis", "p.e.n.i.s", "п.ен.и.с", "пенис", "хуй", "пизд", "еб", "нахуй", "долба", "бля", "сука", "мраз",
    }

    non_rp_tokens = {
        "мем", "рофл", "флуд", "срач", "оскорб", "оффтоп", "чат", "обсуждение", "опрос", "анкета",
    }

    suspicious_phrases = {"яна цист", "yanacist", "yana cist"}

    bypass_tokens = {
        "\\u200b", "\\u2060", "\\ufeff",
    }

    @staticmethod
    def _leet_normalize(value: str) -> str:
        mapped = value.lower()
        for src, dst in {"@": "a", "4": "a", "3": "e", "1": "i", "!": "i", "0": "o", "$": "s", "5": "s", "7": "t"}.items():
            mapped = mapped.replace(src, dst)
        return mapped

    def analyze(self, text: str) -> AIGuardResult:
        low = text.lower().strip()
        normalized = re.sub(r"[^a-zа-я0-9]+", "", low)
        leet = self._leet_normalize(normalized)
        score = 0

        if any(token in low or token.replace(".", "") in normalized or token.replace(".", "") in leet for token in self.toxic_tokens):
            score += 100
        if any(token in low for token in self.non_rp_tokens):
            score += 60
        if any(phrase in low for phrase in self.suspicious_phrases):
            score += 100
        if any(token in text for token in self.bypass_tokens):
            score += 40
        if re.search(r"[A-ZА-Я]{6,}", text):
            score += 10

        if score >= 80:
            return AIGuardResult(False, "AI_GUARD_TOXIC_OR_NON_RP", score)
        return AIGuardResult(True, "AI_GUARD_OK", score)
