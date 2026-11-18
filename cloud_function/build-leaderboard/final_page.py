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

RACE_ENDS = "Wednesday, Dec 2"


def chips(mix, since):
    """A fund's stocks as small colored boxes: share, and the stock's return since the race began (if known)."""
    out = []
    for ticker in sorted(mix, key=lambda t: -mix[t]):
        move = since.get(ticker)
        text = "" if move is None else " <small>%+.1f%%</small>" % move
        out.append("<span class='chip' style='background:%s'><b>%s</b> %.0f%%%s</span>" % (
            holdings_page.shade(move), html.escape(ticker), 100 * mix[ticker], text))
    return "".join(out)


def render(final, entries, prices, links, updated, class_fund=None):
    """final: the board result for the final funds only (ranked among themselves).
    class_fund: {"name", "members", "path"} = the class's average Studio 5 mix held from the close the first final fund
    started (None if there is no class fund yet). It gets a card, an unranked row and a line on the chart."""
    class_path = pd.Series(dtype=float)
    if class_fund is not None:
        class_path = class_fund["path"]
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
    if len(board) > 0 and len(class_path) > 1:
        class_growth = 100 * (class_path.iloc[-1] / class_path.iloc[0] - 1)
        out.append("<div class='card'><div class='big'>%s</div><div class='lab'>the class fund since the first final fund started</div></div>" % page.pct(class_growth))
    out.append("<div class='card'><div class='big'>Dec 2</div><div class='lab'>the race ends at this market close</div></div>")
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
        # the class fund: the average of the class's Studio 5 funds, over the same days as the S&P 500 row
        class_row = None
        if len(class_path) > 0:
            class_value = float(class_path.iloc[-1])
            class_growth = 100 * (class_path.iloc[-1] / class_path.iloc[0] - 1)
            class_drop = 100 * float((1 - class_path / class_path.cummax()).max())
            minus = "–"
            if len(spy) > 0:
                minus = page.points(class_growth - 100 * (spy.iloc[-1] / spy.iloc[0] - 1))
            class_row = (class_value, "<tr style='background:#f3e9f7'><td>–</td><td class='l fund'>%s</td>"
                         "<td class='l theme'>the average of the class's %d Studio 5 funds, since the first final fund started</td>"
                         "<td>$%s</td><td>%s</td><td>%s</td><td>%s</td><td>–</td><td>%s</td>"
                         "<td class='l'><a href='holdings.html'>who holds what</a></td></tr>" % (
                             html.escape(str(class_fund["name"])), int(class_fund["members"]),
                             "{:,.0f}".format(class_value), page.pct(class_growth), minus, page.plain_pct(class_drop),
                             html.escape(class_path.index[0].strftime("%Y-%m-%d"))))

        # the two rows that are not ranked sit where their value puts them, best first
        unranked = []
        if spy_row is not None:
            unranked.append(spy_row)
        if class_row is not None:
            unranked.append(class_row)
        unranked = sorted(unranked, key=lambda pair: -pair[0])
        for i in range(len(board)):
            r = board.loc[i]
            while len(unranked) > 0 and unranked[0][0] > r["with_rules_value"]:
                out.append(unranked[0][1])
                unranked = unranked[1:]
            mix = latest[r["netid"]]["portfolios"]["with_rules"] if r["netid"] in latest else {}
            out.append("<tr><td>%d</td><td class='l fund'>%s</td><td class='l theme'>%s</td><td>$%s</td><td>%s</td><td>%s</td>"
                       "<td>%s</td><td>%d</td><td>%s</td><td class='holds'>%s</td></tr>" % (
                           int(r["rank"]), page.fund_name(r["nickname"], r["netid"], links), html.escape(str(r["theme"])),
                           "{:,.0f}".format(r["with_rules_value"]), page.pct(r["with_rules_growth_pct"]),
                           page.points(r["rules_minus_spy_pct"]), page.plain_pct(r["with_rules_worst_drop_pct"]),
                           int(r["changes"]), html.escape(str(r["started"])), chips(mix, since)))
        for pair in unranked:
            out.append(pair[1])
        out.append("</table></div>")
        out.append("<p class='note'><b>Return since it started</b>: what the fund's $10,000 has done since its first close. "
                   "<b>Fund minus S&amp;P 500</b>: that return minus the S&amp;P 500's over the same days, in percentage points. "
                   "<b>Worst drop</b>: the biggest fall from a high point so far. Each stock shows its share of the fund%s. "
                   "The gray S&amp;P 500 row is not ranked.%s</p>" % (
                       " and its return since the race began, blue up and red down" if len(since) > 0 else "",
                       " The purple row is the <b>class fund</b>: the average of the class's Studio 5 funds, with $10,000 "
                       "placed at the same close as the first final fund. It is not ranked either. Did your final fund "
                       "beat the class?" if class_row is not None else ""))

        extras = []
        if len(class_path) > 0:
            extras.append((str(class_fund["name"]), class_path, "#6a1b9a"))
        race = interactive.race_data(final["values"], board, final["benchmark_path"], extras)
        if race is not None:
            out.append("<h2>The race, day by day</h2><p class='note'>Click a fund to turn its line on or off. The black line is "
                       "the S&amp;P 500%s.</p>" % (" and the purple line is the class fund" if len(class_path) > 0 else ""))
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
