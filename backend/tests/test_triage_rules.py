"""RuleBasedTriage: deterministic, schema-valid, and never fails on valid input."""

from __future__ import annotations

import pytest

from app.models.complaint import Category, Priority
from app.providers.triage.base import TriageProvider, TriageResult
from app.providers.triage.rules import RuleBasedTriage

rules = RuleBasedTriage()


@pytest.mark.parametrize(
    ("text", "category"),
    [
        (
            "Burst water main flooding Street 12 since fajr, water entering ground floors",
            Category.water,
        ),
        ("Bijli nahi aa rahi, transformer se dhuan nikal raha hai", Category.electricity),
        ("Kachra teen din se nahi uthaya gaya, gali mein badboo hai", Category.sanitation),
        ("Sarak par bara gharha hai, motorcycle wale gir rahe hain", Category.roads),
        ("Street light band hai poori gali mein andhera hai raat ko", Category.streetlights),
        ("Park ke bench toot gaye hain, koi dekhne wala nahi", Category.other),
    ],
)
def test_categories(text: str, category: Category):
    assert rules.triage(text, "Anywhere").category == category


def test_streetlight_wins_over_electricity_on_tie():
    # "street light" (streetlights) and "wire" (electricity) tie; the specific category wins.
    result = rules.triage("Street light ki wire latak rahi hai", "Model Town")
    assert result.category == Category.streetlights


def test_urgency_terms_make_priority_high():
    result = rules.triage("Minor leak but water is flooding the basement now", "G-9")
    assert result.priority == Priority.high  # urgency beats "minor"


def test_low_and_normal_priority():
    assert rules.triage("Minor pothole near the school gate", "F-7").priority == Priority.low
    assert (
        rules.triage("Pothole near the school gate for a week", "F-7").priority == Priority.normal
    )


def test_keywords_match_whole_words_only():
    # "tap" must not match "taper"; "road" must not match "broadcast".
    result = rules.triage("The broadcast tower paint is tapering off badly", "I-8")
    assert result.category == Category.other


def test_summary_is_one_line_and_at_most_140_chars():
    text = "Paani  nahi aa raha\npichle teen din se. " + "Bohat pareshani hai. " * 20
    result = rules.triage(text, "Gulberg")
    assert result.summary == "Paani nahi aa raha pichle teen din se."
    long = rules.triage("x" * 500, "Gulberg")
    assert len(long.summary) <= 140
    assert "\n" not in long.summary


def test_deterministic_and_valid():
    text = "Gutter overflow ho raha hai aur bachon ke school ke samne gandagi hai"
    first = rules.triage(text, "Saddar")
    assert all(rules.triage(text, "Saddar") == first for _ in range(5))
    TriageResult.model_validate(first.model_dump())
    assert 0.0 <= first.confidence <= 1.0


def test_satisfies_provider_protocol():
    assert isinstance(rules, TriageProvider)
    assert rules.name == "rules"
