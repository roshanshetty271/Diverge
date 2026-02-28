"""Salary and cost-of-living comparison tools.

Edge cases handled:
- JSON data cached at module level (not re-read on every call)
- JSON parse failure → empty list fallback
- Division by zero in COL comparison → guarded
- Missing fields in data entries → .get() with defaults
"""

import json
import logging
from pathlib import Path
from functools import lru_cache
from strands import tool

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent.parent.parent / "data"


@lru_cache(maxsize=4)
def _load_json(filename: str) -> list:
    """Load and cache a JSON data file. Returns empty list on any failure."""
    path = DATA_DIR / filename
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        logger.warning(f"Data file not found: {path}")
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load {filename}: {e}")
    return []


@tool
def get_salary_data(job_title: str, city: str) -> str:
    """Look up median salary for a job title in a specific US city.

    Args:
        job_title: The job title (e.g. "Software Engineer", "Product Manager")
        city: The US city (e.g. "Boston", "Austin", "New York")

    Returns:
        Salary data as formatted text, or a note that data is unavailable
    """
    data = _load_json("salaries.json")
    title_lower = (job_title or "").lower().strip()
    city_lower = (city or "").lower().strip()

    if not title_lower or not city_lower:
        return "Please provide both a job title and city for salary lookup."

    for entry in data:
        entry_city = entry.get("city", "").lower()
        entry_title = entry.get("title", "").lower()
        if city_lower in entry_city and title_lower in entry_title:
            median = entry.get("median", 0)
            low = entry.get("low", 0)
            high = entry.get("high", 0)
            return (
                f"Median salary for {entry.get('title', job_title)} in {entry.get('city', city)}: "
                f"${median:,}/year "
                f"(range: ${low:,} – ${high:,}). "
                f"Source: BLS/Glassdoor estimates."
            )
    return f"No specific salary data found for '{job_title}' in '{city}'. Use national averages or ask the user."


@tool
def compare_cost_of_living(city_a: str, city_b: str) -> str:
    """Compare cost of living between two US cities.

    Args:
        city_a: First city
        city_b: Second city

    Returns:
        Cost comparison as formatted text
    """
    data = _load_json("cost_of_living.json")
    a_data, b_data = None, None

    city_a_lower = (city_a or "").lower().strip()
    city_b_lower = (city_b or "").lower().strip()

    if not city_a_lower or not city_b_lower:
        return "Please provide two city names for comparison."

    for entry in data:
        entry_city = entry.get("city", "").lower()
        if city_a_lower in entry_city:
            a_data = entry
        if city_b_lower in entry_city:
            b_data = entry

    if a_data and b_data:
        b_index = b_data.get("index", 0)
        a_index = a_data.get("index", 0)
        # Guard against division by zero
        if b_index > 0:
            diff = ((a_index - b_index) / b_index) * 100
        else:
            diff = 0
        direction = "more" if diff > 0 else "less"
        return (
            f"{a_data['city']} vs {b_data['city']}: "
            f"{a_data['city']} is {abs(diff):.0f}% {direction} expensive. "
            f"COL index: {a_data['city']}={a_index}, {b_data['city']}={b_index} (NYC=100). "
            f"Avg 1BR rent: {a_data['city']} ${a_data.get('rent_1br', 'N/A')}/mo, "
            f"{b_data['city']} ${b_data.get('rent_1br', 'N/A')}/mo."
        )
    return f"Limited cost-of-living data for this city pair. The agent should reason from general knowledge."


@tool
def calculate_runway(savings: float, monthly_income: float, monthly_expenses: float) -> str:
    """Calculate financial runway — how long savings last given income and expenses.

    Args:
        savings: Current savings in dollars
        monthly_income: Expected monthly income on this path
        monthly_expenses: Expected monthly expenses

    Returns:
        Runway analysis as formatted text
    """
    # Clamp inputs to sane ranges
    savings = max(0.0, float(savings or 0))
    monthly_income = max(0.0, float(monthly_income or 0))
    monthly_expenses = max(0.0, float(monthly_expenses or 0))

    net = monthly_income - monthly_expenses
    if net >= 0:
        annual_savings = net * 12
        return (
            f"Cash-flow positive: +${net:,.0f}/month net. "
            f"Projected annual savings: ${annual_savings:,.0f}. "
            f"Current savings buffer: ${savings:,.0f}. Financial risk: low."
        )
    else:
        burn = abs(net)
        if burn > 0:
            months = savings / burn
        else:
            months = 999  # Shouldn't happen but guard against float edge cases
        return (
            f"Cash-flow negative: -${burn:,.0f}/month burn rate. "
            f"With ${savings:,.0f} in savings, runway is ~{months:.0f} months "
            f"({months / 12:.1f} years) before needing additional income."
        )
