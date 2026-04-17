"""Curated resource recommendations per decision category.

Resources are not LLM-generated. Titles, authors, and URLs are vetted here so
the model can personalize recommendations without inventing links.
"""

from __future__ import annotations

import re
from collections import defaultdict

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

BOTTLENECK_TAXONOMY = (
    "fear_of_failure",
    "fear_of_rejection",
    "sunk_cost",
    "loss_aversion",
    "scarcity_panic",
    "identity_foreclosure",
    "perfectionism",
    "burnout_avoidance",
    "family_duty_pressure",
)

BOTTLENECK_PATTERNS: dict[str, tuple[str, ...]] = {
    "fear_of_failure": ("fail", "failure", "wrong decision", "mess up", "flop", "risk", "what if it doesn't work"),
    "fear_of_rejection": ("rejection", "rejected", "embarrassed", "confess", "ask out", "tell them", "vulnerable"),
    "sunk_cost": ("already spent", "already invested", "too much time", "can't waste", "sunk cost", "all these years"),
    "loss_aversion": ("lose", "losing", "give up", "leave behind", "comfort", "what i have", "what i built"),
    "scarcity_panic": ("student loans", "debt", "rent", "paycheck", "no safety net", "savings", "bills"),
    "identity_foreclosure": ("who i am", "identity", "first-gen", "prestige", "title", "beginner again", "career path"),
    "perfectionism": ("ready", "certainty", "perfect", "more time", "need a plan", "not sure enough"),
    "burnout_avoidance": ("burned out", "burnt out", "exhausted", "tired", "overwhelmed", "no energy"),
    "family_duty_pressure": (
        "mom",
        "dad",
        "parents",
        "kids",
        "children",
        "caregiver",
        "only nearby",
        "depends on me",
        "depend on me",
        "family depends",
        "send money home",
        "take care of them",
        "feel guilty",
    ),
}

DEFAULT_BOTTLENECK_BY_CATEGORY = {
    "startup": "fear_of_failure",
    "career": "identity_foreclosure",
    "financial": "loss_aversion",
    "education": "scarcity_panic",
    "relationship": "fear_of_rejection",
    "health": "burnout_avoidance",
    "general": "perfectionism",
}

RESOURCE_BOTTLENECK_TAGS: dict[tuple[str, str], tuple[str, ...]] = {
    ("book", "Designing Your Life"): ("fear_of_failure", "identity_foreclosure", "sunk_cost"),
    ("video", "How to find work you love"): ("fear_of_failure", "identity_foreclosure"),
    ("concept", "Sunk-Cost Fallacy"): ("sunk_cost", "loss_aversion"),
    ("book", "Working Identity"): ("identity_foreclosure", "fear_of_failure"),
    ("concept", "Career Capital"): ("identity_foreclosure", "loss_aversion"),
    ("book", "The Lean Startup"): ("fear_of_failure", "scarcity_panic"),
    ("video", "The single biggest reason why startups succeed"): ("fear_of_failure", "scarcity_panic"),
    ("book", "The Mom Test"): ("fear_of_failure", "perfectionism"),
    ("concept", "Survivorship Bias"): ("fear_of_failure", "loss_aversion"),
    ("book", "Attached"): ("fear_of_rejection", "family_duty_pressure"),
    ("video", "The power of vulnerability"): ("fear_of_rejection", "perfectionism"),
    ("concept", "Attachment Theory"): ("fear_of_rejection", "family_duty_pressure"),
    ("book", "Atomic Habits"): ("burnout_avoidance", "perfectionism"),
    ("book", "Tiny Habits"): ("burnout_avoidance", "perfectionism"),
    ("concept", "Acceptance and Commitment Therapy"): ("burnout_avoidance", "perfectionism"),
    ("book", "Range"): ("identity_foreclosure", "fear_of_failure"),
    ("book", "Mindset"): ("fear_of_failure", "perfectionism"),
    ("article", "ROI of Education by Field"): ("scarcity_panic", "loss_aversion"),
    ("concept", "Opportunity Cost"): ("scarcity_panic", "loss_aversion"),
    ("book", "The Psychology of Money"): ("scarcity_panic", "loss_aversion", "family_duty_pressure"),
    ("book", "Your Money or Your Life"): ("scarcity_panic", "loss_aversion", "family_duty_pressure"),
    ("video", "How to buy happiness"): ("loss_aversion", "scarcity_panic"),
    ("concept", "Loss Aversion"): ("loss_aversion", "scarcity_panic"),
    ("book", "Thinking, Fast and Slow"): ("perfectionism", "loss_aversion"),
    ("video", "The paradox of choice"): ("perfectionism", "identity_foreclosure"),
    ("concept", "Sunk-Cost Fallacy"): ("sunk_cost", "loss_aversion"),
}

BOTTLENECK_WHY_SUFFIX: dict[str, dict[str, str]] = {
    "fear_of_failure": {
        "book": "It builds a framework for separating real risk from imagined catastrophe.",
        "video": "It reframes failure as part of the process rather than a final verdict.",
        "concept": "It gives you a mental model for sizing downside honestly.",
    },
    "fear_of_rejection": {
        "book": "It makes emotional risk feel legible instead of overwhelming.",
        "video": "It normalizes the discomfort of putting yourself out there.",
        "concept": "It names the pattern so the fear loses some of its grip.",
    },
    "sunk_cost": {
        "book": "It cuts through loyalty to past effort and returns you to the present choice.",
        "video": "It shows how others walked away from investments that were no longer serving them.",
        "concept": "It separates what you have already spent from what is still worth spending.",
    },
    "loss_aversion": {
        "book": "It slows down the instinct to protect what is familiar at any cost.",
        "video": "It reframes what you are actually losing by not moving.",
        "concept": "It explains why a possible loss feels louder than a bigger gain.",
    },
    "scarcity_panic": {
        "book": "It turns money fear into a clearer tradeoff instead of a fog of dread.",
        "video": "It grounds the financial anxiety in actual numbers rather than worst-case spirals.",
        "concept": "It helps you calculate real runway instead of imagining freefall.",
    },
    "identity_foreclosure": {
        "book": "It loosens the story that one decision has to define who you are forever.",
        "video": "It shows how identity shifts happen gradually, not all at once.",
        "concept": "It names the trap of locking in a self-image too early.",
    },
    "perfectionism": {
        "book": "It replaces waiting for certainty with a smaller, testable next move.",
        "video": "It demonstrates why good enough now beats perfect later.",
        "concept": "It gives you permission to act before you feel ready.",
    },
    "burnout_avoidance": {
        "book": "It makes change feel sustainable instead of like another impossible demand.",
        "video": "It shows how small shifts compound without requiring a dramatic overhaul.",
        "concept": "It reframes rest and recovery as part of the decision, not a delay.",
    },
    "family_duty_pressure": {
        "book": "It holds responsibility and self-direction in the same frame.",
        "video": "It shows how others navigated family obligations without abandoning their own path.",
        "concept": "It separates duty from guilt so you can see the actual tradeoff.",
    },
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
        {
            "type": "video",
            "title": "Rethinking infidelity",
            "author": "Esther Perel (TED)",
            "url": "https://www.ted.com/talks/esther_perel_rethinking_infidelity_a_talk_for_anyone_who_has_ever_loved",
            "why": "Reframes relationship crises as turning points rather than endpoints.",
        },
        {
            "type": "concept",
            "title": "Emotional Bid",
            "author": "Gottman Institute",
            "url": "https://www.gottman.com/blog/turn-toward-instead-of-away/",
            "why": "Small moments of turning toward or away predict relationship outcomes better than grand gestures.",
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
        {
            "type": "video",
            "title": "What makes a good life?",
            "author": "Robert Waldinger (TED)",
            "url": "https://www.ted.com/talks/robert_waldinger_what_makes_a_good_life_lessons_from_the_longest_study_on_happiness",
            "why": "75-year Harvard study on what actually predicts health and happiness.",
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
        {
            "type": "video",
            "title": "The first 20 hours",
            "author": "Josh Kaufman (TEDx)",
            "url": "https://www.ted.com/talks/josh_kaufman_the_first_20_hours_how_to_learn_anything",
            "why": "Breaks the myth that mastering a new skill requires 10,000 hours.",
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


def _phrase_matches(text: str, phrase: str) -> bool:
    tokens = re.findall(r"[a-z0-9']+", phrase.lower())
    if not tokens:
        return False

    pattern = r"\b" + r"\s+".join(re.escape(token) for token in tokens) + r"\b"
    return re.search(pattern, text) is not None


def _phrase_is_negated(text: str, phrase: str) -> bool:
    tokens = re.findall(r"[a-z0-9']+", phrase.lower())
    if not tokens:
        return False

    phrase_pattern = r"\b" + r"\s+".join(re.escape(token) for token in tokens) + r"\b"
    negation_pattern = r"(?:\bno\b|\bnot\b|\bnever\b|\bnobody\b|\bno one\b|\bwithout\b)[^.!?\n]{0,30}" + phrase_pattern
    return re.search(negation_pattern, text) is not None


def _score_categories(path_a: str, path_b: str, constraints: str | None = None) -> list[tuple[str, int]]:
    combined = " ".join(part for part in (path_a, path_b, constraints or "") if part).lower()
    words = _tokenize(combined)
    scores: list[tuple[str, int]] = []

    for category in CATEGORY_ORDER:
        if category == "general":
            continue
        score = len(words & CATEGORY_KEYWORDS[category])
        for phrase in CATEGORY_PHRASES.get(category, ()):
            if _phrase_matches(combined, phrase):
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


def detect_primary_bottleneck(
    path_a: str,
    path_b: str,
    constraints: str | None = None,
    writing_samples: str | None = None,
    decision_category: str | None = None,
) -> str:
    """Infer the user's dominant bottleneck from the intake context."""
    combined = " ".join(part for part in (path_a, path_b, constraints or "", writing_samples or "") if part).lower()
    scores = defaultdict(int)

    for bottleneck, phrases in BOTTLENECK_PATTERNS.items():
        for phrase in phrases:
            if _phrase_matches(combined, phrase) and not _phrase_is_negated(combined, phrase):
                scores[bottleneck] += 1

    if scores:
        return max(BOTTLENECK_TAXONOMY, key=lambda key: (scores[key], -BOTTLENECK_TAXONOMY.index(key)))

    category = (decision_category or select_relevant_categories(path_a, path_b, constraints)[:1] or ["general"])[0]
    return DEFAULT_BOTTLENECK_BY_CATEGORY.get(category, "perfectionism")


def _score_resource(
    resource: dict,
    *,
    primary_category: str,
    secondary_categories: list[str],
    bottleneck: str,
) -> int:
    score = 0
    resource_category = resource.get("category", "general")
    if resource_category == primary_category:
        score += 5
    elif resource_category in secondary_categories:
        score += 3
    elif resource_category == "general":
        score += 1

    tags = RESOURCE_BOTTLENECK_TAGS.get((resource["type"], resource["title"]), ())
    if bottleneck in tags:
        score += 5
    elif tags:
        score += 1

    return score


def _build_personalized_why(resource: dict, bottleneck: str) -> str:
    base = resource.get("why", "").strip().rstrip(".")
    type_suffixes = BOTTLENECK_WHY_SUFFIX.get(bottleneck, {})
    suffix = type_suffixes.get(resource.get("type", ""), "")
    if not base:
        return suffix or "It directly addresses the pressure sitting underneath this decision."
    if not suffix:
        return f"{base}."
    return f"{base}. {suffix}"


def select_deterministic_resources(
    path_a: str,
    path_b: str,
    constraints: str | None = None,
    *,
    writing_samples: str | None = None,
    max_items: int = 3,
    decision_category: str | None = None,
) -> tuple[list[dict], str]:
    """Pick one vetted book, video, and concept using category + bottleneck scoring."""
    selected_categories = select_relevant_categories(path_a, path_b, constraints)
    primary_category = (decision_category or (selected_categories[0] if selected_categories else "general")).lower()
    secondary_categories = [category for category in selected_categories if category != primary_category]
    bottleneck = detect_primary_bottleneck(
        path_a,
        path_b,
        constraints,
        writing_samples=writing_samples,
        decision_category=primary_category,
    )

    candidates = shortlist_resource_candidates(
        path_a,
        path_b,
        constraints,
        max_candidates=24,
        decision_category=primary_category,
    )

    picks: list[dict] = []
    for resource_type in ELIGIBLE_TIMELINE_TYPES:
        typed_candidates = [resource for resource in candidates if resource["type"] == resource_type]
        if not typed_candidates:
            continue
        ranked = sorted(
            typed_candidates,
            key=lambda resource: (
                -_score_resource(
                    resource,
                    primary_category=primary_category,
                    secondary_categories=secondary_categories,
                    bottleneck=bottleneck,
                ),
                resource["title"],
            ),
        )
        chosen = dict(ranked[0])
        chosen.pop("category", None)
        chosen["why"] = _build_personalized_why(chosen, bottleneck)
        picks.append(chosen)

    return picks[:max_items], bottleneck


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
    writing_samples: str | None = None,
) -> list[dict]:
    """Return a diverse deterministic fallback recommendation trio."""
    picks, _ = select_deterministic_resources(
        path_a,
        path_b,
        constraints,
        writing_samples=writing_samples,
        max_items=max_items,
        decision_category=decision_category,
    )
    return picks


def select_timeline_resources(
    path_a: str,
    path_b: str,
    constraints: str | None = None,
    *,
    writing_samples: str | None = None,
    decision_category: str | None = None,
) -> tuple[list[dict], str]:
    """Return structured stage-06 resources with server-generated explanations."""
    picks, bottleneck = select_deterministic_resources(
        path_a,
        path_b,
        constraints,
        writing_samples=writing_samples,
        max_items=3,
        decision_category=decision_category,
    )
    items = [
        {
            "type": resource["type"],
            "title": resource["title"],
            "author": resource["author"],
            "why_it_helps": resource["why"],
            "url": resource["url"],
        }
        for resource in picks
    ]
    return items, bottleneck
