#!/usr/bin/env python3
"""
game.py - play bj2 in the terminal.

    cd blackjack-lab
    python3 game.py

Main menu: new game, continue a saved game, overlook (history + stats),
simulator, strategy chart, rules.

At the table:
    bet prompt   a number, Enter = same bet again, k = Kelly suggestion,
                 m = table menu (panel, x-ray, save, leave)
    moves        h hit, s stand, d double, p split, r surrender,
                 ? = what the chart and the counter would do

STUDY NOTES
- This file is only the "face": printing and asking. Every rule lives in
  rules.py/table.py, every number in ev.py. The Human class below is the
  agent that table.Table talks to; the simulator's Bot is the other one.
- The quant panel shows, before every decision: the EV of each legal move,
  what basic strategy says, what a counter would do at this true count,
  your bust chance if you hit, and the dealer's final-outcome odds.
- "EV lost" adds up (best EV - EV of what you chose) x your stake for every
  decision. It measures your decisions, not your luck. Your actual result
  minus what an average player would expect = luck.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import storage
from cards import Shoe, rank_key
from ev import (decision_evs, insurance_ev, kelly_bet, edge_from_true_count,
                p_dealer_blackjack)
from rules import RulesConfig
from strategy import (chart_move, counted_move, take_insurance, HARD, SOFT,
                      PAIRS, UP_ORDER)
from table import Table

# ----------------------------------------------------------------------
# colours (switch off with NO_COLOR=1)
# ----------------------------------------------------------------------
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(text, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else str(text)


RED, GREEN, YELLOW, CYAN, DIM, BOLD = "31", "32", "33", "36", "2", "1"


def money(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".") if x % 1 else f"{x:,.0f}"


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        print()
        raise SystemExit(0)


def ask_number(prompt: str, lo: float, hi: float, default: float | None = None) -> float:
    while True:
        raw = ask(prompt)
        if raw == "" and default is not None:
            return default
        try:
            v = float(raw)
        except ValueError:
            print("  Please type a number.")
            continue
        if not lo <= v <= hi:
            print(f"  Between {money(lo)} and {money(hi)}, please.")
            continue
        return v


# ----------------------------------------------------------------------
# the human agent
# ----------------------------------------------------------------------
MOVE_KEYS = {"h": "hit", "s": "stand", "d": "double", "p": "split",
             "r": "surrender"}


class Human:
    def __init__(self, state: dict, rules: RulesConfig):
        self.state = state
        self.rules = rules
        self.decisions: list[dict] = []    # filled during one round

    # -- table talks to us through these three methods --
    def event(self, kind: str, data) -> None:
        if kind == "shuffle":
            print(c("  [cut card reached - new shoe shuffled, count back to 0]", DIM))
        elif kind == "deal":
            up = data["up"]
            print(f"\n  Dealer: {up}  [?]")
            print(f"  You:    {data['hand'].show()}   ({data['hand'].describe()})")
        elif kind == "dealer_blackjack":
            print(f"  Dealer turns over: {data['dealer'].show()}  "
                  + c("Dealer blackjack.", RED))
        elif kind == "player_blackjack":
            print(c(f"  BLACKJACK! Paid 3:2 = +{money(data['win'])}", GREEN))
        elif kind == "split_card":
            h = data["hand"]
            print(f"  Hand {data['index'] + 1}: {h.show()}   ({h.describe()})")
        elif kind == "after_move":
            h, m = data["hand"], data["move"]
            if m in ("hit", "double", "split"):
                tag = f"Hand {data['index'] + 1}: " if self._n_hands > 1 or m == "split" else ""
                line = f"  {tag}{h.show()}   ({h.describe()})"
                if h.is_bust():
                    line += c("  BUST", RED)
                print(line)
        elif kind == "dealer_reveal":
            d = data["dealer"]
            print(f"  Dealer turns over: {d.show()}   ({d.describe()})")
        elif kind == "dealer_draw":
            d = data["dealer"]
            line = f"  Dealer draws:      {d.show()}   ({d.describe()})"
            if d.is_bust():
                line += c("  DEALER BUSTS", GREEN)
            print(line)

    def insurance(self, hand, up, shoe) -> bool:
        ev = insurance_ev(shoe.counts_tuple())
        self.ins_ev = ev                   # logged with the round
        p = p_dealer_blackjack("A", shoe.counts_tuple())
        if self.state["panel"]:
            adv = "take it" if take_insurance(shoe.true_count()) else "decline"
            print(c(f"  insurance: P(dealer BJ) {p:.1%}, EV {ev:+.3f} per unit"
                    f" -> counter says {adv} (TC {shoe.true_count():+.1f})", CYAN))
        return ask("  Insurance for half your bet? (y/n) ") == "y"

    _n_hands = 1

    def action(self, hand, up, legal, shoe, n_hands, index) -> str:
        self._n_hands = n_hands
        # EVs are always computed (they feed "EV given away"), shown only
        # when the panel is on
        info = decision_evs(hand, up.key, shoe.counts_tuple(), self.rules, legal)
        chart = chart_move(hand, up.key, legal)
        counted = counted_move(hand, up.key, legal, shoe.true_count())
        if n_hands > 1:
            print(f"  -- Hand {index + 1} of {n_hands}: {hand.show()} ({hand.describe()})")
        if self.state["panel"]:
            self.show_panel(info, chart, counted, shoe)
        if self.state["xray"]:
            nxt = " ".join(str(x) for x in shoe.peek_next(3))
            print(c(f"  x-ray: next cards {nxt}", YELLOW))
        opts = "  ".join(f"{k}={m}" for k, m in MOVE_KEYS.items() if m in legal)
        while True:
            raw = ask(f"  {opts}  > ")
            if raw == "?":
                print(f"  chart says {chart}, counter at TC "
                      f"{shoe.true_count():+.1f} says {counted}")
                continue
            move = MOVE_KEYS.get(raw[:1]) if raw else None
            if raw in legal:
                move = raw
            if move in legal:
                break
            print("  Not a legal move here.")
        evs = info["evs"]
        self.decisions.append({
            "hand": hand.describe(), "up": up.key, "move": move,
            "best": info["best"], "chart": chart,
            "ev_move": round(evs[move], 4), "ev_best": round(evs[info["best"]], 4),
            "cost": round((evs[info["best"]] - evs[move]) * hand.bet, 4)})
        return move

    def show_panel(self, info, chart, counted, shoe) -> None:
        evs, best = info["evs"], info["best"]
        print(c("  ---- quant panel ----", DIM))
        for k in ("stand", "hit", "double", "split", "surrender"):
            if k in evs:
                tag = c("  <- best", GREEN) if k == best else ""
                print(f"   EV {k:<10}{evs[k]:+.3f}{tag}")
        d = info["dist"]
        print(f"   bust if you hit {info['bust']:.0%} | dealer ends: "
              + " ".join(f"{k} {v:.0%}" for k, v in d.items() if k != "bj"))
        tc = shoe.true_count()
        print(f"   chart: {chart}  | counter (TC {tc:+.1f}): {counted}"
              f"  | RC {shoe.running_count:+d}, {shoe.unseen_total()} unseen")


# ----------------------------------------------------------------------
# state and sessions
# ----------------------------------------------------------------------
def new_state(name: str, deposit: float, decks: int) -> dict:
    return {"player": name, "date": date.today().isoformat(),
            "deposit": deposit, "balance": deposit, "decks": decks,
            "panel": True, "xray": False, "last_bet": None,
            "stats": {"rounds": 0, "hands": 0, "win": 0, "lose": 0, "push": 0,
                      "blackjack": 0, "bust": 0, "surrender": 0,
                      "doubles": 0, "splits": 0, "insurance_taken": 0,
                      "insurance_net": 0.0, "wagered": 0.0, "net": 0.0,
                      "peak": 0.0, "max_drawdown": 0.0, "best_round": 0.0,
                      "worst_round": 0.0, "ev_lost": 0.0, "mistakes": 0,
                      "decisions": 0}}


def update_stats(state: dict, r, decisions: list[dict]) -> None:
    s = state["stats"]
    s["rounds"] += 1
    for h in r.hands:
        s["hands"] += 1
        key = {"blackjack": "blackjack", "bust": "bust",
               "surrender": "surrender"}.get(h.outcome, h.outcome)
        s[key] += 1
        if h.outcome in ("blackjack",):
            s["win"] += 1
        if h.outcome == "bust":
            s["lose"] += 1
        if h.outcome == "surrender":
            s["lose"] += 1
        s["doubles"] += h.actions.count("double")
        s["splits"] += h.actions.count("split")
    if r.insurance_bet:
        s["insurance_taken"] += 1
        s["insurance_net"] += r.insurance_net
    s["wagered"] += r.wagered
    s["net"] += r.net
    s["peak"] = max(s["peak"], s["net"])
    s["max_drawdown"] = max(s["max_drawdown"], s["peak"] - s["net"])
    s["best_round"] = max(s["best_round"], r.net)
    s["worst_round"] = min(s["worst_round"], r.net)
    for d in decisions:
        s["decisions"] += 1
        s["ev_lost"] += d["cost"]
        if d["cost"] > 1e-9:
            s["mistakes"] += 1


def print_summary(state: dict) -> None:
    s = state["stats"]
    hands = max(s["hands"], 1)
    print(c("\n  ======== session summary ========", BOLD))
    print(f"  Player {state['player']}   deposit {money(state['deposit'])}"
          f" -> balance {money(state['balance'])}"
          f"   ({'+' if s['net'] >= 0 else ''}{money(s['net'])})")
    print(f"  Rounds {s['rounds']}, hands {s['hands']}: "
          f"won {s['win']} ({s['win'] / hands:.0%}), lost {s['lose']} "
          f"({s['lose'] / hands:.0%}), pushed {s['push']} ({s['push'] / hands:.0%})")
    print(f"  Blackjacks {s['blackjack']}, busts {s['bust']}, doubles {s['doubles']},"
          f" splits {s['splits']}, surrenders {s['surrender']}")
    if s["insurance_taken"]:
        print(f"  Insurance taken {s['insurance_taken']}x, net {money(s['insurance_net'])}")
    if s["wagered"]:
        print(f"  Wagered {money(s['wagered'])}, result {s['net'] / s['wagered']:+.2%}"
              f" of action (house edge is about -0.5% with perfect play)")
    print(f"  Best round +{money(s['best_round'])}, worst {money(s['worst_round'])},"
          f" deepest drawdown {money(s['max_drawdown'])}")
    print(f"  Decisions {s['decisions']}, off the best EV {s['mistakes']},"
          f" EV given away {money(s['ev_lost'])}")
    luck = s["net"] - (-0.005 * s["wagered"] - s["ev_lost"])
    print(f"  Luck (result minus expected) {'+' if luck >= 0 else ''}{money(luck)}")


def finish(state: dict) -> None:
    print_summary(state)
    storage.append_history({"player": state["player"], "date": state["date"],
                            "deposit": state["deposit"],
                            "balance": state["balance"], **state["stats"]})
    storage.clear_game()


# ----------------------------------------------------------------------
# the table loop
# ----------------------------------------------------------------------
def table_menu(state: dict, rules: RulesConfig) -> str | None:
    while True:
        print(f"\n  Table menu: 1) quant panel {'ON' if state['panel'] else 'OFF'}"
              f"  2) x-ray {'ON' if state['xray'] else 'OFF'}  3) rules"
              f"  4) save and leave  5) cash out  6) back")
        k = ask("  > ")
        if k == "1":
            state["panel"] = not state["panel"]
        elif k == "2":
            state["xray"] = not state["xray"]
            if state["xray"]:
                print(c("  X-ray shows the next cards in the shoe. A study cheat:"
                        " watch how much it changes the right move.", YELLOW))
        elif k == "3":
            print(rules.summary())
        elif k == "4":
            return "save"
        elif k == "5":
            return "cashout"
        elif k == "6":
            return None


def play_table(state: dict, shoe: Shoe) -> None:
    rules = RulesConfig(decks=state["decks"])
    table = Table(rules, shoe)
    human = Human(state, rules)
    while True:
        bal = state["balance"]
        if bal < rules.table_min:
            print(c(f"\n  Balance {money(bal)} is below the table minimum of "
                    f"{money(rules.table_min)}. Game over.", RED))
            finish(state)
            return
        tc = shoe.true_count()
        print(c(f"\n  Balance {money(bal)} | true count {tc:+.1f} | "
                f"{len(shoe.cards)} cards in shoe", DIM))
        hi = min(rules.table_max, bal)
        last = state["last_bet"]
        hint = f", Enter = {money(last)}" if last and last <= hi else ""
        while True:
            raw = ask(f"  Bet {money(rules.table_min)}-{money(hi)}{hint}"
                      f" (k Kelly, m menu): ")
            if raw == "m":
                act = table_menu(state, rules)
                if act == "save":
                    state["shoe"] = shoe.to_dict()
                    storage.save_game(state)
                    print(f"  Saved to {storage.SAVE_FILE}")
                    return
                if act == "cashout":
                    finish(state)
                    return
                continue
            if raw == "k":
                edge = edge_from_true_count(tc)
                k = kelly_bet(bal, tc)
                print(f"  Edge now about {edge:+.2%}. Half-Kelly bet: "
                      + (f"{money(k)}" if k else "0, no edge: bet the minimum or sit out"))
                continue
            if raw == "" and last and last <= hi:
                bet = last
                break
            try:
                bet = float(raw)
            except ValueError:
                print("  Type a number, Enter, k or m.")
                continue
            if rules.table_min <= bet <= hi:
                break
            print(f"  Between {money(rules.table_min)} and {money(hi)}.")
        state["last_bet"] = bet
        human.decisions = []
        human.ins_ev = None
        r = table.play_round(bal, bet, human)
        state["balance"] = bal + r.net
        for i, h in enumerate(r.hands):
            tag = f"Hand {i + 1}: " if len(r.hands) > 1 else ""
            col = GREEN if h.net > 0 else RED if h.net < 0 else YELLOW
            print(c(f"  {tag}{h.outcome.upper()} {'+' if h.net > 0 else ''}"
                    f"{money(h.net)}", col))
        if r.insurance_bet:
            print(f"  Insurance {'+' if r.insurance_net > 0 else ''}"
                  f"{money(r.insurance_net)}")
        cost = sum(d["cost"] for d in human.decisions)
        if cost > 1e-9 and state["panel"]:
            print(c(f"  (EV given away this round: {money(cost)})", YELLOW))
        update_stats(state, r, human.decisions)
        storage.log_hand({"player": state["player"], "bet": bet,
                          "up": r.up, "dealer": r.dealer_cards,
                          "dealer_total": r.dealer_total,
                          "tc": round(tc, 2), "net": r.net,
                          "insurance": r.insurance_bet,
                          "insurance_net": r.insurance_net,
                          "ins_ev": human.ins_ev,
                          "hands": [h.__dict__ for h in r.hands],
                          "decisions": human.decisions})
        state["shoe"] = shoe.to_dict()
        storage.save_game(state)          # autosave after every round


# ----------------------------------------------------------------------
# menus
# ----------------------------------------------------------------------
def new_game() -> None:
    name = ask("\n  Your name (Enter = Player): ") or "player"
    name = name.title()
    decks = int(ask_number("  Decks: 1, 2, 6 or 8 (Enter = 6): ", 1, 8, 6))
    if decks not in (1, 2, 6, 8):
        decks = 6
    rules = RulesConfig(decks=decks)
    print("\n" + rules.summary())
    dep = ask_number(f"\n  Deposit ({money(rules.table_min)}-100,000): ",
                     rules.table_min, 100_000)
    state = new_state(name, dep, decks)
    play_table(state, Shoe(decks, rules.penetration))


def continue_game() -> None:
    state = storage.load_game()
    if not state:
        print("  No saved game.")
        return
    print(f"\n  Welcome back, {state['player']}. Balance {money(state['balance'])},"
          f" {state['stats']['rounds']} rounds played.")
    play_table(state, Shoe.from_dict(state["shoe"]))


def overlook() -> None:
    hist = storage.load_history()
    print(c("\n  ======== past sessions ========", BOLD))
    if not hist:
        print("  None yet.")
    for h in hist[-15:]:
        print(f"  {h['date']}  {h['player']:<10} {money(h['deposit']):>8} -> "
              f"{money(h['balance']):>8}  rounds {h['rounds']:>4}  "
              f"EV given away {money(h.get('ev_lost', 0))}")
    hands = storage.read_hands()
    if not hands:
        return
    # results by starting situation
    groups: dict[str, list[float]] = {}
    costs: dict[str, list[float]] = {}
    for rec in hands:
        for h in rec["hands"]:
            key = f"{h['start']} vs {rank_key(rec['up'][:-1])}"
            groups.setdefault(key, []).append(h["net"] / max(rec["bet"], 1))
        for d in rec.get("decisions", []):
            if d["cost"] > 1e-9:
                k = f"{d['hand']} vs {d['up']}: you {d['move']}, best {d['best']}"
                costs.setdefault(k, []).append(d["cost"])
    print(c("\n  ======== your most common situations ========", BOLD))
    print("  situation              n   avg result per bet")
    for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f"  {k:<20} {len(v):>4}   {sum(v) / len(v):+.2f}")
    if costs:
        print(c("\n  ======== your costliest habits ========", BOLD))
        for k, v in sorted(costs.items(), key=lambda kv: -sum(kv[1]))[:8]:
            print(f"  {k:<45} x{len(v):<3} cost {money(sum(v))}")


def show_chart() -> None:
    print("\n  Basic strategy (6 decks, S17, DAS, late surrender)")
    print("  H hit  S stand  D double else hit  Ds double else stand  R surrender")
    print("  you   " + "".join(f"{u:>3}" for u in UP_ORDER))
    for t in range(8, 18):
        lab = f"{t}+" if t == 17 else str(t)
        print(f"  {lab:<5} " + "".join(f"{HARD[t][u]:>3}" for u in UP_ORDER))
    for t in range(13, 21):
        print(f"  A,{t - 11:<3} " + "".join(f"{SOFT[t][u]:>3}" for u in UP_ORDER))
    print("  pairs (Y = split)")
    for k in ("A", "T", "9", "8", "7", "6", "5", "4", "3", "2"):
        print(f"  {k},{k:<3} " + "".join(f"{PAIRS[k][u]:>3}" for u in UP_ORDER))


def run_sim_menu() -> None:
    import sim
    print("\n  play style: basic, counter, mimic, never_bust, always_hit")
    play = ask("  play (Enter = basic): ") or "basic"
    if play not in ("basic", "counter", "mimic", "never_bust", "always_hit"):
        play = "basic"
    bet = ask("  bet system: flat, count, martingale (Enter = flat): ") or "flat"
    if bet not in ("flat", "count", "martingale"):
        bet = "flat"
    n = int(ask_number("  rounds (Enter = 20,000): ", 100, 1_000_000, 20_000))
    br = ask_number("  bankroll, 0 = unlimited (Enter = 0): ", 0, 10_000_000, 0)
    print("  running...")
    sim.print_result(sim.simulate(n, play, bet, 10, br or None))


def main() -> None:
    print(c("\n  ♠ ♥  bj2  ♦ ♣   blackjack with the maths switched on", BOLD))
    while True:
        saved = storage.load_game()
        print("\n  1) New game" + ("   2) Continue " + saved["player"] if saved else "")
              + "   3) Overlook   4) Simulator   5) Strategy chart"
              "   6) Rules   7) Quit   8) Deep analysis")
        k = ask("  > ")
        if k == "1":
            if saved and ask("  This replaces your saved game. Sure? (y/n) ") != "y":
                continue
            new_game()
        elif k == "2" and saved:
            continue_game()
        elif k == "3":
            overlook()
        elif k == "4":
            run_sim_menu()
        elif k == "5":
            show_chart()
        elif k == "6":
            print("\n" + RulesConfig().summary())
        elif k == "8":
            import analyze
            path = analyze.build_report()
            if path:
                print(f"  Report written to {path}")
                analyze.open_file(path)
        elif k == "7":
            print("  Bye. The house thanks you for leaving.")
            return
        else:
            print("  Pick a number from the menu.")


if __name__ == "__main__":
    main()
