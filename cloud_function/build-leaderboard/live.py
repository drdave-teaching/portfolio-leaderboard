# live.py: one featured fund (Dr. Dave's), watched every few minutes during the trading day.
# For watching only: the leaderboard itself is scored on daily closes (board.py).
#
# The featured NetID lives in the PRIVATE bucket (config/featured.txt), so it is not in this public repo.
# Intraday prices (5-minute bars) are cached in prices/intraday_5m.csv and asked for at most every few minutes,
# only while the market is open (plus once after the close).

import io
import json
import logging
from datetime import datetime, time, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd

import board as scoring

INTRADAY_KEY = "prices/intraday_5m.csv"
INTRADAY_STATE_KEY = "prices/intraday_state.json"
FEATURED_KEY = "config/featured.txt"
INTRADAY_MINUTES = 4            # ask Yahoo for new 5-minute bars at most this often
OPEN = time(9, 30)
CLOSED = time(16, 15)           # a few minutes after 4 PM, so the last bars come in
COLORS = {"with_rules": "#e67e22", "no_rules": "#7f8c8d", "spy": "black"}


def market_open(now_et):
    return now_et.weekday() < 5 and OPEN <= now_et.time() < CLOSED


def last_session_end(now_et):
    """The most recent weekday 4:15 PM (Eastern) that has already passed."""
    day = now_et.date()
    if now_et.time() < CLOSED:
        day = day - timedelta(days=1)
    while day.weekday() >= 5:
        day = day - timedelta(days=1)
    return datetime.combine(day, CLOSED, tzinfo=now_et.tzinfo)


def fetch_intraday(tickers, eastern):
    import yfinance as yf
    data = yf.download(sorted(tickers), period="5d", interval="5m", auto_adjust=False, prepost=False,
                       progress=False, group_by="column", threads=True)
    if data is None or len(data) == 0:
        return None
    closes = data["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=sorted(tickers)[0])
    index = pd.to_datetime(closes.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    closes.index = index.tz_convert(eastern)
    return closes.dropna(how="all")


def fetch_previous_closes(tickers, session_day):
    """Each ticker's actual (unadjusted) closing price on the last trading day before session_day."""
    import yfinance as yf
    data = yf.download(sorted(tickers), period="10d", interval="1d", auto_adjust=False, progress=False,
                       group_by="column", threads=True)
    closes = data["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=sorted(tickers)[0])
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes[closes.index < pd.Timestamp(session_day)].dropna(how="all")
    if len(closes) == 0:
        return {}, None
    last = closes.ffill().iloc[-1]
    previous = {}
    for ticker in last.index:
        if not np.isnan(last[ticker]):
            previous[ticker] = float(last[ticker])
    return previous, closes.index[-1]


def get_intraday(bucket, tickers, now_utc, eastern, read_text, write_text):
    """5-minute bars for the latest session, plus the previous close of every ticker. Cached in the bucket."""
    now_et = now_utc.astimezone(eastern)
    state = {}
    state_text = read_text(bucket, INTRADAY_STATE_KEY)
    if state_text is not None:
        state = json.loads(state_text)
    bars = None
    bars_text = read_text(bucket, INTRADAY_KEY)
    if bars_text is not None:
        bars = pd.read_csv(io.StringIO(bars_text), index_col=0)
        bars.index = pd.to_datetime(bars.index, utc=True).tz_convert(eastern)

    fetched = None
    if "fetched_utc" in state:
        fetched = datetime.fromisoformat(state["fetched_utc"])
    new_tickers = set(tickers) - set(state.get("tickers", []))
    due = bars is None or fetched is None or len(new_tickers) > 0
    if not due and market_open(now_et):
        due = (now_utc - fetched) >= timedelta(minutes=INTRADAY_MINUTES)
    if not due and not market_open(now_et):
        due = fetched < last_session_end(now_et)

    if due:
        try:
            fresh = fetch_intraday(tickers, eastern)
        except Exception:
            logging.warning("intraday download failed", exc_info=True)
            fresh = None
        if fresh is not None and len(fresh) > 0:
            session_day = fresh.index[-1].date()
            previous = state.get("previous_close", {})
            if state.get("session_day") != str(session_day) or len(new_tickers) > 0:
                previous, previous_day = fetch_previous_closes(tickers, session_day)
                state["previous_day"] = None if previous_day is None else str(previous_day.date())
            bars = fresh
            state.update({"fetched_utc": now_utc.isoformat(), "tickers": sorted(tickers),
                          "session_day": str(session_day), "previous_close": previous})
            saved = bars.copy()
            saved.index = saved.index.tz_convert("UTC")
            write_text(bucket, INTRADAY_KEY, saved.to_csv(), "text/csv")
            write_text(bucket, INTRADAY_STATE_KEY, json.dumps(state), "application/json")
    if bars is None or "session_day" not in state:
        return None, None, {}
    session_day = pd.Timestamp(state["session_day"])
    today = bars[bars.index.date == session_day.date()].ffill()
    return today, session_day, state.get("previous_close", {})


def today_path(weights, bars, previous):
    """The fund's % change since the previous close, at every 5-minute bar. Missing tickers are held as cash."""
    relative = pd.Series(0.0, index=bars.index)
    for ticker in weights:
        share = weights[ticker]
        if ticker in bars.columns and ticker in previous and bars[ticker].notna().any():
            relative = relative + share * bars[ticker].ffill().bfill() / previous[ticker]
        else:
            relative = relative + share
    total = sum(weights.values())
    return 100 * (relative / total - 1)


def drifted(weights, prices, start_day, end_day):
    """Buy-and-hold shares after the prices moved from start_day to end_day (daily closes)."""
    out = {}
    for ticker in weights:
        if ticker in prices.columns and not np.isnan(prices.loc[start_day, ticker]) and not np.isnan(prices.loc[end_day, ticker]):
            out[ticker] = weights[ticker] * prices.loc[end_day, ticker] / prices.loc[start_day, ticker]
        else:
            out[ticker] = weights[ticker]
    total = sum(out.values())
    for ticker in out:
        out[ticker] = out[ticker] / total
    return out


def featured(netid, entries, prices, result, bucket, now_utc, eastern, read_text, write_text):
    """Everything the page needs for the featured fund, or None if that NetID has no entry."""
    mine = sorted([e for e in entries if e.get("netid") == netid], key=lambda e: e["received_utc"])
    if len(mine) == 0:
        return None
    prices = prices.sort_index().ffill()
    trading_days = list(prices.index)

    tickers = {scoring.BENCHMARK}
    for entry in mine:
        for key in scoring.PORTFOLIO_KEYS:
            tickers = tickers | set(entry["portfolios"][key].keys())
    bars, session_day, previous = get_intraday(bucket, tickers, now_utc, eastern, read_text, write_text)
    if bars is None or len(bars) == 0:
        return None

    # which holdings were in place during this session: the latest entry that counted from a close before it
    segments = []
    for entry in mine:
        day = scoring.first_close_after(entry["received_utc"], trading_days)
        if day is not None and day < session_day:
            segments.append((day, entry))
    live_today = len(segments) > 0
    before = [d for d in trading_days if d < session_day]
    holdings = {}
    for key in scoring.PORTFOLIO_KEYS:
        if live_today and len(before) > 0:
            start_day, entry = segments[-1]
            holdings[key] = drifted(entry["portfolios"][key], prices, start_day, before[-1])
        else:
            holdings[key] = mine[-1]["portfolios"][key]

    today = {}
    for key in scoring.PORTFOLIO_KEYS:
        today[key] = today_path(holdings[key], bars, previous)
    today["spy"] = today_path({scoring.BENCHMARK: 1.0}, bars, previous)

    # since it started: the daily values, plus a live point for today
    values = result["values"]
    since = {}
    if len(values) > 0:
        own = values[values["netid"] == netid]
        for key in scoring.PORTFOLIO_KEYS:
            series = own[own["portfolio"] == key]
            since[key] = pd.Series(series["value"].values, index=pd.to_datetime(series["date"]))
    started = None
    spy_since = pd.Series(dtype=float)
    if len(since) > 0 and len(since["with_rules"]) > 0:
        started = since["with_rules"].index[0]
        spy_since = 10000 * prices.loc[started:, scoring.BENCHMARK] / prices.loc[started, scoring.BENCHMARK]

    value_now = {}
    if live_today and len(since) > 0:
        for key in scoring.PORTFOLIO_KEYS:
            path = since[key][since[key].index < session_day]
            if len(path) > 0:
                value_now[key] = float(path.iloc[-1]) * (1 + today[key].iloc[-1] / 100)

    latest = bars.index[-1]
    nickname = mine[-1].get("nickname", "Featured fund")
    status = "live"
    if not live_today:
        first = scoring.first_close_after(mine[0]["received_utc"], trading_days)
        if first is None:
            status = "Its $10,000 starts at the next close. Until then, this shows how its stocks are moving."
        else:
            status = "It started at the close on %s, so today shows how its stocks moved that day." % first.strftime("%a %b %d")

    # what it holds, and what each stock did to it today (contribution = share x move, in percentage points)
    sectors = mine[-1].get("sectors", {})
    holding_rows = []
    for ticker in sorted(set(holdings["with_rules"]) | set(holdings["no_rules"])):
        move = np.nan
        if ticker in bars.columns and ticker in previous and bars[ticker].notna().any():
            move = 100 * (bars[ticker].ffill().iloc[-1] / previous[ticker] - 1)
        ruled_share = holdings["with_rules"].get(ticker, 0.0)
        holding_rows.append({
            "ticker": ticker,
            "sector": sectors.get(ticker, ""),
            "with_rules_pct": 100 * ruled_share,
            "no_rules_pct": 100 * holdings["no_rules"].get(ticker, 0.0),
            "today_pct": move,
            "contribution_pts": ruled_share * move if ruled_share > 0 else np.nan,
        })
    holding_rows = sorted(holding_rows, key=lambda r: (-r["with_rules_pct"], -r["no_rules_pct"]))

    png = make_live_chart(today, since, spy_since, value_now, session_day, latest, nickname, eastern)
    return {
        "nickname": nickname,
        "status": status,
        "session_label": session_day.strftime("%a %b %d"),
        "as_of": latest.strftime("%I:%M %p ET").lstrip("0"),
        "today_pct": {k: round(float(today[k].iloc[-1]), 2) for k in today},
        "value_now": {k: round(v, 2) for k, v in value_now.items()},
        "holdings": holding_rows,
        "png": png,
    }


def dollars(value, position):
    return "${:,.0f}".format(value)


def make_live_chart(today, since, spy_since, value_now, session_day, latest, nickname, eastern):
    figure = plt.figure(figsize=(12, 4.4), dpi=110)
    left = figure.add_subplot(1, 2, 1)
    labels = {"with_rules": "%s (with rules)" % nickname, "no_rules": "no-rules twin", "spy": "S&P 500 (SPY)"}
    for key in ["spy", "no_rules", "with_rules"]:
        width = 2.6 if key == "with_rules" else 1.6
        left.plot(today[key].index, today[key].values, color=COLORS[key], linewidth=width, label=labels[key])
    left.axhline(0, color="#bbbbbb", linestyle="--", linewidth=1)
    left.set_title("%s: change since the last close (%%)" % session_day.strftime("%a %b %d"))
    left.xaxis.set_major_locator(mdates.HourLocator(tz=eastern))
    left.xaxis.set_major_formatter(mdates.DateFormatter("%I %p", tz=eastern))
    left.grid(alpha=0.25)
    left.legend(fontsize=8, frameon=False, loc="best")

    right = figure.add_subplot(1, 2, 2)
    if len(since) > 0 and len(since["with_rules"]) > 0:
        for key in ["no_rules", "with_rules"]:
            width = 2.6 if key == "with_rules" else 1.6
            right.plot(since[key].index, since[key].values, color=COLORS[key], linewidth=width, marker="o",
                       markersize=3, label=labels[key])
        right.plot(spy_since.index, spy_since.values, color=COLORS["spy"], linewidth=1.8, marker="o", markersize=3,
                   label=labels["spy"])
        if len(value_now) > 0:
            now_day = pd.Timestamp(latest.date())
            for key in value_now:
                last = since[key][since[key].index < now_day]
                if len(last) > 0:
                    right.plot([last.index[-1], now_day], [last.iloc[-1], value_now[key]], color=COLORS[key],
                               linestyle=":", linewidth=1.6)
                    right.plot([now_day], [value_now[key]], color=COLORS[key], marker="*", markersize=11)
            spy_last = spy_since[spy_since.index < now_day]
            if len(spy_last) > 0:
                spy_now = spy_last.iloc[-1] * (1 + today["spy"].iloc[-1] / 100)
                right.plot([spy_last.index[-1], now_day], [spy_last.iloc[-1], spy_now], color="black", linestyle=":")
                right.plot([now_day], [spy_now], color="black", marker="*", markersize=11)
        right.axhline(10000, color="#bbbbbb", linestyle="--", linewidth=1)
        right.set_title("Value of $10,000 since it started (stars = right now)")
        right.legend(fontsize=8, frameon=False, loc="best")
        right.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
        right.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        right.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(dollars))
    else:
        right.text(0.5, 0.5, "The since-it-started line\nbegins after the first close.", ha="center", va="center",
                   fontsize=12, color="#5b6b80", transform=right.transAxes)
        right.set_xticks([])
        right.set_yticks([])
        right.set_title("Value of $10,000 since it started")
    right.grid(alpha=0.25)
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    return buffer.getvalue()
