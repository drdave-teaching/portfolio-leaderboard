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
import interactive
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


def record_slug_for(netid, salt):
    """The private record's address: a different hash, never linked from the board, only sent in the receipt."""
    return hashlib.sha256((salt + netid + "|record").encode("utf-8")).hexdigest()[:24]


def record_json(netid, mine, result, prices, trading_days, updated):
    """Everything a student's dashboard needs: their entries (with holdings) and the daily values."""
    entries_out = []
    for entry in mine:
        day = scoring.first_close_after(entry["received_utc"], trading_days)
        entries_out.append({
            "received_utc": entry["received_utc"],
            "counts_from": day.strftime("%Y-%m-%d") if day is not None else None,
            "reason": entry.get("reason", ""),
            "theme": entry.get("theme", ""),
            "notebook": entry.get("notebook", ""),
            "strategy": entry.get("strategy"),
            "risk_limit": entry.get("risk_limit"),
            "portfolios": entry["portfolios"],
        })
    values = {"dates": [], "with_rules": [], "no_rules": []}
    spy = {"dates": [], "values": []}
    own = result["values"]
    if len(own) > 0:
        own = own[own["netid"] == netid]
        ruled = own[own["portfolio"] == "with_rules"].sort_values("date")
        free = own[own["portfolio"] == "no_rules"].sort_values("date")
        values["dates"] = list(ruled["date"])
        values["with_rules"] = list(ruled["value"])
        values["no_rules"] = list(free["value"])
        if len(ruled) > 0 and scoring.BENCHMARK in prices.columns:
            line = prices.loc[ruled["date"].iloc[0]:, scoring.BENCHMARK].ffill()
            for day in line.index:
                spy["dates"].append(day.strftime("%Y-%m-%d"))
                spy["values"].append(round(float(10000 * line.loc[day] / line.iloc[0]), 2))
    return {"nickname": mine[-1].get("nickname", ""), "theme": mine[-1].get("theme", ""), "updated": updated,
            "last_close": result["last_close"], "entries": entries_out, "values": values, "spy": spy}


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


def page_html(nickname, theme, row, waiting_label, history, has_value_png, backtest, has_backtest_png, window, updated,
              backtest_note=None):
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
    out.append(page.backtest_block(backtest, has_backtest_png, window, nickname, backtest_note))
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
        mark = "%s|%s" % (latest.get("submission_id") or latest.get("received_utc"), nickname)
        last_close = result["last_close"]
        before = state.get(netid, {})

        backtest_src = None
        paths = latest.get("backtest_paths")
        if isinstance(paths, dict) and len(paths) > 0:
            backtest_src = "%s_backtest.png?v=%s" % (slug, hashlib.sha256(str(mark).encode()).hexdigest()[:8])
            if before.get("backtest_for") != mark:
                upload(public_bucket, "funds/%s_backtest.png" % slug, live.make_backtest_chart(paths, nickname, latest.get("backtest_title")), "image/png")
        value_src = None
        if netid in rows:
            value_src = "%s_value.png?v=%s" % (slug, last_close)
            if before.get("value_for") != "%s|%s|live" % (mark, last_close):
                upload(public_bucket, "funds/%s_value.png" % slug, value_chart(netid, nickname, result["values"], prices), "image/png")

        history = []
        for entry in mine:
            day = scoring.first_close_after(entry["received_utc"], trading_days)
            received = pd.Timestamp(entry["received_utc"]).tz_convert(eastern).strftime("%a %b %d, %I:%M %p ET")
            history.append({"received": received,
                            "counts_from": day.strftime("%a %b %d") if day is not None else "the next close",
                            "reason": str(entry.get("reason", ""))})

        body = page_html(nickname, latest.get("theme", ""), rows.get(netid), waiting.get(netid, ""), history, value_src,
                         latest.get("backtest"), backtest_src, latest.get("data_window"), "", latest.get("backtest_note"))
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if before.get("page") != digest:
            full = page_html(nickname, latest.get("theme", ""), rows.get(netid), waiting.get(netid, ""), history, value_src,
                             latest.get("backtest"), backtest_src, latest.get("data_window"), updated,
                             latest.get("backtest_note"))
            upload(public_bucket, "funds/%s.html" % slug, full, "text/html")
        # the private record (only rewritten when something in it changed)
        record = record_json(netid, mine, result, prices, trading_days, "")
        record_digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()
        if before.get("record") != record_digest:
            record["updated"] = updated
            upload(public_bucket, "records/%s.json" % record_slug_for(netid, salt), json.dumps(record), "application/json")
        state[netid] = {"backtest_for": mark, "value_for": "%s|%s|%s" % (mark, last_close, "live" if netid in rows else "waiting"), "page": digest,
                        "record": record_digest}

    write_text(entries_bucket, STATE_KEY, json.dumps(state), "application/json")
    return links


def number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out


def backtest_kind(notebook):
    if notebook == "studio6":
        return "Studio 6 (2026 so far)"
    if notebook == "momentum":
        return "momentum 50/200 (2026)"
    return "Studio 5 (2026, never seen)"


def backtest_board(result, entries):
    """Every fund's Studio 5 backtest, best first, and one chart of all their with-rules backtest lines."""
    keep = set(result["board"]["netid"]) if len(result["board"]) > 0 else set()
    if len(result["pending"]) > 0:
        keep = keep | set(result["pending"]["netid"])
    latest = {}
    for entry in entries:
        netid = entry.get("netid")
        if netid in keep and (netid not in latest or entry["received_utc"] > latest[netid]["received_utc"]):
            latest[netid] = entry
    rows = []
    lines = {}
    spy_line = None
    for netid in latest:
        entry = latest[netid]
        backtest = entry.get("backtest")
        if not isinstance(backtest, dict) or not isinstance(backtest.get("with your rules"), dict):
            continue
        ruled = backtest.get("with your rules", {})
        free = backtest.get("no rules", {})
        spy = backtest.get("S&P 500 (SPY)", {}) if isinstance(backtest.get("S&P 500 (SPY)"), dict) else {}
        rows.append({"netid": netid, "nickname": entry.get("nickname", ""), "theme": entry.get("theme", ""),
                     "stock_list": entry.get("stock_theme", ""),
                     "with_rules": number(ruled.get("ending value ($)")), "no_rules": number(free.get("ending value ($)")),
                     "spy": number(spy.get("ending value ($)")), "worst_drop": number(ruled.get("worst drop (%)")),
                     "window": entry.get("data_window") or ["", ""],
                     "kind": backtest_kind(entry.get("notebook"))})
        paths = entry.get("backtest_paths")
        if isinstance(paths, dict) and isinstance(paths.get("with your rules"), dict):
            lines[entry.get("nickname", netid)] = paths["with your rules"]
            if spy_line is None and isinstance(paths.get("S&P 500 (SPY)"), dict):
                spy_line = paths["S&P 500 (SPY)"]
    rows = sorted(rows, key=lambda r: -r["with_rules"] if r["with_rules"] == r["with_rules"] else 0)
    named = []
    for r in rows:
        name = r["nickname"] or r["netid"]
        if name in lines:
            named.append((name, lines[name]))
    data = interactive.paths_data(named, spy_line) if len(named) > 0 else None
    png = None
    if len(lines) > 0:
        figure = plt.figure(figsize=(11, 4.8), dpi=110)
        axis = figure.add_subplot(111)
        for name in lines:
            line = pd.Series(lines[name])
            line.index = pd.to_datetime(line.index)
            line = line.sort_index()
            axis.plot(line.index, line.values, linewidth=1.6, alpha=0.85, marker="o", markersize=3, label=name)
        if spy_line is not None:
            line = pd.Series(spy_line)
            line.index = pd.to_datetime(line.index)
            line = line.sort_index()
            axis.plot(line.index, line.values, color="black", linewidth=3, label="S&P 500 (SPY)")
        axis.axhline(10000, color="#bbbbbb", linestyle="--", linewidth=1)
        axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(live.dollars))
        axis.set_title("Every fund's latest backtest (with its rules): value of \\$10,000")
        axis.grid(alpha=0.25)
        if len(lines) <= 24:
            axis.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=False)
        figure.tight_layout()
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png")
        plt.close(figure)
        png = buffer.getvalue()
    return rows, png, data
