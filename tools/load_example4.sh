# Load Dr. Dave's example 4 (momentum 50/200 on example 3's stocks) straight into the private bucket. In Cloud Shell:
#   bash ~/portfolio-leaderboard/tools/load_example4.sh
gcloud storage cp ~/portfolio-leaderboard/tools/example4_entry.json \
  "gs://opim5641-portfolio-f26/submissions/zzz00004/2026-11-04T16-08-34Z_ex4.json" --content-type=application/json >/dev/null \
  && echo "✅ example 4 loaded"
