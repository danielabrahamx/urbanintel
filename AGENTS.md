# AGENTS.md - Urban Intelligence

Stop. Read this first. It prevents you from going in circles.

---

## TL;DR

TfL JamCam traffic incident detection system. Python backend fetches camera clips → AI vision models analyze → results persist to Supabase. Next.js 14 frontend displays a map + incident feed. **Public by default** — no auth required to view or analyze.

**Stack:** Python 3.11, FastAPI, Next.js 14 (App Router), Supabase, OpenRouter/Gemini vision models. Deployed on Vercel + Fly.io/Render.

**Before you edit anything:** run `python -m pytest tests/ -v` and `cd frontend && npm run build`. Both must pass.

---

## Decision tree: what are you trying to do?

| Goal | Read this | Then do |
|------|-----------|---------|
| Fix a bug in video analysis | `shared/video_analyzer.py` | Check `BaseAnalyzer` subclasses. OpenRouter needs real URLs, Gemini needs local MP4s |
| Fix a bug in TfL fetching | `shared/tfl_client.py` | Camera IDs are stable, video URLs rotate every cycle. Never cache URLs |
| Fix a bug in DB writes | `shared/incident_repository.py` | `from_env()` returns None when unconfigured — check env vars |
| Add a new API endpoint | `api_server.py` | Use Pydantic models. Keep auth optional. Delegate persistence to `IncidentRepository` |
| Fix frontend auth / public access | `frontend/app/api/analyze/route.ts` | Auth must be optional. Pass `created_by: user?.id ?? null` |
| Fix frontend build | `frontend/lib/supabase.ts` | Build-safe placeholders prevent build failures from missing env vars |
| Fix upload issues / 413 errors | `frontend/app/api/upload-url/route.ts` | Uploads go **direct to Supabase** via presigned URLs — never through Vercel |
| Change incident types or prompts | `config.py` then `shared/video_analyzer.py` | `config.py` is THE editable surface |
| Deploy | See "Deployment" section below | Backend first, then frontend. Set Vercel Root Directory to `frontend` |

---

## Upload architecture (critical — read before touching upload code)

```
Browser                                     Vercel (tiny JSON only)          Supabase
──────                                     ──────────────────────           ────────
1. POST /api/upload-url {filename} ────────→ returns {signedUrl, token, path}
2. PUT signedUrl ───────────────────────────────────────────────────────────→ video stored
3. POST /api/upload {path, lat, lon} ──────→ signed download URL → Python analysis
```

**No video bytes ever touch Vercel.** The largest body Vercel sees is step 3's JSON (~200 bytes). All file data goes direct browser→Supabase via signed URL.

**Why:** Vercel serverless functions have a 4.5 MB body limit (Hobby) / 100 MB (Pro). A 16 MB video uploaded via multipart to `/api/upload` would 413 before the route handler runs. The presigned URL pattern sidesteps this completely.

**Key files:**
- `frontend/app/api/upload-url/route.ts` — generates signed Supabase upload URLs (server-side, uses service role)
- `frontend/app/api/upload/route.ts` — receives `{path, lat, lon, locationName}`, creates signed download URL, forwards to Python backend
- `frontend/app/(protected)/page.tsx` `handleUpload()` — orchestrates the 3-step flow from the browser
- `repro_upload.py` — end-to-end test script for the presigned URL pipeline (16 MB dummy file)

---

## Critical invariants (break these and things fail)

1. **Auth is optional everywhere public.** The map, live status button, manual upload, and incident feed must work without login. Only admin delete requires auth. If you add `if (!user) return 401` to `/api/analyze`, `/api/upload`, or `/api/upload-url`, you break the app.

2. **Uploads MUST use the presigned URL flow.** Never revert to multipart upload through `/api/upload`. Never send `FormData` with a file directly to a Next.js API route — it will 413 on Vercel. Always: get signed URL from `/api/upload-url` → PUT to Supabase → POST metadata to `/api/upload`.

3. **Backend owns all DB writes.** The frontend never inserts into `incidents`. It delegates to Python FastAPI endpoints. Frontend API routes use `createServiceClient()` (service role) for READS only.

4. **TfL video URLs rotate.** Call `TflClient.get_camera_video_url()` fresh every time. Never cache. Never store a video URL in a variable and reuse it.

5. **Temp files must be cleaned up.** `download_video()` returns a temp file path. Every caller must delete it in `finally`:
   ```python
   path = download_video(url)
   try:
       result = analyzer.analyze(path)
   finally:
       if path and os.path.exists(path):
           os.unlink(path)
   ```

6. **Never expose SUPABASE_SERVICE_ROLE_KEY to the browser.** It lives in server-side API routes only. `NEXT_PUBLIC_*` is for the anon key, never the service role.

7. **No hardcoded values outside `config.py`.** Camera IDs, thresholds, prompts, model names all live in `config.py`. If you embed them elsewhere, you create a maintenance trap.

8. **OpenRouter needs real HTTP URLs.** The minimax/minimax-m3 model silently returns null for base64 or file paths. Pass the actual video URL directly. Gemini still needs `download_video()` + Files API.

---

## File cheat sheet

```
Backend (Python)
  config.py                       Tunables — THE EDITABLE SURFACE
  shared/config_loader.py         Typed env config. Call load_config()
  shared/tfl_client.py            TfL API wrapper. Use TflClient.get_camera_video_url()
  shared/video_analyzer.py        GeminiAnalyzer + OpenRouterAnalyzer. See BaseAnalyzer ABC
  shared/incident_repository.py   Supabase persistence. from_env() returns None if unconfigured
  api_server.py                   FastAPI. Auth-free. Handles model inference + DB persistence
  main.py                         CLI watcher. Polls one camera on a loop
  repro_upload.py                 End-to-end upload test (presigned URL pipeline, 16 MB dummy)

Frontend (Next.js — deployed from frontend/ directory)
  app/(protected)/page.tsx           Dashboard: map, live status, manual upload, activity feed
  app/(protected)/incidents/page.tsx Sortable/filterable incident table with CSV export
  app/api/analyze/route.ts           Proxy to Python. Auth OPTIONAL. created_by can be null
  app/api/upload/route.ts            Post-upload handler. Receives {path, lat, lon} JSON, creates signed download URL, forwards to Python
  app/api/upload-url/route.ts        Generates signed Supabase upload URL (service role). Tiny JSON in/out.
  app/api/incidents/route.ts         Public read. Service role. No auth needed.
  app/api/incidents/[id]/route.ts    Admin delete. Auth required.
  components/Map.tsx                 Leaflet map with severity pins and heatmap
  lib/supabase.ts                    Client factory. Uses placeholders during build for safety
  lib/supabase-server.ts             Re-export of createServerClient for backward compat
  lib/types.ts                       TypeScript types. Keep source union in sync with Python
```

---

## Deployment

### Vercel (frontend)

**Root Directory:** The Vercel project's Root Directory setting MUST be `frontend`. The repo root has no Next.js app — Next.js lives in `frontend/`. Without this, builds fail with "Couldn't find any `pages` or `app` directory."

Set it in: Vercel Dashboard → Project Settings → General → Root Directory → `frontend`

Or deploy from the frontend directory directly: `cd frontend && vercel --prod --yes`

**Environment variables** (set in Vercel dashboard):
- `NEXT_PUBLIC_SUPABASE_URL` — Supabase project URL
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` — Supabase anon key
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase service role (server-side only)
- `NEXT_PUBLIC_TFL_APP_KEY` — TfL API key
- `BACKEND_API_URL` or `NEXT_PUBLIC_API_URL` — Python backend URL
- `OPENROUTER_API_KEY` / `GEMINI_API_KEY` — model API keys
- `NEXT_PUBLIC_ADMIN_EMAILS` — comma-separated admin emails

### Python backend (Fly.io / Render / etc.)

1. Set env vars from `.env.example`
2. `python api_server.py` or `uvicorn api_server:app --host 0.0.0.0 --port 8000`
3. Point the frontend's `BACKEND_API_URL` at it

---

## Testing

```bash
# Backend
python -m pytest tests/ -v

# Frontend (must compile with zero errors)
cd frontend && npm run build
```

**Mock everything external.** Never call TfL, OpenRouter, or Gemini in tests. Use fixtures from `tests/conftest.py`.

---

## Troubleshooting (one-liner fixes)

| Symptom | Fix |
|---------|-----|
| 413 on video upload | Uploads must use presigned URL flow. Never multipart through a Vercel API route. See upload architecture above |
| "Unauthorized" on analyze/upload | Remove hard auth check. Use `created_by: user?.id ?? null` |
| "Analysis failed: null content" | Video URL must be publicly accessible HTTPS. Not base64, not file path |
| DB writes silently fail | Check `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set |
| Frontend build fails | Missing env vars during prerender. `lib/supabase.ts` has placeholders — check actual values at runtime |
| Vercel build fails: "Couldn't find `pages` or `app`" | Set Root Directory to `frontend` in Vercel project settings |
| "Camera not found" | Run `python list_cameras.py`. Camera may be offline or ID changed |
| Tests fail with import error | Run from project root: `python -m pytest tests/ -v` |

---

## If you are lost

1. Re-read the decision tree at the top of this file
2. **Upload/413 issues:** read the Upload Architecture section
3. **Vercel build issues:** check the Root Directory is `frontend`
4. Check `config.py` — most tunables are there
5. Check `.env.example` — most config questions are answered there
6. Run the tests — failing tests tell you exactly what's broken
7. Check the troubleshooting table above

Do NOT start grepping for random strings. Use the decision tree.
