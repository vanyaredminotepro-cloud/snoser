import hashlib
import re


COMMON_FIXES = {
    "строет": "строит",
    "постродавшим": "пострадавшим",
    "спецального": "специального",
    "объявляется о": "объявляет о",
    "проводяться": "проводятся",
    "треня": "тренировка",
}

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def strip_hashtags(text: str) -> str:
    return re.sub(r"#\w+", "", text)


def strip_emojis(text: str) -> str:
    return EMOJI_RE.sub("", text)


def autocorrect_news_text(text: str) -> str:
    fixed = text.strip()
    for bad, good in COMMON_FIXES.items():
        fixed = re.sub(rf"(?i)\b{re.escape(bad)}\b", good, fixed)

    fixed = re.sub(r"(?i)\b([А-ЯA-ZЁ][а-яa-zё\-]+)\s+объявляется\b", r"\1 объявляет", fixed)

    fixed = re.sub(r"\s+,", ",", fixed)
    fixed = re.sub(r"\s+\.", ".", fixed)
    fixed = re.sub(r"\s+!", "!", fixed)
    fixed = re.sub(r"\s+\?", "?", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)

    chunks = [c.strip() for c in re.split(r"\n+", fixed) if c.strip()]
    norm_chunks: list[str] = []
    for c in chunks:
        if c and c[-1] not in ".!?…":
            c = f"{c}."
        norm_chunks.append(c)
    return "\n".join(norm_chunks)
