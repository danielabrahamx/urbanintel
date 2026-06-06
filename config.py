"""Centralized configuration with validation - single source of truth for all settings."""

import os
from dataclasses import dataclass
from typing import Optional


# Incident types - single source of truth for all incident classification
INCIDENT_TYPES = [
    "NEAR_MISS",
    "RED_LIGHT_VIOLATION",
    "WRONG_WAY",
    "DANGEROUS_OVERTAKE",
    "PEDESTRIAN_IN_ROAD",
    "VEHICLE_STOPPED_DANGEROUSLY",
    "AGGRESSIVE_DRIVING",
    "CYCLIST_RISK",
]

# Severity ranking for comparison operations
SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# Severity emoji mapping for display
SEVERITY_EMOJI = {
    "none": "[OK]",
    "low": "[!]",
    "medium": "[*]",
    "high": "[**]",
    "critical": "[!!!]",
}

# Default analysis prompt template
DEFAULT_ANALYSIS_PROMPT = """You are an automated road safety system watching a 10-second clip
from a fixed TfL traffic camera at a London road junction.

Your job: detect dangerous driving behaviour and near-miss incidents from vehicle and
pedestrian movement patterns across the full clip. Resolution is low - you cannot and
must not attempt to identify faces, individuals, or number plates.

Dangerous events to flag:
- NEAR_MISS: vehicle comes dangerously close to a pedestrian or another vehicle
- RED_LIGHT_VIOLATION: vehicle clearly runs a red light
- WRONG_WAY: vehicle moving against traffic flow
- DANGEROUS_OVERTAKE: unsafe overtaking manoeuvre
- PEDESTRIAN_IN_ROAD: person in the carriageway in danger
- VEHICLE_STOPPED_DANGEROUSLY: vehicle stopped in a live lane, junction box, or crossroads
- AGGRESSIVE_DRIVING: sudden swerving or obvious tailgating
- CYCLIST_RISK: cyclist in dangerous proximity to a larger vehicle

Only flag what you can clearly observe across the video. If in doubt, return incident_detected: false.
A false negative is better than a false positive.

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


@dataclass
class Config:
    """Application configuration with type-safe access."""

    # TfL API
    tfl_app_key: str
    tfl_app_id: Optional[str] = None  # Deprecated but some legacy code uses it
    tfl_api_url: str = "https://api.tfl.gov.uk/Place/Type/JamCam"

    # Video Analysis
    vision_model: str = "minimax/minimax-m3"
    analysis_prompt: str = DEFAULT_ANALYSIS_PROMPT

    # OpenRouter API
    openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions"

    # Polling settings
    target_camera_id: str = "JamCams_00001.07350"
    poll_interval_seconds: int = 180
    alert_threshold: str = "medium"

    # Supabase
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None  # Service role key for backend operations
    supabase_publishable_key: Optional[str] = None  # Client-side key

    # API Keys
    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # API Server settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list = None

    def __post_init__(self):
        """Initialize derived fields."""
        if self.cors_origins is None:
            self.cors_origins = [
                "http://localhost:3000",
                "https://localhost:3000",
            ]


def load_config() -> Config:
    """Load and validate configuration from environment variables.

    Raises:
        ValueError: If required environment variables are missing.

    Returns:
        Config: Validated configuration instance.
    """
    # Required variables - at minimum need TfL key
    required = ["TFL_APP_KEY"]
    missing = [r for r in required if not os.environ.get(r)]
    if missing:
        raise ValueError(f"Missing required env vars: {missing}")

    # Parse poll interval with fallback
    try:
        poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "180"))
    except ValueError:
        poll_interval = 180

    # Parse CORS origins if provided
    cors_origins_env = os.environ.get("CORS_ORIGINS")
    if cors_origins_env:
        cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]
    else:
        cors_origins = [
            "http://localhost:3000",
            "https://localhost:3000",
        ]

    return Config(
        tfl_app_key=os.environ["TFL_APP_KEY"],
        tfl_app_id=os.environ.get("TFL_APP_ID"),  # Deprecated/optional
        tfl_api_url=os.environ.get("TFL_API_URL", "https://api.tfl.gov.uk/Place/Type/JamCam"),
        vision_model=os.environ.get("VISION_MODEL", "minimax/minimax-m3"),
        analysis_prompt=os.environ.get("ANALYSIS_PROMPT", DEFAULT_ANALYSIS_PROMPT),
        openrouter_api_url=os.environ.get(
            "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
        ),
        target_camera_id=os.environ.get("TARGET_CAMERA_ID", "JamCams_00001.07350"),
        poll_interval_seconds=poll_interval,
        alert_threshold=os.environ.get("ALERT_THRESHOLD", "medium"),
        supabase_url=os.environ.get("NEXT_PUBLIC_SUPABASE_URL"),
        supabase_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
        supabase_publishable_key=os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        api_host=os.environ.get("API_HOST", "0.0.0.0"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        cors_origins=cors_origins,
    )


# Global config instance (lazy-loaded singleton)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get singleton config instance.

    Loads config on first call, then returns cached instance.
    Thread-safe for read access after initial load.

    Returns:
        Config: The application configuration singleton.
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> Config:
    """Force reload configuration from environment.

    Useful for testing or when environment changes at runtime.

    Returns:
        Config: Freshly loaded configuration.
    """
    global _config
    _config = load_config()
    return _config


# Legacy module-level exports for backward compatibility
# These will be removed in a future version - migrate to get_config()
def _get_config_attr(name: str, default=None):
    """Safely get config attribute with fallback to defaults."""
    try:
        cfg = get_config()
        return getattr(cfg, name, default)
    except ValueError:
        # Config not loaded yet, return default
        return default


# Backward-compatible module-level constants
TARGET_CAMERA_ID = _get_config_attr("target_camera_id", "JamCams_00001.07350")
POLL_INTERVAL_SECONDS = _get_config_attr("poll_interval_seconds", 180)
ALERT_THRESHOLD = _get_config_attr("alert_threshold", "medium")
TFL_APP_KEY = _get_config_attr("tfl_app_key", "")
TFL_APP_ID = _get_config_attr("tfl_app_id", None)
VISION_MODEL = _get_config_attr("vision_model", "minimax/minimax-m3")
ANALYSIS_PROMPT = DEFAULT_ANALYSIS_PROMPT  # For backward compatibility
