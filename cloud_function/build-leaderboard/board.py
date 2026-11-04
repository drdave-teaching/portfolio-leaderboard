# board.py: the scoring logic of the OPIM 5641 portfolio leaderboard (no cloud code here, so it can be tested locally).
#
# Rules of the game
#   - Each student's entry has two portfolios, "no_rules" and "with_rules" (ticker -> share of the money).
#   - Every entry counts from the NEXT market close after it was received (no hindsight). Entries made during
#     Wednesday's 7 PM studio count from Thursday's close.
#   - Each portfolio starts at $10,000 and is held (buy and hold) until the student changes it. A change starts the
#     new mix with what the old mix was worth that day, so the value line continues; nothing resets.
#   - Changes are unlimited. Every one is kept, with its time and reason.
#   - A ticker with no price is held as cash (flat), and flagged.

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

EASTERN = ZoneInfo("America/New_York")
START_VALUE = 10000.0
PORTFOLIO_KEYS = ["with_rules", "no_rules"]
BENCHMARK = "SPY"


def close_time_utc(day):
    """The 4 PM Eastern market close of a calendar day, in UTC (handles daylight saving)."""
    local = datetime.combine(pd.Timestamp(day).date(), time(16, 0), tzinfo=EASTERN)
    return pd.Timestamp(local).tz_convert("UTC")


def first_close_after(received_utc, trading_days):
    """The first trading day whose close is after the entry was received, or None if that close has not happened."""
    received = pd.Timestamp(received_utc)
    if received.tzinfo is None:
        received = received.tz_localize("UTC")
    for day in trading_days:
        if close_time_utc(day) > received:
            return pd.Timestamp(day)
    return None


def expected_start_label(received_utc):
    """For an entry still waiting: the weekday whose close it will count from (holidays not checked)."""
    received = pd.Timestamp(received_utc)
    if received.tzinfo is None:
        received = received.tz_localize("UTC")
    local = received.tz_convert(EASTERN)
    day = local.date()
    if local.time() >= time(16, 0):
        day = day + timedelta(days=1)
    while day.weekday() >= 5:
        day = day + timedelta(days=1)
    return "%s %d" % (day.strftime("%a %b"), day.day)


def value_path(segments, prices, start_value=START_VALUE):
    """segments: list of (start_day, weights) sorted by day. Returns (daily value Series, tickers held as cash)."""
    pieces = []
    cash_tickers = set()
    value = start_value
    for k in range(len(segments)):
        start, weights = segments[k]
        if k + 1 < len(segments):
            end = segments[k + 1][0]
        else:
            end = prices.index[-1]
        window = prices.loc[start:end]
        if len(window) == 0:
            continue
        relative = pd.Series(0.0, index=window.index)
        for ticker in weights:
            share = weights[ticker]
            if ticker in window.columns and not np.isnan(window[ticker].iloc[0]):
                relative = relative + share * window[ticker] / window[ticker].iloc[0]
            else:
                relative = relative + share
                cash_tickers.add(ticker)
        segment_values = value * relative
        if len(pieces) > 0:
            segment_values = segment_values.iloc[1:]      # the change day is already the last point of the previous piece
        pieces.append(segment_values)
        if len(segment_values) > 0:
            value = segment_values.iloc[-1]
    if len(pieces) == 0:
        return pd.Series(dtype=float), cash_tickers
    return pd.concat(pieces), cash_tickers


def path_stats(path):
    if len(path) < 1:
        return {"growth_pct": np.nan, "worst_drop_pct": np.nan, "daily_move_pct": np.nan, "value": np.nan}
    daily = path.pct_change().dropna()
    worst = (1 - path / path.cummax()).max()
    move = np.nan
    if len(daily) >= 2:
        move = 100 * daily.std()
    return {
        "value": round(float(path.iloc[-1]), 2),
        "growth_pct": round(100 * (path.iloc[-1] / path.iloc[0] - 1), 2),
        "worst_drop_pct": round(100 * worst, 2),
        "daily_move_pct": round(move, 2) if not np.isnan(move) else np.nan,
    }


def build_board(submissions, prices, allowed_netids=None):
    """submissions: list of entry dicts (as saved by the gatekeeper). prices: daily closes, one column per ticker
    (including SPY), index = trading days. Returns a dict with the leaderboard rows, the daily values and the log."""
    prices = prices.sort_index().ffill()
    trading_days = list(prices.index)

    by_student = {}
    log_rows = []
    for entry in submissions:
        netid = entry.get("netid")
        if allowed_netids is not None and netid not in allowed_netids:
            log_rows.append({"netid": netid, "received_utc": entry.get("received_utc"), "status": "not on roster"})
            continue
        by_student.setdefault(netid, []).append(entry)

    rows = []
    pending = []
    value_rows = []
    for netid in sorted(by_student):
        entries = sorted(by_student[netid], key=lambda e: e["received_utc"])
        latest = entries[-1]

        # one segment per entry, by the close it counts from; two entries before the same close: the later one wins
        segments = {}
        for entry in entries:
            day = first_close_after(entry["received_utc"], trading_days)
            log_rows.append({
                "netid": netid,
                "nickname": entry.get("nickname"),
                "received_utc": entry.get("received_utc"),
                "counts_from": "" if day is None else day.strftime("%Y-%m-%d"),
                "reason": entry.get("reason", ""),
                "holdings_with_rules": len(entry["portfolios"]["with_rules"]),
                "holdings_no_rules": len(entry["portfolios"]["no_rules"]),
                "google_email": entry.get("google_email", ""),
                "status": "counted" if day is not None else "waiting for the next close",
            })
            if day is not None:
                segments[day] = entry

        base = {
            "netid": netid,
            "nickname": latest.get("nickname", netid),
            "theme": latest.get("theme", ""),
            "stock_list": latest.get("stock_theme", ""),
            "google_email": latest.get("google_email", ""),
            "entries": len(entries),
            "changes": len(entries) - 1,
            "last_entry_utc": latest.get("received_utc"),
            "stocks_with_rules": len(latest["portfolios"]["with_rules"]),
            "stocks_no_rules": len(latest["portfolios"]["no_rules"]),
        }
        if len(segments) == 0:
            base["starts"] = expected_start_label(entries[0]["received_utc"])
            pending.append(base)
            continue

        days = sorted(segments)
        row = dict(base)
        row["changes"] = len(days) - 1
        row["started"] = days[0].strftime("%Y-%m-%d")
        row["trading_days"] = len(prices.loc[days[0]:])
        cash_all = set()
        for key in PORTFOLIO_KEYS:
            seg_list = []
            for day in days:
                seg_list.append((day, segments[day]["portfolios"][key]))
            path, cash = value_path(seg_list, prices)
            cash_all = cash_all | cash
            stats = path_stats(path)
            for name in stats:
                row["%s_%s" % (key, name)] = stats[name]
            for day in path.index:
                value_rows.append({"netid": netid, "date": day.strftime("%Y-%m-%d"), "portfolio": key,
                                   "value": round(float(path.loc[day]), 2)})
        spy_path, _ = value_path([(days[0], {BENCHMARK: 1.0})], prices)
        spy = path_stats(spy_path)
        row["spy_growth_pct"] = spy["growth_pct"]
        row["rules_minus_no_rules_pct"] = round(row["with_rules_growth_pct"] - row["no_rules_growth_pct"], 2)
        row["rules_minus_spy_pct"] = round(row["with_rules_growth_pct"] - spy["growth_pct"], 2)
        row["no_price_tickers"] = " ".join(sorted(cash_all))
        rows.append(row)

    board = pd.DataFrame(rows)
    if len(board) > 0:
        board = board.sort_values("with_rules_growth_pct", ascending=False).reset_index(drop=True)
        board.insert(0, "rank", range(1, len(board) + 1))

    benchmark_path = pd.Series(dtype=float)
    if len(board) > 0:
        first_day = pd.Timestamp(board["started"].min())
        benchmark_path, _ = value_path([(first_day, {BENCHMARK: 1.0})], prices)

    return {
        "board": board,
        "pending": pd.DataFrame(pending),
        "values": pd.DataFrame(value_rows),
        "log": pd.DataFrame(log_rows),
        "benchmark_path": benchmark_path,
        "last_close": prices.index[-1].strftime("%Y-%m-%d") if len(prices) > 0 else "",
    }
