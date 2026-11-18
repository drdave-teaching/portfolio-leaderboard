# page.py: the public leaderboard page (nicknames only: no NetIDs, no emails; holdings are on each fund's own page).

import html
import io

import interactive

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


TABS_CSS = """
.tabs { display:flex; gap:6px; flex-wrap:wrap; margin:14px 0 6px; border-bottom:2px solid #d9dee6; }
.tabs a { padding:8px 16px; border-radius:8px 8px 0 0; text-decoration:none; color:#33435c; font-weight:600;
          background:#eef1f5; border:1px solid #d9dee6; border-bottom:none; }
.tabs a.on { background:#13233a; color:white; border-color:#13233a; }
"""


def tabs(active, up=""):
    """The tab bar on every page. active: 'final', 'studio5' or 'holdings'. up: '../' from inside a folder."""
    names = [("final", "index.html", "Final project"), ("studio5", "studio5.html", "Studio 5 funds (practice)"),
             ("holdings", "holdings.html", "Who holds what (Studio 5)")]
    out = ["<style>%s</style><div class='tabs'>" % TABS_CSS]
    for key, href, label in names:
        out.append("<a href='%s%s'%s>%s</a>" % (up, href, " class='on'" if key == active else "", label))
    out.append("</div>")
    return "".join(out)


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


def make_chart(values, board, benchmark_path, extras=None):
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
    for name, path, color in (extras or []):
        axis.plot(path.index, path.values, color=color, linewidth=3, linestyle="--", label=name)
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


STOCK_LISTS = {
    "starter": "⭐ starter list",
    "connecticut": "🏛️ Connecticut",
    "ai_chips": "🤖 AI chips",
    "oil_and_gas": "🛢️ oil and gas",
    "banks_and_payments": "🏦 banks and payments",
    "dividends": "💵 dividends",
    "healthcare": "🩺 healthcare",
    "food_and_restaurants": "🍔 food and restaurants",
    "travel": "✈️ travel",
    "defense_and_aerospace": "🛡️ defense and aerospace",
    "utilities_and_power": "⚡ utilities and power",
    "shopping": "🛍️ shopping",
    "sports_and_entertainment": "🏟️ sports and entertainment",
    "dartboard": "🐒 dartboard",
    "momentum_50_200": "📈 momentum 50/200",
    "concentrated": "🎯 concentrated",
}


def stock_list_label(code):
    """The Studio 5 stock list a fund was built from, with the infographic's emoji; 'custom' when none was picked."""
    if code is None or (isinstance(code, float) and np.isnan(code)) or str(code).strip() == "":
        return "custom"
    return html.escape(STOCK_LISTS.get(str(code), str(code)))


OUTLOOKS = {"bull": "🐂 bull", "bear": "🐻 bear", "sideways": "➖ sideways"}


def outlook_label(code):
    """A fund's latest Studio 6 call; a dash before Studio 6."""
    if code is None or (isinstance(code, float) and np.isnan(code)):
        return "–"
    return html.escape(OUTLOOKS.get(str(code).strip().lower(), "–"))


def fund_name(nickname, netid, links):
    """The nickname, linked to the fund's own page when it has one."""
    text = html.escape(str(nickname))
    if links is not None and netid in links:
        return "<a href='%s'>%s</a>" % (html.escape(links[netid]), text)
    return text


def render(result, updated_et, chart_name="chart.png", featured=None, links=None, backtests=None,
           backtests_chart=False, race_chart=True, race_data=None, backtests_data=None, crowds=None, year_data=None):
    board = result["board"]
    crowds = crowds or {}
    pending = result["pending"]
    out = []
    out.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    out.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    out.append("<title>OPIM 5641 Portfolio Leaderboard</title><style>%s%s</style>" % (CSS, interactive.CSS))
    out.append("<script>%s</script></head><body>" % interactive.JS)
    out.append("<header><div class='wrap'><h1>OPIM 5641 · Studio 5 Funds (practice)</h1>")
    sub = "Fall 2026 · every fund starts with $10,000 · updated %s" % html.escape(updated_et)
    if result["last_close"]:
        sub += " · prices through the close of %s" % html.escape(result["last_close"])
    out.append("<div class='sub'>%s</div></div></header><div class='wrap'>" % sub)
    out.append(tabs("studio5"))

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
        if "outlook" in board.columns:
            mood = {"bull": 0, "bear": 0, "sideways": 0}
            for code in board["outlook"]:
                key = str(code).strip().lower()
                if key in mood:
                    mood[key] += 1
            if mood["bull"] + mood["bear"] + mood["sideways"] > 0:
                out.append("<div class='card'><div class='big'>🐂 %d · 🐻 %d · ➖ %d</div><div class='lab'>the class calls the "
                           "market (Studio 6)</div></div>" % (mood["bull"], mood["bear"], mood["sideways"]))
    for key in ["crowd", "concentrated"]:
        one = crowds.get(key)
        if one is not None and one.get("stats") is not None:
            versus = ""
            if one["stats"].get("spy_growth_pct") is not None:
                versus = " · S&amp;P 500, same days: %+.2f%%" % one["stats"]["spy_growth_pct"]
            out.append("<div class='card'><div class='big'>%s</div><div class='lab'>%s since %s (%d funds)%s</div></div>" % (
                pct(one["stats"]["growth_pct"]), html.escape(one["name"]), html.escape(str(one["start"])), one["members"], versus))
    out.append("</div>")

    if featured is not None:
        out.append(featured_section(featured))

    if n_live > 0:
        out.append("<h2>The leaderboard (ranked by your fund: the portfolio with your rules)</h2>")
        out.append("<p class='note' style='font-size:15px'><a href='holdings.html'><b>Who holds what &rarr;</b></a> "
                   "every fund's stocks on one page, green or red since Nov 5. Click a fund's name for its own page.</p>")
        top = board.loc[0]
        top_spy = top["with_rules_growth_pct"] - top["rules_minus_spy_pct"]
        out.append("<div class='note' style='margin:6px 0 12px'><b>How to read the columns.</b> Every fund starts with $10,000 at its first close."
                   "<ul style='margin:6px 0 0 18px;padding:0'>"
                   "<li><b>Value today</b>: what that $10,000 is worth at the last close.</li>"
                   "<li><b>Fund's return since it started</b>: the same thing as a percent.</li>"
                   "<li><b>Its no-rules twin's return</b>: the same stocks and the same risk limit, with no business rules.</li>"
                   "<li><b>Fund minus twin</b>: the fund's return minus its twin's, in percentage points. Above zero: the fund is ahead of its twin.</li>"
                   "<li><b>Fund minus S&amp;P 500</b>: the fund's return minus the S&amp;P 500's return over the same days, in percentage points. "
                   "Above zero: the fund is ahead of the market.</li>"
                   "<li><b>Worst drop</b>: the biggest fall from a high point so far.</li></ul>"
                   "<div style='margin-top:6px'>Example, %s: the fund is %+.2f%% and its twin is %+.2f%%, so fund minus twin is "
                   "%.2f &minus; (%.2f) = <b>%+.2f</b>. The S&amp;P 500 did %+.2f%% over the same days, so fund minus S&amp;P 500 is "
                   "%.2f &minus; (%.2f) = <b>%+.2f</b>.</div></div>" % (
                       html.escape(str(top["nickname"])), top["with_rules_growth_pct"], top["no_rules_growth_pct"],
                       top["with_rules_growth_pct"], top["no_rules_growth_pct"], top["rules_minus_no_rules_pct"],
                       top_spy, top["with_rules_growth_pct"], top_spy, top["rules_minus_spy_pct"]))
        out.append("<div class='tablebox'><table><tr><th>Rank</th><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th class='l'>Stock list</th><th class='l'>Call</th><th>Value today</th><th>Fund's return since it started</th>"
                   "<th>Its no-rules twin's return</th><th>Fund minus twin (points)</th>"
                   "<th>Fund minus S&amp;P 500 (points)</th><th>Worst drop</th><th>Stocks held</th><th>Changes made</th><th>Started</th></tr>")
        # unranked rows (the S&P 500 and the crowd funds), slotted into the table by their value
        unranked = []
        spy = result["benchmark_path"]
        if len(spy) > 1:
            spy_value = 10000 * spy.iloc[-1] / spy.iloc[0]
            spy_growth = 100 * (spy.iloc[-1] / spy.iloc[0] - 1)
            spy_drop = -100 * (spy / spy.cummax() - 1).min()
            spy_start = str(spy.index[0])[:10]
            unranked.append((spy_value, "<tr style='background:#eef1f5'><td>–</td><td class='l fund'>S&amp;P 500 (SPY)</td>"
                             "<td class='l theme'>the market: $10,000 in the S&amp;P 500</td><td class='l'>–</td><td class='l'>–</td>"
                             "<td>$%s</td><td>%s</td><td>–</td><td>–</td><td>–</td><td>%s</td><td>500</td><td>–</td><td>%s</td></tr>" % (
                                 "{:,.0f}".format(spy_value), pct(spy_growth), plain_pct(spy_drop), html.escape(spy_start))))
        crowd_note = " The gray S&amp;P 500 row is not ranked: it is $10,000 in the S&amp;P 500 since the first fund started."
        for key in ["crowd", "concentrated"]:
            one = crowds.get(key)
            if one is None or one.get("stats") is None:
                continue
            stats = one["stats"]
            unranked.append((stats["value"], "<tr style='background:#f7f2fb'><td>–</td><td class='l fund'>%s</td><td class='l theme'>%s</td>"
                             "<td class='l'>–</td><td class='l'>–</td><td>$%s</td><td>%s</td><td>–</td><td>–</td><td>%s</td><td>%s</td>"
                             "<td>%d</td><td>–</td><td>%s</td></tr>" % (
                                 html.escape(one["name"]), "the same dollars in each of %d %s funds" % (one["members"], "student" if key == "crowd" else "pair"),
                                 "{:,.0f}".format(stats["value"]), pct(stats["growth_pct"]),
                                 points(stats.get("vs_spy_pct")) if stats.get("vs_spy_pct") is not None else "–",
                                 plain_pct(stats["worst_drop_pct"]),
                                 len(one["weights"]), html.escape(str(one["start"])))))
            crowd_note = (" The shaded rows are not ranked: the S&amp;P 500 row is $10,000 in the S&amp;P 500 since the first fund started, "
                          "and the class crowd fund is what you would have if you put the same number of dollars in every "
                          "student's fund (each counts once, Dr. Dave's are left out) at the close on its start day and held. "
                          "Its \"vs S&amp;P 500\" compares it with the S&amp;P 500 over those same days. "
                          "The 🎯 crowd does the same for the pairs' concentrated funds.")
        unranked = sorted(unranked, key=lambda pair: -pair[0])
        next_unranked = 0
        for i in range(len(board)):
            r = board.loc[i]
            while next_unranked < len(unranked) and unranked[next_unranked][0] > r["with_rules_value"]:
                out.append(unranked[next_unranked][1])
                next_unranked += 1
            out.append("<tr><td>%d</td><td class='l fund'>%s</td><td class='l theme'>%s</td><td class='l'>%s</td><td class='l'>%s</td><td>$%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (
                           r["rank"], fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                           stock_list_label(r.get("stock_list")), outlook_label(r.get("outlook")),
                           "{:,.0f}".format(r["with_rules_value"]), pct(r["with_rules_growth_pct"]),
                           pct(r["no_rules_growth_pct"]), points(r["rules_minus_no_rules_pct"]),
                           points(r["rules_minus_spy_pct"]), plain_pct(r["with_rules_worst_drop_pct"]),
                           r["stocks_with_rules"], r["changes"], html.escape(str(r["started"]))))
        while next_unranked < len(unranked):
            out.append(unranked[next_unranked][1])
            next_unranked += 1
        out.append("</table></div>")
        out.append("<p class='note'>\"Rules vs no rules\" and \"vs S&amp;P 500\" are percentage points over the same days. "
                   "\"Worst drop\" is the biggest fall from a high point so far.%s</p>" % crowd_note)
        stamp = html.escape(updated_et.replace(" ", ""))
        if race_data is not None:
            out.append("<h2>The race</h2><p class='note'>Click a fund to turn its line on or off, or type part of a name "
                       "in the search box (type 🎯 for the concentrated funds). Hover over the chart to read every value on that day. "
                       "The black line is the S&amp;P 500; the dashed lines are the class crowd funds.</p>")
            out.append(interactive.block("race", race_data, "%s?t=%s" % (chart_name, stamp) if race_chart else None,
                                         "Value of every fund over time"))
        elif race_chart:
            out.append("<h2>The race</h2><img class='chart' src='%s?t=%s' alt='Value of every fund over time'>" % (
                chart_name, stamp))
        else:
            out.append("<h2>The race</h2><p class='note'>The race chart starts after the second market close: "
                       "a line needs at least two days.</p>")

    if n_wait > 0:
        out.append("<h2>Starting at the next market close</h2>")
        out.append("<div class='tablebox'><table><tr><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th class='l'>Stock list</th><th>Stocks (with rules)</th><th>Stocks (no rules)</th><th>Counts from the close on</th></tr>")
        for i in range(len(pending)):
            r = pending.loc[i]
            out.append("<tr><td class='l fund'>%s</td><td class='l theme'>%s</td><td class='l'>%s</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (
                fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                stock_list_label(r.get("stock_list")), r["stocks_with_rules"],
                r["stocks_no_rules"], html.escape(str(r["starts"]))))
        out.append("</table></div>")

    if year_data is not None:
        out.append("<h2>2026 so far: before and after the funds went live</h2>")
        out.append("<p class='note'>Each line is $10,000 in a fund's <b>current</b> stocks, bought at the Dec 31, 2025 close and held. "
                   "The red dashed line is Nov 5, when the class funds went live. <b>Left of the line is a what-if</b>: the funds did "
                   "not exist yet, and their stocks were chosen knowing how those months turned out, so most of them look good. "
                   "<b>Right of the line is live</b>: nobody knew what would happen next. The black line is the S&amp;P 500. "
                   "Click a fund to turn its line on or off.</p>")
        out.append(interactive.block("year", year_data, None, "Every fund's current stocks through 2026"))

    if backtests is not None and len(backtests) > 0:
        out.append("<h2>Best backtests</h2>")
        out.append("<p class='note'>Each fund's latest backtest. Studio 5: the model was fit on 2021 to 2025, then "
                   "held through 2026. Studio 6 🎯 funds: today's mix held through 2026 so far, a what-if (the mix was picked with 2026 in view). "
                   "Fair tests, but the past, not the race above.</p>")
        if backtests_data is not None:
            out.append(interactive.block("backtests", backtests_data,
                                         "backtests.png?t=%s" % html.escape(updated_et.replace(" ", "")) if backtests_chart else None,
                                         "Every fund backtest"))
        elif backtests_chart:
            out.append("<img class='chart' src='backtests.png?t=%s' alt='Every fund backtest'>" % html.escape(updated_et.replace(" ", "")))
        out.append("<div class='tablebox'><table><tr><th>Rank</th><th class='l'>Fund</th><th class='l'>Theme</th>"
                   "<th class='l'>Stock list</th><th>$10,000 became (with rules)</th><th>Its no-rules twin</th><th>S&amp;P 500, same year</th>"
                   "<th>Beat the S&amp;P 500 by</th><th>Worst drop</th><th>Backtest</th><th>Ended</th></tr>")
        for k in range(len(backtests)):
            r = backtests[k]
            beat = r["with_rules"] - r["spy"]
            out.append("<tr><td>%d</td><td class='l fund'>%s</td><td class='l theme'>%s</td><td class='l'>%s</td><td>%s</td><td>%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                           k + 1, fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                           stock_list_label(r.get("stock_list")),
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
