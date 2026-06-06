"""
shared.incident_repository
==========================
Supabase persistence layer for incidents and camera status.

Design principles
-----------------
- All database interaction lives here. Callers pass plain Python dicts/scalars.
- Errors are raised, not silently swallowed. A failed write is a real problem;
  the caller decides whether to log and continue or abort.
- Input is validated before any network call: unknown severity values, empty
  camera IDs, etc. are caught here with clear messages.
- update_camera_status enforces a valid status transition set so callers can't
  accidentally write arbitrary strings into the status column.
- The Supabase client is injected, not constructed here, so callers (and tests)
  can supply a mock or None.

Typical usage
-------------
    from shared.incident_repository import IncidentRepository

    repo = IncidentRepository.from_env()   # None if creds absent
    if repo:
        repo.save(result, camera_id="JamCams_00001.07350", ...)
        repo.update_camera_status(camera_id=..., status="idle")
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Constants / validation sets
# ---------------------------------------------------------------------------

VALID_SEVERITIES: frozenset[str] = frozenset({"none", "low", "medium", "high", "critical"})

#: Allowed values for the camera_status.status column.
VALID_CAMERA_STATUSES: frozenset[str] = frozenset({"idle", "measuring", "error", "offline"})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RepositoryError(RuntimeError):
    """Raised when a database operation fails."""


class ValidationError(ValueError):
    """Raised when input to a repository method fails validation."""


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class IncidentRepository:
    """Persist incidents and camera status to Supabase.

    Parameters
    ----------
    supabase_client:
        An initialised ``supabase.Client`` instance. Pass ``None`` to create
        a no-op repository (all methods become no-ops, useful in dev/testing).
    """

    def __init__(self, supabase_client) -> None:
        self._client = supabase_client

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> Optional["IncidentRepository"]:
        """Construct from environment variables.

        Returns ``None`` (not an IncidentRepository instance) if either
        ``NEXT_PUBLIC_SUPABASE_URL`` or ``SUPABASE_SERVICE_ROLE_KEY`` is absent.
        That keeps callers simple: ``if repo: repo.save(...)``

        Raises
        ------
        RepositoryError
            If credentials are present but the Supabase client fails to initialise.
        """
        url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            return None

        try:
            from supabase import create_client  # type: ignore[import]
            client = create_client(url, key)
            return cls(client)
        except Exception as exc:
            raise RepositoryError(f"Supabase client init failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True when a live Supabase client is available."""
        return self._client is not None

    def save(
        self,
        analysis_result: dict,
        camera_id: str,
        camera_name: str,
        lat: Optional[float],
        lon: Optional[float],
        source: str = "gemini",
        video_url: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Optional[dict]:
        """Persist an analysis result to the ``incidents`` table.

        Parameters
        ----------
        analysis_result:
            Dict produced by a :class:`~shared.video_analyzer.BaseAnalyzer`.
            Must contain at minimum ``incident_detected`` (bool) and ``severity`` (str).
        camera_id:
            TfL JamCam identifier.
        camera_name:
            Human-readable camera name from TfL feed.
        lat:
            Camera latitude (may be None if TfL didn't provide it).
        lon:
            Camera longitude (may be None if TfL didn't provide it).
        source:
            Analyzer backend label, e.g. ``"gemini"`` or ``"openrouter"``.

        Raises
        ------
        ValidationError
            On bad input before any network call.
        RepositoryError
            If the Supabase insert fails.
        """
        if self._client is None:
            return None  # no-op when not configured

        self._validate_camera_id(camera_id)
        self._validate_analysis_result(analysis_result)

        row = {
            "camera_id": camera_id,
            "camera_name": camera_name or camera_id,
            "lat": lat,
            "lon": lon,
            "incident_detected": bool(analysis_result.get("incident_detected", False)),
            "severity": analysis_result.get("severity", "none"),
            "incidents": analysis_result.get("incidents", []),
            "scene_summary": analysis_result.get("scene_summary", ""),
            "reasoning": analysis_result.get("reasoning", ""),
            "raw_response": analysis_result,
            "source": source,
            "video_url": video_url,
            "created_by": created_by,
        }

        try:
            response = self._client.table("incidents").insert(row).execute()
            return response.data[0] if response.data else None
        except Exception as exc:
            raise RepositoryError(
                f"Failed to write incident for camera {camera_id!r}: {exc}"
            ) from exc

    def update_camera_status(
        self,
        camera_id: str,
        status: str,
        camera_name: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        video_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Upsert a row in the ``camera_status`` table.

        Uses ``on_conflict="camera_id"`` so a new row is inserted on first call
        and updated on subsequent calls.

        Parameters
        ----------
        camera_id:
            TfL JamCam identifier.
        status:
            One of ``"idle"``, ``"measuring"``, ``"error"``, ``"offline"``.
        camera_name:
            Optional - if supplied, updates the stored display name.
        lat / lon:
            Optional coordinate update.
        video_url:
            Optional - current video stream URL being processed.
        error_message:
            Optional - only meaningful when ``status="error"``.
            Truncated to 500 chars to avoid oversized payloads.

        Raises
        ------
        ValidationError
            If ``camera_id`` is empty or ``status`` is not a valid value.
        RepositoryError
            If the Supabase upsert fails.
        """
        if self._client is None:
            return  # no-op when not configured

        self._validate_camera_id(camera_id)
        self._validate_status(status)

        data: dict = {
            "camera_id": camera_id,
            "status": status,
            "last_polled_at": datetime.now().isoformat(),
        }
        if camera_name is not None:
            data["camera_name"] = camera_name
        if lat is not None:
            data["lat"] = lat
        if lon is not None:
            data["lon"] = lon
        if video_url is not None:
            data["video_url"] = video_url
        if error_message is not None:
            data["error_message"] = str(error_message)[:500]

        try:
            self._client.table("camera_status").upsert(
                data, on_conflict="camera_id"
            ).execute()
        except Exception as exc:
            raise RepositoryError(
                f"Failed to update camera status for {camera_id!r} -> {status!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_camera_id(camera_id: str) -> None:
        if not camera_id or not isinstance(camera_id, str):
            raise ValidationError("camera_id must be a non-empty string.")

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in VALID_CAMERA_STATUSES:
            raise ValidationError(
                f"status {status!r} is not valid. "
                f"Must be one of: {sorted(VALID_CAMERA_STATUSES)}"
            )

    @staticmethod
    def _validate_analysis_result(result: dict) -> None:
        if not isinstance(result, dict):
            raise ValidationError(
                f"analysis_result must be a dict, got {type(result).__name__}."
            )
        severity = result.get("severity", "none")
        if severity not in VALID_SEVERITIES:
            raise ValidationError(
                f"analysis_result.severity {severity!r} is not valid. "
                f"Must be one of: {sorted(VALID_SEVERITIES)}"
            )
