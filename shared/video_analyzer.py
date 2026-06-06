"""
shared.video_analyzer
=====================
Abstract analyzer interface plus concrete Gemini and OpenRouter implementations.

Architecture
------------

                    BaseAnalyzer (ABC)
                    .analyze(video_path) -> dict
                          |
          +---------------+----------------+
          |                                |
    GeminiAnalyzer                 OpenRouterAnalyzer
    Uses Gemini Files API          Base64-encodes the MP4 and
    (upload -> poll -> infer        sends to OpenRouter chat
    -> delete lifecycle)            completions endpoint

Both implementations share:
- The same ANALYSIS_PROMPT
- The same output schema (incident_detected, severity, incidents, ...)
- The download_video() utility (separate from analysis - caller's responsibility)

Usage
-----
    from shared.video_analyzer import GeminiAnalyzer, OpenRouterAnalyzer, download_video

    path = download_video(video_url)
    try:
        analyzer = GeminiAnalyzer(api_key="...")
        result = analyzer.analyze(path)
    finally:
        os.unlink(path)
"""

from __future__ import annotations

import abc
import base64
import json
import tempfile
import time
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

#: All valid incident type strings the model may return.
VALID_INCIDENT_TYPES: frozenset[str] = frozenset({
    "NEAR_MISS",
    "RED_LIGHT_VIOLATION",
    "WRONG_WAY",
    "DANGEROUS_OVERTAKE",
    "PEDESTRIAN_IN_ROAD",
    "VEHICLE_STOPPED_DANGEROUSLY",
    "AGGRESSIVE_DRIVING",
    "CYCLIST_RISK",
})

SEVERITY_RANK: dict[str, int] = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

SEVERITY_EMOJI: dict[str, str] = {
    "none": "[OK]",
    "low": "[!]",
    "medium": "[*]",
    "high": "[**]",
    "critical": "[!!!]",
}

#: Shared definition of the dangerous events the model must spot, plus
#: detailed visual cues so the model knows *what each one looks like* rather
#: than just its name.
_EVENT_TAXONOMY: str = """Dangerous events to flag (use the exact type string):
- NEAR_MISS: two road users (vehicle/vehicle, vehicle/pedestrian, vehicle/cyclist)
  come close enough that a collision was narrowly avoided. Visual cues: hard braking,
  sudden swerve to avoid, one party stopping abruptly, paths crossing with little gap,
  brake lights flaring just before contact would have happened.
- RED_LIGHT_VIOLATION: a vehicle crosses the stop line / enters the junction while its
  signal is red. Cue: red light visible AND vehicle continues through.
- WRONG_WAY: vehicle travelling against the established direction of traffic flow.
- DANGEROUS_OVERTAKE: overtaking into oncoming traffic, across solid lines, or with
  insufficient clearance.
- PEDESTRIAN_IN_ROAD: a person in the live carriageway exposed to moving traffic
  (not on a pavement or a green-man crossing).
- VEHICLE_STOPPED_DANGEROUSLY: vehicle stationary in a live lane, junction box,
  crossing, or blocking traffic where it should not be.
- AGGRESSIVE_DRIVING: sudden swerving, weaving, or obvious tailgating.
- CYCLIST_RISK: cyclist squeezed by, undertaking, or in the blind spot of a larger
  vehicle (bus, lorry, van) at close range."""

_JSON_SCHEMA: str = """Respond ONLY with this JSON - no preamble, no markdown, no explanation outside it:
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
}

Set incident_detected to true whenever the incidents array is non-empty, and pick the
overall severity from the most serious item. Keep incident_detected false (empty
incidents) only when nothing dangerous is visible."""

#: Context framing per footage source. The opening framing matters a lot: it tells
#: the model what kind of camera it is looking through, which changes what counts as
#: "normal" vs "dangerous".
_SOURCE_FRAMING: dict[str, str] = {
    "tfl": (
        "You are an automated road-safety monitor watching a short clip from a FIXED,\n"
        "overhead TfL traffic camera at a London road junction. The view is wide and\n"
        "low-resolution. Judge danger from movement patterns across the whole junction.\n"
        "Only flag what you can clearly observe; if genuinely in doubt, do not flag."
    ),
    "manual": (
        "You are a road-safety incident reviewer watching USER-SUBMITTED footage that a\n"
        "member of the public uploaded to report a dangerous moment. It may be dashcam,\n"
        "phone, helmet-cam, or CCTV from ANY angle and distance - not a fixed junction\n"
        "camera. Assume the uploader saw something concerning, so look hard for it.\n"
        "Bias toward triage: flag a plausible NEAR_MISS or other event when you see\n"
        "evasive braking, swerving, abrupt stopping, a road user entering another's path,\n"
        "or dangerous proximity, even if the angle or quality is imperfect. Use\n"
        '"confidence": "low" when evidence is partial, but do NOT dismiss a likely\n'
        "near-miss just because the footage is shaky, brief, or low quality."
    ),
}
# 'upload' is an alias for 'manual'.
_SOURCE_FRAMING["upload"] = _SOURCE_FRAMING["manual"]


def build_analysis_prompt(source: str = "tfl") -> str:
    """Return a source-aware analysis prompt.

    Parameters
    ----------
    source:
        ``"tfl"`` for fixed overhead camera monitoring (conservative), or
        ``"manual"``/``"upload"`` for user-submitted footage (triage-biased).
        Unknown values fall back to the TfL framing.
    """
    framing = _SOURCE_FRAMING.get(source, _SOURCE_FRAMING["tfl"])
    return (
        f"{framing}\n\n"
        "You must not attempt to identify faces, individuals, or number plates.\n\n"
        f"{_EVENT_TAXONOMY}\n\n"
        f"{_JSON_SCHEMA}"
    )


#: Backward-compatible default prompt (TfL framing) used by existing callers/tests.
ANALYSIS_PROMPT: str = build_analysis_prompt("tfl")

#: Default OpenRouter endpoint.
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AnalysisError(RuntimeError):
    """Raised when the vision model call fails or returns unparseable output."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import re as _re

def _parse_json_content(content: str) -> dict:
    """Parse JSON from a model response, stripping markdown code fences if present.

    Some models wrap their JSON output in ```json ... ``` even when
    ``response_format: json_object`` is requested.  This strips the fences
    before parsing so downstream code always gets a plain dict.

    Raises
    ------
    AnalysisError
        If the content cannot be parsed as JSON after stripping.
    """
    text = content.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    fence_match = _re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, _re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnalysisError(
            f"Model returned non-JSON content: {content[:300]}"
        ) from exc


# ---------------------------------------------------------------------------
# Utility: download
# ---------------------------------------------------------------------------

def download_video(video_url: str, timeout: int = 30) -> str:
    """Download an MP4 to a temporary file and return its path.

    The **caller is responsible** for deleting the file (use try/finally or
    contextlib.ExitStack).

    Parameters
    ----------
    video_url:
        Full HTTP(S) URL of the MP4 stream.
    timeout:
        Request timeout in seconds (default 30).

    Returns
    -------
    str
        Absolute path to the downloaded temporary file.

    Raises
    ------
    requests.HTTPError
        If the server returns a non-2xx status.
    requests.Timeout
        If the download exceeds ``timeout`` seconds.
    """
    if not video_url or not isinstance(video_url, str):
        raise ValueError("video_url must be a non-empty string.")

    resp = requests.get(video_url, timeout=timeout)
    resp.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    try:
        tmp.write(resp.content)
    finally:
        tmp.close()

    return tmp.name


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseAnalyzer(abc.ABC):
    """Abstract base class for video analysis backends.

    Subclasses implement :meth:`analyze`, which takes a local MP4 path and
    returns a dict matching the ANALYSIS_PROMPT JSON schema.
    """

    @abc.abstractmethod
    def analyze(self, video_path: str) -> dict:
        """Analyze a locally-stored MP4 clip and return the incident JSON.

        Parameters
        ----------
        video_path:
            Absolute path to the MP4 file.

        Returns
        -------
        dict
            Parsed JSON with keys: incident_detected, severity, incidents,
            scene_summary, reasoning.

        Raises
        ------
        AnalysisError
            On any model API failure or unparseable response.
        ValueError
            If ``video_path`` is empty or the file does not exist.
        """

    @staticmethod
    def _validate_path(video_path: str) -> None:
        """Raise ValueError if path is empty or file is missing."""
        import os
        if not video_path or not isinstance(video_path, str):
            raise ValueError("video_path must be a non-empty string.")
        if not os.path.exists(video_path):
            raise ValueError(f"Video file not found: {video_path!r}")


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------

class GeminiAnalyzer(BaseAnalyzer):
    """Analyze video clips using the Gemini Files API.

    Follows the upload -> poll for ACTIVE state -> generate_content -> delete
    lifecycle required by the Gemini Files API.

    Parameters
    ----------
    api_key:
        Google Generative AI API key (GEMINI_API_KEY).
    model:
        Gemini model name. Defaults to "gemini-1.5-flash".
    poll_interval:
        Seconds to wait between PROCESSING state polls (default 2).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        poll_interval: float = 2.0,
    ) -> None:
        if not api_key:
            raise ValueError("GeminiAnalyzer requires a non-empty api_key.")
        self._api_key = api_key
        self._model = model
        self._poll_interval = poll_interval

        # Configure the SDK once when the analyzer is instantiated.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import google.generativeai as genai  # type: ignore[import]
        genai.configure(api_key=api_key)
        self._genai = genai

    def analyze(self, video_path: str, source: str = "tfl") -> dict:
        """Upload to Gemini, analyse, delete, and return parsed JSON.

        The remote file is always deleted in a finally block so we don't leak
        storage quota even on errors.

        ``source`` selects the prompt framing ("tfl" vs "manual"/"upload").
        """
        self._validate_path(video_path)

        uploaded_file = None
        try:
            print("  Uploading to Gemini...", end=" ", flush=True)
            uploaded_file = self._genai.upload_file(video_path, mime_type="video/mp4")

            # Poll until the file leaves PROCESSING state.
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(self._poll_interval)
                uploaded_file = self._genai.get_file(uploaded_file.name)

            if uploaded_file.state.name != "ACTIVE":
                raise AnalysisError(
                    f"Gemini file processing failed: state={uploaded_file.state.name}"
                )
            print("done")

            print("  Analysing...", end=" ", flush=True)
            model = self._genai.GenerativeModel(self._model)
            response = model.generate_content(
                [uploaded_file, build_analysis_prompt(source)],
                generation_config={"response_mime_type": "application/json"},
            )
            print("done")

            try:
                return json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise AnalysisError(
                    f"Gemini returned non-JSON content: {response.text[:300]}"
                ) from exc

        except AnalysisError:
            raise
        except Exception as exc:
            raise AnalysisError(f"Gemini analysis failed: {exc}") from exc

        finally:
            if uploaded_file is not None:
                try:
                    self._genai.delete_file(uploaded_file.name)
                except Exception:
                    pass  # Best-effort cleanup - don't mask the real error.


# ---------------------------------------------------------------------------
# OpenRouter implementation
# ---------------------------------------------------------------------------

class OpenRouterAnalyzer(BaseAnalyzer):
    """Analyze video clips via the OpenRouter chat completions endpoint.

    Sends the video as a direct HTTP URL (``video_url`` content type).
    minimax/minimax-m3 — and most other multimodal models — require a real
    HTTP/HTTPS URL; base64 data URLs are silently rejected (content: null).

    Parameters
    ----------
    api_key:
        OpenRouter API key (OPENROUTER_API_KEY).
    model:
        OpenRouter model string. Defaults to "minimax/minimax-m3".
    timeout:
        HTTP request timeout in seconds (default 120).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "minimax/minimax-m3",
        timeout: int = 120,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouterAnalyzer requires a non-empty api_key.")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def analyze(self, video_path: str) -> dict:
        """Analyze a local video file.

        Uploads the file to a temporary public URL via Supabase Storage if
        available, otherwise raises AnalysisError with a clear message.
        For direct URL analysis (preferred), use :meth:`analyze_url`.
        """
        self._validate_path(video_path)
        raise AnalysisError(
            "OpenRouterAnalyzer.analyze(path) is not supported — "
            "minimax/minimax-m3 requires an HTTP URL, not a local file. "
            "Call analyze_url(video_url) and pass the original signed URL instead."
        )

    def analyze_url(self, video_url: str, source: str = "tfl") -> dict:
        """Analyze a video by passing its HTTP URL directly to the model.

        Parameters
        ----------
        video_url:
            A publicly-accessible (or signed) HTTPS URL to an MP4 video.
            Must be reachable by the OpenRouter/Minimax backend.
        source:
            Selects the prompt framing ("tfl" vs "manual"/"upload").
        """
        if not video_url.startswith(("http://", "https://")):
            raise AnalysisError(f"video_url must be an HTTP/HTTPS URL, got: {video_url[:80]}")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_analysis_prompt(source)},
                        {"type": "video_url", "video_url": {"url": video_url}},
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
        }

        print("  Sending to OpenRouter...", end=" ", flush=True)
        try:
            resp = requests.post(
                OPENROUTER_API,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise AnalysisError(f"OpenRouter request failed: {exc}") from exc
        print("done")

        try:
            body = resp.json()
            # Check for OpenRouter-level error response
            if "error" in body:
                error_msg = body["error"].get("message", "Unknown OpenRouter error")
                raise AnalysisError(f"OpenRouter API error: {error_msg}")
            content = body["choices"][0]["message"]["content"]
            # Detect silent null — model couldn't process the video URL
            if content is None:
                finish = body["choices"][0].get("finish_reason")
                raise AnalysisError(
                    f"Model returned null content (finish_reason={finish!r}). "
                    "The video URL may be inaccessible or in an unsupported format."
                )
            return _parse_json_content(content)
        except (KeyError, IndexError) as exc:
            raise AnalysisError(
                f"Unexpected OpenRouter response structure: {resp.text[:500]}"
            ) from exc
