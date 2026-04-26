"""Pre-retrieval grounding for debate prompts.

The audit run (`backend/test_tool_invocation_audit.py`) confirmed that
GPT-4o-mini does NOT initiate any of the attached tools on its own. To make
the knowledge base and financial models actually inform debate output, we
fetch them once at the start of every debate and inject the results as fixed
blocks into the round and verdict prompts.

Public surface:
- :func:`build_grounding_context` — call once per debate. Mutates user_context
  in place, adding ``_research_blurb`` (always when chunks match) and
  optionally ``_runway_blurb`` / ``_monte_carlo_blurb`` when the user's
  ``financial_context`` contains enough cleanly-formatted dollar figures.

All retrieval and computation is wrapped in ``try/except`` — a malformed input
or a transient failure must NEVER raise into the debate flow. A missing blurb
just means the corresponding prompt block is omitted.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.tools.data_tools import calculate_runway as _calculate_runway_tool
from app.tools.knowledge import _retrieve_research_content
from app.tools.monte_carlo import monte_carlo_financial as _monte_carlo_tool

logger = logging.getLogger("diverge.grounding")

# Categories where runway / Monte Carlo make sense.
_FINANCIAL_CATEGORIES = {"career", "startup", "financial"}
# Subset where Monte Carlo (which compares two income streams) is appropriate.
_MONTE_CARLO_CATEGORIES = {"startup", "financial"}

# Matches: $15K, $22,400, $2,400/mo, $78K/yr, $1,200.50, etc.
# Group 1: digits (with commas/decimals). Group 2: K|M multiplier (optional).
# Group 3: period suffix (optional).
_DOLLAR_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*([KMkm])?(?:\s*/\s*(mo|month|yr|year))?",
    re.IGNORECASE,
)

_LABEL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "savings": ("savings", "saved", "in the bank", "cushion", "nest egg", "reserve"),
    "income": ("income", "salary", "pay", "earn", "earning", "make", "makes", "revenue", "raise"),
    "expenses": ("expenses", "expense", "cost", "burn", "spend", "spending",
                 "rent", "mortgage", "monthly bills"),
}

# Sentence boundaries used to clip the label-inference window. Without this,
# "Cloud role: $110K/yr but no offer yet. Savings: $15K." mislabels $110K
# as savings because "Savings:" is physically closer than "income" in the
# previous sentence. People use sentence boundaries to mean "the topic just
# changed" — respect that.
_BOUNDARY_RE = re.compile(r"[.!?;\n]")

# Sentence-level cadence cues. Used to infer the period of an unlabeled
# figure when no /mo or /yr suffix is attached: "Monthly expenses $4K" -> month.
_MONTHLY_CUES = ("monthly", "per month", "a month", "each month", "/mo", "/month")
_YEARLY_CUES = ("yearly", "annually", "annual", "per year", "a year", "/yr", "/year")
_WORD_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your",
    "their", "there", "what", "when", "where", "will", "would", "have",
    "just", "only", "role", "income", "salary", "month", "year",
}
_STATUS_QUO_HINTS = (
    "current",
    "existing",
    "present",
    "day-job",
    "day job",
    "today",
    "right now",
)
_CHANGE_HINTS = (
    "new",
    "future",
    "offer",
    "startup",
    "target",
    "other path",
    "new path",
)
_STATUS_QUO_PATH_WORDS = frozenset({
    "stay", "staying", "keep", "keeping", "current", "existing", "stable",
    "promotion", "employed", "job", "day", "agency",
})
_CHANGE_PATH_WORDS = frozenset({
    "leave", "quit", "start", "starting", "startup", "launch", "launching",
    "new", "offer", "change", "changing", "switch", "switching", "move",
    "moving", "cloud", "builder", "opportunity",
})


@dataclass
class ExtractedFigure:
    """A single dollar figure pulled from free-text financial_context."""
    amount: float
    period: Optional[str] = None       # "month" | "year" | None
    label: Optional[str] = None        # "savings" | "income" | "expenses" | None
    path_key: Optional[str] = None     # "path_a" | "path_b" | None
    raw: str = ""                      # original matched substring, for debugging
    start: int = 0
    end: int = 0


def _normalize_period(suffix: Optional[str]) -> Optional[str]:
    if not suffix:
        return None
    s = suffix.lower()
    if s in ("mo", "month"):
        return "month"
    if s in ("yr", "year"):
        return "year"
    return None


def _normalize_amount(raw_digits: str, multiplier: Optional[str]) -> float:
    digits = raw_digits.replace(",", "")
    try:
        value = float(digits)
    except ValueError:
        return 0.0
    if multiplier:
        m = multiplier.lower()
        if m == "k":
            value *= 1_000
        elif m == "m":
            value *= 1_000_000
    return value


def _clip_to_sentence(text: str, match_start: int, match_end: int) -> tuple[str, int, int]:
    """Return the slice of text bounded by the nearest sentence boundaries
    around the match, plus the match offsets relative to that slice."""
    lo = 0
    for m in _BOUNDARY_RE.finditer(text, 0, match_start):
        lo = m.end()
    hi = len(text)
    after = _BOUNDARY_RE.search(text, match_end)
    if after:
        hi = after.start()
    return text[lo:hi], match_start - lo, match_end - lo


def _infer_label(text: str, match_start: int, match_end: int) -> Optional[str]:
    """Pick the label whose closest keyword sits nearest to the dollar match.

    Scoped to the SENTENCE containing the match. A pure proximity scan over a
    fixed character window mislabels "Cloud role: $110K/yr but no offer yet.
    Savings: $15K." as savings — the next sentence's "Savings" keyword is
    physically closer than "income" in the previous sentence. Sentence
    clipping respects the writer's topic boundaries.
    """
    sentence, rel_start, rel_end = _clip_to_sentence(text, match_start, match_end)
    sentence_lower = sentence.lower()

    best_label: Optional[str] = None
    best_distance: float = float("inf")

    for label, keywords in _LABEL_KEYWORDS.items():
        for kw in keywords:
            search_from = 0
            while True:
                kw_pos = sentence_lower.find(kw, search_from)
                if kw_pos == -1:
                    break
                kw_end = kw_pos + len(kw)
                if kw_pos >= rel_end:
                    distance = kw_pos - rel_end
                elif kw_end <= rel_start:
                    distance = rel_start - kw_end
                else:
                    distance = 0
                if distance < best_distance:
                    best_distance = distance
                    best_label = label
                search_from = kw_end
    return best_label


def _infer_period_from_context(text: str, match_start: int, match_end: int) -> Optional[str]:
    """Sentence-level cadence inference for figures lacking a /mo or /yr suffix.

    "Monthly expenses $4K" -> month. "$120K annual salary" -> year.
    Returns None when neither cadence is implied (caller leaves period unset).
    """
    sentence, _, _ = _clip_to_sentence(text, match_start, match_end)
    sentence_lower = sentence.lower()
    if any(cue in sentence_lower for cue in _MONTHLY_CUES):
        return "month"
    if any(cue in sentence_lower for cue in _YEARLY_CUES):
        return "year"
    return None


def _extract_dollar_figures(text: str) -> list[ExtractedFigure]:
    """Extract every ``$amount`` figure from free text with period + label tags.

    Period resolution order:
      1. Explicit suffix on the match itself ("$8K/mo" -> month).
      2. Sentence-level cadence cues ("Monthly expenses $4K" -> month).
      3. None (caller decides whether ambiguous figures are eligible).
    """
    if not text:
        return []
    figures: list[ExtractedFigure] = []
    for m in _DOLLAR_RE.finditer(text):
        raw_digits, multiplier, period_suffix = m.group(1), m.group(2), m.group(3)
        amount = _normalize_amount(raw_digits, multiplier)
        if amount <= 0:
            continue
        period = _normalize_period(period_suffix)
        if period is None:
            period = _infer_period_from_context(text, m.start(), m.end())
        label = _infer_label(text, m.start(), m.end())
        figures.append(ExtractedFigure(
            amount=amount,
            period=period,
            label=label,
            raw=m.group(0),
            start=m.start(),
            end=m.end(),
        ))
    return figures


def _pick(
    figures: list[ExtractedFigure],
    label: str,
    period: Optional[str] = None,
) -> Optional[ExtractedFigure]:
    """Find first figure matching label (and period if specified)."""
    for f in figures:
        if f.label != label:
            continue
        if period is not None and f.period != period:
            continue
        return f
    return None


def _monthly_amount(f: ExtractedFigure) -> float:
    """Coerce a figure to a monthly value.

    /yr salaries divide by 12 (the convention any human reasoner would apply
    when computing runway from an annual income). /mo passes through. No
    period is treated as monthly (the caller decides whether ambiguous figures
    are eligible at all).
    """
    if f.period == "year":
        return f.amount / 12.0
    return f.amount


def _monthly_incomes(figures: list[ExtractedFigure]) -> list[ExtractedFigure]:
    """Income figures usable as a monthly cash-flow input.

    /mo is taken at face value. /yr is accepted (will be divided by 12 at
    use-site). No-period income figures are excluded — too ambiguous to
    silently assume a periodicity.
    """
    return [
        f for f in figures
        if f.label == "income" and f.period in ("month", "year")
    ]


def _monthly_expense(figures: list[ExtractedFigure]) -> Optional[ExtractedFigure]:
    """Pick the first explicitly-monthly expense figure.

    Yearly or no-period expense figures are skipped because they're usually
    balances (e.g. "Student loans: $22K remaining"), not flows. Treating a
    balance as a monthly expense would catastrophically distort runway math.
    """
    for f in figures:
        if f.label == "expenses" and f.period == "month":
            return f
    return None


def _tokenize(text: str) -> set[str]:
    return {
        token for token in _WORD_RE.findall((text or "").lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _path_orientation(path: str) -> Optional[str]:
    tokens = _tokenize(path)
    status_score = len(tokens & _STATUS_QUO_PATH_WORDS)
    change_score = len(tokens & _CHANGE_PATH_WORDS)
    if status_score > change_score and status_score > 0:
        return "status_quo"
    if change_score > status_score and change_score > 0:
        return "change"
    return None


def _path_overlap_score(sentence: str, path: str) -> int:
    return len(_tokenize(sentence) & _tokenize(path))


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _infer_path_key(sentence: str, path_a: str, path_b: str) -> Optional[str]:
    """Infer which decision path an income sentence refers to.

    Prefer token overlap with the actual path text. Fall back to
    status-quo/change cues only when the two paths clearly point in opposite
    directions. Return None when the sentence is still ambiguous.
    """
    sentence_lower = sentence.lower()
    score_a = _path_overlap_score(sentence, path_a)
    score_b = _path_overlap_score(sentence, path_b)

    if score_a > score_b and score_a > 0:
        return "path_a"
    if score_b > score_a and score_b > 0:
        return "path_b"

    orientation_a = _path_orientation(path_a)
    orientation_b = _path_orientation(path_b)
    if orientation_a == orientation_b:
        return None

    if _contains_any(sentence_lower, _STATUS_QUO_HINTS):
        if orientation_a == "status_quo":
            return "path_a"
        if orientation_b == "status_quo":
            return "path_b"

    if _contains_any(sentence_lower, _CHANGE_HINTS):
        if orientation_a == "change":
            return "path_a"
        if orientation_b == "change":
            return "path_b"

    return None


def _assign_income_path_keys(
    figures: list[ExtractedFigure],
    text: str,
    path_a: str,
    path_b: str,
) -> None:
    """Annotate income figures with path ownership when the sentence is clear."""
    for f in figures:
        if f.label != "income":
            continue
        sentence, _, _ = _clip_to_sentence(text, f.start, f.end)
        f.path_key = _infer_path_key(sentence, path_a, path_b)


def _pick_income_for_path(
    figures: list[ExtractedFigure],
    path_key: str,
) -> Optional[ExtractedFigure]:
    for f in figures:
        if f.label == "income" and f.period in ("month", "year") and f.path_key == path_key:
            return f
    return None


def _safe_runway(savings: float, income: float, expenses: float) -> Optional[str]:
    try:
        return _calculate_runway_tool.__wrapped__(
            savings=savings,
            monthly_income=income,
            monthly_expenses=expenses,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("calculate_runway failed during grounding: %s", exc)
        return None


def _safe_monte_carlo(
    savings: float,
    income_a: float,
    income_b: float,
    expenses: float,
) -> Optional[str]:
    try:
        return _monte_carlo_tool.__wrapped__(
            current_savings=savings,
            monthly_income_a=income_a,
            monthly_income_b=income_b,
            monthly_expenses=expenses,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("monte_carlo_financial failed during grounding: %s", exc)
        return None


def _safe_research(query: str, category: str) -> Optional[str]:
    try:
        result = _retrieve_research_content(query=query, category=category, top_k=1)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("research retrieval failed during grounding: %s", exc)
        return None
    if not result or result.startswith("No research data found"):
        return None
    return result


def build_grounding_context(user_context: dict, category: str) -> None:
    """Pre-fetch research + financial models and stash them on ``user_context``.

    Always attempts research retrieval. Conditionally computes runway and
    Monte Carlo when ``financial_context`` yields enough cleanly-formatted
    dollar figures and the category warrants financial modeling. Mutates the
    passed dict in place; never raises.

    Sets:
        user_context["_research_blurb"]      -> str (when chunks matched)
        user_context["_runway_blurb"]        -> str (when extraction succeeded)
        user_context["_monte_carlo_blurb"]   -> str (when extraction succeeded)
    """
    if user_context is None:
        return

    path_a = (user_context.get("path_a") or "").strip()
    path_b = (user_context.get("path_b") or "").strip()
    if path_a or path_b:
        query = f"{path_a} vs {path_b}".strip(" vs")
    else:
        query = category or "decision"

    research = _safe_research(query, category)
    if research:
        user_context["_research_blurb"] = research

    if category not in _FINANCIAL_CATEGORIES:
        return

    financial_context = user_context.get("financial_context", "")
    figures = _extract_dollar_figures(financial_context)
    if len(figures) < 3:
        return

    savings = _pick(figures, label="savings")
    expenses = _monthly_expense(figures)
    incomes = _monthly_incomes(figures)
    _assign_income_path_keys(incomes, financial_context, path_a, path_b)
    income_a = _pick_income_for_path(incomes, "path_a")
    income_b = _pick_income_for_path(incomes, "path_b")

    if savings and expenses and incomes:
        runway_lines: list[str] = []
        if len(incomes) == 1:
            runway = _safe_runway(
                savings.amount,
                _monthly_amount(incomes[0]),
                expenses.amount,
            )
            if runway:
                runway_lines.append(runway)
        else:
            if income_a:
                runway = _safe_runway(
                    savings.amount,
                    _monthly_amount(income_a),
                    expenses.amount,
                )
                if runway:
                    runway_lines.append(f"Path A: {runway}")
            if income_b:
                runway = _safe_runway(
                    savings.amount,
                    _monthly_amount(income_b),
                    expenses.amount,
                )
                if runway:
                    runway_lines.append(f"Path B: {runway}")
        if runway_lines:
            user_context["_runway_blurb"] = "\n".join(runway_lines)

    if category in _MONTE_CARLO_CATEGORIES and savings and expenses and income_a and income_b:
        mc = _safe_monte_carlo(
            savings.amount,
            _monthly_amount(income_a),
            _monthly_amount(income_b),
            expenses.amount,
        )
        if mc:
            user_context["_monte_carlo_blurb"] = mc
