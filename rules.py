"""
rules.py - the table rules in one place, and which moves are legal.

STUDY NOTES
- RulesConfig is a dataclass: a class that is mostly data. Changing a rule
  means changing one field here, and every other module reads it from here.
- legal_actions() is the referee: the game only ever offers moves that come
  out of this function, so the menu and the rules cannot disagree.
- Money is kept as float, so a 3:2 blackjack on a bet of 15 pays 22.5
  exactly. (Fix vs the generated game, which rounded it down to 22.)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from cards import Hand


@dataclass
class RulesConfig:
    decks: int = 6
    penetration: float = 0.75       # cut card at 75% of the shoe
    dealer_hits_soft17: bool = False   # False = S17 (dealer stands on all 17s)
    peek: bool = True               # dealer checks for blackjack with A or T up
    blackjack_pays: float = 1.5     # 3:2
    double_any_two: bool = True
    double_after_split: bool = True
    max_hands: int = 4              # split up to 3 times -> 4 hands
    resplit_aces: bool = False
    hit_split_aces: bool = False    # split Aces get one card each
    late_surrender: bool = True
    insurance: bool = True
    table_min: float = 10
    table_max: float = 1000

    def summary(self) -> str:
        lines = [
            f"{self.decks} deck(s), cut card at {int(self.penetration * 100)}%",
            "Dealer " + ("hits" if self.dealer_hits_soft17 else "stands on")
            + " soft 17" + (", peeks for blackjack" if self.peek else ""),
            "Blackjack pays 3:2" if self.blackjack_pays == 1.5 else f"Blackjack pays {self.blackjack_pays:g} to 1",
            "Double on any two cards" + (", also after a split"
                                          if self.double_after_split else ""),
            f"Split up to {self.max_hands} hands; split Aces get one card"
            + ("" if self.resplit_aces else ", no resplitting Aces"),
            "Late surrender: " + ("yes, lose half" if self.late_surrender else "no"),
            "Insurance: " + ("offered vs Ace, pays 2:1" if self.insurance else "no"),
            f"Bets: {self.table_min:g} to {self.table_max:g}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_RULES = RulesConfig()


def can_double(hand: Hand, rules: RulesConfig, balance: float) -> bool:
    if len(hand.cards) != 2 or hand.split_aces:
        return False
    if hand.from_split and not rules.double_after_split:
        return False
    return balance >= hand.bet


def can_split(hand: Hand, rules: RulesConfig, hands_in_play: int,
              balance: float) -> bool:
    if not hand.is_pair() or hands_in_play >= rules.max_hands:
        return False
    if hand.split_aces and not rules.resplit_aces:
        return False
    return balance >= hand.bet


def can_surrender(hand: Hand, rules: RulesConfig, hands_in_play: int) -> bool:
    # Only the very first decision on the original two cards.
    return (rules.late_surrender and hands_in_play == 1
            and len(hand.cards) == 2 and not hand.from_split)


def legal_actions(hand: Hand, rules: RulesConfig, hands_in_play: int,
                  balance: float) -> list[str]:
    acts = ["hit", "stand"]
    if can_double(hand, rules, balance):
        acts.append("double")
    if can_split(hand, rules, hands_in_play, balance):
        acts.append("split")
    if can_surrender(hand, rules, hands_in_play):
        acts.append("surrender")
    return acts
