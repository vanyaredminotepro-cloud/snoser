import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.filters.rp_filter import RPFilter


def test_final_weapon_rules_matrix() -> None:
    f = RPFilter()
    known_countries = {"обоссляндия", "тнр", "вилония"}
    known_hashtags = {"#OBS", "#TNR", "#VL", "#RP"}

    cases = [
        ("Запустили ракету", True),
        ("Баллистическая ракета готова", True),
        ("Наши танки движутся", False),
        ("Авиация наносит удар", False),
        ("Линкор вышел в море", False),
        ("Ядерное оружие активировано", False),
        ("Лазерная установка стреляет", False),
        ("Роботы захватили завод", False),
        ("Купили страйкбольный автомат", True),
        ("Колонна автомобилей выехала", True),
        ("Почему запрещены танки в правилах?", True),
    ]

    for text, expected_allowed in cases:
        result = f.check(text, known_countries=known_countries, known_hashtags=known_hashtags)
        assert result.allowed is expected_allowed, f"{text} -> {result}"


def test_russian_country_hashtag_is_accepted() -> None:
    f = RPFilter()
    result = f.check(
        "Обоссляндия начинает реформу #ОБС",
        known_countries={"обоссляндия"},
        known_hashtags={"#OBS", "#RP"},
    )
    assert result.allowed is True, result
