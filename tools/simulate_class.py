# Dress rehearsal: run the gatekeeper's checks and the whole leaderboard build locally, with pretend students and
# REAL prices, against an in-memory stand-in for Cloud Storage. Writes the page to tools/out/ so you can open it.
#   python tools/simulate_class.py
import io
import json
import pandas as pd
import os
import sys
import types
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cloud_function", "build-leaderboard"))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)


class FakeBlob:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self.cache_control = None

    @property
    def size(self):
        return len(self.store[self.name]) if self.name in self.store else None

    def exists(self):
        return self.name in self.store

    def download_as_text(self):
        return self.store[self.name].decode("utf-8")

    def download_as_bytes(self):
        return self.store[self.name]

    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        if if_generation_match == 0 and self.name in self.store:
            raise RuntimeError("would overwrite")
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.store[self.name] = data


class FakeBucket:
    def __init__(self):
        self.store = {}

    def blob(self, name):
        return FakeBlob(self.store, name)

    def list_blobs(self, prefix=""):
        names = []
        for name in self.store:
            if name.startswith(prefix):
                names.append(name)
        blobs = []
        for name in sorted(names):
            blobs.append(FakeBlob(self.store, name))
        return blobs


BUCKETS = {"entries": FakeBucket(), "page": FakeBucket()}


class FakeClient:
    def bucket(self, name):
        return BUCKETS[name]


fake_storage = types.ModuleType("google.cloud.storage")
fake_storage.Client = FakeClient
import google.cloud
google.cloud.storage = fake_storage
sys.modules["google.cloud.storage"] = fake_storage

os.environ["ENTRIES_BUCKET"] = "entries"
os.environ["PUBLIC_BUCKET"] = "page"
import main as builder          # noqa: E402  (build-leaderboard/main.py)
import importlib.util           # noqa: E402
spec = importlib.util.spec_from_file_location("gatekeeper", os.path.join(ROOT, "cloud_function", "submit-portfolio", "main.py"))
gatekeeper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gatekeeper)

# ---- 1. the gatekeeper's checks
good = {"netid": "ABC12345", "nickname": "Tech Titans", "theme": "big tech",
        "portfolios": {"no_rules": {"NVDA": 0.6, "LLY": 0.4}, "with_rules": {"NVDA": 0.1, "aapl": 0.1, "MSFT": 0.1, "LLY": 0.1,
                                                                            "XOM": 0.1, "CVX": 0.1, "WMT": 0.1, "CAT": 0.1,
                                                                            "GOOGL": 0.1, "META": 0.0995, "KO": 0.0005}}}
cleaned, problem = gatekeeper.check_entry(good)
assert problem is None, problem
assert cleaned["netid"] == "abc12345" and "AAPL" in cleaned["portfolios"]["with_rules"] and "KO" not in cleaned["portfolios"]["with_rules"]
assert abs(sum(cleaned["portfolios"]["with_rules"].values()) - 1) < 1e-6
bad_cases = [
    dict(good, netid="dave"),
    dict(good, nickname="x"),
    dict(good, portfolios={"no_rules": {"NVDA": 0.5}, "with_rules": good["portfolios"]["with_rules"]}),
    dict(good, portfolios={"no_rules": {"NV DA!": 1.0}, "with_rules": good["portfolios"]["with_rules"]}),
    dict(good, portfolios={"no_rules": {"NVDA": "lots"}, "with_rules": good["portfolios"]["with_rules"]}),
    dict(good, portfolios={"with_rules": good["portfolios"]["with_rules"]}),
]
for case in bad_cases:
    _, problem = gatekeeper.check_entry(case)
    assert problem is not None, case
    print("rejected as expected:", problem)
print("gatekeeper checks OK")

# ---- 1b. a pair's 🎯 concentrated fund (Studio 6)
focus = {"netid": "abc12345", "nickname": "Costco Believers", "theme": "great companies we understand",
         "fund_kind": "concentrated", "partner_netid": "bcd23456",
         "theses": {"COST": "we shop there every week and the membership keeps growing",
                    "AAPL": "everyone in class has an iPhone", "LLY": "weight-loss drugs are a huge market"},
         "portfolios": {"no_rules": {"COST": 0.4, "AAPL": 0.35, "LLY": 0.25},
                        "with_rules": {"COST": 0.4, "AAPL": 0.35, "LLY": 0.25}}}
cleaned, problem = gatekeeper.check_entry(focus)
assert problem is None, problem
assert gatekeeper.fund_id(cleaned) == "abc12345-c" and cleaned["partner_netid"] == "bcd23456"
assert gatekeeper.fund_id(gatekeeper.check_entry(good)[0]) == "abc12345"
focus_bad = [
    dict(focus, fund_kind="yolo"),
    dict(focus, theses={"COST": "a fine store", "AAPL": "phones"}),
    dict(focus, portfolios={"no_rules": {"COST": 0.6, "AAPL": 0.4}, "with_rules": {"COST": 0.6, "AAPL": 0.4}}),
    dict(focus, portfolios={"no_rules": {"COST": 0.4, "AAPL": 0.3, "NVDA": 0.3}, "with_rules": {"COST": 0.4, "AAPL": 0.3, "NVDA": 0.3}}),
    dict(focus, partner_netid="dave"),
    dict(focus, theses={"COST": "ok", "AAPL": "everyone in class has an iPhone", "LLY": "weight-loss drugs"}),
]
for case in focus_bad:
    _, problem = gatekeeper.check_entry(case)
    assert problem is not None, case
    print("rejected as expected:", problem)
print("concentrated checks OK")
builder.crowd.CROWD_START = "2026-10-21"          # the real start (Nov 5) has no closes yet in a test run
builder.crowd.CONCENTRATED_START = "2026-10-28"


# ---- 2. pretend students (entries saved straight into the fake bucket, as the gatekeeper would)
def save(netid, nickname, theme, received, no_rules, with_rules, reason="first launch"):
    entry = {"netid": netid, "nickname": nickname, "theme": theme, "reason": reason, "received_utc": received,
             "google_email": netid + "@example.com", "portfolios": {"no_rules": no_rules, "with_rules": with_rules}}
    key = "submissions/%s/%s.json" % (netid, received.replace(":", "-"))
    BUCKETS["entries"].blob(key).upload_from_string(json.dumps(entry))


ten = {}
for t in ["NVDA", "LLY", "XOM", "CVX", "WMT", "CAT", "GOOGL", "META", "AAPL", "GS"]:
    ten[t] = 0.1
save("abc12345", "Tech Titans", "big tech and friends", "2026-10-07T23:30:00Z", {"NVDA": 0.7, "LLY": 0.3}, ten)
save("bcd23456", "Steady Eddie", "dividends", "2026-10-07T23:45:00Z", {"KO": 0.5, "PG": 0.5},
     {"KO": 0.2, "PG": 0.2, "JNJ": 0.2, "PEP": 0.2, "VZ": 0.2})
save("cde34567", "Oil Barons", "energy", "2026-10-07T23:50:00Z", {"XOM": 1.0},
     {"XOM": 0.25, "CVX": 0.25, "COP": 0.25, "SLB": 0.25})
# a change two weeks later (counts from the next close), and a typo ticker held as cash
save("cde34567", "Oil Barons", "energy, then cooled off", "2026-10-21T14:00:00Z", {"XOM": 1.0},
     {"XOM": 0.2, "CVX": 0.2, "NEE": 0.2, "DUK": 0.2, "ZZZZQ": 0.2}, reason="added utilities after the oil drop")
# a student who joins tonight: waiting for the next close
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
save("def45678", "Late Bloomer", "sports and streaming", now, {"NFLX": 1.0}, {"NFLX": 0.5, "DIS": 0.3, "NKE": 0.2})

# a crowd (SIM_CROWD=20): a full class, to check the clickable charts stay readable; each has a pretend backtest
crowd = int(os.getenv("SIM_CROWD", "0"))
pool = ["NVDA", "LLY", "XOM", "CVX", "WMT", "CAT", "GOOGL", "META", "AAPL", "GS", "KO", "PG", "JNJ", "PEP", "VZ",
        "NEE", "DUK", "MSFT", "AMZN", "JPM", "COST", "HD", "UNH", "AVGO", "LMT", "RTX", "DIS", "NFLX", "MCD", "SBUX"]
for k in range(crowd):
    picks = {}
    for j in range(5):
        picks[pool[(k * 3 + j * 7) % len(pool)]] = 0.2
    received = "2026-10-%02dT2%d:00:00Z" % (7 + (k % 3) * 7, k % 4)
    netid = "sim%05d" % k
    save(netid, "Student fund %d" % (k + 1), "pretend theme %d" % (k + 1), received, {pool[k % len(pool)]: 1.0}, picks)
    path = {}
    spy = {}
    level = 10000.0
    for m in range(1, 11):
        level = level * (1 + 0.004 * ((k % 7) - 2) + 0.01 * ((m * (k + 3)) % 5 - 2) / 2)
        path["2026-%02d-28" % m] = round(level, 2)
        spy["2026-%02d-28" % m] = round(10000 * (1 + 0.011 * m), 2)
    key = "submissions/%s/%s.json" % (netid, received.replace(":", "-"))
    entry = json.loads(BUCKETS["entries"].store[key].decode())
    entry["backtest"] = {"with your rules": {"ending value ($)": level, "worst drop (%)": 4.0},
                         "no rules": {"ending value ($)": level * 1.02}, "S&P 500 (SPY)": {"ending value ($)": spy["2026-10-28"]}}
    entry["backtest_paths"] = {"with your rules": path, "S&P 500 (SPY)": spy}
    entry["data_window"] = ["2021-09-01", "2026-10-28"]
    BUCKETS["entries"].blob(key).upload_from_string(json.dumps(entry))
# two pairs' 🎯 funds, saved where the gatekeeper puts them, plus a Dr. Dave demo fund the crowd must ignore
for netid, name, picks in [("abc12345", "Costco Believers", {"COST": 0.4, "AAPL": 0.35, "LLY": 0.25}),
                           ("cde34567", "Chip Conviction", {"NVDA": 0.4, "AVGO": 0.3, "AMD": 0.15, "MU": 0.15})]:
    theses = {}
    for t in picks:
        theses[t] = "we understand %s and think it keeps growing" % t
    entry = {"netid": netid, "nickname": name, "theme": "pair fund", "reason": "Studio 6 concentrated fund",
             "received_utc": "2026-10-27T23:30:00Z", "google_email": netid + "@example.com", "fund_kind": "concentrated",
             "theses": theses, "partner_netid": "", "portfolios": {"no_rules": picks, "with_rules": picks}}
    BUCKETS["entries"].blob("submissions/%s-c/2026-10-27T23-30-00Z.json" % netid).upload_from_string(json.dumps(entry))
save("zzz00009", "Dr. Dave demo", "demo", "2026-10-07T23:30:00Z", {"TSLA": 1.0}, {"TSLA": 1.0})
# FINAL-PROJECT funds (Studio 6 "Your Final Fund"): saved under the student's own NetID, as the gatekeeper does.
# abc12345 already has a Studio 5 fund; its final fund must be a separate fund that starts with $10,000.
twelve = {}
for t in ["NVDA", "LLY", "XOM", "CVX", "WMT", "KO", "GE", "JNJ", "AVGO", "AMD", "COST", "JPM"]:
    twelve[t] = round(1 / 12, 6)
for netid, name, strategy, received in [("abc12345", "FINAL: Chips and Steady", "momentum plus steady names", "2026-10-28T23:10:00Z"),
                                        ("bcd23456", "FINAL: Bargain Bin", "bargains", "2026-10-29T15:00:00Z"),
                                        ("cde34567", "FINAL: Sent Tonight", "my own view", now)]:
    entry = {"netid": netid, "nickname": name, "theme": strategy, "reason": "Studio 6 final fund. Test.",
             "received_utc": received, "google_email": netid + "@example.com", "decision": "final", "notebook": "studio6",
             "stock_theme": "final fund", "portfolios": {"no_rules": {"NVDA": 0.6, "LLY": 0.4}, "with_rules": twelve}}
    BUCKETS["entries"].blob("submissions/%s/final_%s.json" % (netid, received.replace(":", "-"))).upload_from_string(json.dumps(entry))
if crowd > 0:
    # a Studio 6 decision (Nov 17 rework): sim00001 changes the fund from the Studio 6 notebook. No backtest is sent.
    # The crowd must keep the Studio 5 mix, and the fund's Studio 5 backtest must stay on its page and the board.
    decided = {"netid": "sim00001", "nickname": "Student fund 2", "theme": "pretend theme 2",
               "reason": "Studio 6 (change): moved into two stocks after the drop", "received_utc": "2026-10-28T23:30:00Z",
               "google_email": "sim00001@example.com", "notebook": "studio6", "decision": "change",
               "portfolios": {"no_rules": {"SBUX": 1.0}, "with_rules": {"SBUX": 0.5, "MCD": 0.5}}}
    BUCKETS["entries"].blob("submissions/sim00001/2026-10-28T23-30-00Z.json").upload_from_string(json.dumps(decided))
    # ... and a student whose FIRST fund comes from the Studio 6 notebook still joins the crowd
    first = {"netid": "new00001", "nickname": "Launched in Studio 6", "theme": "late start",
             "reason": "Studio 6 (refresh): first fund", "received_utc": "2026-10-28T23:40:00Z",
             "google_email": "new00001@example.com", "notebook": "studio6", "decision": "refresh",
             "portfolios": {"no_rules": {"HD": 1.0}, "with_rules": {"HD": 0.5, "UNH": 0.5}}}
    BUCKETS["entries"].blob("submissions/new00001/2026-10-28T23-40-00Z.json").upload_from_string(json.dumps(first))
    # Dr. Dave renames one fund without anyone resubmitting
    BUCKETS["entries"].blob("config/nicknames.json").upload_from_string(json.dumps({"sim00000": "Renamed by Dr. Dave"}))

# ---- 3. build it twice (the second run must reuse the price cache)
for attempt in range(2):
    body, status, _ = builder.build_http(None)
    print("build", attempt + 1, status, body[:300])
    assert status == 200

store = BUCKETS["entries"].store
for key in ["class/leaderboard_private.csv", "class/daily_values.csv", "class/entries_log.csv", "prices/daily_closes.csv"]:
    assert key in store, key
public_crowd = json.loads(BUCKETS["page"].store["crowd.json"].decode())
late = 1 if crowd > 0 else 0          # the student who launched from the Studio 6 notebook
assert public_crowd["crowd"]["members"] == 4 + crowd + late, public_crowd["crowd"]["members"]      # no demo, no 🎯
if crowd > 0:
    studio5_mix = json.loads(store["submissions/sim00001/2026-10-14T21-00-00Z.json"].decode())["portfolios"]["with_rules"]
    assert studio5_mix in public_crowd["funds"], "the crowd lost sim00001's Studio 5 mix"
    assert {"SBUX": 0.5, "MCD": 0.5} not in public_crowd["funds"], "a Studio 6 decision moved the crowd"
    assert {"HD": 0.5, "UNH": 0.5} in public_crowd["funds"], "a first fund sent from Studio 6 should join the crowd"
    board_text = BUCKETS["page"].store["studio5.html"].decode()
    kept = 0
    for name in BUCKETS["page"].store:
        if name.startswith("funds/") and name.endswith(".html"):
            text = BUCKETS["page"].store[name].decode()
            if "Studio 6 (change): moved into two stocks" in text:
                assert "No backtest was sent" not in text, "the Studio 6 decision erased the Studio 5 backtest"
                kept += 1
    assert kept == 1, kept
    print("Studio 6 decision OK: crowd unchanged, backtest kept")
assert public_crowd["concentrated_crowd"]["members"] == 2
assert "TSLA" not in public_crowd["crowd"]["weights"]
assert len(public_crowd["funds"]) == 4 + crowd + late and len(public_crowd["concentrated_funds"]) == 2
total = 0
for t in public_crowd["crowd"]["weights"]:
    total += public_crowd["crowd"]["weights"][t]
assert abs(total - 1) < 1e-4, total
assert len(public_crowd["named_funds"]) == len(public_crowd["funds"])
named_text = json.dumps(public_crowd["named_funds"])
assert "Tech Titans" in named_text and "abc12345" not in named_text and "@example.com" not in named_text
for one in public_crowd["named_funds"]:
    assert one["weights"] in public_crowd["funds"], one["name"]
holding_pages = 0
for name in BUCKETS["page"].store:
    if name.startswith("funds/") and name.endswith(".html"):
        text = BUCKETS["page"].store[name].decode()
        assert "abc12345" not in text and "@example.com" not in text, name
        if "What it holds" in text:
            holding_pages += 1
assert holding_pages >= 4, holding_pages
print("fund pages OK:", holding_pages, "pages list their holdings")
who = BUCKETS["page"].store["holdings.html"].decode()
assert "Tech Titans" in who and "Who holds what" in who and "abc12345" not in who and "@example.com" not in who
assert "holdings.html" in BUCKETS["page"].store["studio5.html"].decode()
open(os.path.join(OUT, "holdings.html"), "wb").write(BUCKETS["page"].store["holdings.html"])
assert "spy_growth_pct" in public_crowd["crowd"]["stats"] and "vs_spy_pct" in public_crowd["crowd"]["stats"]
assert "the same dollars in each of" in BUCKETS["page"].store["studio5.html"].decode()
print("holdings page OK; crowd vs S&P:", public_crowd["crowd"]["stats"]["vs_spy_pct"])
index_text = BUCKETS["page"].store["studio5.html"].decode()
assert "2026 so far: before and after the funds went live" in index_text and "lbChart('year'" in index_text
assert '"marker":{"date":"2026-11-05"' in index_text
print("2026-so-far chart OK")
front = BUCKETS["page"].store["index.html"].decode()
practice_page = BUCKETS["page"].store["studio5.html"].decode()
assert "Final Project Leaderboard" in front and "FINAL: Chips and Steady" in front and "FINAL: Bargain Bin" in front
assert "FINAL: Sent Tonight" in front and "Starting at the next market close" in front
assert "Tech Titans" not in front, "a Studio 5 fund is on the final board"
assert "FINAL:" not in practice_page, "a final fund is on the Studio 5 board"
assert "Tech Titans" in practice_page and "Studio 5 Funds (practice)" in practice_page
assert "abc12345" not in front and "@example.com" not in front
private = pd.read_csv(io.StringIO(store["class/leaderboard_private.csv"].decode()))
finals = private[private["netid"].astype(str).str.endswith("-f")]
assert len(finals) == 2, len(finals)
values = pd.read_csv(io.StringIO(store["class/daily_values.csv"].decode()))
first = values[(values["netid"] == "abc12345-f") & (values["portfolio"] == "with_rules")].sort_values("date").iloc[0]
assert abs(first["value"] - 10000) < 1, first["value"]      # the test mix adds up to 0.999996
assert {"NVDA": 0.6, "LLY": 0.4} not in public_crowd["funds"] and twelve not in public_crowd["funds"], "a final fund is in the crowd"
open(os.path.join(OUT, "final.html"), "wb").write(BUCKETS["page"].store["index.html"])
open(os.path.join(OUT, "studio5.html"), "wb").write(BUCKETS["page"].store["studio5.html"])
print("final arena OK:", len(finals), "final funds ranked, 1 waiting; Studio 5 board untouched")
index = json.loads(BUCKETS["page"].store["fund_records.json"].decode())
index_names = [one["name"] for one in index["funds"]]
assert "Tech Titans" in index_names and not any(name.startswith("FINAL:") for name in index_names), index_names
titans = [one for one in index["funds"] if one["name"] == "Tech Titans"][0]
record_key = titans["record"].split("/page/")[-1] if "/page/" in titans["record"] else "records/" + titans["record"].split("/records/")[-1]
assert record_key in BUCKETS["page"].store, record_key
assert "abc12345" not in json.dumps(index)
print("fund_records.json OK:", len(index_names), "funds listed by name")
print("crowd OK:", public_crowd["crowd"]["members"], "funds,", public_crowd["crowd"]["stats"])
open(os.path.join(OUT, "crowd.json"), "wb").write(BUCKETS["page"].store["crowd.json"])
page_text = BUCKETS["page"].store["studio5.html"].decode()
assert "🎯 Costco Believers" in page_text and "Class crowd fund" in page_text
focus_pages = []
for name in BUCKETS["page"].store:
    if name.startswith("funds/") and name.endswith(".html") and "Why these companies" in BUCKETS["page"].store[name].decode():
        focus_pages.append(name)
assert len(focus_pages) == 2, focus_pages
open(os.path.join(OUT, "focus_page.html"), "wb").write(BUCKETS["page"].store[focus_pages[0]])
open(os.path.join(OUT, "index.html"), "wb").write(BUCKETS["page"].store["studio5.html"])
open(os.path.join(OUT, "chart.png"), "wb").write(BUCKETS["page"].store["chart.png"])
open(os.path.join(OUT, "leaderboard_private.csv"), "wb").write(store["class/leaderboard_private.csv"])
open(os.path.join(OUT, "entries_log.csv"), "wb").write(store["class/entries_log.csv"])
print(store["class/leaderboard_private.csv"].decode()[:2000])
print(store["class/entries_log.csv"].decode())
print("wrote", OUT)
