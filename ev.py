"""
ev.py - the maths engine: dealer odds and the expected value of every move.

STUDY NOTES (read these before the code)

1. Expected value (EV). For a move M, EV(M) = sum over outcomes of
   P(outcome) x money won in that outcome, measured in units of the bet.
   +0.20 means "on average you win 20% of your bet with this move".
   The best move is simply the one with the highest EV.

2. Card counts. Everything works from a tuple of 10 numbers: how many
   A,2,3,4,5,6,7,8,9,T the PLAYER has not seen yet. The dealer's hole card
   is inside these counts (you can't see it), which is correct.

3. Dealer odds (dealer_distribution). The dealer has no choices, so we can
   follow every possible draw: hit below 17, stand on 17-21, bust over 21.
   A recursive function walks all branches; lru_cache remembers each
   (total, ace, cards-left) state so each one is only calculated once.

4. The PEEK. With an Ace or a ten showing, the dealer checks the hole card
   before you play. If you are asked to decide, the dealer does NOT have
   blackjack. So the hole card is drawn only from cards that don't make a
   natural. (Fix vs the generated game, which forgot this: it said stand
   on 20 vs Ace was worth +0.16 when it is really about +0.66.)

5. Player recursion. Hitting: for every card you could draw, either you
   bust (-1) or you are in a new position where you again pick the better
   of stand / hit. Each drawn card is removed from the counts on the way
   down (fix vs the generated game, which kept drawing from the same counts).
   Simplification, stated honestly: the dealer's odds are worked out once,
   at the moment of the decision, and not recomputed for every card you
   might draw. The error from that is a fraction of a percent.

6. Split. The EV of ONE split hand is computed, then multiplied by 2,
   because a split puts two bets on the table. (Fix vs the generated game,
   which compared one hand's EV with the whole bet.) Resplits are ignored,
   so the true split EV is very slightly higher than shown.

7. Insurance. It pays 2:1 when the hole card is a ten. If p = tens unseen /
   cards unseen, one unit of insurance is worth 2p - (1-p) = 3p - 1.
   It only pays when p > 1/3, i.e. a very ten-rich shoe.
"""

from __future__ import annotations

from functools import lru_cache

from cards import KEYS, KEY_INDEX, KEY_VALUE, Hand
from rules import RulesConfig

OUTCOMES = ("17", "18", "19", "20", "21", "bust")
T = KEY_INDEX["T"]
A = KEY_INDEX["A"]
FRESH_DECK = (4, 4, 4, 4, 4, 4, 4, 4, 4, 16)


def fresh_counts(decks: int) -> tuple[int, ...]:
    return tuple(c * decks for c in FRESH_DECK)


def _minus(counts: tuple[int, ...], i: int) -> tuple[int, ...]:
    lst = list(counts)
    lst[i] -= 1
    return tuple(lst)


def _best_total(hard: int, has_ace: bool) -> int:
    return hard + 10 if has_ace and hard + 10 <= 21 else hard


# ----------------------------------------------------------------------
# Dealer
# ----------------------------------------------------------------------
@lru_cache(maxsize=None)
def _dealer_from(hard: int, has_ace: bool, counts: tuple[int, ...],
                 h17: bool) -> tuple[float, ...]:
    """Probabilities of (17,18,19,20,21,bust) from this dealer position."""
    if hard > 21:
        return (0, 0, 0, 0, 0, 1.0)
    total = _best_total(hard, has_ace)
    soft = total != hard
    if total >= 17 and not (h17 and soft and total == 17):
        out = [0.0] * 6
        out[total - 17] = 1.0
        return tuple(out)
    n = sum(counts)
    if n == 0:                       # empty shoe: fall back to a fresh deck
        counts, n = FRESH_DECK, 52
    acc = [0.0] * 6
    for i, c in enumerate(counts):
        if c == 0:
            continue
        p = c / n
        sub = _dealer_from(hard + KEY_VALUE[KEYS[i]], has_ace or i == A,
                           _minus(counts, i), h17)
        for k in range(6):
            acc[k] += p * sub[k]
    return tuple(acc)


def dealer_distribution(up_key: str, counts: tuple[int, ...],
                        rules: RulesConfig) -> dict[str, float]:
    """Final-outcome odds for the dealer, given the upcard and unseen cards.

    With peek on, a dealer natural is excluded (you only decide when the
    dealer has already checked and has no blackjack). With peek off, the
    probability of a dealer natural is returned under the key 'bj'.
    """
    up_i = KEY_INDEX[up_key]
    n = sum(counts)
    weights: list[tuple[int, float]] = []
    bj = 0.0
    for i, c in enumerate(counts):
        if c == 0:
            continue
        natural = (up_i == A and i == T) or (up_i == T and i == A)
        if natural:
            if rules.peek:
                continue
            bj += c / n
            continue
        weights.append((i, c))
    wsum = sum(c for _, c in weights)
    scale = (1.0 - bj) / wsum
    acc = [0.0] * 6
    for i, c in weights:
        p = c * scale
        sub = _dealer_from(KEY_VALUE[up_key] + KEY_VALUE[KEYS[i]],
                           up_i == A or i == A, _minus(counts, i),
                           rules.dealer_hits_soft17)
        for k in range(6):
            acc[k] += p * sub[k]
    dist = dict(zip(OUTCOMES, acc))
    if not rules.peek:
        dist["bj"] = bj
    return dist


def p_dealer_blackjack(up_key: str, counts: tuple[int, ...]) -> float:
    """Chance the hole card makes a natural (before the peek)."""
    n = sum(counts)
    if up_key == "A":
        return counts[T] / n
    if up_key == "T":
        return counts[A] / n
    return 0.0


# ----------------------------------------------------------------------
# Player
# ----------------------------------------------------------------------
def stand_ev(total: int, dist: dict[str, float]) -> float:
    """EV of standing on `total` against the dealer odds `dist`."""
    if total > 21:
        return -1.0
    ev = dist["bust"] - dist.get("bj", 0.0)
    for k in ("17", "18", "19", "20", "21"):
        d = int(k)
        if total > d:
            ev += dist[k]
        elif total < d:
            ev -= dist[k]
    # totals under 17 lose to every dealer total, already handled above
    return ev


class Evaluator:
    """All the EVs for one decision point (one upcard, one set of counts)."""

    def __init__(self, up_key: str, counts: tuple[int, ...], rules: RulesConfig):
        self.up_key = up_key
        self.counts = counts
        self.rules = rules
        self.dist = dealer_distribution(up_key, counts, rules)
        self._memo: dict[tuple, float] = {}
        self._stand: dict[int, float] = {}

    # stand EV for every total, cached
    def stand(self, total: int) -> float:
        if total not in self._stand:
            self._stand[total] = stand_ev(total, self.dist)
        return self._stand[total]

    def best_hit_stand(self, hard: int, has_ace: bool,
                       counts: tuple[int, ...]) -> float:
        """EV when you may still hit or stand (no double), playing perfectly."""
        total = _best_total(hard, has_ace)
        if hard > 21:
            return -1.0
        if total == 21:
            return self.stand(21)
        return max(self.stand(total), self.hit(hard, has_ace, counts))

    def hit(self, hard: int, has_ace: bool, counts: tuple[int, ...]) -> float:
        """EV of taking one card, then playing perfectly."""
        key = (hard, has_ace, counts)
        if key in self._memo:
            return self._memo[key]
        n = sum(counts)
        ev = 0.0
        for i, c in enumerate(counts):
            if c == 0:
                continue
            p = c / n
            nh = hard + KEY_VALUE[KEYS[i]]
            if nh > 21:
                ev -= p
            else:
                ev += p * self.best_hit_stand(nh, has_ace or i == A,
                                              _minus(counts, i))
        self._memo[key] = ev
        return ev

    def double(self, hard: int, has_ace: bool, counts: tuple[int, ...]) -> float:
        """EV of doubling: twice the bet, exactly one more card, then stand."""
        n = sum(counts)
        ev = 0.0
        for i, c in enumerate(counts):
            if c == 0:
                continue
            p = c / n
            nh = hard + KEY_VALUE[KEYS[i]]
            if nh > 21:
                ev -= p
            else:
                ev += p * self.stand(_best_total(nh, has_ace or i == A))
        return 2 * ev

    def split(self, pair_key: str, counts: tuple[int, ...]) -> float:
        """EV of splitting, for BOTH hands together (= 2 x one hand)."""
        v = KEY_VALUE[pair_key]
        aces = pair_key == "A"
        n = sum(counts)
        one = 0.0
        for i, c in enumerate(counts):
            if c == 0:
                continue
            p = c / n
            hard = v + KEY_VALUE[KEYS[i]]
            has_ace = aces or i == A
            rest = _minus(counts, i)
            total = _best_total(hard, has_ace)
            if aces and not self.rules.hit_split_aces:
                ev = self.stand(total)          # one card only, 21 is not a BJ
            else:
                ev = self.best_hit_stand(hard, has_ace, rest)
                if self.rules.double_after_split:
                    ev = max(ev, self.double(hard, has_ace, rest))
            one += p * ev
        return 2 * one

    def bust_chance(self, hard: int, counts: tuple[int, ...]) -> float:
        """P(bust) if you take exactly one more card."""
        n = sum(counts)
        return sum(c for i, c in enumerate(counts)
                   if hard + KEY_VALUE[KEYS[i]] > 21) / n


def insurance_ev(counts: tuple[int, ...]) -> float:
    """EV of one unit of insurance: 3p - 1, p = tens unseen / cards unseen."""
    p = counts[T] / sum(counts)
    return 3 * p - 1


def decision_evs(hand: Hand, up_key: str, counts: tuple[int, ...],
                 rules: RulesConfig, legal: list[str]) -> dict:
    """EV of every legal move for this hand, plus the best one.

    Returns {"evs": {move: ev}, "best": move, "dist": dealer odds,
             "bust": P(bust on one card)}.
    """
    ev = Evaluator(up_key, counts, rules)
    hard, has_ace = hand.hard_total(), hand.has_ace()
    evs: dict[str, float] = {}
    evs["stand"] = ev.stand(hand.total())
    evs["hit"] = ev.hit(hard, has_ace, counts)
    if "double" in legal:
        evs["double"] = ev.double(hard, has_ace, counts)
    if "split" in legal:
        evs["split"] = ev.split(hand.cards[0].key, counts)
    if "surrender" in legal:
        evs["surrender"] = -0.5
    best = max(evs, key=evs.get)
    return {"evs": evs, "best": best, "dist": ev.dist,
            "bust": ev.bust_chance(hard, counts)}


# ----------------------------------------------------------------------
# Count-based edge and bet size
# ----------------------------------------------------------------------
BASE_EDGE = -0.005        # player edge off the top, these rules, ~ -0.5%
EDGE_PER_TC = 0.005       # each +1 true count adds about +0.5%
VARIANCE = 1.33           # variance of one blackjack hand, in bet units^2


def edge_from_true_count(tc: float) -> float:
    """Rough player edge from the Hi-Lo true count (rule of thumb)."""
    return BASE_EDGE + EDGE_PER_TC * tc


def kelly_bet(bankroll: float, tc: float, fraction: float = 0.5) -> float:
    """Kelly bet = bankroll x edge / variance (here half-Kelly by default).

    Kelly maximises long-run growth; half-Kelly gives up a little growth
    for much smaller swings. With no edge the answer is 0 = don't bet.
    """
    edge = edge_from_true_count(tc)
    if edge <= 0:
        return 0.0
    return bankroll * fraction * edge / VARIANCE
