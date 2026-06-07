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

#: Event taxonomy for fixed-overhead TfL junction cameras (unchanged).
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

#: Cyclist-POV event taxonomy — used for user-uploaded helmet/handlebar-cam footage.
#: Every event is described from the camera holder's first-person perspective.
#: NEAR_MISS is the central event type; spatial proximity is the primary signal.
_CYCLIST_EVENT_TAXONOMY: str = """Dangerous events to flag from the CYCLIST'S POINT OF VIEW (use the exact type string).
The camera IS the cyclist. Judge every event from what the camera holder experiences.

HOW TO JUDGE PROXIMITY FROM POV FOOTAGE (read this before classifying):
- A vehicle that occupies >40% of the frame width as it passes is within ~1 metre.
- If you can see bodywork detail on a passing vehicle (door handles, panel gaps,
  badges, wing mirror shape, the driver's face or arm) the clearance is under 1m.
- The critical question: is there visible road surface or daylight between the
  cyclist and the passing vehicle? If NO — the vehicle fills the frame edge-to-edge
  with zero visible gap — that is a near-miss. Collision was avoided only because
  the vehicle happened to be travelling straight and the cyclist held their line.
- Camera shake is a SECONDARY cue — its absence does NOT mean the pass was safe.
  Many near-misses show no camera movement because the cyclist held steady.
- A SAFE pass: you can see clear road surface between cyclist and vehicle, the
  vehicle occupies less than ~30% of the frame width, and there is obvious space.

- NEAR_MISS (THE PRIMARY EVENT — scrutinise every overtake for this):
  A collision was narrowly avoided because the margin for error was dangerously
  small. A near-miss means: if the cyclist had wobbled slightly, or the vehicle
  had drifted slightly, contact would have occurred. The defining evidence is
  PROXIMITY — how much space existed between the cyclist and the vehicle.
  From POV, a near-miss looks like ONE OR MORE of the following:
  * [OVERTAKE] A vehicle passes with no visible gap between it and the cyclist.
    The vehicle bodywork fills most of the frame. You cannot see road surface
    between the cyclist and the vehicle. This IS a near-miss — the proximity
    itself is the danger, regardless of whether anyone swerved.
  * [OVERTAKE] A vehicle passes close enough that you can see fine detail on
    its side (door handles, badges, the driver's face through the window, wing
    mirror at head height). This means the vehicle is within arm's reach.
  * [OVERTAKE] A vehicle overtakes and immediately cuts in front of the cyclist
    before fully clearing them — the vehicle's rear is still close ahead.
  * [PULL-OUT] A vehicle pulls out from a side road, driveway, or parking space
    into the cyclist's path with barely enough room, forcing the cyclist to brake
    or take evasive action.
  * [HOOK] A vehicle ahead turns left across the cyclist's path (left hook),
    or an oncoming vehicle turns right across the cyclist's path (right hook),
    with the cyclist having to brake or swerve to avoid collision.
  * [DOORING] A vehicle door swings open directly in the cyclist's path.
  * [PEDESTRIAN] A pedestrian steps into the road immediately ahead of the
    cyclist, forcing emergency braking or a swerve.
  For each near-miss, your description MUST state what the proximity was and
  why it was dangerous. Example: "Vehicle passes within ~0.5m — no visible gap,
  door handles and badge legible, wing mirror at head height."

  SEVERITY FOR OVERTAKE NEAR-MISSES:
  - CRITICAL: vehicle fills the frame completely (no gap at all), you can read
    the badge or see the driver's facial features, wing mirror passes within
    inches of the camera.
  - HIGH: vehicle occupies most of the frame (>50% width), no road surface
    visible between cyclist and vehicle, bodywork detail clearly legible.
  - MEDIUM: the pass is tight — vehicle occupies 30-50% of frame width, some
    visible detail on the vehicle side, gap is clearly less than a car-door width.
  - LOW: vehicle is closer than comfortable but there is visible space and the
    pass would not be dangerous if the cyclist held their line.

- CYCLIST_RISK:
  The cyclist is put in a vulnerable position by another vehicle's behaviour.
  From POV:
  * Cyclist squeezed against the kerb or parked cars by a vehicle alongside.
  * A bus, lorry, or van passes and pulls in before fully clearing the cyclist.
  * Cyclist in a large vehicle's blind spot with no acknowledgment from driver.
  * A vehicle encroaches into a cycle lane, forcing the cyclist into traffic.
  * Filtering through queuing traffic — a vehicle closes a gap unpredictably.

- DANGEROUS_OVERTAKE:
  A vehicle overtakes in a way that creates danger beyond proximity alone.
  From POV:
  * Overtaking into visible oncoming traffic.
  * Overtaking approaching a junction, traffic island, or crossing with no room
    to complete the pass.
  * Overtaking then immediately braking or turning left across the cyclist.
  * Overtaking at speed with a trailer or wide load that cuts in early.

- RED_LIGHT_VIOLATION:
  A vehicle runs a red light while the cyclist has right of way. From POV:
  * Cyclist has green, a vehicle from the crossing direction goes through on red.
  * A vehicle behind or alongside the cyclist runs a red light.

- WRONG_WAY:
  A vehicle or other road user travels against traffic flow toward the camera.

- PEDESTRIAN_IN_ROAD:
  A pedestrian is in the live carriageway in the cyclist's path.
  From POV: person steps off the pavement into the road ahead, or walks in the
  road with their back to traffic.

- VEHICLE_STOPPED_DANGEROUSLY:
  A stationary vehicle forces the cyclist into danger. From POV:
  * A parked car or van blocks a cycle lane, forcing the cyclist into live traffic.
  * A vehicle stopped in a live lane or junction box.
  * A delivery vehicle, taxi, or bus pulled up in the cyclist's path without warning.

- AGGRESSIVE_DRIVING:
  Deliberately intimidating or hostile behaviour toward the cyclist. From POV:
  * A "punishment pass" — an extremely close overtake paired with horn use,
    engine revving, or the vehicle immediately pulling in front.
  * A vehicle tailgates the cyclist from behind (audible engine noise close
    behind; fills rear camera if present).
  * Driver gestures, shouts, or behaves threateningly.
  * Vehicle repeatedly brake-checks or slows to confront the cyclist."""

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
        "You are a road-safety incident reviewer watching footage from a CYCLIST'S\n"
        "POINT OF VIEW — a helmet camera or handlebar camera worn by someone cycling\n"
        "in traffic. The camera MOVES WITH THE CYCLIST. It is NOT a fixed junction\n"
        "camera. The camera holder IS the vulnerable road user.\n"
        "\n"
        "YOUR TASK: identify near-misses — moments where a collision was narrowly\n"
        "avoided because the margin for error was dangerously small. The PRIMARY\n"
        "evidence of a near-miss is PROXIMITY: how much space existed between the\n"
        "cyclist and the vehicle? If the answer is 'almost none', that IS a near-miss.\n"
        "\n"
        "HOW TO JUDGE PROXIMITY FROM POV FOOTAGE:\n"
        "- A vehicle occupying >40% of the frame width is within ~1 metre.\n"
        "- Visible bodywork detail (door handles, badges, panel gaps, wing mirror\n"
        "  shape, driver's face) means clearance is under 1 metre — dangerous.\n"
        "- The critical test: is there visible ROAD SURFACE or DAYLIGHT between the\n"
        "  cyclist and the passing vehicle? If NO — the vehicle fills the frame with\n"
        "  zero gap — collision was avoided only by both parties holding a straight\n"
        "  line. This IS a near-miss. Flag it.\n"
        "- Camera shake MAY be present (from wind buffeting or evasive movement) but\n"
        "  its ABSENCE does NOT indicate a safe pass. Many dangerous passes show no\n"
        "  camera movement at all. Judge by the SPACE, not by camera stability.\n"
        "- A safe pass: clear road surface visible between cyclist and vehicle,\n"
        "  vehicle occupies <30% of frame width, obvious gap.\n"
        "\n"
        "TRIAGE POSTURE:\n"
        "Assume the uploader submitted this because they experienced something\n"
        "dangerous. Scrutinise EVERY overtake for proximity. When you see a vehicle\n"
        "pass with little or no visible gap, flag it as NEAR_MISS and explain exactly\n"
        "what the proximity was (e.g. 'no road surface visible between cyclist and\n"
        "vehicle, door handles legible, vehicle fills >50% of frame width').\n"
        "Use confidence: low when evidence is partial, but do NOT dismiss a likely\n"
        "near-miss just because the footage is shaky, brief, or the angle is unusual.\n"
        "\n"
        "Do NOT describe the scene as 'normal traffic flow at a junction' — you are\n"
        "watching from within the traffic, at road level, from a vulnerable position.\n"
        "A vehicle passing inches from a cyclist IS a near-miss, even if traffic is\n"
        "otherwise flowing normally."
    ),
}
# 'upload' is an alias for 'manual'.
_SOURCE_FRAMING["upload"] = _SOURCE_FRAMING["manual"]


def build_analysis_prompt(source: str = "tfl", memory_context: str = "") -> str:
    """Return a source-aware analysis prompt.

    Parameters
    ----------
    source:
        ``"tfl"`` for fixed overhead camera monitoring (conservative), or
        ``"manual"``/``"upload"`` for user-submitted footage (triage-biased,
        cyclist-POV-optimised). Unknown values fall back to the TfL framing.
    memory_context:
        Optional historical context (e.g. past incidents at this camera) to
        prepend to the prompt. Empty string = no extra context.
    """
    framing = _SOURCE_FRAMING.get(source, _SOURCE_FRAMING["tfl"])
    # Use cyclist-POV taxonomy for manual/upload sources, junction taxonomy for TfL.
    if source in ("manual", "upload", "cyclist"):
        taxonomy = _CYCLIST_EVENT_TAXONOMY
    else:
        taxonomy = _EVENT_TAXONOMY
    parts: list[str] = []
    if memory_context:
        parts.append(memory_context)
    parts.extend([
        framing,
        "You must not attempt to identify faces, individuals, or number plates.",
        taxonomy,
        _JSON_SCHEMA,
    ])
    return "\n\n".join(parts)


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

    def analyze(self, video_path: str, source: str = "tfl", memory_context: str = "") -> dict:
        """Upload to Gemini, analyse, delete, and return parsed JSON.

        The remote file is always deleted in a finally block so we don't leak
        storage quota even on errors.

        ``source`` selects the prompt framing ("tfl" vs "manual"/"upload").
        ``memory_context`` is optionally prepended to the prompt (no-op when empty).
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
                [uploaded_file, build_analysis_prompt(source, memory_context=memory_context)],
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

    def analyze_url(self, video_url: str, source: str = "tfl", memory_context: str = "") -> dict:
        """Analyze a video by passing its HTTP URL directly to the model.

        Parameters
        ----------
        video_url:
            A publicly-accessible (or signed) HTTPS URL to an MP4 video.
            Must be reachable by the OpenRouter/Minimax backend.
        source:
            Selects the prompt framing ("tfl" vs "manual"/"upload").
        memory_context:
            Optional historical context to prepend to the prompt.
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
                        {"type": "text", "text": build_analysis_prompt(source, memory_context=memory_context)},
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
