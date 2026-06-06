# Urban Intelligence

AI-powered road safety monitoring for London using TfL JamCam feeds.

Polls traffic camera clips, runs them through vision models for incident detection, and surfaces results on a live dashboard.

---

## Architecture

```
                    +---------------+
                    |   TfL API     |
                    | (JamCam feeds)|
                    +-------+-------+
                            |
                            v
+-------------------+   +-------------------+   +------------------+
|  Python Watcher   |   |  FastAPI Server   |   |  Next.js Frontend |
|  (main.py)        |   |  (api_server.py)  |   |  (frontend/)      |
|  - polls TfL      |   |  - /analyze       |   |  - Map view       |
|  - analyzes clips |   |  - /upload        |   |  - Incident table |
|  - writes DB      |   |  - /health        |   |  - Manual upload  |
+--------+----------+   +--------+----------+   +---------+---------+
         |                       |                       |
         v                       v                       v
         +-----------------------+-----------------------+
                                 |
                                 v
                     +----------------------+
                     |  Supabase Postgres   |
                     |  - incidents table   |
                     |  - camera_status     |
                     |  - Storage (uploads) |
                     +----------------------+
```

### Upload flow (presigned URL — bypasses Vercel body limits)

```
Browser                          Vercel API routes         Supabase
──────                          ──────────────────         ────────
1. POST /api/upload-url ──────→ generates signed URL
2. PUT video ────────────────────────────────────────────→ stored directly
3. POST /api/upload ──────────→ signed download → Python analysis
```

The browser uploads video **directly to Supabase Storage** via a presigned URL. Vercel never touches the file bytes — only tiny JSON payloads (~200 bytes). This avoids the 4.5 MB Vercel body limit.

### Backend

| File | Role |
|------|------|
| `main.py` | CLI watcher - polls one camera on a loop, prints results, writes to DB |
| `api_server.py` | FastAPI server - frontend calls this for analysis and uploads |
| `shared/tfl_client.py` | TfL API wrapper with retry/back-off |
| `shared/video_analyzer.py` | Gemini + OpenRouter analyzers with source-aware prompts |
| `shared/incident_repository.py` | Supabase persistence layer |
| `shared/config_loader.py` | Typed config from env vars + config.py |
| `config.py` | Tunables (camera ID, poll interval, thresholds, prompt template) |
| `repro_upload.py` | End-to-end upload test with the presigned URL pipeline (16 MB dummy) |

### Frontend

| File | Role |
|------|------|
| `frontend/app/(protected)/page.tsx` | Dashboard - map, live status button, manual upload, recent activity |
| `frontend/app/(protected)/incidents/page.tsx` | Sortable/filterable incident table with CSV export |
| `frontend/components/Map.tsx` | Leaflet map with severity pins and heatmap |
| `frontend/app/api/analyze/route.ts` | Proxies video analysis to Python backend |
| `frontend/app/api/upload-url/route.ts` | Generates presigned Supabase upload URL (server-side, service role) |
| `frontend/app/api/upload/route.ts` | Post-upload handler — creates signed download URL, triggers analysis |
| `frontend/app/api/incidents/route.ts` | Public read endpoint (service role) |
| `frontend/app/api/incidents/[id]/route.ts` | Admin delete endpoint (auth required) |
| `frontend/lib/supabase.ts` | Unified Supabase client factory (browser / server / middleware) |

---

## Setup

### 1. Clone and install Python dependencies

```bash
cd urbanintel
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

Minimum required:

```
TFL_APP_KEY=your_tfl_key        # Free at https://api-portal.tfl.gov.uk
OPENROUTER_API_KEY=your_key     # https://openrouter.ai/keys
```

Optional but recommended for the dashboard:

```
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
```

### 4. Set up Supabase

1. Create a project at https://supabase.com
2. Run the migrations in `frontend/supabase/migrations/`
3. Create a storage bucket called `uploads` (private)

---

## Running

### Watcher (CLI)

Polls a single camera indefinitely. Good for production monitoring.

```bash
.venv\Scripts\activate
python main.py
```

Override camera: edit `TARGET_CAMERA_ID` in `config.py` or set env var.

### API Server

Backend for the frontend. Must be running for the dashboard to work.

```bash
.venv\Scripts\activate
python api_server.py
# Or: uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Status check |
| `/analyze` | POST | Analyze video URL (TfL or manual) |
| `/upload` | POST | Same as analyze but forces source=manual |
| `/cameras/{id}/video-url` | GET | Get current TfL video URL for a camera |

### Frontend

```bash
cd frontend
npm run dev
```

Open http://localhost:3000

---

## Testing

```bash
.venv\Scripts\activate
python -m pytest tests/ -v
```

All external APIs are mocked. Tests run fast and isolated.

| File | Coverage |
|------|----------|
| `test_tfl_client.py` | TfL API wrapper, retry logic, validation |
| `test_video_analyzer.py` | Gemini + OpenRouter analyzers |
| `test_incident_repository.py` | Supabase persistence |
| `test_config.py` | Config loading and validation |
| `test_api_server.py` | FastAPI endpoints, CORS, cleanup |

---

## Video Analysis Pipeline

The core loop is the same everywhere:

```
fetch camera URL  ->  download clip  ->  analyze with vision model  ->  persist result
```

Two vision backends:

| Backend | Model | Input | Use case |
|---------|-------|-------|----------|
| OpenRouter | minimax/minimax-m3 | Direct video URL | Default - fast, cheap, no download needed |
| Gemini | gemini-2.0-flash | Downloaded MP4 via Files API | Fallback, second opinion, eval.py |

The prompt adapts to the source:
- **TfL** (fixed overhead camera): conservative - only flag what is clearly observable
- **Manual/Upload** (user-submitted): triage-biased - look hard, use low confidence when evidence is partial

---

## Upload Architecture

Manual video uploads use a **three-step presigned URL flow** to avoid Vercel's 4.5 MB serverless body limit:

```
1. Browser  →  POST /api/upload-url  {filename, contentType}
             ←  {signedUrl, token, path}

2. Browser  →  PUT signedUrl (Supabase Storage directly)
             ←  200 OK

3. Browser  →  POST /api/upload  {path, lat, lon, locationName}
             ←  {success, incident_detected, severity, ...}
```

Step 2 uploads directly to Supabase — Vercel never touches the video bytes. Step 3 creates a signed download URL and forwards it to the Python backend for analysis. The whole flow works without authentication (public uploads).

**Test it:** `python repro_upload.py` (defaults to 16 MB dummy file against localhost:3000).

---

## Key Design Decisions

1. **Public by default** - The map and incident feed are readable without auth. Only admin delete and realtime subscriptions require login. Manual upload is open — anyone can submit footage.

2. **Service role for reads** - The frontend API routes use `createServiceClient()` (service role key) for DB reads. This avoids depending on open RLS policies and keeps the public experience reliable.

3. **Backend handles persistence** - The FastAPI server writes to Supabase via `IncidentRepository`. The frontend never writes directly to the DB.

4. **Source-aware prompts** - `build_analysis_prompt(source)` returns different framing for TfL vs manual footage. This is the single seam for adjusting model behavior per input type.

5. **No-op when unconfigured** - `IncidentRepository.from_env()` returns `None` if Supabase creds are missing. The watcher and API server continue to work without persistence.

6. **Presigned URL uploads** - Video files go direct browser→Supabase. Vercel serverless functions only handle tiny JSON payloads. This sidesteps Vercel's body size limit permanently and scales to any file size.

---

## Deployment

### Backend (Fly.io / Render / etc.)

1. Set env vars from `.env.example`
2. `python api_server.py` or `uvicorn api_server:app --host 0.0.0.0 --port 8000`
3. Point `BACKEND_API_URL` or `NEXT_PUBLIC_API_URL` at it

### Frontend (Vercel)

**Important:** Set the Vercel project's **Root Directory** to `frontend`. The repo root has no Next.js app — the framework lives in the `frontend/` subdirectory.

1. Go to Vercel Dashboard → Project Settings → General → Root Directory → set to `frontend`
2. Set env vars in Vercel dashboard (see list below)
3. Deploy: `cd frontend && vercel --prod --yes`

**Environment variables:**
- `NEXT_PUBLIC_SUPABASE_URL` — Supabase project URL
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` — Supabase anon key
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase service role (server-side only)
- `NEXT_PUBLIC_TFL_APP_KEY` — TfL API key
- `BACKEND_API_URL` or `NEXT_PUBLIC_API_URL` — Python backend URL
- `OPENROUTER_API_KEY` / `GEMINI_API_KEY` — model API keys
- `NEXT_PUBLIC_ADMIN_EMAILS` — comma-separated admin emails

The frontend build is safe without Supabase credentials — it falls back to placeholders and fails at request time, not build time.

### GitHub auto-deploy

Set the Vercel project's Root Directory to `frontend` (see above). Without this, auto-deploy on push fails with "Couldn't find any `pages` or `app` directory."

---

## Directory Structure

```
urbanintel/
├── main.py                     # CLI watcher
├── api_server.py               # FastAPI backend
├── config.py                   # Tunables and constants
├── repro_upload.py             # Upload pipeline E2E test
├── requirements.txt
├── .env.example
│
├── shared/
│   ├── tfl_client.py           # TfL API wrapper
│   ├── video_analyzer.py       # Gemini + OpenRouter
│   ├── incident_repository.py  # Supabase persistence
│   └── config_loader.py        # Typed env config
│
├── tests/
│   ├── conftest.py             # Fixtures
│   ├── test_tfl_client.py
│   ├── test_video_analyzer.py
│   ├── test_incident_repository.py
│   ├── test_config.py
│   └── test_api_server.py
│
└── frontend/                   # Next.js 14 app (Vercel root directory)
    ├── app/
    │   ├── layout.tsx
    │   ├── (protected)/
    │   │   ├── page.tsx          # Dashboard
    │   │   └── incidents/
    │   │       └── page.tsx      # Incident table
    │   └── api/
    │       ├── analyze/route.ts
    │       ├── upload/route.ts
    │       ├── upload-url/route.ts
    │       └── incidents/
    │           ├── route.ts
    │           └── [id]/route.ts
    ├── components/
    │   ├── Map.tsx
    │   ├── SeverityBadge.tsx
    │   └── ...
    ├── lib/
    │   ├── supabase.ts
    │   ├── supabase-server.ts
    │   └── types.ts
    └── supabase/migrations/
```
