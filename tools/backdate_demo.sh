# Dr. Dave's demo funds start at the Oct 21, 2026 close (Dave's call, Nov 4), so the board has two weeks of history.
# Dave's fund and examples 2-3: every entry moves to Oct 21 (seconds keep their order); example 4 gets its Oct 20 picks
# from Oct 21 and keeps today's picks as a change. In Cloud Shell:  bash ~/portfolio-leaderboard/tools/backdate_demo.sh
BUCKET="gs://opim5641-portfolio-f26"
for NETID in dww05002 zzz00002 zzz00003; do
  N=0
  for FILE in $(gcloud storage ls "${BUCKET}/submissions/${NETID}/" | sort); do
    N=$((N + 1))
    gcloud storage cat "${FILE}" \
      | sed -e "s/\"received_utc\": \"[^\"]*\"/\"received_utc\": \"2026-10-21T19:00:0${N}Z\"/" \
            -e "s/\"submission_id\": \"submissions\//\"submission_id\": \"backdated\/submissions\//" \
            -e "s/, started at the Nov 2 close)\"/, backdated by Dr. Dave to the Oct 21 close, for the demo)\"/" \
            -e "s/\"reason\": \"\([^\"(]*\)\"/\"reason\": \"\1 (backdated by Dr. Dave to the Oct 21 close, for the demo)\"/" \
      | gcloud storage cp - "${FILE}" --content-type=application/json >/dev/null
  done
  echo "✅ ${NETID}: ${N} entries now start at the Oct 21 close"
done
gcloud storage cp ~/portfolio-leaderboard/tools/example4_entry_oct21.json "${BUCKET}/submissions/zzz00004/2026-10-21T19-00-00Z_ex4.json" --content-type=application/json >/dev/null
gcloud storage cp ~/portfolio-leaderboard/tools/example4_entry.json "${BUCKET}/submissions/zzz00004/2026-11-04T16-08-34Z_ex4.json" --content-type=application/json >/dev/null
echo "✅ zzz00004: Oct 20 picks from Oct 21, today's picks as a change"
gcloud scheduler jobs run build-leaderboard-15min --location=us-central1 >/dev/null 2>&1 && echo "✅ rebuild started"
