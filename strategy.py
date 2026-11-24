"""
strategy.py - basic strategy chart, count deviations, and betting systems.

STUDY NOTES
- Basic strategy is the best move for every (your hand, dealer upcard) when
  you know nothing about which cards are gone. It is what the EV engine
  gives for a fresh shoe, stored as a chart so the simulator is fast.
  Rules assumed: 4-8 decks, dealer stands on soft 17, double after split,
  late surrender (the defaults in rules.py).
- Chart letters:  H hit, S stand, D double (else hit), Ds double (else
  stand), P split, R surrender (else hit).
- Deviations ("Illustrious 18"): when the true count passes an index
  number, the best play changes. Example: 16 vs 10 is a hit off the top,
  but at true count 0 or higher you stand, because the shoe is rich in
  tens and the hit busts more often.
- Betting systems are functions that turn (state) into the next bet. The
  bet is recomputed every hand from the base unit, so a double or a split
  can never leak into the next hand. (Fix vs the generated simulator,
  whose bet kept doubling forever.)
"""

from __future__ import annotations

from cards import Hand

UP_ORDER = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "A")


def _row(s: str) -> dict[str, str]:
    return dict(zip(UP_ORDER, s.split()))


#                 2  3  4  5  6  7  8  9  T  A
HARD = {
    8:  _row("H  H  H  H  H  H  H  H  H  H"),
    9:  _row("H  D  D  D  D  H  H  H  H  H"),
    10: _row("D  D  D  D  D  D  D  D  H  H"),
    11: _row("D  D  D  D  D  D  D  D  D  H"),
    12: _row("H  H  S  S  S  H  H  H  H  H"),
    13: _row("S  S  S  S  S  H  H  H  H  H"),
    14: _row("S  S  S  S  S  H  H  H  H  H"),
    15: _row("S  S  S  S  S  H  H  H  R  H"),
    16: _row("S  S  S  S  S  H  H  R  R  R"),
    17: _row("S  S  S  S  S  S  S  S  S  S"),
}
SOFT = {   # key = total with the Ace as 11
    13: _row("H  H  H  D  D  H  H  H  H  H"),
    14: _row("H  H  H  D  D  H  H  H  H  H"),
    15: _row("H  H  D  D  D  H  H  H  H  H"),
    16: _row("H  H  D  D  D  H  H  H  H  H"),
    17: _row("H  D  D  D  D  H  H  H  H  H"),
    18: _row("S  Ds Ds Ds Ds S  S  H  H  H"),
    19: _row("S  S  S  S  S  S  S  S  S  S"),
    20: _row("S  S  S  S  S  S  S  S  S  S"),
}
PAIRS = {  # Y = split, N = play as a normal total
    "A": _row("Y  Y  Y  Y  Y  Y  Y  Y  Y  Y"),
    "T": _row("N  N  N  N  N  N  N  N  N  N"),
    "9": _row("Y  Y  Y  Y  Y  N  Y  Y  N  N"),
    "8": _row("Y  Y  Y  Y  Y  Y  Y  Y  Y  Y"),
    "7": _row("Y  Y  Y  Y  Y  Y  N  N  N  N"),
    "6": _row("Y  Y  Y  Y  Y  N  N  N  N  N"),
    "5": _row("N  N  N  N  N  N  N  N  N  N"),
    "4": _row("N  N  N  Y  Y  N  N  N  N  N"),
    "3": _row("Y  Y  Y  Y  Y  Y  N  N  N  N"),
    "2": _row("Y  Y  Y  Y  Y  Y  N  N  N  N"),
}

# Illustrious 18 (S17 version): (kind, total, upcard, index, play at/above)
# For negative-index rows the play applies BELOW the index instead.
DEVIATIONS = [
    ("hard", 16, "T", 0, "S"),
    ("hard", 15, "T", 4, "S"),
    ("pair", 20, "5", 5, "P"),
    ("pair", 20, "6", 4, "P"),
    ("hard", 10, "T", 4, "D"),
    ("hard", 12, "3", 2, "S"),
    ("hard", 12, "2", 3, "S"),
    ("hard", 11, "A", 1, "D"),
    ("hard", 9, "2", 1, "D"),
    ("hard", 10, "A", 4, "D"),
    ("hard", 9, "7", 3, "D"),
    ("hard", 16, "9", 5, "S"),
    ("hard", 13, "2", -1, "H"),   # below -1: hit
    ("hard", 12, "4", 0, "H"),    # below 0: hit
    ("hard", 12, "5", -2, "H"),
    ("hard", 12, "6", -1, "H"),
    ("hard", 13, "3", -2, "H"),
]
INSURANCE_INDEX = 3   # take insurance at true count +3 or more


def chart_move(hand: Hand, up_key: str, legal: list[str]) -> str:
    """Basic strategy, translated into a legal move name."""
    if hand.is_pair() and "split" in legal:
        if PAIRS[hand.cards[0].key][up_key] == "Y":
            return "split"
    total = hand.total()
    if hand.is_soft() and total < 21:
        code = "H" if total <= 12 else SOFT[total][up_key]
    else:
        code = HARD[min(max(total, 8), 17)][up_key]
    return _translate(code, legal)


def _translate(code: str, legal: list[str]) -> str:
    if code == "R":
        return "surrender" if "surrender" in legal else "hit"
    if code == "D":
        return "double" if "double" in legal else "hit"
    if code == "Ds":
        return "double" if "double" in legal else "stand"
    if code == "P":
        return "split" if "split" in legal else "stand"
    return {"H": "hit", "S": "stand"}[code]


def counted_move(hand: Hand, up_key: str, legal: list[str], tc: float) -> str:
    """Basic strategy plus the count deviations."""
    total = hand.total()
    is_tt_pair = hand.is_pair() and hand.cards[0].key == "T"
    for kind, t, up, idx, play in DEVIATIONS:
        if up != up_key or t != total:
            continue
        if kind == "pair" and not is_tt_pair:
            continue
        if kind == "hard" and (hand.is_soft() or is_tt_pair and play != "S"):
            continue
        if play == "H":                    # negative-index style row
            if tc < idx:
                return "hit"
            continue
        if tc >= idx:
            if play == "S" and "surrender" in legal and total in (15, 16):
                # surrender still beats standing at these counts
                return "surrender"
            return _translate(play, legal)
    return chart_move(hand, up_key, legal)


def take_insurance(tc: float) -> bool:
    return tc >= INSURANCE_INDEX


# ----------------------------------------------------------------------
# Betting systems: each returns the next bet in money
# ----------------------------------------------------------------------
def bet_flat(unit: float, **_) -> float:
    return unit


def bet_count_ramp(unit: float, tc: float, **_) -> float:
    """1 unit below TC +2, then 2 units per true count, capped at 12 units."""
    if tc < 2:
        return unit
    return unit * min(12, 2 * int(tc))


def bet_martingale(unit: float, last_result: float, last_bet: float, **_) -> float:
    """Double after a loss, back to 1 unit after a win or push."""
    if last_result < 0:
        return last_bet * 2
    return unit


BET_SYSTEMS = {"flat": bet_flat, "count": bet_count_ramp,
               "martingale": bet_martingale}
