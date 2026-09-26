-- ════════════════════════════════════════════════════════════════════════
-- Run details: configuration, case and result of each run (admin "Runs" tab)
--
-- Apply after 20260926000000_agent_calls.sql:
--   Supabase Dashboard › SQL Editor › paste › Run   (or: supabase db push)
--
-- `config`  : model and effort of each agent, e.g.
--             {"strategist": {"model": "claude-sonnet-5", "effort": "high"}, ...}
-- `ranking` : compact prioritisation (id, title, rank, RICE inputs, MoSCoW),
--             light enough to compare many runs at once
-- `result`  : the full result as JSON, to reopen a past run
-- ════════════════════════════════════════════════════════════════════════

create table if not exists public.run_details (
    run_id      uuid  primary key references public.runs (id) on delete cascade,
    case_label  text,
    config      jsonb not null default '{}'::jsonb,
    ranking     jsonb not null default '[]'::jsonb,
    result      jsonb
);

comment on table public.run_details is 'Per-run configuration (model and effort per agent), case and result.';

alter table public.run_details enable row level security;
revoke all on public.run_details from anon;

-- Same rules as agent_calls: follow the parent run.
drop policy if exists "run_details: read via run" on public.run_details;
create policy "run_details: read via run" on public.run_details
    for select to authenticated
    using (exists (
        select 1 from public.runs r
        where r.id = run_id and (r.user_id = (select auth.uid()) or (select public.is_admin()))
    ));

drop policy if exists "run_details: insert via run" on public.run_details;
create policy "run_details: insert via run" on public.run_details
    for insert to authenticated
    with check (exists (
        select 1 from public.runs r
        where r.id = run_id and (r.user_id = (select auth.uid()) or (select public.is_admin()))
    ));
