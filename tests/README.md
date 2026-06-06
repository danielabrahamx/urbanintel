# Urban Intelligence Test Suite

Comprehensive test suite for the Urban Intelligence traffic monitoring system. All tests are fast, isolated, and use mocking to avoid real API calls.

## Running Tests

### Run all tests
```bash
python -m pytest tests/
```

### Run with verbose output
```bash
python -m pytest tests/ -v
```

### Run specific test file
```bash
python -m pytest tests/test_tfl_client.py -v
python -m pytest tests/test_video_analyzer.py -v
python -m pytest tests/test_incident_repository.py -v
python -m pytest tests/test_config.py -v
python -m pytest tests/test_api_server.py -v
```

### Run specific test class
```bash
python -m pytest tests/test_tfl_client.py::TestGetCameraVideoUrlSuccess -v
```

### Run specific test
```bash
python -m pytest tests/test_tfl_client.py::TestGetCameraVideoUrlSuccess::test_get_camera_video_url_success -v
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and utilities
├── test_tfl_client.py       # TfL API client tests
├── test_video_analyzer.py   # Video analysis (Gemini + OpenRouter) tests
├── test_incident_repository.py  # Supabase database tests
├── test_config.py           # Configuration tests
├── test_api_server.py       # FastAPI endpoint tests
└── README.md               # This file
```

## Fixtures (conftest.py)

### Sample Data Fixtures
- `sample_camera_id` - Sample TfL camera ID
- `sample_camera_response` - Sample TfL API response
- `sample_camera_no_video` - Camera without video URL
- `sample_incident_detected` - AI result with incident
- `sample_incident_no_detection` - AI result with no incident
- `sample_incident_low_severity` - Low severity incident result
- `sample_invalid_response` - Malformed AI response

### Mock Fixtures
- `mock_supabase` - Mock Supabase client with chainable operations
- `mock_analyzer` - Mock video analyzer function
- `mock_requests_response` - Factory for mock HTTP responses
- `mock_temp_video_file` - Temporary video file for testing

### Environment Fixtures
- `clean_env` - Clean environment variables
- `mock_env_vars` - Set up mock environment variables

## Test Coverage

### TfL Client (`test_tfl_client.py`)
- `test_get_camera_video_url_success` - Successful video URL retrieval
- `test_get_camera_not_found` - Camera ID not found error
- `test_get_camera_no_video_url` - Camera exists but no video URL
- `test_api_error_handling` - HTTP, connection, timeout errors
- `test_download_video_success` - Video download to temp file

### Video Analyzer (`test_video_analyzer.py`)
- `test_analyze_with_incident` - Incident detection via Gemini
- `test_analyze_no_incident` - Clear scene detection
- `test_analyze_invalid_response` - Malformed JSON handling
- `test_analyze_file_processing_polling` - File processing state polling
- `test_analyze_file_processing_failed` - Failed file processing
- Tests for OpenRouter implementation with same scenarios

### Incident Repository (`test_incident_repository.py`)
- `test_save_incident_success` - Write incident to Supabase
- `test_save_incident_validation_error` - Invalid data handling
- `test_save_incident_database_error` - DB failure handling
- `test_update_camera_status` - Camera status updates
- `test_init_supabase_*` - Client initialization tests

### Config (`test_config.py`)
- `test_load_config_success` - Config loading
- `test_load_config_missing_required` - Missing optional config
- `test_alert_threshold_valid_values` - Threshold validation
- `test_poll_interval_positive` - Interval validation
- `test_severity_rank_mapping` - Severity ordering

### API Server (`test_api_server.py`)
- `test_health_endpoint` - Health check
- `test_analyze_endpoint_success` - Video analysis endpoint
- `test_analyze_endpoint_validation_error` - Input validation
- `test_analyze_endpoint_download_failure` - Download error handling
- `test_temp_file_cleanup_*` - Resource cleanup
- `test_cors_*` - CORS middleware

## Key Principles

1. **No Real API Calls** - All external services are mocked
2. **Fast Execution** - No sleeping, no real downloads
3. **Independent Tests** - Each test can run in isolation
4. **Clear Names** - Test names describe what's being tested
5. **Proper Cleanup** - Temporary files and patches cleaned up

## Adding New Tests

1. Add shared fixtures to `conftest.py`
2. Create test class in appropriate test file
3. Use descriptive test names starting with `test_`
4. Use existing fixtures where possible
5. Mock external dependencies
6. Clean up resources in `finally` blocks or use context managers

## Configuration

Tests are configured in `pytest.ini`:
- Verbose output enabled
- Short tracebacks
- Warnings disabled for cleaner output
- Markers for slow/integration tests

## Troubleshooting

### Import errors
Ensure you're running from the project root:
```bash
cd c:/Users/danie/urbanintel
python -m pytest tests/
```

### Module not found
The test suite adds the parent directory to `sys.path` in `conftest.py`.
If imports fail, verify the project structure is correct.

### Mock not working
Ensure patches target the correct import path (e.g., `main.requests.get` not just `requests.get`).
