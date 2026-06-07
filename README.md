# Urban Intelligence

AI-powered near-miss detection for UK roads — using public CCTV and crowdsourced footage to prevent accidents before they happen.

Every year on London's roads, **21,000 collisions** result in **3,500 serious injuries** and **108 deaths**. Behind each number is a preventable failure: a junction with poor sightlines, a parking scheme that forces cyclists into traffic, a sign placed too late. Transport for London and local councils invest heavily in post-collision analysis, but waiting for a death to trigger intervention is too late.

Urban Intelligence detects *near misses* at scale. It analyses video from TfL's JamCam network and crowdsourced dashcam footage, identifying dangerous driving, road-design hazards, and close-proximity incidents — geo-located, severity-rated, and delivered as actionable reports for councils and National Highways.

We started with academic foundations (UCL's CyclingNet) and modern vision models. Within 24 hours of launching, we crowdsourced 18 real near-miss videos. Outputs are 100% reproducible, algorithmically transparent, and designed to scale nationally.

---

## Quick start

```bash
# Backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # add TFL_APP_KEY + OPENROUTER_API_KEY
python api_server.py

# Frontend
cd frontend && npm install && npm run dev
# → http://localhost:3000
```

---

## How it works

```
TfL CCTV / crowdsourced video  →  vision model analysis  →  structured incident report
                                                                  ↓
                                                          Supabase (geo-located,
                                                          severity-rated, timestamped)
                                                                  ↓
                                               Live dashboard ← reports for councils
```

Each detection includes: incident type, severity, confidence, timestamp in clip, scene summary, and reasoning. The analysis prompt adapts to the source — conservative for fixed overhead cameras, triage-biased for user-submitted footage.

Two vision backends: **OpenRouter** (minimax/minimax-m3, works with direct video URLs) and **Gemini** (gemini-2.0-flash, used for second opinions).

---

## What we're building toward

With sufficient near-miss footage, we'll train our own deep learning models — building on UCL's CyclingNet research — to create the first nationally scalable near-miss detection system purpose-built for UK road safety. The density of public CCTV plus early crowdsourcing traction (18 videos in 24 hours) shows this is achievable.

---

## Architecture

```
                    +---------------+
                    |   TfL API     |
                    +-------+-------+
                            |
                            v
+-------------------+   +-------------------+   +------------------+
|  Python Watcher   |   |  FastAPI Server   |   |  Next.js Frontend |
|  (main.py)        |   |  (api_server.py)  |   |  (frontend/)      |
|  - polls cameras  |   |  - /analyze       |   |  - live map       |
|  - runs AI models |   |  - /upload        |   |  - incident feed  |
|  - persists to DB |   |  - /health        |   |  - manual upload  |
+--------+----------+   +--------+----------+   +---------+---------+
         |                       |                       |
         v                       v                       v
         +-----------------------+-----------------------+
                                 |
                                 v
                     +----------------------+
                     |  Supabase Postgres   |
                     +----------------------+
```

Uploads bypass Vercel's body limit via presigned URLs — videos go direct browser→Supabase, API routes only handle tiny JSON payloads.

---

## Project layout

```
urbanintel/
├── main.py                     # CLI watcher — polls one camera on loop
├── api_server.py               # FastAPI — frontend calls this for analysis
├── config.py                   # Tunables (camera IDs, thresholds, prompts)
├── repro_upload.py             # E2E upload pipeline test (16 MB dummy)
│
├── shared/
│   ├── tfl_client.py           # TfL API wrapper with retry/back-off
│   ├── video_analyzer.py       # Gemini + OpenRouter, source-aware prompts
│   ├── incident_repository.py  # Supabase persistence layer
│   └── config_loader.py        # Typed env config
│
├── tests/                      # pytest suite — all external APIs mocked
│
└── frontend/                   # Next.js 14 (App Router) — Vercel root dir
    ├── app/(protected)/        # Dashboard + incident table
    ├── app/api/                # analyze, upload, upload-url, incidents
    ├── components/             # Map (Leaflet), SeverityBadge, etc.
    └── lib/                    # Supabase client, types
```

---

## Key decisions

- **Public by default** — map, incident feed, and uploads work without auth. Only admin delete requires login.
- **Near misses, not just crashes** — the leading indicator is what happens before the collision.
- **Source-aware prompts** — different analysis framing for fixed CCTV vs user-submitted footage.
- **Backend owns persistence** — the frontend never writes directly to Supabase.
- **Presigned URL uploads** — video never touches Vercel, sidestepping the 4.5 MB body limit permanently.
- **No-op when unconfigured** — works without Supabase; falls back gracefully.

---

## Deployment

**Backend:** any cloud VM. Set env vars → `uvicorn api_server:app --host 0.0.0.0 --port 8000`

**Frontend:** Vercel. **Set Root Directory to `frontend`** in Project Settings. Required env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_TFL_APP_KEY`, `BACKEND_API_URL`, `OPENROUTER_API_KEY`.

---

## Testing

```bash
python -m pytest tests/ -v        # backend
cd frontend && npm run build      # frontend (must compile)
```
