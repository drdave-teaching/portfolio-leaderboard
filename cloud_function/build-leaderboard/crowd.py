# crowd.py: the class crowd fund (Studio 6).
#
# The crowd fund is the average of every STUDENT's diversified fund (their latest Studio 5 mix, with rules), each
# student counting equally, bought at the close on CROWD_START and held. Dr. Dave's funds (dww05002, zzz*) and any
# NetID listed in the PRIVATE config/crowd_exclude.txt are left out. Entries received after FREEZE_UTC do not change the
# crowd (the funds still race on the board).
#
# The 🎯 crowd is the same idea for the pairs' concentrated funds (fund_kind "concentrated"), held from
# CONCENTRATED_START.
#
# Public output, crowd.json: the crowd's mix and its live line, plus every member fund's weights WITHOUT names, in a
# shuffled order, so a notebook can draw the class on a risk-return map and still never say whose fund is whose.

import hashlib
import json

import pandas as pd

import board as scoring

FREEZE_UTC = "2026-11-19T04:59:59Z"        # Wed Nov 18, 11:59:59 PM Eastern
CROWD_START = "2026-11-05"                 # the Studio 5 makeup: the crowd is held from this close
CONCENTRATED_START = "2026-11-19"          # 🎯 funds are sent on Studio 6 night (Nov 18), so they count from Nov 19
EXCLUDE_KEY = "config/crowd_exclude.txt"
DEMO_NETIDS = {"dww05002"}
CONCENTRATED_SUFFIX = "-c"


def is_demo(netid):
    netid = str(netid)
    if netid.endswith(CONCENTRATED_SUFFIX):
        netid = netid[:-len(CONCENTRATED_SUFFIX)]
    return netid in DEMO_NETIDS or netid.startswith("zzz")


def read_excluded(bucket, read_text):
    excluded = set()
    text = read_text(bucket, EXCLUDE_KEY)
    if text is None:
        return excluded
    for line in text.splitlines():
        if line.strip() != "":
            excluded.add(line.strip().lower())
    return excluded


def members(entries, concentrated, excluded):
    """{fund id: that fund's latest with-rules mix received before the freeze}."""
    latest = {}
    for entry in entries:
        netid = str(entry.get("netid", ""))
        is_concentrated = netid.endswith(CONCENTRATED_SUFFIX)
        if is_concentrated != concentrated:
            continue
        if is_demo(netid) or netid in excluded or entry.get("owner_netid", netid) in excluded:
            continue
        if entry["received_utc"] > FREEZE_UTC:
            continue
        if netid not in latest or entry["received_utc"] > latest[netid]["received_utc"]:
            latest[netid] = entry
    mixes = {}
    for netid in latest:
        mixes[netid] = latest[netid]["portfolios"]["with_rules"]
    return mixes


def average_mix(mixes):
    total = {}
    for netid in mixes:
        for ticker in mixes[netid]:
            total[ticker] = total.get(ticker, 0.0) + mixes[netid][ticker] / len(mixes)
    out = {}
    for ticker in sorted(total, key=lambda t: -total[t]):
        out[ticker] = round(total[ticker], 6)
    return out


def first_day_on_or_after(day, trading_days):
    target = pd.Timestamp(day)
    for d in trading_days:
        if pd.Timestamp(d) >= target:
            return pd.Timestamp(d)
    return None


def one_crowd(mixes, prices, start_day, name):
    if len(mixes) == 0:
        return None
    mix = average_mix(mixes)
    out = {"name": name, "members": len(mixes), "weights": mix, "start": None, "path": pd.Series(dtype=float),
           "stats": None}
    start = first_day_on_or_after(start_day, list(prices.index))
    if start is None:
        return out
    path, _ = scoring.value_path([(start, mix)], prices)
    out["start"] = start.strftime("%Y-%m-%d")
    out["path"] = path
    if len(path) > 0:
        out["stats"] = scoring.path_stats(path)
    return out


def anonymous(mixes):
    """The member mixes with no names, in an order that has nothing to do with the board."""
    keyed = []
    for netid in mixes:
        text = json.dumps(mixes[netid], sort_keys=True)
        keyed.append((hashlib.sha256(text.encode("utf-8")).hexdigest(), mixes[netid]))
    keyed = sorted(keyed, key=lambda pair: pair[0])
    out = []
    for pair in keyed:
        out.append(pair[1])
    return out


def path_json(path):
    out = {"dates": [], "values": []}
    for day in path.index:
        out["dates"].append(pd.Timestamp(day).strftime("%Y-%m-%d"))
        out["values"].append(round(float(path.loc[day]), 2))
    return out


def build(entries, prices, bucket, read_text, now_utc, updated):
    """Returns {"crowd": ..., "concentrated": ..., "json": public text}. Either crowd can be None."""
    prices = prices.sort_index().ffill()
    excluded = read_excluded(bucket, read_text)
    diversified = members(entries, False, excluded)
    focused = members(entries, True, excluded)
    crowd = one_crowd(diversified, prices, CROWD_START, "👥 Class crowd fund")
    concentrated = one_crowd(focused, prices, CONCENTRATED_START, "🎯 Concentrated crowd")
    public = {"updated": updated, "last_close": prices.index[-1].strftime("%Y-%m-%d") if len(prices) > 0 else "",
              "freeze_utc": FREEZE_UTC, "frozen": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ") > FREEZE_UTC,
              "note": "Each fund counts once (students only). Funds are listed with no names, in a shuffled order."}
    for key, funds_key, one, mixes in [("crowd", "funds", crowd, diversified),
                                       ("concentrated_crowd", "concentrated_funds", concentrated, focused)]:
        public[funds_key] = anonymous(mixes)
        if one is None:
            public[key] = None
            continue
        public[key] = {"members": one["members"], "start": one["start"], "weights": one["weights"],
                       "stats": one["stats"], "path": path_json(one["path"])}
    return {"crowd": crowd, "concentrated": concentrated, "json": json.dumps(public)}
