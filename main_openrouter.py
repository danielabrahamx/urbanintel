"""Urban Intelligence Agent - OpenRouter backend (minimax/minimax-m3 with full video input)."""

import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from config import (
    ALERT_THRESHOLD,
    POLL_INTERVAL_SECONDS,
    TARGET_CAMERA_ID,
)

from shared.config_loader import load_config
from shared.tfl_client import TflClient, TFL_API  # noqa: F401 - TFL_API kept for api_server compat
from shared.video_analyzer import (
    OpenRouterAnalyzer,
    download_video,
    SEVERITY_RANK,
    SEVERITY_EMOJI,
)
from shared.incident_repository import IncidentRepository

# ---------------------------------------------------------------------------
# Module-level constants still referenced by api_server.py imports
# ---------------------------------------------------------------------------

#: The OpenRouter model in use - kept here so api_server health check can report it.
VISION_MODEL = "minimax/minimax-m3"

#: Convenience re-export so callers that do `from main_openrouter import TFL_APP_KEY`
#: continue to work without changes.
TFL_APP_KEY = os.environ.get("TFL_APP_KEY", "")


# ---------------------------------------------------------------------------
# Backward-compat shim: api_server.py calls analyze_video(path, api_key)
# ---------------------------------------------------------------------------

def analyze_video(video_path: str, api_key: str) -> dict:
    """Thin wrapper kept for api_server.py backward compatibility.

    New code should instantiate OpenRouterAnalyzer directly.
    """
    analyzer = OpenRouterAnalyzer(api_key=api_key, model=VISION_MODEL)
    return analyzer.analyze(video_path)


# Backward-compat shim: api_server.py also imports get_camera_video_url
def get_camera_video_url(camera_id: str):
    """Thin wrapper kept for api_server.py backward compatibility."""
    tfl = TflClient(app_key=TFL_APP_KEY)
    return tfl.get_camera_video_url(camera_id)


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
        print(
            f"  -> [{inc.get('type', 'UNKNOWN')}] {inc.get('description', '')} "
            f"(confidence: {inc.get('confidence', '?')})"
        )
    print(f"{'=' * 65}\n")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    if not TARGET_CAMERA_ID:
        print("ERROR: Set TARGET_CAMERA_ID in config.py before running.")
        sys.exit(1)

    cfg = load_config(require_openrouter=True)
    api_key = cfg.require_openrouter_key()

    analyzer = OpenRouterAnalyzer(api_key=api_key, model=VISION_MODEL)
    tfl = TflClient(app_key=cfg.tfl_app_key)

    repo = IncidentRepository.from_env()
    if repo and repo.is_connected:
        print("   DB     : Supabase connected")
    else:
        print(
            "   DB     : not configured "
            "(set NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env)"
        )

    print("Urban Intelligence - OpenRouter watcher")
    print(f"   Camera : {TARGET_CAMERA_ID}")
    print(f"   Model  : {VISION_MODEL}")
    print(f"   Poll   : every {POLL_INTERVAL_SECONDS}s")
    print(f"   Alerts : {ALERT_THRESHOLD}+ severity")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    poll = 0
    camera_name_cache: str | None = None
    lat_cache: float | None = None
    lon_cache: float | None = None

    while True:
        poll += 1
        print(f"[Poll #{poll}]")

        video_path = None
        try:
            print("  Fetching video URL from TfL...", end=" ", flush=True)
            video_url, camera_name, lat, lon = tfl.get_camera_video_url(TARGET_CAMERA_ID)
            camera_name_cache, lat_cache, lon_cache = camera_name, lat, lon
            print(f"done ({camera_name})")

            if repo:
                try:
                    repo.update_camera_status(
                        camera_id=TARGET_CAMERA_ID,
                        status="measuring",
                        camera_name=camera_name,
                        lat=lat,
                        lon=lon,
                        video_url=video_url,
                    )
                except Exception as db_exc:
                    print(f"  [warn] Camera status update failed: {db_exc}")

            print("  Downloading video...", end=" ", flush=True)
            video_path = download_video(video_url)
            size_kb = os.path.getsize(video_path) // 1024
            print(f"done ({size_kb} KB)")

            result = analyzer.analyze(video_path)
            print_result(result, camera_name)

            if repo:
                try:
                    repo.save(
                        result, TARGET_CAMERA_ID, camera_name, lat, lon, source="openrouter"
                    )
                    repo.update_camera_status(
                        camera_id=TARGET_CAMERA_ID,
                        status="idle",
                        camera_name=camera_name,
                        lat=lat,
                        lon=lon,
                        video_url=video_url,
                    )
                except Exception as db_exc:
                    print(f"  [warn] DB operation failed: {db_exc}")

        except Exception as exc:
            print(f"  ERROR: {exc}")
            if repo and camera_name_cache:
                try:
                    repo.update_camera_status(
                        camera_id=TARGET_CAMERA_ID,
                        status="error",
                        camera_name=camera_name_cache,
                        lat=lat_cache,
                        lon=lon_cache,
                        error_message=str(exc)[:200],
                    )
                except Exception as db_exc:
                    print(f"  [warn] Error status update failed: {db_exc}")

        finally:
            if video_path and os.path.exists(video_path):
                os.unlink(video_path)

        print(f"  Sleeping {POLL_INTERVAL_SECONDS}s...\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
