"""Grounding and style guardrails for generated debate content."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger("diverge.content_guardrails")

BIOGRAPHY_TERMS: dict[str, tuple[str, ...]] = {
    "partner": ("girlfriend", "boyfriend", "partner", "wife", "husband", "fiance", "fiancee", "spouse"),
    "children": ("child", "children", "kid", "kids", "son", "daughter", "baby"),
    "family": ("mom", "mother", "dad", "father", "parent", "parents", "sister", "brother"),
    "property": ("house", "condo", "mortgage", "backyard", "workshop", "property", "homeowner"),
}

ATTACK_DOG_PATTERNS: dict[str, re.Pattern[str]] = {
    "attack_dog_opener": re.compile(
        r"^\s*(?:you think|let'?s be real|it'?s an illusion|behind the fa(?:cade|\u00e7ade))\b",
        re.IGNORECASE,
    ),
    "attack_dog_phrase": re.compile(
        r"\b(?:you think|let'?s be real|it'?s an illusion|behind the fa(?:cade|\u00e7ade))\b",
        re.IGNORECASE,
    ),
    "banned_cliche": re.compile(r"\bgilded cage\b", re.IGNORECASE),
}

MOTIF_PATTERNS: dict[str, re.Pattern[str]] = {
    "coffee": re.compile(r"\b(?:coffee|cafe|caf\u00e9)\b", re.IGNORECASE),
    "sunlit_room": re.compile(r"\b(?:sunlit kitchen|sunlight streaming|sunlight pours?|sunlight filtering)\b", re.IGNORECASE),
    "buzzing_office": re.compile(r"\bbuzz(?:ing)? of (?:voices|ideas|coworkers|excited voices)\b", re.IGNORECASE),
    "racing_heart": re.compile(r"\b(?:heart races|heart racing|pulse races|pulse racing)\b", re.IGNORECASE),
    "weight_in_my_chest": re.compile(r"\bweight in my chest\b", re.IGNORECASE),
}

MOTIF_REPLACEMENTS: dict[str, tuple[tuple[re.Pattern[str], str], ...]] = {
    "coffee": (
        (re.compile(r"\bcoffee shop\b", re.IGNORECASE), "quiet corner"),
        (re.compile(r"\bcoffeehouse\b", re.IGNORECASE), "quiet corner"),
        (re.compile(r"\bcaf(?:e|\u00e9)\b", re.IGNORECASE), "quiet corner"),
        (re.compile(r"\bcoffee\b", re.IGNORECASE), "warm drink"),
    ),
    "sunlit_room": (
        (re.compile(r"\bsunlit kitchen\b", re.IGNORECASE), "familiar kitchen"),
        (re.compile(r"\bsunlight streaming\b", re.IGNORECASE), "light coming through"),
        (re.compile(r"\bsunlight pours?\b", re.IGNORECASE), "light settles"),
        (re.compile(r"\bsunlight filtering\b", re.IGNORECASE), "light moving"),
    ),
    "buzzing_office": (
        (re.compile(r"\bbuzz(?:ing)? of (?:voices|ideas|coworkers|excited voices)\b", re.IGNORECASE), "office noise around me"),
    ),
    "racing_heart": (
        (re.compile(r"\bheart races\b", re.IGNORECASE), "my chest tightens"),
        (re.compile(r"\bheart racing\b", re.IGNORECASE), "my chest tightening"),
        (re.compile(r"\bpulse races\b", re.IGNORECASE), "my pulse kicks up"),
        (re.compile(r"\bpulse racing\b", re.IGNORECASE), "my pulse kicking up"),
    ),
    "weight_in_my_chest": (
        (re.compile(r"\bweight in my chest\b", re.IGNORECASE), "tension sitting in me"),
    ),
}

MONEY_PATTERN = re.compile(r"(?:\$ ?\d[\d,]*(?:\.\d+)?(?:\s?[kKmM])?|\b\d+(?:\.\d+)?\s?(?:k|K|million|thousand)\b)")
LOCATION_PATTERN = re.compile(r"\b(?:in|to|from|near|outside|across)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")

LOCATION_STOPWORDS = {
    "Year",
    "Final",
    "Path",
    "The",
    "This",
    "That",
    "Right",
    "Left",
}

MEDICAL_LEGAL_PATTERNS = {
    "medical_diagnosis": re.compile(r"\byou (?:have|developed|were diagnosed with)\b", re.IGNORECASE),
    "legal_fact": re.compile(r"\b(?:sued|arrested|charged|convicted|custody battle)\b", re.IGNORECASE),
}

VERDICT_FORBIDDEN_PATTERNS = {
    "deathbed_imagery": re.compile(r"\bdeathbed\b", re.IGNORECASE),
    "life_snapshot_header": re.compile(r"\*\*Life Snapshot", re.IGNORECASE),
    "old_verdict_header": re.compile(r"\*\*The question you should actually be asking:\*\*", re.IGNORECASE),
}

REQUIRED_VERDICT_HEADERS = (
    "**Where {path_a} wins:**",
    "**Where {path_b} wins:**",
    "**What this decision is really about:**",
    "**The bottleneck:**",
    "**Your next move:**",
)


@dataclass(frozen=True)
class ContentViolation:
    code: str
    detail: str


CATEGORY_BIOGRAPHY_EXEMPTIONS: dict[str, tuple[str, ...]] = {
    "relationship": ("partner", "family"),
    "health": ("family",),
    "career": ("property",),
    "financial": ("property",),
    "startup": ("property",),
}


@dataclass
class GroundingProfile:
    allowed_biography_terms: set[str] = field(default_factory=set)
    allowed_money_tokens: set[str] = field(default_factory=set)
    allowed_location_phrases: set[str] = field(default_factory=set)
    motif_counts: Counter[str] = field(default_factory=Counter)
    user_language: str = ""
    sparse_context: bool = False
    category: str = ""


@dataclass
class ValidationResult:
    violations: list[ContentViolation]

    @property
    def is_valid(self) -> bool:
        return not self.violations


def extract_repeated_motif_names(result: ValidationResult) -> list[str]:
    motifs: list[str] = []
    for violation in result.violations:
        if violation.code != "repeated_motif":
            continue
        match = re.search(r'"([^"]+)"', violation.detail)
        if match:
            motif = match.group(1)
            if motif not in motifs:
                motifs.append(motif)
    return motifs


def scrub_repeated_motifs(text: str, result: ValidationResult) -> str:
    updated = text
    for motif in extract_repeated_motif_names(result):
        for pattern, replacement in MOTIF_REPLACEMENTS.get(motif, ()):
            updated = pattern.sub(replacement, updated)
    updated = re.sub(r" {2,}", " ", updated)
    return updated.strip()


def _collect_context_text(user_ctx: dict, prior_texts: list[str] | None = None) -> str:
    parts = [
        user_ctx.get("path_a", ""),
        user_ctx.get("path_b", ""),
        user_ctx.get("constraints", ""),
        user_ctx.get("financial_context", ""),
        user_ctx.get("values", ""),
        user_ctx.get("writing_samples", ""),
    ]
    if prior_texts:
        parts.extend(prior_texts)
    return "\n".join(part for part in parts if part)


def _extract_biography_terms(text: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for terms in BIOGRAPHY_TERMS.values():
        for term in terms:
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                found.add(term)
    return found


def _extract_money_tokens(text: str) -> set[str]:
    return {match.group(0).lower().replace(" ", "") for match in MONEY_PATTERN.finditer(text)}


def _extract_location_phrases(text: str) -> set[str]:
    phrases: set[str] = set()
    for match in LOCATION_PATTERN.finditer(text):
        phrase = match.group(1).strip()
        if phrase in LOCATION_STOPWORDS:
            continue
        phrases.add(phrase.lower())
    return phrases


def _count_motifs(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for key, pattern in MOTIF_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            counts[key] += len(matches)
    return counts


def build_grounding_profile(
    user_ctx: dict,
    prior_texts: list[str] | None = None,
    *,
    category: str = "",
) -> GroundingProfile:
    """Build the grounding profile from user input and validated prior transcript."""
    context_text = _collect_context_text(user_ctx, prior_texts)
    user_language = "\n".join(
        part
        for part in (
            user_ctx.get("constraints", ""),
            user_ctx.get("writing_samples", ""),
        )
        if part
    ).lower()
    sparse_context = len(re.findall(r"[A-Za-z0-9']+", context_text)) < 25
    prior_text_blob = "\n".join(prior_texts or [])

    allowed_bio = _extract_biography_terms(context_text)
    for group_key in CATEGORY_BIOGRAPHY_EXEMPTIONS.get(category.lower(), ()):
        allowed_bio.update(BIOGRAPHY_TERMS.get(group_key, ()))

    return GroundingProfile(
        allowed_biography_terms=allowed_bio,
        allowed_money_tokens=_extract_money_tokens(context_text),
        allowed_location_phrases=_extract_location_phrases(context_text),
        motif_counts=_count_motifs(prior_text_blob),
        user_language=user_language,
        sparse_context=sparse_context,
        category=category.lower(),
    )


def validate_generated_text(
    text: str,
    profile: GroundingProfile,
    content_kind: str,
    *,
    path_a: str | None = None,
    path_b: str | None = None,
) -> ValidationResult:
    """Validate generated output against grounding and style rules."""
    violations: list[ContentViolation] = []
    lowered = text.lower()

    for label, pattern in ATTACK_DOG_PATTERNS.items():
        match = pattern.search(text)
        if match:
            violations.append(ContentViolation(label, f'Use of banned phrase "{match.group(0)}".'))

    for label, pattern in MEDICAL_LEGAL_PATTERNS.items():
        match = pattern.search(text)
        if match:
            violations.append(ContentViolation(label, f'Unsupported high-stakes claim "{match.group(0)}".'))

    output_bio_terms = _extract_biography_terms(text)
    disallowed_bio_terms = sorted(output_bio_terms - profile.allowed_biography_terms)
    for term in disallowed_bio_terms:
        violations.append(ContentViolation("invented_biography", f'Introduced unsupported biography term "{term}".'))

    output_money_tokens = _extract_money_tokens(text)
    disallowed_money = sorted(output_money_tokens - profile.allowed_money_tokens)
    for token in disallowed_money:
        violations.append(ContentViolation("invented_money", f'Introduced unsupported money detail "{token}".'))

    output_locations = _extract_location_phrases(text)
    disallowed_locations = sorted(output_locations - profile.allowed_location_phrases)
    for location in disallowed_locations:
        violations.append(ContentViolation("invented_location", f'Introduced unsupported location "{location}".'))

    motif_hits = _count_motifs(text)
    for motif, count in motif_hits.items():
        if MOTIF_PATTERNS[motif].search(profile.user_language):
            continue
        if profile.motif_counts.get(motif, 0) > 0:
            violations.append(ContentViolation("repeated_motif", f'Reused overplayed motif "{motif}".'))
        if count > 1:
            violations.append(ContentViolation("repeated_motif", f'Repeated motif "{motif}" inside the same passage.'))

    if content_kind == "verdict":
        if path_a and path_b:
            required_headers = [header.format(path_a=path_a, path_b=path_b) for header in REQUIRED_VERDICT_HEADERS]
            for header in required_headers:
                if header not in text:
                    violations.append(ContentViolation("missing_verdict_header", f'Missing required verdict section "{header}".'))
        for label, pattern in VERDICT_FORBIDDEN_PATTERNS.items():
            match = pattern.search(text)
            if match:
                violations.append(ContentViolation(label, f'Verdict used forbidden pattern "{match.group(0)}".'))

    if profile.sparse_context and not profile.category in CATEGORY_BIOGRAPHY_EXEMPTIONS:
        if re.search(r"\b(?:my|our)\s+(?:daughter|son|wife|husband|partner|house|mortgage|condo|backyard|workshop)\b", lowered):
            violations.append(ContentViolation("sparse_context_biography", "Sparse-context output introduced specific biography or property details."))

    return ValidationResult(violations=violations)


def format_violation_report(result: ValidationResult) -> str:
    """Convert validation failures into a terse rewrite brief."""
    if result.is_valid:
        return ""
    bullets = "\n".join(f"- {violation.detail}" for violation in result.violations[:8])
    repeated_motifs = extract_repeated_motif_names(result)
    motif_line = (
        f'- Absolutely do not mention these motifs again: {", ".join(repeated_motifs)}.\n'
        if repeated_motifs
        else ""
    )
    return (
        "Your previous draft violated the grounding/style rules. Rewrite from scratch and fix ALL of this:\n"
        f"{bullets}\n"
        f"{motif_line}"
        "- Keep the scene grounded and generic when context is sparse.\n"
        "- Do not add new people, places, money outcomes, or property details.\n"
        "- Do not use aggressive opener phrases or familiar coffee/sunlight cliches."
    )


def strict_grounding_rewrite_brief() -> str:
    """Return the strict fallback rewrite brief for a second regeneration pass."""
    return (
        "STRICT FALLBACK MODE:\n"
        "- Rewrite from scratch using only grounded, generic details.\n"
        "- No named people, named places, exact money amounts, children, partners, property, or diagnoses unless explicitly provided.\n"
        "- No attack-dog phrasing. No cliches like coffee, sunlit kitchen, buzzing office, racing heart, weight in my chest, or gilded cage.\n"
        "- Keep the tradeoff honest, concise, and plausible."
    )


def log_validation_failure(debate_id: str | None, stage: str, result: ValidationResult) -> None:
    """Emit observability logs for content failures."""
    for violation in result.violations:
        logger.warning(
            "Content validation failed debate_id=%s stage=%s code=%s detail=%s",
            debate_id or "unknown",
            stage,
            violation.code,
            violation.detail,
        )
