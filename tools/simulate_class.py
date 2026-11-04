# Dress rehearsal: run the gatekeeper's checks and the whole leaderboard build locally, with pretend students and
# REAL prices, against an in-memory stand-in for Cloud Storage. Writes the page to tools/out/ so you can open it.
#   python tools/simulate_class.py
import json
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
if crowd > 0:
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
open(os.path.join(OUT, "index.html"), "wb").write(BUCKETS["page"].store["index.html"])
open(os.path.join(OUT, "chart.png"), "wb").write(BUCKETS["page"].store["chart.png"])
open(os.path.join(OUT, "leaderboard_private.csv"), "wb").write(store["class/leaderboard_private.csv"])
open(os.path.join(OUT, "entries_log.csv"), "wb").write(store["class/entries_log.csv"])
print(store["class/leaderboard_private.csv"].decode()[:2000])
print(store["class/entries_log.csv"].decode())
print("wrote", OUT)
