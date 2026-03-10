import hashlib
import re


COMMON_FIXES = {
    "строет": "строит",
    "постродавшим": "пострадавшим",
    "спецального": "специального",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def strip_hashtags(text: str) -> str:
    return re.sub(r"#\w+", "", text)


def autocorrect_news_text(text: str) -> str:
    fixed = text.strip()
    for bad, good in COMMON_FIXES.items():
        fixed = re.sub(rf"(?i)\b{re.escape(bad)}\b", good, fixed)

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
