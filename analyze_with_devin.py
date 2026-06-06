"""Analyze JamCam using Devin's vision - no API costs."""
import os
import sys
import tempfile
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

from config import POLL_INTERVAL_SECONDS, TARGET_CAMERA_ID, TFL_APP_ID, TFL_APP_KEY, get_config

# Use centralized config for API URL
_cfg = get_config()
TFL_API = _cfg.tfl_api_url


def get_camera_urls(camera_id: str) -> tuple[str, str, str]:
    """Fetch camera and return (image_url, video_url, camera_name)."""
    cfg = get_config()
    params = {}
    if cfg.tfl_app_id:
        params["app_id"] = cfg.tfl_app_id
    if cfg.tfl_app_key:
        params["app_key"] = cfg.tfl_app_key

    resp = requests.get(cfg.tfl_api_url, params=params, timeout=15)
    resp.raise_for_status()
    cameras = resp.json()

    for cam in cameras:
        if cam.get("id") != camera_id:
            continue

        name = cam.get("commonName", camera_id)
        image_url = None
        video_url = None

        for prop in cam.get("additionalProperties", []):
            if prop.get("key") == "imageUrl":
                image_url = prop["value"]
            if prop.get("key") == "videoUrl":
                video_url = prop["value"]

        return image_url, video_url, name

    raise ValueError(f"Camera {camera_id} not found")


def download_image(image_url: str) -> str:
    """Download JPG to temp file, return path."""
    resp = requests.get(image_url, timeout=30)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(resp.content)
    tmp.close()
    return tmp.name


def main() -> None:
    load_dotenv()
    # Reload config after dotenv loads
    cfg = get_config()

    if not cfg.target_camera_id:
        print("ERROR: Set TARGET_CAMERA_ID in config")
        sys.exit(1)

    print("Urban Intelligence Agent (Devin Vision Mode)")
    print(f"   Camera: {cfg.target_camera_id}")
    print(f"   Poll: every {cfg.poll_interval_seconds}s")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    poll = 0
    while True:
        poll += 1
        print(f"[Poll #{poll}]")

        image_path = None
        try:
            print("  Fetching camera URLs...", end=" ", flush=True)
            image_url, video_url, camera_name = get_camera_urls(cfg.target_camera_id)
            print(f"done ({camera_name})")

            if not image_url:
                print("  ERROR: No image URL available")
                continue

            print("  Downloading image...", end=" ", flush=True)
            image_path = download_image(image_url)
            size_kb = os.path.getsize(image_path) // 1024
            print(f"done ({size_kb}KB)")

            # Save to project folder for Devin analysis
            analysis_dir = os.path.join(os.path.dirname(__file__), "analysis_frames")
            os.makedirs(analysis_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_path = os.path.join(analysis_dir, f"frame_{timestamp}.jpg")
            os.rename(image_path, saved_path)
            image_path = saved_path

            print(f"\n  === IMAGE READY FOR DEVIN ANALYSIS ===")
            print(f"  Path: {image_path}")
            print(f"  Camera: {camera_name}")
            print(f"  \n  (Devin: Read this image and analyze for traffic incidents)")
            print(f"  ========================================\n")

        except Exception as exc:
            print(f"  ERROR: {exc}")
            import traceback
            traceback.print_exc()

        finally:
            if image_path and os.path.exists(image_path):
                os.unlink(image_path)

        print(f"  Sleeping {cfg.poll_interval_seconds}s...\n")
        time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    main()
