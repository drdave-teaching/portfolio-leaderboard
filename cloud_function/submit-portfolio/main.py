# submit-portfolio: the gatekeeper for the OPIM 5641 portfolio leaderboard.
#
# Students run one cell at the end of the Studio 5 notebook. It signs them in with Google (Colab does this) and sends
# their entry here. This function accepts the entry only if:
#   1. the Google sign-in is real (we ask Google who the token belongs to, so the email cannot be faked),
#   2. the class code matches (Dr. Dave writes it on the board; it is NOT in the public notebook),
#   3. the entry is a sensible portfolio file (NetID format, two portfolios whose shares add up to 1, small).
# Then it saves the entry as a NEW file, gs://<entries bucket>/submissions/<netid>/<time>_<random>.json, and never
# overwrites anything, so every change a student makes is kept with its time and reason.
# HTTP entrypoint: submit_http

import hashlib
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone

import requests
from google.api_core import exceptions as gexc
from google.cloud import storage

ENTRIES_BUCKET = os.getenv("ENTRIES_BUCKET", "")
CLASS_CODE = os.getenv("CLASS_CODE", "")
BOARD_URL = os.getenv("BOARD_URL", "")
MAX_BYTES = 64 * 1024              # a real entry is a few KB
MAX_HOLDINGS = 80                  # per portfolio
NETID_PATTERN = re.compile(r"^[a-z]{3}[0-9]{5}$")       # UConn NetID: three letters, five digits
TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-^=]{1,12}$")
PORTFOLIO_KEYS = ["no_rules", "with_rules"]
FUND_KINDS = ["diversified", "concentrated"]
CONCENTRATED_MIN = 3              # a Studio 6 🎯 fund: 3 to 6 companies ...
CONCENTRATED_MAX = 6
CONCENTRATED_CAP = 0.40           # ... and at most 40% in any one of them
CONCENTRATED_SUFFIX = "-c"        # the builder uses the same suffix (crowd.py)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")


def reply(status, body):
    return (json.dumps(body), status, {"Content-Type": "application/json"})


def who_is_signed_in(request):
    """Ask Google whose access token this is. Returns the verified email, or None."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer "):].strip()
    try:
        answer = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": token}, timeout=10)
    except requests.RequestException:
        return None
    if answer.status_code != 200:
        return None
    info = answer.json()
    if info.get("email_verified") not in (True, "true"):
        return None
    return info.get("email")


def clean_portfolio(weights):
    """Return (cleaned weights, problem). Drops shares below 0.1% and rescales the rest to add up to exactly 1."""
    if not isinstance(weights, dict) or len(weights) == 0:
        return None, "a portfolio is empty"
    kept = {}
    for ticker in weights:
        share = weights[ticker]
        if not isinstance(ticker, str) or not TICKER_PATTERN.match(ticker.upper()):
            return None, "this does not look like a ticker: %r" % (ticker,)
        try:
            share = float(share)
        except (TypeError, ValueError):
            return None, "the share for %s is not a number" % ticker
        if share < -0.001 or share > 1.001:
            return None, "the share for %s must be between 0 and 1" % ticker
        if share >= 0.001:
            kept[ticker.upper()] = share
    if len(kept) == 0:
        return None, "a portfolio holds nothing"
    if len(kept) > MAX_HOLDINGS:
        return None, "a portfolio holds more than %d stocks" % MAX_HOLDINGS
    total = sum(kept.values())
    if total < 0.97 or total > 1.03:
        return None, "the shares add up to %.3f, not 1" % total
    for ticker in kept:
        kept[ticker] = round(kept[ticker] / total, 6)
    return kept, None


def check_entry(entry):
    """Return (cleaned entry, problem)."""
    if not isinstance(entry, dict):
        return None, "the entry is not a JSON object"
    netid = str(entry.get("netid", "")).strip().lower()
    if not NETID_PATTERN.match(netid):
        return None, "NetID should look like abc12345 (three letters, five digits)"
    nickname = str(entry.get("nickname", "")).strip()
    if len(nickname) < 2 or len(nickname) > 30:
        return None, "pick a nickname of 2 to 30 characters"
    portfolios = entry.get("portfolios", {})
    if not isinstance(portfolios, dict):
        return None, "portfolios is missing"
    cleaned_portfolios = {}
    for key in PORTFOLIO_KEYS:
        weights, problem = clean_portfolio(portfolios.get(key))
        if problem is not None:
            return None, "%s: %s" % (key, problem)
        cleaned_portfolios[key] = weights
    cleaned = dict(entry)
    cleaned.pop("class_code", None)
    cleaned["netid"] = netid
    cleaned["nickname"] = nickname
    cleaned["theme"] = str(entry.get("theme", "")).strip()[:80]
    cleaned["reason"] = str(entry.get("reason", "")).strip()[:200]
    cleaned["portfolios"] = cleaned_portfolios
    kind = str(entry.get("fund_kind", "diversified") or "diversified").strip().lower()
    if kind not in FUND_KINDS:
        return None, "fund_kind should be 'diversified' or 'concentrated'"
    cleaned["fund_kind"] = kind
    if kind == "concentrated":
        problem = check_concentrated(entry, cleaned)
        if problem is not None:
            return None, problem
    return cleaned, None


def check_concentrated(entry, cleaned):
    """A Studio 6 🎯 fund: 3 to 6 companies, at most 40% in one, and a one-line thesis for every company it holds."""
    theses = entry.get("theses")
    if not isinstance(theses, dict) or len(theses) < CONCENTRATED_MIN or len(theses) > CONCENTRATED_MAX:
        return "a concentrated fund needs %d to %d companies, each with a one-line thesis" % (CONCENTRATED_MIN, CONCENTRATED_MAX)
    kept = {}
    for ticker in theses:
        if not isinstance(ticker, str) or not TICKER_PATTERN.match(ticker.upper()):
            return "this does not look like a ticker: %r" % (ticker,)
        text = str(theses[ticker]).strip()
        if len(text) < 5:
            return "write a one-line thesis for %s" % ticker.upper()
        kept[ticker.upper()] = text[:200]
    for key in PORTFOLIO_KEYS:
        mix = cleaned["portfolios"][key]
        if len(mix) > CONCENTRATED_MAX:
            return "a concentrated fund holds at most %d companies" % CONCENTRATED_MAX
        for ticker in mix:
            if mix[ticker] > CONCENTRATED_CAP + 0.005:
                return "%s is %.0f%% of the fund; the cap is %.0f%%" % (ticker, 100 * mix[ticker], 100 * CONCENTRATED_CAP)
            if ticker not in kept:
                return "%s is in the fund but has no thesis" % ticker
    partner = str(entry.get("partner_netid", "") or "").strip().lower()
    if partner != "" and not NETID_PATTERN.match(partner):
        return "partner_netid should look like abc12345 (or leave it blank)"
    cleaned["theses"] = kept
    cleaned["partner_netid"] = partner
    return None


def fund_id(cleaned):
    """Where the fund lives: the NetID, or the NetID + '-c' for a pair's concentrated fund (its own line on the board)."""
    if cleaned.get("fund_kind") == "concentrated":
        return cleaned["netid"] + CONCENTRATED_SUFFIX
    return cleaned["netid"]


def submit_http(request):
    if request.method == "GET":
        return reply(200, {"ok": True, "message": "The portfolio gatekeeper is running. Submit from the Studio 5 notebook."})
    if request.method != "POST":
        return reply(405, {"ok": False, "problem": "use POST"})
    if request.content_length is not None and request.content_length > MAX_BYTES:
        return reply(413, {"ok": False, "problem": "the entry is too big"})

    email = who_is_signed_in(request)
    if email is None:
        return reply(401, {"ok": False, "problem": "Google sign-in did not work. Re-run the cell and sign in when Colab asks."})

    try:
        entry = json.loads(request.get_data(as_text=True))
    except ValueError:
        return reply(400, {"ok": False, "problem": "the entry is not valid JSON"})
    if not isinstance(entry, dict):
        return reply(400, {"ok": False, "problem": "the entry is not a JSON object"})

    if CLASS_CODE == "" or str(entry.get("class_code", "")).strip().lower() != CLASS_CODE.strip().lower():
        return reply(403, {"ok": False, "problem": "the class code is not right (Dr. Dave writes it on the board)"})

    cleaned, problem = check_entry(entry)
    if problem is not None:
        return reply(400, {"ok": False, "problem": problem})

    now = datetime.now(timezone.utc)
    cleaned["received_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    cleaned["google_email"] = email
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    key = "submissions/%s/%s_%s.json" % (fund_id(cleaned), stamp, secrets.token_hex(3))
    cleaned["submission_id"] = key

    blob = storage.Client().bucket(ENTRIES_BUCKET).blob(key)
    try:
        # if_generation_match=0: only create, never overwrite
        blob.upload_from_string(json.dumps(cleaned, indent=1), content_type="application/json", if_generation_match=0)
    except gexc.PreconditionFailed:
        return reply(409, {"ok": False, "problem": "please run the cell again"})
    logging.info("saved %s from %s", key, email)

    return reply(200, {
        "ok": True,
        "netid": cleaned["netid"],
        "nickname": cleaned["nickname"],
        "theme": cleaned["theme"],
        "reason": cleaned["reason"],
        "received_utc": cleaned["received_utc"],
        "google_email": email,
        "submission_id": key,
        "holdings": {"no_rules": len(cleaned["portfolios"]["no_rules"]), "with_rules": len(cleaned["portfolios"]["with_rules"])},
        "portfolios": cleaned["portfolios"],
        "risk_limit": cleaned.get("risk_limit"),
        "rules": cleaned.get("rules"),
        "data_window": cleaned.get("data_window"),
        "backtest_has_lines": isinstance(cleaned.get("backtest_paths"), dict),
        "counts_from": "the next market close after %s" % cleaned["received_utc"],
        "board": BOARD_URL,
        "fund_kind": cleaned["fund_kind"],
        "fund_page": fund_page_url(fund_id(cleaned)),
        "record": record_url(fund_id(cleaned)),
    })


def fund_page_url(netid):
    """The fund's own page on the leaderboard (same address the builder uses), or '' before the builder has run."""
    try:
        salt_blob = storage.Client().bucket(ENTRIES_BUCKET).blob("config/salt.txt")
        if not salt_blob.exists():
            return ""
        salt = salt_blob.download_as_text().strip()
    except Exception:
        return ""
    slug = hashlib.sha256((salt + netid).encode("utf-8")).hexdigest()[:12]
    return BOARD_URL.rsplit("/", 1)[0] + "/funds/%s.html" % slug


def record_url(netid):
    """The fund's private record (for the final-project dashboard). Same address the builder writes."""
    try:
        salt_blob = storage.Client().bucket(ENTRIES_BUCKET).blob("config/salt.txt")
        if not salt_blob.exists():
            return ""
        salt = salt_blob.download_as_text().strip()
    except Exception:
        return ""
    slug = hashlib.sha256((salt + netid + "|record").encode("utf-8")).hexdigest()[:24]
    return BOARD_URL.rsplit("/", 1)[0] + "/records/%s.json" % slug
