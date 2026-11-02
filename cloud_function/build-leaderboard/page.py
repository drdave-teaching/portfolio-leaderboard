# page.py: the public leaderboard page (nicknames only: no NetIDs, no emails, no holdings).

import html
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CSS = """
:root { --ink:#13233a; --muted:#5b6b80; --line:#e3e8ef; --navy:#0e2a52; --up:#13804b; --down:#c0392b; --bg:#f6f8fb; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font-family: "Segoe UI", Arial, sans-serif; font-size:15px; }
.wrap { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
header { background:var(--navy); color:white; padding:22px 16px; }
header .wrap { padding:0 16px; }
h1 { margin:0; font-size:26px; }
.sub { margin-top:6px; color:#c9d6ea; font-size:14px; }
.cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin:20px 0; }
.card { background:white; border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.card .big { font-size:26px; font-weight:700; }
.card .lab { color:var(--muted); font-size:13px; margin-top:2px; }
h2 { font-size:19px; margin:28px 0 10px; }
.tablebox { overflow-x:auto; background:white; border:1px solid var(--line); border-radius:10px; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { padding:9px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
th { background:#eef2f7; font-weight:600; color:var(--muted); font-size:12.5px; }
td.l, th.l { text-align:left; }
td.fund { font-weight:600; }
td.theme { color:var(--muted); white-space:normal; min-width:140px; }
.up { color:var(--up); } .down { color:var(--down); }
img.chart { width:100%; background:white; border:1px solid var(--line); border-radius:10px; }
.note { color:var(--muted); font-size:13.5px; line-height:1.5; }
ul.how { line-height:1.6; }
"""


def pct(value, signed=True):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    css = "up" if value > 0 else ("down" if value < 0 else "")
    text = ("%+.2f%%" if signed else "%.2f%%") % value
    return '<span class="%s">%s</span>' % (css, text)


def plain_pct(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    return "%.2f%%" % value


def points(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    css = "up" if value > 0 else ("down" if value < 0 else "")
    return '<span class="%s">%+.2f</span>' % (css, value)


def make_chart(values, board, benchmark_path):
    """Every fund's with-rules value since it started, plus the S&P 500 from the first start day."""
    figure = plt.figure(figsize=(11, 5), dpi=110)
    axis = figure.add_subplot(111)
    rules = values[values["portfolio"] == "with_rules"]
    nicknames = {}
    for i in range(len(board)):
        nicknames[board.loc[i, "netid"]] = board.loc[i, "nickname"]
    for netid in nicknames:
        mine = rules[rules["netid"] == netid]
        if len(mine) == 0:
            continue
        axis.plot(pd.to_datetime(mine["date"]), mine["value"], linewidth=1.6, alpha=0.85, label=nicknames[netid])
    if len(benchmark_path) > 0:
        axis.plot(benchmark_path.index, benchmark_path.values, color="black", linewidth=3, label="S&P 500 (SPY)")
    axis.axhline(10000, color="#bbbbbb", linestyle="--", linewidth=1)
    axis.set_ylabel("Value of $10,000")
    axis.set_title("Every fund (with its rules) since it started")
    axis.grid(alpha=0.25)
    if len(nicknames) <= 24:
        axis.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=False)
    figure.autofmt_xdate()
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    return buffer.getvalue()


def render(result, updated_et, chart_name="chart.png"):
    board = result["board"]
    pending = result["pending"]
    out = []
    out.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    out.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    out.append("<title>OPIM 5641 Portfolio Leaderboard</title><style>%s</style></head><body>" % CSS)
    out.append("<header><div class='wrap'><h1>OPIM 5641 · Portfolio Leaderboard</h1>")
    sub = "Fall 2026 · every fund starts with $10,000 · updated %s" % html.escape(updated_et)
    if result["last_close"]:
        sub += " · prices through the close of %s" % html.escape(result["last_close"])
    out.append("<div class='sub'>%s</div></div></header><div class='wrap'>" % sub)

    # the cards
    n_live = len(board)
    n_wait = len(pending)
    out.append("<div class='cards'>")
    out.append("<div class='card'><div class='big'>%d</div><div class='lab'>funds on the board</div></div>" % n_live)
    if n_wait > 0:
        out.append("<div class='card'><div class='big'>%d</div><div class='lab'>funds starting at the next close</div></div>" % n_wait)
    if n_live > 0:
        spy = result["benchmark_path"]
        if len(spy) > 0:
            spy_growth = 100 * (spy.iloc[-1] / spy.iloc[0] - 1)
            out.append("<div class='card'><div class='big'>%s</div><div class='lab'>S&amp;P 500 since the first fund started</div></div>" % pct(spy_growth))
        beat_spy = int((board["rules_minus_spy_pct"] > 0).sum())
        rules_won = int((board["rules_minus_no_rules_pct"] > 0).sum())
        out.append("<div class='card'><div class='big'>%d of %d</div><div class='lab'>funds ahead of the S&amp;P 500</div></div>" % (beat_spy, n_live))
        out.append("<div class='card'><div class='big'>%d of %d</div><div class='lab'>funds where the rules beat no rules</div></div>" % (rules_won, n_live))
    out.append("</div>")

    if n_live > 0:
        out.append("<h2>The leaderboard (ranked by your fund: the portfolio with your rules)</h2>")
        out.append("<div class='tablebox'><table><tr><th>Rank</th><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th>Value</th><th>Since start</th><th>Its no-rules twin</th><th>Rules vs no rules</th>"
                   "<th>vs S&amp;P 500</th><th>Worst drop</th><th>Stocks</th><th>Changes</th><th>Started</th></tr>")
        for i in range(len(board)):
            r = board.loc[i]
            out.append("<tr><td>%d</td><td class='l fund'>%s</td><td class='l theme'>%s</td><td>$%s</td><td>%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (
                           r["rank"], html.escape(str(r["nickname"])), html.escape(str(r["theme"])),
                           "{:,.0f}".format(r["with_rules_value"]), pct(r["with_rules_growth_pct"]),
                           pct(r["no_rules_growth_pct"]), points(r["rules_minus_no_rules_pct"]),
                           points(r["rules_minus_spy_pct"]), plain_pct(r["with_rules_worst_drop_pct"]),
                           r["stocks_with_rules"], r["changes"], html.escape(str(r["started"]))))
        out.append("</table></div>")
        out.append("<p class='note'>\"Rules vs no rules\" and \"vs S&amp;P 500\" are percentage points over the same days. "
                   "\"Worst drop\" is the biggest fall from a high point so far.</p>")
        out.append("<h2>The race</h2><img class='chart' src='%s' alt='Value of every fund over time'>" % chart_name)

    if n_wait > 0:
        out.append("<h2>Starting at the next market close</h2>")
        out.append("<div class='tablebox'><table><tr><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th>Stocks (with rules)</th><th>Stocks (no rules)</th><th>Counts from the close on</th></tr>")
        for i in range(len(pending)):
            r = pending.loc[i]
            out.append("<tr><td class='l fund'>%s</td><td class='l theme'>%s</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (
                html.escape(str(r["nickname"])), html.escape(str(r["theme"])), r["stocks_with_rules"],
                r["stocks_no_rules"], html.escape(str(r["starts"]))))
        out.append("</table></div>")

    if n_live == 0 and n_wait == 0:
        out.append("<p class='note'>No funds yet. Entries from the Studio 5 notebook show up here within 15 minutes.</p>")

    out.append("<h2>How it works</h2><ul class='how'>"
               "<li>Each entry has two portfolios from the Studio 5 model: <b>with your rules</b> (your fund, ranked here) and its <b>no-rules twin</b>.</li>"
               "<li>Both start with $10,000 at the first market close after you submit, and are held until you change them.</li>"
               "<li>You can change your portfolio as often as you like by re-running the cell. A change counts from the next close, "
               "and starts from what your fund was worth that day. Every change is kept.</li>"
               "<li>Prices are daily closing prices, adjusted for splits and dividends. The page updates every 15 minutes; "
               "the numbers move once a day, after the close.</li></ul>")
    out.append("</div></body></html>")
    return "".join(out)
