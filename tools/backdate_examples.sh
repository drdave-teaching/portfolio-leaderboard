# Start Dr. Dave's two EXAMPLE funds (zzz00002, zzz00003) at the Nov 2, 2026 close instead of the Nov 3 close
# (Dr. Dave's call, Nov 3). Rewrites only their received time and notes it in their reason. In Cloud Shell:
#   bash ~/portfolio-leaderboard/tools/backdate_examples.sh
BUCKET="gs://opim5641-portfolio-f26"
for NETID in zzz00002 zzz00003; do
  for FILE in $(gcloud storage ls "${BUCKET}/submissions/${NETID}/"); do
    gcloud storage cat "${FILE}" \
      | sed -e 's/"received_utc": "[^"]*"/"received_utc": "2026-11-02T19:00:00Z"/' \
            -e 's/"reason": "first launch (an example fund from Dr. Dave)"/"reason": "first launch (an example fund from Dr. Dave, started at the Nov 2 close)"/' \
      | gcloud storage cp - "${FILE}" --content-type=application/json >/dev/null \
      && echo "✅ ${NETID}: now counts from the Nov 2 close"
  done
done
