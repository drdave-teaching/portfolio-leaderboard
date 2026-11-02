# A one-cell smoke test of the gatekeeper from Colab (Dr. Dave's side). In a Colab cell:
#   code = 'the class code'
#   !wget -q -O colab_test_submit.py https://raw.githubusercontent.com/drdave-teaching/portfolio-leaderboard/main/tools/colab_test_submit.py
#   exec(open('colab_test_submit.py').read())
# It submits a TEST entry (NetID tst00001). Delete it afterwards:
#   gcloud storage rm "gs://opim5641-portfolio-f26/submissions/tst00001/**"
import json

import google.auth
import google.auth.transport.requests
import requests
from google.colab import auth

auth.authenticate_user()
credentials, _ = google.auth.default()
credentials.refresh(google.auth.transport.requests.Request())
entry = {
    "netid": "tst00001",
    "nickname": "TEST entry (delete me)",
    "theme": "smoke test",
    "reason": "testing the gatekeeper",
    "class_code": code,
    "portfolios": {"no_rules": {"NVDA": 0.6, "LLY": 0.4},
                   "with_rules": {"NVDA": 0.25, "LLY": 0.25, "XOM": 0.25, "WMT": 0.25}},
    "notebook": "smoke-test",
}
answer = requests.post("https://us-central1-opim5641-portfolio-f26.cloudfunctions.net/submit-portfolio",
                       data=json.dumps(entry), timeout=60,
                       headers={"Authorization": "Bearer " + credentials.token, "Content-Type": "application/json"})
print(answer.status_code, answer.text)
