"""Pytest fixtures and utilities for Urban Intelligence test suite."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_camera_id():
    """Sample TfL camera ID."""
    return "JamCams_00001.07350"


@pytest.fixture
def sample_camera_response():
    """Sample TfL API response for a camera with video URL."""
    return [
        {
            "id": "JamCams_00001.07350",
            "commonName": "Test Junction Camera",
            "lat": 51.5074,
            "lon": -0.1278,
            "additionalProperties": [
                {"key": "videoUrl", "value": "https://example.com/video1.mp4"},
                {"key": "otherProp", "value": "ignored"},
            ],
        },
        {
            "id": "JamCams_00002.12345",
            "commonName": "Other Camera",
            "lat": 51.5,
            "lon": -0.1,
            "additionalProperties": [
                {"key": "videoUrl", "value": "https://example.com/video2.mp4"},
            ],
        },
    ]


@pytest.fixture
def sample_camera_no_video():
    """Sample TfL API response for a camera without video URL."""
    return [
        {
            "id": "JamCams_00001.07350",
            "commonName": "Broken Camera",
            "lat": 51.5074,
            "lon": -0.1278,
            "additionalProperties": [
                {"key": "otherProp", "value": "no video here"},
            ],
        }
    ]


@pytest.fixture
def sample_incident_detected():
    """Sample AI analysis result with incident detected."""
    return {
        "incident_detected": True,
        "severity": "high",
        "incidents": [
            {
                "type": "NEAR_MISS",
                "severity": "high",
                "description": "Vehicle came dangerously close to pedestrian",
                "confidence": "high",
                "timestamp_in_clip": "0:04",
            }
        ],
        "scene_summary": "Busy junction with heavy pedestrian traffic",
        "reasoning": "Detected near-miss incident with high confidence",
    }


@pytest.fixture
def sample_incident_no_detection():
    """Sample AI analysis result with no incident."""
    return {
        "incident_detected": False,
        "severity": "none",
        "incidents": [],
        "scene_summary": "Normal traffic flow at junction",
        "reasoning": "No dangerous driving behavior observed",
    }


@pytest.fixture
def sample_incident_low_severity():
    """Sample AI analysis result with low severity incident."""
    return {
        "incident_detected": True,
        "severity": "low",
        "incidents": [
            {
                "type": "VEHICLE_STOPPED_DANGEROUSLY",
                "severity": "low",
                "description": "Vehicle stopped briefly at junction",
                "confidence": "medium",
                "timestamp_in_clip": "0:02",
            }
        ],
        "scene_summary": "Light traffic with brief stop",
        "reasoning": "Minor traffic violation detected",
    }


@pytest.fixture
def sample_invalid_response():
    """Sample invalid/incorrect AI response."""
    return {
        "invalid_field": "this is not a valid response",
    }


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_supabase():
    """Mock Supabase client with chainable table operations."""
    mock_client = MagicMock()
    
    # Create chainable mock for table operations
    mock_table = MagicMock()
    mock_insert = MagicMock()
    mock_upsert = MagicMock()
    mock_execute = MagicMock()
    
    # Set up the chain: client.table().insert().execute()
    mock_table.insert.return_value = mock_insert
    mock_table.upsert.return_value = mock_upsert
    mock_insert.execute.return_value = mock_execute
    mock_upsert.execute.return_value = mock_execute
    mock_client.table.return_value = mock_table
    
    return mock_client


@pytest.fixture
def mock_analyzer():
    """Mock video analyzer that returns configurable results."""
    analyzer = MagicMock()
    analyzer.return_value = {
        "incident_detected": False,
        "severity": "none",
        "incidents": [],
        "scene_summary": "Mock analysis result",
        "reasoning": "Mock reasoning",
    }
    return analyzer


@pytest.fixture
def mock_requests_response():
    """Factory fixture for creating mock requests responses."""
    def _create_response(json_data=None, status_code=200, content=None, raise_error=None):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data if json_data is not None else {}
        if content is not None:
            response.content = content
        else:
            response.content = b"mock video content"
        
        if raise_error:
            response.raise_for_status.side_effect = raise_error
        else:
            response.raise_for_status.return_value = None
        
        return response
    return _create_response


@pytest.fixture
def mock_temp_video_file():
    """Create a temporary video file for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.write(b"mock video content")
    tmp.close()
    
    yield tmp.name
    
    # Cleanup
    try:
        os.unlink(tmp.name)
    except FileNotFoundError:
        pass


# =============================================================================
# Environment Fixtures
# =============================================================================

@pytest.fixture
def clean_env():
    """Clean environment variables for config testing."""
    # Save original env vars
    original_env = {}
    env_vars_to_clear = [
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "TFL_APP_KEY",
        "TFL_APP_ID",
        "NEXT_PUBLIC_SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]
    
    for var in env_vars_to_clear:
        original_env[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]
    
    yield
    
    # Restore original env vars
    for var, value in original_env.items():
        if value is not None:
            os.environ[var] = value


@pytest.fixture
def mock_env_vars():
    """Set up mock environment variables."""
    env_vars = {
        "GEMINI_API_KEY": "test-gemini-key-12345",
        "OPENROUTER_API_KEY": "test-openrouter-key-12345",
        "TFL_APP_KEY": "test-tfl-key-12345",
        "NEXT_PUBLIC_SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-key-12345",
    }
    
    for key, value in env_vars.items():
        os.environ[key] = value
    
    yield env_vars
    
    # Cleanup handled by clean_env fixture if used together, or manually



