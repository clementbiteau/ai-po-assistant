"""Model choice per agent, run details and the admin run comparison (offline)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from agents import ClaudeGateway, POAssistantPipeline, PrioritizationOutput, ranking_summary
from config import AGENT_KEYS, EFFORTS, MODELS, PRESETS, AgentModels, Settings
from store import RunDetails, RunRecord, SQLiteRepository
from tests.test_agents import DEMO, SETTINGS, FakeMessages, demo_router, fake_message
from ui.runs import config_summary, critical_path, match_rankings, ranking_verdict

VALID = PrioritizationOutput(assessments=[DEMO.scored_features[0].assessment], portfolio_insight="ok")


def call(gateway: ClaudeGateway, model: str, effort: str = "medium") -> None:
    gateway.structured(agent="t", system="s", prompt="p", schema=PrioritizationOutput, effort=effort, model=model)


# ── Request shape per model ──────────────────────────────────────────────


def test_each_model_gets_the_request_it_supports() -> None:
    std = FakeMessages([fake_message(VALID.model_dump_json())] * 3)
    gateway = ClaudeGateway(SETTINGS)
    gateway._client = SimpleNamespace(messages=std)  # type: ignore[assignment]

    call(gateway, "claude-sonnet-5", "high")
    sonnet = std.calls[-1]
    assert sonnet["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert sonnet["output_config"]["effort"] == "high"

    call(gateway, "claude-haiku-4-5", "medium")  # no effort parameter: a thinking budget instead
    haiku = std.calls[-1]
    assert "effort" not in haiku["output_config"] and haiku["output_config"]["format"]["type"] == "json_schema"
    assert haiku["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    call(gateway, "claude-haiku-4-5", "low")
    assert "thinking" not in std.calls[-1]


def test_each_agent_runs_and_is_costed_on_its_own_model() -> None:
    settings = replace(SETTINGS, models=AgentModels(writer="claude-haiku-4-5"))
    messages = FakeMessages(router=demo_router)
    pipeline = POAssistantPipeline(settings)
    pipeline.gateway._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]

    result = pipeline.run("x" * 200, DEMO.context, top_n=2)

    assert [c["model"] for c in messages.calls] == [
        "claude-sonnet-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "claude-haiku-4-5",
    ]
    assert result.config["writer"] == {"model": "claude-haiku-4-5", "effort": "medium"}
    assert result.model == "claude-sonnet-5 / claude-sonnet-5 / claude-haiku-4-5"
    usage = result.usage.per_agent
    assert usage["UserStoryWriter"].model == "claude-haiku-4-5"
    # every fake call uses 100 input / 50 output tokens: 2 on Sonnet ($2/$10), 2 on Haiku ($1/$5)
    assert abs(result.usage.estimated_cost_usd - (2 * (100 * 2 + 50 * 10) + 2 * (100 * 1 + 50 * 5)) / 1e6) < 1e-12
    assert {c.model for c in result.usage.calls} == {"claude-sonnet-5", "claude-haiku-4-5"}


# ── Configuration ────────────────────────────────────────────────────────


def test_presets_are_valid_and_priced() -> None:
    base = Settings(anthropic_api_key="x")
    assert abs(base.estimated_run_usd() * 0.86 - 0.163) < 0.001  # reproduces the measured reference run
    costs = {}
    for key, preset in PRESETS.items():
        assert set(preset.config) == set(AGENT_KEYS) and preset.rationale
        for c in preset.config.values():
            assert c["model"] in MODELS and c["effort"] in EFFORTS
        costs[key] = base.with_agent_config(preset.config).estimated_run_usd()
    assert costs["all_haiku"] < costs["writer_haiku"] < costs["reference"]
    assert not any("opus" in m or "fable" in m for m in MODELS)  # judged overkill for this task


def test_agent_config_ignores_unknown_values() -> None:
    base = Settings(anthropic_api_key="x")
    changed = base.with_agent_config(
        {"writer": {"model": "gpt-4", "effort": "turbo"}, "analyst": {"model": "claude-haiku-4-5"}}
    )
    assert changed.model_for("writer") == base.model_for("writer") and changed.efforts.writer == base.efforts.writer
    assert changed.model_for("analyst") == "claude-haiku-4-5"


# ── Storage ──────────────────────────────────────────────────────────────


def test_run_details_roundtrip(tmp_path) -> None:
    repo = SQLiteRepository(tmp_path / "t.db")
    user = repo.ensure_user("admin@x.dev", "pw", role="admin")
    ranking = ranking_summary(DEMO)
    details = RunDetails(
        "Notifications & churn", DEMO.config or SETTINGS.run_config(), ranking, DEMO.model_dump(mode="json")
    )
    run = RunRecord(user_id=user, kind="pipeline", status="success", model="m", details=details)
    repo.record_run(run)
    repo.record_run(RunRecord(user_id=user, kind="pipeline", status="success", model="m"))  # before tracking

    frame = repo.fetch_details([run.id])
    assert frame.loc[0, "case_label"] == "Notifications & churn"
    assert frame.loc[0, "config"]["strategist"]["effort"] == "high"
    assert [f["rank"] for f in frame.loc[0, "ranking"]] == sorted(f["rank"] for f in ranking)
    reopened = type(DEMO).model_validate(repo.fetch_result(run.id))
    assert reopened.analysis == DEMO.analysis
    assert repo.fetch_result("missing") is None


# ── Comparison helpers ───────────────────────────────────────────────────


def _feature(title: str, rank: int, moscow: str = "Should") -> dict:
    return {"title": title, "rank": rank, "rice": 100.0 / rank, "moscow": moscow, "impact": 3, "effort": 2}


def test_rankings_match_by_title_and_verdict() -> None:
    a = [
        _feature("Maîtrise des notifications", 1),
        _feature("Alertes Slack et Teams", 2),
        _feature("Vue de charge", 3),
        _feature("SSO", 4),
    ]
    b_same = [_feature("Maîtrise et regroupement des notifications", 1), _feature("Alertes dans Slack et Teams", 2),
              _feature("Vue de charge par personne", 3), _feature("SSO Azure AD", 4)]  # fmt: skip
    rows = match_rankings(a, b_same)
    assert all(r["a"] and r["b"] for r in rows)
    assert ranking_verdict(a, b_same) == "Même top 3, dans le même ordre."

    b_swapped = [b_same[1] | {"rank": 1}, b_same[0] | {"rank": 2}, b_same[2], b_same[3]]
    assert ranking_verdict(a, b_swapped) == "Même top 3, mais dans un ordre différent."

    b_changed = [b_same[0], b_same[3] | {"rank": 2}, b_same[1] | {"rank": 3}, b_same[2] | {"rank": 4}]
    verdict = ranking_verdict(a, b_changed)
    assert verdict.startswith("Le top 3 change") and "Vue de charge" in verdict and "SSO Azure AD" in verdict
    assert "non comparable" in ranking_verdict(a, [])


def test_critical_path_counts_the_slowest_story_only() -> None:
    now = datetime.now(timezone.utc)
    calls = pd.DataFrame(
        [
            {"run_id": "r", "agent": "FeedbackAnalyst", "duration_s": 29.0, "attempt": 1, "started_at": now},
            {"run_id": "r", "agent": "PrioritizationStrategist", "duration_s": 40.0, "attempt": 1, "started_at": now},
            {"run_id": "r", "agent": "PrioritizationStrategist", "duration_s": 10.0, "attempt": 2, "started_at": now},
            {"run_id": "r", "agent": "UserStoryWriter", "duration_s": 31.0, "attempt": 1, "started_at": now},
            {"run_id": "r", "agent": "UserStoryWriter", "duration_s": 25.0, "attempt": 1, "started_at": now},
        ]
    )
    row = critical_path(calls).set_index("run_id").loc["r"]
    assert (row["Analyste"], row["Stratège"], row["Stories"], row["Corrections"]) == (29.0, 50.0, 31.0, 1)
    assert critical_path(calls.iloc[0:0]).empty


def test_config_summary() -> None:
    config = PRESETS["writer_haiku"].config
    assert config_summary(config) == "Sonnet 5 (moyen) · Sonnet 5 (élevé) · Haiku 4.5 (moyen)"
    assert config_summary({}) == "—"
