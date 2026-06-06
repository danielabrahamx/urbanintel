import os

TARGET_CAMERA_ID = "JamCams_00001.07350"

POLL_INTERVAL_SECONDS = 180
ALERT_THRESHOLD = "medium"

# TfL API key - register free at https://api-portal.tfl.gov.uk
# Only app_key is needed; app_id was deprecated by TfL.
TFL_APP_KEY = os.environ.get("TFL_APP_KEY", "")
