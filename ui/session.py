"""Per-browser-session state: auth service, signed-in profile, quotas, usage logging.

Everything user-specific lives in ``st.session_state`` — never in
``st.cache_resource`` — so one visitor's Supabase session can never leak
into another visitor's (Streamlit serves all sessions from one process).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import streamlit as st

from agents import UsageReport
from auth import AuthError, AuthService, build_auth_service
from config import Settings, apply_secrets
from governance import Consumption, CostEstimator, consumption_from_runs, period_starts
from store import AgentRecord, Profile, Repository, RunRecord, StoreError

_CONSUMPTION_TTL_S = 60


def load_secrets_into_env() -> None:
    """Expose Streamlit secrets to the (environment-driven) configuration.

    Called on every run: secrets edited on Streamlit Community Cloud after
    deployment are applied immediately (see :func:`config.apply_secrets`).
    """
    try:
        secrets = st.secrets.to_dict()
    except Exception:  # noqa: BLE001 — no secrets file is a normal local setup
        return
    apply_secrets(secrets)


def auth_service(settings: Settings) -> AuthService:
    """This session's auth service (created once per browser session).

    Raises:
        AuthError: When authentication is not configured (fail closed).
    """
    service = st.session_state.get("_auth_service")
    if service is None:
        service = build_auth_service(settings)
        st.session_state["_auth_service"] = service
    return service


def current_profile() -> Profile | None:
    """The signed-in user's profile, if any."""
    return st.session_state.get("_profile")


def repository() -> Repository:
    """Repository bound to the signed-in user."""
    return st.session_state["_auth_service"].repository


def sign_in(settings: Settings, email: str, password: str) -> Profile:
    """Authenticate and store the profile in the session."""
    profile = auth_service(settings).sign_in(email, password)
    st.session_state["_profile"] = profile
    st.session_state.pop("_consumption", None)
    return profile


def sign_out() -> None:
    """Revoke the session and wipe every user-specific key."""
    service = st.session_state.get("_auth_service")
    if service is not None:
        service.sign_out()
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def refresh_profile() -> Profile | None:
    """Reload the profile (role / quotas may have been changed by an admin)."""
    profile = current_profile()
    if profile is None:
        return None
    try:
        profile = repository().get_profile(profile.id)
    except StoreError:
        return current_profile()
    st.session_state["_profile"] = profile
    return profile


def consumption(settings: Settings, *, force: bool = False) -> Consumption:
    """Current day / week / month spend of the signed-in user (cached 60 s)."""
    cached = st.session_state.get("_consumption")
    if cached and not force and time.monotonic() - cached[0] < _CONSUMPTION_TTL_S:
        return cached[1]
    profile = current_profile()
    if profile is None:
        return Consumption()
    now = datetime.now(timezone.utc)
    _, week_start, month_start = period_starts(now, settings.timezone)
    rows = repository().user_costs_since(profile.id, min(week_start, month_start))
    value = consumption_from_runs(rows, now, settings.timezone)
    st.session_state["_consumption"] = (time.monotonic(), value)
    return value


@dataclass(frozen=True)
class CreditStatus:
    """Estimated Anthropic credit balance (USD)."""

    loaded_usd: float
    spent_usd: float

    @property
    def remaining_usd(self) -> float:
        """Loaded credits minus what the app spent (never below zero)."""
        return max(self.loaded_usd - self.spent_usd, 0.0)

    @property
    def ratio_left(self) -> float:
        """Share of credits left, between 0 and 1."""
        return self.remaining_usd / self.loaded_usd if self.loaded_usd else 0.0


def credit_status(settings: Settings, *, force: bool = False) -> CreditStatus | None:
    """Remaining-credit estimate, or ``None`` when ``ANTHROPIC_CREDITS_USD`` is unset (cached 60 s)."""
    if not settings.anthropic_credits_usd:
        return None
    cached = st.session_state.get("_credit")
    if cached and not force and time.monotonic() - cached[0] < _CONSUMPTION_TTL_S:
        return cached[1]
    try:
        spent = repository().total_real_cost_usd()
    except StoreError:
        return None
    status = CreditStatus(loaded_usd=settings.anthropic_credits_usd, spent_usd=spent)
    st.session_state["_credit"] = (time.monotonic(), status)
    return status


def cost_estimator() -> CostEstimator:
    """Cost model trained on the runs this user can see (own runs, or all for admins)."""
    try:
        runs, _ = repository().fetch_usage(datetime.now(timezone.utc) - timedelta(days=90))
    except StoreError:
        return CostEstimator()
    return CostEstimator().fit(runs)


def record_usage(
    settings: Settings,
    usage: UsageReport | None,
    *,
    kind: str,
    status: str,
    input_chars: int = 0,
    features_count: int = 0,
    stories_count: int = 0,
    error: str | None = None,
) -> None:
    """Persist one run for quotas and analytics. Never raises (logging must not break the UX)."""
    profile = current_profile()
    if profile is None:
        return
    pricing = settings.pricing or (0.0, 0.0)
    rate = settings.usd_to_eur
    agents: list[AgentRecord] = []
    input_tokens = output_tokens = 0
    for name, u in (usage.per_agent if usage else {}).items():
        cost_usd = (u.input_tokens * pricing[0] + u.output_tokens * pricing[1]) / 1e6
        agents.append(AgentRecord(name, u.calls, u.input_tokens, u.output_tokens, cost_usd * rate, u.seconds))
        input_tokens += u.input_tokens
        output_tokens += u.output_tokens
    cost_usd = (usage.estimated_cost_usd or 0.0) if usage else 0.0
    run = RunRecord(
        user_id=profile.id,
        kind=kind,
        status=status,
        model=settings.model,
        input_chars=input_chars,
        features_count=features_count,
        stories_count=stories_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cost_eur=cost_usd * rate,
        duration_s=usage.wall_clock_s if usage else 0.0,
        error=error,
        agents=tuple(agents),
    )
    try:
        repository().record_run(run)
    except StoreError as exc:
        st.toast(f"Usage non enregistré : {exc.user_message}")
    st.session_state.pop("_consumption", None)
    st.session_state.pop("_credit", None)


__all__ = [
    "AuthError",
    "auth_service",
    "consumption",
    "credit_status",
    "cost_estimator",
    "current_profile",
    "load_secrets_into_env",
    "record_usage",
    "refresh_profile",
    "repository",
    "sign_in",
    "sign_out",
]
