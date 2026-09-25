"""Synthetic usage history, so the admin console is meaningful in a demo.

Rows are flagged ``is_synthetic = true`` in the database: they can be hidden
in every chart and purged in one click. Patterns are realistic on purpose —
weekday seasonality, adoption growth, heavy vs light users, a cost driven by
input size and number of stories, occasional errors and quota blocks — so
the ML models have real signal to learn.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from store import AgentRecord, CallRecord, Profile, RunRecord

AGENT_SPLIT = {"FeedbackAnalyst": 0.28, "PrioritizationStrategist": 0.30, "UserStoryWriter": 0.42}


def generate_runs(
    profiles: Sequence[Profile],
    *,
    today: date,
    days: int = 60,
    model: str = "claude-sonnet-5",
    usd_to_eur: float = 0.86,
    tz: str = "Europe/Paris",
    seed: int = 42,
) -> list[RunRecord]:
    """Generate ``days`` of plausible runs for the given profiles.

    Args:
        profiles: Users to attribute runs to.
        today: Last day of the generated period (inclusive).
        days: Length of the history.
        model: Model name written on each run.
        usd_to_eur: Rate used to derive USD costs and token counts.
        tz: Timezone of the office hours used for timestamps.
        seed: Random seed (deterministic output).

    Returns:
        Synthetic :class:`RunRecord` objects, oldest first.
    """
    if not profiles:
        return []
    rng = np.random.default_rng(seed)
    zone = ZoneInfo(tz)
    intensity = {p.id: (1.4 if p.is_admin else float(rng.uniform(0.35, 1.1))) for p in profiles}
    runs: list[RunRecord] = []

    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        weekday_factor = 1.0 if day.weekday() < 5 else 0.15
        growth = 0.45 + 0.9 * (days - offset) / max(days, 1)  # adoption ramps up
        for profile in profiles:
            for _ in range(int(rng.poisson(intensity[profile.id] * weekday_factor * growth))):
                runs.append(_one_run(rng, profile, day, zone, model, usd_to_eur))

    runs.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=zone))
    return runs


def _one_run(
    rng: np.random.Generator, profile: Profile, day: date, zone: ZoneInfo, model: str, usd_to_eur: float
) -> RunRecord:
    minute = int(rng.integers(8 * 60, 19 * 60))
    created_at = datetime.combine(day, time(minute // 60, minute % 60), tzinfo=zone)
    is_story = rng.random() < 0.15

    if is_story:
        chars, stories, features = 0, 1, 0
        cost = max(0.05 + rng.normal(0, 0.008), 0.02)
    else:
        chars = int(np.clip(rng.lognormal(np.log(6000), 0.55), 1200, 30000))
        stories = int(rng.choice([1, 2, 3, 4, 5], p=[0.08, 0.2, 0.42, 0.18, 0.12]))
        features = int(np.clip(round(chars / 1400 + rng.normal(0, 1)), 2, 12))
        cost = max(0.025 + 0.011 * chars / 1000 + 0.042 * stories + rng.normal(0, 0.018), 0.02)

    status = "success"
    roll = rng.random()
    if roll < 0.02:
        status, cost = "blocked", 0.0
    elif roll < 0.06:
        status, cost = "error", cost * 0.35

    cost_usd = cost / usd_to_eur
    input_tokens = int(chars / 3.3 * 2.4 + 3500 * (stories + 1)) if status != "blocked" else 0
    output_tokens = max(int((cost_usd * 1e6 - input_tokens * 2.0) / 10.0), 0)
    duration = 0.0 if status == "blocked" else float(20 + 5.5 * chars / 1000 + 11 * stories + rng.normal(0, 4))

    split = {"UserStoryWriter": 1.0} if is_story else AGENT_SPLIT
    agents = tuple(
        AgentRecord(
            agent=name,
            calls=(stories if name == "UserStoryWriter" else 1),
            input_tokens=int(input_tokens * share),
            output_tokens=int(output_tokens * share),
            cost_eur=round(cost * share, 6),
            seconds=round(max(duration, 0) * share, 2),
        )
        for name, share in split.items()
        if status != "blocked"
    )
    calls = _synthetic_calls(rng, created_at, agents, duration, stories) if status != "blocked" else ()
    return RunRecord(
        user_id=profile.id,
        kind="story" if is_story else "pipeline",
        status=status,
        model=model,
        input_chars=chars,
        features_count=features,
        stories_count=stories,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 6),
        cost_eur=round(cost, 6),
        duration_s=round(max(duration, 0), 2),
        error="Synthetic error" if status == "error" else ("Quota" if status == "blocked" else None),
        is_synthetic=True,
        created_at=created_at,
        agents=agents,
        calls=calls,
    )


_NO_THINKING = "Donnée synthétique : aucune réflexion enregistrée."


def _synthetic_calls(
    rng: np.random.Generator, start: datetime, agents: tuple[AgentRecord, ...], duration: float, stories: int
) -> tuple[CallRecord, ...]:
    """Plausible per-request timeline: analyst, then strategist, then writers in parallel."""
    by_name = {a.agent: a for a in agents}
    calls: list[CallRecord] = []
    offset = 0.0
    for name in ("FeedbackAnalyst", "PrioritizationStrategist"):
        if name in by_name:
            share = 0.28 if name == "FeedbackAnalyst" else 0.32
            seconds = max(duration * share, 1.0)
            a = by_name[name]
            calls.append(CallRecord(len(calls) + 1, name, start + timedelta(seconds=offset), seconds, 1, "success",
                                    "end_turn", a.input_tokens, a.output_tokens, _NO_THINKING))  # fmt: skip
            offset += seconds
    writer = by_name.get("UserStoryWriter")
    if writer:
        n = max(stories, 1)
        for _ in range(n):
            seconds = max(duration * 0.4 * float(rng.uniform(0.75, 1.0)), 1.0)
            calls.append(CallRecord(len(calls) + 1, "UserStoryWriter", start + timedelta(seconds=offset), seconds, 1,
                                    "success", "end_turn", writer.input_tokens // n, writer.output_tokens // n,
                                    _NO_THINKING))  # fmt: skip
    return tuple(calls)
