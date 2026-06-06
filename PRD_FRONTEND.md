# Urban Intelligence - Frontend PRD

## What we're building

A hosted, client-facing web dashboard for councils and transport authorities to monitor road
safety incidents detected by the Urban Intelligence watcher. Shows a live incident feed, an
area heatmap, and historical filtering. Backed by Supabase. Deployed to Vercel.

---

## Context

The existing Python watcher (`main.py`) polls TfL JamCam feeds, sends clips to Gemini for
analysis, and currently just prints results to stdout. This frontend:

1. Gives the watcher somewhere to persist incidents (Supabase Postgres)
2. Surfaces those incidents in a professional client-facing UI

The backend watcher is not being rewritten - just extended to write to the DB.

---

## Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Frontend | Next.js 14 (App Router) | Vercel-native, good map support |
| Styling | Tailwind CSS | Fast, consistent |
| Map | Leaflet + react-leaflet | Open source, no API key needed |
| Backend API | Next.js API routes | Keeps it a single repo, no separate service |
| Database | Supabase (Postgres) | Already set up, free tier, REST + realtime built in |
| Auth | Supabase Auth | Simple email/password for client logins |
| Hosting | Vercel | Already decided |

---

## Environment variables

All present in `.env` / `.env.example`:

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
SUPABASE_SERVICE_ROLE_KEY        # server-side only, never exposed to browser
```

---

## Database schema

Single table to start. Run as a Supabase migration.

```sql
create table incidents (
  id               uuid primary key default gen_random_uuid(),
  created_at       timestamptz not null default now(),
  camera_id        text not null,
  camera_name      text not null,
  lat              float,
  lon              float,
  incident_detected boolean not null,
  severity         text not null,   -- none | low | medium | high | critical
  incidents        jsonb,           -- raw array from Gemini
  scene_summary    text,
  reasoning        text,
  raw_response     jsonb            -- full Gemini JSON for debugging
);

-- Indexes for the common query patterns
create index on incidents (camera_id);
create index on incidents (created_at desc);
create index on incidents (severity);
```

---

## Watcher change (Python)

Add a `write_incident()` function to `main.py` that inserts a row after every analysis.
Use the Supabase Python client (`supabase-py`). Add `supabase` to `requirements.txt`.

The existing print logic stays unchanged - DB write is additive.

```python
# pseudocode - agent should implement properly
from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def write_incident(result: dict, camera_id: str, camera_name: str, lat: float, lon: float):
    supabase.table("incidents").insert({
        "camera_id": camera_id,
        "camera_name": camera_name,
        "lat": lat,
        "lon": lon,
        "incident_detected": result.get("incident_detected", False),
        "severity": result.get("severity", "none"),
        "incidents": result.get("incidents", []),
        "scene_summary": result.get("scene_summary", ""),
        "reasoning": result.get("reasoning", ""),
        "raw_response": result,
    }).execute()
```

The camera lat/lon is available from the TfL API response - add it to `get_camera_video_url()`
return value (currently returns `(video_url, camera_name)`, extend to
`(video_url, camera_name, lat, lon)`).

---

## Frontend pages

### `/` - Map view

- Full-viewport Leaflet map centred on London
- Marker per camera that has recorded at least one incident
- Marker colour = worst severity recorded in last 24h
  - grey = none, yellow = low, orange = medium, red = high, dark red = critical
- Click marker → popover showing camera name, last incident type, timestamp, scene summary
- Top-right: severity filter chips (All / Low / Medium / High / Critical)
- Top-left: date range picker (Today / Last 7 days / Last 30 days / Custom)
- Live: new incidents appear without page refresh (Supabase realtime subscription)

### `/incidents` - Incident table

- Sortable, filterable table of all incidents where `incident_detected = true`
- Columns: Time | Camera | Area | Type(s) | Severity | Confidence | Summary
- Filters: date range, camera, incident type (multi-select), severity (multi-select)
- Row expand → shows full Gemini reasoning + all detected incident details
- Export button → downloads filtered results as CSV

### `/camera/[id]` - Per-camera detail

- Camera name + location on a small map
- Stats bar: total incidents, most common type, worst severity, last seen
- Timeline chart: incident count per day (last 30 days), stacked by severity
- Full incident history table for this camera (same columns as `/incidents`)

### `/` auth gate

- All pages behind Supabase Auth (email + password)
- Simple login page at `/login`
- No self-signup - accounts created manually via Supabase dashboard for now

---

## Design

- Dark theme - looks professional for a safety/monitoring product
- Colour system:
  - Background: `#0f1117`
  - Surface: `#1a1d27`
  - Border: `#2a2d3a`
  - Text primary: `#f0f2f8`
  - Text muted: `#6b7280`
  - Severity colours: grey / `#eab308` / `#f97316` / `#ef4444` / `#7f1d1d`
- Font: Inter
- No rounded corners on data elements - sharp, utilitarian
- Logo/brand: "Urban Intelligence" wordmark top-left, no icon needed yet

---

## File structure

```
urbanintel/
  frontend/                   # new Next.js app
    app/
      layout.tsx
      page.tsx                # map view
      login/page.tsx
      incidents/page.tsx
      camera/[id]/page.tsx
    components/
      Map.tsx
      IncidentTable.tsx
      SeverityBadge.tsx
      DateRangePicker.tsx
    lib/
      supabase.ts             # client + server clients
      types.ts                # Incident type, severity enums
    public/
  main.py                     # existing - extend with write_incident()
  requirements.txt            # add supabase
  .env
  .env.example
```

---

## Out of scope for this build

- Video playback in the dashboard (future)
- Multi-tenant / per-client data isolation (future)
- Automated alerting / email/SMS on high severity (future)
- MuBit memory integration (future)
- Fine-tuned model / YOLO pipeline (future)

---

## Definition of done

- [ ] Supabase `incidents` table created via migration file
- [ ] `main.py` writes to DB on every analysis cycle
- [ ] Map loads, shows markers, popover works
- [ ] `/incidents` table loads, filters work, CSV export works
- [ ] `/camera/[id]` loads with stats and timeline
- [ ] Auth gate works - unauthenticated users redirected to `/login`
- [ ] Deployed to Vercel, accessible via public URL
- [ ] `.env.example` has all required variables documented
