#!/usr/bin/env python3
"""
sim.py - simulator, EV tables and experiments.

Usage (inside the project folder):
    python3 sim.py                                  # 100,000 hands, basic, flat
    python3 sim.py --hands 200000 --play counter --bet count
    python3 sim.py --play basic --bet martingale --bankroll 2000
    python3 sim.py --compare 50000                  # every play style side by side
    python3 sim.py --table                          # dealer odds + stand EVs
    python3 sim.py --cutcard 100000                 # does penetration matter?
    python3 sim.py --seed 7                         # repeatable run

Play styles:
    basic      the basic strategy chart
    counter    chart + Illustrious 18 deviations + insurance at TC >= 3
    mimic      play like the dealer: hit below 17, never double/split
    never_bust stand on hard 12 or more, otherwise hit
    always_hit hit until bust or 21

Bet systems: flat, count (spread 1-12 units by true count), martingale.

STUDY NOTES
- A simulation is an experiment: play many hands, then measure.
  Edge = total won / total wagered. With N hands the 95% confidence
  interval is about edge +/- 1.96 x SD / sqrt(N). With SD ~ 1.15 bets,
  100,000 hands still only pins the edge down to about +/- 0.7%, which
  is wider than the house edge itself. That's why one evening at a
  casino tells you nothing about whether you played well.
- Max drawdown = the biggest fall from a peak. It shows how deep the
  hole gets on the way, which the final result hides.
"""

from __future__ import annotations

import argparse
import math
import random
import time

from cards import Shoe
from rules import RulesConfig
from strategy import (BET_SYSTEMS, chart_move, counted_move, take_insurance)
from table import Table
from ev import Evaluator, dealer_distribution, fresh_counts, OUTCOMES
from cards import KEY_INDEX


class Bot:
    """A player that decides by rule; plugs into Table like a person."""

    def __init__(self, style: str):
        self.style = style

    def insurance(self, hand, up, shoe) -> bool:
        return self.style == "counter" and take_insurance(shoe.true_count())

    def action(self, hand, up, legal, shoe, n_hands, index) -> str:
        s = self.style
        if s == "basic":
            return chart_move(hand, up.key, legal)
        if s == "counter":
            return counted_move(hand, up.key, legal, shoe.true_count())
        if s == "mimic":
            return "hit" if hand.total() < 17 else "stand"
        if s == "never_bust":
            if not hand.is_soft() and hand.total() >= 12:
                return "stand"
            return "hit" if hand.total() < 17 else "stand"
        if s == "always_hit":
            return "hit"
        raise ValueError(s)

    def event(self, kind, data) -> None:
        pass


def simulate(hands: int = 100_000, play: str = "basic", bet: str = "flat",
             unit: float = 10, bankroll: float | None = None,
             rules: RulesConfig | None = None, seed: int | None = None,
             rng: random.Random | None = None) -> dict:
    """Play `hands` rounds. bankroll=None means unlimited money.

    `rng` overrides `seed` entirely when given (e.g. pass
    `random.SystemRandom()` to shuffle from OS entropy instead of the
    default Mersenne Twister PRNG); see tools/rng_check.py.
    """
    rules = rules or RulesConfig()
    shoe = Shoe(rules.decks, rules.penetration, rng or random.Random(seed))
    table = Table(rules, shoe)
    bot = Bot(play)
    system = BET_SYSTEMS[bet]
    balance = bankroll if bankroll is not None else float("inf")
    start = balance
    net = wagered = sum_sq = 0.0
    peak = trough_dd = 0.0
    last_result, last_bet, max_bet = 0.0, unit, 0.0
    ruined_at = None
    rounds = 0
    for n in range(hands):
        # the bet is worked out fresh every round from the base unit
        b = system(unit=unit, tc=shoe.true_count(),
                   last_result=last_result, last_bet=last_bet)
        b = max(rules.table_min, min(b, rules.table_max, balance))
        if balance < rules.table_min:
            ruined_at = n
            break
        r = table.play_round(balance, b, bot)
        rounds += 1
        balance += r.net
        net += r.net
        wagered += r.wagered
        sum_sq += (r.net / unit) ** 2
        peak = max(peak, net)
        trough_dd = max(trough_dd, peak - net)
        last_result, last_bet = r.net, b
        max_bet = max(max_bet, b)
    mean_u = net / unit / max(rounds, 1)
    sd_u = math.sqrt(max(sum_sq / max(rounds, 1) - mean_u ** 2, 0))
    edge = net / wagered if wagered else 0.0
    ci = 1.96 * sd_u / math.sqrt(max(rounds, 1)) * unit * rounds / wagered \
        if wagered else 0.0
    return {"play": play, "bet": bet, "rounds": rounds, "net": net,
            "wagered": wagered, "edge": edge, "ci": ci, "sd_units": sd_u,
            "max_drawdown": trough_dd, "max_bet": max_bet,
            "final_balance": None if bankroll is None else balance,
            "start": start, "ruined_at": ruined_at}


def print_result(r: dict) -> None:
    print(f"  play={r['play']:<11} bet={r['bet']:<10} rounds={r['rounds']:,}")
    print(f"    wagered {r['wagered']:>14,.0f}   net {r['net']:>+12,.0f}")
    print(f"    edge    {r['edge']:>+13.2%}   95% range "
          f"{r['edge'] - r['ci']:+.2%} to {r['edge'] + r['ci']:+.2%}")
    print(f"    SD per round {r['sd_units']:.2f} units   "
          f"max drawdown {r['max_drawdown']:,.0f}   biggest bet {r['max_bet']:,.0f}")
    if r["final_balance"] is not None:
        print(f"    bankroll {r['start']:,.0f} -> {r['final_balance']:,.0f}", end="")
        if r["ruined_at"] is not None:
            print(f"   RUINED after {r['ruined_at']:,} rounds", end="")
        print()


def ev_table(rules: RulesConfig | None = None) -> None:
    """Dealer final odds and stand EV for each upcard, fresh shoe, peek."""
    rules = rules or RulesConfig()
    ups = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "A")
    print(f"\nDealer final outcome, {rules.decks} decks, after the peek")
    print("up   " + "".join(f"{o:>7}" for o in OUTCOMES))
    for up in ups:
        c = list(fresh_counts(rules.decks))
        c[KEY_INDEX[up]] -= 1
        d = dealer_distribution(up, tuple(c), rules)
        print(f"{up:<5}" + "".join(f"{d[o]:>7.1%}" for o in OUTCOMES))
    print("\nEV of STANDING (per unit bet)")
    print("you  " + "".join(f"{u:>7}" for u in ups))
    for total in (12, 13, 14, 15, 16, 17, 18, 19, 20, 21):
        row = []
        for up in ups:
            c = list(fresh_counts(rules.decks))
            c[KEY_INDEX[up]] -= 1
            row.append(Evaluator(up, tuple(c), rules).stand(total))
        print(f"{total:<5}" + "".join(f"{v:>+7.2f}" for v in row))


def cutcard_experiment(hands: int, seed: int | None) -> None:
    """Counter with a bet spread, at different cut-card depths."""
    print(f"\nCut card experiment: counter + count bets, {hands:,} rounds each")
    for pen in (0.50, 0.65, 0.75, 0.85):
        rules = RulesConfig(penetration=pen)
        r = simulate(hands, "counter", "count", rules=rules, seed=seed)
        print(f"  cut at {pen:.0%}: edge {r['edge']:+.2%} "
              f"(95% {r['edge'] - r['ci']:+.2%} .. {r['edge'] + r['ci']:+.2%})")
    print("  Deeper cut = more hands at high counts = bigger edge for a counter.")


def compare(hands: int, seed: int | None) -> None:
    print(f"\nAll play styles, flat bet 10, {hands:,} rounds each")
    for play in ("basic", "counter", "mimic", "never_bust", "always_hit"):
        print_result(simulate(hands, play, "flat", seed=seed))
    print("\nBetting systems on basic play, bankroll 2,000, unit 10")
    for bet in ("flat", "martingale"):
        print_result(simulate(hands, "basic", bet, bankroll=2000, seed=seed))
    print_result(simulate(hands, "counter", "count", bankroll=2000, seed=seed))


def main() -> None:
    ap = argparse.ArgumentParser(description="bj2 simulator")
    ap.add_argument("--hands", type=int, default=100_000)
    ap.add_argument("--play", default="basic",
                    choices=["basic", "counter", "mimic", "never_bust", "always_hit"])
    ap.add_argument("--bet", default="flat", choices=list(BET_SYSTEMS))
    ap.add_argument("--unit", type=float, default=10)
    ap.add_argument("--bankroll", type=float, default=None)
    ap.add_argument("--decks", type=int, default=6)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--compare", type=int, metavar="HANDS")
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--cutcard", type=int, metavar="HANDS")
    a = ap.parse_args()
    t0 = time.time()
    if a.table:
        ev_table(RulesConfig(decks=a.decks))
    elif a.compare:
        compare(a.compare, a.seed)
    elif a.cutcard:
        cutcard_experiment(a.cutcard, a.seed)
    else:
        r = simulate(a.hands, a.play, a.bet, a.unit, a.bankroll,
                     RulesConfig(decks=a.decks), a.seed)
        print()
        print_result(r)
    print(f"\n  ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
