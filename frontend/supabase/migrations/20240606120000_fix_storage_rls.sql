-- Fix Storage RLS policies for manual uploads
-- Issue: auth.uid() returns UUID but foldername returns text, causing type mismatch

-- Ensure bucket exists
insert into storage.buckets (id, name, public)
values ('uploads', 'uploads', false)
on conflict (id) do nothing;

-- Drop existing policies if they exist (to recreate with fixes)
drop policy if exists "Users can upload to their folder" on storage.objects;
drop policy if exists "Users can read their uploads" on storage.objects;
drop policy if exists "Users can update their uploads" on storage.objects;
drop policy if exists "Users can delete their uploads" on storage.objects;

-- Enable RLS on storage.objects (should already be enabled, but safe to ensure)
alter table storage.objects enable row level security;

-- Policy: authenticated users can INSERT to their own folder
-- Fixed: proper casting to text for comparison
-- Path format: user_id/filename.ext where user_id is a UUID
-- storage.foldername(name) returns array of path components
-- (storage.foldername(name))[1] gets the first folder (user_id)
create policy "Users can upload to their folder"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Policy: users can SELECT their own uploads
create policy "Users can read their uploads"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Policy: users can UPDATE their own uploads (needed for upsert/replace)
create policy "Users can update their uploads"
  on storage.objects for update
  to authenticated
  using (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Policy: users can DELETE their own uploads
create policy "Users can delete their uploads"
  on storage.objects for delete
  to authenticated
  using (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Verify policies were created
select
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname = 'storage' and tablename = 'objects';
