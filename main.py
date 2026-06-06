import json
import os
import sys
import tempfile
import time
import warnings
from datetime import datetime

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import google.generativeai as genai

import requests
from dotenv import load_dotenv

from config import (
    ALERT_THRESHOLD,
    POLL_INTERVAL_SECONDS,
    TARGET_CAMERA_ID,
    TFL_APP_ID,
    TFL_APP_KEY,
    VISION_MODEL,
)

SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_EMOJI = {
    "none": "[OK]",
    "low": "[!]",
    "medium": "[*]",
    "high": "[**]",
    "critical": "[!!!]",
}

TFL_API = "https://api.tfl.gov.uk/Place/Type/JamCam"


def get_camera_video_url(camera_id: str) -> tuple[str, str]:
    """
    Fetch the camera list from TfL and return (video_url, camera_name).
    Re-fetches every poll because TfL can rotate JamCam URLs.
    """
    params = {}
    if TFL_APP_ID:
        params["app_id"] = TFL_APP_ID
    if TFL_APP_KEY:
        params["app_key"] = TFL_APP_KEY

    resp = requests.get(TFL_API, params=params, timeout=15)
    resp.raise_for_status()
    cameras = resp.json()

    for cam in cameras:
        if cam.get("id") != camera_id:
            continue

        name = cam.get("commonName", camera_id)
        for prop in cam.get("additionalProperties", []):
            if prop.get("key") == "videoUrl":
                return prop["value"], name

    raise ValueError(f"Camera {camera_id} not found or has no videoUrl")


def download_video(video_url: str) -> str:
    """
    Download the MP4 to a temporary file and return its path.
    Caller is responsible for deleting it.
    """
    resp = requests.get(video_url, timeout=30)
    resp.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.write(resp.content)
    tmp.close()
    return tmp.name


ANALYSIS_PROMPT = """You are an automated road safety system watching a 10-second clip
from a fixed TfL traffic camera at a London road junction.

Your job: detect dangerous driving behaviour and near-miss incidents from vehicle and
pedestrian movement patterns. Resolution is low — you cannot and must not attempt to
identify faces, individuals, or number plates.

Dangerous events to flag:
- NEAR_MISS: vehicle comes dangerously close to a pedestrian or another vehicle
- RED_LIGHT_VIOLATION: vehicle clearly runs a red light
- WRONG_WAY: vehicle moving against traffic flow
- DANGEROUS_OVERTAKE: unsafe overtaking manoeuvre
- PEDESTRIAN_IN_ROAD: person in the carriageway in danger
- VEHICLE_STOPPED_DANGEROUSLY: vehicle stopped in a live lane, junction box, or crossroads
- AGGRESSIVE_DRIVING: sudden swerving or obvious tailgating
- CYCLIST_RISK: cyclist in dangerous proximity to a larger vehicle

Only flag what you can clearly observe. If in doubt, do not flag.
When in doubt, return incident_detected: false. A false negative is better than a false positive.

Respond ONLY with this JSON — no preamble, no markdown, no explanation outside it:
{
  "incident_detected": true | false,
  "severity": "none" | "low" | "medium" | "high" | "critical",
  "incidents": [
    {
      "type": "<one of the event types above>",
      "severity": "low" | "medium" | "high" | "critical",
      "description": "<1-2 sentences describing exactly what you see>",
      "confidence": "low" | "medium" | "high",
      "timestamp_in_clip": "<approximate time in clip e.g. '0:04'>"
    }
  ],
  "scene_summary": "<one sentence describing overall traffic conditions>",
  "reasoning": "<one sentence explaining why you did or did not flag an incident>"
}"""


def analyse_video(video_path: str) -> dict:
    """
    Upload video to Gemini Files API, analyse it, delete it, and return parsed JSON.
    """
    uploaded_file = None
    try:
        print("  Uploading to Gemini...", end=" ", flush=True)
        uploaded_file = genai.upload_file(video_path, mime_type="video/mp4")

        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            raise RuntimeError(
                f"File processing failed: state={uploaded_file.state.name}"
            )

        print("done")

        print("  Analysing...", end=" ", flush=True)
        model = genai.GenerativeModel(VISION_MODEL)
        response = model.generate_content(
            [uploaded_file, ANALYSIS_PROMPT],
            generation_config={"response_mime_type": "application/json"},
        )
        print("done")

        return json.loads(response.text)

    finally:
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
                pass


def print_result(result: dict, camera_name: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    severity = result.get("severity", "none")
    emoji = SEVERITY_EMOJI.get(severity, "[!]")

    if not result.get("incident_detected"):
        scene = result.get("scene_summary", "")
        print(f"[{ts}] {emoji}  {camera_name} — Clear  |  {scene}")
        return

    if SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK.get(ALERT_THRESHOLD, 2):
        print(f"[{ts}] [watch] {camera_name} — Activity below threshold ({severity})")
        return

    print(f"\n{'=' * 65}")
    print(f"[{ts}] {emoji}  INCIDENT — {camera_name}")
    print(f"  Severity : {severity.upper()}")
    print(f"  Scene    : {result.get('scene_summary', '')}")
    print(f"  Reasoning: {result.get('reasoning', '')}")
    for inc in result.get("incidents", []):
        incident_type = inc.get("type", "UNKNOWN")
        timestamp = inc.get("timestamp_in_clip", "?")
        description = inc.get("description", "")
        confidence = inc.get("confidence", "?")
        print(
            f"  → [{incident_type}] @ {timestamp}  "
            f"{description}  (confidence: {confidence})"
        )
    print(f"{'=' * 65}\n")


def main() -> None:
    load_dotenv()

    if not TARGET_CAMERA_ID:
        print("ERROR: Set TARGET_CAMERA_ID in config.py before running.")
        print("Tip: run list_cameras.py to find a camera with a videoUrl.")
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: Set the GEMINI_API_KEY environment variable.")
        sys.exit(1)

    genai.configure(api_key=api_key)

    print("Urban Intelligence Agent")
    print(f"   Camera : {TARGET_CAMERA_ID}")
    print(f"   Model  : {VISION_MODEL}")
    print(f"   Poll   : every {POLL_INTERVAL_SECONDS}s")
    print(f"   Alerts : {ALERT_THRESHOLD}+ severity")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    poll = 0
    while True:
        poll += 1
        print(f"[Poll #{poll}]")

        video_path = None
        try:
            print("  Fetching video URL from TfL...", end=" ", flush=True)
            video_url, camera_name = get_camera_video_url(TARGET_CAMERA_ID)
            print(f"done ({camera_name})")

            print("  Downloading video...", end=" ", flush=True)
            video_path = download_video(video_url)
            size_kb = os.path.getsize(video_path) // 1024
            print(f"done ({size_kb}KB)")

            result = analyse_video(video_path)
            print_result(result, camera_name)

        except Exception as exc:
            print(f"  ERROR: {exc}")

        finally:
            if video_path and os.path.exists(video_path):
                os.unlink(video_path)

        print(f"  Sleeping {POLL_INTERVAL_SECONDS}s...\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
