"""
shared.tfl_client
=================
TfL Unified API wrapper for JamCam data.

Design principles
-----------------
- Single TFL_API constant used across the whole project.
- Input validation before any network call (camera_id format, non-empty strings).
- Automatic retry with exponential back-off on transient HTTP errors.
- Clear exceptions: ValueError for bad input, TflApiError for API failures,
  CameraNotFoundError when a camera ID is absent from the feed.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TFL_API = "https://api.tfl.gov.uk/Place/Type/JamCam"

#: Camera IDs always start with "JamCams_" according to TfL's naming scheme.
_CAMERA_ID_PREFIX = "JamCams_"

#: HTTP status codes worth retrying (server-side transient errors).
_RETRY_STATUSES = {429, 500, 502, 503, 504}

#: Default retry policy: 3 attempts with 2s, 4s back-off.
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 2.0  # seconds


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TflApiError(RuntimeError):
    """Raised when the TfL API returns an unexpected response."""


class CameraNotFoundError(ValueError):
    """Raised when the requested camera ID is absent from the TfL feed."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TflClient:
    """Thin wrapper around the TfL Unified API JamCam endpoint.

    Parameters
    ----------
    app_key:
        TfL primary API key. Pass an empty string for anonymous access
        (lower rate limit - fine for development).
    max_retries:
        Number of retry attempts on transient failures (default 3).
    backoff_base:
        Base seconds for exponential back-off between retries (default 2.0).
    timeout:
        HTTP request timeout in seconds (default 15).
    """

    def __init__(
        self,
        app_key: str = "",
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        timeout: int = 15,
    ) -> None:
        self._app_key = app_key
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_camera_video_url(
        self, camera_id: str
    ) -> tuple[str, str, Optional[float], Optional[float]]:
        """Fetch live camera data and return the video stream details.

        TfL rotates JamCam video URLs, so call this every polling cycle rather
        than caching the URL.

        Parameters
        ----------
        camera_id:
            TfL JamCam identifier, e.g. "JamCams_00001.07350".

        Returns
        -------
        tuple[str, str, float | None, float | None]
            ``(video_url, camera_name, latitude, longitude)``

        Raises
        ------
        ValueError
            If ``camera_id`` is empty or obviously malformed.
        CameraNotFoundError
            If the camera ID is not in the current TfL feed, or the camera
            entry has no ``videoUrl`` property.
        TflApiError
            On non-recoverable HTTP errors from the TfL API.
        """
        self._validate_camera_id(camera_id)
        cameras = self._fetch_cameras()

        for cam in cameras:
            if cam.get("id") != camera_id:
                continue

            name: str = cam.get("commonName") or camera_id
            lat: Optional[float] = cam.get("lat")
            lon: Optional[float] = cam.get("lon")

            for prop in cam.get("additionalProperties", []):
                if prop.get("key") == "videoUrl":
                    url: str = prop["value"]
                    if not url:
                        raise CameraNotFoundError(
                            f"Camera {camera_id!r} has an empty videoUrl - "
                            "it may be offline."
                        )
                    return url, name, lat, lon

            raise CameraNotFoundError(
                f"Camera {camera_id!r} found in feed but has no videoUrl property. "
                "It may be temporarily offline."
            )

        raise CameraNotFoundError(
            f"Camera {camera_id!r} not found in TfL feed. "
            "Run list_cameras.py to see available IDs."
        )

    def list_cameras(self) -> list[dict]:
        """Return the raw list of all JamCam entries from TfL.

        Useful for discovering available camera IDs (see list_cameras.py).
        """
        return self._fetch_cameras()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_camera_id(camera_id: str) -> None:
        """Raise ValueError early if camera_id is clearly wrong."""
        if not camera_id or not isinstance(camera_id, str):
            raise ValueError("camera_id must be a non-empty string.")
        if not camera_id.startswith(_CAMERA_ID_PREFIX):
            raise ValueError(
                f"camera_id {camera_id!r} looks invalid - "
                f"expected it to start with {_CAMERA_ID_PREFIX!r}."
            )

    def _build_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self._app_key:
            params["app_key"] = self._app_key
        return params

    def _fetch_cameras(self) -> list[dict]:
        """GET the JamCam list with retry/back-off."""
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = requests.get(
                    TFL_API,
                    params=self._build_params(),
                    timeout=self._timeout,
                )

                if resp.status_code in _RETRY_STATUSES:
                    raise requests.HTTPError(
                        f"TfL API returned {resp.status_code}", response=resp
                    )

                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, list):
                    raise TflApiError(
                        f"Expected a JSON array from TfL API, got {type(data).__name__}. "
                        f"Response snippet: {resp.text[:200]}"
                    )

                return data

            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    wait = self._backoff_base ** attempt
                    print(
                        f"  [tfl] Attempt {attempt}/{self._max_retries} failed "
                        f"({exc}). Retrying in {wait:.0f}s..."
                    )
                    time.sleep(wait)

        raise TflApiError(
            f"TfL API unreachable after {self._max_retries} attempts. "
            f"Last error: {last_exc}"
        ) from last_exc
