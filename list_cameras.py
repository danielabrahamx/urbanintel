"""
Run once to find central London TfL JamCams with a downloadable videoUrl.
"""

import requests
from dotenv import load_dotenv

load_dotenv()

from config import TFL_APP_KEY, get_config  # noqa: E402

# Use centralized config for API URL
_cfg = get_config()
TFL_API = _cfg.tfl_api_url


def main() -> None:
    cfg = get_config()

    params = {}
    if cfg.tfl_app_key:
        params["app_key"] = cfg.tfl_app_key

    resp = requests.get(cfg.tfl_api_url, params=params, timeout=15)
    resp.raise_for_status()
    cameras = resp.json()

    results = []
    for cam in cameras:
        lat = cam.get("lat", 0)
        lon = cam.get("lon", 0)
        if not (51.48 < lat < 51.54 and -0.15 < lon < -0.05):
            continue

        video_url = next(
            (
                prop["value"]
                for prop in cam.get("additionalProperties", [])
                if prop.get("key") == "videoUrl"
            ),
            None,
        )
        if video_url:
            results.append(
                (cam["id"], cam.get("commonName", "?"), lat, lon, video_url)
            )

    print(f"Found {len(results)} central London cameras with videoUrl:\n")
    for cam_id, name, lat, lon, url in results[:25]:
        print(f"  {cam_id}")
        print(f"  {name}  ({lat:.4f}, {lon:.4f})")
        print(f"  {url}")
        print()


if __name__ == "__main__":
    main()
