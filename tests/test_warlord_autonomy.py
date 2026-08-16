import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.warlord_autonomy import CountryCardInput, WarlordAutonomyCore


def test_economy_formula_and_rule_answer():
    assert WarlordAutonomyCore.economy.daily_income(
        factories=2,
        ports=1,
        citizens=100,
        tax_level="Повышенный",
    ) == 2450
    assert WarlordAutonomyCore.economy.daily_expense(soldiers=20, citizens=100) == 300

    answer = WarlordAutonomyCore.answer_rule(
        "Фабрика",
        "15к вирт-руб.",
        "6ч; лимит стройки: 1 здание + 2 НП/дороги",
        "Даёт +500 вирт-руб./день.",
    )
    assert "🎯 <b>Фабрика</b>" in answer
    assert "15к" in answer


def test_moderation_and_missing_flag_notice():
    violations = WarlordAutonomyCore.moderation_violations("Захватил страну мгновенно без боя")
    assert "PG: победа/захват без отыгрыша" in violations

    card = WarlordAutonomyCore.render_country_card(
        CountryCardInput(
            country="Тестландия",
            ruler="@leader",
            ruler_mention="@leader",
            citizens=100,
            previous_citizens=100,
            capacity=120,
            budget=10000,
            previous_budget=9000,
            soldiers=20,
            previous_soldiers=20,
            stability=60,
            previous_stability=60,
            war_support=40,
            happiness=55,
            flag_present=False,
            channel_has_avatar=True,
            factories=1,
        )
    )
    assert "[Фото флага отсутствует]" in card
    assert "(+1000)" in card
    assert "Население:</b> 100 (Вместимость" in card
    assert "дай согласие использовать аватарку твоего канала" in card
