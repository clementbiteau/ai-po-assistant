"""SQLite repository, local auth, synthetic data and DuckDB analytics."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

import analytics as sql
from auth import AuthError, LocalAuthService, build_auth_service
from config import Settings
from governance import Quota
from store import AgentRecord, RunRecord, SQLiteRepository, hash_password, verify_password
from synthetic import generate_runs

SINCE = datetime(2000, 1, 1, tzinfo=timezone.utc)


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
    repo.insert_runs(generate_runs(repo.list_profiles(), today=date.today(), days=10))
    assert repo.user_costs_since(uid, SINCE) == []
    assert repo.purge_synthetic() > 0
    assert repo.fetch_usage(SINCE)[0].empty


def test_update_profile(repo: SQLiteRepository) -> None:
    uid = repo.ensure_user("a@test.dev", "pw")
    repo.update_profile(uid, "admin", Quota(daily_eur=3.5))
    profile = repo.get_profile(uid)
    assert profile.is_admin and profile.quota == Quota(daily_eur=3.5)


def test_every_admin_query_runs(repo: SQLiteRepository) -> None:
    repo.ensure_user("admin@test.dev", "pw", role="admin")
    repo.ensure_user("a@test.dev", "pw")
    profiles = repo.list_profiles()
    repo.insert_runs(generate_runs(profiles, today=date.today(), days=40))
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


def test_synthetic_runs_come_with_a_journal(repo: SQLiteRepository) -> None:
    repo.ensure_user("a@test.dev", "pw")
    runs = generate_runs(repo.list_profiles(), today=date.today(), days=5)
    repo.insert_runs(runs)
    pipeline = next(r for r in runs if r.kind == "pipeline" and r.status == "success")
    calls = repo.fetch_calls([pipeline.id])
    assert list(calls["agent"])[:2] == ["FeedbackAnalyst", "PrioritizationStrategist"]
    assert (calls["agent"] == "UserStoryWriter").sum() == pipeline.stories_count
