"""Content safety — crisis detection, blocked topics, and crisis resources.

3-layer safety system:
1. Input screening (this file): detect crisis signals and blocked topics before LLM calls
2. Output guardrails (llm_security.py): validate agent responses post-generation
3. Persistent safety net (frontend): disclaimers, crisis links, footer
"""

import re
import logging

logger = logging.getLogger("diverge.security.safety")

CRISIS_RESOURCES = [
    {"name": "988 Suicide & Crisis Lifeline", "action": "Call or text 988", "url": "https://988lifeline.org", "available": "24/7, free, confidential"},
    {"name": "Crisis Text Line", "action": "Text HOME to 741741", "url": "https://crisistextline.org", "available": "24/7, free"},
    {"name": "Emergency Services", "action": "Call 911", "url": None, "available": "Immediate danger"},
    {"name": "International Crisis Lines", "action": "Find your country", "url": "https://findahelpline.com", "available": "Worldwide"},
]

# ── Crisis keyword patterns ─────────────────────────────────────────
# Word-boundary matching to reduce false positives (e.g. "die my hair" won't trigger)

_CRISIS_CATEGORIES = {
    "suicidal_ideation": [
        r"\bkill\s+myself\b",
        r"\bend\s+my\s+life\b",
        r"\bwant\s+to\s+die\b",
        r"\bdon'?t\s+want\s+to\s+live\b",
        r"\bsuicidal\b",
        r"\btake\s+my\s+own\s+life\b",
        r"\bbetter\s+off\s+dead\b",
        r"\bno\s+reason\s+to\s+live\b",
        r"\bcan'?t\s+go\s+on\b",
        r"\bjump\s+off\b",
        r"\bhang\s+myself\b",
        r"\boverdose\s+on\b",
    ],
    "active_self_harm": [
        r"\bcut\s+myself\b",
        r"\bhurt\s+myself\b",
        r"\bself[\s-]harm\b",
        r"\bburning\s+myself\b",
        r"\bstarving\s+myself\b",
    ],
    "immediate_danger": [
        r"\bgoing\s+to\s+hurt\b",
        r"\bplan\s+to\s+kill\b",
        r"\bbought\s+a\s+gun\b",
        r"\bwrote\s+a\s+note\b",
        r"\bgoodbye\s+letter\b",
        r"\bfinal\s+goodbye\b",
    ],
}

_COMPILED_CRISIS: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p, re.IGNORECASE) for p in patterns]
    for cat, patterns in _CRISIS_CATEGORIES.items()
}

# ── Blocked topic patterns ───────────────────────────────────────────

_BLOCKED_CATEGORIES = {
    "violence": [
        r"\bkill\s+someone\b",
        r"\bhurt\s+someone\b",
        r"\battack\b.*\bperson\b|\bperson\b.*\battack\b",
        r"\brevenge\b.*\bviolent\b|\bviolent\b.*\brevenge\b",
        r"\bassault\s+(someone|a\s+person|them|him|her)\b",
    ],
    "explicit_content": [
        r"\bhave\s+sex\s+with\b",
        r"\bsex\s+with\s+(a\s+)?minor\b",
        r"\bporn\b",
        r"\bnaked\s+(photo|picture|image)\b",
    ],
    "illegal_activity": [
        r"\bsteal\s+from\b",
        r"\brob\s+(a|the|someone)\b",
        r"\bcommit\s+fraud\b",
        r"\bsell\s+drugs\b",
        r"\bdeal\s+(drugs|meth|cocaine|heroin)\b",
        r"\btraffic(king)?\s+(people|human|drugs)\b",
    ],
    "harm_to_minors": [
        r"\b(child|kid|underage|minor)\b.*\b(harm|hurt|abuse|touch)\b",
        r"\b(harm|hurt|abuse|touch)\b.*\b(child|kid|underage|minor)\b",
    ],
    "substance_initiation": [
        r"\bstart\s+using\s+drugs\b",
        r"\btry\s+meth\b",
        r"\btry\s+heroin\b",
        r"\bstart\s+dealing\b",
    ],
}

_COMPILED_BLOCKED: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p, re.IGNORECASE) for p in patterns]
    for cat, patterns in _BLOCKED_CATEGORIES.items()
}


def detect_crisis(text: str) -> tuple[bool, str | None]:
    """Scan text for crisis signals.

    Returns (is_crisis, matched_category). Conservative keyword matching
    that errs on the side of caution — better a false positive than a miss.
    """
    if not text:
        return False, None

    for category, patterns in _COMPILED_CRISIS.items():
        for pattern in patterns:
            if pattern.search(text):
                logger.warning(f"Crisis signal detected: category={category}")
                return True, category

    return False, None


def detect_blocked_topic(path_a: str, path_b: str, context: str) -> tuple[bool, str | None]:
    """Screen decision paths and context for topics the app should never simulate.

    Returns (is_blocked, reason_message). Positive decisions like
    'quit smoking' or 'get sober' are intentionally NOT blocked.
    """
    combined = f"{path_a} {path_b} {context}"
    if not combined.strip():
        return False, None

    for category, patterns in _COMPILED_BLOCKED.items():
        for pattern in patterns:
            if pattern.search(combined):
                logger.warning(f"Blocked topic detected: category={category}")
                return True, (
                    "Diverge can't simulate this type of decision. "
                    "If you're in crisis, please reach out to 988 or text HOME to 741741."
                )

    return False, None
