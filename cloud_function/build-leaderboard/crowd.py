# crowd.py: the class crowd fund (Studio 6).
#
# The crowd fund is the average of every STUDENT's diversified fund (their latest Studio 5 mix, with rules; Studio 6
# decisions do not change it), each student counting equally, bought at the close on CROWD_START and held. Dr. Dave's funds (dww05002, zzz*) and any
# NetID listed in the PRIVATE config/crowd_exclude.txt are left out. Entries received after FREEZE_UTC do not change the
# crowd (the funds still race on the board).
#
# The 🎯 crowd is the same idea for the pairs' concentrated funds (fund_kind "concentrated"), held from
# CONCENTRATED_START.
#
# Public output, crowd.json: the crowd's mix and its live line, plus every member fund's weights WITHOUT names, in a
# shuffled order ("funds"), so a notebook can draw the class on a risk-return map and never say whose fund is whose.
# "named_funds" (Nov 17, Studio 6 "who holds it?") lists the same student funds by their PUBLIC leaderboard nickname:
# the board already shows each nickname with its holdings on the fund's page. NetIDs and emails are never in this file.

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
FINAL_SUFFIX = "-f"                        # a final-project fund (Studio 6 "Your Final Fund"): its own fund id


def is_demo(netid):
    netid = str(netid)
    if netid.endswith(CONCENTRATED_SUFFIX):
        netid = netid[:-len(CONCENTRATED_SUFFIX)]
    if netid.endswith(FINAL_SUFFIX):
        netid = netid[:-len(FINAL_SUFFIX)]
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
    """({fund id: that fund's latest with-rules mix received before the freeze}, {fund id: its public nickname})."""
    latest = {}
    managed = {}      # a student's first Studio 6 decision: only used when they have no Studio 5 fund at all
    for entry in entries:
        netid = str(entry.get("netid", ""))
        is_concentrated = netid.endswith(CONCENTRATED_SUFFIX)
        if is_concentrated != concentrated:
            continue
        if is_demo(netid) or netid in excluded or entry.get("owner_netid", netid) in excluded:
            continue
        if entry["received_utc"] > FREEZE_UTC:
            continue
        if entry.get("decision") == "final" or netid.endswith(FINAL_SUFFIX):
            continue          # a final-project fund is not part of the class crowd fund (that is the Studio 5 funds)
        if not concentrated and entry.get("notebook") == "studio6":
            # the crowd is the class's Studio 5 funds, held: a Studio 6 decision (hold / refresh / change) is that
            # manager's own move, and must not move the benchmark everyone is compared with
            if netid not in managed or entry["received_utc"] < managed[netid]["received_utc"]:
                managed[netid] = entry
            continue
        if netid not in latest or entry["received_utc"] > latest[netid]["received_utc"]:
            latest[netid] = entry
    for netid in managed:
        if netid not in latest:
            latest[netid] = managed[netid]
    mixes = {}
    names = {}
    for netid in latest:
        mixes[netid] = latest[netid]["portfolios"]["with_rules"]
        names[netid] = str(latest[netid].get("nickname", "") or "a fund")
    return mixes, names


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
        # the S&P 500 over the same days, so the crowd can be compared with the market
        spy_path, _ = scoring.value_path([(start, {scoring.BENCHMARK: 1.0})], prices)
        if len(spy_path) > 0:
            spy_growth = 100 * (float(spy_path.iloc[-1]) / float(spy_path.iloc[0]) - 1)
            out["stats"]["spy_growth_pct"] = round(spy_growth, 2)
            out["stats"]["vs_spy_pct"] = round(out["stats"]["growth_pct"] - spy_growth, 2)
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
    diversified, names = members(entries, False, excluded)
    focused, focused_names = members(entries, True, excluded)
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
    named = []
    for netid in sorted(diversified, key=lambda n: names[n].lower()):
        named.append({"name": names[netid], "weights": diversified[netid]})
    public["named_funds"] = named
    return {"crowd": crowd, "concentrated": concentrated, "json": json.dumps(public)}
