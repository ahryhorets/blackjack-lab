#!/usr/bin/env python3
"""
tools/build_showcase.py - builds docs/index.html (the GitHub Pages site)
from docs/results.json (tools/experiments.py) and examples/sample_session.jsonl.

    python3 tools/build_showcase.py
"""

from __future__ import annotations

import html
import json
import math
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import analyze                                   # noqa: E402
from ev import (Evaluator, dealer_distribution, fresh_counts,  # noqa: E402
                insurance_ev, stand_ev)
from rules import RulesConfig                    # noqa: E402
from cards import KEY_INDEX                      # noqa: E402
from strategy import HARD, SOFT, PAIRS, UP_ORDER  # noqa: E402

REPO = "https://github.com/ahryhorets/blackjack-lab"
R = json.load(open(os.path.join(ROOT, "docs", "results.json")))
E = html.escape


def pct(x, d=2, sign=True):
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def money(x, sign=False):
    s = f"{abs(x):,.0f}"
    return ("+" if x > 0 and sign else "−" if x < 0 else "") + s


def table(head, rows, nums=()):
    th = "".join(f'<th{" class=n" if i in nums else ""}>{h}</th>' for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f'<td{" class=n" if i in nums else ""}>{c}</td>'
                                    for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def cnt(*rem):
    c = list(fresh_counts(6))
    for k in rem:
        c[KEY_INDEX[k]] -= 1
    return tuple(c)


# ------------------------------------------------------------------ numbers
S = R["styles"]
basic = S["basic"]
rules = R["rules"]
std_key = next(iter(rules))
p_bj = 2 * (24 / 312) * (96 / 311)
p_both = p_bj * (1 - 0.0475)          # dealer has no blackjack too (approx.)
exact_65 = -p_both * 0.3

KNOWN = {"6:5 blackjack": f"{exact_65 * 100:+.2f}% (exact: P(blackjack) × 0.3)",
         "dealer hits soft 17": "≈ −0.2% (published)",
         "no surrender": "≈ −0.08% (published)",
         "8 decks": "≈ −0.02% (published)"}
rule_rows = []
for k, v in rules.items():
    diff = v["edge"] - rules[std_key]["edge"]
    rule_rows.append([E(k), pct(v["edge"]), "" if k == std_key else pct(diff),
                      KNOWN.get(k, "baseline")])

ins = R["insurance"]
sw = R["stop_win"]
sysm = R["systems"]
bk = R["bankroll"]
lr = R["long_run"]

c_a = cnt("T", "T", "A")
ev20 = stand_ev(20, dealer_distribution("A", c_a, RulesConfig()))
c16 = cnt("T", "6", "T")
e16 = Evaluator("T", c16, RulesConfig())
ups = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"]
bust = [dealer_distribution(u, cnt(u), RulesConfig())["bust"] * 100 for u in ups]

# example session
rounds = analyze.read_file(os.path.join(ROOT, "examples", "sample_session.jsonl"))
analyze.enrich(rounds)
N = len(rounds)
net = sum(r["net"] for r in rounds)
exp_ = sum(r["expected"] for r in rounds)
decs = [d for r in rounds for d in r.get("decisions", [])]
best_ok = sum(1 for d in decs if d["cost"] <= 1e-9)
avg_bet = sum(r["bet"] for r in rounds) / N
z = (net - exp_) / (1.15 * avg_bet * math.sqrt(N))
eq = [("Actual result", analyze.cumulative([r["net"] for r in rounds]), "--c1", ""),
      ("What the cards + decisions were worth", analyze.cumulative([r["expected"] for r in rounds]), "--c2", "6 4"),
      ("Same cards, perfect play", analyze.cumulative([r["perfect"] for r in rounds]), "--c3", "2 3")]

chart_rows = []
for t in range(8, 18):
    chart_rows.append([f"{t}+" if t == 17 else str(t)] + [HARD[t][u] for u in UP_ORDER])
for t in range(13, 21):
    chart_rows.append([f"A,{t - 11}"] + [SOFT[t][u] for u in UP_ORDER])
for k in ("A", "T", "9", "8", "7", "6", "5", "4", "3", "2"):
    chart_rows.append([f"{k},{k}"] + ["P" if PAIRS[k][u] == "Y" else "·" for u in UP_ORDER])


def cell(v):
    cls = {"H": "h", "S": "s", "D": "d", "Ds": "d", "R": "r", "P": "p"}.get(v, "")
    return f'<td class="sc {cls}">{v}</td>'


chart_html = ('<div class="tw"><table class="strat"><thead><tr><th>you</th>'
              + "".join(f'<th class="n">{u}</th>' for u in UP_ORDER) + "</tr></thead><tbody>"
              + "".join("<tr><td>" + r[0] + "</td>" + "".join(cell(v) for v in r[1:]) + "</tr>"
                        for r in chart_rows) + "</tbody></table></div>")

css = """
:root{--bg:#fbfbfd;--fg:#1b1f2a;--mute:#5d6475;--line:#e3e5ec;--card:#fff;--code:#f4f5f9;
--c1:#2f6fdf;--c2:#8a8fa0;--c3:#1f9d6b;--neg:#d24b4b;--warn:#c98a12}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#12141a;--fg:#e7e9ef;--mute:#9aa1b2;
--line:#2a2e39;--card:#1a1d25;--code:#161921;--c1:#6c9cff;--c2:#7d8396;--c3:#3fc48d;--neg:#ff7070;--warn:#e6b04a}}
:root[data-theme="dark"]{--bg:#12141a;--fg:#e7e9ef;--mute:#9aa1b2;--line:#2a2e39;--card:#1a1d25;--code:#161921;
--c1:#6c9cff;--c2:#7d8396;--c3:#3fc48d;--neg:#ff7070;--warn:#e6b04a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15.5px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 16px 80px}
.top{display:flex;gap:14px;align-items:center;font-size:13.5px;margin-bottom:22px}.top a{color:var(--c1);text-decoration:none}
.top button{margin-left:auto;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}
h1{font-size:34px;line-height:1.15;margin:0 0 8px}h2{font-size:22px;margin:48px 0 8px;padding-top:16px;border-top:1px solid var(--line)}
h3{font-size:16.5px;margin:26px 0 6px}.sub{color:var(--mute);margin:0 0 18px;font-size:16px}
.side{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:2px 9px;border-radius:10px;margin-bottom:4px}
.side.bad{background:rgba(210,75,75,.14);color:var(--neg)}.side.good{background:rgba(31,157,107,.14);color:var(--c3)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:18px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.kl{color:var(--mute);font-size:12.5px}.kv{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}
.chart{width:100%;height:auto;display:block;background:var(--card);border:1px solid var(--line);border-radius:8px}
.chart .grid{stroke:var(--line)}.chart .zero{stroke:var(--mute);stroke-width:1}
.chart text{fill:var(--mute);font-size:11px}.ylab{text-anchor:end}.xlab{text-anchor:middle}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin:6px 0;font-size:13px;color:var(--mute)}
.key i{display:inline-block;width:14px;height:3px;margin-right:6px;vertical-align:middle}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card);margin:8px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--mute);font-weight:600}.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}tr:last-child td{border-bottom:0}
table.strat td,table.strat th{padding:4px 6px;text-align:center;font-size:12.5px}
.sc.h{background:rgba(210,75,75,.10)}.sc.s{background:rgba(31,157,107,.14)}.sc.d{background:rgba(47,111,223,.16)}
.sc.r{background:rgba(201,138,18,.20)}.sc.p{background:rgba(138,36,51,.14)}
.note{background:var(--card);border-left:3px solid var(--c1);padding:10px 14px;border-radius:4px;margin:12px 0}
.note.bad{border-left-color:var(--neg)}.note.good{border-left-color:var(--c3)}.note.warn{border-left-color:var(--warn)}
code{background:var(--code);border:1px solid var(--line);padding:0 5px;border-radius:4px;font-size:13px}
pre{background:var(--code);border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow-x:auto;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}
.math{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0;
font:13.5px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-x:auto;white-space:pre}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media (max-width:700px){.two{grid-template-columns:1fr}}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.box h4{margin:0 0 6px;font-size:15px}.box ul{margin:0;padding-left:18px}
footer{margin-top:48px;color:var(--mute);font-size:13px;border-top:1px solid var(--line);padding-top:14px}
"""

ruin_rows = [[f'{b["play"]}{" + count bets" if b["bet"] == "count" else ", flat"}', money(b["unit"]),
              money(b["median"]), f'{b["share_down"]:.0%}', f'{b["ruined"]} of {b["runs"]}']
             for b in bk]

style_rows = [
    ["Plays like the dealer (hit below 17, never double/split)", pct(S["mimic"]["edge"])],
    ["“Never bust” (stand on any 12+)", pct(S["never_bust"]["edge"])],
    ["Always hit until 21 or bust", pct(S["always_hit"]["edge"])],
    ["Basic strategy chart", pct(basic["edge"])],
    ["Counting, flat bets", pct(S["counter_flat"]["edge"])],
    ["Counting + bet spread 1–12 units", pct(S["counter_spread"]["edge"])],
]

doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blackjack Lab</title>
<meta name="description" content="A blackjack lab in pure Python: how the casino wins, what informed decisions are worth, and how much of a win is luck.">
<style>{css}</style></head><body><main>
<div class="top"><a href="{REPO}">GitHub repo</a><a href="{REPO}#run-it">Run it</a><a href="sample_analysis.html">Example analysis</a>
<button id="themeBtn" type="button">Theme</button></div>

<h1>The house doesn't need luck.<br>Do you?</h1>
<p class="sub">A blackjack lab in pure Python. It plays millions of hands to show two things: how the casino quietly
wins, and what an informed decision is actually worth, measured, not felt.</p>

<div class="kpis">
<div class="kpi"><div class="kl">Perfect play, still</div><div class="kv">{pct(basic["edge"])}</div></div>
<div class="kpi"><div class="kl">“Never bust” player</div><div class="kv">{pct(S["never_bust"]["edge"])}</div></div>
<div class="kpi"><div class="kl">Sessions that “won”</div><div class="kv">{sw["share_winning"]:.0%}</div></div>
<div class="kpi"><div class="kl">…average session</div><div class="kv">{sw["avg_result"]:+.1f} chips</div></div>
<div class="kpi"><div class="kl">Martingale, 2,000 bankroll</div><div class="kv">broke in {sysm["martingale"]["ruined_at"]:,} hands</div></div>
<div class="kpi"><div class="kl">Counting + bet sizing</div><div class="kv">{pct(S["counter_spread"]["edge"])}</div></div>
</div>

<div class="note warn"><b>Disclaimer.</b> Education only. No real money, not gambling advice, not financial advice.
The casino keeps its edge against almost everyone, and card counting, while legal in most places, gets you banned.
If gambling is a problem for you or someone close to you, please talk to someone and get support.</div>

<h2>Part 1 · How the casino wins</h2>
<span class="side bad">the house's playbook</span>

<h3>1. One unfair rule is enough</h3>
<p>Everything in blackjack is symmetric except one thing: <b>you act first</b>. If you bust, you lose, even if the dealer busts
afterwards. That single rule is the house edge. Every "extra" you get (3:2 blackjacks, doubling, splitting, surrender)
only exists to win some of it back, and only if you use them at the right moments.</p>

<h3>2. Bad habits are where the real money is</h3>
{analyze.bar_chart(["dealer copy", "never bust", "basic", "count flat", "count + bets"],
                   [S["mimic"]["edge"] * 100, S["never_bust"]["edge"] * 100, basic["edge"] * 100,
                    S["counter_flat"]["edge"] * 100, S["counter_spread"]["edge"] * 100])}
{table(["how you play", "edge (200,000 hands each)"], style_rows, nums={1})}
<p>"Never bust" sounds careful. It loses about <b>{S["never_bust"]["edge"] / basic["edge"]:.0f}× more</b> than the chart, because standing on 12–16 against a 7–A loses
more than half the time. The casino doesn't need to cheat: intuition does the work.</p>

<h3>3. The small print: rule tweaks</h3>
{table(["table rules", "simulated edge (500k hands)", "vs standard", "known value"], rule_rows, nums={1, 2})}
<p><b>6:5 blackjack is the big one.</b> Blackjacks arrive about {p_bj:.2%} of the time; paying 1.2 instead of 1.5 takes 0.3 bets each time.
It looks like a tiny change on the felt and it multiplies the house edge several times. Smaller tweaks (H17, no surrender)
are within the simulation's noise at 500k hands, which is itself a lesson: <b>small edges need huge samples to see</b>.</p>

<h3>4. Insurance: the side bet that sounds like protection</h3>
<div class="math">Insurance pays 2:1 if the dealer's hidden card is a ten.
Tens left with an Ace showing: 96 of 311 cards = {96 / 311:.1%}
EV = 2 × p − 1 × (1 − p) = 3p − 1 = {insurance_ev(cnt("A")):+.3f}  →  you lose ~7.4% of every insurance bet
Simulated, always insuring: {pct(ins["always"]["insurance_return"])} on {money(ins["always"]["insurance_staked"])} staked</div>
<p>It only breaks even when more than 1 in 3 unseen cards are tens. Off the top of the shoe, never.</p>

<h3>5. "Quit while you're ahead"</h3>
<p>{sw["sessions"]:,} sessions of 10-chip bets with perfect basic strategy. Leave at <b>+{sw["win_stop"]}</b>, at
<b>−{sw["loss_stop"]}</b>, or after {sw["max_rounds"]} hands.</p>
<div class="kpis">
<div class="kpi"><div class="kl">Sessions that ended up</div><div class="kv">{sw["share_winning"]:.0%}</div></div>
<div class="kpi"><div class="kl">Average winning session</div><div class="kv">{money(sw["avg_win"], True)}</div></div>
<div class="kpi"><div class="kl">Average losing session</div><div class="kv">{money(sw["avg_loss"], True)}</div></div>
<div class="kpi"><div class="kl">Average session overall</div><div class="kv">{sw["avg_result"]:+.1f}</div></div>
</div>
<p>It <i>feels</i> like a winning system: most nights you go home up. But the losing nights are about
{abs(sw["avg_loss"] / sw["avg_win"]):.1f}× bigger, and the total is still negative. No stopping rule can change the value of the hands you
do play. Mathematicians call it the optional stopping theorem; casinos call it a good night.</p>

<h3>6. Martingale: double after every loss</h3>
<p>On a 2,000 bankroll with 10-chip units, martingale went broke after <b>{sysm["martingale"]["ruined_at"]:,} hands</b>.
Flat betting the same game lasted {sysm["flat"]["rounds"]:,} hands. Seven losses in a row (about 1 in 100 streaks) needs a 1,280 bet;
the table limit and your bankroll end the system. Many small wins, one huge loss: the same shape as "quit while ahead".</p>

<div class="note bad"><b>The playbook in one line:</b> frequent small wins, rare big losses, fast hands, and rules nobody reads.
None of it needs luck. It needs volume.</div>

<h2>Part 2 · What an informed decision is worth</h2>
<span class="side good">the math side</span>

<h3>7. Every decision has a price tag</h3>
<p>The engine computes the expected value (EV) of every legal move from the exact cards left in the shoe.
EV = average result in bets, if you made this choice forever.</p>
{table(["situation", "move", "EV", "what it means"], [
    ["20 vs dealer Ace", "stand", f"{ev20:+.3f}", "the dealer already peeked: no blackjack. A naive model says +0.15"],
    ["16 vs dealer 10", "hit", f"{e16.hit(16, False, c16):+.3f}", "both options lose; hitting loses less"],
    ["16 vs dealer 10", "stand", f"{e16.stand(16):+.3f}", ""],
    ["16 vs dealer 10", "surrender", "−0.500", "the best of the three"],
], nums={2})}
{analyze.bar_chart(ups, bust)}
<p>Dealer bust % by upcard. 2–6 bust 35–42% of the time: stand on weak hands and let them. 7–A bust under 27%: you have to improve.</p>

<h3>8. The chart: all those EVs, memorised</h3>
{chart_html}
<p><b>H</b> hit · <b>S</b> stand · <b>D</b> double (else hit) · <b>Ds</b> double (else stand) · <b>R</b> surrender · <b>P</b> split.
6 decks, dealer stands on soft 17, double after split, late surrender. This turns ~−2% (typical player) into ~−0.4%.</p>

<h3>9. The only real edge: count, then size your bets</h3>
<p>Cards that have been dealt don't come back until the shuffle, so the shoe has memory. Hi-Lo counting: 2–6 = +1, 7–9 = 0,
tens and Aces = −1; divide by decks left to get the true count. Rich shoe → bet more.</p>
<p>Counting with a flat bet barely helps ({pct(S["counter_flat"]["edge"])}). Betting 1 unit in bad shoes and up to 12 units in good ones:
<b>{pct(S["counter_spread"]["edge"])}</b>. But that edge is thin and slow:</p>
{table(["hands played", "≈ hours", "chance you're ahead", "expected profit (10-unit)"],
       [[f'{t["rounds"]:,}', f'{t["rounds"] / 80:,.0f}', f'{t["p_ahead"]:.0%}', money(t["expected"], True)] for t in lr["table"]],
       nums={0, 1, 2, 3})}
<h3>10. Bankroll decides whether you survive the swings</h3>
<p>10,000 bankroll, {bk[0]["rounds"]:,} hands (~400 hours), {bk[0]["runs"]} runs each:</p>
{table(["strategy", "unit", "median final", "runs below 10,000", "went broke"], ruin_rows, nums={1, 2, 3, 4})}
<p>Same edge, bigger bets → more ruin. A safe unit is about 1/1,000 of the bankroll (Kelly sizing).</p>

<h3>11. Luck vs skill, on a real session</h3>
<p>{N} hands played by the author with the decision panel on. The analyzer splits the result into what the cards and decisions
were worth (grey) and what luck added on top (blue minus grey):</p>
{analyze.line_chart(eq)}
<div class="math">result {money(net, True)}   ·   worth on average {money(exp_, True)}   ·   luck {money(net - exp_, True)} ({z:+.1f}σ, normal)
decisions matching the best EV: {best_ok} of {len(decs)} ({best_ok / len(decs):.0%})</div>
<p>Good decisions, mostly lucky result. That's the point: <b>an informed decision doesn't guarantee the outcome, it puts the
average on your side</b>. Full report: <a href="sample_analysis.html">example analysis</a>.</p>

<h2 id="run-it">Part 3 · Run it yourself</h2>
<pre>git clone {REPO}.git
cd blackjack-lab
python3 game.py                       # play, with the EV panel on
python3 sim.py --compare 50000        # every strategy side by side
python3 sim.py --table                # dealer odds + EV of standing
python3 tests.py                      # 19 tests
python3 analyze.py                    # deep analysis of your own hands</pre>
<p>Python 3.10+, standard library only. Nothing to install.</p>
<div class="two">
<div class="box"><h4>Try this</h4><ul>
<li>Play 100 hands with the panel on, then menu 8 for your luck vs skill report</li>
<li>Turn on x-ray mode (table menu) and see how knowing the next card changes the right move</li>
<li>Set <code>blackjack_pays = 1.2</code> in <code>rules.py</code> and rerun the sim</li></ul></div>
<div class="box"><h4>Break it</h4><ul>
<li>Find a hand where the panel's best move looks wrong, then prove it with the sim</li>
<li>Write a bot that beats basic strategy without counting (spoiler: you can't, but try)</li>
<li>Open an issue with what we should test next</li></ul></div>
</div>

<h2>Part 4 · How this was built</h2>
<p>Built with AI (Claude) and directed, tested and studied by the author. It started as a side project inspired by a
uni Python assignment, and is completely separate from it. Everything is checked rather than trusted: 19 unit tests,
results compared against published blackjack tables, a 3,000-hand random-input fuzz run, and every experiment is
seeded, so you get the same numbers.</p>
<p><b>Known simplifications:</b> dealer odds aren't recomputed for every card you might draw; split EV ignores resplits;
the count-to-edge rule (−0.5% + 0.5% per true count) is a rule of thumb; one player at the table.</p>

<footer>Generated {date.today():%d %b %Y} from <code>docs/results.json</code> (seed {R["seed"]}). MIT licence.
Education only, not gambling or financial advice.</footer>
</main>
<script>
(function(){{var K='bjlab-theme',r=document.documentElement;
try{{var t=localStorage.getItem(K);if(t)r.setAttribute('data-theme',t);}}catch(e){{}}
document.getElementById('themeBtn').addEventListener('click',function(){{
var c=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
var n=c==='dark'?'light':'dark';r.setAttribute('data-theme',n);try{{localStorage.setItem(K,n);}}catch(e){{}}}});}})();
</script></body></html>"""

with open(os.path.join(ROOT, "docs", "index.html"), "w", encoding="utf-8") as f:
    f.write(doc)
print("wrote docs/index.html")

# ------------------------------------------------------------------ README
PAGES = "https://ahryhorets.github.io/blackjack-lab/"
rule_md = "\n".join(f"| {k} | {v['edge'] * 100:+.2f}% |" for k, v in rules.items())
ruin_md = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in ruin_rows)
long_md = "\n".join(f"| {t['rounds']:,} | {t['rounds'] / 80:,.0f} | {t['p_ahead']:.0%} | {t['expected']:+,.0f} |"
                    for t in lr["table"])
readme = f"""# Blackjack Lab 🃏

**The house doesn't need luck. Do you?**

A blackjack engine, simulator and analyzer in pure Python (standard library only). It plays millions of hands to show
two sides of the same game:

- **How the casino wins:** one asymmetric rule, bad intuition, small-print rule tweaks, insurance, and betting
  "systems" that feel like winning.
- **What an informed decision is worth:** the exact expected value of every move, the strategy chart, card counting,
  bet sizing, and how to tell luck from skill in your own results.

👉 **Read the findings with charts: [{PAGES}]({PAGES})**

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

**In the game:** `h` hit, `s` stand, `d` double, `p` split, `r` surrender, `?` what the chart/counter say.
At the bet prompt: `k` Kelly bet suggestion, `m` table menu (panel on/off, **x-ray mode** shows the next cards, save).

---

## Findings

Basic rules: 6 decks, 3:2, dealer stands on soft 17, double after split, late surrender, cut card at 75%.
All numbers are from seeded simulations in `docs/results.json`.

### Play style (200,000 hands each, flat bet)

| How you play | Edge |
|---|---|
""" + "\n".join(f"| {r[0]} | {r[1]} |" for r in style_rows) + f"""

"Never bust" sounds careful and loses ~{S["never_bust"]["edge"] / basic["edge"]:.0f}× more than the chart.

### Rule tweaks (500,000 hands each, basic strategy)

| Table | Edge |
|---|---|
{rule_md}

6:5 blackjack costs about {abs(exact_65) * 100:.2f}% exactly (P(blackjack) × 0.3). The smaller tweaks are within simulation noise at
500k hands (±~0.3%), which is a lesson in itself: small edges need enormous samples.

### Insurance

EV = 3p − 1, where p = share of tens left. Off the top: p = 96/311 → **−7.4%**. Simulated, always insuring:
{ins["always"]["insurance_return"] * 100:+.1f}% on the insurance money.

### "Quit while you're ahead"

{sw["sessions"]:,} sessions: leave at +{sw["win_stop"]}, −{sw["loss_stop"]} or after {sw["max_rounds"]} hands (10-chip bets, perfect play).
**{sw["share_winning"]:.0%} of sessions end up**, average win {sw["avg_win"]:+.0f}, average loss {sw["avg_loss"]:+.0f}, average session
{sw["avg_result"]:+.1f}. Feels like a system, still loses (optional stopping theorem).

### Betting systems on a 2,000 bankroll

Martingale went broke after **{sysm["martingale"]["ruined_at"]:,} hands**. Flat betting lasted {sysm["flat"]["rounds"]:,}.

### Counting + bet spread

Hi-Lo count, bet 1 unit below true count +2, then 2 units per true count up to 12: **{S["counter_spread"]["edge"] * 100:+.2f}%**.
Real, but slow:

| Hands | ≈ hours | Chance you're ahead | Expected (10-unit) |
|---|---|---|---|
{long_md}

10,000 bankroll over ~400 hours ({bk[0]["runs"]} runs each):

| Strategy | Unit | Median final | Runs below start | Broke |
|---|---|---|---|---|
{ruin_md}

### Luck vs skill: a real session

{N} hands by the author: result **{net:+,.0f}**, worth on average **{exp_:+,.0f}** given the cards and decisions,
so **{net - exp_:+,.0f} was luck** ({z:+.1f}σ). {best_ok}/{len(decs)} decisions matched the best EV.
[Full example report]({PAGES}sample_analysis.html).

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
"""
with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as f:
    f.write(readme)
print("wrote README.md")
