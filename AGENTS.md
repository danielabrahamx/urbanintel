# AGENTS.md - Urban Intelligence

Stop. Read this first. It prevents you from going in circles.

---

## TL;DR

This is a TfL JamCam traffic incident detection system. Python backend fetches camera clips, AI vision models analyze them, results go to Supabase. Next.js frontend displays a map and incident feed. The app is **public by default** - no auth required to view or analyze.

**Stack:** Python 3.11, FastAPI, Next.js 14, Supabase, OpenRouter/Gemini vision models.

**Before you edit anything:** run `python -m pytest tests/ -v` and `cd frontend && npm run build`. Both must pass.

---

## Decision tree: what are you trying to do?

| Goal | Read this | Then do |
|------|-----------|---------|
| Fix a bug in video analysis | `shared/video_analyzer.py` | Check `BaseAnalyzer` subclasses. OpenRouter needs real URLs, Gemini needs local MP4s |
| Fix a bug in TfL fetching | `shared/tfl_client.py` | Camera IDs are stable, video URLs rotate every cycle. Never cache URLs |
| Fix a bug in DB writes | `shared/incident_repository.py` | `from_env()` returns None when unconfigured - check env vars |
| Add a new API endpoint | `api_server.py` | Use Pydantic models. Keep auth optional. Delegate persistence to `IncidentRepository` |
| Fix frontend auth / public access | `frontend/app/api/analyze/route.ts` | Auth must be optional. Pass `created_by: user?.id ?? null` |
| Fix frontend build | `frontend/lib/supabase.ts` | Build-safe placeholders prevent build failures from missing env vars |
| Change incident types or prompts | `config.py` then `shared/video_analyzer.py` | `config.py` is THE editable surface |
| Deploy | `README.md` Deployment section | Backend first, then frontend |

---

## Critical invariants (break these and things fail)

1. **Auth is optional everywhere public.** The map, live status button, manual upload, and incident feed must work without login. Only admin delete requires auth. If you add `if (!user) return 401` to `/api/analyze` or `/api/upload`, you break the app.

2. **Backend owns all DB writes.** The frontend never inserts into `incidents`. It delegates to Python FastAPI endpoints. Frontend API routes use `createServiceClient()` (service role) for READS only.

3. **TfL video URLs rotate.** Call `TflClient.get_camera_video_url()` fresh every time. Never cache. Never store a video URL in a variable and reuse it.

4. **Temp files must be cleaned up.** `download_video()` returns a temp file path. Every caller must delete it in `finally`:
   ```python
   path = download_video(url)
   try:
       result = analyzer.analyze(path)
   finally:
       if path and os.path.exists(path):
           os.unlink(path)
   ```

5. **Never expose SUPABASE_SERVICE_ROLE_KEY to the browser.** It lives in server-side API routes only. `NEXT_PUBLIC_*` is for the anon key, never the service role.

6. **No hardcoded values outside `config.py`.** Camera IDs, thresholds, prompts, model names all live in `config.py`. If you embed them elsewhere, you create a maintenance trap.

7. **OpenRouter needs real HTTP URLs.** The minimax/minimax-m3 model silently returns null for base64 or file paths. Pass the actual video URL directly. Gemini still needs `download_video()` + Files API.

---

## File cheat sheet

```
Backend (Python)
  config.py                   Tunables - THE EDITABLE SURFACE
  shared/config_loader.py     Typed env config. Call load_config()
  shared/tfl_client.py        TfL API wrapper. Use TflClient.get_camera_video_url()
  shared/video_analyzer.py    GeminiAnalyzer + OpenRouterAnalyzer. See BaseAnalyzer ABC
  shared/incident_repository.py  Supabase persistence. from_env() returns None if unconfigured
  api_server.py               FastAPI. Auth-free. Handles model inference + DB persistence
  main.py                     CLI watcher. Polls one camera on a loop.

Frontend (Next.js)
  app/api/analyze/route.ts    Proxy to Python. Auth OPTIONAL. created_by can be null
  app/api/upload/route.ts     Multipart -> Supabase Storage -> signed URL -> Python
  app/api/incidents/route.ts  Public read. Service role. No auth needed.
  lib/supabase.ts             Client factory. Uses placeholders during build for safety
  lib/types.ts                TypeScript types. Keep source union in sync with Python
```

---

## Testing

```bash
# Backend (must be 101/101)
python -m pytest tests/ -v

# Frontend (must compile with zero errors)
cd frontend && npm run build
```

**Mock everything external.** Never call TfL, OpenRouter, or Gemini in tests. Use fixtures from `tests/conftest.py`.

---

## Troubleshooting (one-liner fixes)

| Symptom | Fix |
|---------|-----|
| "Unauthorized" on analyze | Remove hard auth check. Use `created_by: user?.id ?? null` |
| "Analysis failed: null content" | Video URL must be publicly accessible HTTPS. Not base64, not file path |
| DB writes silently fail | Check `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set |
| Frontend build fails | Missing env vars during prerender. `lib/supabase.ts` has placeholders - check actual values at runtime |
| "Camera not found" | Run `python list_cameras.py`. Camera may be offline or ID changed |
| Tests fail with import error | Run from project root: `python -m pytest tests/ -v` |

---

## If you are lost

1. Re-read the decision tree at the top of this file
2. Check `config.py` - most tunables are there
3. Check `.env.example` - most config questions are answered there
4. Run the tests - failing tests tell you exactly what's broken
5. Check the troubleshooting table above

Do NOT start grepping for random strings. Use the decision tree.
