"""Tests for TfL API client (shared.tfl_client)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from shared.tfl_client import (
    TflClient,
    TflApiError,
    CameraNotFoundError,
    TFL_API,
)


class TestTflClientInit:
    """Test TflClient initialization."""

    def test_default_init(self):
        """Test client initializes with default values."""
        client = TflClient()
        assert client._app_key == ""
        assert client._max_retries == 3
        assert client._backoff_base == 2.0
        assert client._timeout == 15

    def test_custom_init(self):
        """Test client initializes with custom values."""
        client = TflClient(
            app_key="test-key",
            max_retries=5,
            backoff_base=1.5,
            timeout=30,
        )
        assert client._app_key == "test-key"
        assert client._max_retries == 5
        assert client._backoff_base == 1.5
        assert client._timeout == 30


class TestGetCameraVideoUrlSuccess:
    """Test successful camera video URL retrieval."""

    @patch("shared.tfl_client.requests.get")
    def test_get_camera_video_url_success(self, mock_get, sample_camera_response, sample_camera_id):
        """Test successful retrieval of camera video URL with all data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_camera_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = TflClient(app_key="test-key")
        url, name, lat, lon = client.get_camera_video_url(sample_camera_id)

        assert url == "https://example.com/video1.mp4"
        assert name == "Test Junction Camera"
        assert lat == 51.5074
        assert lon == -0.1278

        # Verify API key was passed
        call_args = mock_get.call_args
        assert call_args[1]["params"] == {"app_key": "test-key"}
        assert call_args[1]["timeout"] == 15

    @patch("shared.tfl_client.requests.get")
    def test_get_camera_without_api_key(self, mock_get, sample_camera_response, sample_camera_id):
        """Test retrieval works without API key (anonymous access)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_camera_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = TflClient()  # No API key
        url, name, lat, lon = client.get_camera_video_url(sample_camera_id)

        assert url == "https://example.com/video1.mp4"

        # Verify no API key was passed
        call_args = mock_get.call_args
        assert call_args[1]["params"] == {}


class TestCameraNotFound:
    """Test camera not found scenarios."""

    @patch("shared.tfl_client.requests.get")
    def test_camera_not_found(self, mock_get, sample_camera_id):
        """Test CameraNotFoundError raised when camera ID is not in API response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "JamCams_99999.99999", "commonName": "Other Camera"}
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = TflClient()
        with pytest.raises(CameraNotFoundError, match="Camera 'JamCams_00001.07350' not found"):
            client.get_camera_video_url(sample_camera_id)

    @patch("shared.tfl_client.requests.get")
    def test_camera_no_video_url(self, mock_get, sample_camera_no_video, sample_camera_id):
        """Test CameraNotFoundError raised when camera exists but has no videoUrl."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_camera_no_video
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = TflClient()
        with pytest.raises(CameraNotFoundError, match="found in feed but has no videoUrl"):
            client.get_camera_video_url(sample_camera_id)

    @patch("shared.tfl_client.requests.get")
    def test_camera_empty_video_url(self, mock_get, sample_camera_id):
        """Test CameraNotFoundError raised when camera has empty videoUrl."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": sample_camera_id,
                "commonName": "Test Camera",
                "additionalProperties": [
                    {"key": "videoUrl", "value": ""},  # Empty URL
                ],
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = TflClient()
        with pytest.raises(CameraNotFoundError, match="empty videoUrl"):
            client.get_camera_video_url(sample_camera_id)


class TestCameraIdValidation:
    """Test camera ID input validation."""

    def test_invalid_camera_id_empty(self):
        """Test ValueError raised for empty camera_id."""
        client = TflClient()
        with pytest.raises(ValueError, match="camera_id must be a non-empty string"):
            client.get_camera_video_url("")

    def test_invalid_camera_id_wrong_prefix(self):
        """Test ValueError raised for camera_id not starting with JamCams_."""
        client = TflClient()
        with pytest.raises(ValueError, match="expected it to start with 'JamCams_'"):
            client.get_camera_video_url("InvalidCameraID")

    def test_invalid_camera_id_none(self):
        """Test ValueError raised for None camera_id."""
        client = TflClient()
        with pytest.raises(ValueError, match="camera_id must be a non-empty string"):
            client.get_camera_video_url(None)


class TestApiErrorHandling:
    """Test API error handling scenarios."""

    @patch("shared.tfl_client.requests.get")
    def test_api_error_http_error(self, mock_get):
        """Test TflApiError raised on HTTP errors from TfL API."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = mock_response

        client = TflClient(max_retries=1)
        with pytest.raises(TflApiError):
            client.get_camera_video_url("JamCams_00001.07350")

    @patch("shared.tfl_client.requests.get")
    def test_api_error_connection_error(self, mock_get):
        """Test TflApiError raised on connection errors."""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        client = TflClient(max_retries=1)
        with pytest.raises(TflApiError):
            client.get_camera_video_url("JamCams_00001.07350")

    @patch("shared.tfl_client.requests.get")
    def test_api_error_timeout(self, mock_get):
        """Test TflApiError raised on timeout errors."""
        mock_get.side_effect = requests.Timeout("Request timed out")

        client = TflClient(max_retries=1)
        with pytest.raises(TflApiError):
            client.get_camera_video_url("JamCams_00001.07350")

    @patch("shared.tfl_client.requests.get")
    def test_api_error_invalid_json(self, mock_get):
        """Test TflApiError raised when API returns non-JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"not": "a list"}  # Should be a list
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = TflClient()
        with pytest.raises(TflApiError, match="Expected a JSON array"):
            client.get_camera_video_url("JamCams_00001.07350")


class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    @patch("shared.tfl_client.requests.get")
    @patch("shared.tfl_client.time.sleep")
    def test_retry_on_429(self, mock_sleep, mock_get, sample_camera_response, sample_camera_id):
        """Test retry on rate limit (429) response."""
        # First call returns 429, second call succeeds
        error_response = MagicMock()
        error_response.status_code = 429
        error_response.raise_for_status.side_effect = requests.HTTPError("429 Rate Limited")

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = sample_camera_response
        success_response.raise_for_status.return_value = None

        mock_get.side_effect = [error_response, success_response]

        client = TflClient(max_retries=2, backoff_base=2.0)
        url, name, lat, lon = client.get_camera_video_url(sample_camera_id)

        assert url == "https://example.com/video1.mp4"
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once()  # Should sleep between retries

    @patch("shared.tfl_client.requests.get")
    @patch("shared.tfl_client.time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep, mock_get):
        """Test that retry delays increase exponentially."""
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.raise_for_status.side_effect = requests.HTTPError("503 Service Unavailable")

        mock_get.side_effect = [error_response, error_response, error_response]

        client = TflClient(max_retries=3, backoff_base=2.0)
        with pytest.raises(TflApiError):
            client.get_camera_video_url("JamCams_00001.07350")

        # Should sleep with exponential backoff: 2^1=2s, 2^2=4s
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 2.0
        assert mock_sleep.call_args_list[1][0][0] == 4.0


class TestListCameras:
    """Test list_cameras method."""

    @patch("shared.tfl_client.requests.get")
    def test_list_cameras_success(self, mock_get, sample_camera_response):
        """Test successful retrieval of all cameras."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_camera_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = TflClient()
        cameras = client.list_cameras()

        assert len(cameras) == 2
        assert cameras[0]["id"] == "JamCams_00001.07350"
        assert cameras[1]["id"] == "JamCams_00002.12345"


class TestTflApiConstant:
    """Test TFL_API constant."""

    def test_tfl_api_constant(self):
        """Test that TFL_API constant is correctly defined."""
        assert TFL_API == "https://api.tfl.gov.uk/Place/Type/JamCam"
