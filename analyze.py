#!/usr/bin/env python3
"""
analyze.py - deep analysis of every hand you played, as an HTML report.

    python3 analyze.py                 # report for the last player
    python3 analyze.py --player Bbl    # a specific player
    python3 analyze.py --all           # everyone together

Also on the main menu of game.py as "8) Deep analysis".

STUDY NOTES: the three equity lines
- ACTUAL: your real running profit, round by round.
- EXPECTED (all-in EV): what you "deserved" given the cards you were dealt
  and the moves you actually chose. For each round:
      first decision's EV x bet  -  money given away on later decisions
  (the first EV assumes perfect play afterwards, so later mistakes are
  subtracted). Rounds with no decision (blackjacks) count at face value.
  ACTUAL - EXPECTED = LUCK (the cards after your decisions).
- PERFECT: the same rounds if every decision had been the best one.
  PERFECT - EXPECTED = what your mistakes cost = SKILL gap.
- Luck in sigmas: one round has a standard deviation of about 1.15 bets.
  Over N rounds the luck total has SD about 1.15 x average bet x sqrt(N).
  luck / that SD = how unusual your luck was (|z| > 2 happens ~5% of the time).
"""

from __future__ import annotations

import argparse
import html
import math
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

import storage
from cards import rank_key

REPORT = os.path.join(storage.DATA_DIR, "analysis.html")
SD_PER_ROUND = 1.15
FALLBACK_INS_EV = -0.07     # typical 6-deck insurance EV, for old records


# ----------------------------------------------------------------------
# numbers
# ----------------------------------------------------------------------
def enrich(rounds: list[dict]) -> None:
    """Add expected / perfect / luck to each round record."""
    for r in rounds:
        hands_net = sum(h["net"] for h in r["hands"])
        ins_net = r.get("insurance_net", r["net"] - hands_net)
        ins = r.get("insurance", 0) or 0
        ins_ev = r.get("ins_ev")
        exp_ins = ins * (ins_ev if ins_ev is not None else FALLBACK_INS_EV)
        decs = r.get("decisions", [])
        costs = sum(d["cost"] for d in decs)
        if decs:
            exp_main = decs[0]["ev_move"] * r["bet"] - sum(d["cost"] for d in decs[1:])
        else:
            exp_main = hands_net          # blackjack / dealer blackjack: fixed
        r["ins_net"] = ins_net
        r["expected"] = exp_main + exp_ins
        r["perfect"] = exp_main + costs + max(exp_ins, 0.0)
        r["luck"] = r["net"] - r["expected"]
        r["cost"] = costs
        r["up_key"] = rank_key(r["up"][:-1])


def cumulative(vals):
    out, s = [], 0.0
    for v in vals:
        s += v
        out.append(s)
    return out


def pct(a, b):
    return f"{a / b:.1%}" if b else "-"


def m(x: float, sign: bool = False) -> str:
    s = f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}"
    return ("+" + s) if sign and x > 0 else s


def tc_bucket(tc: float) -> str:
    if tc <= -2:
        return "TC ≤ -2"
    if tc < 1:
        return "-2 to +1"
    if tc < 2:
        return "+1 to +2"
    if tc < 3:
        return "+2 to +3"
    return "TC ≥ +3"


TC_ORDER = ["TC ≤ -2", "-2 to +1", "+1 to +2", "+2 to +3", "TC ≥ +3"]
UP_ORDER = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"]
THEORY_BUST = {"2": .354, "3": .374, "4": .396, "5": .418, "6": .423,
               "7": .262, "8": .244, "9": .229, "T": .230, "A": .167}


# ----------------------------------------------------------------------
# SVG charts (no libraries: an SVG is just shapes written as text)
# ----------------------------------------------------------------------
W, H, PAD_L, PAD_R, PAD_T, PAD_B = 900, 300, 64, 16, 16, 34


def _nice_ticks(lo, hi, n=5):
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=raw)
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while t <= hi + step * 0.001:
        ticks.append(round(t, 10))
        t += step
    return ticks


def line_chart(series: list[tuple[str, list[float], str, str]],
               ylabel: str = "", zero: bool = True, height: int = H) -> str:
    """series = [(name, values, css colour var, dash pattern)]"""
    allv = [v for _, vals, _, _ in series for v in vals] + ([0] if zero else [])
    if not allv:
        return ""
    lo, hi = min(allv), max(allv)
    ticks = _nice_ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    n = max(len(s[1]) for s in series)
    pw, ph = W - PAD_L - PAD_R, height - PAD_T - PAD_B

    def x(i):
        return PAD_L + (pw * i / max(n - 1, 1))

    def y(v):
        return PAD_T + ph * (1 - (v - lo) / (hi - lo or 1))

    out = [f'<svg viewBox="0 0 {W} {height}" class="chart" role="img">']
    for t in ticks:
        out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{y(t) + 4:.1f}" class="ylab">{m(t)}</text>')
    if zero and lo < 0 < hi:
        out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="zero"/>')
    for k in _nice_ticks(0, n - 1, 6):
        if 0 <= k <= n - 1:
            out.append(f'<text x="{x(k):.1f}" y="{height - 12}" class="xlab">{int(k) + 1}</text>')
    for name, vals, col, dash in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        d = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<polyline points="{pts}" fill="none" stroke="var({col})" '
                   f'stroke-width="2" stroke-linejoin="round"{d}>'
                   f'<title>{html.escape(name)}</title></polyline>')
    out.append(f'<text x="{PAD_L}" y="{height - 0}" class="xlab" text-anchor="start">round</text>')
    out.append("</svg>")
    legend = "".join(
        f'<span class="key"><i style="background:var({col})"></i>{html.escape(name)}</span>'
        for name, _, col, _ in series)
    return f'<div class="legend">{legend}</div>' + "".join(out)


def bar_chart(labels: list[str], vals: list[float], col: str = "--c1") -> str:
    n = len(vals)
    if not n:
        return ""
    lo, hi = min(0, min(vals)), max(0, max(vals))
    ticks = _nice_ticks(lo, hi, 4)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    height = 240
    pw, ph = W - PAD_L - PAD_R, height - PAD_T - PAD_B
    bw = pw / n

    def y(v):
        return PAD_T + ph * (1 - (v - lo) / (hi - lo or 1))

    out = [f'<svg viewBox="0 0 {W} {height}" class="chart">']
    for t in ticks:
        out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{y(t) + 4:.1f}" class="ylab">{m(t)}</text>')
    for i, (lab, v) in enumerate(zip(labels, vals)):
        x0 = PAD_L + i * bw + bw * 0.15
        y0, y1 = sorted((y(0), y(v)))
        c = col if v >= 0 else "--neg"
        out.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bw * 0.7:.1f}" '
                   f'height="{max(y1 - y0, 1):.1f}" fill="var({c})"><title>{lab}: {m(v)}</title></rect>')
        out.append(f'<text x="{x0 + bw * 0.35:.1f}" y="{height - 12}" class="xlab">{html.escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


# ----------------------------------------------------------------------
# report
# ----------------------------------------------------------------------
def table(head: list[str], rows: list[list], num_from: int = 1) -> str:
    th = "".join(f'<th{" class=n" if i >= num_from else ""}>{h}</th>'
                 for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(
        f'<td{" class=n" if i >= num_from else ""}>{c}</td>'
        for i, c in enumerate(row)) + "</tr>" for row in rows)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def group_rows(rounds, keyf, order=None):
    g = defaultdict(lambda: {"n": 0, "net": 0.0, "bet": 0.0, "exp": 0.0, "win": 0, "lose": 0, "push": 0})
    for r in rounds:
        k = keyf(r)
        if k is None:
            continue
        s = g[k]
        s["n"] += 1
        s["net"] += r["net"]
        s["bet"] += r["bet"]
        s["exp"] += r["expected"]
        for h in r["hands"]:
            o = h["outcome"]
            s["win" if o in ("win", "blackjack") else "push" if o == "push" else "lose"] += 1
    keys = order if order else sorted(g, key=lambda k: -g[k]["n"])
    return [(k, g[k]) for k in keys if k in g]


def read_file(path: str) -> list[dict]:
    """Read any hands.jsonl file (e.g. examples/sample_session.jsonl)."""
    import json
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_report(player: str | None = None, everyone: bool = False,
                 source: str | None = None, out: str | None = None) -> str | None:
    rounds = read_file(source) if source else storage.read_hands()
    if not rounds:
        print("  No hands recorded yet. Play some first.")
        return None
    if not everyone:
        player = player or rounds[-1].get("player")
        rounds = [r for r in rounds if r.get("player") == player]
    enrich(rounds)
    N = len(rounds)
    hands = [h for r in rounds for h in r["hands"]]
    decs = [d for r in rounds for d in r.get("decisions", [])]
    net = sum(r["net"] for r in rounds)
    wag = sum(sum(h["bet"] for h in r["hands"]) + (r.get("insurance") or 0) for r in rounds)
    exp = sum(r["expected"] for r in rounds)
    perf = sum(r["perfect"] for r in rounds)
    luck = net - exp
    avg_bet = sum(r["bet"] for r in rounds) / N
    luck_sd = SD_PER_ROUND * avg_bet * math.sqrt(N)
    z = luck / luck_sd if luck_sd else 0
    outc = defaultdict(int)
    for h in hands:
        outc[h["outcome"]] += 1
    wins = outc["win"] + outc["blackjack"]
    losses = outc["lose"] + outc["bust"] + outc["surrender"]
    best_ok = sum(1 for d in decs if d["cost"] <= 1e-9)
    chart_ok = sum(1 for d in decs if d["move"] == d.get("chart"))
    costs = sum(d["cost"] for d in decs)

    # equity
    actual = cumulative([r["net"] for r in rounds])
    expected = cumulative([r["expected"] for r in rounds])
    perfect = cumulative([r["perfect"] for r in rounds])
    peak, dd = 0.0, []
    for v in actual:
        peak = max(peak, v)
        dd.append(v - peak)
    luck_line = cumulative([r["luck"] for r in rounds])

    # per-round units histogram
    bins = ["≤-3", "-2", "-1.5", "-1", "-0.5", "0", "+0.5", "+1", "+1.5", "+2", "≥+3"]
    edges = [-3, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3]
    hist = [0] * len(bins)
    for r in rounds:
        u = r["net"] / r["bet"]
        i = min(range(len(edges)), key=lambda j: abs(edges[j] - max(-3, min(3, u))))
        hist[i] += 1

    # groups
    by_up = group_rows(rounds, lambda r: r["up_key"], UP_ORDER)
    up_bust = defaultdict(lambda: [0, 0])
    for r in rounds:
        up_bust[r["up_key"]][1] += 1
        if r["dealer_total"] == "bust":
            up_bust[r["up_key"]][0] += 1
    by_tc = group_rows(rounds, lambda r: tc_bucket(r["tc"]), TC_ORDER)

    def start_cat(r):
        s = r["hands"][0]["start"]
        if s.startswith("pair"):
            return s
        kind, t = s.split(" ") if " " in s else ("", s)
        if s == "Blackjack":
            return "Blackjack"
        t = int(t)
        if kind == "hard":
            return ("hard 5-8" if t <= 8 else f"hard {t}" if t <= 11
                    else "hard 12-16" if t <= 16 else "hard 17+")
        return f"soft {t}" if t >= 19 else "soft 13-18"
    by_start = group_rows(rounds, start_cat)

    acts = defaultdict(lambda: {"n": 0, "net": 0.0, "bet": 0.0})
    for h in hands:
        a = h["actions"][0] if h["actions"] else ("blackjack" if h["outcome"] == "blackjack" else "no decision")
        if "double" in h["actions"]:
            a = "double"
        acts[a]["n"] += 1
        acts[a]["net"] += h["net"]
        acts[a]["bet"] += h["bet"]

    mistakes = [(i + 1, d, r) for i, r in enumerate(rounds)
                for d in r.get("decisions", []) if d["cost"] > 1e-9]
    ins_rounds = [r for r in rounds if r.get("insurance")]

    # ---- html ----
    kpi = [
        ("Rounds / hands", f"{N} / {len(hands)}"),
        ("Result", m(net, True)),
        ("Wagered", m(wag)),
        ("Return on action", f"{net / wag:+.2%}" if wag else "-"),
        ("Expected (all-in EV)", m(exp, True)),
        ("Luck", f"{m(luck, True)} ({z:+.1f}σ)"),
        ("EV given away", m(costs)),
        ("Decisions = best EV", f"{best_ok}/{len(decs)} ({pct(best_ok, len(decs))})"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="kl">{a}</div><div class="kv">{b}</div></div>'
                       for a, b in kpi)

    up_rows = []
    for k, s in by_up:
        b, n_ = up_bust[k]
        up_rows.append([k, s["n"], m(s["net"], True), f"{s['net'] / s['bet']:+.2f}",
                        f"{s['exp'] / s['bet']:+.2f}", pct(b, n_), f"{THEORY_BUST[k]:.1%}"])
    tc_rows = [[k, s["n"], m(s["bet"] / s["n"]), m(s["net"], True), f"{s['net'] / s['bet']:+.2f}",
                f"{s['exp'] / s['bet']:+.2f}"] for k, s in by_tc]
    st_rows = [[k, s["n"], pct(s["win"], s["win"] + s["lose"] + s["push"]),
                m(s["net"], True), f"{s['net'] / s['bet']:+.2f}", f"{s['exp'] / s['bet']:+.2f}"]
               for k, s in by_start]
    act_rows = [[k, v["n"], m(v["net"], True), f"{v['net'] / v['bet']:+.2f}"]
                for k, v in sorted(acts.items(), key=lambda kv: -kv[1]["n"])]
    mis_rows = [[i, html.escape(d["hand"]), d["up"], d["move"], d["best"], d.get("chart", ""),
                 f"{d['ev_move']:+.3f}", f"{d['ev_best']:+.3f}", m(d["cost"])]
                for i, d, r in sorted(mistakes, key=lambda t: -t[1]["cost"])]
    ins_rows = [[rounds.index(r) + 1, m(r["insurance"]), f"{r['tc']:+.1f}",
                 "yes" if r.get("dealer_total") == "Blackjack" else "no",
                 m(r["ins_net"], True),
                 f"{r['ins_ev']:+.3f}" if r.get("ins_ev") is not None else "≈-0.07"]
                for r in ins_rounds]
    log_rows = []
    for i, r in enumerate(rounds):
        hs = " | ".join(f"{html.escape(h['cards'])} → {h['outcome']}" for h in r["hands"])
        moves = ", ".join(d["move"] + ("" if d["cost"] <= 1e-9 else "✗") for d in r.get("decisions", []))
        log_rows.append([i + 1, m(r["bet"]), f"{r['tc']:+.1f}", html.escape(r["dealer"]),
                         r["dealer_total"], hs, moves, m(r["net"], True),
                         f"{r['expected']:+.0f}", m(actual[i], True)])

    who = "all players" if everyone else html.escape(str(player))
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>bj2 Deep Analysis</title>
<style>
:root{{--bg:#fbfbfd;--fg:#1b1f2a;--mute:#5d6475;--line:#e3e5ec;--card:#fff;
--c1:#2f6fdf;--c2:#8a8fa0;--c3:#1f9d6b;--neg:#d24b4b;--warn:#c98a12}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#12141a;--fg:#e7e9ef;--mute:#9aa1b2;
--line:#2a2e39;--card:#1a1d25;--c1:#6c9cff;--c2:#7d8396;--c3:#3fc48d;--neg:#ff7070;--warn:#e6b04a}}}}
:root[data-theme="dark"]{{--bg:#12141a;--fg:#e7e9ef;--mute:#9aa1b2;--line:#2a2e39;--card:#1a1d25;
--c1:#6c9cff;--c2:#7d8396;--c3:#3fc48d;--neg:#ff7070;--warn:#e6b04a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:19px;margin:36px 0 8px;padding-top:12px;border-top:1px solid var(--line)}}
h3{{font-size:16px;margin:20px 0 6px}}p,li{{color:var(--fg)}}.sub{{color:var(--mute);margin:0 0 18px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
.kl{{color:var(--mute);font-size:12.5px}}.kv{{font-size:19px;font-weight:600;font-variant-numeric:tabular-nums}}
.chart{{width:100%;height:auto;display:block;background:var(--card);border:1px solid var(--line);border-radius:8px}}
.chart .grid{{stroke:var(--line)}}.chart .zero{{stroke:var(--mute);stroke-width:1}}
.chart text{{fill:var(--mute);font-size:11px}}.ylab{{text-anchor:end}}.xlab{{text-anchor:middle}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;margin:6px 0;font-size:13px;color:var(--mute)}}
.key i{{display:inline-block;width:14px;height:3px;margin-right:6px;vertical-align:middle}}
.tw{{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}th,td{{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}
th{{color:var(--mute);font-weight:600}}.n{{text-align:right;font-variant-numeric:tabular-nums}}
tr:last-child td{{border-bottom:0}}details{{margin-top:10px}}summary{{cursor:pointer;color:var(--c1)}}
.note{{background:var(--card);border-left:3px solid var(--c1);padding:10px 14px;border-radius:4px;margin:10px 0}}
code{{background:var(--line);padding:1px 5px;border-radius:4px;font-size:13px}}
</style></head><body><main>
<h1>bj2 deep analysis</h1>
<p class="sub">Player: {who} · {N} rounds · generated {datetime.now():%d %b %Y %H:%M} from <code>data/hands.jsonl</code></p>
<div class="kpis">{kpi_html}</div>

<h2>1. Equity curve</h2>
{line_chart([("Actual result", actual, "--c1", ""), ("Expected given your cards and moves", expected, "--c2", "6 4"), ("Perfect play on the same cards", perfect, "--c3", "2 3")])}
<div class="note"><b>How to read it.</b> Blue is your real money. Grey dashed is what your cards and your decisions were
worth on average. Green dotted is the same cards played perfectly. <b>Blue minus grey = luck</b>
({m(luck, True)}, that's {z:+.1f} standard deviations; anything inside ±2 is normal noise).
<b>Green minus grey = your mistakes</b> ({m(perf - exp)}: decisions {m(costs)}, insurance {m(perf - exp - costs)}). Only the second one is under your control.</div>

<h3>Luck, running total</h3>
{line_chart([("Cumulative luck (actual - expected)", luck_line, "--warn", "")], height=220)}

<h3>Drawdown from the peak</h3>
{line_chart([("Drawdown", dd, "--neg", "")], height=200)}
<p>Deepest fall from a high: <b>{m(min(dd) if dd else 0)}</b>. Even a winning session goes through holes like this; the
simulator showed basic strategy players routinely sit 30-70 bets below their peak.</p>

<h3>Bet size and true count</h3>
{line_chart([("Bet", [r["bet"] for r in rounds], "--c1", "")], zero=False, height=180)}
{line_chart([("True count when the bet was placed", [r["tc"] for r in rounds], "--c3", "")], height=180)}
<p>A counter's two lines move together: big bets when the count is high. If your bets go up after losses instead,
that's chasing, which the martingale test showed is the fastest way to ruin.</p>

<h2>2. Results</h2>
<h3>Every round in bet units</h3>
{bar_chart(bins, hist, "--c1")}
<p>Hands: won {wins} ({pct(wins, len(hands))}), lost {losses} ({pct(losses, len(hands))}), pushed {outc["push"]}
({pct(outc["push"], len(hands))}). Blackjacks {outc["blackjack"]} (expected about 4.7% of rounds = {0.047 * N:.1f}),
busts {outc["bust"]}, surrenders {outc["surrender"]}. Typical play wins ~43%, loses ~48%, pushes ~9%:
you lose more hands than you win, and doubles, splits and 3:2 blackjacks pull it back.</p>

<h3>By your first move</h3>
{table(["move", "hands", "result", "per bet"], act_rows)}

<h3>By starting hand</h3>
{table(["start", "rounds", "won", "result", "per bet", "expected per bet"], st_rows)}

<h3>By dealer upcard</h3>
{table(["upcard", "rounds", "result", "per bet", "expected per bet", "dealer bust (you)", "dealer bust (theory)"], up_rows)}

<h3>By true count</h3>
{table(["count", "rounds", "avg bet", "result", "per bet", "expected per bet"], tc_rows)}
<p>Theory: each +1 of true count adds about +0.5% to your edge. With under a few thousand rounds per row, the "per bet"
column is mostly luck; the "expected" column is the cleaner signal.</p>

<h2>3. Decisions</h2>
<p>{len(decs)} decisions. Matched the best EV {best_ok} times ({pct(best_ok, len(decs))}); matched the basic
strategy chart {chart_ok} times ({pct(chart_ok, len(decs))}). Total EV given away: <b>{m(costs)}</b>.
(Chart and best EV can differ: the EV engine sees the exact cards left, the chart assumes a fresh shoe.)</p>
{table(["round", "hand", "vs", "you", "best", "chart", "EV you", "EV best", "cost"], mis_rows, 6) if mis_rows else "<p>No mistakes. Every decision was the best EV.</p>"}

<h3>Insurance</h3>
{table(["round", "stake", "TC", "dealer BJ", "result", "EV / unit"], ins_rows) if ins_rows else "<p>Never taken.</p>"}
<p>Insurance is a side bet that the hole card is a ten. It pays 2:1, so it only wins long-run when more than 1 in 3 unseen
cards are tens (EV = 3p - 1 &gt; 0), which needs a true count around +3. Off the top of a 6-deck shoe it loses about 7% per unit.</p>

<h2>4. Every round</h2>
<details><summary>Show all {N} rounds</summary>
{table(["#", "bet", "TC", "dealer", "dealer total", "your hand(s)", "moves (✗ = not best)", "result", "expected", "running"], log_rows, 0)}
</details>

<h2>5. Strategy lab: how the simulator tests work</h2>
<p>The simulator (<code>python3 sim.py</code>) plays bots through exactly the same <code>table.py</code> round code
you play through. Only the decision-maker changes. For each strategy it plays N rounds from a shuffled 6-deck shoe and measures:</p>
<ul>
<li><b>Edge</b> = total won ÷ total wagered. -0.5% means you lose 50 cents per 100 bet, on average.</li>
<li><b>95% range</b> = edge ± 1.96 × SD ÷ √N. One round has SD ≈ 1.15 bets, so after 200,000 rounds the
range is still about ±0.45%. That's why the basic strategy result (-0.17%) is "consistent with -0.4%".</li>
<li><b>Max drawdown</b>: deepest fall from a peak. <b>Ruined</b>: balance fell below the minimum bet.</li>
</ul>
<h3>The players</h3>
{table(["bot", "how it decides", "edge (200k rounds)"], [
    ["basic", "Looks up the basic strategy chart (menu 5): hit/stand/double/split/surrender for every hand vs every upcard. No memory of cards.", "-0.17%"],
    ["counter", "Same chart, plus Hi-Lo: 2-6 = +1, 7-9 = 0, tens/Aces = -1. Running count ÷ decks left = true count. At certain counts it changes plays (the 'Illustrious 18', e.g. stand 16 vs 10 at TC ≥ 0) and takes insurance at TC ≥ +3.", "-0.10% flat bet"],
    ["counter + count bets", "Counter's play, and bets 1 unit at TC &lt; 2, then 2 units per true count, max 12 units. Bets big only when the shoe favours the player.", "+0.93%"],
    ["mimic", "Plays like the dealer: hit below 17, never double or split.", "-5.74%"],
    ["never_bust", "Stands on any hard 12+, so it never busts.", "-6.28%"],
    ["always_hit", "Hits until bust or 21.", "-64.6%"],
    ["martingale", "Basic play, but doubles the bet after every loss and resets after a win. Bankroll 2,000.", "ruined in 425 rounds"],
], 2)}
<h3>Why each result comes out the way it does</h3>
<ul>
<li><b>The house edge comes from one rule:</b> if you bust, you lose, even if the dealer busts later. Everything else is symmetric or favours you (3:2 blackjack, doubling, splitting, surrender).</li>
<li><b>Mimic the dealer</b> keeps that disadvantage and gives up all your extras: -5.7%.</li>
<li><b>Never bust</b> avoids the double-bust trap, but standing on 12-16 against a 7-A loses ~50-55% of the time, and the dealer only busts ~23% vs a ten: -6.3%.</li>
<li><b>Basic strategy</b> uses every option at the right moment and cuts the edge to about -0.4%. That's the most you can get without tracking cards.</li>
<li><b>Counting with a flat bet</b> barely helps: the deviations add about 0.1-0.2%. The money in counting comes from the <b>bet spread</b>: small bets in bad shoes, big bets in good ones. Average edge per hand is still slightly negative, but weighted by bet size it turns positive (+0.93%).</li>
<li><b>Martingale</b> doesn't change the edge at all (every bet is still -0.4%). It just stacks big bets onto losing streaks. Seven losses in a row (about 1 in 100 sequences) needs 1,280 for the next bet, and the table max of 1,000 makes recovery impossible. Many small wins, one huge loss.</li>
</ul>
<p>Rerun any of it: <code>python3 sim.py --compare 50000</code>, <code>python3 sim.py --play counter --bet count --bankroll 2000</code>,
<code>python3 sim.py --cutcard 100000</code> (deeper cut card = more high-count hands = bigger counter edge).</p>
</main></body></html>"""
    out = out or REPORT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    return out


def open_file(path: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            import webbrowser
            webbrowser.open("file://" + path)
    except OSError:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--player")
    ap.add_argument("--file", help="analyze this hands.jsonl instead of data/")
    ap.add_argument("--out", help="write the report here")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    p = build_report(a.player, a.all, a.file, a.out)
    if p:
        print(f"Report: {p}")
        if not a.no_open:
            open_file(p)


if __name__ == "__main__":
    main()
