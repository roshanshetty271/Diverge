"""Run the best demo-video scenario: career pivot into cloud/AI — relatable to AWS Builder judges."""

import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests

DEBATE_BASE = "https://nj4y3i5l3ezxlr2cu2k2lemcn40qghrk.lambda-url.us-east-1.on.aws"
TIMEOUT = 300


SCENARIOS = [
    {
        "name": "Cloud Career Pivot",
        "input": {
            "path_a": "Stay at my stable enterprise IT job",
            "path_b": "Leave and go all-in on cloud and AI",
            "template_id": "career",
            "user_name": "Alex",
            "age": 28,
            "financial_context": "Current income: $78K/yr. Cloud role: $110K/yr but no offer yet. Savings: $15K. Student loans: $22K remaining.",
            "values": "growth, impact, financial stability",
            "constraints": "I manage legacy infrastructure at a company that won't modernize. I've been learning AWS on my own for 8 months. I passed the Solutions Architect cert but have no production cloud experience. My manager says I'm next in line for a promotion.",
        },
        "interjection_after_round": 2,
        "interjection_text": "I just got an interview for a cloud engineer role at a startup building on AWS. They said they'd mentor me but the pay is only $85K to start.",
    },
    {
        "name": "Career Crossroads - Broad Appeal",
        "input": {
            "path_a": "Accept the promotion and stay on the management track",
            "path_b": "Turn it down, go back to building, and bet on the role I actually want",
            "template_id": "career",
            "user_name": "Jordan",
            "age": 30,
            "financial_context": "Current income: $105K/yr. Promotion: $130K/yr. If I leave for the builder role: probably $95K to start. Savings: $28K.",
            "values": "craft, autonomy, financial security",
            "constraints": "I'm good at managing but it drains me. I miss building things. The promotion comes with a team of 8 and a title bump, but I'd spend my days in meetings. The builder role I want doesn't exist at my company — I'd have to leave.",
            "writing_samples": "Every Sunday night I feel a knot in my chest thinking about Monday.\nI keep saying next quarter will be different but it never is.\nThe last time I felt alive at work was shipping a feature at 2 AM three years ago.",
        },
        "interjection_after_round": 2,
        "interjection_text": "My skip-level manager just told me the promotion comes with a $25K signing bonus and they're willing to let me keep one technical project on the side",
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
    print(f"  Interjection after R{interjection_round}: \"{interjection_text}\"")
    print(f"{'='*70}")

    round_times = []
    total_start = time.time()

    # Round 1
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
    print(f"\n    === ALPHA ({len(r1['alpha'])} chars) ===")
    print(f"    {r1['alpha'][:300]}...")
    print(f"\n    === BETA ({len(r1['beta'])} chars) ===")
    print(f"    {r1['beta'][:300]}...")

    # Rounds 2-5
    for round_num in range(2, 6):
        interjection = None
        if round_num == interjection_round + 1:
            interjection = interjection_text
            print(f"\n  {'>'*5} INTERJECTION: \"{interjection}\"")

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
            print(f"\n    === ALPHA ({len(r['alpha'])} chars) ===")
            print(f"    {r['alpha'][:300]}...")
            print(f"\n    === BETA ({len(r['beta'])} chars) ===")
            print(f"    {r['beta'][:300]}...")

            # Check interjection pickup
            if interjection and round_num == interjection_round + 1:
                # Check for key phrases from interjection
                alpha_lower = r["alpha"].lower()
                beta_lower = r["beta"].lower()
                keywords_to_check = ["interview", "cloud engineer", "startup", "mentor", "$85k"] if "interview" in interjection.lower() else ["bonus", "signing", "$25k", "technical project", "skip"]
                alpha_hits = [kw for kw in keywords_to_check if kw in alpha_lower]
                beta_hits = [kw for kw in keywords_to_check if kw in beta_lower]
                print(f"\n    INTERJECTION PICKUP:")
                print(f"      Alpha references: {alpha_hits or 'none'}")
                print(f"      Beta references: {beta_hits or 'none'}")

        # Final round extras
        if data.get("verdict") and round_num == 5:
            print(f"\n  {'─'*60}")
            print(f"  FULL VERDICT ({len(data['verdict'])} chars):")
            for line in data["verdict"].split("\n"):
                print(f"    {line}")

            if data.get("timeline"):
                tl = data["timeline"]
                print(f"\n  FULL TIMELINE:")
                stages = [
                    ("Year 1 - The Ripple", "stage_01_the_ripple_year_1"),
                    ("Year 3 - The Ledger", "stage_02_the_ledger_year_3"),
                    ("Year 5 - The Mirror", "stage_03_the_mirror_year_5"),
                    ("Year 10 - The Ghost", "stage_04_the_ghost_year_10"),
                    ("Final Words - The Knot", "stage_05_the_knot_final_words"),
                ]
                for label, key in stages:
                    stage = tl.get(key, {})
                    print(f"\n    {label}:")
                    print(f"      SAFE: {stage.get('path_a_safe', 'N/A')}")
                    print(f"      BOLD: {stage.get('path_b_bet', 'N/A')}")
                    if "verdict_path_of_least_regret" in stage:
                        print(f"      VERDICT: {stage['verdict_path_of_least_regret']}")

                if tl.get("stage_06_what_to_explore_next"):
                    print(f"\n  RESOURCES:")
                    for res in tl["stage_06_what_to_explore_next"]:
                        print(f"    [{res['type'].upper()}] {res['title']} - {res['author']}")
                        print(f"      {res['why_it_helps']}")

    total_time = time.time() - total_start
    print(f"\n  {'─'*60}")
    print(f"  TIMING SUMMARY:")
    for i, t in enumerate(round_times):
        tag = " << INTERJECTION" if i + 1 == interjection_round + 1 else ""
        print(f"    Round {i+1}: {t:.1f}s{tag}")
    print(f"    TOTAL: {total_time:.1f}s ({total_time/60:.1f} min)")

    return {"name": name, "total": total_time, "rounds": round_times}


if __name__ == "__main__":
    print(f"Demo scenario test — {time.strftime('%H:%M:%S')}")
    results = []
    for s in SCENARIOS:
        try:
            results.append(run_scenario(s))
        except Exception as e:
            print(f"\n  FAILED: {s['name']}: {e}")

    print(f"\n\n{'='*70}")
    print("COMPARISON")
    print(f"{'='*70}")
    for r in results:
        print(f"  {r['name']}: {r['total']:.0f}s total, rounds: {' / '.join(f'{t:.0f}s' for t in r['rounds'])}")
