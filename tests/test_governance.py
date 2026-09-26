"""Quotas, consumption windows and ML cost models (pure functions)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from governance import (
    PRIOR_COEFFICIENTS,
    Consumption,
    CostEstimator,
    Quota,
    consumption_from_runs,
    evaluate_quota,
    forecast_spend,
    period_starts,
)

PARIS = ZoneInfo("Europe/Paris")


def test_period_starts_follow_the_local_calendar() -> None:
    # Wednesday 2026-09-23 00:30 in Paris is still Tuesday 22:30 UTC.
    now = datetime(2026, 9, 22, 22, 30, tzinfo=timezone.utc)
    day, week, month = period_starts(now, "Europe/Paris")
    assert day == datetime(2026, 9, 23, tzinfo=PARIS)
    assert week == datetime(2026, 9, 21, tzinfo=PARIS)  # Monday
    assert month == datetime(2026, 9, 1, tzinfo=PARIS)


def test_consumption_windows() -> None:
    now = datetime(2026, 9, 23, 12, tzinfo=PARIS)
    runs = [
        (datetime(2026, 9, 23, 9, tzinfo=PARIS), 0.30),  # today
        (datetime(2026, 9, 21, 9, tzinfo=PARIS), 0.20),  # this week
        (datetime(2026, 9, 2, 9, tzinfo=PARIS), 0.50),  # this month
        (datetime(2026, 8, 31, 9, tzinfo=PARIS), 9.99),  # last month: ignored
    ]
    assert consumption_from_runs(runs, now) == Consumption(day_eur=0.30, week_eur=0.50, month_eur=1.00)


@pytest.mark.parametrize(
    ("quota", "used", "estimate", "allowed", "budget"),
    [
        (Quota(), Consumption(), 5.0, True, None),  # unlimited
        (Quota(max_eur_per_request=0.5), Consumption(), 0.2, True, 0.5),
        (Quota(max_eur_per_request=0.5), Consumption(), 0.6, False, None),  # estimate too high
        (Quota(daily_eur=2.0), Consumption(day_eur=2.0), 0.1, False, None),  # exhausted
        (Quota(daily_eur=2.0), Consumption(day_eur=1.95), 0.1, False, None),  # would overflow
        (Quota(max_eur_per_request=0.5, weekly_eur=5, monthly_eur=10), Consumption(week_eur=4.8), 0.1, True, 0.2),
    ],
)
def test_evaluate_quota(quota: Quota, used: Consumption, estimate: float, allowed: bool, budget: float | None) -> None:
    decision = evaluate_quota(quota, used, estimate)
    assert decision.allowed is allowed
    if allowed:
        assert decision.budget_eur == pytest.approx(budget) if budget is not None else decision.budget_eur is None
    else:
        assert decision.reason


def test_estimator_uses_prior_until_enough_history() -> None:
    estimate = CostEstimator().fit(pd.DataFrame()).predict(5_500, 3)
    b0, b1, b2 = PRIOR_COEFFICIENTS
    assert estimate.source == "prior"
    assert estimate.point_eur == pytest.approx(b0 + b1 * 5.5 + b2 * 3, abs=1e-4)
    assert estimate.upper_eur > estimate.point_eur


def test_estimator_recovers_true_coefficients() -> None:
    rng = np.random.default_rng(0)
    chars = rng.integers(1_000, 30_000, 200)
    stories = rng.integers(1, 6, 200)
    cost = 0.02 + 0.01 * chars / 1000 + 0.05 * stories + rng.normal(0, 0.005, 200)
    runs = pd.DataFrame(
        {"input_chars": chars, "stories_count": stories, "cost_eur": cost, "status": "success", "kind": "pipeline"}
    )
    model = CostEstimator().fit(runs)
    assert model.report.source == "model"
    assert model.report.r2 > 0.98
    assert model.coefficients == pytest.approx((0.02, 0.01, 0.05), abs=3e-3)


def test_forecast_projects_a_growing_trend() -> None:
    today = date(2026, 9, 20)
    days = [today - timedelta(days=i) for i in range(28)]
    daily = pd.DataFrame({"day": days, "cost_eur": [1.0 + 0.1 * (27 - i) for i in range(28)]})
    forecast = forecast_spend(daily, today)
    assert forecast.slope_eur_per_day == pytest.approx(0.1, abs=1e-6)
    assert forecast.month_end_projection_eur > forecast.month_to_date_eur
    assert forecast.frame["is_forecast"].sum() == 30


def test_forecast_handles_no_data() -> None:
    forecast = forecast_spend(pd.DataFrame(columns=["day", "cost_eur"]), date(2026, 9, 20))
    assert forecast.month_end_projection_eur == 0
