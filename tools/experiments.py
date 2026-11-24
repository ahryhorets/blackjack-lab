#!/usr/bin/env python3
"""
tools/experiments.py - every experiment behind the showcase page.

    python3 tools/experiments.py            # ~10 minutes, writes docs/results.json
    python3 tools/experiments.py --quick    # 10x fewer hands, for a fast look

Each experiment uses fixed seeds, so anyone can rerun it and get the same
numbers. The questions it answers:
  A. How much does each way of playing cost (or earn)?
  B. How much do the casino's rule tweaks take (6:5, H17, no surrender)?
  C. Is insurance ever worth it off the top?
  D. "Quit while you're ahead": does a stop-win rule beat the house?
  E. Betting systems on a fixed bankroll: who survives?
  F. A 10,000 bankroll over 400 hours: what does counting really pay?
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import sim                                    # noqa: E402
from cards import Shoe                        # noqa: E402
from rules import RulesConfig                 # noqa: E402
from table import Table                       # noqa: E402

QUICK = "--quick" in sys.argv
K = 10 if QUICK else 1
SEED = 11


def run(n, play="basic", bet="flat", **kw):
    r = sim.simulate(n // K, play, bet, seed=kw.pop("seed", SEED), **kw)
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}


class Insurer(sim.Bot):
    """Basic strategy, but ALWAYS takes insurance (the casino's favourite)."""
    def insurance(self, hand, up, shoe) -> bool:
        return True


def insurance_experiment(n):
    rules = RulesConfig()
    out = {}
    for name, bot in (("never", sim.Bot("basic")), ("always", Insurer("basic"))):
        shoe = Shoe(rules.decks, rules.penetration, random.Random(SEED))
        t = Table(rules, shoe)
        ins_net = ins_staked = net = wag = 0.0
        for _ in range(n // K):
            r = t.play_round(float("inf"), 10, bot)
            ins_net += r.insurance_net
            ins_staked += r.insurance_bet
            net += r.net
            wag += r.wagered
        out[name] = {"net": net, "wagered": wag, "edge": net / wag,
                     "insurance_net": ins_net, "insurance_staked": ins_staked,
                     "insurance_return": ins_net / ins_staked if ins_staked else 0}
    return out


def stop_win_experiment(sessions, win_stop=50, loss_stop=200, max_rounds=300):
    """Sessions of 10-chip bets: leave at +50, at -200, or after 300 rounds."""
    rules = RulesConfig()
    rng = random.Random(SEED)
    bot = sim.Bot("basic")
    results, lengths = [], []
    for s in range(sessions // K):
        shoe = Shoe(rules.decks, rules.penetration, random.Random(rng.random()))
        t = Table(rules, shoe)
        net, n = 0.0, 0
        while n < max_rounds and -loss_stop < net < win_stop:
            net += t.play_round(float("inf"), 10, bot).net
            n += 1
        results.append(net)
        lengths.append(n)
    wins = [x for x in results if x > 0]
    losses = [x for x in results if x < 0]
    total_wag_est = sum(lengths) * 10 * 1.13
    return {"sessions": len(results), "win_stop": win_stop, "loss_stop": loss_stop,
            "max_rounds": max_rounds,
            "share_winning": len(wins) / len(results),
            "avg_win": statistics.mean(wins) if wins else 0,
            "avg_loss": statistics.mean(losses) if losses else 0,
            "avg_result": statistics.mean(results),
            "total_result": sum(results),
            "avg_rounds": statistics.mean(lengths),
            "edge_est": sum(results) / total_wag_est}


def bankroll_experiment(runs=20, rounds=32000):
    out = []
    for play, bet, unit in (("basic", "flat", 25), ("counter", "count", 10),
                            ("counter", "count", 25), ("counter", "count", 50)):
        finals, ruined = [], 0
        for s in range(runs):
            r = sim.simulate(rounds // K, play, bet, unit=unit, bankroll=10000, seed=100 + s)
            finals.append(r["final_balance"])
            ruined += r["ruined_at"] is not None
        out.append({"play": play, "bet": bet, "unit": unit, "runs": runs,
                    "rounds": rounds // K, "median": statistics.median(finals),
                    "mean": statistics.mean(finals), "worst": min(finals),
                    "best": max(finals),
                    "share_down": sum(f < 10000 for f in finals) / runs,
                    "ruined": ruined})
    return out


def main():
    t0 = time.time()
    res = {"seed": SEED, "quick": QUICK, "generated": time.strftime("%Y-%m-%d %H:%M")}
    print("A. play styles...")
    res["styles"] = {name: run(200_000, p, b) for name, p, b in (
        ("basic", "basic", "flat"), ("counter_flat", "counter", "flat"),
        ("counter_spread", "counter", "count"), ("mimic", "mimic", "flat"),
        ("never_bust", "never_bust", "flat"), ("always_hit", "always_hit", "flat"))}
    print("B. casino rule tweaks...")
    res["rules"] = {
        "standard (3:2, S17, surrender, 6 decks)": run(500_000),
        "6:5 blackjack": run(500_000, rules=RulesConfig(blackjack_pays=1.2)),
        "dealer hits soft 17": run(500_000, rules=RulesConfig(dealer_hits_soft17=True)),
        "no surrender": run(500_000, rules=RulesConfig(late_surrender=False)),
        "8 decks": run(500_000, rules=RulesConfig(decks=8)),
    }
    print("C. insurance...")
    res["insurance"] = insurance_experiment(200_000)
    print("D. stop-win sessions...")
    res["stop_win"] = stop_win_experiment(20_000)
    print("E. betting systems on 2,000...")
    res["systems"] = {
        "flat": run(200_000, "basic", "flat", bankroll=2000),
        "martingale": run(200_000, "basic", "martingale", bankroll=2000),
        "count spread": run(200_000, "counter", "count", bankroll=2000),
    }
    print("F. 10,000 bankroll over 400 hours...")
    res["bankroll"] = bankroll_experiment()
    # G. the long run, from the counter-spread numbers
    c = res["styles"]["counter_spread"]
    avg_bet = c["wagered"] / c["rounds"]
    mu, sd = c["edge"] * avg_bet, c["sd_units"] * 10
    res["long_run"] = {"avg_bet": avg_bet, "mu_per_round": mu, "sd_per_round": sd,
                       "n0": (sd / mu) ** 2 if mu > 0 else None,
                       "table": [{"rounds": n, "p_ahead": 0.5 * (1 + math.erf(mu * math.sqrt(n) / sd / math.sqrt(2))),
                                  "expected": mu * n} for n in (1000, 10000, 28000, 76000, 112000)]}
    res["seconds"] = round(time.time() - t0)
    out = os.path.join(ROOT, "docs", "results.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"wrote {out} in {res['seconds']}s")


if __name__ == "__main__":
    main()
