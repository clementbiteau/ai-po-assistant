"""Cost governance: quotas, consumption windows and ML cost models.

Everything here is pure Python / NumPy — no Streamlit, no database — so the
rules that protect the API budget are fully unit-tested.

* :func:`evaluate_quota` decides whether a user may launch a run, and with
  which hard spending cap, given their per-request / daily / weekly /
  monthly limits.
* :class:`CostEstimator` predicts the cost of a run *before* it starts, with
  an ordinary-least-squares regression trained on past runs
  (``cost ≈ β0 + β1·kchars + β2·stories``) and a conservative prior when
  history is too thin.
* :func:`forecast_spend` projects daily spend with a linear trend and a
  prediction band, to anticipate the month-end bill.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════════
# Quotas
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Quota:
    """Spending limits of one user, in euros. ``None`` means unlimited."""

    max_eur_per_request: float | None = None
    daily_eur: float | None = None
    weekly_eur: float | None = None
    monthly_eur: float | None = None

    @property
    def is_unlimited(self) -> bool:
        """True when no limit at all is set."""
        return all(v is None for v in (self.max_eur_per_request, self.daily_eur, self.weekly_eur, self.monthly_eur))


@dataclass(frozen=True)
class Consumption:
    """What a user already spent in each rolling calendar window, in euros."""

    day_eur: float = 0.0
    week_eur: float = 0.0
    month_eur: float = 0.0


@dataclass(frozen=True)
class QuotaDecision:
    """Outcome of :func:`evaluate_quota`.

    Attributes:
        allowed: Whether the run may start.
        reason: Human-readable explanation when blocked (French).
        budget_eur: Hard cap to enforce during the run (``None`` = no cap).
    """

    allowed: bool
    reason: str | None = None
    budget_eur: float | None = None


def period_starts(now: datetime, tz: str = "Europe/Paris") -> tuple[datetime, datetime, datetime]:
    """Start of the current day, ISO week (Monday) and month in ``tz``.

    Returns timezone-aware datetimes, directly comparable with the
    ``timestamptz`` values stored in the database.
    """
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    day = datetime.combine(local.date(), time.min, tzinfo=zone)
    week = day - timedelta(days=local.weekday())
    month = day.replace(day=1)
    return day, week, month


def consumption_from_runs(
    runs: Iterable[tuple[datetime, float]], now: datetime, tz: str = "Europe/Paris"
) -> Consumption:
    """Aggregate ``(created_at, cost_eur)`` pairs into day / week / month totals."""
    day, week, month = period_starts(now, tz)
    d = w = m = 0.0
    for created_at, cost in runs:
        cost = float(cost or 0.0)
        if created_at >= month:
            m += cost
        if created_at >= week:
            w += cost
        if created_at >= day:
            d += cost
    return Consumption(day_eur=round(d, 6), week_eur=round(w, 6), month_eur=round(m, 6))


def _fmt(value: float) -> str:
    """French euro formatting: ``1 234,56 €``."""
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def evaluate_quota(quota: Quota, used: Consumption, estimated_eur: float) -> QuotaDecision:
    """Decide whether a run fits in the user's limits.

    Rules, in order:

    1. A window already exhausted blocks the run.
    2. A run whose *estimated* cost exceeds the per-request limit, or what
       is left in any window, is blocked before spending anything.
    3. Otherwise the run is allowed, with a hard cap equal to the tightest
       remaining allowance, enforced call by call inside the pipeline.

    Args:
        quota: The user's limits.
        used: What the user already spent.
        estimated_eur: Predicted cost of the run.

    Returns:
        A :class:`QuotaDecision`.
    """
    windows = [
        ("journalier", quota.daily_eur, used.day_eur),
        ("hebdomadaire", quota.weekly_eur, used.week_eur),
        ("mensuel", quota.monthly_eur, used.month_eur),
    ]
    remaining: list[float] = []
    for label, limit, spent in windows:
        if limit is None:
            continue
        left = limit - spent
        if left <= 0:
            return QuotaDecision(
                False, f"Quota {label} atteint ({_fmt(spent)} / {_fmt(limit)}). Contactez un administrateur."
            )
        if estimated_eur > left:
            return QuotaDecision(
                False,
                f"Coût estimé de ce run ({_fmt(estimated_eur)}) supérieur au reste de votre quota "
                f"{label} ({_fmt(left)}). Réduisez le volume de feedbacks ou le nombre de stories.",
            )
        remaining.append(left)

    if quota.max_eur_per_request is not None:
        if estimated_eur > quota.max_eur_per_request:
            return QuotaDecision(
                False,
                f"Coût estimé de ce run ({_fmt(estimated_eur)}) supérieur à votre limite par requête "
                f"({_fmt(quota.max_eur_per_request)}). Réduisez le volume de feedbacks ou le nombre de stories.",
            )
        remaining.append(quota.max_eur_per_request)

    return QuotaDecision(True, budget_eur=min(remaining) if remaining else None)


# ══════════════════════════════════════════════════════════════════════════
# ML — cost per run
# ══════════════════════════════════════════════════════════════════════════

#: Conservative prior (EUR) used until enough runs exist to fit the model.
#: Calibrated on the reference demo run (≈ 5.5 k characters, 3 stories).
PRIOR_COEFFICIENTS: tuple[float, float, float] = (0.03, 0.012, 0.045)
MIN_TRAINING_RUNS = 8
_Z_P90 = 1.2816


@dataclass(frozen=True)
class CostEstimate:
    """Predicted cost of one run, in euros."""

    point_eur: float
    upper_eur: float
    source: str  # "model" or "prior"


@dataclass(frozen=True)
class ModelReport:
    """Fit quality of :class:`CostEstimator`, for the admin dashboard."""

    n: int
    r2: float | None
    mae_eur: float | None
    coefficients: tuple[float, float, float]
    source: str


class CostEstimator:
    """OLS regression ``cost_eur ~ β0 + β1·(input_chars / 1000) + β2·stories``.

    Deliberately simple: the cost of a run is driven by the tokens read
    (proportional to the input size) and written (proportional to the number
    of stories), so a linear model is both accurate and explainable. The
    upper bound uses the residual standard deviation (≈ P90), which is what
    quota checks use to stay on the safe side.
    """

    def __init__(self) -> None:
        self.coefficients: tuple[float, float, float] = PRIOR_COEFFICIENTS
        self.residual_std: float = 0.0
        self.report = ModelReport(0, None, None, PRIOR_COEFFICIENTS, "prior")

    @staticmethod
    def _design(kchars: np.ndarray, stories: np.ndarray) -> np.ndarray:
        return np.column_stack([np.ones_like(kchars), kchars, stories])

    def fit(self, runs: pd.DataFrame) -> CostEstimator:
        """Fit on successful pipeline runs.

        Args:
            runs: DataFrame with ``input_chars``, ``stories_count``,
                ``cost_eur``, ``status`` and ``kind`` columns.

        Returns:
            ``self``, for chaining.
        """
        needed = {"input_chars", "stories_count", "cost_eur", "status", "kind"}
        if runs is None or runs.empty or not needed.issubset(runs.columns):
            return self
        data = runs[(runs["status"] == "success") & (runs["kind"] == "pipeline")].dropna(subset=list(needed))
        n = len(data)
        if n < MIN_TRAINING_RUNS:
            self.report = ModelReport(n, None, None, PRIOR_COEFFICIENTS, "prior")
            return self

        kchars = data["input_chars"].to_numpy(dtype=float) / 1000
        stories = data["stories_count"].to_numpy(dtype=float)
        y = data["cost_eur"].to_numpy(dtype=float)
        x = self._design(kchars, stories)
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        predicted = x @ beta
        residuals = y - predicted
        ss_res = float(np.sum(residuals**2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        dof = max(n - x.shape[1], 1)

        self.coefficients = (float(beta[0]), float(beta[1]), float(beta[2]))
        self.residual_std = float(np.sqrt(ss_res / dof))
        self.report = ModelReport(
            n=n,
            r2=1 - ss_res / ss_tot if ss_tot > 0 else None,
            mae_eur=float(np.mean(np.abs(residuals))),
            coefficients=self.coefficients,
            source="model",
        )
        return self

    def predict(self, input_chars: int, stories: int) -> CostEstimate:
        """Predict the cost of a run (never below zero)."""
        b0, b1, b2 = self.coefficients
        point = max(b0 + b1 * input_chars / 1000 + b2 * stories, 0.0)
        # Without residuals yet (prior), stay conservative with a +50 % margin.
        upper = point * 1.5 if self.report.source == "prior" else point + _Z_P90 * self.residual_std
        return CostEstimate(point_eur=round(point, 4), upper_eur=round(upper, 4), source=self.report.source)

    def predict_frame(self, runs: pd.DataFrame) -> np.ndarray:
        """Vectorised prediction for a DataFrame of runs."""
        b0, b1, b2 = self.coefficients
        return (
            b0
            + b1 * runs["input_chars"].to_numpy(dtype=float) / 1000
            + b2 * runs["stories_count"].to_numpy(dtype=float)
        )


# ══════════════════════════════════════════════════════════════════════════
# ML — spend forecast
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SpendForecast:
    """Daily spend history and projection."""

    frame: pd.DataFrame  # columns: day, actual, fitted, lower, upper, is_forecast
    month_to_date_eur: float
    month_end_projection_eur: float
    slope_eur_per_day: float


def forecast_spend(daily: pd.DataFrame, today: date, lookback_days: int = 28, horizon_days: int = 30) -> SpendForecast:
    """Fit a linear trend on recent daily spend and project it forward.

    Args:
        daily: DataFrame with ``day`` (date) and ``cost_eur`` columns. Missing
            days count as zero spend.
        today: Reference date ("now" in the app's timezone).
        lookback_days: Training window.
        horizon_days: Forecast horizon.

    Returns:
        A :class:`SpendForecast`, including the projected month-end total.
    """
    start = today - timedelta(days=lookback_days - 1)
    calendar = pd.DataFrame({"day": pd.date_range(start, today, freq="D").date})
    history = daily.copy()
    if not history.empty:
        history["day"] = pd.to_datetime(history["day"]).dt.date
        history = history.groupby("day", as_index=False)["cost_eur"].sum()
    else:
        history = pd.DataFrame({"day": [], "cost_eur": []})
    train = calendar.merge(history, on="day", how="left").fillna({"cost_eur": 0.0})

    t = np.arange(len(train), dtype=float)
    y = train["cost_eur"].to_numpy(dtype=float)
    if len(train) >= 2 and np.any(y):
        slope, intercept = np.polyfit(t, y, 1)
        sigma = float(np.std(y - (intercept + slope * t), ddof=min(2, len(train) - 1)))
    else:
        slope, intercept, sigma = 0.0, float(y.mean()) if len(y) else 0.0, 0.0

    future_t = np.arange(len(train), len(train) + horizon_days, dtype=float)
    future_days = [today + timedelta(days=i) for i in range(1, horizon_days + 1)]
    fitted_hist = np.maximum(intercept + slope * t, 0)
    fitted_future = np.maximum(intercept + slope * future_t, 0)

    frame = pd.concat(
        [
            pd.DataFrame(
                {
                    "day": train["day"],
                    "actual": y,
                    "fitted": fitted_hist,
                    "lower": np.maximum(fitted_hist - _Z_P90 * sigma, 0),
                    "upper": fitted_hist + _Z_P90 * sigma,
                    "is_forecast": False,
                }
            ),
            pd.DataFrame(
                {
                    "day": future_days,
                    "actual": np.nan,
                    "fitted": fitted_future,
                    "lower": np.maximum(fitted_future - _Z_P90 * sigma, 0),
                    "upper": fitted_future + _Z_P90 * sigma,
                    "is_forecast": True,
                }
            ),
        ],
        ignore_index=True,
    )

    month_start = today.replace(day=1)
    mtd = float(train.loc[train["day"] >= month_start, "cost_eur"].sum())
    if not history.empty:  # history may extend before the lookback window
        mtd = float(history.loc[history["day"] >= month_start, "cost_eur"].sum())
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    remaining = frame[(frame["is_forecast"]) & (frame["day"] < next_month)]["fitted"].sum()
    return SpendForecast(
        frame=frame,
        month_to_date_eur=round(mtd, 4),
        month_end_projection_eur=round(mtd + float(remaining), 4),
        slope_eur_per_day=float(slope),
    )
