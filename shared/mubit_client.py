"""
shared.mubit_client
===================
Optional MuBit memory wrapper. Completely silent when the SDK is not installed
or the API key is missing. All methods are fire-and-forget: errors are caught
and swallowed so MuBit can never break the analysis pipeline.

Usage
-----
    from shared.mubit_client import MubitMemory

    mubit = MubitMemory(project_id="proj-...")
    context = mubit.recall_camera_context("JamCams_00001.07350")
    mubit.remember_incident("JamCams_00001.07350", result, source="tfl")
"""

from __future__ import annotations

import os
from typing import Optional


class MubitMemory:
    """Optional MuBit agent-memory wrapper.

    If ``MUBIT_API_KEY`` is absent or the ``mubit`` package is not installed,
    every call becomes a no-op. The class never raises.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        self._client: Optional[object] = None
        self._project_id = project_id

        key = api_key or os.environ.get("MUBIT_API_KEY")
        if not key:
            return

        try:
            import mubit  # type: ignore[import]

            url = endpoint or os.environ.get("MUBIT_ENDPOINT", "https://api.mubit.ai")
            client = mubit.Client(endpoint=url)
            client.set_api_key(key)
            self._client = client
        except Exception:
            self._client = None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall_camera_context(self, camera_id: str) -> str:
        """Return a memory-context paragraph for *camera_id*, or ``""``.

        The string is designed to be prepended to the vision-model prompt.
        """
        if not self._client or not camera_id:
            return ""

        try:
            result = self._client.recall(
                session_id=f"urbanintel:{camera_id}",
                agent_id="urbanintel-monitor",
                query=f"What past incidents or patterns have been observed at camera {camera_id}?",
                entry_types=["lesson", "fact"],
            )
            answer = result.get("final_answer", "")
            # MuBit returns a stock sentence when nothing is found.
            if answer and "no relevant" not in answer.lower():
                return (
                    f"\nHISTORICAL CONTEXT FOR THIS CAMERA:\n"
                    f"{answer}\n"
                    f"Use this history when assessing severity and incident patterns.\n"
                )
        except Exception:
            pass

        return ""

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def remember_incident(
        self,
        camera_id: str,
        result: dict,
        source: str = "tfl",
    ) -> None:
        """Store an incident analysis in MuBit. Fire-and-forget."""
        if not self._client or not camera_id:
            return

        try:
            severity = result.get("severity", "none")
            detected = result.get("incident_detected", False)
            scene = result.get("scene_summary", "")
            incidents = result.get("incidents", [])

            content = (
                f"Camera {camera_id} ({source}): incident_detected={detected}, "
                f"severity={severity}. Scene: {scene}"
            )
            if incidents:
                content += f". Total incidents: {len(incidents)}."
                for inc in incidents[:3]:
                    desc = inc.get("description", "")[:120]
                    content += f" [{inc.get('type')}: {desc}]"

            self._client.remember(
                session_id=f"urbanintel:{camera_id}",
                agent_id="urbanintel-monitor",
                content=content,
                intent="lesson",
                lesson_scope="global",
            )
        except Exception:
            pass
