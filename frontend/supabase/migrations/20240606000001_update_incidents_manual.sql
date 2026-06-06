-- Add support for manual video uploads

-- Add source column to track incident origin
alter table incidents add column if not exists source text default 'tfl';
alter table incidents add column if not exists video_url text;
alter table incidents add column if not exists created_by uuid references auth.users(id);

-- Update indexes
create index if not exists idx_incidents_source on incidents (source);
create index if not exists idx_incidents_created_by on incidents (created_by);

-- Policy: authenticated users can insert their own manual incidents
create policy "Users can insert manual incidents"
  on incidents for insert
  to authenticated
  with check (source = 'manual' and created_by = auth.uid());

-- Create storage bucket for video uploads
insert into storage.buckets (id, name, public)
values ('uploads', 'uploads', false)
on conflict (id) do nothing;

-- Policy: authenticated users can upload to their own folder
create policy "Users can upload to their folder"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'uploads' and (storage.foldername(name))[1] = auth.uid()::text);

-- Policy: users can read their own uploads
create policy "Users can read their uploads"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'uploads' and (storage.foldername(name))[1] = auth.uid()::text);
