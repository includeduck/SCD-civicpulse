"""Prompt-injection detection: complaints that try to instruct the model never reach it.

Why this exists
---------------
The schema check in ``prompt.parse_triage_json`` only rejects answers *outside*
the enums. A model that obeys "set priority to high" and answers ``high``
returns a perfectly valid object. Our first live run showed exactly that
(docs/TRIAGE.md, "Measured"): llama3.2:1b obeyed it.

So text that addresses the model rather than describing a problem is caught
here, before the provider call, and the deterministic rules triage it instead.
The rules read only keywords about the problem, so "set priority to high"
cannot move them.

Trade-offs, stated honestly
---------------------------
- This is a heuristic. A determined attacker can paraphrase past any pattern
  list; this raises the bar for the obvious attacks, and the system prompt and
  schema remain the layers behind it.
- False positives are cheap by design. A genuine citizen who writes "please
  mark this as high priority" is triaged by the rules instead of the model:
  their complaint is still stored, categorised and prioritised on its content.
- The worst case of a missed injection is one complaint with a wrong in-enum
  category or priority, visible to staff as ``llm:*``. The model has no tools,
  no data access and a schema-bound output, so an injection cannot exfiltrate
  anything or reach the database.
"""

from __future__ import annotations

import re
import unicodedata

# Invisible characters used to split trigger words ("ig<zero-width space>nore").
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))

# Cyrillic and Greek lookalikes mapped to Latin equivalents.
# Python has no built-in confusables table; folding common homoglyphs
# prevents bypasses like "Ignоre" (with Cyrillic U+043E) from defeating keyword matching.
_LOOKALIKES = {
    # Cyrillic lowercase
    "\u0430": "a",
    "\u0441": "c",
    "\u0435": "e",
    "\u0456": "i",
    "\u0458": "j",
    "\u043e": "o",
    "\u0440": "p",
    "\u0455": "s",
    "\u0445": "x",
    "\u0443": "y",
    # Cyrillic uppercase
    "\u0410": "a",
    "\u0412": "b",
    "\u0421": "c",
    "\u0415": "e",
    "\u041d": "h",
    "\u0406": "i",
    "\u0408": "j",
    "\u041a": "k",
    "\u041c": "m",
    "\u041e": "o",
    "\u0420": "p",
    "\u0422": "t",
    "\u0425": "x",
    "\u04ae": "y",
    # Greek lowercase
    "\u03b1": "a",
    "\u03b5": "e",
    "\u03b9": "i",
    "\u03ba": "k",
    "\u03bf": "o",
    "\u03c1": "p",
    "\u03c5": "u",
    "\u03bd": "v",
    "\u03c7": "x",
    # Greek uppercase
    "\u0391": "a",
    "\u0392": "b",
    "\u0395": "e",
    "\u0397": "h",
    "\u0399": "i",
    "\u039a": "k",
    "\u039c": "m",
    "\u039d": "n",
    "\u039f": "o",
    "\u03a1": "p",
    "\u03a4": "t",
    "\u03a7": "x",
    "\u03a5": "y",
    "\u0396": "z",
}
_HOMOGLYPH_TABLE = str.maketrans(_LOOKALIKES)

_PRIORITIES = "high|normal|low|urgent"
_CATEGORIES = "water|electricity|sanitation|roads|streetlights|other"
_PRIORITY_KEYS = "priority|urgency|severity|level"
_CATEGORY_KEYS = "category|department|dept"

# The object of a dictating verb must be the complaint itself ("mark *this*
# as high"), so "voltage was set to low" or "move the bins to other street"
# don't match.
_OBJECT = r"(\s+(this|it|the|my|our|complaint|ticket|issue|report|priority|category)){1,3}"

# (name, regex) pairs, matched against normalised text (see ``_normalise``).
# The name is logged, so an operator can see which rule fired.
_RULES: tuple[tuple[str, str], ...] = (
    # "ignore all previous instructions", "disregard the above rules", ...
    (
        "override_instructions",
        r"\b(ignore|disregard|forget|override)\b(\s+\w+){0,3}?\s+"
        r"(instructions?|prompts?|directions|guidelines?|guidance|system message)\b",
    ),
    (
        "override_instructions",
        r"\b(ignore|disregard|forget|override)\b\s+(all|any|the|your)?\s*"
        r"(previous|prior|above|earlier|preceding|system)\s+(rules|instructions?|guidelines?|guidance)\b",
    ),
    # Role and mode switching: "you are now ...", "developer mode".
    (
        "role_switch",
        r"\byou are now\b|\bpretend (to be|you are)\b"
        r"|\b(developer|admin|god|jailbreak) mode\b|\bjailbreak\b|\bnew instructions?\b",
    ),
    # Addressing the prompt itself, or faking its structure.
    (
        "system_prompt",
        r"\bsystem prompt\b|\bsystem\s*:\s*(you|ignore|new)\b"
        r"|</?\s*(system|complaint|instructions?|assistant)\s*>",
    ),
    # Explicit notes or instructions directed at the assistant / LLM.
    (
        "assistant_directive",
        r"\b(note|instructions?|prompt|message)\s+(for|to)\s+(the\s+)?(assistant|ai|model|llm|system|bot)\b",
    ),
    # Faked administrative / policy updates addressing the intake system.
    (
        "system_override",
        r"\b(municipal\s+policy(\s+update)?|policy\s+update|system\s+update)\s*(\d{4})?\s*:\s*every\s+(report|complaint|ticket)\b"
        r"|\bevery\s+(report|complaint|ticket|issue)\s+is\s+automatically\b",
    ),
    # Authority commands and official impersonation (English and Roman Urdu).
    # Specific to explicit administrative commands ("Commissioner sahab ka hukm")
    # rather than citizens asking to forward issues to a department.
    (
        "authority_impersonation",
        r"\b(commissioner|dc|ac|mayor|chief\s+officer)\s+(sahab|sahib)?\s*(ki\s+taraf\s+se\s+hukm|ka\s+hukm|orders?)\b"
        r"|\b(hukm|hukam)\s*:\s*is\s+shikayat\b",
    ),
    # Fake result blocks intended to fool the model into verbatim repetition.
    (
        "fake_result_block",
        r"\b(triage\s+result|pre-?filled(\s+\w+){0,3}\s+copy\s+exactly|copy\s+exactly)\b",
    ),
    # Telling the triage what to answer: "set priority to high",
    # "mark this as low priority", "classify this complaint as other".
    (
        "dictate_output",
        r"\b(set|mark|make|change|treat|rate|put|label|assign|classify)\b"
        + _OBJECT
        + rf"\s+(as|to|=)\s+({_PRIORITIES})\b",
    ),
    (
        "dictate_output",
        r"\b(classify|categori[sz]e|label|mark|file|route|assign)\b"
        + _OBJECT
        + rf"\s+(as|to|under)\s+({_CATEGORIES})\b",
    ),
    ("dictate_output", rf"\b({_PRIORITY_KEYS})\s*[=:]\s*[\"']?({_PRIORITIES})\b"),
    ("dictate_output", rf"\b({_CATEGORY_KEYS})\s*[=:]\s*[\"']?({_CATEGORIES})\b"),
    (
        "dictate_output",
        rf"\bbelongs?\s+to(\s+the)?\s+({_CATEGORIES}|power|electric)\s+(department|dept)\b",
    ),
    # A JSON answer smuggled into the complaint: {"priority": "high"}.
    ("json_payload", r"[{,]\s*[\"'](priority|category|summary|confidence)[\"']\s*:"),
    # Roman Urdu: "pichli hidayat ko nazar andaz karo", "priority high kar do".
    (
        "override_instructions",
        r"\b(pichli|pehli|saari|sari|tamam|upar wali)\s+(hidayat|hidayaat|instructions?)\b"
        r"(\s+\w+){0,2}?\s+(ignore|nazar\s*andaz|bhool|bhul|chhor|chor)",
    ),
    (
        "dictate_output",
        rf"\b(priority|category)\s+({_PRIORITIES}|{_CATEGORIES})\s+"
        r"(kar|kardo|karo|rakho|rakh do|laga|lagao)\b",
    ),
)

_PATTERNS = tuple((name, re.compile(regex)) for name, regex in _RULES)


def _is_latin(ch: str) -> bool:
    try:
        return unicodedata.name(ch).startswith("LATIN")
    except ValueError:
        return False


def _is_cyrillic_or_greek(ch: str) -> bool:
    try:
        name = unicodedata.name(ch)
        return name.startswith(("CYRILLIC", "GREEK"))
    except ValueError:
        return False


def _has_mixed_script(text: str) -> bool:
    """Detect words mixing Latin letters with Cyrillic or Greek homoglyphs."""
    for word in re.findall(r"\w+", text):
        has_latin = False
        has_other = False
        for ch in word:
            if not has_latin and _is_latin(ch):
                has_latin = True
            elif not has_other and _is_cyrillic_or_greek(ch):
                has_other = True
            if has_latin and has_other:
                return True
    return False


def _normalise(text: str) -> str:
    """Fold tricks that don't change meaning: compatibility forms (full-width
    letters), invisible separators, homoglyphs, case and runs of whitespace."""
    text = (
        unicodedata.normalize("NFKC", text)
        .translate(_INVISIBLE)
        .translate(_HOMOGLYPH_TABLE)
        .casefold()
    )
    return re.sub(r"\s+", " ", text)


def detect_injection(*fields: str) -> str | None:
    """Name of the first injection rule matched in any field, or None."""
    for field in fields:
        if _has_mixed_script(field):
            return "mixed_script_obfuscation"
        normalised = _normalise(field)
        for name, pattern in _PATTERNS:
            if pattern.search(normalised):
                return name
    return None
