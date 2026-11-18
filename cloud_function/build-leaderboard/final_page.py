# final_page.py: the FINAL PROJECT leaderboard (index.html), Studio 6, Nov 18.
#
# Only funds sent from the Studio 6 "Your Final Fund" notebook are here (their entries carry decision = "final"; the
# builder gives them their own fund id, NetID + "-f", so a final fund never mixes with the student's Studio 5 fund).
# Every final fund starts with $10,000 at the first market close after it was sent and is held until its manager sends
# a new version. The Studio 5 funds live on their own tab (studio5.html). Fund nicknames only: no NetIDs, no emails.

import html

import pandas as pd

import board as scoring
import holdings_page
import interactive
import page

RACE_ENDS = "Thursday, Dec 3"


def chips(mix, since):
    """A fund's stocks as small colored boxes: share, and the stock's return since the race began (if known)."""
    out = []
    for ticker in sorted(mix, key=lambda t: -mix[t]):
        move = since.get(ticker)
        text = "" if move is None else " <small>%+.1f%%</small>" % move
        out.append("<span class='chip' style='background:%s'><b>%s</b> %.0f%%%s</span>" % (
            holdings_page.shade(move), html.escape(ticker), 100 * mix[ticker], text))
    return "".join(out)


def render(final, entries, prices, links, updated):
    """final: the board result for the final funds only (ranked among themselves)."""
    board = final["board"]
    pending = final["pending"]

    # each final fund's newest entry (for its strategy and its stocks)
    latest = {}
    for entry in entries:
        netid = entry.get("netid")
        if netid not in latest or entry["received_utc"] > latest[netid]["received_utc"]:
            latest[netid] = entry

    # every stock's return since the first final fund started (None until there are two closes)
    since = {}
    race_start = None
    if len(board) > 0:
        race_start = pd.Timestamp(board["started"].min())
        window = prices.sort_index().ffill().loc[race_start:]
        if len(window) >= 2:
            for ticker in window.columns:
                first = window[ticker].iloc[0]
                last = window[ticker].iloc[-1]
                if first == first and last == last and first != 0:
                    since[ticker] = 100 * (float(last) / float(first) - 1)

    out = []
    out.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    out.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    out.append("<title>OPIM 5641 Final Project Leaderboard</title><style>%s%s%s</style>" % (
        page.CSS, interactive.CSS, holdings_page.EXTRA_CSS))
    out.append("<script>%s</script></head><body>" % interactive.JS)
    out.append("<header><div class='wrap'><h1>OPIM 5641 · Final Project Leaderboard</h1>")
    sub = "Fall 2026 · every final fund starts with $10,000 · updated %s" % html.escape(updated)
    if final["last_close"]:
        sub += " · prices through the close of %s" % html.escape(final["last_close"])
    out.append("<div class='sub'>%s</div></div></header><div class='wrap'>" % sub)
    out.append(page.tabs("final"))

    # the cards
    out.append("<div class='cards'>")
    out.append("<div class='card'><div class='big'>%d</div><div class='lab'>final funds in the race</div></div>" % len(board))
    if len(pending) > 0:
        out.append("<div class='card'><div class='big'>%d</div><div class='lab'>final funds starting at the next close</div></div>" % len(pending))
    spy = final["benchmark_path"]
    if len(board) > 0 and len(spy) > 1:
        spy_growth = 100 * (spy.iloc[-1] / spy.iloc[0] - 1)
        out.append("<div class='card'><div class='big'>%s</div><div class='lab'>S&amp;P 500 since the first final fund started</div></div>" % page.pct(spy_growth))
        ahead = int((board["rules_minus_spy_pct"] > 0).sum())
        out.append("<div class='card'><div class='big'>%d of %d</div><div class='lab'>final funds ahead of the S&amp;P 500</div></div>" % (ahead, len(board)))
    out.append("<div class='card'><div class='big'>Dec 3</div><div class='lab'>the race ends at this market close</div></div>")
    out.append("</div>")

    out.append("<p class='note' style='font-size:15px'><b>Only final funds are here</b>: funds sent from the Studio 6 notebook, "
               "<i>Your Final Fund</i>. Each one starts with $10,000 at the first market close after it was sent, and is held "
               "until its manager sends a new version. The race ends at the market close on %s. "
               "The Studio 5 funds are on their own tab.</p>" % RACE_ENDS)

    if len(board) == 0 and len(pending) == 0:
        out.append("<h2>No final funds yet</h2><p class='note' style='font-size:15px'>Send yours from the last part of the "
                   "Studio 6 notebook. It shows up here within five minutes.</p>")

    if len(board) > 0:
        out.append("<h2>The final project race</h2>")
        out.append("<div class='tablebox'><table><tr><th>Rank</th><th class='l'>Fund</th><th class='l'>Strategy</th>"
                   "<th>Value today</th><th>Return since it started</th><th>Fund minus S&amp;P 500 (points)</th>"
                   "<th>Worst drop</th><th>Changes made</th><th>Started</th><th class='l'>What it holds</th></tr>")
        spy_row = None
        if len(spy) > 0:
            spy_value = float(spy.iloc[-1])
            spy_growth = 100 * (spy.iloc[-1] / spy.iloc[0] - 1)
            spy_drop = 100 * float((1 - spy / spy.cummax()).max())
            spy_row = (spy_value, "<tr style='background:#eef1f5'><td>–</td><td class='l fund'>S&amp;P 500 (SPY)</td>"
                       "<td class='l theme'>the market, since the first final fund started</td><td>$%s</td><td>%s</td><td>–</td>"
                       "<td>%s</td><td>–</td><td>%s</td><td class='l'>–</td></tr>" % (
                           "{:,.0f}".format(spy_value), page.pct(spy_growth), page.plain_pct(spy_drop),
                           html.escape(spy.index[0].strftime("%Y-%m-%d"))))
        placed = False
        for i in range(len(board)):
            r = board.loc[i]
            if spy_row is not None and not placed and spy_row[0] > r["with_rules_value"]:
                out.append(spy_row[1])
                placed = True
            mix = latest[r["netid"]]["portfolios"]["with_rules"] if r["netid"] in latest else {}
            out.append("<tr><td>%d</td><td class='l fund'>%s</td><td class='l theme'>%s</td><td>$%s</td><td>%s</td><td>%s</td>"
                       "<td>%s</td><td>%d</td><td>%s</td><td class='holds'>%s</td></tr>" % (
                           int(r["rank"]), page.fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                           "{:,.0f}".format(r["with_rules_value"]), page.pct(r["with_rules_growth_pct"]),
                           page.points(r["rules_minus_spy_pct"]), page.plain_pct(r["with_rules_worst_drop_pct"]),
                           int(r["changes"]), html.escape(str(r["started"])), chips(mix, since)))
        if spy_row is not None and not placed:
            out.append(spy_row[1])
        out.append("</table></div>")
        out.append("<p class='note'><b>Return since it started</b>: what the fund's $10,000 has done since its first close. "
                   "<b>Fund minus S&amp;P 500</b>: that return minus the S&amp;P 500's over the same days, in percentage points. "
                   "<b>Worst drop</b>: the biggest fall from a high point so far. Each stock shows its share of the fund%s. "
                   "The gray S&amp;P 500 row is not ranked.</p>" % (
                       " and its return since the race began, green up and red down" if len(since) > 0 else ""))

        race = interactive.race_data(final["values"], board, final["benchmark_path"], [])
        if race is not None:
            out.append("<h2>The race, day by day</h2><p class='note'>Click a fund to turn its line on or off. The black line is "
                       "the S&amp;P 500.</p>")
            out.append(interactive.block("finalrace", race, None, "Value of every final fund over time"))

    if len(pending) > 0:
        out.append("<h2>Starting at the next market close</h2>")
        out.append("<div class='tablebox'><table><tr><th class='l'>Fund</th><th class='l'>Strategy</th><th>Counts from the close on</th>"
                   "<th class='l'>What it holds</th></tr>")
        for i in range(len(pending)):
            r = pending.loc[i]
            mix = latest[r["netid"]]["portfolios"]["with_rules"] if r["netid"] in latest else {}
            out.append("<tr><td class='l fund'>%s</td><td class='l theme'>%s</td><td>%s</td><td class='holds'>%s</td></tr>" % (
                page.fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                html.escape(str(r["starts"])), chips(mix, {})))
        out.append("</table></div>")
        out.append("<p class='note'>These funds were sent after the last market close, so they start at the next one "
                   "(4 PM Eastern on a weekday). They move into the race above the next morning.</p>")

    out.append("<p class='note'>Fund names only. Page last built %s.</p>" % html.escape(updated))
    out.append("</div></body></html>")
    return "".join(out)
