"""
shared - common utilities for the Urban Intelligence pipeline.

Modules
-------
config_loader       Load and validate environment/config, returns a typed AppConfig.
tfl_client          TfL JamCam API wrapper with retries and input validation.
video_analyzer      Abstract analyzer interface plus Gemini and OpenRouter implementations.
incident_repository Supabase persistence for incidents and camera status.
"""

from shared.config_loader import AppConfig, load_config
from shared.tfl_client import TflClient, TFL_API
from shared.video_analyzer import (
    BaseAnalyzer,
    GeminiAnalyzer,
    OpenRouterAnalyzer,
    download_video,
    ANALYSIS_PROMPT,
    SEVERITY_RANK,
    SEVERITY_EMOJI,
)
from shared.incident_repository import IncidentRepository

__all__ = [
    "AppConfig",
    "load_config",
    "TflClient",
    "TFL_API",
    "BaseAnalyzer",
    "GeminiAnalyzer",
    "OpenRouterAnalyzer",
    "download_video",
    "ANALYSIS_PROMPT",
    "SEVERITY_RANK",
    "SEVERITY_EMOJI",
    "IncidentRepository",
]
