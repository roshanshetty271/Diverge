"""Shared decision template catalog.

The backend is the single source of truth for all first-party templates.
Frontend consumers should read these via /api/templates rather than
re-declaring local copies.
"""

from __future__ import annotations

from dataclasses import dataclass


DEBATE_CATEGORIES = {
    "career",
    "startup",
    "relationship",
    "health",
    "education",
    "financial",
    "general",
}


FINANCIAL_CONTEXT_CATEGORIES = {"career", "startup", "education", "financial"}


@dataclass(frozen=True)
class TemplateCatalogItem:
    id: str
    emoji: str
    title: str
    question: str
    path_a: str
    path_b: str
    category: str

    @property
    def needs_financial_context(self) -> bool:
        return self.category in FINANCIAL_CONTEXT_CATEGORIES

    def to_api_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "emoji": self.emoji,
            "title": self.title,
            "question": self.question,
            "pathA": self.path_a,
            "pathB": self.path_b,
            "category": self.category,
        }


TEMPLATE_CATALOG: tuple[TemplateCatalogItem, ...] = (
    TemplateCatalogItem(
        id="career",
        emoji="💼",
        title="Career Change",
        question="Should I stay or take the new offer?",
        path_a="Stay at my current job",
        path_b="Take the new opportunity",
        category="career",
    ),
    TemplateCatalogItem(
        id="city",
        emoji="🏙️",
        title="New City",
        question="Should I move or stay put?",
        path_a="Stay in my current city",
        path_b="Move somewhere new",
        category="financial",
    ),
    TemplateCatalogItem(
        id="startup",
        emoji="🚀",
        title="Launch a Startup",
        question="Should I go for it or play it safe?",
        path_a="Stay employed",
        path_b="Start my own thing",
        category="startup",
    ),
    TemplateCatalogItem(
        id="education",
        emoji="🎓",
        title="Education",
        question="Should I study or keep working?",
        path_a="Keep working",
        path_b="Go back to school",
        category="education",
    ),
    TemplateCatalogItem(
        id="relationship",
        emoji="❤️",
        title="Relationship",
        question="Should I say something or let it go?",
        path_a="Say what I feel",
        path_b="Keep it to myself",
        category="relationship",
    ),
    TemplateCatalogItem(
        id="lifestyle",
        emoji="🌿",
        title="Lifestyle Change",
        question="Should I make the change or stay comfortable?",
        path_a="Commit to the change",
        path_b="Keep things as they are",
        category="health",
    ),
    TemplateCatalogItem(
        id="volunteer",
        emoji="🤝",
        title="Give Back",
        question="How should I serve my community?",
        path_a="Volunteer locally with what I know",
        path_b="Go where the need is greatest",
        category="general",
    ),
    TemplateCatalogItem(
        id="trade",
        emoji="🛠️",
        title="Trade vs. Degree",
        question="What's the smartest path forward?",
        path_a="Learn a skilled trade",
        path_b="Pursue a 4-year degree",
        category="education",
    ),
    TemplateCatalogItem(
        id="family",
        emoji="🏠",
        title="Family Crossroads",
        question="How do I balance what I want with what they need?",
        path_a="Prioritize family stability",
        path_b="Take the risk for a better future",
        category="general",
    ),
)


TEMPLATE_INDEX = {template.id: template for template in TEMPLATE_CATALOG}


def get_template_catalog() -> list[TemplateCatalogItem]:
    """Return all first-party templates."""
    return list(TEMPLATE_CATALOG)


def get_template_by_id(template_id: str | None) -> TemplateCatalogItem | None:
    """Look up a template by id."""
    if not template_id:
        return None
    return TEMPLATE_INDEX.get(template_id)
