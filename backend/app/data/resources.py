"""Curated resource recommendations per decision category.

Resources are not LLM-generated. Titles, authors, and URLs are vetted here so
the model can personalize recommendations without inventing links.
"""

from __future__ import annotations

import hashlib
import re

from app.agents.prompts import (
    CAREER_KEYWORDS,
    EDUCATION_KEYWORDS,
    FINANCIAL_KEYWORDS,
    HEALTH_KEYWORDS,
    RELATIONSHIP_KEYWORDS,
    STARTUP_KEYWORDS,
)

ELIGIBLE_TIMELINE_TYPES = ("book", "video", "concept")
CATEGORY_ORDER = ("career", "startup", "relationship", "health", "education", "financial", "general")

CATEGORY_KEYWORDS = {
    "career": CAREER_KEYWORDS,
    "startup": STARTUP_KEYWORDS,
    "relationship": RELATIONSHIP_KEYWORDS,
    "health": HEALTH_KEYWORDS,
    "education": EDUCATION_KEYWORDS,
    "financial": FINANCIAL_KEYWORDS,
}

CATEGORY_PHRASES: dict[str, tuple[str, ...]] = {
    "relationship": ("break up", "ask out", "move in", "fall in love", "tell them"),
    "startup": ("start a company", "launch a startup", "quit and build", "raise money"),
    "career": ("change jobs", "take the offer", "stay in my role", "switch careers"),
    "education": ("go back to school", "go to grad school", "take on tuition"),
    "financial": ("move cities", "relocate", "take the pay cut", "invest the money"),
    "health": ("get in shape", "get sober", "start therapy", "fix my sleep"),
}

RESOURCES: dict[str, list[dict]] = {
    "career": [
        {
            "type": "book",
            "title": "Designing Your Life",
            "author": "Bill Burnett & Dave Evans",
            "url": "https://designingyour.life/the-book/",
            "why": "Stanford framework for prototyping career changes before committing.",
        },
        {
            "type": "book",
            "title": "So Good They Can't Ignore You",
            "author": "Cal Newport",
            "url": "https://www.calnewport.com/books/so-good/",
            "why": "Why 'follow your passion' is bad advice - build rare skills instead.",
        },
        {
            "type": "video",
            "title": "How to find work you love",
            "author": "Scott Dinsmore (TED)",
            "url": "https://www.ted.com/talks/scott_dinsmore_how_to_find_work_you_love",
            "why": "15-minute framework for identifying work that aligns with your strengths.",
        },
        {
            "type": "podcast",
            "title": "How I Built This",
            "author": "Guy Raz (NPR)",
            "url": "https://www.npr.org/series/490248027/how-i-built-this",
            "why": "Real stories of career pivots from founders who took the leap.",
        },
        {
            "type": "article",
            "title": "The Career Lattice: Why Lateral Moves Matter",
            "author": "Harvard Business Review",
            "url": "https://hbr.org/topic/career-planning",
            "why": "Career growth is not always vertical - lateral moves build versatility.",
        },
        {
            "type": "book",
            "title": "Working Identity",
            "author": "Herminia Ibarra",
            "url": "https://store.hbr.org/product/working-identity-unconventional-strategies-for-reinventing-your-career/10488",
            "why": "Research on how people actually reinvent their professional lives.",
        },
        {
            "type": "concept",
            "title": "Career Capital",
            "author": "Cal Newport Framework",
            "url": "https://www.calnewport.com/books/so-good/",
            "why": "Build leverage first, then use that leverage to shape work that fits your life.",
        },
    ],
    "startup": [
        {
            "type": "book",
            "title": "The Lean Startup",
            "author": "Eric Ries",
            "url": "https://theleanstartup.com/book",
            "why": "The framework for validating business ideas before burning cash.",
        },
        {
            "type": "book",
            "title": "Zero to One",
            "author": "Peter Thiel",
            "url": "https://zerotoonebook.com/",
            "why": "Contrarian thinking about what makes a startup actually valuable.",
        },
        {
            "type": "video",
            "title": "The single biggest reason why startups succeed",
            "author": "Bill Gross (TED)",
            "url": "https://www.ted.com/talks/bill_gross_the_single_biggest_reason_why_start_ups_succeed",
            "why": "Data-driven analysis of 200+ startups - timing beats idea and team.",
        },
        {
            "type": "podcast",
            "title": "How I Built This",
            "author": "Guy Raz (NPR)",
            "url": "https://www.npr.org/series/490248027/how-i-built-this",
            "why": "Honest founder stories including the failures and near-death moments.",
        },
        {
            "type": "article",
            "title": "Do Things That Don't Scale",
            "author": "Paul Graham",
            "url": "http://paulgraham.com/ds.html",
            "why": "The most important essay on early-stage startup strategy.",
        },
        {
            "type": "book",
            "title": "The Mom Test",
            "author": "Rob Fitzpatrick",
            "url": "https://momtestbook.com/",
            "why": "How to validate your idea by talking to customers without lying to yourself.",
        },
        {
            "type": "concept",
            "title": "Survivorship Bias",
            "author": "Cognitive Bias",
            "url": "https://thedecisionlab.com/biases/survivorship-bias",
            "why": "Separates the loud founder success stories from the quiet pile of failures you never see.",
        },
    ],
    "relationship": [
        {
            "type": "book",
            "title": "Attached",
            "author": "Amir Levine & Rachel Heller",
            "url": "https://www.attachedthebook.com/",
            "why": "The science of adult attachment - understand your patterns.",
        },
        {
            "type": "book",
            "title": "The Courage to Be Disliked",
            "author": "Ichiro Kishimi & Fumitake Koga",
            "url": "https://www.simonandschuster.com/books/The-Courage-to-Be-Disliked/Ichiro-Kishimi/9781501197277",
            "why": "Adlerian psychology on why fear of rejection controls your life.",
        },
        {
            "type": "video",
            "title": "The power of vulnerability",
            "author": "Brene Brown (TED)",
            "url": "https://www.ted.com/talks/brene_brown_the_power_of_vulnerability",
            "why": "Research on why vulnerability is the birthplace of connection.",
        },
        {
            "type": "podcast",
            "title": "Where Should We Begin?",
            "author": "Esther Perel",
            "url": "https://www.estherperel.com/podcast",
            "why": "Real therapy sessions about the decisions that shape relationships.",
        },
        {
            "type": "book",
            "title": "Hold Me Tight",
            "author": "Sue Johnson",
            "url": "https://drsuejohnson.com/hold-me-tight/",
            "why": "Emotionally Focused Therapy - the science of lasting bonds.",
        },
        {
            "type": "article",
            "title": "The 36 Questions That Lead to Love",
            "author": "Arthur Aron (via NY Times)",
            "url": "https://www.nytimes.com/2015/01/09/style/no-37-big-wedding-or-small.html",
            "why": "Structured vulnerability creates closeness faster than months of casual interaction.",
        },
        {
            "type": "concept",
            "title": "Attachment Theory",
            "author": "Attachment Framework",
            "url": "https://www.verywellmind.com/what-is-attachment-theory-2795337",
            "why": "Explains why fear of rejection, withdrawal, and over-pursuing can feel so physically intense.",
        },
    ],
    "health": [
        {
            "type": "book",
            "title": "Atomic Habits",
            "author": "James Clear",
            "url": "https://jamesclear.com/atomic-habits",
            "why": "The definitive guide to building habits that stick - systems over goals.",
        },
        {
            "type": "book",
            "title": "The Power of Habit",
            "author": "Charles Duhigg",
            "url": "https://charlesduhigg.com/the-power-of-habit/",
            "why": "The neuroscience of habit loops and how to rewire them.",
        },
        {
            "type": "video",
            "title": "The secret to self control",
            "author": "Jonathan Bricker (TEDx)",
            "url": "https://www.ted.com/talks/jonathan_bricker_the_secret_to_self_control",
            "why": "ACT-based approach to behavior change that outperforms willpower.",
        },
        {
            "type": "podcast",
            "title": "Huberman Lab",
            "author": "Andrew Huberman",
            "url": "https://hubermanlab.com/",
            "why": "Neuroscience-based protocols for sleep, exercise, and mental health.",
        },
        {
            "type": "book",
            "title": "Tiny Habits",
            "author": "BJ Fogg",
            "url": "https://www.tinyhabits.com/book",
            "why": "Stanford researcher's method for starting so small you cannot fail.",
        },
        {
            "type": "article",
            "title": "How Long Does It Actually Take to Form a New Habit?",
            "author": "James Clear",
            "url": "https://jamesclear.com/new-habit",
            "why": "Debunks the 21-day myth with actual research (66 days average).",
        },
        {
            "type": "concept",
            "title": "Acceptance and Commitment Therapy",
            "author": "ACT Framework",
            "url": "https://www.psychologytoday.com/us/therapy-types/acceptance-and-commitment-therapy",
            "why": "Helps people move with discomfort instead of waiting for perfect motivation before they act.",
        },
    ],
    "education": [
        {
            "type": "book",
            "title": "Range",
            "author": "David Epstein",
            "url": "https://books.apple.com/us/book/range/id1435005899",
            "why": "Why generalists triumph in a specialized world - broad learning wins long-term.",
        },
        {
            "type": "book",
            "title": "Ultralearning",
            "author": "Scott Young",
            "url": "https://www.scotthyoung.com/blog/ultralearning/",
            "why": "How to learn hard things fast - relevant whether you go back to school or not.",
        },
        {
            "type": "video",
            "title": "The myth of average",
            "author": "Todd Rose (TEDx)",
            "url": "https://www.ted.com/talks/todd_rose_the_myth_of_average",
            "why": "Why standardized education paths do not fit most people.",
        },
        {
            "type": "article",
            "title": "ROI of Education by Field",
            "author": "Georgetown CEW",
            "url": "https://cew.georgetown.edu/cew-reports/collegeroi/",
            "why": "Hard data on which degrees actually pay back and how long it takes.",
        },
        {
            "type": "podcast",
            "title": "Hidden Brain: You 2.0",
            "author": "Shankar Vedantam (NPR)",
            "url": "https://hiddenbrain.org/",
            "why": "Psychology of personal reinvention and how identity shapes learning.",
        },
        {
            "type": "book",
            "title": "Mindset",
            "author": "Carol Dweck",
            "url": "https://www.penguinrandomhouse.com/books/44330/mindset-by-carol-s-dweck-phd/",
            "why": "Growth vs fixed mindset - the foundation of whether education works for you.",
        },
        {
            "type": "concept",
            "title": "Opportunity Cost",
            "author": "Decision-Making Framework",
            "url": "https://www.investopedia.com/terms/o/opportunitycost.asp",
            "why": "Forces the decision out of abstract prestige and back into what your time, debt, and attention are replacing.",
        },
    ],
    "financial": [
        {
            "type": "book",
            "title": "The Psychology of Money",
            "author": "Morgan Housel",
            "url": "https://www.harriman-house.com/thepsychologyofmoney",
            "why": "Why financial decisions are about behavior, not math.",
        },
        {
            "type": "book",
            "title": "I Will Teach You to Be Rich",
            "author": "Ramit Sethi",
            "url": "https://www.iwillteachyoutoberich.com/books/",
            "why": "Practical system for automating financial decisions so you stop agonizing.",
        },
        {
            "type": "video",
            "title": "How to buy happiness",
            "author": "Michael Norton (TED)",
            "url": "https://www.ted.com/talks/michael_norton_how_to_buy_happiness",
            "why": "Research on the relationship between money and actual life satisfaction.",
        },
        {
            "type": "podcast",
            "title": "The Indicator",
            "author": "NPR/Planet Money",
            "url": "https://www.npr.org/sections/money/",
            "why": "Short episodes making economic decisions feel less abstract.",
        },
        {
            "type": "article",
            "title": "The True Cost of Relocating",
            "author": "NerdWallet",
            "url": "https://www.nerdwallet.com/article/mortgages/the-cost-of-moving",
            "why": "Real numbers on what it costs to move cities - beyond the rent difference.",
        },
        {
            "type": "book",
            "title": "Your Money or Your Life",
            "author": "Vicki Robin",
            "url": "https://www.penguinrandomhouse.com/books/211176/your-money-or-your-life-by-vicki-robin-and-joe-dominguez/",
            "why": "Reframes money as life energy - helps clarify what the financial trade-off really means.",
        },
        {
            "type": "concept",
            "title": "Loss Aversion",
            "author": "Behavioral Economics",
            "url": "https://thedecisionlab.com/biases/loss-aversion",
            "why": "Explains why a possible loss can feel louder than a bigger long-term gain.",
        },
    ],
    "general": [
        {
            "type": "book",
            "title": "Thinking, Fast and Slow",
            "author": "Daniel Kahneman",
            "url": "https://en.wikipedia.org/wiki/Thinking,_Fast_and_Slow",
            "why": "The foundational work on how humans make (and mess up) decisions.",
        },
        {
            "type": "book",
            "title": "The Paradox of Choice",
            "author": "Barry Schwartz",
            "url": "https://www.harpercollins.com/products/the-paradox-of-choice-barry-schwartz",
            "why": "Why more options make decisions harder - and what to do about it.",
        },
        {
            "type": "video",
            "title": "The paradox of choice",
            "author": "Barry Schwartz (TED)",
            "url": "https://www.ted.com/talks/barry_schwartz_the_paradox_of_choice",
            "why": "19-minute talk on why 'good enough' beats 'the best possible' for happiness.",
        },
        {
            "type": "podcast",
            "title": "Hidden Brain",
            "author": "Shankar Vedantam (NPR)",
            "url": "https://hiddenbrain.org/",
            "why": "The unconscious patterns that drive your biggest decisions.",
        },
        {
            "type": "book",
            "title": "Stumbling on Happiness",
            "author": "Daniel Gilbert",
            "url": "https://www.penguinrandomhouse.com/books/298755/stumbling-on-happiness-by-daniel-gilbert/",
            "why": "Why we are terrible at predicting what will make us happy - and how to improve.",
        },
        {
            "type": "article",
            "title": "How to Make Hard Choices",
            "author": "Ruth Chang (TED)",
            "url": "https://www.ted.com/talks/ruth_chang_how_to_make_hard_choices",
            "why": "Philosopher reframes hard choices as opportunities for self-creation.",
        },
        {
            "type": "concept",
            "title": "Sunk-Cost Fallacy",
            "author": "Cognitive Bias",
            "url": "https://thedecisionlab.com/biases/the-sunk-cost-fallacy",
            "why": "Names the trap of defending yesterday's investment instead of choosing today's best move.",
        },
    ],
}


def get_resources_for_category(category: str) -> list[dict]:
    """Get curated resources for a decision category."""
    return RESOURCES.get(category, RESOURCES["general"])


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _score_categories(path_a: str, path_b: str, constraints: str | None = None) -> list[tuple[str, int]]:
    combined = " ".join(part for part in (path_a, path_b, constraints or "") if part).lower()
    words = _tokenize(combined)
    scores: list[tuple[str, int]] = []

    for category in CATEGORY_ORDER:
        if category == "general":
            continue
        score = len(words & CATEGORY_KEYWORDS[category])
        for phrase in CATEGORY_PHRASES.get(category, ()):
            if phrase in combined:
                score += 2
        if score > 0:
            scores.append((category, score))

    return sorted(scores, key=lambda item: (-item[1], CATEGORY_ORDER.index(item[0])))


def select_relevant_categories(path_a: str, path_b: str, constraints: str | None = None) -> list[str]:
    """Select the 1-2 most relevant resource categories from user text."""
    scored = _score_categories(path_a, path_b, constraints)
    if not scored:
        return []

    selected = [scored[0][0]]
    if len(scored) > 1 and scored[1][1] > 0:
        selected.append(scored[1][0])
    return selected[:2]


def _copy_resource(resource: dict, category: str) -> dict:
    copied = dict(resource)
    copied["category"] = category
    return copied


def _iter_timeline_eligible(category: str) -> list[dict]:
    return [
        _copy_resource(resource, category)
        for resource in get_resources_for_category(category)
        if resource.get("type") in ELIGIBLE_TIMELINE_TYPES and resource.get("url")
    ]


def shortlist_resource_candidates(
    path_a: str,
    path_b: str,
    constraints: str | None = None,
    max_candidates: int = 12,
    decision_category: str | None = None,
) -> list[dict]:
    """Build a small, deterministic candidate list for stage-06 prompting."""
    scored_categories = [category for category, _ in _score_categories(path_a, path_b, constraints)]
    
    if decision_category:
        selected = [decision_category.lower()]
    else:
        selected = select_relevant_categories(path_a, path_b, constraints)

    if selected:
        ordered_categories = list(selected)
        if "general" not in ordered_categories:
            ordered_categories.append("general")
        ordered_categories.extend(
            category for category in scored_categories if category not in ordered_categories
        )
    else:
        ordered_categories = ["general", "health", "relationship", "career"]

    ordered_categories.extend(
        category for category in CATEGORY_ORDER if category not in ordered_categories
    )

    target_per_type = 3 if max_candidates >= 9 else max(1, max_candidates // len(ELIGIBLE_TIMELINE_TYPES))
    grouped: dict[str, list[dict]] = {resource_type: [] for resource_type in ELIGIBLE_TIMELINE_TYPES}
    seen: set[tuple[str, str, str]] = set()

    for category in ordered_categories:
        eligible = _iter_timeline_eligible(category)
        for resource_type in ELIGIBLE_TIMELINE_TYPES:
            if len(grouped[resource_type]) >= target_per_type:
                continue
            for resource in eligible:
                if resource["type"] != resource_type:
                    continue
                signature = (resource["type"], resource["title"], resource["author"])
                if signature in seen:
                    continue
                grouped[resource_type].append(resource)
                seen.add(signature)
                break

        if all(len(items) >= target_per_type for items in grouped.values()):
            break

    candidates = grouped["book"] + grouped["video"] + grouped["concept"]
    return candidates[:max_candidates]


def get_rotating_fallback_resources(
    path_a: str,
    path_b: str,
    constraints: str | None = None,
    max_items: int = 3,
    decision_category: str | None = None,
) -> list[dict]:
    """Return a diverse deterministic fallback recommendation trio."""
    shortlist = shortlist_resource_candidates(path_a, path_b, constraints, max_candidates=12, decision_category=decision_category)
    
    if decision_category:
        selected_categories = {decision_category.lower()}
    else:
        selected_categories = set(select_relevant_categories(path_a, path_b, constraints))
        
    grouped: dict[str, list[dict]] = {resource_type: [] for resource_type in ELIGIBLE_TIMELINE_TYPES}
    for resource in shortlist:
        grouped.setdefault(resource["type"], []).append(resource)

    digest = hashlib.sha256(
        f"{path_a}|{path_b}|{constraints or ''}".encode("utf-8")
    ).digest()

    picks: list[dict] = []
    for index, resource_type in enumerate(ELIGIBLE_TIMELINE_TYPES):
        options = grouped.get(resource_type, [])
        if not options:
            continue
        preferred = [resource for resource in options if resource.get("category") in selected_categories]
        candidate_pool = preferred or options
        chosen = dict(candidate_pool[digest[index] % len(candidate_pool)])
        chosen.pop("category", None)
        picks.append(chosen)

    return picks[:max_items]
