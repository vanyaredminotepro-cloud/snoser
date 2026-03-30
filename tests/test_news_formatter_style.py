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


def test_official_created_phrase_is_normalized() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Обоссляндия",
        text="Обоссляндия Официально создаём новейшую версию ОЯТ\n\n#OBS",
        country_hashtags={"Обоссляндия": ["#OBS"]},
    )
    assert "Обоссляндия официально создала новейшую версию оят".lower() in text.lower()


def test_leading_we_after_country_is_removed() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Обоссляндия",
        text="Обоссляндия Мы официально создали новейшую версию ОЯТ\n\n#OBS",
        country_hashtags={"Обоссляндия": ["#OBS"]},
    )
    assert "Мы официально" not in text
    assert "обоссляндия официально создала новейшую версию оят" in text.lower()


def test_country_prefix_is_removed_if_country_is_already_in_body() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Вилония",
        text='Подразделения морской пехоты Вилонии перебазированы в аванпост "Ягуар" в ТНР.',
        country_hashtags={"Вилония": ["#VL"], "ТНР": ["#TNR"]},
        country_aliases={"Вилония": ["вилония", "вилонии"]},
    )
    assert "🧭 Вилония Подразделения" not in text
    assert "подразделения морской пехоты вилонии" in text.lower()


def test_military_text_gets_non_default_eye_emoji() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Вилония",
        text='Подразделения морской пехоты Вилонии перебазированы в аванпост "Ягуар" в ТНР.',
        country_hashtags={"Вилония": ["#VL"], "ТНР": ["#TNR"]},
        country_aliases={"Вилония": ["вилония", "вилонии"]},
    )
    first_char = text.split(" ", 1)[0]
    assert first_char != "👀"


def test_country_not_duplicated_when_already_in_text() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Вилония",
        text='Подразделения морской пехоты Вилонии перебазированы в аванпост "Ягуар" в ТНР.\n\n#VL #TNR',
        country_hashtags={"Вилония": ["#VL"], "ТНР": ["#TNR"]},
        country_aliases={"Вилония": ["вилония", "вилонии"]},
    )
    first_line = text.splitlines()[0]
    assert "Вилония Вилонии" not in first_line
    assert "вилонии" in first_line.lower()


def test_military_text_gets_non_default_emoji() -> None:
    fmt = NewsFormatter()
    text, _ = fmt.format_news_entities(
        country="Вилония",
        text='Подразделения морской пехоты перебазированы в аванпост "Ягуар". Размещены ракетные комплексы.',
        country_hashtags={"Вилония": ["#VL"]},
    )
    first_line = text.splitlines()[0]
    assert not first_line.startswith("👀 "), first_line


def test_emoji_to_key_covers_expanded_variants() -> None:
    # New expanded variants should still map to semantic premium keys.
    assert NewsFormatter.emoji_to_key.get("🛰️") in {"MAP", "WARNING", "DEFAULT"}
    assert NewsFormatter.emoji_to_key.get("💸") == "ECONOMY"
    assert NewsFormatter.emoji_to_key.get("🗳️") == "DIPLOMACY"
    assert NewsFormatter.emoji_to_key.get("⚡") == "WARNING"
    assert NewsFormatter.emoji_to_key.get("⚡️") == "WARNING"


def test_rewrite_replaces_our_country_phrase_with_specific_country() -> None:
    fmt = NewsFormatter()
    rewritten = fmt.rewrite("Вилония", "В нашей стране проводятся масштабные исследования.")
    assert "в вилонии" in rewritten.lower()
