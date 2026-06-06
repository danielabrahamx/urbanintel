"""Tests for configuration management."""
import importlib
import os
from unittest.mock import patch

import pytest

import config


class TestConfigLoading:
    """Test configuration loading and defaults."""

    def test_load_config_success(self):
        """Test successful config loading with all required values."""
        with patch.dict("os.environ", {"TFL_APP_KEY": "test-tfl-key"}, clear=True):
            cfg = config.load_config()

            assert cfg.tfl_app_key == "test-tfl-key"
            assert cfg.target_camera_id == "JamCams_00001.07350"
            assert cfg.poll_interval_seconds == 180
            assert cfg.alert_threshold == "medium"
            assert cfg.vision_model == "minimax/minimax-m3"
            assert cfg.tfl_api_url == "https://api.tfl.gov.uk/Place/Type/JamCam"

    def test_load_config_missing_required(self):
        """Test error when required TFL_APP_KEY is missing."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="Missing required env vars"):
                config.load_config()

    def test_load_config_custom_values(self):
        """Test loading with custom environment values."""
        env_vars = {
            "TFL_APP_KEY": "custom-key",
            "TARGET_CAMERA_ID": "JamCams_99999.99999",
            "POLL_INTERVAL_SECONDS": "300",
            "ALERT_THRESHOLD": "high",
            "VISION_MODEL": "custom-model",
            "TFL_API_URL": "https://custom.api.url",
            "NEXT_PUBLIC_SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-key",
            "OPENROUTER_API_KEY": "openrouter-key",
            "GEMINI_API_KEY": "gemini-key",
        }
        with patch.dict("os.environ", env_vars, clear=True):
            cfg = config.load_config()

            assert cfg.tfl_app_key == "custom-key"
            assert cfg.target_camera_id == "JamCams_99999.99999"
            assert cfg.poll_interval_seconds == 300
            assert cfg.alert_threshold == "high"
            assert cfg.vision_model == "custom-model"
            assert cfg.tfl_api_url == "https://custom.api.url"
            assert cfg.supabase_url == "https://test.supabase.co"
            assert cfg.supabase_key == "test-key"
            assert cfg.openrouter_api_key == "openrouter-key"
            assert cfg.gemini_api_key == "gemini-key"

    def test_load_config_invalid_poll_interval(self):
        """Test fallback when POLL_INTERVAL_SECONDS is invalid."""
        with patch.dict("os.environ", {
            "TFL_APP_KEY": "test-key",
            "POLL_INTERVAL_SECONDS": "invalid",
        }, clear=True):
            cfg = config.load_config()
            assert cfg.poll_interval_seconds == 180  # Default fallback


class TestGetConfigSingleton:
    """Test get_config singleton behavior."""

    def test_get_config_singleton(self):
        """Test that get_config returns same instance (singleton)."""
        # Reset singleton
        config._config = None

        with patch.dict("os.environ", {"TFL_APP_KEY": "test-key"}, clear=True):
            cfg1 = config.get_config()
            cfg2 = config.get_config()

            assert cfg1 is cfg2

    def test_reload_config(self):
        """Test reload_config creates new instance."""
        with patch.dict("os.environ", {"TFL_APP_KEY": "key1"}, clear=True):
            config._config = None
            cfg1 = config.get_config()

        with patch.dict("os.environ", {"TFL_APP_KEY": "key2"}, clear=True):
            cfg2 = config.reload_config()

            assert cfg1 is not cfg2
            assert cfg1.tfl_app_key == "key1"
            assert cfg2.tfl_app_key == "key2"


class TestLegacyExports:
    """Test backward-compatible module-level exports."""

    def test_legacy_constants_exist(self):
        """Test that legacy module-level constants are exported."""
        # These should exist for backward compatibility
        assert hasattr(config, "TARGET_CAMERA_ID")
        assert hasattr(config, "POLL_INTERVAL_SECONDS")
        assert hasattr(config, "ALERT_THRESHOLD")
        assert hasattr(config, "TFL_APP_KEY")
        assert hasattr(config, "TFL_APP_ID")
        assert hasattr(config, "VISION_MODEL")
        assert hasattr(config, "ANALYSIS_PROMPT")

    def test_incident_types_constant(self):
        """Test that INCIDENT_TYPES constant is exported."""
        assert hasattr(config, "INCIDENT_TYPES")
        assert isinstance(config.INCIDENT_TYPES, list)
        assert "NEAR_MISS" in config.INCIDENT_TYPES
        assert "RED_LIGHT_VIOLATION" in config.INCIDENT_TYPES

    def test_severity_order_constant(self):
        """Test that SEVERITY_ORDER constant is exported."""
        assert hasattr(config, "SEVERITY_ORDER")
        assert config.SEVERITY_ORDER["none"] == 0
        assert config.SEVERITY_ORDER["critical"] == 4

    def test_severity_emoji_constant(self):
        """Test that SEVERITY_EMOJI constant is exported."""
        assert hasattr(config, "SEVERITY_EMOJI")
        assert "none" in config.SEVERITY_EMOJI
        assert "critical" in config.SEVERITY_EMOJI


class TestConfigDataclass:
    """Test Config dataclass properties."""

    def test_config_cors_origins_default(self):
        """Test default CORS origins."""
        with patch.dict("os.environ", {"TFL_APP_KEY": "test-key"}, clear=True):
            cfg = config.load_config()

            assert "http://localhost:3000" in cfg.cors_origins
            assert "https://localhost:3000" in cfg.cors_origins

    def test_config_cors_origins_from_env(self):
        """Test CORS origins from environment variable."""
        with patch.dict("os.environ", {
            "TFL_APP_KEY": "test-key",
            "CORS_ORIGINS": "http://app1.com, http://app2.com",
        }, clear=True):
            cfg = config.load_config()

            assert "http://app1.com" in cfg.cors_origins
            assert "http://app2.com" in cfg.cors_origins

    def test_config_optional_fields_none(self):
        """Test that optional fields default to None."""
        with patch.dict("os.environ", {"TFL_APP_KEY": "test-key"}, clear=True):
            cfg = config.load_config()

            assert cfg.supabase_url is None
            assert cfg.supabase_key is None
            assert cfg.openrouter_api_key is None
            assert cfg.gemini_api_key is None


class TestAnalysisPrompt:
    """Test analysis prompt constant."""

    def test_analysis_prompt_exists(self):
        """Test that ANALYSIS_PROMPT is defined."""
        assert hasattr(config, "ANALYSIS_PROMPT")
        assert isinstance(config.ANALYSIS_PROMPT, str)
        assert len(config.ANALYSIS_PROMPT) > 0

    def test_default_analysis_prompt(self):
        """Test DEFAULT_ANALYSIS_PROMPT constant."""
        assert hasattr(config, "DEFAULT_ANALYSIS_PROMPT")
        assert isinstance(config.DEFAULT_ANALYSIS_PROMPT, str)
        assert "incident_detected" in config.DEFAULT_ANALYSIS_PROMPT
        assert "severity" in config.DEFAULT_ANALYSIS_PROMPT
