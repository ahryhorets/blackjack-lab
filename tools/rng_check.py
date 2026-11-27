#!/usr/bin/env python3
"""
tools/rng_check.py - does the random generator change any published result?

Question (from a reader): every number on the findings page comes from
Python's default generator, the Mersenne Twister (random.Random), which is
fast and seedable but NOT cryptographically secure. Would the results hold
with OS-level randomness (random.SystemRandom, i.e. os.urandom)?

Method
1. tools/experiments.py runs the WHOLE published suite twice, same sizes:
     python3 tools/experiments.py                 -> docs/results.json
     python3 tools/experiments.py --system-rng    -> docs/results_systemrandom.json
2. This script compares every published number with a z-score:
       z = (SystemRandom - MersenneTwister) / sqrt(SE_MT^2 + SE_SR^2)
   |z| < 2  -> same result, the gap is normal sampling noise
   |z| 2-3  -> borderline; with ~25 tests, about 1 is EXPECTED by pure chance
   |z| > 3  -> a real difference worth investigating
3. Martingale's "broke after N hands" is ONE random draw per run, so it can't
   be compared from one run each. Here it is repeated 200 times per generator.

    python3 tools/rng_check.py          # needs both JSON files; ~1 min for the martingale part

Output: printed table + docs/rng_check.json
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import sim  # noqa: E402

MT = json.load(open(os.path.join(ROOT, "docs", "results.json")))
SR = json.load(open(os.path.join(ROOT, "docs", "results_systemrandom.json")))
rows: list[dict] = []


def verdict(z: float) -> str:
    a = abs(z)
    return "same" if a < 2 else "borderline" if a < 3 else "DIFFERENT"


def add(group, name, mt, sr, se_mt, se_sr, fmt="pct"):
    z = (sr - mt) / math.sqrt(se_mt ** 2 + se_sr ** 2) if (se_mt or se_sr) else 0.0
    rows.append({"group": group, "name": name, "mt": mt, "sr": sr, "z": z,
                 "verdict": verdict(z), "fmt": fmt})


def se_edge(r):          # sim.py stores the 95% half-width as "ci"
    return r["ci"] / 1.96


# 1. play styles (200k hands each)
for k in MT["styles"]:
    add("play style", k, MT["styles"][k]["edge"], SR["styles"][k]["edge"],
        se_edge(MT["styles"][k]), se_edge(SR["styles"][k]))

# 2. rule tweaks (500k hands each)
for k in MT["rules"]:
    add("rule tweak", k, MT["rules"][k]["edge"], SR["rules"][k]["edge"],
        se_edge(MT["rules"][k]), se_edge(SR["rules"][k]))

# 3. insurance return: each insurance bet pays +2 (prob p) or -1, SD = 3*sqrt(p(1-p))
for src_name in ("always",):
    out = []
    for R in (MT, SR):
        x = R["insurance"][src_name]
        n = x["insurance_staked"] / 5
        p = (x["insurance_return"] + 1) / 3
        out.append((x["insurance_return"], 3 * math.sqrt(p * (1 - p)) / math.sqrt(n)))
    add("insurance", "return on insurance bets", out[0][0], out[1][0], out[0][1], out[1][1])

# 4. stop-win sessions (20,000 sessions)
for key, label in (("share_winning", "sessions that end up"), ("avg_result", "average session (chips)")):
    vals, ses = [], []
    for R in (MT, SR):
        s = R["stop_win"]
        n = s["sessions"]
        vals.append(s[key])
        if key == "share_winning":
            ses.append(math.sqrt(s[key] * (1 - s[key]) / n))
        else:
            sd = s.get("sd_result") or SR["stop_win"]["sd_result"]
            ses.append(sd / math.sqrt(n))
    add("quit while ahead", label, vals[0], vals[1], ses[0], ses[1],
        "pct" if key == "share_winning" else "num")

# 5. 10,000 bankroll over 400 hours: 20 runs each -> proportions of runs
for i, b in enumerate(MT["bankroll"]):
    s = SR["bankroll"][i]
    name = f'{b["play"]}{" + count bets" if b["bet"] == "count" else ", flat"}, unit {b["unit"]:g}'
    for key, label in (("share_down", "runs ending below 10,000"),):
        p1, p2, n = b[key], s[key], b["runs"]
        pooled = (p1 + p2) / 2
        se = math.sqrt(max(pooled * (1 - pooled), 1e-9) / n)
        add("bankroll 10k", f"{name}: {label}", p1, p2, se, se)
    p1, p2, n = b["ruined"] / b["runs"], s["ruined"] / s["runs"], b["runs"]
    pooled = (p1 + p2) / 2
    se = math.sqrt(max(pooled * (1 - pooled), 1e-9) / n)
    add("bankroll 10k", f"{name}: runs that went broke", p1, p2, se, se)

# 6. martingale ruin time: 200 runs per generator (one run proves nothing)
REPS = 200
ruin = {}
for label, factory in (("MT", lambda i: random.Random(5000 + i)),
                       ("SR", lambda i: random.SystemRandom())):
    times = []
    for i in range(REPS):
        r = sim.simulate(200_000, "basic", "martingale", bankroll=2000, rng=factory(i))
        times.append(r["ruined_at"] if r["ruined_at"] is not None else 200_000)
    ruin[label] = times
logs = {k: [math.log(t) for t in v] for k, v in ruin.items()}
add("martingale 2,000 (200 runs each)", "typical hands until broke (log scale)",
    statistics.mean(logs["MT"]), statistics.mean(logs["SR"]),
    statistics.stdev(logs["MT"]) / math.sqrt(REPS), statistics.stdev(logs["SR"]) / math.sqrt(REPS), "num")
mart = {k: {"median": statistics.median(v), "q1": statistics.quantiles(v, n=4)[0],
            "q3": statistics.quantiles(v, n=4)[2], "min": min(v), "max": max(v),
            "share_broke": sum(t < 200_000 for t in v) / REPS} for k, v in ruin.items()}

# ------------------------------------------------------------------ report
def f(x, kind):
    return f"{x * 100:+.2f}%" if kind == "pct" else f"{x:,.2f}"


print(f"\nMersenne Twister (seeded) vs SystemRandom (OS entropy), same experiments\n")
print(f"{'group':<32}{'result':<52}{'MT':>10}{'SysRand':>10}{'z':>7}  verdict")
for r in rows:
    print(f"{r['group']:<32}{r['name'][:51]:<52}{f(r['mt'], r['fmt']):>10}{f(r['sr'], r['fmt']):>10}"
          f"{r['z']:>+7.2f}  {r['verdict']}")
print(f"\nMartingale, hands until broke over {REPS} runs each:")
for k, m in mart.items():
    print(f"  {k}: median {m['median']:,.0f} (middle half {m['q1']:,.0f} to {m['q3']:,.0f}), "
          f"range {m['min']:,} to {m['max']:,}, broke within 200k: {m['share_broke']:.0%}")
n_border = sum(r["verdict"] == "borderline" for r in rows)
n_diff = sum(r["verdict"] == "DIFFERENT" for r in rows)
print(f"\n{len(rows)} comparisons: {len(rows) - n_border - n_diff} same, {n_border} borderline, {n_diff} different.")
print(f"By chance alone, ~{len(rows) * 0.05:.1f} of {len(rows)} would land at |z| >= 2 even with identical generators.")

json.dump({"rows": rows, "martingale": mart, "reps": REPS,
           "mt_generated": MT["generated"], "sr_generated": SR["generated"]},
          open(os.path.join(ROOT, "docs", "rng_check.json"), "w"), indent=1)
print("wrote docs/rng_check.json")
