"""
table.py - one round of blackjack, from bet to payout.

STUDY NOTES
- This file knows the ORDER of a real round and nothing about the screen.
  Who decides (a person typing, or a bot in the simulator) is passed in as
  an "agent": any object with the methods insurance(...), action(...) and
  event(...). That's called dependency injection, and it means the game and
  the simulator run exactly the same round code.
- Order of a round (fixes vs the generated game marked *):
    1. take the bet *before* the cards come out (*)
    2. deal: player, dealer up, player, dealer hole (face down)
    3. insurance offer if the dealer shows an Ace
    4. peek: dealer with A or T checks for blackjack
    5. player blackjack is paid 3:2 straight away
    6. play each hand: hit / stand / double / split / surrender
    7. turn the hole card over (only NOW does it enter the count) (*)
    8. dealer draws to 17
    9. settle EVERY hand on its own (*): a split with one win and one
       loss is one win and one loss, not "a push"
- `committed` tracks money already on the table, so you can't double or
  split with chips you don't have.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cards import Card, Hand, Shoe
from rules import RulesConfig, legal_actions


@dataclass
class HandResult:
    cards: str
    start: str          # e.g. "hard 16", "pair 8", "soft 18"
    bet: float          # final stake on this hand (after any double)
    outcome: str        # win / lose / push / blackjack / surrender / bust
    net: float
    actions: list[str] = field(default_factory=list)


@dataclass
class RoundResult:
    base_bet: float
    up: str
    dealer_cards: str
    dealer_total: str
    hands: list[HandResult]
    insurance_bet: float = 0.0
    insurance_net: float = 0.0
    dealer_blackjack: bool = False
    reshuffled: bool = False

    @property
    def net(self) -> float:
        return sum(h.net for h in self.hands) + self.insurance_net

    @property
    def wagered(self) -> float:
        return sum(h.bet for h in self.hands) + self.insurance_bet


def start_label(hand: Hand) -> str:
    if hand.is_pair():
        return f"pair {hand.cards[0].key}"
    return hand.describe()


def dealer_should_hit(dealer: Hand, rules: RulesConfig) -> bool:
    t = dealer.total()
    if t < 17:
        return True
    return t == 17 and dealer.is_soft() and rules.dealer_hits_soft17


class Table:
    def __init__(self, rules: RulesConfig, shoe: Shoe):
        self.rules = rules
        self.shoe = shoe

    def play_round(self, balance: float, bet: float, agent) -> RoundResult:
        rules, shoe = self.rules, self.shoe
        reshuffled = False
        if shoe.needs_shuffle():
            shoe.reshuffle()
            reshuffled = True
            agent.event("shuffle", None)

        # 1-2. bet is already fixed; deal
        first = Hand(bet=bet)
        dealer = Hand()
        first.add(shoe.draw())
        up = shoe.draw()
        dealer.add(up)
        first.add(shoe.draw())
        hole = shoe.draw(face_up=False)
        dealer.add(hole)
        committed = bet
        hands = [first]
        labels = [start_label(first)]
        agent.event("deal", {"hand": first, "up": up})

        # 3. insurance
        ins = 0.0
        if (rules.insurance and up.key == "A"
                and balance - committed >= bet / 2
                and agent.insurance(first, up, shoe)):
            ins = bet / 2
            committed += ins

        def reveal_hole() -> None:
            shoe.see(hole)

        # 4. peek: a dealer natural ends the round before you act, so you
        #    can only ever lose your original bet to it
        dealer_bj = dealer.is_blackjack()
        if dealer_bj:
            reveal_hole()
            ins_net = 2 * ins if ins else 0.0
            if first.is_blackjack():
                res = HandResult(first.show(), labels[0], bet, "push", 0.0)
            else:
                res = HandResult(first.show(), labels[0], bet, "lose", -bet)
            agent.event("dealer_blackjack", {"dealer": dealer})
            return RoundResult(bet, str(up), dealer.show(), "Blackjack", [res],
                               ins, ins_net, True, reshuffled)
        ins_net = -ins

        # 5. player blackjack
        if first.is_blackjack():
            reveal_hole()
            win = bet * rules.blackjack_pays
            res = HandResult(first.show(), labels[0], bet, "blackjack", win)
            agent.event("player_blackjack", {"win": win})
            return RoundResult(bet, str(up), dealer.show(), str(dealer.total()),
                               [res], ins, ins_net, False, reshuffled)

        # 6. play every hand
        actions: list[list[str]] = [[]]
        i = 0
        while i < len(hands):
            h = hands[i]
            if len(h.cards) == 1:                 # second card for a split hand
                h.add(shoe.draw())
                agent.event("split_card", {"hand": h, "index": i})
            while not h.finished():
                legal = legal_actions(h, rules, len(hands), balance - committed)
                move = agent.action(h, up, legal, shoe, len(hands), i)
                if move not in legal:
                    raise ValueError(f"illegal move {move!r}, legal: {legal}")
                actions[i].append(move)
                if move == "hit":
                    h.add(shoe.draw())
                elif move == "stand":
                    h.stood = True
                elif move == "double":
                    committed += h.bet
                    h.bet *= 2
                    h.doubled = True
                    h.add(shoe.draw())
                elif move == "surrender":
                    h.surrendered = True
                elif move == "split":
                    committed += h.bet
                    aces = h.cards[0].key == "A"
                    new = Hand(cards=[h.cards.pop()], bet=h.bet,
                               from_split=True, split_aces=aces)
                    h.from_split = True
                    h.split_aces = aces
                    h.add(shoe.draw())
                    hands.insert(i + 1, new)
                    actions.insert(i + 1, [])
                    labels.insert(i + 1, labels[i])
                agent.event("after_move", {"hand": h, "move": move, "index": i})
            i += 1

        # 7-8. dealer
        reveal_hole()
        live = [h for h in hands if not h.is_bust() and not h.surrendered]
        agent.event("dealer_reveal", {"dealer": dealer})
        if live:
            while dealer_should_hit(dealer, rules):
                dealer.add(shoe.draw())
                agent.event("dealer_draw", {"dealer": dealer})

        # 9. settle each hand
        d = dealer.total()
        results = []
        for h, lab, acts in zip(hands, labels, actions):
            if h.surrendered:
                out, net = "surrender", -h.bet / 2
            elif h.is_bust():
                out, net = "bust", -h.bet
            elif d > 21 or h.total() > d:
                out, net = "win", h.bet
            elif h.total() < d:
                out, net = "lose", -h.bet
            else:
                out, net = "push", 0.0
            results.append(HandResult(h.show(), lab, h.bet, out, net, acts))
        dealer_total = "bust" if d > 21 else str(d)
        return RoundResult(bet, str(up), dealer.show(), dealer_total, results,
                           ins, ins_net, False, reshuffled)
