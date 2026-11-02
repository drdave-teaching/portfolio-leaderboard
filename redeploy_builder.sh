# Redeploy only the leaderboard builder after a code change (the gatekeeper and its class code are not touched).
# In Cloud Shell:  bash ~/portfolio-leaderboard/redeploy_builder.sh
# The featured (live) fund is one NetID in the private bucket, set once:
#   echo NETID | gcloud storage cp - gs://opim5641-portfolio-f26/config/featured.txt
PROJECT_ID="opim5641-portfolio-f26"
REGION="us-central1"
APP_SA="leaderboard@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}"
cd ~/portfolio-leaderboard && git pull -q
gcloud functions deploy build-leaderboard --gen2 --region="${REGION}" --runtime=python312 \
  --source="${HOME}/portfolio-leaderboard/cloud_function/build-leaderboard" --entry-point=build_http \
  --trigger-http --no-allow-unauthenticated --service-account="${APP_SA}" \
  --set-env-vars="ENTRIES_BUCKET=${PROJECT_ID},PUBLIC_BUCKET=opim5641-leaderboard-f26" \
  --memory=1Gi --timeout=540 --max-instances=1 --quiet \
  && echo "✅ build-leaderboard redeployed"
gcloud scheduler jobs update http build-leaderboard-15min --location="${REGION}" --schedule="*/5 * * * *" >/dev/null   && echo "✅ the page rebuilds every 5 minutes"
gcloud scheduler jobs run build-leaderboard-15min --location="${REGION}" >/dev/null 2>&1 \
  && echo "✅ rebuild started (the page updates in about a minute)"
