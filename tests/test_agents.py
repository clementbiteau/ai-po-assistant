"""Offline tests: deterministic scoring, gateway robustness, full pipeline, exports.

The Anthropic client is replaced by a fake, so the suite runs in < 1 s,
costs nothing and needs no API key:  pytest -q
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from agents import (
    AgentAuthError,
    AgentOutputError,
    AgentTimeoutError,
    ClaudeGateway,
    GherkinScenario,
    PipelineResult,
    POAssistantPipeline,
    PrioritizationOutput,
    backlog_order,
    compute_rice,
    moscow_bucket,
    score_portfolio,
)
from config import Settings
from exporters import to_feature_files, to_jira_csv, to_markdown

DEMO = PipelineResult.model_validate_json(
    (Path(__file__).parent.parent / "data" / "demo_result.json").read_text(encoding="utf-8")
)
SETTINGS = Settings(anthropic_api_key="sk-ant-test", max_retries=0)


# ── Fakes ────────────────────────────────────────────────────────────────


def fake_message(text: str, stop_reason: str = "end_turn", thinking: str = "") -> SimpleNamespace:
    """Mimic the attributes of ``anthropic.types.Message`` the gateway reads."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=thinking), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=100, output_tokens=50, cache_creation_input_tokens=0, cache_read_input_tokens=0
        ),
        _request_id="req_test",
    )


class FakeMessages:
    """Replays queued responses, or routes by agent when given a router."""

    def __init__(self, responses: list[Any] | None = None, router: Any = None) -> None:
        self.responses = list(responses or [])
        self.router = router
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.router:
            return self.router(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def gateway_with(messages: FakeMessages) -> ClaudeGateway:
    gateway = ClaudeGateway(SETTINGS)
    gateway._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]
    return gateway


def demo_router(kwargs: dict[str, Any]) -> SimpleNamespace:
    """Answer each agent with the matching slice of the demo fixture."""
    system, prompt = kwargs["system"], kwargs["messages"][-1]["content"]
    if system.startswith("You are FeedbackAnalyst"):
        return fake_message(DEMO.analysis.model_dump_json())
    if system.startswith("You are PrioritizationStrategist"):
        output = PrioritizationOutput(
            assessments=[s.assessment for s in DEMO.scored_features], portfolio_insight=DEMO.portfolio_insight
        )
        return fake_message(output.model_dump_json())
    feature_id = re.search(r"Write the user story for (F\d+)", prompt).group(1)  # type: ignore[union-attr]
    story = DEMO.stories.get(feature_id) or next(iter(DEMO.stories.values()))
    return fake_message(story.model_copy(update={"feature_id": feature_id}).model_dump_json())


# ── Deterministic scoring ────────────────────────────────────────────────


def test_compute_rice_formula() -> None:
    assert compute_rice(reach_users=5400, impact=5, confidence_pct=100, effort=3) == 9000.0
    assert compute_rice(reach_users=1000, impact=2, confidence_pct=50, effort=0) == 1000.0  # effort clamped


def test_moscow_is_relative_and_mandatory_wins() -> None:
    assert moscow_bucket(900, 1000) == "Must"
    assert moscow_bucket(400, 1000) == "Should"
    assert moscow_bucket(150, 1000) == "Could"
    assert moscow_bucket(50, 1000) == "Won't"
    assert moscow_bucket(1, 1000, is_mandatory=True) == "Must"


def test_score_portfolio_ranks_and_backlog_puts_mandatory_first() -> None:
    pairs = [(s.feature, s.assessment) for s in DEMO.scored_features]
    scored = score_portfolio(pairs, active_users=12_000)
    assert [s.rank for s in scored] == [1, 2, 3, 4, 5]
    assert scored[0].feature.id == "F1"
    order = [s.feature.id for s in backlog_order(scored)]
    assert order[:2] == ["F1", "F4"]  # SSO is a mandatory Must despite a lower RICE
    assert "F5" not in order  # Won't is excluded


def test_gherkin_rendering_strips_duplicate_keywords() -> None:
    scenario = GherkinScenario(
        title="Digest", given=["Given a manager", "and 3 projects"], when=["When it is 8am"], then=["Then one email."]
    )
    assert scenario.to_gherkin().splitlines() == [
        "  Scenario: Digest",
        "    Given a manager",
        "    And 3 projects",
        "    When it is 8am",
        "    Then one email",
    ]


# ── Gateway robustness ───────────────────────────────────────────────────


def test_gateway_self_corrects_after_invalid_answer() -> None:
    valid = PrioritizationOutput(assessments=[DEMO.scored_features[0].assessment], portfolio_insight="ok")
    invalid = json.loads(valid.model_dump_json())
    invalid["assessments"][0]["impact"] = 7  # outside the 1-5 scale
    messages = FakeMessages([fake_message(json.dumps(invalid)), fake_message(valid.model_dump_json())])

    result = gateway_with(messages).structured(
        agent="t", system="s", prompt="p", schema=PrioritizationOutput, effort="low"
    )

    assert result == valid
    assert len(messages.calls) == 2
    assert "not valid" in messages.calls[1]["messages"][-1]["content"]
    assert messages.calls[0]["output_config"]["format"]["type"] == "json_schema"
    assert messages.calls[0]["thinking"] == {"type": "adaptive", "display": "summarized"}


def test_gateway_gives_up_after_one_retry() -> None:
    messages = FakeMessages([fake_message("{}"), fake_message("{}")])
    with pytest.raises(AgentOutputError):
        gateway_with(messages).structured(agent="t", system="s", prompt="p", schema=PrioritizationOutput, effort="low")


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_gateway_rejects_refusals_and_truncations(stop_reason: str) -> None:
    messages = FakeMessages([fake_message("{", stop_reason=stop_reason)])
    with pytest.raises(AgentOutputError):
        gateway_with(messages).structured(agent="t", system="s", prompt="p", schema=PrioritizationOutput, effort="low")


def test_gateway_maps_sdk_errors() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    auth = anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=request), body=None)
    for error, expected in ((auth, AgentAuthError), (anthropic.APITimeoutError(request=request), AgentTimeoutError)):
        with pytest.raises(expected):
            gateway_with(FakeMessages([error])).structured(
                agent="t", system="s", prompt="p", schema=PrioritizationOutput, effort="low"
            )


def test_missing_api_key_is_a_typed_error() -> None:
    with pytest.raises(AgentAuthError):
        ClaudeGateway(Settings(anthropic_api_key=None))


# ── End-to-end pipeline (fake LLM) ───────────────────────────────────────


def test_pipeline_end_to_end_with_events() -> None:
    events = []
    pipeline = POAssistantPipeline(SETTINGS, on_event=events.append)
    pipeline.gateway._client = SimpleNamespace(messages=FakeMessages(router=demo_router))  # type: ignore[assignment]

    result = pipeline.run("x" * 200, DEMO.context, top_n=3)

    assert [s.feature.id for s in result.scored_features][:2] == ["F1", "F3"]
    assert set(result.stories) == {"F1", "F4", "F3"}
    assert result.usage.per_agent["UserStoryWriter"].calls == 3
    assert result.usage.estimated_cost_usd and result.usage.estimated_cost_usd > 0
    assert [(e.step, e.status) for e in events if e.status != "running"] == [
        ("analyst", "done"),
        ("strategist", "done"),
        ("writer", "done"),
    ]


def test_strategist_must_score_every_feature() -> None:
    def router(kwargs: dict[str, Any]) -> SimpleNamespace:
        if kwargs["system"].startswith("You are PrioritizationStrategist"):
            partial = PrioritizationOutput(assessments=[DEMO.scored_features[0].assessment], portfolio_insight="x")
            return fake_message(partial.model_dump_json())
        return demo_router(kwargs)

    pipeline = POAssistantPipeline(SETTINGS)
    pipeline.gateway._client = SimpleNamespace(messages=FakeMessages(router=router))  # type: ignore[assignment]
    with pytest.raises(AgentOutputError):
        pipeline.run("x" * 200, DEMO.context)


# ── Exports ──────────────────────────────────────────────────────────────


def test_jira_csv_is_importable() -> None:
    rows = list(csv.reader(io.StringIO(to_jira_csv(DEMO).decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    assert header[:4] == ["Summary", "Issue Type", "Priority", "Story Points"]
    assert header.count("Labels") == 4
    assert len(body) == len(DEMO.stories)
    assert body[0][2] == "Highest"  # F1 is a Must
    assert "Scenario:" in body[0][-1] and "{noformat}" in body[0][-1]


def test_markdown_and_feature_exports() -> None:
    assert "## Priorisation RICE" in to_markdown(DEMO)
    features = to_feature_files(DEMO)
    assert features.count("Feature:") == len(DEMO.stories)
    assert all(line.startswith(("#", "Feature:", "  ", "")) for line in features.splitlines())


def test_budget_cap_stops_the_pipeline() -> None:
    from agents import AgentBudgetError

    pipeline = POAssistantPipeline(SETTINGS, budget_usd=0.000001)
    pipeline.gateway._client = SimpleNamespace(messages=FakeMessages(router=demo_router))  # type: ignore[assignment]
    with pytest.raises(AgentBudgetError):
        pipeline.run("x" * 200, DEMO.context)
    assert pipeline.tracker.cost_usd(SETTINGS.pricing) > 0  # the first call was made and is accounted for


def test_every_request_is_journaled_with_its_reasoning() -> None:
    valid = PrioritizationOutput(assessments=[DEMO.scored_features[0].assessment], portfolio_insight="ok")
    messages = FakeMessages(
        [fake_message("{}", thinking="first try"), fake_message(valid.model_dump_json(), thinking="fixed it")]
    )
    gateway = gateway_with(messages)
    gateway.structured(
        agent="PrioritizationStrategist", system="s", prompt="p", schema=PrioritizationOutput, effort="low"
    )
    calls = gateway.tracker.report(0.0, None).calls
    assert [(c.seq, c.attempt, c.status) for c in calls] == [(1, 1, "retry"), (2, 2, "success")]
    assert calls[1].thinking == "fixed it" and calls[1].input_tokens == 100 and calls[1].output_excerpt


def test_pipeline_keeps_the_source_text_and_journal() -> None:
    pipeline = POAssistantPipeline(SETTINGS)
    pipeline.gateway._client = SimpleNamespace(messages=FakeMessages(router=demo_router))  # type: ignore[assignment]
    result = pipeline.run("x" * 200, DEMO.context, top_n=2)
    assert result.source_text == "x" * 200
    assert [c.agent for c in result.usage.calls][:2] == ["FeedbackAnalyst", "PrioritizationStrategist"]
    assert len(result.usage.calls) == 4


def test_quote_grounding() -> None:
    from agents import quote_in_source

    source = "Bonjour, je passe la première heure de ma journée à trier les notifs Orbit. Merci !"
    assert quote_in_source("je passe la première heure de ma journée à trier les notifs", source)
    assert quote_in_source("Je passe la première heure… trier les notifs Orbit", source)  # ellipsis
    assert not quote_in_source("je perds une heure par jour à trier mes notifications", source)  # paraphrase
    assert not quote_in_source("…", source)
    assert all(quote_in_source(q, DEMO.source_text) for f in DEMO.analysis.feature_requests for q in f.evidence_quotes)
