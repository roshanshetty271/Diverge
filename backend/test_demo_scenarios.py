"""Run 3 best demo-video candidate scenarios with detailed timing and quality analysis."""

import sys
import time
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests

DEBATE_BASE = "https://nj4y3i5l3ezxlr2cu2k2lemcn40qghrk.lambda-url.us-east-1.on.aws"
TIMEOUT = 300


SCENARIOS = [
    {
        "name": "Career Decision",
        "input": {
            "path_a": "Stay at my current software job",
            "path_b": "Join an early-stage AI startup for equity",
            "template_id": "career",
            "user_name": "Roshan",
            "age": 26,
            "financial_context": "Current income: $95K/yr. New path income: $70K/yr + equity. Savings: $12K.",
            "values": "growth, financial security, impact",
            "constraints": "I have student loans and no safety net. My family depends on me.",
        },
        "interjection_after_round": 2,
        "interjection_text": "My girlfriend said she'd support me for 6 months if I took the startup offer",
    },
    {
        "name": "Launch a Startup",
        "input": {
            "path_a": "Stay employed and keep building my idea nights and weekends",
            "path_b": "Quit now and go all-in on the startup",
            "template_id": "startup",
            "user_name": "Ava",
            "age": 29,
            "financial_context": "Current income: $140K/yr. Startup income: $0 for at least 6 months. Savings: $85K. Partner income: $60K/yr.",
            "values": "autonomy, creativity, stability",
            "constraints": "I already have a few early customers and real momentum, but my partner wants us to start a family soon. I can handle risk, but not chaos without a plan.",
        },
        "interjection_after_round": 2,
        "interjection_text": "A former VP just offered to advise us and introduce me to angel investors if I go all-in",
    },
    {
        "name": "Family Crossroads",
        "input": {
            "path_a": "Stay home, help run the family restaurant, and keep everyone's life stable",
            "path_b": "Take the strategy job in Chicago and send money home",
            "template_id": "family",
            "user_name": "Sofia",
            "age": 32,
            "financial_context": "Current income: $42K/yr from the family business. New role: $135K/yr. Savings: $14K.",
            "values": "duty, ambition, generational mobility",
            "constraints": "My parents depend on me more than they admit. My younger brother is not ready to step up yet. This offer could change my financial ceiling.",
        },
        "interjection_after_round": 3,
        "interjection_text": "My brother just said he'd come home after college if I take the Chicago role",
    },
]


def run_scenario(scenario):
    name = scenario["name"]
    inp = scenario["input"]
    interjection_round = scenario["interjection_after_round"]
    interjection_text = scenario["interjection_text"]

    print(f"\n{'='*70}")
    print(f"  SCENARIO: {name}")
    print(f"  Path A: {inp['path_a']}")
    print(f"  Path B: {inp['path_b']}")
    print(f"  Interjection after Round {interjection_round}: \"{interjection_text}\"")
    print(f"{'='*70}")

    round_times = []
    total_start = time.time()

    # Round 1 — start
    print(f"\n  Starting Round 1...")
    t0 = time.time()
    resp = requests.post(f"{DEBATE_BASE}/api/debate/session/start", json=inp, timeout=TIMEOUT)
    resp.raise_for_status()
    elapsed = time.time() - t0
    round_times.append(elapsed)
    data = resp.json()
    debate_id = data["debate_id"]

    r1 = data["transcript"][-1]
    print(f"  Round 1 ({r1['round_name']}): {elapsed:.1f}s")
    print(f"    ALPHA ({len(r1['alpha'])} chars): {r1['alpha'][:150]}...")
    print(f"    BETA  ({len(r1['beta'])} chars): {r1['beta'][:150]}...")

    # Rounds 2-5
    for round_num in range(2, 6):
        interjection = None
        if round_num == interjection_round + 1:
            interjection = interjection_text
            print(f"\n  >>> INTERJECTION: \"{interjection}\"")

        print(f"\n  Starting Round {round_num}...")
        t0 = time.time()
        resp = requests.post(
            f"{DEBATE_BASE}/api/debate/session/{debate_id}/continue",
            json={"interjection": interjection},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        elapsed = time.time() - t0
        round_times.append(elapsed)
        data = resp.json()

        if data.get("transcript") and len(data["transcript"]) >= round_num:
            r = data["transcript"][-1]
            print(f"  Round {round_num} ({r['round_name']}): {elapsed:.1f}s")
            print(f"    ALPHA ({len(r['alpha'])} chars): {r['alpha'][:150]}...")
            print(f"    BETA  ({len(r['beta'])} chars): {r['beta'][:150]}...")

            # Check if interjection was picked up
            if interjection and round_num == interjection_round + 1:
                alpha_has = any(kw in r["alpha"].lower() for kw in interjection.lower().split()[:3])
                beta_has = any(kw in r["beta"].lower() for kw in interjection.lower().split()[:3])
                print(f"    INTERJECTION ABSORBED? Alpha={alpha_has}, Beta={beta_has}")
        else:
            print(f"  Round {round_num}: {elapsed:.1f}s (no transcript data)")

        # Final round — show verdict + timeline + resources
        if data.get("verdict") and round_num == 5:
            print(f"\n  {'─'*50}")
            print(f"  VERDICT ({len(data['verdict'])} chars):")
            # Show first 500 chars of verdict
            for line in data["verdict"][:500].split("\n"):
                print(f"    {line}")
            if len(data["verdict"]) > 500:
                print(f"    ... ({len(data['verdict'])} total chars)")

            if data.get("timeline"):
                tl = data["timeline"]
                print(f"\n  TIMELINE:")
                for key in ["stage_01_the_ripple_year_1", "stage_02_the_ledger_year_3",
                           "stage_03_the_mirror_year_5", "stage_04_the_ghost_year_10",
                           "stage_05_the_knot_final_words"]:
                    stage = tl.get(key, {})
                    safe = stage.get("path_a_safe", "")[:100]
                    bet = stage.get("path_b_bet", "")[:100]
                    print(f"    {key.split('_', 2)[-1]}:")
                    print(f"      Safe: {safe}...")
                    print(f"      Bold: {bet}...")

                if tl.get("stage_06_what_to_explore_next"):
                    print(f"\n  RESOURCES:")
                    for res in tl["stage_06_what_to_explore_next"]:
                        print(f"    [{res['type'].upper()}] {res['title']} - {res['author']}")
                        print(f"      Why: {res['why_it_helps'][:120]}...")

            if data.get("resources"):
                print(f"\n  FALLBACK RESOURCES:")
                for res in data["resources"]:
                    print(f"    [{res['type'].upper()}] {res['title']} - {res['author']}")
                    print(f"      Why: {res['why'][:120]}...")

    total_time = time.time() - total_start
    print(f"\n  {'─'*50}")
    print(f"  TIMING SUMMARY for {name}:")
    for i, t in enumerate(round_times):
        label = "  ** INTERJECTION ROUND" if i + 1 == interjection_round + 1 else ""
        print(f"    Round {i+1}: {t:.1f}s{label}")
    print(f"    TOTAL:   {total_time:.1f}s")
    print(f"    Average per round: {total_time/5:.1f}s")

    return {
        "name": name,
        "total": total_time,
        "rounds": round_times,
        "verdict_len": len(data.get("verdict", "")),
        "has_timeline": data.get("timeline") is not None,
        "resource_count": len(data.get("resources", [])),
    }


if __name__ == "__main__":
    print(f"Running 3 demo scenarios at {DEBATE_BASE}")
    print(f"Started: {time.strftime('%H:%M:%S')}")

    results = []
    for scenario in SCENARIOS:
        try:
            result = run_scenario(scenario)
            results.append(result)
        except Exception as e:
            print(f"\n  FAILED: {scenario['name']}: {e}")
            results.append({"name": scenario["name"], "total": 0, "error": str(e)})

    print(f"\n\n{'='*70}")
    print("FINAL COMPARISON")
    print(f"{'='*70}")
    for r in results:
        if "error" in r:
            print(f"  {r['name']}: FAILED - {r['error']}")
        else:
            print(f"  {r['name']}:")
            print(f"    Total time: {r['total']:.1f}s")
            print(f"    Round times: {' / '.join(f'{t:.1f}s' for t in r['rounds'])}")
            print(f"    Verdict: {r['verdict_len']} chars | Timeline: {r['has_timeline']} | Resources: {r['resource_count']}")
    print(f"\nDone: {time.strftime('%H:%M:%S')}")
