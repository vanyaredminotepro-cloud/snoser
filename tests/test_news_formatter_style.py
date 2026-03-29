import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.formatters.news_formatter import NewsFormatter


def test_official_style_removes_signatures_and_converts_verb() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="ДШРГ Торнадо",
        text="🏛️ДШРГ Торнадо - Начинаем полную подготовку бойцов.\n\n— Командование ДШРГ Торнадо\n\n#TRD",
        country_hashtags={"ДШРГ Торнадо": ["#TRD"]},
    )
    assert "Командование" not in text
    assert "<b>" not in text
    assert "начинает полную подготовку бойцов" in text.lower()
    assert text.endswith("#TRD")


def test_compact_signature_removed_and_verb_fixed() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="КК-8",
        text="⚔️КК-8 — Объявляем войну! — Пресс-служба КК-8 #KK8",
        country_hashtags={"КК-8": ["#KK8"]},
    )
    assert "Пресс-служба" not in text
    assert "объявляет войну" in text.lower()
    assert text.endswith("#KK8")


def test_keep_we_sentence_without_forced_subject() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Обоссляндия",
        text="🇷🇺Мы начинаем строительство завода.",
        country_hashtags={"Обоссляндия": ["#OBS"]},
    )
    assert "Мы начинаем строительство завода." in text


def test_russian_hashtag_rewritten_to_english() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Кермания",
        text="Кермания начинает маневры. #КК8",
        country_hashtags={"Кермания": ["#KK8", "#КК8"]},
    )
    assert "#KK8" in text
    assert "#КК8" not in text
