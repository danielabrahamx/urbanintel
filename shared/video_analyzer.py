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

ANALYSIS_PROMPT: str = """You are an automated road safety system watching a 10-second clip
from a fixed TfL traffic camera at a London road junction.

Your job: detect dangerous driving behaviour and near-miss incidents from vehicle and
pedestrian movement patterns. Resolution is low - you cannot and must not attempt to
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

Respond ONLY with this JSON - no preamble, no markdown, no explanation outside it:
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

#: Default OpenRouter endpoint.
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AnalysisError(RuntimeError):
    """Raised when the vision model call fails or returns unparseable output."""


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

    def analyze(self, video_path: str) -> dict:
        """Upload to Gemini, analyse, delete, and return parsed JSON.

        The remote file is always deleted in a finally block so we don't leak
        storage quota even on errors.
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
                [uploaded_file, ANALYSIS_PROMPT],
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
    """Analyze video clips by base64-encoding the MP4 and sending it to
    OpenRouter's chat completions endpoint.

    Currently targets minimax/minimax-m3 which accepts ``video_url`` data URLs
    in the message content.

    Parameters
    ----------
    api_key:
        OpenRouter API key (OPENROUTER_API_KEY).
    model:
        OpenRouter model string. Defaults to "minimax/minimax-m3".
    timeout:
        HTTP request timeout in seconds (default 120 - video payloads are large).
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
        """Base64-encode the MP4 and call the OpenRouter completions API."""
        self._validate_path(video_path)

        with open(video_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:video/mp4;base64,{b64}"

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
                        {"type": "text", "text": ANALYSIS_PROMPT},
                        {"type": "video_url", "video_url": {"url": data_url}},
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
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AnalysisError(
                f"Unexpected OpenRouter response structure: {resp.text[:300]}"
            ) from exc
