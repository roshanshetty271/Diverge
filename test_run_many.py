"""Run multiple checkpointed debates end-to-end and save raw JSON for each."""

import concurrent.futures
import json
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEBATE_BASE = "https://d1re6fh5kw2kbg.cloudfront.net"
TIMEOUT = 300

ROBOTIC_FALLBACK_PATTERNS = [
    "Right now, living with",
    "This path gives something real",
    "The tradeoff behind this",
    "Nothing here is clean",
    "version of life you would have to keep waking up inside",
    "This perspective could not be generated",
]

SCENARIOS = [
    {
        "name": "Relationship_Confession",
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
        "interjection_after_round": 2,
        "interjection_text": "She just texted me asking to grab dinner alone this weekend to 'catch up about something important'.",
    },
    {
        "name": "Startup_Quit_Job",
        "input": {
            "path_a": "Stay employed and keep building my idea nights and weekends",
            "path_b": "Quit now and go all-in on the startup",
            "template_id": "startup",
            "user_name": "Ava",
            "age": 29,
            "financial_context": "Current income: $140K/yr. Startup income: $0 for at least 6 months. Savings: $85K. Partner income: $60K/yr.",
            "values": "autonomy, creativity, stability",
            "constraints": (
                "I already have 4 paying customers at $500/mo each. "
                "My partner wants us to start a family in the next 2 years. "
                "I can handle risk, but not chaos without a plan."
            ),
        },
        "interjection_after_round": 2,
        "interjection_text": "A former VP just offered to advise us and introduce me to angel investors if I go all-in.",
    },
    {
        "name": "Family_vs_Career",
        "input": {
            "path_a": "Stay home and help run the family restaurant",
            "path_b": "Take the strategy job in Chicago and send money home",
            "template_id": "family",
            "user_name": "Sofia",
            "age": 32,
            "financial_context": "Current income: $42K from family business. New role: $135K/yr. Savings: $14K.",
            "values": "duty, ambition, generational mobility",
            "constraints": (
                "My parents depend on me more than they admit. "
                "My younger brother is not ready to step up yet. "
                "This offer could change my financial ceiling."
            ),
        },
        "interjection_after_round": 3,
        "interjection_text": "My brother just said he'd come home after college if I take the Chicago role.",
    },
]


def run_scenario(scenario: dict) -> dict:
    name = scenario["name"]
    inp = scenario["input"]
    inj_round = scenario["interjection_after_round"]
    inj_text = scenario["interjection_text"]

    out = {
        "scenario": name,
        "input": inp,
        "interjection": {"after_round": inj_round, "text": inj_text},
        "rounds": [],
        "quality_warnings": [],
    }

    total_start = time.time()

    t0 = time.time()
    r = requests.post(f"{DEBATE_BASE}/api/debate/session/start", json=inp, timeout=TIMEOUT)
    r.raise_for_status()
    elapsed = time.time() - t0
    data = r.json()
    debate_id = data["debate_id"]
    out["debate_id"] = debate_id

    r1 = data["transcript"][-1]
    out["rounds"].append({
        "round": 1, "name": r1["round_name"], "elapsed_s": round(elapsed, 2),
        "alpha_chars": len(r1["alpha"]), "beta_chars": len(r1["beta"]),
        "alpha": r1["alpha"], "beta": r1["beta"],
        "metrics": r1.get("metrics"), "sentiment": r1.get("sentiment"),
        "interjection": None,
    })
    print(f"  [{name}] R1 {elapsed:.1f}s", flush=True)

    for n in range(2, 6):
        inj = inj_text if n == inj_round + 1 else None
        t0 = time.time()
        r = requests.post(
            f"{DEBATE_BASE}/api/debate/session/{debate_id}/continue",
            json={"interjection": inj},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        elapsed = time.time() - t0
        data = r.json()
        rN = data["transcript"][-1]
        out["rounds"].append({
            "round": n, "name": rN["round_name"], "elapsed_s": round(elapsed, 2),
            "alpha_chars": len(rN["alpha"]), "beta_chars": len(rN["beta"]),
            "alpha": rN["alpha"], "beta": rN["beta"],
            "metrics": rN.get("metrics"), "sentiment": rN.get("sentiment"),
            "interjection": inj,
        })
        tag = " [INJ]" if inj else ""
        print(f"  [{name}] R{n} {elapsed:.1f}s{tag}", flush=True)

    out["verdict"] = data.get("verdict", "")
    out["timeline"] = data.get("timeline")
    out["resources"] = data.get("resources", [])
    out["total_elapsed_s"] = round(time.time() - total_start, 2)
    out["total_elapsed_min"] = round(out["total_elapsed_s"] / 60, 2)
    out["quality_warnings"] = find_quality_warnings(out)

    Path("test_results").mkdir(exist_ok=True)
    (Path("test_results") / f"{name}_live.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    return out


def find_quality_warnings(result: dict) -> list[str]:
    warnings = []
    for rd in result.get("rounds", []):
        for side in ("alpha", "beta"):
            text = rd.get(side, "")
            for pattern in ROBOTIC_FALLBACK_PATTERNS:
                if pattern in text:
                    warnings.append(
                        f"R{rd['round']} {side} matched robotic fallback pattern: {pattern!r}"
                    )
    return warnings


def main():
    print(f"Starting 3 scenarios in parallel at {time.strftime('%H:%M:%S')}", flush=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(run_scenario, s): s["name"] for s in SCENARIOS}
        for fut in concurrent.futures.as_completed(futures):
            name = futures[fut]
            try:
                results.append(fut.result())
                print(f"  DONE: {name}", flush=True)
            except Exception as e:
                print(f"  FAILED: {name}: {e}", flush=True)
                results.append({"scenario": name, "error": str(e)})

    print("\n===== SUMMARY =====")
    had_quality_warnings = False
    for r in sorted(results, key=lambda x: x.get("scenario", "")):
        if "error" in r:
            print(f"  {r['scenario']}: FAILED - {r['error']}")
            continue
        rounds = " / ".join(f"{rd['elapsed_s']:.0f}s" for rd in r["rounds"])
        quality = "WARN" if r.get("quality_warnings") else "PASS"
        had_quality_warnings = had_quality_warnings or bool(r.get("quality_warnings"))
        print(
            f"  {r['scenario']:<30} total={r['total_elapsed_s']:.1f}s  "
            f"rounds={rounds}  verdict={len(r['verdict'])}ch  "
            f"timeline={'Y' if r['timeline'] else 'N'}  quality={quality}"
        )
        for warning in r.get("quality_warnings", []):
            print(f"    QUALITY: {warning}")

    if any("error" in r for r in results) or had_quality_warnings:
        sys.exit(1)


if __name__ == "__main__":
    main()
