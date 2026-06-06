# Urban Intelligence Frontend

Next.js 14 dashboard for the Urban Intelligence traffic monitoring system.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | Next.js 14 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS + inline styles (dark theme) |
| Map | Leaflet + react-leaflet |
| UI Components | lucide-react icons, custom components |
| State | React hooks (no external state library) |
| Backend | Python FastAPI (separate process) |
| Database | Supabase (Postgres + Storage) |

---

## Getting Started

```bash
npm install
npm run dev
```

Open http://localhost:3000

---

## Environment Variables

Create `.env.local` in this directory:

```
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...          # Server-side only
ADMIN_EMAILS=admin@example.com          # Comma-separated for admin delete
NEXT_PUBLIC_TFL_APP_KEY=...             # Optional - for client-side TfL calls
BACKEND_API_URL=http://localhost:8000   # Python FastAPI server
```

The build is safe without these - it uses placeholders and fails at request time, not during `next build`.

---

## Project Structure

```
app/
  layout.tsx                    Root layout (dark theme)
  (protected)/                  Grouped routes
    page.tsx                    Dashboard - map, live status, upload, activity feed
    incidents/
      page.tsx                  Full incident table with filters, sort, CSV export
  api/
    analyze/route.ts            Proxy to Python /analyze (public, auth optional)
    upload/route.ts             Multipart upload to Supabase Storage + analysis
    incidents/route.ts          Public read endpoint (service role)
    incidents/[id]/route.ts     Admin-only delete

components/
  Map.tsx                       Leaflet map with severity pins + heatmap
  SeverityBadge.tsx
  IncidentTypeChip.tsx
  DateRangePicker.tsx
  EmptyState.tsx
  LocationPicker.tsx

lib/
  supabase.ts                 Unified client factory (browser/server/middleware)
  types.ts                    Incident, Severity, CameraStatus types

supabase/migrations/          SQL schema + RLS policies
```

---

## Auth Model

The app is **public by default**.

- Anyone can view the map and incident feed
- Anyone can click "Get Live Status" to analyze a TfL camera
- Anyone can upload a video for analysis
- Only **admin users** (matched against `ADMIN_EMAILS` env var) can delete manual incidents
- Auth is only required for admin features and Supabase realtime subscriptions

The login page exists but is optional. Unauthenticated users get full read access.

---

## API Routes

### `POST /api/analyze`

Proxies video analysis to the Python backend.

**Body:** `{ videoUrl, cameraId, cameraName, lat, lon, source?, secondOpinion? }`

**Response:** `{ success, incident_detected, result, incident }`

### `POST /api/upload`

Receives multipart form with video file + lat/lon/locationName.

1. Uploads to Supabase Storage private `uploads` bucket
2. Creates signed URL
3. Sends to Python backend `/upload`
4. Returns analysis result

### `GET /api/incidents`

Public read. Query params:
- `detectedOnly=true` - only incidents with `incident_detected=true`
- `since=<ISO>` - filter by date
- `limit=<n>` - max rows (default 200, cap 5000)

### `DELETE /api/incidents/{id}`

Admin only. Only manual uploads can be deleted.

---

## Key Design Decisions

1. **Service role for reads** - API routes use `createServiceClient()` (service role key) instead of anon RLS. This makes the public experience reliable and explicit.

2. **No direct DB writes from frontend** - The frontend never inserts into `incidents`. It always delegates to the Python backend, which owns persistence.

3. **Build-safe env vars** - `lib/supabase.ts` uses placeholder fallbacks during Next.js prerender so the build never fails from missing env vars.

4. **Realtime + polling fallback** - Uses Supabase realtime subscription when authenticated, plus a 15s polling fallback so anonymous visitors still see updates.

---

## Deployment

```bash
vercel --prod
```

Set all env vars in the Vercel dashboard first. The build does not need the Python backend to be running.
