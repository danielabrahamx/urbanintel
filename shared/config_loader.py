"""
shared.config_loader
====================
Load, validate, and expose typed configuration for the Urban Intelligence pipeline.

Design principles
-----------------
- Fail fast: if a required env var is missing, raise immediately with a clear message
  rather than letting a KeyError surface somewhere deep in the call stack.
- One source of truth: every caller imports AppConfig from here; nothing reads
  os.environ directly except this module.
- Backward-compatible: config.py tunables (TARGET_CAMERA_ID etc.) are still read
  from config.py so existing callers that import from there continue to work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Typed config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """Immutable, fully-typed snapshot of runtime configuration.

    Attributes
    ----------
    gemini_api_key:
        Google Generative AI API key. Required for GeminiAnalyzer.
    openrouter_api_key:
        OpenRouter API key. Required for OpenRouterAnalyzer.
    supabase_url:
        Supabase project URL. Optional - persistence is disabled when absent.
    supabase_service_role_key:
        Supabase service-role key. Optional - paired with supabase_url.
    tfl_app_key:
        TfL Unified API primary key. Optional - anonymous access used when absent.
    target_camera_id:
        JamCam ID to monitor (e.g. "JamCams_00001.07350").
    poll_interval_seconds:
        Seconds between polling cycles.
    alert_threshold:
        Minimum severity to print a full alert banner ("none"/"low"/"medium"/"high"/"critical").
    vision_model:
        Gemini model name (e.g. "gemini-1.5-flash").
    openrouter_vision_model:
        OpenRouter model name (e.g. "minimax/minimax-m3").
    """

    # API keys
    gemini_api_key: Optional[str]
    openrouter_api_key: Optional[str]
    supabase_url: Optional[str]
    supabase_service_role_key: Optional[str]
    tfl_app_key: str

    # Operational tunables (sourced from config.py)
    target_camera_id: str
    poll_interval_seconds: int
    alert_threshold: str
    vision_model: str
    openrouter_vision_model: str

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def has_supabase(self) -> bool:
        """True when both Supabase credentials are present."""
        return bool(self.supabase_url and self.supabase_service_role_key)

    def require_gemini_key(self) -> str:
        """Return the Gemini API key, raising ConfigError if absent."""
        if not self.gemini_api_key:
            raise ConfigError(
                "GEMINI_API_KEY is not set. "
                "Create one at https://aistudio.google.com/apikey and add it to .env"
            )
        return self.gemini_api_key

    def require_openrouter_key(self) -> str:
        """Return the OpenRouter API key, raising ConfigError if absent."""
        if not self.openrouter_api_key:
            raise ConfigError(
                "OPENROUTER_API_KEY is not set. "
                "Create one at https://openrouter.ai/keys and add it to .env"
            )
        return self.openrouter_api_key


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(require_gemini: bool = False, require_openrouter: bool = False) -> AppConfig:
    """Load configuration from environment variables and config.py.

    Parameters
    ----------
    require_gemini:
        When True, raise ConfigError immediately if GEMINI_API_KEY is absent.
    require_openrouter:
        When True, raise ConfigError immediately if OPENROUTER_API_KEY is absent.

    Returns
    -------
    AppConfig
        Frozen dataclass with all config values populated.

    Raises
    ------
    ConfigError
        If a required key (controlled by the flags above) is missing.
    """
    # Import tunables from config.py so they remain the single editable source.
    # We import lazily inside the function to avoid circular-import issues if
    # config.py ever imports from shared/.
    try:
        import config as _cfg  # type: ignore[import]
    except ModuleNotFoundError as exc:
        raise ConfigError(
            "config.py not found. Make sure you run from the urbanintel project root."
        ) from exc

    gemini_key = os.environ.get("GEMINI_API_KEY") or None
    openrouter_key = os.environ.get("OPENROUTER_API_KEY") or None
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or None
    supabase_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None
    tfl_app_key = os.environ.get("TFL_APP_KEY", "") or getattr(_cfg, "TFL_APP_KEY", "")

    cfg = AppConfig(
        gemini_api_key=gemini_key,
        openrouter_api_key=openrouter_key,
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_service_key,
        tfl_app_key=tfl_app_key,
        target_camera_id=getattr(_cfg, "TARGET_CAMERA_ID", ""),
        poll_interval_seconds=int(getattr(_cfg, "POLL_INTERVAL_SECONDS", 180)),
        alert_threshold=getattr(_cfg, "ALERT_THRESHOLD", "medium"),
        vision_model=getattr(_cfg, "VISION_MODEL", "gemini-1.5-flash"),
        openrouter_vision_model=getattr(_cfg, "OPENROUTER_VISION_MODEL", "minimax/minimax-m3"),
    )

    # Fail-fast checks
    if require_gemini:
        cfg.require_gemini_key()
    if require_openrouter:
        cfg.require_openrouter_key()

    # Non-fatal warnings
    if not cfg.tfl_app_key:
        print(
            "[warn] TFL_APP_KEY not set - using anonymous TfL access (lower rate limit). "
            "Register free at https://api-portal.tfl.gov.uk"
        )

    return cfg
