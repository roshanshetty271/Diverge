"""Diagnostic: monkey-patch every debate tool to record calls, then run one
debate per scenario and report which tools were actually invoked.

Originally answered the question: 'is the knowledge base / research / salary
/ runway / Monte Carlo tooling ever actually used by the model during a
debate?' The first run proved zero invocations across all five tools.

Now also verifies the pre-retrieval grounding pipeline is doing its job:
- `_retrieve_research_content` should fire EXACTLY ONCE per debate (called by
  `app.grounding.build_grounding_context`, not by the model).
- `calculate_runway.__wrapped__` and `monte_carlo_financial.__wrapped__`
  should fire only when `financial_context` yields the right shape of dollar
  figures AND the category permits financial modeling.
- The original @tool wrappers should still show zero invocations from the
  model — confirming the activation comes from grounding, not from the LLM
  suddenly deciding to call tools.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

# Import the orchestrator namespace so we can mutate its tool references before
# TOOL_MAP is rebuilt during a run. Tools are re-read from TOOL_MAP each debate
# via `TOOL_MAP.get(category, [research_insight])`, so patching inside the tool
# modules themselves and inside TOOL_MAP is the complete fix.
from app import grounding, orchestrator  # noqa: E402
from app.tools import knowledge, data_tools, monte_carlo  # noqa: E402

CALL_COUNTS: Counter[str] = Counter()


def _wrap(name, fn):
    # Strands' @tool decorator exposes the underlying callable at fn.__wrapped__
    # in some SDK versions and as the object itself in others. We handle both.
    target = getattr(fn, "__wrapped__", fn)

    def traced(*args, **kwargs):
        CALL_COUNTS[name] += 1
        print(f"  >>> TOOL CALLED: {name} args={args!r} kwargs={kwargs!r}", flush=True)
        return target(*args, **kwargs)

    # Preserve the wrapper so Strands still sees it as a tool.
    if hasattr(fn, "tool_spec"):
        traced.tool_spec = fn.tool_spec  # type: ignore[attr-defined]
    if hasattr(fn, "__name__"):
        traced.__name__ = name
    return traced


# Patch each @tool wrapper in its source module AND in any local references the
# orchestrator pulled at import time. Counts here measure *model-initiated*
# tool calls (which we expect to remain zero — grounding is doing the work now).
_TOOLS_TO_TRACE = {
    "research_insight": (knowledge, "research_insight"),
    "get_salary_data": (data_tools, "get_salary_data"),
    "compare_cost_of_living": (data_tools, "compare_cost_of_living"),
    "calculate_runway": (data_tools, "calculate_runway"),
    "monte_carlo_financial": (monte_carlo, "monte_carlo_financial"),
}

for name, (mod, attr) in _TOOLS_TO_TRACE.items():
    original = getattr(mod, attr)
    traced = _wrap(name, original)
    setattr(mod, attr, traced)
    if hasattr(orchestrator, attr):
        setattr(orchestrator, attr, traced)

# Rebuild TOOL_MAP with the traced versions so agents receive them.
from app.tools.knowledge import research_insight  # noqa: E402
from app.tools.data_tools import get_salary_data, compare_cost_of_living, calculate_runway  # noqa: E402
from app.tools.monte_carlo import monte_carlo_financial  # noqa: E402

FINANCIAL_TOOLS = [monte_carlo_financial, get_salary_data, compare_cost_of_living, calculate_runway]

orchestrator.TOOL_MAP = {
    "career":       [research_insight, get_salary_data, compare_cost_of_living],
    "startup":      [research_insight, monte_carlo_financial, calculate_runway],
    "financial":    [research_insight] + FINANCIAL_TOOLS,
    "education":    [research_insight, get_salary_data],
    "relationship": [research_insight],
    "health":       [research_insight],
    "general":      [research_insight],
}


# Patch the grounding pipeline's actual call-sites. These are what fire the
# financial models / research today (the @tool wrappers above stay dormant
# because GPT-4o-mini doesn't reliably initiate tool calls).
def _patch_grounding():
    orig_research = grounding._safe_research
    orig_runway = grounding._safe_runway
    orig_mc = grounding._safe_monte_carlo

    def traced_research(*args, **kwargs):
        CALL_COUNTS["grounding._safe_research"] += 1
        print(f"  >>> GROUNDING: research retrieval args={args!r}", flush=True)
        return orig_research(*args, **kwargs)

    def traced_runway(*args, **kwargs):
        CALL_COUNTS["grounding._safe_runway"] += 1
        print(f"  >>> GROUNDING: runway computation args={args!r}", flush=True)
        return orig_runway(*args, **kwargs)

    def traced_mc(*args, **kwargs):
        CALL_COUNTS["grounding._safe_monte_carlo"] += 1
        print(f"  >>> GROUNDING: monte_carlo computation args={args!r}", flush=True)
        return orig_mc(*args, **kwargs)

    grounding._safe_research = traced_research
    grounding._safe_runway = traced_runway
    grounding._safe_monte_carlo = traced_mc


_patch_grounding()


# ── Scenarios ──────────────────────────────────────────────────────

CAREER_SCENARIO = {
    "name": "career_no_monthly_expenses",
    "input": {
        "path_a": "Stay at my stable enterprise IT job",
        "path_b": "Leave and go all-in on cloud and AI",
        "template_id": "career",
        "user_name": "Alex",
        "age": 28,
        "financial_context": (
            "Current income: $78K/yr. Cloud role: $110K/yr but no offer yet. "
            "Savings: $15K. Student loans: $22K remaining."
        ),
        "values": "growth, impact, financial stability",
        "constraints": (
            "I manage legacy infrastructure at a company that won't modernize. "
            "I've been learning AWS on my own for 8 months."
        ),
    },
    # Career scenario has yearly salaries and a debt balance but no monthly
    # expenses → runway/MC must NOT fire (would require fabricating an
    # expenses figure). Research SHOULD fire.
    "expected": {
        "grounding._safe_research": 1,
        "grounding._safe_runway": 0,
        "grounding._safe_monte_carlo": 0,
    },
}

STARTUP_SCENARIO = {
    "name": "startup_with_monthly_figures",
    "input": {
        "path_a": "Stay at my day job at the agency",
        "path_b": "Quit to launch the SaaS startup full-time",
        "template_id": "startup",
        "user_name": "Sam",
        "age": 31,
        "financial_context": (
            "Savings $50K. Day-job income $8K/mo. "
            "Startup income $1K/mo for the first year. "
            "Monthly expenses $4K covers rent and food."
        ),
        "values": "autonomy, ownership, learning",
        "constraints": (
            "Two cofounders. We have one paying customer and a waitlist of 40. "
            "No outside funding yet."
        ),
    },
    # Has savings + 2 monthly incomes + monthly expenses + startup category
    # → both runway and Monte Carlo must fire.
    "expected": {
        "grounding._safe_research": 1,
        "grounding._safe_runway": 1,
        "grounding._safe_monte_carlo": 1,
    },
}


def _run_one(scenario: dict) -> dict:
    name = scenario["name"]
    print(f"\n[{time.strftime('%H:%M:%S')}] Running scenario: {name}", flush=True)
    CALL_COUNTS.clear()
    t0 = time.time()
    resp = orchestrator.run_debate(dict(scenario["input"]))
    elapsed = time.time() - t0

    print(
        f"\n  [{name}] complete in {elapsed:.1f}s. "
        f"Completed {resp.completed_rounds}/{resp.total_rounds} rounds.",
        flush=True,
    )

    counts = dict(CALL_COUNTS)
    print(f"  [{name}] call counts: {counts}")

    # Verify expectations
    failures: list[str] = []
    for key, expected in scenario["expected"].items():
        actual = counts.get(key, 0)
        if actual != expected:
            failures.append(f"{key}: expected {expected}, got {actual}")

    return {"name": name, "counts": counts, "failures": failures, "elapsed_s": round(elapsed, 1)}


def main():
    print(f"Tool-invocation audit starting at {time.strftime('%H:%M:%S')}", flush=True)
    results: list[dict] = []
    for scenario in (CAREER_SCENARIO, STARTUP_SCENARIO):
        try:
            results.append(_run_one(scenario))
        except Exception as exc:
            print(f"  [{scenario['name']}] FAILED: {exc}", flush=True)
            results.append({"name": scenario["name"], "failures": [str(exc)]})

    print("\n===== AUDIT SUMMARY =====")
    overall_ok = True
    for r in results:
        status = "PASS" if not r.get("failures") else "FAIL"
        if r.get("failures"):
            overall_ok = False
        print(f"  {r['name']:<35} {status}  ({r.get('elapsed_s', '?')}s)")
        for fail in r.get("failures", []):
            print(f"    - {fail}")

    print("\nModel-initiated @tool calls across both runs (expected to be ~0):")
    for tool_name in _TOOLS_TO_TRACE:
        # CALL_COUNTS was reset between scenarios so this only reflects the
        # last run; we just want to flag if the model started calling tools.
        n = CALL_COUNTS.get(tool_name, 0)
        if n:
            print(f"  - {tool_name}: {n}")
    if all(CALL_COUNTS.get(name, 0) == 0 for name in _TOOLS_TO_TRACE):
        print("  (none — model still doesn't self-initiate tool calls; grounding is the activation path.)")

    print("\nOverall:", "PASS" if overall_ok else "FAIL")
    if not overall_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
