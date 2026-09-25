-- Minimal stand-in for the pieces of Supabase the migration relies on, so the
-- schema and its RLS policies can be tested on a vanilla PostgreSQL (>= 14).
-- Never run this against a real Supabase project.
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key default gen_random_uuid(), email text);
create or replace function auth.uid() returns uuid language sql stable as $$
    select nullif(current_setting('request.jwt.claims', true)::json ->> 'sub', '')::uuid
$$;
do $$ begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
end $$;
grant usage on schema public, auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;
-- Supabase grants table privileges to API roles by default; RLS does the filtering.
alter default privileges in schema public grant all on tables to anon, authenticated;
