# page.py: the public leaderboard page (nicknames only: no NetIDs, no emails, no holdings).

import html
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
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
td.fund a { color:var(--navy); }
td.theme { color:var(--muted); white-space:normal; min-width:140px; }
.up { color:var(--up); } .down { color:var(--down); }
img.chart { width:100%; background:white; border:1px solid var(--line); border-radius:10px; }
.note { color:var(--muted); font-size:13.5px; line-height:1.5; }
ul.how { line-height:1.6; }
.tabs { display:flex; gap:6px; flex-wrap:wrap; margin:6px 0 12px; }
.tab { border:1px solid var(--line); background:white; color:var(--ink); border-radius:999px; padding:7px 16px;
       font-size:14px; cursor:pointer; font-family:inherit; }
.tab.on { background:var(--navy); color:white; border-color:var(--navy); }
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


def share(value):
    if value is None or (isinstance(value, float) and np.isnan(value)) or value < 0.05:
        return "-"
    return "%.1f%%" % value


def money_diff(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    css = "up" if value > 0 else ("down" if value < 0 else "")
    sign = "+" if value >= 0 else "-"
    return '<span class="%s">%s$%s</span>' % (css, sign, "{:,.0f}".format(abs(value)))


def points(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    css = "up" if value > 0 else ("down" if value < 0 else "")
    return '<span class="%s">%+.2f</span>' % (css, value)


def dollars(value, position):
    return "${:,.0f}".format(value)


def make_chart(values, board, benchmark_path):
    """Every fund's with-rules value since it started, plus the S&P 500 from the first start day.
    None until there are at least two closes (a line through one point draws nothing)."""
    rules = values[values["portfolio"] == "with_rules"]
    if len(rules) == 0 or rules["date"].nunique() < 2:
        return None
    figure = plt.figure(figsize=(11, 5), dpi=110)
    axis = figure.add_subplot(111)
    nicknames = {}
    for i in range(len(board)):
        nicknames[board.loc[i, "netid"]] = board.loc[i, "nickname"]
    for netid in nicknames:
        mine = rules[rules["netid"] == netid]
        if len(mine) == 0:
            continue
        axis.plot(pd.to_datetime(mine["date"]), mine["value"], linewidth=1.6, alpha=0.85, marker="o", markersize=3,
                  label=nicknames[netid])
    if len(benchmark_path) > 0:
        axis.plot(benchmark_path.index, benchmark_path.values, color="black", linewidth=3, marker="o", markersize=3,
                  label="S&P 500 (SPY)")
    axis.axhline(10000, color="#bbbbbb", linestyle="--", linewidth=1)
    axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(dollars))
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


def backtest_cell(value, money=False):
    if value is None or value == "-" or (isinstance(value, float) and np.isnan(value)):
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if money:
        return "$" + "{:,.0f}".format(number)
    return "%.2f" % number if abs(number) < 10 else "%.1f" % number


def backtest_block(backtest, image_src, window, nickname, note=None):
    """The Studio 5 Part 4 backtest of one fund: a note, the chart (if any) and the table."""
    out = []
    if not isinstance(backtest, dict) or len(backtest) == 0:
        out.append("<p class='note'>No backtest was sent with this fund.</p>")
        return "".join(out)
    window = window or ["", ""]
    if note:
        out.append("<p class='note'>%s Data: %s to %s.</p>" % (html.escape(str(note)), html.escape(str(window[0])),
                                                                html.escape(str(window[-1]))))
    else:
        out.append("<p class='note'>From the Studio 5 notebook (Part 4). The model was fit on the data before the last "
                   "12 months, then each portfolio was held through those 12 months, which the model never saw. "
                   "Data window: %s to %s.</p>" % (html.escape(str(window[0])), html.escape(str(window[-1]))))
    if image_src is not None:
        out.append("<img class='chart' src='%s' alt='Backtest chart'>" % html.escape(image_src))
    columns = []
    for row_name in backtest:
        if isinstance(backtest[row_name], dict):
            for column in backtest[row_name]:
                if column not in columns:
                    columns.append(column)
    out.append("<div class='tablebox'><table><tr><th class='l'>Portfolio</th>")
    for column in columns:
        out.append("<th>%s</th>" % html.escape(column))
    out.append("</tr>")
    for row_name in backtest:
        if not isinstance(backtest[row_name], dict):
            continue
        label = row_name
        if row_name == "with your rules":
            label = "%s (with rules)" % nickname
        out.append("<tr><td class='l fund'>%s</td>" % html.escape(label))
        for column in columns:
            out.append("<td>%s</td>" % backtest_cell(backtest[row_name].get(column), money=column.startswith("ending value")))
        out.append("</tr>")
    out.append("</table></div>")
    has_promised = False
    for column in columns:
        if column.startswith("promised"):
            has_promised = True
    if has_promised:
        out.append("<p class='note'>\"Promised average month\" is what the model expected from the data it was fit on; "
                   "\"average month\" is what actually happened in the year it never saw.</p>")
    return "".join(out)


def featured_section(featured):
    """The featured fund in three tabs: Today, Holdings, Backtest (plain buttons, a few lines of script)."""
    name = html.escape(featured["nickname"])
    stamp = html.escape(featured["as_of"].replace(" ", ""))
    out = []
    out.append("<h2>%s · live</h2>" % name)
    out.append("<div class='tabs'><button class='tab on' data-tab='today'>Today</button>"
               "<button class='tab' data-tab='holdings'>What it holds</button>"
               "<button class='tab' data-tab='backtest'>Backtest</button></div>")

    # Today
    out.append("<div class='pane' id='pane-today'>")
    if featured["status"] != "live":
        out.append("<p class='note'>%s</p>" % html.escape(featured["status"]))
    today = featured["today_pct"]
    out.append("<div class='cards'>")
    out.append("<div class='card'><div class='big'>%s</div><div class='lab'>%s with its rules, today</div></div>" % (pct(today["with_rules"]), name))
    out.append("<div class='card'><div class='big'>%s</div><div class='lab'>its no-rules twin, today</div></div>" % pct(today["no_rules"]))
    out.append("<div class='card'><div class='big'>%s</div><div class='lab'>S&amp;P 500 (SPY), today</div></div>" % pct(today["spy"]))
    if "with_rules" in featured["value_now"]:
        out.append("<div class='card'><div class='big'>$%s</div><div class='lab'>its $10,000, right now</div></div>" %
                   "{:,.0f}".format(featured["value_now"]["with_rules"]))
    out.append("</div>")
    out.append("<img class='chart' src='live.png?t=%s' alt='The featured fund today and since it started'>" % stamp)
    out.append("<p class='note'>%s, prices as of %s, every 5 minutes while the market is open (Yahoo Finance; "
               "they can run up to 15 minutes behind). \"Today\" is the change since the last close. "
               "This is for watching: the leaderboard below is scored on daily closes.</p>" % (
                   html.escape(featured["session_label"]), html.escape(featured["as_of"])))
    out.append("</div>")

    # What it holds
    out.append("<div class='pane' id='pane-holdings' hidden>")
    out.append("<div class='tablebox'><table><tr><th class='l'>Stock</th><th class='l'>Sector</th>"
               "<th>Share with rules</th><th>Share, no-rules twin</th><th>Today</th><th>Added to the fund today</th></tr>")
    for r in featured["holdings"]:
        out.append("<tr><td class='l fund'>%s</td><td class='l theme'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            html.escape(r["ticker"]), html.escape(str(r["sector"])),
            share(r["with_rules_pct"]), share(r["no_rules_pct"]), pct(r["today_pct"]), points(r["contribution_pts"])))
    out.append("</table></div>")
    out.append("<p class='note'>\"Added to the fund today\" is the stock's share times its move, in percentage points; "
               "they add up to the fund's day. Shares drift as prices move (buy and hold).</p>")
    out.append("</div>")

    # Backtest
    out.append("<div class='pane' id='pane-backtest' hidden>")
    out.append(backtest_block(featured.get("backtest"), "backtest.png?t=%s" % stamp if featured.get("backtest_png") is not None else None,
                              featured.get("data_window"), featured["nickname"], featured.get("backtest_note")))
    out.append("</div>")

    out.append("""<script>
document.querySelectorAll('.tab').forEach(function (button) {
  button.addEventListener('click', function () {
    document.querySelectorAll('.tab').forEach(function (b) { b.classList.remove('on'); });
    document.querySelectorAll('.pane').forEach(function (p) { p.hidden = true; });
    button.classList.add('on');
    document.getElementById('pane-' + button.dataset.tab).hidden = false;
  });
});
</script>""")
    return "".join(out)


def fund_name(nickname, netid, links):
    """The nickname, linked to the fund's own page when it has one."""
    text = html.escape(str(nickname))
    if links is not None and netid in links:
        return "<a href='%s'>%s</a>" % (html.escape(links[netid]), text)
    return text


def render(result, updated_et, chart_name="chart.png", featured=None, links=None, backtests=None,
           backtests_chart=False, race_chart=True):
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

    if featured is not None:
        out.append(featured_section(featured))

    if n_live > 0:
        out.append("<h2>The leaderboard (ranked by your fund: the portfolio with your rules)</h2>")
        out.append("<div class='tablebox'><table><tr><th>Rank</th><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th>Value</th><th>Since start</th><th>Its no-rules twin</th><th>Rules vs no rules</th>"
                   "<th>vs S&amp;P 500</th><th>Worst drop</th><th>Stocks</th><th>Changes</th><th>Started</th></tr>")
        for i in range(len(board)):
            r = board.loc[i]
            out.append("<tr><td>%d</td><td class='l fund'>%s</td><td class='l theme'>%s</td><td>$%s</td><td>%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (
                           r["rank"], fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                           "{:,.0f}".format(r["with_rules_value"]), pct(r["with_rules_growth_pct"]),
                           pct(r["no_rules_growth_pct"]), points(r["rules_minus_no_rules_pct"]),
                           points(r["rules_minus_spy_pct"]), plain_pct(r["with_rules_worst_drop_pct"]),
                           r["stocks_with_rules"], r["changes"], html.escape(str(r["started"]))))
        out.append("</table></div>")
        out.append("<p class='note'>\"Rules vs no rules\" and \"vs S&amp;P 500\" are percentage points over the same days. "
                   "\"Worst drop\" is the biggest fall from a high point so far.</p>")
        if race_chart:
            out.append("<h2>The race</h2><img class='chart' src='%s?t=%s' alt='Value of every fund over time'>" % (
                chart_name, html.escape(updated_et.replace(" ", ""))))
        else:
            out.append("<h2>The race</h2><p class='note'>The race chart starts after the second market close: "
                       "a line needs at least two days.</p>")

    if n_wait > 0:
        out.append("<h2>Starting at the next market close</h2>")
        out.append("<div class='tablebox'><table><tr><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th>Stocks (with rules)</th><th>Stocks (no rules)</th><th>Counts from the close on</th></tr>")
        for i in range(len(pending)):
            r = pending.loc[i]
            out.append("<tr><td class='l fund'>%s</td><td class='l theme'>%s</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (
                fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])), r["stocks_with_rules"],
                r["stocks_no_rules"], html.escape(str(r["starts"]))))
        out.append("</table></div>")

    if backtests is not None and len(backtests) > 0:
        out.append("<h2>Best backtests</h2>")
        out.append("<p class='note'>Each fund's latest backtest. Studio 5: the model was fit on 2021 to 2025, then "
                   "held through 2026. Studio 6: the fund's rebalancing strategy run through 2026 so far, after trading costs. "
                   "Fair tests, but the past, not the race above.</p>")
        if backtests_chart:
            out.append("<img class='chart' src='backtests.png?t=%s' alt='Every fund backtest'>" % html.escape(updated_et.replace(" ", "")))
        out.append("<div class='tablebox'><table><tr><th>Rank</th><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th>$10,000 became (with rules)</th><th>Its no-rules twin</th><th>S&amp;P 500, same year</th>"
                   "<th>Beat the S&amp;P 500 by</th><th>Worst drop</th><th>Backtest</th><th>Ended</th></tr>")
        for k in range(len(backtests)):
            r = backtests[k]
            beat = r["with_rules"] - r["spy"]
            out.append("<tr><td>%d</td><td class='l fund'>%s</td><td class='l theme'>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                           k + 1, fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                           backtest_cell(r["with_rules"], money=True), backtest_cell(r["no_rules"], money=True),
                           backtest_cell(r["spy"], money=True), money_diff(beat), plain_pct(r["worst_drop"]),
                           html.escape(str(r["kind"])), html.escape(str(r["window"][-1]))))
        out.append("</table></div>")

    if n_live == 0 and n_wait == 0:
        out.append("<p class='note'>No funds yet. Entries from the Studio 5 notebook show up here within 5 minutes.</p>")

    out.append("<h2>How it works</h2><ul class='how'>"
               "<li>Each entry has two portfolios from the Studio 5 model: <b>with your rules</b> (your fund, ranked here) and its <b>no-rules twin</b>.</li>"
               "<li>Click a fund's name to see its own page: its value since it started, its Studio 5 backtest and its history.</li>"
               "<li>Both start with $10,000 at the first market close after you submit, and are held until you change them.</li>"
               "<li>You can change your portfolio as often as you like by re-running the cell. A change counts from the next close, "
               "and starts from what your fund was worth that day. Every change is kept.</li>"
               "<li>Prices are daily closing prices, adjusted for splits and dividends. The page updates every 5 minutes; "
               "the leaderboard numbers move once a day, after the close.</li></ul>")
    out.append("</div></body></html>")
    return "".join(out)
