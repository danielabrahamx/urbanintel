"""Tests for incident repository (shared.incident_repository)."""
import sys
from unittest.mock import MagicMock, patch

import pytest

from shared.incident_repository import (
    IncidentRepository,
    RepositoryError,
    ValidationError,
    VALID_SEVERITIES,
    VALID_CAMERA_STATUSES,
)


class TestIncidentRepositoryInit:
    """Test IncidentRepository initialization."""

    def test_init_with_client(self):
        """Test initialization with Supabase client."""
        mock_client = MagicMock()
        repo = IncidentRepository(mock_client)
        assert repo._client == mock_client
        assert repo.is_connected is True

    def test_init_without_client(self):
        """Test initialization without Supabase client."""
        repo = IncidentRepository(None)
        assert repo._client is None
        assert repo.is_connected is False


class TestIncidentRepositoryFromEnv:
    """Test factory method from_env."""

    @patch.dict("os.environ", {
        "NEXT_PUBLIC_SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-key",
    })
    def test_from_env_success(self):
        """Test successful creation from environment variables."""
        # Patch the supabase module where it's used inside from_env
        mock_client = MagicMock()
        mock_create_client = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"supabase": MagicMock(create_client=mock_create_client)}):
            repo = IncidentRepository.from_env()

            assert repo is not None
            assert repo.is_connected is True
            mock_create_client.assert_called_once_with("https://test.supabase.co", "test-key")

    def test_from_env_missing_url(self):
        """Test returns None when Supabase URL is missing."""
        with patch.dict("os.environ", {}, clear=True):
            repo = IncidentRepository.from_env()
        assert repo is None

    def test_from_env_missing_key(self):
        """Test returns None when Service Role Key is missing."""
        with patch.dict("os.environ", {"NEXT_PUBLIC_SUPABASE_URL": "https://test.supabase.co"}, clear=True):
            repo = IncidentRepository.from_env()
        assert repo is None

    @patch.dict("os.environ", {
        "NEXT_PUBLIC_SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-key",
    })
    def test_from_env_init_failure(self):
        """Test RepositoryError raised when client creation fails."""
        mock_create_client = MagicMock(side_effect=Exception("Connection failed"))

        with patch.dict("sys.modules", {"supabase": MagicMock(create_client=mock_create_client)}):
            with pytest.raises(RepositoryError, match="Supabase client init failed"):
                IncidentRepository.from_env()


class TestSaveIncident:
    """Test saving incidents to database."""

    def test_save_incident_success(self, mock_supabase, sample_incident_detected, sample_camera_id):
        """Test successful incident write to database."""
        repo = IncidentRepository(mock_supabase)

        repo.save(
            analysis_result=sample_incident_detected,
            camera_id=sample_camera_id,
            camera_name="Test Camera",
            lat=51.5074,
            lon=-0.1278,
            source="gemini",
        )

        # Verify table was accessed
        mock_supabase.table.assert_called_once_with("incidents")

        # Verify insert was called with correct data
        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["camera_id"] == sample_camera_id
        assert call_args["camera_name"] == "Test Camera"
        assert call_args["lat"] == 51.5074
        assert call_args["lon"] == -0.1278
        assert call_args["incident_detected"] is True
        assert call_args["severity"] == "high"
        assert call_args["incidents"] == sample_incident_detected["incidents"]
        assert call_args["scene_summary"] == sample_incident_detected["scene_summary"]
        assert call_args["reasoning"] == sample_incident_detected["reasoning"]
        assert call_args["raw_response"] == sample_incident_detected
        assert call_args["source"] == "gemini"

    def test_save_no_detection(self, mock_supabase, sample_incident_no_detection, sample_camera_id):
        """Test writing incident result with no detection."""
        repo = IncidentRepository(mock_supabase)

        repo.save(
            analysis_result=sample_incident_no_detection,
            camera_id=sample_camera_id,
            camera_name="Test Camera",
            lat=51.5074,
            lon=-0.1278,
        )

        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["incident_detected"] is False
        assert call_args["severity"] == "none"
        assert call_args["incidents"] == []
        assert call_args["source"] == "gemini"  # default

    def test_save_null_client(self, sample_incident_detected, sample_camera_id):
        """Test that save returns early when client is None."""
        repo = IncidentRepository(None)

        # Should not raise any error
        repo.save(
            analysis_result=sample_incident_detected,
            camera_id=sample_camera_id,
            camera_name="Test Camera",
            lat=51.5074,
            lon=-0.1278,
        )

    def test_save_database_error(self, mock_supabase, sample_incident_detected, sample_camera_id):
        """Test RepositoryError raised when database insert fails."""
        mock_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("DB Error")

        repo = IncidentRepository(mock_supabase)
        with pytest.raises(RepositoryError, match="Failed to write incident"):
            repo.save(
                analysis_result=sample_incident_detected,
                camera_id=sample_camera_id,
                camera_name="Test Camera",
                lat=51.5074,
                lon=-0.1278,
            )

    def test_save_invalid_camera_id(self, mock_supabase, sample_incident_detected):
        """Test ValidationError raised for invalid camera_id."""
        repo = IncidentRepository(mock_supabase)

        with pytest.raises(ValidationError, match="camera_id must be a non-empty string"):
            repo.save(
                analysis_result=sample_incident_detected,
                camera_id="",
                camera_name="Test Camera",
                lat=51.5074,
                lon=-0.1278,
            )

    def test_save_invalid_severity(self, mock_supabase, sample_camera_id):
        """Test ValidationError raised for invalid severity."""
        repo = IncidentRepository(mock_supabase)

        invalid_result = {"incident_detected": True, "severity": "invalid"}

        with pytest.raises(ValidationError, match="analysis_result.severity 'invalid' is not valid"):
            repo.save(
                analysis_result=invalid_result,
                camera_id=sample_camera_id,
                camera_name="Test Camera",
                lat=51.5074,
                lon=-0.1278,
            )

    def test_save_default_camera_name(self, mock_supabase, sample_incident_detected, sample_camera_id):
        """Test that camera_id is used as default camera_name."""
        repo = IncidentRepository(mock_supabase)

        repo.save(
            analysis_result=sample_incident_detected,
            camera_id=sample_camera_id,
            camera_name="",  # Empty name
            lat=51.5074,
            lon=-0.1278,
        )

        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["camera_name"] == sample_camera_id  # Falls back to camera_id


class TestUpdateCameraStatus:
    """Test updating camera status."""

    def test_update_status_success(self, mock_supabase, sample_camera_id):
        """Test successful camera status update."""
        repo = IncidentRepository(mock_supabase)

        repo.update_camera_status(
            camera_id=sample_camera_id,
            status="idle",
            camera_name="Test Camera",
            lat=51.5074,
            lon=-0.1278,
            video_url="https://example.com/video.mp4",
        )

        mock_supabase.table.assert_called_once_with("camera_status")

        call_args = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert call_args["camera_id"] == sample_camera_id
        assert call_args["status"] == "idle"
        assert call_args["camera_name"] == "Test Camera"
        assert call_args["lat"] == 51.5074
        assert call_args["lon"] == -0.1278
        assert call_args["video_url"] == "https://example.com/video.mp4"
        assert "last_polled_at" in call_args

    def test_update_status_error(self, mock_supabase, sample_camera_id):
        """Test error status with error message."""
        repo = IncidentRepository(mock_supabase)

        repo.update_camera_status(
            camera_id=sample_camera_id,
            status="error",
            error_message="Connection timeout",
        )

        call_args = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert call_args["status"] == "error"
        assert call_args["error_message"] == "Connection timeout"
        assert "video_url" not in call_args

    def test_update_status_error_message_truncated(self, mock_supabase, sample_camera_id):
        """Test that error messages are truncated to 500 chars."""
        repo = IncidentRepository(mock_supabase)

        long_message = "x" * 1000
        repo.update_camera_status(
            camera_id=sample_camera_id,
            status="error",
            error_message=long_message,
        )

        call_args = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert len(call_args["error_message"]) == 500

    def test_update_status_optional_fields(self, mock_supabase, sample_camera_id):
        """Test that optional fields are only included when provided."""
        repo = IncidentRepository(mock_supabase)

        repo.update_camera_status(
            camera_id=sample_camera_id,
            status="measuring",
        )

        call_args = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert call_args["status"] == "measuring"
        assert "camera_name" not in call_args
        assert "lat" not in call_args
        assert "lon" not in call_args
        assert "video_url" not in call_args
        assert "error_message" not in call_args

    def test_update_status_null_client(self, sample_camera_id):
        """Test that update returns early when client is None."""
        repo = IncidentRepository(None)

        # Should not raise any error
        repo.update_camera_status(
            camera_id=sample_camera_id,
            status="idle",
        )

    def test_update_status_database_error(self, mock_supabase, sample_camera_id):
        """Test RepositoryError raised when status update fails."""
        mock_supabase.table.return_value.upsert.return_value.execute.side_effect = Exception("DB Error")

        repo = IncidentRepository(mock_supabase)
        with pytest.raises(RepositoryError, match="Failed to update camera status"):
            repo.update_camera_status(
                camera_id=sample_camera_id,
                status="idle",
            )

    def test_update_status_invalid_camera_id(self, mock_supabase):
        """Test ValidationError raised for invalid camera_id."""
        repo = IncidentRepository(mock_supabase)

        with pytest.raises(ValidationError, match="camera_id must be a non-empty string"):
            repo.update_camera_status(
                camera_id="",
                status="idle",
            )

    def test_update_status_invalid_status(self, mock_supabase, sample_camera_id):
        """Test ValidationError raised for invalid status."""
        repo = IncidentRepository(mock_supabase)

        with pytest.raises(ValidationError, match="status 'invalid_status' is not valid"):
            repo.update_camera_status(
                camera_id=sample_camera_id,
                status="invalid_status",
            )


class TestValidationConstants:
    """Test validation constants."""

    def test_valid_severities(self):
        """Test that valid severities are correctly defined."""
        expected = {"none", "low", "medium", "high", "critical"}
        assert VALID_SEVERITIES == expected

    def test_valid_camera_statuses(self):
        """Test that valid camera statuses are correctly defined."""
        expected = {"idle", "measuring", "error", "offline"}
        assert VALID_CAMERA_STATUSES == expected


class TestOnConflict:
    """Test on_conflict parameter in upsert."""

    def test_upsert_on_conflict(self, mock_supabase, sample_camera_id):
        """Test that upsert uses correct on_conflict parameter."""
        repo = IncidentRepository(mock_supabase)

        repo.update_camera_status(
            camera_id=sample_camera_id,
            status="idle",
        )

        call_kwargs = mock_supabase.table.return_value.upsert.call_args[1]
        assert call_kwargs["on_conflict"] == "camera_id"
