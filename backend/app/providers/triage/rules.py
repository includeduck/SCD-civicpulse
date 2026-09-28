"""Deterministic keyword triage (assignment §2.5: "always available, never fails").

Used directly when TRIAGE_PROVIDER=rules and as the fallback for LLM providers.

Rules
-----
Category: count whole-word/phrase keyword hits per category (English plus
common romanised Urdu). Highest count wins; ties resolve in ``_CATEGORY_ORDER``.
No hits -> ``other``.

Priority: any urgency term -> ``high``; otherwise any low-urgency term -> ``low``;
otherwise ``normal``. Urgency is checked first so "minor fire" is still high.

Summary: first sentence of the complaint, whitespace-collapsed, cut to 140 chars.

Confidence: 0.3 with no category hits, otherwise 0.5 + 0.1 per hit, capped at 0.9.
"""

from __future__ import annotations

import re

from app.models.complaint import Category, Priority
from app.providers.triage.base import TriageResult

_CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.water: (
        "water",
        "pani",
        "paani",
        "pipe",
        "pipeline",
        "leak",
        "leakage",
        "burst",
        "tanker",
        "supply line",
        "water main",
        "tap",
        "nalka",
    ),
    Category.electricity: (
        "electricity",
        "bijli",
        "power",
        "outage",
        "transformer",
        "load shedding",
        "loadshedding",
        "voltage",
        "wire",
        "wires",
        "taar",
        "meter",
        "sparking",
        "short circuit",
    ),
    Category.sanitation: (
        "garbage",
        "kachra",
        "trash",
        "waste",
        "sewer",
        "sewage",
        "sewerage",
        "gutter",
        "drain",
        "naali",
        "gandagi",
        "smell",
        "badboo",
    ),
    Category.roads: (
        "road",
        "roads",
        "pothole",
        "potholes",
        "sarak",
        "sadak",
        "gharha",
        "gadha",
        "asphalt",
        "speed breaker",
        "footpath",
        "bridge",
    ),
    Category.streetlights: (
        "street light",
        "street lights",
        "streetlight",
        "streetlights",
        "lamp",
        "lamp post",
        "khamba",
        "andhera",
        "dark street",
        "dark road",
    ),
}

# Tie-break order: the more specific / more dangerous category wins.
_CATEGORY_ORDER: tuple[Category, ...] = (
    Category.streetlights,
    Category.electricity,
    Category.water,
    Category.sanitation,
    Category.roads,
)

_HIGH_PRIORITY_TERMS: tuple[str, ...] = (
    "flood",
    "flooding",
    "fire",
    "aag",
    "danger",
    "dangerous",
    "khatra",
    "khatarnak",
    "sparking",
    "spark",
    "electrocution",
    "current lag",
    "accident",
    "injured",
    "zakhmi",
    "children at risk",
    "gas leak",
    "collapse",
    "emergency",
    "burst",
    "overflowing",
)

_LOW_PRIORITY_TERMS: tuple[str, ...] = (
    "minor",
    "small",
    "suggestion",
    "request",
    "whenever possible",
    "thora",
    "cosmetic",
    "faded",
)

_SUMMARY_MAX = 140


def _compile(terms: tuple[str, ...]) -> re.Pattern[str]:
    # Whole words/phrases only, so "tap" does not match "taper".
    alternatives = "|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


_CATEGORY_PATTERNS = {cat: _compile(words) for cat, words in _CATEGORY_KEYWORDS.items()}
_HIGH_PATTERN = _compile(_HIGH_PRIORITY_TERMS)
_LOW_PATTERN = _compile(_LOW_PRIORITY_TERMS)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _summarise(text: str) -> str:
    one_line = " ".join(text.split())
    first_sentence = _SENTENCE_END.split(one_line, maxsplit=1)[0]
    if len(first_sentence) <= _SUMMARY_MAX:
        return first_sentence
    return first_sentence[: _SUMMARY_MAX - 3].rstrip() + "..."


class RuleBasedTriage:
    """Keyword-based triage. Pure function of its input; never raises on valid text."""

    name = "rules"

    def triage(self, text: str, location: str) -> TriageResult:  # noqa: ARG002
        hits = {cat: len(pattern.findall(text)) for cat, pattern in _CATEGORY_PATTERNS.items()}
        best = max(_CATEGORY_ORDER, key=lambda cat: (hits[cat], -_CATEGORY_ORDER.index(cat)))
        top_hits = hits[best]
        category = best if top_hits > 0 else Category.other

        if _HIGH_PATTERN.search(text):
            priority = Priority.high
        elif _LOW_PATTERN.search(text):
            priority = Priority.low
        else:
            priority = Priority.normal

        confidence = 0.3 if top_hits == 0 else min(0.9, 0.5 + 0.1 * top_hits)

        return TriageResult(
            category=category,
            priority=priority,
            summary=_summarise(text),
            confidence=confidence,
        )
