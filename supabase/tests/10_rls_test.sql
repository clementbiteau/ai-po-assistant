-- RLS behaviour tests. Run after 00_supabase_stub.sql + the migration.
-- Every block raises an exception (and psql stops) if a rule is violated.
\set ON_ERROR_STOP on
begin;

insert into auth.users (id, email) values
    ('00000000-0000-0000-0000-00000000000a', 'admin@test.dev'),
    ('00000000-0000-0000-0000-00000000000b', 'alice@test.dev'),
    ('00000000-0000-0000-0000-00000000000c', 'bob@test.dev');

-- the trigger created profiles with default quotas
do $$ begin
    assert (select count(*) from public.profiles) = 3, 'trigger must create one profile per user';
    assert (select daily_eur_limit from public.profiles where email = 'alice@test.dev') = 2.00, 'default daily quota';
end $$;
update public.profiles set role = 'admin' where email = 'admin@test.dev';

-- ── as Alice (member) ───────────────────────────────────────────────────
set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000b"}';

insert into public.runs (id, user_id, kind, status, model, cost_eur)
values ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-00000000000b', 'pipeline', 'success', 'm', 0.2);
insert into public.run_agents (run_id, agent, calls) values ('10000000-0000-0000-0000-000000000001', 'FeedbackAnalyst', 1);

do $$ begin
    assert (select count(*) from public.profiles) = 1, 'member sees only own profile';
    assert (select count(*) from public.runs) = 1, 'member sees only own runs';
    assert (select public.is_admin()) = false, 'member is not admin';
end $$;

-- cannot insert a run for someone else
do $$ begin
    insert into public.runs (user_id, kind, status, model) values ('00000000-0000-0000-0000-00000000000c', 'pipeline', 'success', 'm');
    raise exception 'FAIL: member inserted a run for another user';
exception when insufficient_privilege then null;
end $$;

-- cannot flag own run as synthetic
do $$ begin
    insert into public.runs (user_id, kind, status, model, is_synthetic) values ('00000000-0000-0000-0000-00000000000b', 'pipeline', 'success', 'm', true);
    raise exception 'FAIL: member inserted synthetic data';
exception when insufficient_privilege then null;
end $$;

-- cannot raise own quota nor become admin (update silently matches 0 rows)
update public.profiles set daily_eur_limit = 999, role = 'admin' where id = '00000000-0000-0000-0000-00000000000b';
-- cannot delete own runs
delete from public.runs;
reset role;
do $$ begin
    assert (select daily_eur_limit from public.profiles where email = 'alice@test.dev') = 2.00, 'member must not change quota';
    assert (select role from public.profiles where email = 'alice@test.dev') = 'member', 'member must not escalate';
    assert (select count(*) from public.runs) = 1, 'member must not delete runs';
end $$;

-- ── as Bob (member) : cannot read Alice's data ───────────────────────────
set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000c"}';
do $$ begin
    assert (select count(*) from public.runs) = 0, 'Bob must not see Alice runs';
    assert (select count(*) from public.run_agents) = 0, 'Bob must not see Alice agent rows';
end $$;

-- ── as admin ─────────────────────────────────────────────────────────────
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000a"}';
do $$ begin
    assert (select public.is_admin()), 'admin detected';
    assert (select count(*) from public.profiles) = 3, 'admin sees all profiles';
    assert (select count(*) from public.runs) = 1, 'admin sees all runs';
end $$;
update public.profiles set daily_eur_limit = 3.5 where email = 'alice@test.dev';
insert into public.runs (user_id, kind, status, model, cost_eur, is_synthetic)
values ('00000000-0000-0000-0000-00000000000c', 'pipeline', 'success', 'm', 0.1, true);
delete from public.runs;  -- only synthetic rows are deletable
do $$ begin
    assert (select daily_eur_limit from public.profiles where email = 'alice@test.dev') = 3.5, 'admin edits quotas';
    assert (select count(*) from public.runs where is_synthetic) = 0, 'admin purges synthetic';
    assert (select count(*) from public.runs where not is_synthetic) = 1, 'admin cannot delete real runs';
end $$;

-- ── anonymous ────────────────────────────────────────────────────────────
reset role;
set local role anon;
do $$ begin
    perform count(*) from public.runs;
    raise exception 'FAIL: anon could read runs';
exception when insufficient_privilege then null;
end $$;

reset role;
rollback;
\echo 'ALL RLS TESTS PASSED'
