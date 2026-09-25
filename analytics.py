"""SQL analytics for the admin console, powered by DuckDB.

Usage rows are loaded from the database (subject to RLS), then analysed
in-process with DuckDB — a columnar SQL engine with a PostgreSQL-flavoured
dialect. Each query is a named constant so the UI can show the exact SQL
behind every chart ("show me the query" is a CTO's first question).
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

TZ_PLACEHOLDER = "{tz}"


@dataclass(frozen=True)
class Query:
    """A named, displayable SQL query."""

    title: str
    sql: str


KPIS = Query(
    "Indicateurs du mois",
    """
select
    coalesce(sum(cost_eur), 0)                                          as spend_eur,
    count(*) filter (where status = 'success')                          as successful_runs,
    count(*) filter (where status = 'blocked')                          as blocked_runs,
    count(*) filter (where status = 'error')                            as failed_runs,
    count(distinct user_id)                                             as active_users,
    coalesce(avg(cost_eur) filter (where status = 'success' and kind = 'pipeline'), 0) as avg_run_eur,
    coalesce(sum(input_tokens + output_tokens), 0)                      as tokens
from runs
where timezone('{tz}', created_at) >= date_trunc('month', timezone('{tz}', now()))
""",
)

DAILY_BY_AGENT = Query(
    "Dépense quotidienne par agent (€)",
    """
select
    cast(timezone('{tz}', r.created_at) as date) as day,
    a.agent,
    sum(a.cost_eur)                              as cost_eur
from run_agents a
join runs r on r.id = a.run_id
group by all
order by day, agent
""",
)

DAILY_TOKENS = Query(
    "Tokens consommés par jour",
    """
select
    cast(timezone('{tz}', created_at) as date) as day,
    sum(input_tokens)                          as input_tokens,
    sum(output_tokens)                         as output_tokens,
    sum(cost_eur)                              as cost_eur
from runs
group by all
order by day
""",
)

BY_USER = Query(
    "Consommation par utilisateur (mois en cours)",
    """
with month_runs as (
    select *
    from runs
    where timezone('{tz}', created_at) >= date_trunc('month', timezone('{tz}', now()))
)
select
    p.email,
    p.role,
    count(r.id)                                                  as runs,
    coalesce(sum(r.cost_eur), 0)                                 as spend_eur,
    coalesce(avg(r.cost_eur) filter (where r.status = 'success'), 0) as avg_run_eur,
    count(r.id) filter (where r.status = 'blocked')              as blocked,
    p.monthly_eur_limit,
    case when p.monthly_eur_limit > 0
         then coalesce(sum(r.cost_eur), 0) / p.monthly_eur_limit end as quota_used
from profiles p
left join month_runs r on r.user_id = p.id
group by p.id, p.email, p.role, p.monthly_eur_limit
order by spend_eur desc
""",
)

COST_DRIVERS = Query(
    "Coût par run vs taille de l'input",
    """
select
    id,
    email,
    input_chars,
    stories_count,
    cost_eur,
    duration_s
from runs
where status = 'success' and kind = 'pipeline'
order by created_at
""",
)

ALL_QUERIES = (KPIS, DAILY_BY_AGENT, DAILY_TOKENS, BY_USER, COST_DRIVERS)


def render_sql(query: Query, tz: str) -> str:
    """SQL text with the timezone inlined (for execution and display)."""
    return query.sql.replace(TZ_PLACEHOLDER, tz.replace("'", "")).strip()


def run(query: Query, *, runs: pd.DataFrame, agents: pd.DataFrame, profiles: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Execute ``query`` on in-memory tables ``runs``, ``run_agents``, ``profiles``.

    A fresh DuckDB connection per call keeps this thread-safe (Streamlit
    serves several sessions from one process).
    """
    con = duckdb.connect(database=":memory:")
    try:
        con.register("runs", runs)
        con.register("run_agents", agents)
        con.register("profiles", profiles)
        return con.execute(render_sql(query, tz)).df()
    finally:
        con.close()
