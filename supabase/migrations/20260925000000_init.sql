-- ════════════════════════════════════════════════════════════════════════
-- AI Product Owner Assistant — usage, quotas & access control
--
-- Apply once: Supabase Dashboard › SQL Editor › paste › Run
--          or: supabase db push
--
-- Security model (Row Level Security everywhere):
--   * a member reads only their own profile and runs, and can only insert
--     runs for themselves; they can never change their role or quotas;
--   * an admin reads everything, edits roles/quotas, and manages the
--     synthetic demo data set.
-- ════════════════════════════════════════════════════════════════════════

-- ── Profiles (1-1 with auth.users) ───────────────────────────────────────
create table if not exists public.profiles (
    id                   uuid primary key references auth.users (id) on delete cascade,
    email                text        not null default '',
    role                 text        not null default 'member' check (role in ('admin', 'member')),
    -- Spending limits in EUR; NULL = unlimited. Defaults protect the API
    -- budget as soon as someone is invited.
    max_eur_per_request  numeric(10, 4) default 0.50,
    daily_eur_limit      numeric(10, 4) default 2.00,
    weekly_eur_limit     numeric(10, 4) default 5.00,
    monthly_eur_limit    numeric(10, 4) default 10.00,
    created_at           timestamptz not null default now(),
    constraint quotas_are_positive check (
        coalesce(max_eur_per_request, 0) >= 0 and coalesce(daily_eur_limit, 0) >= 0
        and coalesce(weekly_eur_limit, 0) >= 0 and coalesce(monthly_eur_limit, 0) >= 0
    )
);

comment on table public.profiles is 'App profile, role and spending quotas (EUR) of each user.';

-- ── Runs: one row per pipeline execution or on-demand story ──────────────
create table if not exists public.runs (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid        not null references public.profiles (id) on delete cascade,
    created_at      timestamptz not null default now(),
    kind            text        not null check (kind in ('pipeline', 'story')),
    status          text        not null check (status in ('success', 'error', 'blocked')),
    model           text        not null,
    input_chars     integer     not null default 0 check (input_chars >= 0),
    features_count  integer     not null default 0 check (features_count >= 0),
    stories_count   integer     not null default 0 check (stories_count >= 0),
    input_tokens    integer     not null default 0 check (input_tokens >= 0),
    output_tokens   integer     not null default 0 check (output_tokens >= 0),
    cost_usd        numeric(12, 6) not null default 0 check (cost_usd >= 0),
    cost_eur        numeric(12, 6) not null default 0 check (cost_eur >= 0),
    duration_s      numeric(10, 2) not null default 0,
    error           text,
    is_synthetic    boolean     not null default false
);

create index if not exists runs_user_created_idx on public.runs (user_id, created_at desc);
create index if not exists runs_created_idx on public.runs (created_at desc);

comment on table public.runs is 'Every Claude-backed execution, with tokens and cost — source of truth for quotas.';

-- ── Per-agent breakdown of a run ─────────────────────────────────────────
create table if not exists public.run_agents (
    run_id         uuid    not null references public.runs (id) on delete cascade,
    agent          text    not null,
    calls          integer not null default 0,
    input_tokens   integer not null default 0,
    output_tokens  integer not null default 0,
    cost_eur       numeric(12, 6) not null default 0,
    seconds        numeric(10, 2) not null default 0,
    primary key (run_id, agent)
);

-- ── Helpers ──────────────────────────────────────────────────────────────
-- SECURITY DEFINER avoids infinite recursion when a policy on `profiles`
-- needs to read `profiles`. search_path is pinned to prevent hijacking.
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.profiles
        where id = (select auth.uid()) and role = 'admin'
    );
$$;

revoke execute on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.profiles (id, email) values (new.id, coalesce(new.email, ''))
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Users created before this migration get a profile too.
insert into public.profiles (id, email)
select id, coalesce(email, '') from auth.users
on conflict (id) do nothing;

-- ── Row Level Security ───────────────────────────────────────────────────
alter table public.profiles   enable row level security;
alter table public.runs       enable row level security;
alter table public.run_agents enable row level security;

-- Anonymous visitors get nothing at all.
revoke all on public.profiles, public.runs, public.run_agents from anon;

-- profiles
drop policy if exists "profiles: read own or admin" on public.profiles;
create policy "profiles: read own or admin" on public.profiles
    for select to authenticated
    using (id = (select auth.uid()) or (select public.is_admin()));

drop policy if exists "profiles: admin updates" on public.profiles;
create policy "profiles: admin updates" on public.profiles
    for update to authenticated
    using ((select public.is_admin()))
    with check ((select public.is_admin()));

-- runs
drop policy if exists "runs: read own or admin" on public.runs;
create policy "runs: read own or admin" on public.runs
    for select to authenticated
    using (user_id = (select auth.uid()) or (select public.is_admin()));

drop policy if exists "runs: insert own, admin anything" on public.runs;
create policy "runs: insert own, admin anything" on public.runs
    for insert to authenticated
    with check (
        (user_id = (select auth.uid()) and is_synthetic = false)
        or (select public.is_admin())
    );

drop policy if exists "runs: admin purges synthetic" on public.runs;
create policy "runs: admin purges synthetic" on public.runs
    for delete to authenticated
    using ((select public.is_admin()) and is_synthetic);

-- run_agents follow their parent run
drop policy if exists "run_agents: read via run" on public.run_agents;
create policy "run_agents: read via run" on public.run_agents
    for select to authenticated
    using (exists (
        select 1 from public.runs r
        where r.id = run_id and (r.user_id = (select auth.uid()) or (select public.is_admin()))
    ));

drop policy if exists "run_agents: insert via run" on public.run_agents;
create policy "run_agents: insert via run" on public.run_agents
    for insert to authenticated
    with check (exists (
        select 1 from public.runs r
        where r.id = run_id and (r.user_id = (select auth.uid()) or (select public.is_admin()))
    ));

-- ── Promote your first admin (run once, with your own email) ─────────────
-- update public.profiles set role = 'admin', max_eur_per_request = null,
--        daily_eur_limit = null, weekly_eur_limit = null, monthly_eur_limit = null
-- where email = 'you@example.com';
