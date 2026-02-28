"""Monte Carlo financial projection tool.

Edge cases handled:
- Negative/zero inputs → clamped to safe minimums
- Extremely large inputs → capped to prevent memory/CPU abuse
- Division by zero → guarded
- months=0 → minimum 1
"""

import random
from strands import tool

MAX_MONTHS = 120  # 10 years max
MAX_AMOUNT = 1_000_000_000  # $1B cap


def _clamp_positive(value: float, default: float = 0.0, cap: float = MAX_AMOUNT) -> float:
    """Clamp a financial value to a safe positive range."""
    try:
        v = float(value)
        return max(0.0, min(v, cap))
    except (TypeError, ValueError):
        return default


@tool
def monte_carlo_financial(
    current_savings: float,
    monthly_income_a: float,
    monthly_income_b: float,
    monthly_expenses: float,
    months: int = 60,
) -> str:
    """Run Monte Carlo simulation comparing financial outcomes of two life paths.

    Runs 1000 randomized scenarios per path accounting for income variance,
    expense variance, and unexpected events.

    Args:
        current_savings: Current savings in dollars
        monthly_income_a: Expected monthly income on Path A (staying)
        monthly_income_b: Expected monthly income on Path B (jumping)
        monthly_expenses: Expected monthly expenses
        months: Projection period in months (default 60 = 5 years)

    Returns:
        Formatted comparison with percentile outcomes for both paths
    """
    # Input validation and clamping
    savings = _clamp_positive(current_savings)
    inc_a = _clamp_positive(monthly_income_a)
    inc_b = _clamp_positive(monthly_income_b)
    expenses = _clamp_positive(monthly_expenses, default=1.0)  # avoid 0
    months = max(1, min(int(months), MAX_MONTHS))

    RUNS = 1000

    def simulate(monthly_income: float) -> dict:
        finals = []
        for _ in range(RUNS):
            balance = savings
            for _ in range(months):
                inc = monthly_income * random.uniform(0.80, 1.20)
                exp = expenses * random.uniform(0.85, 1.15)
                # 4% chance of emergency expense per month
                if random.random() < 0.04:
                    exp += expenses * 2
                balance += inc - exp
            finals.append(balance)
        finals.sort()
        total = len(finals)
        return {
            "worst": round(finals[int(total * 0.05)]),
            "median": round(finals[total // 2]),
            "best": round(finals[int(total * 0.95)]),
            "positive_pct": round(sum(1 for f in finals if f > 0) / total * 100, 1),
            "growth_pct": round(sum(1 for f in finals if f > savings) / total * 100, 1),
        }

    a = simulate(inc_a)
    b = simulate(inc_b)

    return (
        f"MONTE CARLO PROJECTION ({RUNS} simulations, {months} months):\n\n"
        f"PATH A — ${inc_a:,.0f}/mo income:\n"
        f"  5th percentile: ${a['worst']:,}\n"
        f"  Median outcome: ${a['median']:,}\n"
        f"  95th percentile: ${a['best']:,}\n"
        f"  Chance of staying above $0: {a['positive_pct']}%\n"
        f"  Chance of growing savings: {a['growth_pct']}%\n\n"
        f"PATH B — ${inc_b:,.0f}/mo income:\n"
        f"  5th percentile: ${b['worst']:,}\n"
        f"  Median outcome: ${b['median']:,}\n"
        f"  95th percentile: ${b['best']:,}\n"
        f"  Chance of staying above $0: {b['positive_pct']}%\n"
        f"  Chance of growing savings: {b['growth_pct']}%"
    )
