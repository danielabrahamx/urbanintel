"""Tests for video analysis (shared.video_analyzer)."""
import base64
import json
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests

from shared.video_analyzer import (
    download_video,
    GeminiAnalyzer,
    OpenRouterAnalyzer,
    AnalysisError,
    SEVERITY_RANK,
    SEVERITY_EMOJI,
    VALID_INCIDENT_TYPES,
)


class TestDownloadVideo:
    """Test download_video utility function."""

    @patch("shared.video_analyzer.requests.get")
    @patch("shared.video_analyzer.tempfile.NamedTemporaryFile")
    def test_download_video_success(self, mock_tempfile, mock_requests_get, mock_temp_video_file):
        """Test successful video download to temp file."""
        mock_response = MagicMock()
        mock_response.content = b"fake video content"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_file = MagicMock()
        mock_file.name = mock_temp_video_file
        mock_file.write = MagicMock()
        mock_file.close = MagicMock()
        mock_tempfile.return_value = mock_file

        result = download_video("https://example.com/video.mp4")

        assert result == mock_temp_video_file
        mock_requests_get.assert_called_once_with("https://example.com/video.mp4", timeout=30)

    @patch("shared.video_analyzer.requests.get")
    def test_download_video_http_error(self, mock_requests_get):
        """Test HTTP errors during download are propagated."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_requests_get.return_value = mock_response

        with pytest.raises(requests.HTTPError):
            download_video("https://example.com/missing.mp4")

    @patch("shared.video_analyzer.requests.get")
    def test_download_video_timeout(self, mock_requests_get):
        """Test timeout errors during download."""
        mock_requests_get.side_effect = requests.Timeout("Request timed out")

        with pytest.raises(requests.Timeout):
            download_video("https://example.com/video.mp4")

    def test_download_video_invalid_url(self):
        """Test validation of invalid video URL."""
        with pytest.raises(ValueError, match="video_url must be a non-empty string"):
            download_video("")

        with pytest.raises(ValueError, match="video_url must be a non-empty string"):
            download_video(None)


class TestGeminiAnalyzer:
    """Test GeminiAnalyzer class."""

    def test_init_requires_api_key(self):
        """Test that GeminiAnalyzer requires an API key."""
        with pytest.raises(ValueError, match="requires a non-empty api_key"):
            GeminiAnalyzer(api_key="")

    def test_analyze_with_incident(self, sample_incident_detected, mock_temp_video_file):
        """Test successful analysis with incident detected."""
        # Create a mock genai module
        mock_genai = MagicMock()

        # Setup mock file
        mock_file = MagicMock()
        mock_file.name = "uploaded-file-123"
        mock_file.state.name = "ACTIVE"

        mock_genai.upload_file.return_value = mock_file
        mock_genai.get_file.return_value = mock_file

        # Setup model response
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(sample_incident_detected)
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        # Patch the import in the video_analyzer module and os.path.exists
        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock(generativeai=mock_genai)}):
            with patch("os.path.exists", return_value=True):
                with patch("warnings.catch_warnings"):
                    mock_warnings = MagicMock()
                    mock_warnings.return_value.__enter__ = MagicMock(return_value=mock_warnings)
                    mock_warnings.return_value.__exit__ = MagicMock(return_value=False)
                    with patch("warnings.simplefilter"):
                        analyzer = GeminiAnalyzer(api_key="test-api-key")
                        analyzer._genai = mock_genai  # Replace with our mock
                        result = analyzer.analyze(mock_temp_video_file)

        assert result["incident_detected"] is True
        assert result["severity"] == "high"
        assert len(result["incidents"]) == 1
        assert result["incidents"][0]["type"] == "NEAR_MISS"

    def test_analyze_no_incident(self, sample_incident_no_detection, mock_temp_video_file):
        """Test successful analysis with no incident."""
        mock_genai = MagicMock()

        mock_file = MagicMock()
        mock_file.name = "uploaded-file-456"
        mock_file.state.name = "ACTIVE"

        mock_genai.upload_file.return_value = mock_file
        mock_genai.get_file.return_value = mock_file

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(sample_incident_no_detection)
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock(generativeai=mock_genai)}):
            with patch("os.path.exists", return_value=True):
                with patch("warnings.catch_warnings"):
                    with patch("warnings.simplefilter"):
                        analyzer = GeminiAnalyzer(api_key="test-api-key")
                        analyzer._genai = mock_genai
                        result = analyzer.analyze(mock_temp_video_file)

        assert result["incident_detected"] is False
        assert result["severity"] == "none"
        assert len(result["incidents"]) == 0

    def test_analyze_invalid_response(self, mock_temp_video_file):
        """Test handling of invalid JSON response."""
        mock_genai = MagicMock()

        mock_file = MagicMock()
        mock_file.name = "uploaded-file-789"
        mock_file.state.name = "ACTIVE"

        mock_genai.upload_file.return_value = mock_file
        mock_genai.get_file.return_value = mock_file

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock(generativeai=mock_genai)}):
            with patch("os.path.exists", return_value=True):
                with patch("warnings.catch_warnings"):
                    with patch("warnings.simplefilter"):
                        analyzer = GeminiAnalyzer(api_key="test-api-key")
                        analyzer._genai = mock_genai
                        with pytest.raises(AnalysisError):
                            analyzer.analyze(mock_temp_video_file)

    @patch("time.sleep")
    def test_file_processing_polling(self, mock_sleep, sample_incident_no_detection, mock_temp_video_file):
        """Test that file processing state is polled until ACTIVE."""
        mock_genai = MagicMock()

        mock_file = MagicMock()
        mock_file.name = "uploaded-file-abc"
        mock_file.state.name = "PROCESSING"

        mock_file_active = MagicMock()
        mock_file_active.name = "uploaded-file-abc"
        mock_file_active.state.name = "ACTIVE"

        mock_genai.upload_file.return_value = mock_file
        mock_genai.get_file.side_effect = [mock_file, mock_file_active]

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(sample_incident_no_detection)
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock(generativeai=mock_genai)}):
            with patch("os.path.exists", return_value=True):
                with patch("warnings.catch_warnings"):
                    with patch("warnings.simplefilter"):
                        analyzer = GeminiAnalyzer(api_key="test-api-key", poll_interval=1.0)
                        analyzer._genai = mock_genai
                        result = analyzer.analyze(mock_temp_video_file)

        # Sleep is called at least once (while polling)
        assert mock_sleep.call_count >= 1
        assert result["incident_detected"] is False

    def test_file_processing_failed(self, mock_temp_video_file):
        """Test error when file processing fails."""
        mock_genai = MagicMock()

        mock_file = MagicMock()
        mock_file.name = "uploaded-file-def"
        mock_file.state.name = "FAILED"

        mock_genai.upload_file.return_value = mock_file

        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock(generativeai=mock_genai)}):
            with patch("os.path.exists", return_value=True):
                with patch("warnings.catch_warnings"):
                    with patch("warnings.simplefilter"):
                        analyzer = GeminiAnalyzer(api_key="test-api-key")
                        analyzer._genai = mock_genai
                        with pytest.raises(AnalysisError, match="Gemini file processing failed"):
                            analyzer.analyze(mock_temp_video_file)

    def test_analyze_missing_file(self):
        """Test error when video file does not exist."""
        mock_genai = MagicMock()
        with patch.dict("sys.modules", {"google.generativeai": mock_genai, "google": MagicMock(generativeai=mock_genai)}):
            with patch("warnings.catch_warnings"):
                with patch("warnings.simplefilter"):
                    analyzer = GeminiAnalyzer(api_key="test-api-key")
                    with pytest.raises(ValueError, match="Video file not found"):
                        analyzer.analyze("/nonexistent/path/video.mp4")


class TestOpenRouterAnalyzer:
    """Test OpenRouterAnalyzer class."""

    def test_init_requires_api_key(self):
        """Test that OpenRouterAnalyzer requires an API key."""
        with pytest.raises(ValueError, match="requires a non-empty api_key"):
            OpenRouterAnalyzer(api_key="")

    @patch("shared.video_analyzer.requests.post")
    def test_analyze_url_with_incident(self, mock_post, sample_incident_detected):
        """Test successful analysis with incident via analyze_url."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(sample_incident_detected)}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        result = analyzer.analyze_url("https://example.com/video.mp4")

        assert result["incident_detected"] is True
        assert result["severity"] == "high"

        # Verify API call
        call_args = mock_post.call_args
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-api-key"
        assert call_args[1]["json"]["model"] == "minimax/minimax-m3"
        # Verify the URL is passed directly (not base64-encoded)
        content = call_args[1]["json"]["messages"][0]["content"]
        video_entry = [item for item in content if item.get("type") == "video_url"][0]
        assert video_entry["video_url"]["url"] == "https://example.com/video.mp4"

    @patch("shared.video_analyzer.requests.post")
    def test_analyze_url_no_incident(self, mock_post, sample_incident_no_detection):
        """Test successful analysis with no incident via analyze_url."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(sample_incident_no_detection)}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        result = analyzer.analyze_url("https://example.com/video.mp4")

        assert result["incident_detected"] is False
        assert result["severity"] == "none"

    @patch("shared.video_analyzer.requests.post")
    def test_analyze_url_strips_markdown_fences(self, mock_post):
        """Test that markdown code fences around JSON are stripped."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '```json\n{"incident_detected": false, "severity": "none", "incidents": [], "scene_summary": "test", "reasoning": "test"}\n```'}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        result = analyzer.analyze_url("https://example.com/video.mp4")

        assert result["incident_detected"] is False

    @patch("shared.video_analyzer.requests.post")
    def test_analyze_url_invalid_response(self, mock_post):
        """Test handling of malformed response from OpenRouter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not valid json"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        with pytest.raises(AnalysisError):
            analyzer.analyze_url("https://example.com/video.mp4")

    @patch("shared.video_analyzer.requests.post")
    def test_analyze_url_null_content(self, mock_post):
        """Test that null content (silent rejection) raises a clear error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"finish_reason": None, "message": {"content": None}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        with pytest.raises(AnalysisError, match="null content"):
            analyzer.analyze_url("https://example.com/video.mp4")

    @patch("shared.video_analyzer.requests.post")
    def test_analyze_url_api_error(self, mock_post):
        """Test API error handling during analysis."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_post.return_value = mock_response

        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        with pytest.raises(AnalysisError):
            analyzer.analyze_url("https://example.com/video.mp4")

    def test_analyze_url_requires_http(self):
        """Test that analyze_url rejects non-HTTP URLs."""
        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        with pytest.raises(AnalysisError, match="HTTP/HTTPS URL"):
            analyzer.analyze_url("/local/path/video.mp4")

    def test_analyze_path_raises_clear_error(self):
        """Test that calling analyze(path) raises a clear AnalysisError."""
        analyzer = OpenRouterAnalyzer(api_key="test-api-key")
        with patch("os.path.exists", return_value=True):
            with pytest.raises(AnalysisError, match="analyze_url"):
                analyzer.analyze("/some/path/video.mp4")


class TestSeverityConstants:
    """Test severity ranking and emoji constants."""

    def test_severity_rank_order(self):
        """Test that severity rank mapping has correct order."""
        assert SEVERITY_RANK["none"] < SEVERITY_RANK["low"]
        assert SEVERITY_RANK["low"] < SEVERITY_RANK["medium"]
        assert SEVERITY_RANK["medium"] < SEVERITY_RANK["high"]
        assert SEVERITY_RANK["high"] < SEVERITY_RANK["critical"]

    def test_all_severities_have_emoji(self):
        """Test that all severity levels have corresponding emojis."""
        for severity in SEVERITY_RANK.keys():
            assert severity in SEVERITY_EMOJI
            assert isinstance(SEVERITY_EMOJI[severity], str)
            assert len(SEVERITY_EMOJI[severity]) > 0

    def test_valid_incident_types(self):
        """Test that valid incident types are defined."""
        expected_types = {
            "NEAR_MISS",
            "RED_LIGHT_VIOLATION",
            "WRONG_WAY",
            "DANGEROUS_OVERTAKE",
            "PEDESTRIAN_IN_ROAD",
            "VEHICLE_STOPPED_DANGEROUSLY",
            "AGGRESSIVE_DRIVING",
            "CYCLIST_RISK",
        }
        assert VALID_INCIDENT_TYPES == expected_types
