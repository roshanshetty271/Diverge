"""Local regression harness: directly calls run_debate on the CURRENT (fixed) code.

Why not hit the deployed Lambda? It still has the pre-fix code. The plan's scenario
harness was for "after each tier, run test_run_one.py / test_run_many.py and grep the
output for 'My my', 'warm drink', 'Right now, I', 'navigat'". Until we redeploy, the
only honest way to run those greps against the fixed code is to call it in-process.

This script:
  1. Loads the backend .env (so OpenAI key, model IDs are live).
  2. Runs `run_debate` for two scenarios sequentially.
  3. Serializes every round's alpha+beta + verdict into a JSON file per scenario.
  4. Greps the JSONs for the four forbidden substrings and prints a pass/fail table.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load .env before importing app (it reads env on import).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from app.orchestrator import run_debate  # noqa: E402
from app.agents.prompts import detect_decision_category  # noqa: E402


SCENARIOS = [
    {
        "name": "Career_Pivot_Cloud_AI",
        "category": "career",
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
                "I've been learning AWS on my own for 8 months. I passed the Solutions "
                "Architect cert but have no production cloud experience. My manager "
                "says I'm next in line for a promotion."
            ),
        },
    },
    {
        "name": "Relationship_Confession",
        "category": "relationship",
        "input": {
            "path_a": "Stay quiet and keep the friendship as it is",
            "path_b": "Tell my best friend I've been in love with her for three years",
            "template_id": "relationship",
            "user_name": "Dev",
            "age": 27,
            "financial_context": "",
            "values": "honesty, connection, self-respect",
            "constraints": (
                "We have been friends since college. She is currently single. "
                "I have never told anyone how I feel. Our friend group would be "
                "affected if this went badly. I have been stuck on this for three years."
            ),
        },
    },
    {
        # Added to exercise the conditional financial-models grounding path.
        # Has explicit monthly figures so runway + Monte Carlo will fire.
        "name": "Startup_Quit_To_Build",
        "category": "startup",
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
                "No outside funding yet. My partner can cover us for 6 months if needed."
            ),
        },
    },
]

# Case-insensitive, whole-word-ish regression patterns from the plan.
FORBIDDEN = {
    "My my":        re.compile(r"\bmy\s+my\b", re.IGNORECASE),
    "warm drink":   re.compile(r"\bwarm drink\b", re.IGNORECASE),
    "Right now, I": re.compile(r"right now,\s*i['\u2019]?m\b", re.IGNORECASE),
    "navigat":      re.compile(r"\bnavigat(?:e|ed|ing|es)\b", re.IGNORECASE),
}

# Category-specific stat fingerprints from `data/knowledge/chunks.json`. If
# grounding is wired correctly, the BACKGROUND RESEARCH block in each round
# prompt should make at least one of these literal stats land in the output.
# Hit count of 0 across all rounds means the model is ignoring the injected
# block (or the chunk didn't match for that category).
CATEGORY_FINGERPRINTS: dict[str, dict[str, re.Pattern]] = {
    "career": {
        "67%":              re.compile(r"\b67\s*%"),
        "13%":              re.compile(r"\b13\s*%"),
        "5.2%":             re.compile(r"\b5\.2\s*%"),
        "6.3%":             re.compile(r"\b6\.3\s*%"),
        "identity gap":     re.compile(r"identity gap", re.IGNORECASE),
        "18 months":        re.compile(r"\b18\s+months?\b", re.IGNORECASE),
        "72%":              re.compile(r"\b72\s*%"),
    },
    "relationship": {
        "60%":              re.compile(r"\b60\s*%"),
        "70%":              re.compile(r"\b70\s*%"),
        "45%":              re.compile(r"\b45\s*%"),
        "anxious attachment": re.compile(r"anxious attachment", re.IGNORECASE),
        "secure attachment":  re.compile(r"secure attachment", re.IGNORECASE),
        "rejection":          re.compile(r"\brejection\b", re.IGNORECASE),
    },
    "startup": {
        "90%":              re.compile(r"\b90\s*%"),
        "42%":              re.compile(r"\b42\s*%"),
        "product-market fit": re.compile(r"product[-\s]market fit", re.IGNORECASE),
        "18% first-time":   re.compile(r"\b18\s*%"),
        "29% run out":      re.compile(r"\b29\s*%"),
    },
}


def _serialize_debate(scenario_name: str, response) -> dict:
    rounds = []
    for i, rd in enumerate(response.transcript):
        rounds.append({
            "round": i + 1,
            "name": rd.round_name,
            "title": rd.round_title,
            "status": rd.status,
            "alpha": rd.alpha,
            "beta": rd.beta,
            "alpha_chars": len(rd.alpha or ""),
            "beta_chars": len(rd.beta or ""),
        })
    return {
        "scenario": scenario_name,
        "debate_id": response.debate_id,
        "completed_rounds": response.completed_rounds,
        "total_rounds": response.total_rounds,
        "verdict": response.verdict,
        "rounds": rounds,
    }


def _grep_forbidden(payload: dict) -> dict:
    """Search the serialized JSON blob (as a single string) for each forbidden pattern.

    We stringify the whole payload so a hit in any round's alpha/beta, or in the verdict,
    still counts. Line-by-line is unnecessary for a binary pass/fail regression check.
    """
    blob = json.dumps(payload, ensure_ascii=False)
    hits = {}
    for name, pat in FORBIDDEN.items():
        matches = pat.findall(blob)
        hits[name] = len(matches)
    return hits


def _grep_fingerprints(payload: dict, category: str) -> tuple[dict[str, int], int]:
    """Search the debate output for category-specific chunk stats.

    Returns (per-pattern hit counts, total hits). Total hits >= 1 means
    grounding is working — at least one stat from chunks.json reached the
    output. Total hits == 0 means the BACKGROUND RESEARCH block was either
    not injected, or the model ignored it.
    """
    fingerprints = CATEGORY_FINGERPRINTS.get(category, {})
    if not fingerprints:
        return {}, 0
    blob = json.dumps(payload, ensure_ascii=False)
    hits: dict[str, int] = {}
    total = 0
    for name, pat in fingerprints.items():
        count = len(pat.findall(blob))
        if count:
            hits[name] = count
            total += count
    return hits, total


def _run_one(scenario: dict) -> tuple[dict, dict, dict, int]:
    name = scenario["name"]
    declared_category = scenario.get("category", "general")
    inputs = scenario["input"]
    # Use the orchestrator's actual detector so fingerprint lookup matches the
    # chunk that grounding actually injected. Declared category is just an
    # author hint; the runtime category can drift (e.g. a career-vs-startup
    # pivot routes to "startup" because the goal is launching a company).
    detected_category = detect_decision_category(
        inputs.get("path_a", ""),
        inputs.get("path_b", ""),
        inputs.get("constraints"),
        None,
        inputs.get("template_id"),
    )
    print(
        f"\n[{time.strftime('%H:%M:%S')}] Running scenario: {name} "
        f"(declared={declared_category}, detected={detected_category})",
        flush=True,
    )
    t0 = time.time()
    resp = run_debate(dict(inputs))
    elapsed = time.time() - t0

    payload = _serialize_debate(name, resp)
    payload["total_elapsed_s"] = round(elapsed, 2)
    payload["total_elapsed_min"] = round(elapsed / 60, 2)
    payload["declared_category"] = declared_category
    payload["detected_category"] = detected_category
    category = detected_category  # used downstream for fingerprint lookup

    out_dir = ROOT.parent / "test_results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{name}_local.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    hits = _grep_forbidden(payload)
    fingerprint_hits, fingerprint_total = _grep_fingerprints(payload, category)
    print(
        f"  [{name}] done in {elapsed:.1f}s ({elapsed/60:.1f} min), "
        f"completed {payload['completed_rounds']}/{payload['total_rounds']} rounds",
        flush=True,
    )
    print(
        f"  [{name}] forbidden-pattern counts: {hits}",
        flush=True,
    )
    if fingerprint_hits:
        print(
            f"  [{name}] grounding fingerprints ({category}): {fingerprint_hits} "
            f"(total={fingerprint_total})",
            flush=True,
        )
    else:
        print(
            f"  [{name}] grounding fingerprints ({category}): NONE — "
            f"BACKGROUND RESEARCH block did not land in any round",
            flush=True,
        )
    return payload, hits, fingerprint_hits, fingerprint_total


def main():
    print(f"Local regression harness starting at {time.strftime('%H:%M:%S')}", flush=True)
    all_hits: dict[str, dict] = {}
    fingerprint_summary: dict[str, tuple[str, dict, int]] = {}
    all_failed = False
    for scenario in SCENARIOS:
        try:
            payload, hits, fp_hits, fp_total = _run_one(scenario)
            all_hits[scenario["name"]] = hits
            fingerprint_summary[scenario["name"]] = (
                payload.get("detected_category", scenario.get("category", "general")),
                fp_hits,
                fp_total,
            )
        except Exception as exc:
            print(f"  [{scenario['name']}] FAILED: {exc}", flush=True)
            all_hits[scenario["name"]] = {"__error__": str(exc)}
            all_failed = True

    print("\n===== REGRESSION GREP SUMMARY =====")
    header = ["scenario"] + list(FORBIDDEN.keys())
    print("  " + " | ".join(f"{h:<22}" for h in header))
    overall_ok = True
    for name, hits in all_hits.items():
        if "__error__" in hits:
            print(f"  {name:<22} ERROR: {hits['__error__']}")
            overall_ok = False
            continue
        row = [name]
        for k in FORBIDDEN:
            count = hits[k]
            row.append(f"{count} hit{'s' if count != 1 else ''}")
            if count > 0:
                overall_ok = False
        print("  " + " | ".join(f"{c:<22}" for c in row))

    print("\n===== GROUNDING FINGERPRINT SUMMARY =====")
    print("  Target: >= 1 category-specific stat from chunks.json per debate")
    grounding_ok = True
    for name, (category, fp_hits, fp_total) in fingerprint_summary.items():
        if fp_total >= 1:
            verdict = f"OK ({fp_total} hit{'s' if fp_total != 1 else ''})"
        else:
            verdict = "MISS — no chunk stats reached output"
            grounding_ok = False
        print(f"  {name:<26} category={category:<14} {verdict}")
        if fp_hits:
            print(f"    matches: {fp_hits}")

    print(
        "\nForbidden patterns:",
        "PASS — zero forbidden patterns" if overall_ok else "FAIL — at least one pattern still present",
    )
    print(
        "Grounding fingerprints:",
        "PASS — every scenario hit a stat" if grounding_ok else "FAIL — at least one scenario had zero hits",
    )
    if all_failed or not overall_ok or not grounding_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
