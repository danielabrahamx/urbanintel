-- Public users can view the map/incidents without an account.
drop policy if exists "Public users can read incidents" on incidents;

create policy "Public users can read incidents"
  on incidents for select
  to anon
  using (true);

-- Keep uploads private. The Next.js upload API uses the service role to write files,
-- so anonymous visitors never receive direct storage write permissions.
