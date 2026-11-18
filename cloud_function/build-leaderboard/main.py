# build-leaderboard: Dr. Dave's class leaderboard for the OPIM 5641 portfolios (Studio 5, Studio 6, final project).
#
# Every 5 minutes (Cloud Scheduler) this function:
#   1. reads every entry the gatekeeper saved:   gs://<entries bucket>/submissions/<netid>/*.json
#      (optional) a roster:                       gs://<entries bucket>/roster/allowed_netids.csv  (one column: netid)
#   2. keeps a cache of daily closing prices:     gs://<entries bucket>/prices/daily_closes.csv
#      (asks Yahoo Finance only when a new close should exist or a new ticker shows up)
#   3. scores every fund (board.py) and writes, PRIVATE (entries bucket):
#        class/leaderboard_private.csv   one row per student: NetID, Google email, nickname, every number
#        class/daily_values.csv          every fund's value every day (netid, date, portfolio, value)
#        class/entries_log.csv           every entry ever made: when, which close it counts from, the reason
#      and PUBLIC (page bucket): index.html + chart.png (nicknames only)
#   4. (optional) a featured fund, watched every 5 minutes during the trading day (live.py): live.png
#      The featured NetID is one line in the PRIVATE bucket: config/featured.txt
#   5. one public page per fund (fund_pages.py): funds/<hash>.html, linked from each nickname
# HTTP entrypoint: build_http

import io
import json
import logging
import os
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from google.cloud import storage

import board as scoring
import crowd
import final_page
import fund_pages
import holdings_page
import interactive
import live
import page

ENTRIES_BUCKET = os.getenv("ENTRIES_BUCKET", "")
PUBLIC_BUCKET = os.getenv("PUBLIC_BUCKET", "")
PRICES_KEY = "prices/daily_closes.csv"
FETCH_STATE_KEY = "prices/last_fetch.json"
ROSTER_KEY = "roster/allowed_netids.csv"
NICKNAMES_KEY = "config/nicknames.json"   # optional, PRIVATE: {"netid": "Better fund name", ...} renames a fund everywhere
PRICE_HISTORY_DAYS = 14          # fetch from this many days before the first entry
YEAR_PRICES_FROM = "2025-12-30"  # ... and never later than this: the "2026 so far" chart holds every fund from Dec 31, 2025
REFETCH_MINUTES = 120            # after a fetch, wait at least this long before asking Yahoo again
EASTERN = ZoneInfo("America/New_York")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")


def read_text(bucket, key):
    blob = bucket.blob(key)
    if not blob.exists():
        return None
    return blob.download_as_text()


def write_text(bucket, key, text, content_type, cache=False):
    blob = bucket.blob(key)
    if not cache:
        blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(text, content_type=content_type)


def read_entries(bucket):
    entries = []
    for blob in bucket.list_blobs(prefix="submissions/"):
        if not blob.name.endswith(".json") or blob.size is None or blob.size > 64 * 1024:
            continue
        try:
            entry = json.loads(blob.download_as_text())
        except ValueError:
            logging.warning("skipping unreadable %s", blob.name)
            continue
        if "portfolios" in entry and "received_utc" in entry and "netid" in entry:
            entries.append(entry)
    return entries


def tag_concentrated(entries):
    """A pair's 🎯 concentrated fund (Studio 6) is its own fund on the board: fund id = the sender's NetID + '-c'."""
    for entry in entries:
        if entry.get("fund_kind") == "concentrated" and not str(entry.get("netid", "")).endswith(crowd.CONCENTRATED_SUFFIX):
            entry["owner_netid"] = entry["netid"]
            entry["netid"] = entry["netid"] + crowd.CONCENTRATED_SUFFIX


def tag_final(entries):
    """A final-project fund (sent from the Studio 6 notebook, decision = 'final') is its own fund on the board:
    fund id = the sender's NetID + '-f'. It starts with $10,000 at its first close, apart from the Studio 5 fund."""
    for entry in entries:
        if entry.get("decision") == "final" and not str(entry.get("netid", "")).endswith(crowd.FINAL_SUFFIX):
            entry["owner_netid"] = entry["netid"]
            entry["netid"] = entry["netid"] + crowd.FINAL_SUFFIX


def one_arena(result, prices, final):
    """The part of a board result that belongs to one arena (final funds, or everything else), ranked on its own."""
    def mine(frame):
        if len(frame) == 0:
            return frame
        is_final = frame["netid"].astype(str).str.endswith(crowd.FINAL_SUFFIX)
        return frame[is_final == final].reset_index(drop=True)

    board = mine(result["board"])
    if len(board) > 0:
        board = board.sort_values("with_rules_growth_pct", ascending=False).reset_index(drop=True)
        board["rank"] = range(1, len(board) + 1)
    benchmark_path = pd.Series(dtype=float)
    if len(board) > 0 and len(prices) > 0:
        first_day = pd.Timestamp(board["started"].min())
        benchmark_path, _ = scoring.value_path([(first_day, {scoring.BENCHMARK: 1.0})], prices.sort_index().ffill())
    return {"board": board, "pending": mine(result["pending"]), "values": mine(result["values"]), "log": result["log"],
            "benchmark_path": benchmark_path, "last_close": result["last_close"]}


def mark_concentrated(entries):
    for entry in entries:
        if entry.get("fund_kind") == "concentrated" and not str(entry.get("nickname", "")).startswith("🎯"):
            entry["nickname"] = "🎯 " + str(entry.get("nickname", ""))


def apply_nicknames(bucket, entries):
    """Dr. Dave can rename any fund (a typo, a clearer name) without anyone resubmitting."""
    text = read_text(bucket, NICKNAMES_KEY)
    if text is None or text.strip() == "":
        return
    try:
        names = json.loads(text)
    except ValueError:
        logging.warning("config/nicknames.json is not valid JSON; ignoring it")
        return
    for entry in entries:
        name = names.get(str(entry.get("netid", "")).lower())
        if isinstance(name, str) and name.strip() != "":
            entry["nickname"] = name.strip()[:60]


def latest_expected_close(now_utc):
    """The most recent weekday whose close (plus 30 minutes for the data to settle) has passed."""
    local = now_utc.astimezone(EASTERN)
    day = local.date()
    if local.hour * 60 + local.minute < 16 * 60 + 30:
        day = day - timedelta(days=1)
    while day.weekday() >= 5:
        day = day - timedelta(days=1)
    return pd.Timestamp(day)


def fetch_prices(tickers, start_day):
    import yfinance as yf
    data = yf.download(sorted(tickers), start=start_day.strftime("%Y-%m-%d"), interval="1d", auto_adjust=True,
                       progress=False, group_by="column", threads=True)
    if data is None or len(data) == 0:
        return None
    closes = data["Close"] if "Close" in data else data
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=sorted(tickers)[0])
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes.dropna(how="all")
    return closes


def get_prices(bucket, tickers, first_entry_utc, now_utc):
    cached = None
    text = read_text(bucket, PRICES_KEY)
    if text is not None:
        cached = pd.read_csv(io.StringIO(text), index_col=0, parse_dates=True)
    state = {}
    state_text = read_text(bucket, FETCH_STATE_KEY)
    if state_text is not None:
        state = json.loads(state_text)

    # during the trading day Yahoo returns today's price so far as today's row: it is not a close, so drop it
    last_close = latest_expected_close(now_utc)
    if cached is not None:
        cached = cached[cached.index <= last_close]

    start_day = pd.Timestamp(first_entry_utc).tz_localize(None).normalize() - pd.Timedelta(days=PRICE_HISTORY_DAYS)
    start_day = min(start_day, pd.Timestamp(YEAR_PRICES_FROM))
    needed = set(tickers)
    stale = cached is None
    if cached is not None:
        missing = needed - set(cached.columns)
        if len(missing) > 0 or cached.index.max() < last_close or cached.index.min() > start_day:
            stale = True
    recently = False
    if "fetched_utc" in state:
        last = datetime.fromisoformat(state["fetched_utc"])
        new_tickers = needed - set(state.get("tickers", []))
        recently = (now_utc - last) < timedelta(minutes=REFETCH_MINUTES) and len(new_tickers) == 0
    if stale and not recently:
        try:
            fresh = fetch_prices(needed, start_day)
        except Exception:
            logging.warning("price download failed: %s", traceback.format_exc())
            fresh = None
        if fresh is not None:
            fresh = fresh[fresh.index <= last_close]
        write_text(bucket, FETCH_STATE_KEY, json.dumps({"fetched_utc": now_utc.isoformat(), "tickers": sorted(needed),
                                                        "ok": fresh is not None}), "application/json")
        if fresh is not None and len(fresh) > 0:
            if cached is not None:
                # keep any old column Yahoo did not return this time
                for column in cached.columns:
                    if column not in fresh.columns:
                        fresh[column] = cached[column].reindex(fresh.index)
            cached = fresh
            write_text(bucket, PRICES_KEY, cached.to_csv(), "text/csv")
            logging.info("prices refreshed: %d days x %d tickers, last %s", len(cached), len(cached.columns),
                         cached.index.max().date())
    return cached


def build_http(request):
    try:
        now_utc = datetime.now(timezone.utc)
        client = storage.Client()
        entries_bucket = client.bucket(ENTRIES_BUCKET)
        public_bucket = client.bucket(PUBLIC_BUCKET)

        entries = read_entries(entries_bucket)
        tag_concentrated(entries)
        tag_final(entries)
        apply_nicknames(entries_bucket, entries)
        mark_concentrated(entries)
        allowed = None
        roster_text = read_text(entries_bucket, ROSTER_KEY)
        if roster_text is not None:
            roster = pd.read_csv(io.StringIO(roster_text), dtype=str)
            if len(roster) > 0:
                allowed = set(roster.iloc[:, 0].str.strip().str.lower())

        tickers = {scoring.BENCHMARK}
        for entry in entries:
            for key in scoring.PORTFOLIO_KEYS:
                tickers = tickers | set(entry["portfolios"][key].keys())

        prices = None
        if len(entries) > 0:
            first = min(entry["received_utc"] for entry in entries)
            prices = get_prices(entries_bucket, tickers, first, now_utc)
        if prices is None or len(prices) == 0:
            prices = pd.DataFrame(columns=[scoring.BENCHMARK], dtype=float)

        result = scoring.build_board(entries, prices, allowed_netids=allowed)
        # two arenas, each ranked on its own: the Studio 5 funds (practice) and the final-project funds
        practice = one_arena(result, prices, final=False)
        final = one_arena(result, prices, final=True)
        paged = dict(result)                      # for the fund pages: every fund, with its rank in its own arena
        paged["board"] = pd.concat([practice["board"], final["board"]]).reset_index(drop=True)

        # private tables
        if len(result["board"]) > 0:
            write_text(entries_bucket, "class/leaderboard_private.csv", result["board"].to_csv(index=False), "text/csv")
        if len(result["pending"]) > 0 or len(result["board"]) == 0:
            write_text(entries_bucket, "class/waiting_private.csv", result["pending"].to_csv(index=False), "text/csv")
        write_text(entries_bucket, "class/daily_values.csv", result["values"].to_csv(index=False), "text/csv")
        write_text(entries_bucket, "class/entries_log.csv", result["log"].to_csv(index=False), "text/csv")

        # the featured fund (watching only, never part of the scoring)
        featured = None
        featured_text = read_text(entries_bucket, live.FEATURED_KEY)
        if featured_text is not None and featured_text.strip() != "" and len(prices) > 0:
            try:
                featured = live.featured(featured_text.strip().lower(), entries, prices, result, entries_bucket,
                                         now_utc, EASTERN, read_text, write_text)
            except Exception:
                logging.warning("featured fund skipped: %s", traceback.format_exc())
        if featured is not None:
            blob = public_bucket.blob("live.png")
            blob.cache_control = "no-cache, max-age=0"
            blob.upload_from_string(featured["png"], content_type="image/png")
            if featured["backtest_png"] is not None:
                blob = public_bucket.blob("backtest.png")
                blob.cache_control = "no-cache, max-age=0"
                blob.upload_from_string(featured["backtest_png"], content_type="image/png")

        # public page
        updated = now_utc.astimezone(EASTERN).strftime("%a %b %d, %I:%M %p ET")

        # one page per fund (click a nickname); never let it break the leaderboard
        links = {}
        try:
            links = fund_pages.build(paged, entries, prices, entries_bucket, public_bucket, read_text, write_text,
                                     updated, EASTERN)
        except Exception:
            logging.warning("fund pages skipped: %s", traceback.format_exc())
        # "Who holds what": every fund's stocks on one page (fund names only)
        try:
            write_text(public_bucket, "holdings.html", holdings_page.render(practice, entries, prices, links, updated), "text/html")
        except Exception:
            logging.warning("holdings page skipped: %s", traceback.format_exc())
        backtests = []
        backtests_png = None
        backtests_data = None
        try:
            backtests, backtests_png, backtests_data = fund_pages.backtest_board(practice, entries)
            if backtests_png is not None:
                blob = public_bucket.blob("backtests.png")
                blob.cache_control = "no-cache, max-age=0"
                blob.upload_from_string(backtests_png, content_type="image/png")
        except Exception:
            logging.warning("backtest board skipped: %s", traceback.format_exc())
        # "2026 so far": every fund's current mix held from Dec 31, 2025, with a line where the funds went live
        year_data = None
        try:
            year_data = fund_pages.year_so_far(practice, entries, prices)
        except Exception:
            logging.warning("2026-so-far chart skipped: %s", traceback.format_exc())
        crowds = {"crowd": None, "concentrated": None}
        try:
            crowds = crowd.build(entries, prices, entries_bucket, read_text, now_utc, updated)
            write_text(public_bucket, "crowd.json", crowds["json"], "application/json")
        except Exception:
            logging.warning("crowd skipped: %s", traceback.format_exc())
        extras = []
        for key in ["crowd", "concentrated"]:
            one = crowds.get(key)
            if one is not None and len(one["path"]) > 0:
                extras.append((one["name"], one["path"], "#6a1b9a" if key == "crowd" else "#c2185b"))
        race_chart = None
        race_data = None
        if len(practice["board"]) > 0:
            race_chart = page.make_chart(practice["values"], practice["board"], practice["benchmark_path"], extras)
            race_data = interactive.race_data(practice["values"], practice["board"], practice["benchmark_path"], extras)
        if race_chart is not None:
            blob = public_bucket.blob("chart.png")
            blob.cache_control = "no-cache, max-age=0"
            blob.upload_from_string(race_chart, content_type="image/png")
        # the front page is the final-project leaderboard; the Studio 5 funds have their own tab
        try:
            write_text(public_bucket, "index.html", final_page.render(final, entries, prices, links, updated), "text/html")
        except Exception:
            logging.warning("final page skipped: %s", traceback.format_exc())
        write_text(public_bucket, "studio5.html", page.render(practice, updated, featured=featured, links=links, backtests=backtests,
                                                                backtests_chart=backtests_png is not None,
                                                                race_chart=race_chart is not None, race_data=race_data,
                                                                backtests_data=backtests_data, crowds=crowds,
                                                                year_data=year_data), "text/html")

        summary = {"ok": True, "entries": len(entries), "funds_live": len(result["board"]),
                   "funds_waiting": len(result["pending"]), "last_close": result["last_close"],
                   "featured": None if featured is None else featured["as_of"]}
        logging.info("built: %s", summary)
        return (json.dumps(summary), 200, {"Content-Type": "application/json"})
    except Exception:
        logging.error("build failed: %s", traceback.format_exc())
        return (json.dumps({"ok": False, "error": traceback.format_exc()[-800:]}), 500, {"Content-Type": "application/json"})
