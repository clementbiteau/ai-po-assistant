-- ════════════════════════════════════════════════════════════════════════
-- Agent journal: one row per request sent to Claude (admin "Agents" tab)
--
-- Apply after 20260925000000_init.sql:
--   Supabase Dashboard › SQL Editor › paste › Run   (or: supabase db push)
--
-- `thinking` stores the SUMMARISED reasoning returned by the API
-- (thinking.display = "summarized"), never a raw chain of thought.
-- ════════════════════════════════════════════════════════════════════════

create table if not exists public.agent_calls (
    run_id          uuid        not null references public.runs (id) on delete cascade,
    seq             integer     not null,
    agent           text        not null,
    started_at      timestamptz not null,
    duration_s      numeric(10, 3) not null default 0,
    attempt         integer     not null default 1,
    status          text        not null check (status in ('success', 'retry', 'error')),
    stop_reason     text,
    input_tokens    integer     not null default 0 check (input_tokens >= 0),
    output_tokens   integer     not null default 0 check (output_tokens >= 0),
    thinking        text        not null default '',
    output_excerpt  text        not null default '',
    error           text,
    primary key (run_id, seq)
);

comment on table public.agent_calls is 'Per-request agent journal: timing, tokens, summarised reasoning.';

alter table public.agent_calls enable row level security;
revoke all on public.agent_calls from anon;

-- Same rule as run_agents: follow the parent run.
drop policy if exists "agent_calls: read via run" on public.agent_calls;
create policy "agent_calls: read via run" on public.agent_calls
    for select to authenticated
    using (exists (
        select 1 from public.runs r
        where r.id = run_id and (r.user_id = (select auth.uid()) or (select public.is_admin()))
    ));

drop policy if exists "agent_calls: insert via run" on public.agent_calls;
create policy "agent_calls: insert via run" on public.agent_calls
    for insert to authenticated
    with check (exists (
        select 1 from public.runs r
        where r.id = run_id and (r.user_id = (select auth.uid()) or (select public.is_admin()))
    ));
