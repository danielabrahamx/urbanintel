# Agent Guide - Urban Intelligence

How to work with this codebase. Read this before touching anything.

---

## Quick start (do this first)

When you open this codebase for the first time:

1. Read `.env.example` to see what env vars exist
2. Skim `config.py` to understand the tunable surface
3. Look at the file map at the bottom of this doc to orient yourself
4. Run `python -m pytest tests/ -v` to make sure the test suite passes
5. Run `cd frontend && npm run build` to make sure the frontend compiles

Do NOT start editing code until you have run the tests and the build.

---

## What this project is

Urban Intelligence watches TfL traffic cameras with AI vision models to detect road safety incidents. It has three parts:

1. **Python backend** - fetches camera clips, analyzes them, persists results
2. **FastAPI server** - REST API that the frontend calls for analysis
3. **Next.js frontend** - dashboard with map, incident table, and manual upload

---

## Architecture at a glance

```
TfL API  -->  Python backend  -->  Supabase DB
                  ^                    ^
                  |                    |
            Next.js frontend  <-------+
```

### Data flow

1. **Watcher mode** (`main.py`): polls one camera on a loop. Fetches URL from TfL, downloads MP4, sends to vision model, prints result, writes to Supabase.
2. **API mode** (`api_server.py`): frontend calls `/analyze` or `/upload`. The server handles model inference AND database persistence. The frontend never writes to the DB directly.
3. **Dashboard** (`frontend/`): reads incidents via `/api/incidents` (public), triggers analysis via `/api/analyze` (public), handles manual uploads via `/api/upload` (public).

---

## Key modules and their jobs

### `shared/tfl_client.py` - TfL API wrapper

- `TflClient.get_camera_video_url(camera_id)` returns `(video_url, camera_name, lat, lon)`
- Validates `JamCams_` prefix before any network call
- Retries with exponential back-off on 429/500/502/503/504
- Raises `CameraNotFoundError` or `TflApiError`

**When modifying**: keep retry logic intact. Camera IDs are stable but video URLs rotate.

### `shared/video_analyzer.py` - Vision model interface

- `BaseAnalyzer` (ABC) with `analyze(video_path)` and `analyze_url(video_url)`
- `GeminiAnalyzer` - uses Google Files API (upload -> poll -> infer -> delete)
- `OpenRouterAnalyzer` - sends video URL directly to OpenRouter chat completions
- `download_video()` - downloads MP4 to a temp file
- `build_analysis_prompt(source)` - returns TfL or manual framing

**Critical**: OpenRouter with minimax/minimax-m3 requires a real HTTP URL, not base64. The analyzer passes the URL directly to the model. Gemini still needs a local download.

**When adding a new model**: subclass `BaseAnalyzer`, implement `analyze()` and optionally `analyze_url()`. Add to `api_server.py` second-opinion logic if relevant.

### `shared/incident_repository.py` - Database layer

- `IncidentRepository.from_env()` returns `None` if Supabase creds missing (no-op mode)
- `repo.save(analysis_result, camera_id, camera_name, lat, lon, source, video_url, created_by)` - inserts to `incidents` table
- `repo.update_camera_status(...)` - upserts `camera_status` table

**When modifying**: validate inputs before network calls. The repo should raise `ValidationError` for bad data, `RepositoryError` for DB failures.

### `shared/config_loader.py` - Typed configuration

- `load_config(require_gemini=False, require_openrouter=False)` returns `AppConfig` dataclass
- Reads env vars, falls back to `config.py` module-level constants for backward compatibility
- `AppConfig.require_gemini_key()` and `require_openrouter_key()` raise `ConfigError` if missing

**When adding a new config value**: add it to `AppConfig`, read it in `load_config()`, and add to `.env.example`.

### `config.py` - Tunables

Module-level constants: `TARGET_CAMERA_ID`, `POLL_INTERVAL_SECONDS`, `ALERT_THRESHOLD`, `VISION_MODEL`, `DEFAULT_ANALYSIS_PROMPT`, `INCIDENT_TYPES`, `SEVERITY_ORDER`, `SEVERITY_EMOJI`.

**This is the editable surface**. Agents should read these before changing behavior. Never hardcode camera IDs, thresholds, or prompts in logic modules.

### `api_server.py` - FastAPI

Endpoints:
- `POST /analyze` - analyze video URL, persist result
- `POST /upload` - same but forces `source="manual"`
- `GET /cameras/{id}/video-url` - get current TfL URL
- `GET /health` - status check

**Auth**: none. The app is public by design. The `created_by` field is optional.

**Second opinion**: `/analyze` with `second_opinion=true` switches to Gemini instead of OpenRouter.

### `frontend/app/api/analyze/route.ts` - Frontend proxy

- Optional auth check (user can be null)
- Forwards to Python backend at `BACKEND_API_URL` or `NEXT_PUBLIC_API_URL`
- Passes `created_by: user?.id ?? null`

**When modifying**: keep auth optional. The public experience must not break.

### `frontend/app/api/upload/route.ts` - Manual upload

1. Receives multipart form (video + lat + lon + locationName)
2. Uploads to Supabase Storage private `uploads` bucket
3. Creates signed URL (1 hour)
4. Sends signed URL to Python backend `/upload`
5. Returns analysis result

**When modifying**: the service role key handles storage writes. Never expose it to the browser.

### `frontend/app/api/incidents/route.ts` - Public read

- Uses `createServiceClient()` (service role) to read incidents
- Query params: `detectedOnly`, `since`, `limit`
- Returns `{ incidents: [...] }`

**Why service role?** So anonymous visitors can see the map without depending on RLS policies.

---

## Database schema

### `incidents` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid | Primary key |
| `created_at` | timestamptz | Auto |
| `camera_id` | text | TfL JamCam ID or `manual_{timestamp}` |
| `camera_name` | text | Human-readable |
| `lat`, `lon` | float | Nullable |
| `incident_detected` | boolean | |
| `severity` | text | none / low / medium / high / critical |
| `incidents` | jsonb | Array of incident objects |
| `scene_summary` | text | |
| `reasoning` | text | |
| `raw_response` | jsonb | Full model JSON |
| `source` | text | `tfl`, `manual`, `upload` |
| `video_url` | text | For manual uploads only |
| `created_by` | uuid | Nullable, references auth.users |

### `camera_status` table

| Column | Type | Notes |
|--------|------|-------|
| `camera_id` | text | Primary key |
| `status` | text | idle / measuring / error / offline |
| `camera_name` | text | |
| `lat`, `lon` | float | |
| `last_polled_at` | timestamptz | |
| `last_incident_at` | timestamptz | |
| `incident_count_24h` | int | |
| `error_message` | text | |
| `video_url` | text | Current stream URL |
| `poll_interval_seconds` | int | |

### RLS policies

- `anon` can SELECT from `incidents` (public read)
- `authenticated` can INSERT manual incidents (checked: `source = 'manual' AND created_by = auth.uid()`)
- Admin delete via `/api/incidents/[id]` checks `ADMIN_EMAILS` env var

---

## Testing conventions

1. **Mock external APIs** - Never call TfL, Gemini, or OpenRouter in tests
2. **Use fixtures from `conftest.py`** - `mock_supabase`, `mock_requests_response`, `sample_incident_detected`
3. **Patch the right import path** - e.g. `shared.tfl_client.requests.get` not `requests.get`
4. **Clean up temp files** - use `try/finally` or context managers
5. **Run from project root** - `python -m pytest tests/ -v`

### How to test a new analyzer

```python
# In tests/test_video_analyzer.py
class TestMyAnalyzer:
    @patch("shared.video_analyzer.requests.post")
    def test_analyze_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": '{"incident_detected": true, ...}'}}]},
        )
        analyzer = MyAnalyzer(api_key="test")
        result = analyzer.analyze("path/to/video.mp4")
        assert result["incident_detected"] is True
```

---

## Common patterns

### Adding a new incident detection type

1. Add the type string to `VALID_INCIDENT_TYPES` in `shared/video_analyzer.py`
2. Add a description to `_EVENT_TAXONOMY` in the same file
3. Update `INCIDENT_TYPES` in `config.py`
4. Update frontend `lib/types.ts` if the type needs UI display logic

### Adding a new camera source

1. Add source string to `_SOURCE_FRAMING` in `shared/video_analyzer.py`
2. Add validation in `api_server.py` `AnalyzeRequest.validate_source`
3. Update `frontend/lib/types.ts` `source` union type

### Changing the analysis prompt

1. Edit `DEFAULT_ANALYSIS_PROMPT` in `config.py`
2. The `_EVENT_TAXONOMY` and `_JSON_SCHEMA` in `shared/video_analyzer.py` auto-include it
3. Test with `eval.py` against real clips before deploying

---

## Seams (where to inject behavior)

| Seam | Interface | Adapters |
|------|-----------|----------|
| Vision backend | `BaseAnalyzer` | `GeminiAnalyzer`, `OpenRouterAnalyzer` |
| Camera source | `TflClient` | Could add `MockTflClient` for testing |
| Persistence | `IncidentRepository` | `from_env()` returns real or None (no-op) |
| Config | `AppConfig` | `load_config()` reads env, `config.py` provides defaults |

---

## Important invariants

1. **Video URL rotation** - TfL rotates JamCam URLs. Never cache a video URL between polling cycles. Always call `get_camera_video_url()` fresh.

2. **Temp file cleanup** - `download_video()` creates a temp file. The caller MUST delete it. Pattern:
   ```python
   path = download_video(url)
   try:
       result = analyzer.analyze(path)
   finally:
       if path and os.path.exists(path):
           os.unlink(path)
   ```

3. **Public by default** - All frontend pages and API routes work without auth. Auth is only for admin delete and personal data.

4. **Backend owns persistence** - The Python FastAPI server writes to Supabase. The frontend never does direct inserts.

5. **Build-safe env vars** - The frontend uses placeholder fallbacks for Supabase URL/key during Next.js build. Real values are inlined at runtime or read server-side.

---

## When something breaks

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Unauthorized" on analyze | `/api/analyze` was checking `supabase.auth.getUser()` and rejecting anon users | Make auth optional, pass `created_by: user?.id ?? null` |
| "Analysis failed: null content" | OpenRouter video URL is inaccessible or model rejected format | Check URL is publicly accessible HTTPS. minimax-m3 needs real URLs, not base64 |
| DB writes silently fail | `IncidentRepository.from_env()` returned None | Check `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set |
| Frontend build fails | Missing `NEXT_PUBLIC_SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Set them in Vercel dashboard or `.env` |
| "Camera not found" | Camera ID changed or is offline | Run `python list_cameras.py` to verify ID exists and has a videoUrl |

---

## Env var reference

| Variable | Required | Used by |
|----------|----------|---------|
| `TFL_APP_KEY` | Yes (for watcher) | `shared/tfl_client.py` |
| `OPENROUTER_API_KEY` | Yes (for API) | `api_server.py`, `shared/video_analyzer.py` |
| `GEMINI_API_KEY` | Yes (for watcher, second opinion) | `main.py`, `shared/video_analyzer.py` |
| `NEXT_PUBLIC_SUPABASE_URL` | No (optional) | `shared/incident_repository.py`, frontend |
| `SUPABASE_SERVICE_ROLE_KEY` | No (optional) | `shared/incident_repository.py`, frontend API routes |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | No (optional) | Frontend Supabase client |
| `ADMIN_EMAILS` | No (optional) | Frontend admin delete |
| `NEXT_PUBLIC_TFL_APP_KEY` | No (optional) | Frontend TfL API calls from browser |
| `BACKEND_API_URL` / `NEXT_PUBLIC_API_URL` | No (optional) | Frontend proxy to Python backend |

---

## Anti-patterns (things that have caused bugs)

**Do NOT require auth on public-facing routes.** The map, incident feed, live status button, and manual upload must all work for anonymous users. Auth is only for admin delete and Supabase realtime subscriptions. If you add a `if (!user) return 401` guard to `/api/analyze`, `/api/upload`, or `/api/incidents`, you break the public experience.

**Do NOT expose the service role key to the browser.** `SUPABASE_SERVICE_ROLE_KEY` must only be used in server-side API routes (`route.ts`), never in client components or `NEXT_PUBLIC_*` env vars.

**Do NOT call `download_video()` without cleanup.** It creates a temp file. Every caller must delete it in `finally`.

**Do NOT cache TfL video URLs.** TfL rotates them. Call `get_camera_video_url()` every time you need a URL.

**Do NOT hardcode camera IDs or thresholds outside `config.py`.** All tunables live there. If you embed `"JamCams_00001.07350"` or `"medium"` in logic code, you create a maintenance trap.

**Do NOT return 500 from the frontend proxy.** If the Python backend returns an error, the frontend proxy (`route.ts`) should still return a structured JSON response the UI can display. Never let raw FastAPI stack traces leak to the browser.

**Do NOT forget to update both Python and TypeScript types.** `source` is `'tfl' | 'manual' | 'upload'` in both `api_server.py` validation AND `frontend/lib/types.ts`. Keep them in sync.

---

## Pre-commit checklist

Before you commit or push, run ALL of these. Do not skip any.

```bash
# 1. Backend tests (must be 100% pass)
.venv/Scripts/python -m pytest tests/ -v

# 2. Frontend build (must compile with zero errors)
cd frontend && npm run build

# 3. Check for secrets in the diff
cd .. && git diff --cached | findstr -i "api_key service_role password secret token"
# On macOS/Linux: git diff --cached | grep -i -E "api_key|service_role|password|secret|token"

# 4. Verify no temp files were staged
git diff --cached --name-only | findstr -i "debug_ deploy test_upload .env.vercel"
```

If any step fails, fix it before committing.

---

## How to verify a change

1. Run tests: `python -m pytest tests/ -v`
2. Start backend: `python api_server.py`
3. Start frontend: `cd frontend && npm run dev`
4. Open http://localhost:3000
5. Click "Get Live Status" on a camera - should fetch TfL clip, analyze, show result
6. Try manual upload - upload a video, pick location, verify analysis shows in incidents table
7. Check map - incident pins should appear

---

## File map

```
urbanintel/
  main.py                     CLI watcher (production polling)
  api_server.py               FastAPI (frontend backend)
  config.py                   Tunables (THE EDITABLE SURFACE)
  list_cameras.py             Discover TfL cameras with video URLs
  eval.py                     Evaluate model accuracy against labeled clips

  shared/
    __init__.py
    tfl_client.py             TfL API wrapper
    video_analyzer.py           Gemini + OpenRouter + download_video
    incident_repository.py      Supabase persistence
    config_loader.py            Typed env config

  tests/
    conftest.py                 Fixtures
    test_tfl_client.py
    test_video_analyzer.py
    test_incident_repository.py
    test_config.py
    test_api_server.py

  frontend/
    app/
      layout.tsx
      (protected)/
        page.tsx                Dashboard (map + live status + upload)
        incidents/
          page.tsx              Incident table
      api/
        analyze/route.ts        Proxy to Python /analyze
        upload/route.ts         Receive multipart, store, trigger analysis
        incidents/route.ts      Public read
        incidents/[id]/route.ts Admin delete
    components/
      Map.tsx                   Leaflet map with severity pins
      SeverityBadge.tsx
      IncidentTypeChip.tsx
      DateRangePicker.tsx
      EmptyState.tsx
      LocationPicker.tsx
    lib/
      supabase.ts               Client factory (browser/server/middleware)
      supabase-server.ts        Backward-compat re-export
      types.ts                  TypeScript types
    supabase/migrations/        SQL migrations
```
