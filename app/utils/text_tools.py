import hashlib
import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def strip_hashtags(text: str) -> str:
    return re.sub(r"#\w+", "", text)
