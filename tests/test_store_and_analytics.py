"""SQLite repository, local auth, quotas and DuckDB analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import analytics as sql
from auth import AuthError, LocalAuthService, build_auth_service
from config import Settings
from governance import Quota
from store import AgentRecord, Profile, RunRecord, SQLiteRepository, hash_password, verify_password

SINCE = datetime(2000, 1, 1, tzinfo=timezone.utc)
_AGENTS = ("FeedbackAnalyst", "PrioritizationStrategist", "UserStoryWriter")


def usage(profiles: list[Profile], days: int, *, synthetic: bool = False) -> list[RunRecord]:
    """A few real-looking runs per user and day, today included: every status and kind the admin shows."""
    now = datetime.now(timezone.utc)
    runs = []
    for day in range(days):
        when = now - timedelta(days=day)
        for p in profiles:
            agents = tuple(AgentRecord(a, 1, 5000, 3000, 0.05, 30.0) for a in _AGENTS)
            common = {"user_id": p.id, "model": "claude-sonnet-5", "created_at": when, "is_synthetic": synthetic}
            runs += [
                RunRecord(kind="pipeline", status="success", input_chars=5000 + 100 * day, features_count=5,
                          stories_count=3, input_tokens=15000, output_tokens=9000, cost_usd=0.19, cost_eur=0.16,
                          duration_s=110.0, agents=agents, **common),
                RunRecord(kind="story", status="success", stories_count=1, input_tokens=2800, output_tokens=2400,
                          cost_usd=0.03, cost_eur=0.026, duration_s=25.0, **common),
                RunRecord(kind="pipeline", status="blocked", **common),
                RunRecord(kind="pipeline", status="error", error="timeout", **common),
            ]  # fmt: skip
    return runs


@pytest.fixture
def repo(tmp_path) -> SQLiteRepository:
    return SQLiteRepository(tmp_path / "test.db")


def test_password_hashing() -> None:
    stored = hash_password("s3cret")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", None)


def test_local_auth(tmp_path) -> None:
    service = LocalAuthService(str(tmp_path / "a.db"), "dev-pass")
    assert service.sign_in("ADMIN@local.dev ", "dev-pass").is_admin
    member = service.sign_in("demo@local.dev", "dev-pass")
    assert not member.is_admin and member.quota.daily_eur == 2.0
    with pytest.raises(AuthError):
        service.sign_in("demo@local.dev", "nope")


def test_auth_fails_closed_without_supabase() -> None:
    with pytest.raises(AuthError, match="non configurée"):
        build_auth_service(Settings(anthropic_api_key=None, auth_mode="supabase"))


def test_record_and_read_back(repo: SQLiteRepository) -> None:
    uid = repo.ensure_user("a@test.dev", "pw")
    run = RunRecord(
        user_id=uid, kind="pipeline", status="success", model="m", input_chars=5000, stories_count=3,
        cost_usd=0.3, cost_eur=0.26, agents=(AgentRecord("FeedbackAnalyst", 1, 100, 50, 0.1, 3.0),),
    )  # fmt: skip
    repo.record_run(run)
    runs, agents = repo.fetch_usage(SINCE)
    assert runs.loc[0, "email"] == "a@test.dev" and runs.loc[0, "cost_eur"] == pytest.approx(0.26)
    assert agents.loc[0, "agent"] == "FeedbackAnalyst"
    assert repo.user_costs_since(uid, SINCE)[0][1] == pytest.approx(0.26)


def test_synthetic_data_never_counts_towards_quotas(repo: SQLiteRepository) -> None:
    uid = repo.ensure_user("a@test.dev", "pw")
    repo.insert_runs(usage(repo.list_profiles(), days=10, synthetic=True))  # legacy generated rows
    assert repo.user_costs_since(uid, SINCE) == []
    assert repo.total_real_cost_usd() == 0


def test_update_profile(repo: SQLiteRepository) -> None:
    uid = repo.ensure_user("a@test.dev", "pw")
    repo.update_profile(uid, "admin", Quota(daily_eur=3.5))
    profile = repo.get_profile(uid)
    assert profile.is_admin and profile.quota == Quota(daily_eur=3.5)


def test_every_admin_query_runs(repo: SQLiteRepository) -> None:
    repo.ensure_user("admin@test.dev", "pw", role="admin")
    repo.ensure_user("a@test.dev", "pw")
    profiles = repo.list_profiles()
    repo.insert_runs(usage(profiles, days=40))
    runs, agents = repo.fetch_usage(datetime.now(timezone.utc) - timedelta(days=90))
    profiles_df = pd.DataFrame(
        [{"id": p.id, "email": p.email, "role": p.role, "monthly_eur_limit": p.quota.monthly_eur} for p in profiles]
    )
    for query in sql.ALL_QUERIES:
        result = sql.run(query, runs=runs, agents=agents, profiles=profiles_df, tz="Europe/Paris")
        assert not result.empty, query.title
    by_user = sql.run(sql.BY_USER, runs=runs, agents=agents, profiles=profiles_df, tz="Europe/Paris")
    assert set(by_user["email"]) == {"admin@test.dev", "a@test.dev"}


def test_queries_survive_empty_tables(repo: SQLiteRepository) -> None:
    runs, agents = repo.fetch_usage(SINCE)
    profiles_df = pd.DataFrame(columns=["id", "email", "role", "monthly_eur_limit"]).astype(
        {"monthly_eur_limit": float}
    )
    kpi = sql.run(sql.KPIS, runs=runs, agents=agents, profiles=profiles_df, tz="Europe/Paris")
    assert kpi.loc[0, "spend_eur"] == 0


def test_agent_journal_roundtrip(repo: SQLiteRepository) -> None:
    from store import CallRecord

    uid = repo.ensure_user("a@test.dev", "pw")
    start = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
    run = RunRecord(
        user_id=uid, kind="pipeline", status="success", model="m",
        calls=(
            CallRecord(1, "FeedbackAnalyst", start, 12.5, 1, "success", "end_turn", 4000, 3000, "Je segmente…", "{}"),
            CallRecord(2, "PrioritizationStrategist", start, 20.0, 1, "retry", "end_turn", 5000, 4000, "", "{}", "bad"),
        ),
    )  # fmt: skip
    repo.record_run(run)
    calls = repo.fetch_calls([run.id])
    assert list(calls["agent"]) == ["FeedbackAnalyst", "PrioritizationStrategist"]
    assert calls.loc[0, "thinking"] == "Je segmente…" and calls.loc[1, "status"] == "retry"
    assert repo.fetch_calls([]).empty
