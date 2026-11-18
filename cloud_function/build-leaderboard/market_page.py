# market_page.py: "The market" tab (market.html), Studio 6, Nov 18.
#
# One picture, the same quilt the Studio 6 notebook draws: the 100 biggest companies in the S&P 500 (menu100.csv, the
# list as of Dec 31, 2025), one row per sector, the biggest company on the left, each square colored by the stock's
# return since the class start (fund_pages.HOLDINGS_SINCE): blue rose, red fell. A small number on a square says how
# many FINAL-PROJECT funds hold that stock. Below it: the stocks the final funds hold most, and the ten best and ten
# worst of the 100. Fund nicknames only.

import html
import os

import pandas as pd

import fund_pages
import holdings_page
import page

MENU_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu100.csv")

EXTRA_CSS = """
.qrow { display:flex; flex-wrap:wrap; align-items:center; margin:5px 0; }
.qname { width:190px; font-weight:600; text-align:right; padding-right:12px; box-sizing:border-box; }
.qsq { flex:1; min-width:250px; }
@media (max-width:560px) { .qname { width:100%; text-align:left; padding:6px 0 2px; } }
.sq { display:inline-block; position:relative; width:54px; margin:2px 3px 2px 0; padding:5px 0 4px; border-radius:6px;
      text-align:center; font-size:12px; line-height:1.25; border:1px solid rgba(0,0,0,0.10); }
.sq b { display:block; }
.sq .held { position:absolute; top:-7px; right:-6px; background:#13233a; color:white; border-radius:9px;
            font-size:10.5px; font-weight:700; padding:0 5px; line-height:17px; }
.two { display:flex; gap:28px; flex-wrap:wrap; }
.two > div { flex:1; min-width:300px; }
"""


def menu():
    """The 100 biggest companies: a DataFrame indexed by ticker (company, sector), biggest first."""
    return pd.read_csv(MENU_FILE).set_index("ticker")


def tickers():
    """Every ticker on the menu, so the builder downloads their prices."""
    return set(menu().index)


def render(final, entries, prices, links, updated):
    """final: the board result for the final-project funds (board + pending)."""
    companies = menu()
    start = pd.Timestamp(fund_pages.HOLDINGS_SINCE)
    label = start.strftime("%b %d").replace(" 0", " ")
    prices = prices.sort_index().ffill()

    # each stock's return since the class start
    since = {}
    for ticker in companies.index:
        since[ticker] = None
        if ticker in prices.columns:
            window = prices.loc[start:, ticker].dropna()
            if len(window) >= 2:
                since[ticker] = 100 * (float(window.iloc[-1]) / float(window.iloc[0]) - 1)

    # which final funds hold each stock (the funds in the race, and the ones starting at the next close)
    final_ids = []
    for frame in [final["board"], final["pending"]]:
        for i in range(len(frame)):
            final_ids.append((str(frame.loc[i, "netid"]), str(frame.loc[i, "nickname"])))
    latest = {}
    for entry in entries:
        netid = entry.get("netid")
        if netid not in latest or entry["received_utc"] > latest[netid]["received_utc"]:
            latest[netid] = entry
    holders = {}
    for netid, nickname in final_ids:
        if netid not in latest:
            continue
        mix = latest[netid]["portfolios"]["with_rules"]
        for ticker in mix:
            holders.setdefault(ticker, []).append("%s %.0f%%" % (nickname, 100 * mix[ticker]))

    out = []
    out.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    out.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    out.append("<title>The market · OPIM 5641</title><style>%s%s%s</style></head><body>" % (
        page.CSS, holdings_page.EXTRA_CSS, EXTRA_CSS))
    out.append("<header><div class='wrap'><h1>The market: the 100 biggest companies</h1>")
    out.append("<div class='sub'>the quilt from Studio 6 · updated %s</div></div></header><div class='wrap'>" % html.escape(updated))
    out.append(page.tabs("market"))

    out.append("<p class='note key' style='font-size:15px'>One row for each sector, the biggest company on the left. Each square is a "
               "company and its return since the %s close: "
               "<span style='background:%s'>rose a lot</span><span style='background:%s'>rose a little</span>"
               "<span style='background:%s'>fell a little</span><span style='background:%s'>fell a lot</span> "
               "A dark number on a square is <b>how many final-project funds hold that stock</b> (%d final funds so far).</p>" % (
                   html.escape(label), holdings_page.shade(15), holdings_page.shade(1), holdings_page.shade(-1),
                   holdings_page.shade(-15), len(final_ids)))

    # the quilt: one row per sector, companies in order of size
    out.append("<div class='tablebox' style='padding:10px 12px'>")
    for sector in sorted(companies["sector"].unique()):
        row = companies[companies["sector"] == sector]
        squares = []
        for ticker in row.index:
            move = since[ticker]
            number = "–" if move is None else "%+.0f%%" % move
            badge = ""
            if ticker in holders:
                badge = "<span class='held'>%d</span>" % len(holders[ticker])
            squares.append("<span class='sq' style='background:%s' title='%s'><b>%s</b>%s%s</span>" % (
                holdings_page.shade(move), html.escape(str(row.loc[ticker, "company"])), html.escape(ticker), number, badge))
        out.append("<div class='qrow'><div class='qname'>%s</div><div class='qsq'>%s</div></div>" % (
            html.escape(sector), "".join(squares)))
    out.append("</div>")
    out.append("<p class='note'>The 100 biggest companies in the S&amp;P 500 by market value at the end of 2025. Hold the mouse over "
               "a square for the company's name.</p>")

    # what the final funds hold most
    if len(holders) > 0:
        out.append("<h2>What the final funds hold most</h2>")
        out.append("<div class='tablebox'><table><tr><th class='l'>Stock</th><th class='l'>Company</th><th>Final funds holding it</th>"
                   "<th>Its return since %s</th><th class='l'>Held by (share of that fund)</th></tr>" % html.escape(label))
        for ticker in sorted(holders, key=lambda t: (-len(holders[t]), t))[:12]:
            move = since.get(ticker)
            if ticker not in since and ticker in prices.columns:
                window = prices.loc[start:, ticker].dropna()
                if len(window) >= 2:
                    move = 100 * (float(window.iloc[-1]) / float(window.iloc[0]) - 1)
            company = str(companies.loc[ticker, "company"]) if ticker in companies.index else ticker
            out.append("<tr><td class='l'><b>%s</b></td><td class='l'>%s</td><td>%d</td><td style='background:%s'>%s</td>"
                       "<td class='holds'>%s</td></tr>" % (
                           html.escape(ticker), html.escape(company), len(holders[ticker]), holdings_page.shade(move),
                           "–" if move is None else "%+.1f%%" % move, html.escape("; ".join(holders[ticker]))))
        out.append("</table></div>")

    # the ten best and the ten worst of the 100
    known = [t for t in companies.index if since[t] is not None]
    ranked = sorted(known, key=lambda t: -since[t])
    if len(ranked) >= 20:
        out.append("<h2>The ten best and the ten worst since %s</h2><div class='two'>" % html.escape(label))
        for title, group in [("The ten best", ranked[:10]), ("The ten worst", ranked[::-1][:10])]:
            out.append("<div><div class='tablebox'><table><tr><th class='l'>%s</th><th class='l'>Sector</th><th>Return</th>"
                       "<th>Final funds</th></tr>" % title)
            for ticker in group:
                out.append("<tr><td class='l'><b>%s</b> %s</td><td class='l'>%s</td><td style='background:%s'>%+.1f%%</td><td>%s</td></tr>" % (
                    html.escape(ticker), html.escape(str(companies.loc[ticker, "company"])),
                    html.escape(str(companies.loc[ticker, "sector"])), holdings_page.shade(since[ticker]), since[ticker],
                    len(holders[ticker]) if ticker in holders else "–"))
            out.append("</table></div></div>")
        out.append("</div>")

    out.append("<p class='note'>Fund names only. Page last built %s.</p>" % html.escape(updated))
    out.append("</div></body></html>")
    return "".join(out)
