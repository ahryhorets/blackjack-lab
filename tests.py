#!/usr/bin/env python3
"""
tests.py - proves the fixes. Run:  python3 tests.py

STUDY NOTES
- unittest: each method starting with test_ is one check. assertEqual /
  assertAlmostEqual / assertTrue fail loudly if the code is wrong.
- A "rigged shoe" (cards in a known order) makes a random game testable:
  we decide exactly which cards come out, then check the money.
- Each test is labelled with the flaw number from the study report.
"""

from __future__ import annotations

import random
import unittest

from cards import Card, Hand, Shoe, KEY_INDEX
from ev import Evaluator, dealer_distribution, fresh_counts, insurance_ev
from rules import RulesConfig
from table import Table
from strategy import chart_move, bet_count_ramp
import sim


def H(*ranks: str) -> Hand:
    return Hand(cards=[Card(r, "♠") for r in ranks])


def counts_without(decks: int, *keys: str) -> tuple[int, ...]:
    c = list(fresh_counts(decks))
    for k in keys:
        c[KEY_INDEX[k]] -= 1
    return tuple(c)


def rigged_shoe(order: list[str], decks: int = 6) -> Shoe:
    """Shoe whose NEXT cards are `order` (first in list comes out first)."""
    shoe = Shoe(decks, 0.99, random.Random(0))
    for r in order:                      # move these cards to the top
        idx = next(i for i, c in enumerate(shoe.cards) if c.rank == r)
        shoe.cards.pop(idx)
    shoe.cards.extend(Card(r, "♣") for r in reversed(order))
    shoe.unseen = list(fresh_counts(decks))
    return shoe


class Script:
    """Agent that plays a fixed list of moves."""
    def __init__(self, moves, insure=False):
        self.moves = list(moves)
        self.insure = insure

    def insurance(self, *a):
        return self.insure

    def action(self, hand, up, legal, *a):
        return self.moves.pop(0)

    def event(self, *a):
        pass


class TestHands(unittest.TestCase):
    def test_values(self):
        self.assertEqual(H("A", "K").total(), 21)
        self.assertEqual(H("A", "A").total(), 12)
        self.assertEqual(H("A", "A", "9").total(), 21)
        self.assertTrue(H("A", "A", "9").is_soft())

    def test_flaw4_second_ace_stays_soft(self):
        h = H("A", "4", "A")
        self.assertEqual(h.total(), 16)
        self.assertTrue(h.is_soft())       # generated engine said hard 16

    def test_split_21_is_not_blackjack(self):
        h = H("A", "K")
        h.from_split = True
        self.assertFalse(h.is_blackjack())


class TestMaths(unittest.TestCase):
    R = RulesConfig()

    def test_flaw1_peek_stand20_vs_ace(self):
        c = counts_without(6, "T", "T", "A")
        ev = Evaluator("A", c, self.R).stand(20)
        self.assertAlmostEqual(ev, 0.655, delta=0.01)   # engine said +0.16

    def test_dealer_bust_vs_6(self):
        d = dealer_distribution("6", counts_without(6, "6"), self.R)
        self.assertAlmostEqual(d["bust"], 0.423, delta=0.005)

    def test_dealer_odds_sum_to_one(self):
        for up in ("2", "7", "T", "A"):
            d = dealer_distribution(up, counts_without(6, up), self.R)
            self.assertAlmostEqual(sum(d.values()), 1.0, places=9)

    def test_flaw2_split_counts_both_hands(self):
        c = counts_without(6, "8", "8", "T")
        ev = Evaluator("T", c, self.R).split("8", c)
        self.assertAlmostEqual(ev, -0.48, delta=0.03)   # engine said -0.28

    def test_flaw10_insurance_formula(self):
        c = counts_without(6, "A")
        p = c[KEY_INDEX["T"]] / sum(c)
        self.assertAlmostEqual(insurance_ev(c), 3 * p - 1, places=12)
        self.assertLess(insurance_ev(c), 0)

    def test_hit_vs_stand_16_vs_10(self):
        c = counts_without(6, "T", "6", "T")
        e = Evaluator("T", c, self.R)
        self.assertGreater(e.hit(16, False, c), e.stand(16))   # hit, barely


class TestTable(unittest.TestCase):
    R = RulesConfig(decks=6, penetration=0.99)

    def play(self, order, moves, bet=10, balance=1000, insure=False):
        t = Table(self.R, rigged_shoe(order))
        return t.play_round(balance, bet, Script(moves, insure))

    def test_flaw11_blackjack_pays_exact_3_to_2(self):
        # deal order: player, dealer up, player, dealer hole
        r = self.play(["A", "9", "K", "7"], [], bet=15)
        self.assertEqual(r.net, 22.5)     # generated game paid 22

    def test_flaw9_split_win_and_loss_counted_per_hand(self):
        # 8,8 vs dealer 10 + 7 (17). Hand 1 gets 3 -> 11, hits K -> 21: win.
        # Hand 2 gets 5 -> 13, stands: loses to 17. One win + one loss = 0.
        order = ["8", "10", "8", "7", "3", "K", "5"]
        r = self.play(order, ["split", "hit", "stand"])
        outs = [h.outcome for h in r.hands]
        self.assertEqual(outs, ["win", "lose"])
        self.assertEqual(r.net, 0)

    def test_double_pays_double(self):
        r = self.play(["6", "6", "5", "10", "K", "9"], ["double"])
        self.assertEqual(r.hands[0].outcome, "win")    # 21 vs 6,10,9 bust
        self.assertEqual(r.net, 20)

    def test_surrender_loses_half(self):
        r = self.play(["10", "10", "6", "9"], ["surrender"])
        self.assertEqual(r.net, -5)

    def test_insurance_pays_when_dealer_has_bj(self):
        r = self.play(["10", "A", "9", "K"], [], insure=True)
        self.assertTrue(r.dealer_blackjack)
        self.assertEqual(r.net, -10 + 10)   # lose 10, insurance 5 pays 10

    def test_flaw6_hole_card_not_counted_until_reveal(self):
        shoe = rigged_shoe(["2", "3", "4", "5"])
        seen = []

        class Peek(Script):
            def action(self, hand, up, legal, shoe, *a):
                seen.append(shoe.unseen_total())
                return "stand"
        Table(self.R, shoe).play_round(1000, 10, Peek([]))
        self.assertEqual(seen[0], 312 - 3)   # hole card still unseen


class TestSim(unittest.TestCase):
    def test_flaw3_bet_resets_every_hand(self):
        r = sim.simulate(3000, "basic", "flat", seed=5)
        self.assertEqual(r["max_bet"], 10)          # never grows

    def test_flaw7_low_balance_ends_game(self):
        r = sim.simulate(10_000, "always_hit", "flat", bankroll=50, seed=1)
        self.assertIsNotNone(r["ruined_at"])        # stops, doesn't hang
        self.assertGreaterEqual(r["final_balance"], 0)

    def test_count_ramp(self):
        self.assertEqual(bet_count_ramp(10, tc=0), 10)
        self.assertEqual(bet_count_ramp(10, tc=3.4), 60)
        self.assertEqual(bet_count_ramp(10, tc=9), 120)

    def test_chart_basics(self):
        self.assertEqual(chart_move(H("10", "6"), "T", ["hit", "stand", "surrender"]),
                         "surrender")
        self.assertEqual(chart_move(H("8", "8"), "T", ["hit", "stand", "split"]), "split")
        self.assertEqual(chart_move(H("A", "7"), "3", ["hit", "stand"]), "stand")


if __name__ == "__main__":
    unittest.main(verbosity=2)
