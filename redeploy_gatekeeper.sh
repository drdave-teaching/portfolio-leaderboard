# Redeploy only the gatekeeper after a code change, KEEPING the class code it already has (read from the live function).
# In Cloud Shell:  bash ~/portfolio-leaderboard/redeploy_gatekeeper.sh
PROJECT_ID="opim5641-portfolio-f26"
REGION="us-central1"
APP_SA="leaderboard@${PROJECT_ID}.iam.gserviceaccount.com"
BOARD_URL="https://storage.googleapis.com/opim5641-leaderboard-f26/index.html"

gcloud config set project "${PROJECT_ID}"
cd ~/portfolio-leaderboard && git pull -q
CLASS_CODE=$(gcloud functions describe submit-portfolio --gen2 --region="${REGION}" --format='value(serviceConfig.environmentVariables.CLASS_CODE)')
if [ -z "${CLASS_CODE}" ]; then
  echo "❌ could not read the current class code; nothing deployed (use setup_leaderboard.sh instead)"
else
  gcloud functions deploy submit-portfolio --gen2 --region="${REGION}" --runtime=python312 \
    --source="${HOME}/portfolio-leaderboard/cloud_function/submit-portfolio" --entry-point=submit_http \
    --trigger-http --allow-unauthenticated --service-account="${APP_SA}" \
    --set-env-vars="ENTRIES_BUCKET=${PROJECT_ID},CLASS_CODE=${CLASS_CODE},BOARD_URL=${BOARD_URL}" \
    --memory=256Mi --timeout=60 --max-instances=10 --quiet >/dev/null \
    && echo "✅ submit-portfolio redeployed (class code unchanged)"
fi
