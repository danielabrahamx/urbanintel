"""Tests for FastAPI server endpoints."""
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Mock supabase before importing api_server
sys.modules['supabase'] = MagicMock()

from api_server import app, AnalyzeRequest


client = TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint(self):
        """Test health endpoint returns correct status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "model" in data

    def test_health_endpoint_get_only(self):
        """Test that health endpoint only accepts GET."""
        response = client.post("/health")
        assert response.status_code == 405  # Method not allowed

        response = client.put("/health")
        assert response.status_code == 405


class TestAnalyzeEndpointSuccess:
    """Test successful video analysis endpoint."""

    @patch("shared.video_analyzer.requests.get")
    @patch("shared.video_analyzer.OpenRouterAnalyzer.analyze")
    def test_analyze_endpoint_success(self, mock_analyze, mock_requests_get):
        """Test successful video analysis with incident detection."""
        # Setup mock video download
        mock_response = MagicMock()
        mock_response.content = b"fake video content"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        # Setup mock analysis result
        mock_analyze.return_value = {
            "incident_detected": True,
            "severity": "high",
            "incidents": [
                {
                    "type": "NEAR_MISS",
                    "severity": "high",
                    "description": "Vehicle came close to pedestrian",
                    "confidence": "high",
                    "timestamp_in_clip": "0:03",
                }
            ],
            "scene_summary": "Busy intersection",
            "reasoning": "Near miss detected",
        }

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={
                    "video_url": "https://example.com/video.mp4",
                    "camera_id": "JamCams_00001.07350",
                    "camera_name": "Test Camera",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["incident_detected"] is True
        assert data["severity"] == "high"
        assert len(data["incidents"]) == 1
        assert data["incidents"][0]["type"] == "NEAR_MISS"

    @patch("shared.video_analyzer.requests.get")
    @patch("shared.video_analyzer.OpenRouterAnalyzer.analyze")
    def test_analyze_endpoint_no_incident(self, mock_analyze, mock_requests_get):
        """Test successful video analysis with no incident."""
        mock_response = MagicMock()
        mock_response.content = b"fake video content"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_analyze.return_value = {
            "incident_detected": False,
            "severity": "none",
            "incidents": [],
            "scene_summary": "Clear intersection",
            "reasoning": "No incidents detected",
        }

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={"video_url": "https://example.com/video.mp4"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["incident_detected"] is False
        assert data["severity"] == "none"
        assert data["incidents"] == []

    @patch("shared.video_analyzer.requests.get")
    @patch("shared.video_analyzer.OpenRouterAnalyzer.analyze")
    def test_analyze_endpoint_optional_fields(self, mock_analyze, mock_requests_get):
        """Test that camera_id and camera_name are optional."""
        mock_response = MagicMock()
        mock_response.content = b"fake video content"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_analyze.return_value = {
            "incident_detected": False,
            "severity": "none",
            "incidents": [],
            "scene_summary": "Test",
            "reasoning": "Test",
        }

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            # Request without optional fields
            response = client.post(
                "/analyze",
                json={"video_url": "https://example.com/video.mp4"},
            )

        assert response.status_code == 200


class TestAnalyzeEndpointValidation:
    """Test validation on analyze endpoint."""

    def test_analyze_endpoint_missing_video_url(self):
        """Test error when video_url is missing."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post("/analyze", json={})

        assert response.status_code == 422  # Validation error

    def test_analyze_endpoint_invalid_video_url(self):
        """Test error when video_url is not a valid HTTP URL."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post("/analyze", json={"video_url": "not-a-url"})

        assert response.status_code == 422

    def test_analyze_endpoint_invalid_lat(self):
        """Test error when lat is out of range."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={
                    "video_url": "https://example.com/video.mp4",
                    "lat": 100.0,  # Invalid: must be -90 to 90
                },
            )

        assert response.status_code == 422

    def test_analyze_endpoint_invalid_lon(self):
        """Test error when lon is out of range."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={
                    "video_url": "https://example.com/video.mp4",
                    "lon": 200.0,  # Invalid: must be -180 to 180
                },
            )

        assert response.status_code == 422

    def test_analyze_endpoint_invalid_source(self):
        """Test error when source is not a valid value."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={
                    "video_url": "https://example.com/video.mp4",
                    "source": "invalid",
                },
            )

        assert response.status_code == 422


class TestAnalyzeEndpointErrorHandling:
    """Test error handling on analyze endpoint."""

    def test_analyze_endpoint_missing_api_key(self):
        """Test error when OPENROUTER_API_KEY is not configured."""
        with patch.dict("os.environ", {}, clear=True):
            response = client.post(
                "/analyze",
                json={"video_url": "https://example.com/video.mp4"},
            )

        assert response.status_code == 500
        assert "OPENROUTER_API_KEY" in response.json()["detail"]

    @patch("shared.video_analyzer.requests.get")
    def test_analyze_endpoint_download_failure(self, mock_requests_get):
        """Test error handling when video download fails."""
        import requests

        mock_requests_get.side_effect = requests.RequestException("Connection failed")

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={"video_url": "https://example.com/video.mp4"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "Failed to download video" in data["detail"]

    @patch("shared.video_analyzer.requests.get")
    def test_analyze_endpoint_http_error(self, mock_requests_get):
        """Test error handling when video URL returns HTTP error."""
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_requests_get.return_value = mock_response

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={"video_url": "https://example.com/missing.mp4"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "Failed to download video" in data["detail"]

    @patch("shared.video_analyzer.requests.get")
    @patch("shared.video_analyzer.OpenRouterAnalyzer.analyze")
    def test_analyze_endpoint_analysis_failure(self, mock_analyze, mock_requests_get):
        """Test error handling when video analysis fails."""
        mock_response = MagicMock()
        mock_response.content = b"fake video content"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_analyze.side_effect = Exception("AI analysis failed")

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={"video_url": "https://example.com/video.mp4"},
            )

        assert response.status_code == 500
        assert "Analysis failed" in response.json()["detail"]


class TestAnalyzeEndpointTempFileCleanup:
    """Test temporary file cleanup."""

    @patch("shared.video_analyzer.requests.get")
    @patch("shared.video_analyzer.OpenRouterAnalyzer.analyze")
    @patch("os.path.exists")
    @patch("os.unlink")
    def test_temp_file_cleanup_on_success(
        self, mock_unlink, mock_exists, mock_analyze, mock_requests_get
    ):
        """Test that temp file is cleaned up after successful analysis."""
        mock_response = MagicMock()
        mock_response.content = b"fake video content"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_analyze.return_value = {
            "incident_detected": False,
            "severity": "none",
            "incidents": [],
            "scene_summary": "Test",
            "reasoning": "Test",
        }

        mock_exists.return_value = True

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-api-key"}):
            response = client.post(
                "/analyze",
                json={"video_url": "https://example.com/video.mp4"},
            )

        assert response.status_code == 200
        mock_unlink.assert_called_once()


class TestCORSMiddleware:
    """Test CORS middleware configuration."""

    def test_cors_preflight_request(self):
        """Test CORS preflight request handling."""
        response = client.options(
            "/analyze",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_headers_present(self):
        """Test that CORS headers are present in responses."""
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})

        assert "access-control-allow-origin" in response.headers


class TestResponseModel:
    """Test response model structure."""

    def test_analyze_response_model_fields(self):
        """Test that AnalyzeResponse model has all required fields."""
        from api_server import AnalyzeResponse

        # Create instance with all fields
        response = AnalyzeResponse(
            incident_detected=True,
            severity="high",
            incidents=[{"type": "NEAR_MISS"}],
            scene_summary="Test scene",
            reasoning="Test reasoning",
        )

        assert response.incident_detected is True
        assert response.severity == "high"
        assert len(response.incidents) == 1
        assert response.scene_summary == "Test scene"
        assert response.reasoning == "Test reasoning"

    def test_analyze_request_model(self):
        """Test that AnalyzeRequest model accepts all fields."""
        from api_server import AnalyzeRequest

        # With all fields
        request = AnalyzeRequest(
            video_url="https://example.com/video.mp4",
            camera_id="JamCams_00001.07350",
            camera_name="Test Camera",
            lat=51.5074,
            lon=-0.1278,
            source="tfl",
        )
        assert request.video_url == "https://example.com/video.mp4"
        assert request.camera_id == "JamCams_00001.07350"
        assert request.camera_name == "Test Camera"
        assert request.lat == 51.5074
        assert request.lon == -0.1278
        assert request.source == "tfl"

        # With only required field and defaults
        request_minimal = AnalyzeRequest(video_url="https://example.com/video.mp4")
        assert request_minimal.video_url == "https://example.com/video.mp4"
        assert request_minimal.camera_id is None
        assert request_minimal.source == "tfl"  # default

    def test_analyze_request_url_validation(self):
        """Test URL validation in AnalyzeRequest."""
        from api_server import AnalyzeRequest

        # Valid URLs
        req1 = AnalyzeRequest(video_url="http://example.com/video.mp4")
        assert req1.video_url == "http://example.com/video.mp4"

        req2 = AnalyzeRequest(video_url="https://example.com/video.mp4")
        assert req2.video_url == "https://example.com/video.mp4"

        # Invalid URL - should raise validation error during model creation
        with pytest.raises(ValueError):
            AnalyzeRequest(video_url="ftp://example.com/video.mp4")

    def test_analyze_request_lat_lon_validation(self):
        """Test lat/lon validation in AnalyzeRequest."""
        from api_server import AnalyzeRequest

        # Valid coordinates
        req = AnalyzeRequest(
            video_url="https://example.com/video.mp4",
            lat=51.5074,
            lon=-0.1278,
        )
        assert req.lat == 51.5074
        assert req.lon == -0.1278

        # Invalid lat - should raise validation error
        with pytest.raises(ValueError):
            AnalyzeRequest(
                video_url="https://example.com/video.mp4",
                lat=100.0,
            )

        # Invalid lon - should raise validation error
        with pytest.raises(ValueError):
            AnalyzeRequest(
                video_url="https://example.com/video.mp4",
                lon=200.0,
            )

    def test_analyze_request_source_validation(self):
        """Test source validation in AnalyzeRequest."""
        from api_server import AnalyzeRequest

        # Valid sources
        for source in ["tfl", "manual", "upload"]:
            req = AnalyzeRequest(
                video_url="https://example.com/video.mp4",
                source=source,
            )
            assert req.source == source

        # Invalid source - should raise validation error
        with pytest.raises(ValueError):
            AnalyzeRequest(
                video_url="https://example.com/video.mp4",
                source="invalid",
            )
