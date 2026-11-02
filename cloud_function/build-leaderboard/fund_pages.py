# fund_pages.py: one public page per fund (click a nickname on the leaderboard).
# Each page: the fund's value since it started vs its no-rules twin and the S&P 500, its Studio 5 backtest, and its
# change history. No NetIDs, no emails, no holdings (only the featured fund shows holdings, on the main page).
#
# The page address is a hash of the NetID with a secret salt kept in the PRIVATE bucket (config/salt.txt), so nobody
# can work out whose page is whose. Images and pages are only re-made when something changed (cheap to run often).

import hashlib
import html
import io
import json
import secrets

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import pandas as pd

import board as scoring
import live
import page

SALT_KEY = "config/salt.txt"
STATE_KEY = "config/fund_pages_state.json"


def get_salt(bucket, read_text, write_text):
    salt = read_text(bucket, SALT_KEY)
    if salt is None or salt.strip() == "":
        salt = secrets.token_hex(16)
        write_text(bucket, SALT_KEY, salt, "text/plain")
    return salt.strip()


def slug_for(netid, salt):
    return hashlib.sha256((salt + netid).encode("utf-8")).hexdigest()[:12]


def upload(bucket, key, data, content_type):
    blob = bucket.blob(key)
    blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(data, content_type=content_type)


def value_chart(netid, nickname, values, prices):
    own = values[values["netid"] == netid]
    figure = plt.figure(figsize=(11, 4.4), dpi=110)
    axis = figure.add_subplot(111)
    start = None
    for key in ["no_rules", "with_rules"]:
        line = own[own["portfolio"] == key]
        dates = pd.to_datetime(line["date"])
        if len(dates) > 0:
            start = dates.min()
        label = "%s (with rules)" % nickname if key == "with_rules" else "its no-rules twin"
        width = 2.6 if key == "with_rules" else 1.6
        axis.plot(dates, line["value"], color=live.COLORS[key], linewidth=width, marker="o", markersize=3, label=label)
    if start is not None and scoring.BENCHMARK in prices.columns:
        spy = prices.loc[start:, scoring.BENCHMARK].ffill()
        axis.plot(spy.index, 10000 * spy / spy.iloc[0], color="black", linewidth=1.8, marker="o", markersize=3,
                  label="S&P 500 (SPY)")
    axis.axhline(10000, color="#bbbbbb", linestyle="--", linewidth=1)
    axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(live.dollars))
    axis.set_title("Value of $10,000 since it started (daily closes)")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=9, frameon=False, loc="best")
    figure.autofmt_xdate()
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    return buffer.getvalue()


def page_html(nickname, theme, row, waiting_label, history, has_value_png, backtest, has_backtest_png, window, updated):
    out = []
    out.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    out.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    out.append("<title>%s · OPIM 5641 fund</title><style>%s</style></head><body>" % (html.escape(nickname), page.CSS))
    out.append("<header><div class='wrap'><div class='sub'><a href='../index.html' style='color:#c9d6ea'>&larr; the class leaderboard</a></div>")
    out.append("<h1>%s</h1><div class='sub'>%s</div></div></header><div class='wrap'>" % (html.escape(nickname), html.escape(theme)))
    if row is not None:
        out.append("<div class='cards'>")
        out.append("<div class='card'><div class='big'>$%s</div><div class='lab'>its $10,000 at the last close</div></div>" %
                   "{:,.0f}".format(row["with_rules_value"]))
        out.append("<div class='card'><div class='big'>%s</div><div class='lab'>since it started (%s)</div></div>" %
                   (page.pct(row["with_rules_growth_pct"]), html.escape(str(row["started"]))))
        out.append("<div class='card'><div class='big'>%s</div><div class='lab'>its no-rules twin</div></div>" % page.pct(row["no_rules_growth_pct"]))
        out.append("<div class='card'><div class='big'>%s</div><div class='lab'>S&amp;P 500, same days</div></div>" % page.pct(row["spy_growth_pct"]))
        out.append("<div class='card'><div class='big'>#%d</div><div class='lab'>on the leaderboard</div></div>" % row["rank"])
        out.append("</div>")
        if has_value_png:
            out.append("<img class='chart' src='%s' alt='Value since it started'>" % html.escape(has_value_png))
    else:
        out.append("<p class='note'>This fund starts at the close on %s. Its line shows up here after that close.</p>" %
                   html.escape(waiting_label))
    out.append("<h2>Its backtest</h2>")
    out.append(page.backtest_block(backtest, has_backtest_png, window, nickname))
    out.append("<h2>Its history</h2><div class='tablebox'><table><tr><th class='l'>Received</th><th class='l'>Counts from the close on</th><th class='l'>Why</th></tr>")
    for item in history:
        out.append("<tr><td class='l'>%s</td><td class='l'>%s</td><td class='l theme'>%s</td></tr>" % (
            html.escape(item["received"]), html.escape(item["counts_from"]), html.escape(item["reason"])))
    out.append("</table></div>")
    out.append("<p class='note'>Page last changed %s.</p></div></body></html>" % html.escape(updated))
    return "".join(out)


def build(result, entries, prices, entries_bucket, public_bucket, read_text, write_text, updated, eastern):
    """Make or refresh every fund's page. Returns {netid: 'funds/<slug>.html'} for the leaderboard links."""
    salt = get_salt(entries_bucket, read_text, write_text)
    state_text = read_text(entries_bucket, STATE_KEY)
    state = json.loads(state_text) if state_text is not None else {}

    board = result["board"]
    pending = result["pending"]
    rows = {}
    for i in range(len(board)):
        rows[board.loc[i, "netid"]] = board.loc[i]
    waiting = {}
    for i in range(len(pending)):
        waiting[pending.loc[i, "netid"]] = pending.loc[i, "starts"]

    by_student = {}
    for entry in entries:
        by_student.setdefault(entry.get("netid"), []).append(entry)

    trading_days = list(prices.sort_index().index)
    links = {}
    for netid in list(rows) + list(waiting):
        mine = sorted(by_student.get(netid, []), key=lambda e: e["received_utc"])
        if len(mine) == 0:
            continue
        latest = mine[-1]
        slug = slug_for(netid, salt)
        links[netid] = "funds/%s.html" % slug
        nickname = latest.get("nickname", "fund")
        mark = latest.get("submission_id") or latest.get("received_utc")
        last_close = result["last_close"]
        before = state.get(netid, {})

        backtest_src = None
        paths = latest.get("backtest_paths")
        if isinstance(paths, dict) and len(paths) > 0:
            backtest_src = "%s_backtest.png?v=%s" % (slug, hashlib.sha256(str(mark).encode()).hexdigest()[:8])
            if before.get("backtest_for") != mark:
                upload(public_bucket, "funds/%s_backtest.png" % slug, live.make_backtest_chart(paths, nickname), "image/png")
        value_src = None
        if netid in rows:
            value_src = "%s_value.png?v=%s" % (slug, last_close)
            if before.get("value_for") != "%s|%s" % (mark, last_close):
                upload(public_bucket, "funds/%s_value.png" % slug, value_chart(netid, nickname, result["values"], prices), "image/png")

        history = []
        for entry in mine:
            day = scoring.first_close_after(entry["received_utc"], trading_days)
            received = pd.Timestamp(entry["received_utc"]).tz_convert(eastern).strftime("%a %b %d, %I:%M %p ET")
            history.append({"received": received,
                            "counts_from": day.strftime("%a %b %d") if day is not None else "the next close",
                            "reason": str(entry.get("reason", ""))})

        body = page_html(nickname, latest.get("theme", ""), rows.get(netid), waiting.get(netid, ""), history, value_src,
                         latest.get("backtest"), backtest_src, latest.get("data_window"), "")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if before.get("page") != digest:
            full = page_html(nickname, latest.get("theme", ""), rows.get(netid), waiting.get(netid, ""), history, value_src,
                             latest.get("backtest"), backtest_src, latest.get("data_window"), updated)
            upload(public_bucket, "funds/%s.html" % slug, full, "text/html")
        state[netid] = {"backtest_for": mark, "value_for": "%s|%s" % (mark, last_close), "page": digest}

    write_text(entries_bucket, STATE_KEY, json.dumps(state), "application/json")
    return links
