# ============================================================================================================
# OPIM 5641 portfolio leaderboard: one-time setup. Paste into Cloud Shell, in the project opim5641-portfolio-f26.
# Takes about 5 minutes. Safe to re-run (every step skips what already exists). Re-run it to change the class code.
# ============================================================================================================
PROJECT_ID="opim5641-portfolio-f26"
REGION="us-central1"
CLASS_CODE="change-me"                         # <-- the code you write on the board (students type it to submit)
ENTRIES_BUCKET="${PROJECT_ID}"                 # PRIVATE: every entry ever made, prices, your class tables
PUBLIC_BUCKET="opim5641-leaderboard-f26"       # PUBLIC: the student leaderboard page (nicknames only)
BOARD_URL="https://storage.googleapis.com/${PUBLIC_BUCKET}/index.html"
APP_SA="leaderboard@${PROJECT_ID}.iam.gserviceaccount.com"
INVOKER_SA="leaderboard-invoker@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')

# (the job keeps its old name build-leaderboard-15min; it runs every 5 minutes)
# 1. Services
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com logging.googleapis.com \
  && echo "✅ 1. services on"

# 2. Two service accounts: 'leaderboard' runs both functions, 'leaderboard-invoker' starts the build every 15 minutes
gcloud iam service-accounts create leaderboard --display-name="Portfolio leaderboard (gatekeeper + builder)" 2>/dev/null || true
gcloud iam service-accounts create leaderboard-invoker --display-name="Starts the leaderboard build" 2>/dev/null || true
sleep 10
echo "✅ 2. service accounts"

# 3. The private entries bucket (only the leaderboard account and you can read it)
if ! gcloud storage buckets describe "gs://${ENTRIES_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${ENTRIES_BUCKET}" --location="${REGION}" --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets add-iam-policy-binding "gs://${ENTRIES_BUCKET}" \
  --member="serviceAccount:${APP_SA}" --role="roles/storage.objectAdmin" >/dev/null \
  && echo "✅ 3. private bucket gs://${ENTRIES_BUCKET}"

# 4. The public page bucket: readable by anyone, written only by the builder
if ! gcloud storage buckets describe "gs://${PUBLIC_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${PUBLIC_BUCKET}" --location="${REGION}" --uniform-bucket-level-access
fi
# anyone can open a file by its address, but nobody can LIST the bucket (so the private records/ links stay unknown)
gcloud storage buckets add-iam-policy-binding "gs://${PUBLIC_BUCKET}" --member="allUsers" --role="roles/storage.legacyObjectReader" >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://${PUBLIC_BUCKET}" \
  --member="serviceAccount:${APP_SA}" --role="roles/storage.objectAdmin" >/dev/null \
  && echo "✅ 4. public page: ${BOARD_URL}"

# 5. The gatekeeper (anyone can call it; it checks the Google sign-in and the class code itself)
rm -rf ~/portfolio-leaderboard && git clone -q https://github.com/drdave-teaching/portfolio-leaderboard.git ~/portfolio-leaderboard
gcloud functions deploy submit-portfolio --gen2 --region="${REGION}" --runtime=python312 \
  --source="${HOME}/portfolio-leaderboard/cloud_function/submit-portfolio" --entry-point=submit_http \
  --trigger-http --allow-unauthenticated --service-account="${APP_SA}" \
  --set-env-vars="ENTRIES_BUCKET=${ENTRIES_BUCKET},CLASS_CODE=${CLASS_CODE},BOARD_URL=${BOARD_URL}" \
  --memory=256Mi --timeout=60 --max-instances=10 --quiet \
  && echo "✅ 5. submit-portfolio deployed"

# 6. The builder (private), started every 5 minutes
gcloud functions deploy build-leaderboard --gen2 --region="${REGION}" --runtime=python312 \
  --source="${HOME}/portfolio-leaderboard/cloud_function/build-leaderboard" --entry-point=build_http \
  --trigger-http --no-allow-unauthenticated --service-account="${APP_SA}" \
  --set-env-vars="ENTRIES_BUCKET=${ENTRIES_BUCKET},PUBLIC_BUCKET=${PUBLIC_BUCKET}" \
  --memory=1Gi --timeout=540 --max-instances=1 --quiet \
  && echo "✅ 6. build-leaderboard deployed"

gcloud functions add-invoker-policy-binding build-leaderboard --gen2 --region="${REGION}" \
  --member="serviceAccount:${INVOKER_SA}" >/dev/null
gcloud iam service-accounts add-iam-policy-binding "${INVOKER_SA}" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" >/dev/null 2>&1 || true
URL=$(gcloud functions describe build-leaderboard --gen2 --region="${REGION}" --format='value(serviceConfig.uri)')
gcloud scheduler jobs create http build-leaderboard-15min --location="${REGION}" --schedule="*/5 * * * *" \
  --time-zone="America/New_York" --uri="${URL}" --http-method=POST \
  --oidc-service-account-email="${INVOKER_SA}" --oidc-token-audience="${URL}" >/dev/null 2>&1 \
|| gcloud scheduler jobs update http build-leaderboard-15min --location="${REGION}" --schedule="*/5 * * * *" \
  --time-zone="America/New_York" --uri="${URL}" --http-method=POST \
  --oidc-service-account-email="${INVOKER_SA}" --oidc-token-audience="${URL}" >/dev/null
gcloud scheduler jobs run build-leaderboard-15min --location="${REGION}" >/dev/null 2>&1 || true
echo "✅ 7. the page rebuilds every 5 minutes"

echo
echo "Gatekeeper (goes in the Studio 5 notebook):  $(gcloud functions describe submit-portfolio --gen2 --region=${REGION} --format='value(url)')"
echo "Class code:        ${CLASS_CODE}"
echo "Student page:      ${BOARD_URL}"
echo "Your private table: gcloud storage cat gs://${ENTRIES_BUCKET}/class/leaderboard_private.csv"
