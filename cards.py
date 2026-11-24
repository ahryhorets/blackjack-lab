"""
cards.py - cards, hands and the shoe.

STUDY NOTES
- A Card is a small immutable record (frozen dataclass): rank + suit.
- A Hand stores its cards and works out its total the way a dealer does:
  every Ace first counts 1, then ONE Ace is upgraded to 11 if that does not
  bust the hand. Only one Ace can ever be 11 (two would be 22), so
  "soft" just means "an Ace is currently counted as 11".
  (Fix vs the generated game: there the soft flag was a yes/no that got lost
  when a second Ace arrived. Here the total is always recomputed from cards.)
- The Shoe keeps TWO views of the cards:
    * self.cards   - the physical order left to deal (what the dealer has)
    * self.unseen  - how many of each rank the PLAYER has not seen yet
  The dealer's hole card is drawn face down: it leaves the shoe but stays
  "unseen" (and out of the Hi-Lo count) until it is turned over.
  (Fix vs the generated game, which counted the hole card the moment it was
  dealt, so the maths panel "knew" a card the player could not see.)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

SUITS = ("♠", "♥", "♦", "♣")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")

# Ranks the maths cares about: all ten-value cards are the same "T".
# Index order is used for the counts tuple in ev.py: A,2,3,...,9,T
KEYS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "T")
KEY_INDEX = {k: i for i, k in enumerate(KEYS)}
KEY_VALUE = {"A": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
             "7": 7, "8": 8, "9": 9, "T": 10}


def rank_key(rank: str) -> str:
    """'10','J','Q','K' -> 'T'; everything else stays the same."""
    return "T" if rank in ("10", "J", "Q", "K") else rank


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def key(self) -> str:
        return rank_key(self.rank)

    @property
    def hard_value(self) -> int:
        """Value with an Ace counted as 1."""
        return KEY_VALUE[self.key]

    @property
    def hi_lo(self) -> int:
        """Hi-Lo tag: 2-6 = +1, 7-9 = 0, tens and Aces = -1."""
        if self.key in ("2", "3", "4", "5", "6"):
            return 1
        if self.key in ("T", "A"):
            return -1
        return 0

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


@dataclass
class Hand:
    cards: list[Card] = field(default_factory=list)
    bet: float = 0.0
    from_split: bool = False     # made by splitting a pair
    split_aces: bool = False     # split Aces get one card only
    doubled: bool = False
    surrendered: bool = False
    stood: bool = False

    def add(self, card: Card) -> None:
        self.cards.append(card)

    # ---- value -------------------------------------------------------
    def hard_total(self) -> int:
        return sum(c.hard_value for c in self.cards)

    def has_ace(self) -> bool:
        return any(c.key == "A" for c in self.cards)

    def total(self) -> int:
        t = self.hard_total()
        if self.has_ace() and t + 10 <= 21:
            return t + 10
        return t

    def is_soft(self) -> bool:
        return self.has_ace() and self.hard_total() + 10 <= 21

    def is_bust(self) -> bool:
        return self.total() > 21

    def is_blackjack(self) -> bool:
        """Natural: exactly two cards worth 21, and NOT made by a split."""
        return len(self.cards) == 2 and self.total() == 21 and not self.from_split

    def is_pair(self) -> bool:
        return len(self.cards) == 2 and self.cards[0].key == self.cards[1].key

    def finished(self) -> bool:
        return (self.stood or self.surrendered or self.doubled
                or self.is_bust() or self.total() == 21
                or (self.split_aces and len(self.cards) == 2))

    def describe(self) -> str:
        if self.is_blackjack():
            return "Blackjack"
        kind = "soft" if self.is_soft() else "hard"
        return f"{kind} {self.total()}"

    def show(self) -> str:
        return " ".join(str(c) for c in self.cards)


class Shoe:
    def __init__(self, decks: int = 6, penetration: float = 0.75,
                 rng: random.Random | None = None):
        self.decks = decks
        self.penetration = penetration
        self.rng = rng or random.Random()
        self.reshuffle()

    # ---- building ----------------------------------------------------
    def reshuffle(self) -> None:
        self.cards = [Card(r, s) for _ in range(self.decks)
                      for s in SUITS for r in RANKS]
        self.rng.shuffle(self.cards)
        self.unseen = [0] * 10
        for c in self.cards:
            self.unseen[KEY_INDEX[c.key]] += 1
        self.running_count = 0
        self.shuffles = getattr(self, "shuffles", 0) + 1

    @property
    def total_cards(self) -> int:
        return self.decks * 52

    def needs_shuffle(self) -> bool:
        """Cut card: reshuffle once this share of the shoe has been dealt."""
        dealt = self.total_cards - len(self.cards)
        return dealt >= self.penetration * self.total_cards

    # ---- dealing -----------------------------------------------------
    def draw(self, face_up: bool = True) -> Card:
        card = self.cards.pop()
        if face_up:
            self.see(card)
        return card

    def see(self, card: Card) -> None:
        """The player sees a card: update unseen counts and Hi-Lo."""
        self.unseen[KEY_INDEX[card.key]] -= 1
        self.running_count += card.hi_lo

    def peek_next(self, n: int = 3) -> list[Card]:
        """X-ray mode: the next n cards that will come out (last = next)."""
        return list(reversed(self.cards[-n:]))

    # ---- counting ----------------------------------------------------
    def unseen_total(self) -> int:
        return sum(self.unseen)

    def decks_unseen(self) -> float:
        return max(self.unseen_total() / 52, 0.25)

    def true_count(self) -> float:
        return self.running_count / self.decks_unseen()

    def counts_tuple(self) -> tuple[int, ...]:
        return tuple(self.unseen)

    # ---- saving ------------------------------------------------------
    def to_dict(self) -> dict:
        return {"decks": self.decks, "penetration": self.penetration,
                "cards": [[c.rank, c.suit] for c in self.cards],
                "unseen": self.unseen, "running_count": self.running_count,
                "shuffles": self.shuffles}

    @classmethod
    def from_dict(cls, d: dict) -> "Shoe":
        shoe = cls.__new__(cls)
        shoe.decks = d["decks"]
        shoe.penetration = d["penetration"]
        shoe.rng = random.Random()
        shoe.cards = [Card(r, s) for r, s in d["cards"]]
        shoe.unseen = list(d["unseen"])
        shoe.running_count = d["running_count"]
        shoe.shuffles = d.get("shuffles", 1)
        return shoe
