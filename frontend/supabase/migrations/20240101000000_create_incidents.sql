-- Urban Intelligence: incidents table
create table if not exists incidents (
  id               uuid primary key default gen_random_uuid(),
  created_at       timestamptz not null default now(),
  camera_id        text not null,
  camera_name      text not null,
  lat              float,
  lon              float,
  incident_detected boolean not null default false,
  severity         text not null default 'none',
  incidents        jsonb,
  scene_summary    text,
  reasoning        text,
  raw_response     jsonb
);

-- Indexes for common query patterns
create index if not exists idx_incidents_camera_id on incidents (camera_id);
create index if not exists idx_incidents_created_at on incidents (created_at desc);
create index if not exists idx_incidents_severity on incidents (severity);
create index if not exists idx_incidents_incident_detected on incidents (incident_detected) where incident_detected = true;

-- Enable Row Level Security
alter table incidents enable row level security;

-- Policy: authenticated users can read all incidents
create policy "Authenticated users can read incidents"
  on incidents for select
  to authenticated
  using (true);

-- Policy: service role can insert (used by Python watcher)
create policy "Service role can insert incidents"
  on incidents for insert
  to service_role
  with check (true);
