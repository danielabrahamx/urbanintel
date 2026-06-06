-- Urban Intelligence: camera_status table for real-time command center
-- Tracks polling state of each camera in the fleet

create table if not exists camera_status (
  id                uuid primary key default gen_random_uuid(),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  camera_id         text not null unique,
  camera_name       text not null,
  lat               float,
  lon               float,
  status            text not null default 'idle', -- 'idle', 'measuring', 'error', 'offline'
  last_polled_at    timestamptz,
  last_incident_at  timestamptz,
  incident_count_24h int not null default 0,
  error_message     text,
  video_url         text,
  poll_interval_seconds int default 180
);

-- Indexes for command center queries
create index if not exists idx_camera_status_status on camera_status (status);
create index if not exists idx_camera_status_updated_at on camera_status (updated_at desc);
create index if not exists idx_camera_status_incident_count on camera_status (incident_count_24h desc);

-- Enable realtime
alter publication supabase_realtime add table camera_status;

-- Enable Row Level Security
alter table camera_status enable row level security;

-- Policy: authenticated users can read all camera status
create policy "Authenticated users can read camera_status"
  on camera_status for select
  to authenticated
  using (true);

-- Policy: service role can manage camera status (used by Python watcher)
create policy "Service role can manage camera_status"
  on camera_status for all
  to service_role
  using (true)
  with check (true);

-- Function to update updated_at automatically
create or replace function update_camera_status_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trigger_update_camera_status_updated_at
  before update on camera_status
  for each row
  execute function update_camera_status_updated_at();
