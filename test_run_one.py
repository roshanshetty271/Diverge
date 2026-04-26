"""Run one checkpointed debate end-to-end, capture timing + full content to JSON."""

import json
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEBATE_BASE = "https://nj4y3i5l3ezxlr2cu2k2lemcn40qghrk.lambda-url.us-east-1.on.aws"
TIMEOUT = 300

SCENARIO = {
    "name": "Career_Pivot_Cloud_AI",
    "input": {
        "path_a": "Stay at my stable enterprise IT job",
        "path_b": "Leave and go all-in on cloud and AI",
        "template_id": "career",
        "user_name": "Alex",
        "age": 28,
        "financial_context": "Current income: $78K/yr. Cloud role: $110K/yr but no offer yet. Savings: $15K. Student loans: $22K remaining.",
        "values": "growth, impact, financial stability",
        "constraints": (
            "I manage legacy infrastructure at a company that won't modernize. "
            "I've been learning AWS on my own for 8 months. I passed the Solutions "
            "Architect cert but have no production cloud experience. My manager "
            "says I'm next in line for a promotion."
        ),
    },
    "interjection_after_round": 2,
    "interjection_text": (
        "I just got an interview for a cloud engineer role at a startup building on AWS. "
        "They said they'd mentor me but the pay is only $85K to start."
    ),
}


def run():
    out = {
        "scenario": SCENARIO["name"],
        "input": SCENARIO["input"],
        "interjection": {
            "after_round": SCENARIO["interjection_after_round"],
            "text": SCENARIO["interjection_text"],
        },
        "rounds": [],
    }

    total_start = time.time()

    # Round 1
    print(f"[{time.strftime('%H:%M:%S')}] POST /session/start", flush=True)
    t0 = time.time()
    r = requests.post(f"{DEBATE_BASE}/api/debate/session/start", json=SCENARIO["input"], timeout=TIMEOUT)
    r.raise_for_status()
    elapsed = time.time() - t0
    data = r.json()
    debate_id = data["debate_id"]
    round1 = data["transcript"][-1]
    out["debate_id"] = debate_id
    out["rounds"].append({
        "round": 1,
        "name": round1["round_name"],
        "title": round1["round_title"],
        "elapsed_s": round(elapsed, 2),
        "alpha_chars": len(round1["alpha"]),
        "beta_chars": len(round1["beta"]),
        "alpha": round1["alpha"],
        "beta": round1["beta"],
        "metrics": round1.get("metrics"),
        "sentiment": round1.get("sentiment"),
        "interjection": None,
    })
    print(f"  R1 done in {elapsed:.1f}s", flush=True)

    # Rounds 2-5
    for n in range(2, 6):
        inj = None
        if n == SCENARIO["interjection_after_round"] + 1:
            inj = SCENARIO["interjection_text"]
            print(f"  >>> INTERJECTING: {inj}", flush=True)

        print(f"[{time.strftime('%H:%M:%S')}] POST /session/{debate_id}/continue (R{n})", flush=True)
        t0 = time.time()
        r = requests.post(
            f"{DEBATE_BASE}/api/debate/session/{debate_id}/continue",
            json={"interjection": inj},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        elapsed = time.time() - t0
        data = r.json()
        roundN = data["transcript"][-1]
        out["rounds"].append({
            "round": n,
            "name": roundN["round_name"],
            "title": roundN["round_title"],
            "elapsed_s": round(elapsed, 2),
            "alpha_chars": len(roundN["alpha"]),
            "beta_chars": len(roundN["beta"]),
            "alpha": roundN["alpha"],
            "beta": roundN["beta"],
            "metrics": roundN.get("metrics"),
            "sentiment": roundN.get("sentiment"),
            "interjection": inj,
        })
        print(f"  R{n} done in {elapsed:.1f}s", flush=True)

    out["verdict"] = data.get("verdict", "")
    out["timeline"] = data.get("timeline")
    out["resources"] = data.get("resources", [])
    out["total_elapsed_s"] = round(time.time() - total_start, 2)
    out["total_elapsed_min"] = round(out["total_elapsed_s"] / 60, 2)

    Path("test_results").mkdir(exist_ok=True)
    out_path = Path("test_results") / f"{SCENARIO['name']}_live.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print("\n===== SUMMARY =====")
    for rd in out["rounds"]:
        tag = " << INTERJECTION" if rd["interjection"] else ""
        print(f"  R{rd['round']} {rd['name']:<12} {rd['elapsed_s']:>6.1f}s  alpha={rd['alpha_chars']:>4}ch beta={rd['beta_chars']:>4}ch{tag}")
    print(f"  TOTAL: {out['total_elapsed_s']}s ({out['total_elapsed_min']} min)")
    print(f"  Verdict: {len(out['verdict'])} chars | Timeline: {bool(out['timeline'])} | Resources: {len(out['resources'])}")
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    run()
