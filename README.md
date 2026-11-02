# portfolio-leaderboard

Dr. Dave's class leaderboard for the OPIM 5641 portfolio project (Studio 5, Studio 6 and the final project).
Students build Ms. Womack's model with their own business rules in the Studio 5 notebook and submit **two**
portfolios: one **with their rules** (their fund) and its **no-rules twin**. The leaderboard tracks both every day,
starting with $10,000 each.

```
Studio 5 notebook (Part 5)                 your project: opim5641-portfolio-f26
  Google sign-in + class code  ──POST──▶  submit-portfolio  (the gatekeeper: checks sign-in, code, entry)
                                              │ saves a NEW file, never overwrites
                                              ▼
                                   gs://opim5641-portfolio-f26/submissions/<netid>/<time>.json   (private)
                                              │ every 5 minutes
                                              ▼
                                   build-leaderboard  ── prices (Yahoo, cached) ── scores every fund
                                     private: class/leaderboard_private.csv, class/daily_values.csv, class/entries_log.csv
                                     public:  https://storage.googleapis.com/opim5641-leaderboard-f26/index.html
```

## Rules of the game
- An entry counts from the **next market close** after it is received (no hindsight). Wednesday-night studio entries
  count from Thursday's close.
- Each portfolio is held (buy and hold) until the student changes it. Changes are unlimited and logged; a change
  starts from what the fund was worth that day, so the value line continues.
- A ticker with no price is held as cash and listed in the private table (`no_price_tickers`).
- A **featured fund** (Dr. Dave's) gets a live panel: its move today vs the S&P 500 from 5-minute prices, and its
  value since it started. Watching only; the ranks use daily closes. The NetID is set in the private bucket
  (`config/featured.txt`), not in this repo.
- The page ranks by the fund **with rules** and shows the no-rules twin, the S&P 500 (SPY) over the same days, the
  worst drop and the number of changes. Nicknames only.

## Once: set it up (about 5 minutes)
1. The project `opim5641-portfolio-f26` exists. Link billing (Billing → Link a billing account).
2. Open Cloud Shell in that project, paste [`setup_leaderboard.sh`](setup_leaderboard.sh) after changing
   `CLASS_CODE` on line 7. Count seven ✅ lines.
3. To change the class code later, edit it and paste the script again.

## Watch it
```bash
BUCKET=opim5641-portfolio-f26
gcloud storage cat gs://$BUCKET/class/leaderboard_private.csv      # NetID, Google email, nickname, every number
gcloud storage cat gs://$BUCKET/class/entries_log.csv              # every entry: when, counts from, reason
gcloud scheduler jobs run build-leaderboard-15min --location=us-central1   # rebuild now
```

Optional roster: put a one-column CSV of NetIDs at `gs://$BUCKET/roster/allowed_netids.csv` and entries from any
other NetID are left off the board (they are still kept and logged).

## Test it locally
`python tools/simulate_class.py` runs the gatekeeper's checks and a full build with pretend students and real prices,
and writes the page to `tools/out/`.
