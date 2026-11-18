# holdings_page.py: "Who holds what" (holdings.html), one public page for the whole class (Studio 6, Nov 17).
#
# Every fund on the board, in rank order, with the stocks it holds today's mix of. Each stock is colored by its return
# since the class start (fund_pages.HOLDINGS_SINCE): green went up, red went down, stronger color = bigger move. Below
# that, every stock and which funds hold it. Fund nicknames only: no NetIDs, no emails, no real names.

import html

import pandas as pd

import fund_pages
import page

EXTRA_CSS = """
.chip { display:inline-block; margin:2px 4px 2px 0; padding:3px 7px; border-radius:6px; font-size:12.5px;
        border:1px solid rgba(0,0,0,0.08); white-space:nowrap; }
.chip small { color:#333; }
td.holds { text-align:left; white-space:normal; min-width:420px; }
.key span { display:inline-block; padding:2px 8px; border-radius:6px; margin-right:6px; font-size:12.5px; }
"""


def shade(since_pct):
    """A background color for a return: green up, red down, full strength at a 15% move, gray when unknown."""
    if since_pct is None:
        return "rgba(0,0,0,0.05)"
    strength = min(abs(since_pct) / 15.0, 1.0)
    if since_pct >= 0:
        return "rgba(26,127,55,%.2f)" % (0.10 + 0.50 * strength)
    return "rgba(180,35,24,%.2f)" % (0.10 + 0.50 * strength)


def render(result, entries, prices, links, updated):
    board = result["board"]
    start = pd.Timestamp(fund_pages.HOLDINGS_SINCE)
    label = start.strftime("%b %d").replace(" 0", " ")

    # each fund's newest entry
    latest = {}
    for entry in entries:
        netid = entry.get("netid")
        if netid not in latest or entry["received_utc"] > latest[netid]["received_utc"]:
            latest[netid] = entry

    # each stock's return since the class start
    since = {}

    def since_start(ticker):
        if ticker not in since:
            since[ticker] = None
            if ticker in prices.columns:
                window = prices.loc[start:, ticker].dropna()
                if len(window) >= 2:
                    since[ticker] = 100 * (float(window.iloc[-1]) / float(window.iloc[0]) - 1)
        return since[ticker]

    out = []
    out.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    out.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    out.append("<title>Who holds what · OPIM 5641</title><style>%s%s</style></head><body>" % (page.CSS, EXTRA_CSS))
    out.append("<header><div class='wrap'><div class='sub'><a href='index.html' style='color:#c9d6ea'>&larr; the class leaderboard</a></div>")
    out.append("<h1>Who holds what</h1><div class='sub'>every fund on the board and its stocks · updated %s</div></div></header>" % html.escape(updated))
    out.append("<div class='wrap'>")
    out.append(page.tabs("holdings"))
    out.append("<p class='note key'>Each stock shows its share of the fund and its return since the %s close: "
               "<span style='background:%s'>up a lot</span><span style='background:%s'>up a little</span>"
               "<span style='background:%s'>down a little</span><span style='background:%s'>down a lot</span></p>" % (
                   html.escape(label), shade(15), shade(1), shade(-1), shade(-15)))

    out.append("<h2>Every fund, in leaderboard order</h2>")
    out.append("<div class='tablebox'><table><tr><th>Rank</th><th class='l'>Fund</th><th>Value</th><th>Since it started</th>"
               "<th class='l'>What it holds</th></tr>")
    holders = {}
    for i in range(len(board)):
        row = board.loc[i]
        netid = row["netid"]
        if netid not in latest:
            continue
        mix = latest[netid]["portfolios"]["with_rules"]
        name = html.escape(str(row["nickname"]))
        if links and netid in links:
            name = "<a href='%s'>%s</a>" % (html.escape(links[netid]), name)
        chips = []
        for ticker in sorted(mix, key=lambda t: -mix[t]):
            move = since_start(ticker)
            text = "" if move is None else " <small>%+.1f%%</small>" % move
            chips.append("<span class='chip' style='background:%s'><b>%s</b> %.0f%%%s</span>" % (
                shade(move), html.escape(ticker), 100 * mix[ticker], text))
            holders.setdefault(ticker, []).append("%s %.0f%%" % (str(row["nickname"]), 100 * mix[ticker]))
        out.append("<tr><td>%d</td><td class='l'><b>%s</b><br><span class='theme'>%s</span></td><td>$%s</td><td>%s</td>"
                   "<td class='holds'>%s</td></tr>" % (
                       int(row["rank"]), name, html.escape(str(row.get("theme", ""))),
                       "{:,.0f}".format(row["with_rules_value"]), page.pct(row["with_rules_growth_pct"]), "".join(chips)))
    out.append("</table></div>")

    out.append("<h2>Every stock, and who holds it</h2>")
    out.append("<div class='tablebox'><table><tr><th class='l'>Stock</th><th>Funds</th><th>Its return since %s</th>"
               "<th class='l'>Held by (share of that fund)</th></tr>" % html.escape(label))
    for ticker in sorted(holders, key=lambda t: (-len(holders[t]), t)):
        move = since_start(ticker)
        cell = "-" if move is None else "%+.1f%%" % move
        out.append("<tr><td class='l'><b>%s</b></td><td>%d</td><td style='background:%s'>%s</td><td class='holds'>%s</td></tr>" % (
            html.escape(ticker), len(holders[ticker]), shade(move), cell, html.escape("; ".join(holders[ticker]))))
    out.append("</table></div>")
    out.append("<p class='note'>Fund names only. A fund's mix is the newest one its manager sent.</p>")
    out.append("</div></body></html>")
    return "".join(out)
