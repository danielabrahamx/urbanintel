"""Urban Intelligence Agent - Gemini backend.

Polls a single TfL JamCam, downloads the latest clip, sends it to Gemini for
incident analysis, prints results, and persists to Supabase.
"""

import os
import sys
import time
import warnings
from datetime import datetime

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import google.generativeai as genai  # noqa: F401 - SDK configured via GeminiAnalyzer

from dotenv import load_dotenv

from config import (
    ALERT_THRESHOLD,
    POLL_INTERVAL_SECONDS,
    TARGET_CAMERA_ID,
    VISION_MODEL,
)

from shared.config_loader import load_config
from shared.tfl_client import TflClient, TFL_API  # noqa: F401 - TFL_API re-exported for eval.py
from shared.video_analyzer import (
    GeminiAnalyzer,
    download_video,
    ANALYSIS_PROMPT,  # noqa: F401 - re-exported for eval.py
    SEVERITY_RANK,
    SEVERITY_EMOJI,
)
from shared.incident_repository import IncidentRepository


# ---------------------------------------------------------------------------
# Display helper
# ---------------------------------------------------------------------------

def print_result(result: dict, camera_name: str) -> None:
    """Print a formatted summary of an analysis result to stdout."""
    ts = datetime.now().strftime("%H:%M:%S")
    severity = result.get("severity", "none")
    emoji = SEVERITY_EMOJI.get(severity, "[!]")

    if not result.get("incident_detected"):
        scene = result.get("scene_summary", "")
        print(f"[{ts}] {emoji}  {camera_name} - Clear  |  {scene}")
        return

    if SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK.get(ALERT_THRESHOLD, 2):
        print(f"[{ts}] [watch] {camera_name} - Activity below threshold ({severity})")
        return

    print(f"\n{'=' * 65}")
    print(f"[{ts}] {emoji}  INCIDENT - {camera_name}")
    print(f"  Severity : {severity.upper()}")
    print(f"  Scene    : {result.get('scene_summary', '')}")
    print(f"  Reasoning: {result.get('reasoning', '')}")
    for inc in result.get("incidents", []):
        incident_type = inc.get("type", "UNKNOWN")
        timestamp = inc.get("timestamp_in_clip", "?")
        description = inc.get("description", "")
        confidence = inc.get("confidence", "?")
        print(
            f"  -> [{incident_type}] @ {timestamp}  "
            f"{description}  (confidence: {confidence})"
        )
    print(f"{'=' * 65}\n")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    if not TARGET_CAMERA_ID:
        print("ERROR: Set TARGET_CAMERA_ID in config.py before running.")
        print("Tip: run list_cameras.py to find a camera with a videoUrl.")
        sys.exit(1)

    cfg = load_config(require_gemini=True)

    analyzer = GeminiAnalyzer(api_key=cfg.require_gemini_key(), model=VISION_MODEL)
    tfl = TflClient(app_key=cfg.tfl_app_key)

    repo = IncidentRepository.from_env()
    if repo and repo.is_connected:
        print("   DB     : Supabase connected")
    else:
        print(
            "   DB     : not configured "
            "(set NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)"
        )

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
            video_url, camera_name, lat, lon = tfl.get_camera_video_url(TARGET_CAMERA_ID)
            print(f"done ({camera_name})")

            print("  Downloading video...", end=" ", flush=True)
            video_path = download_video(video_url)
            size_kb = os.path.getsize(video_path) // 1024
            print(f"done ({size_kb}KB)")

            result = analyzer.analyze(video_path)
            print_result(result, camera_name)

            if repo:
                try:
                    repo.save(result, TARGET_CAMERA_ID, camera_name, lat, lon, source="gemini")
                except Exception as db_exc:
                    print(f"  [warn] DB write failed: {db_exc}")

        except Exception as exc:
            print(f"  ERROR: {exc}")

        finally:
            if video_path and os.path.exists(video_path):
                os.unlink(video_path)

        print(f"  Sleeping {POLL_INTERVAL_SECONDS}s...\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
