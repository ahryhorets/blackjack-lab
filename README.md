# Blackjack Lab 🃏

**The house doesn't need luck. Do you?**

A blackjack engine, simulator and analyzer in pure Python (standard library only). It plays millions of hands to show
two sides of the same game:

- **How the casino wins:** one asymmetric rule, bad intuition, small-print rule tweaks, insurance, and betting
  "systems" that feel like winning.
- **What an informed decision is worth:** the exact expected value of every move, the strategy chart, card counting,
  bet sizing, and how to tell luck from skill in your own results.

👉 **Read the findings with charts: [https://ahryhorets.github.io/blackjack-lab/](https://ahryhorets.github.io/blackjack-lab/)**

> ⚠️ **Disclaimer.** Education only. No real money, not gambling advice, not financial advice. The casino keeps its
> edge against almost everyone. Card counting is legal in most places but casinos can and do ban counters. If gambling
> is a problem for you or someone close to you, please talk to someone and get support.

---

## Run it

```bash
git clone https://github.com/ahryhorets/blackjack-lab.git
cd blackjack-lab
python3 game.py
```

Python 3.10+. Nothing to install.

| Command | What it does |
|---|---|
| `python3 game.py` | Play. Before every decision a panel shows the EV of each move, the chart move, what a counter would do, your bust chance and the dealer's odds |
| `python3 sim.py --compare 50000` | Every play style and betting system, side by side |
| `python3 sim.py --play counter --bet count --bankroll 2000` | One strategy on a fixed bankroll |
| `python3 sim.py --table` | Dealer final odds and EV of standing, every total vs every upcard |
| `python3 sim.py --cutcard 100000` | Does a deeper cut card help a counter? |
| `python3 analyze.py` | HTML report of your own hands: equity curve, luck vs skill, every mistake |
| `python3 analyze.py --file examples/sample_session.jsonl` | Same report on the example session |
| `python3 tests.py` | 19 tests |
| `python3 tools/experiments.py` | Rerun every number on the findings page (~10 min, seeded) |
| `python3 tools/experiments.py --system-rng` | Same suite with OS randomness (`random.SystemRandom`) instead of Mersenne Twister |
| `python3 tools/rng_check.py` | Compare both runs: z-score for every published number |

**In the game:** `h` hit, `s` stand, `d` double, `p` split, `r` surrender, `?` what the chart/counter say.
At the bet prompt: `k` Kelly bet suggestion, `m` table menu (panel on/off, **x-ray mode** shows the next cards, save).

---

## Findings

Basic rules: 6 decks, 3:2, dealer stands on soft 17, double after split, late surrender, cut card at 75%.
All numbers are from seeded simulations in `docs/results.json`.

### Play style (200,000 hands each, flat bet)

| How you play | Edge |
|---|---|
| Plays like the dealer (hit below 17, never double/split) | -5.74% |
| “Never bust” (stand on any 12+) | -6.28% |
| Always hit until 21 or bust | -64.55% |
| Basic strategy chart | -0.17% |
| Counting, flat bets | -0.10% |
| Counting + bet spread 1–12 units | +0.66% (±0.15, 4M hands) |

"Never bust" sounds careful and loses ~37× more than the chart.

### Rule tweaks (500,000 hands each, basic strategy)

| Table | Edge |
|---|---|
| standard (3:2, S17, surrender, 6 decks) | -0.26% |
| 6:5 blackjack | -1.46% |
| dealer hits soft 17 | -0.47% |
| no surrender | -0.26% |
| 8 decks | -0.49% |

6:5 blackjack costs about 1.36% exactly (P(blackjack) × 0.3). The smaller tweaks are within simulation noise at
500k hands (±~0.3%), which is a lesson in itself: small edges need enormous samples.

### Insurance

EV = 3p − 1, where p = share of tens left. Off the top: p = 96/311 → **−7.4%**. Simulated, always insuring:
-7.1% on the insurance money.

### "Quit while you're ahead"

20,000 sessions: leave at +50, −200 or after 300 hands (10-chip bets, perfect play).
**76% of sessions end up**, average win +54, average loss -186, average session
-3.7. Feels like a system, still loses (optional stopping theorem).

### Betting systems on a 2,000 bankroll

Martingale went broke after **425 hands**. Flat betting lasted 121,690.

### Counting + bet spread

Hi-Lo count, bet 1 unit below true count +2, then 2 units per true count up to 12: **+0.66%**
(95% range +0.51% to +0.82%, 4 million hands under two random generators).
An earlier version said +0.93%: one 200,000-hand run that happened to be lucky; this strategy is too swingy for 200k hands.
Real, but slow:

| Hands | ≈ hours | Chance you're ahead | Expected (10-unit) |
|---|---|---|---|
| 1,000 | 12 | 55% | +140 |
| 10,000 | 125 | 66% | +1,396 |
| 50,000 | 625 | 83% | +6,978 |
| 100,000 | 1,250 | 91% | +13,955 |
| 200,000 | 2,500 | 97% | +27,911 |

10,000 bankroll over ~400 hours (20 runs each):

| Strategy | Unit | Median final | Runs below start | Broke |
|---|---|---|---|---|
| basic, flat | 25 | 4,769 | 75% | 4 of 20 |
| counter + count bets | 10 | 13,938 | 35% | 2 of 20 |
| counter + count bets | 25 | 16,694 | 40% | 8 of 20 |
| counter + count bets | 50 | 0 | 65% | 13 of 20 |

### Luck vs skill: a real session

95 hands by the author: result **+2,950**, worth on average **+389** given the cards and decisions,
so **+2,561 was luck** (+1.3σ). 120/124 decisions matched the best EV.
[Full example report](https://ahryhorets.github.io/blackjack-lab/sample_analysis.html).

### Does the random generator matter?

Every experiment rerun with `random.SystemRandom` (OS entropy) instead of the seeded Mersenne Twister, same sizes:
**23 of 23 results agree within normal noise** (|z| < 2). Martingale over 200 runs each:
median 632 vs 659 hands until broke. Counting + bet sizing at
2M hands each: +0.68% vs +0.64%. The generator doesn't drive the results; the check did
show that the earlier +0.93% counting edge (one 200k run) was a lucky sample. Credit: a reader's question.

---

## How it works

```
game.py     you play: menus, the EV panel, session stats
sim.py      bots play the same rounds, fast, seeded
analyze.py  HTML report from data/hands.jsonl (SVG charts drawn by hand, no libraries)
  └── table.py     one round in the real order: bet → deal → insurance → peek → play → dealer → settle
        ├── cards.py     cards, hand totals (soft aces), shoe with Hi-Lo count and "unseen" cards
        ├── rules.py     every table rule in one dataclass + legal moves
        ├── ev.py        dealer outcome odds (recursive, cached) and EV of every move
        └── strategy.py  basic strategy chart, count deviations, bet systems
storage.py  saves, history, one JSON line per hand
tests.py    19 tests with rigged shoes
```

- **The game and the simulator share one round engine.** The table asks an "agent" for decisions: a human, a bot or
  a test script. Same code, so simulated results describe the game you actually play.
- **EV engine:** the dealer has no choices, so a recursive function follows every possible draw; `lru_cache` makes it
  fast. Uses the cards *you* haven't seen (the hole card counts only when it's turned over) and conditions on the dealer's
  peek. Stand on 20 vs Ace = **+0.655**.
- **Split EV is for both hands** (× 2), insurance is 3p − 1, chips are decimals so 3:2 pays exactly.

### Known simplifications

- When you hit, dealer odds aren't recomputed for every card you might draw (error: a fraction of a percent).
- Split EV ignores resplits.
- True count → edge uses the rule of thumb −0.5% + 0.5% per count.
- One player at the table.

---

## How this was built

Built with AI (Claude), directed, tested and studied by the author. It started as a side project inspired by a uni
Python assignment and is separate from it. Checked, not trusted: unit tests, comparison with published blackjack
tables, a 3,000-hand random-input fuzz run, seeded experiments.

Issues and pull requests welcome, especially "you're wrong about X, here's the proof".

## Licence

MIT. Education only, not gambling or financial advice.
