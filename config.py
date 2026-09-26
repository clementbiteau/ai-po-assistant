"""Centralised runtime configuration for the AI Product Owner Assistant.

All tunables are read from environment variables (optionally loaded from a
local ``.env`` file). On Streamlit Community Cloud, root-level secrets are
exposed as environment variables too, so the same code works locally and
in the cloud without touching ``st.secrets``.

This module deliberately has **no dependency on Streamlit or on the
Anthropic SDK**: it can be imported by tests, scripts, or another frontend.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any, Literal

from dotenv import load_dotenv

load_dotenv()

Effort = Literal["low", "medium", "high", "xhigh", "max"]
AuthMode = Literal["supabase", "local"]
AgentKey = Literal["analyst", "strategist", "writer"]
AGENT_KEYS: tuple[AgentKey, ...] = ("analyst", "strategist", "writer")
EFFORTS: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")

#: Default model. Claude 3.5 Sonnet was retired in Oct. 2025 — Claude Sonnet 5
#: is its direct successor (better reasoning, native structured outputs,
#: adaptive thinking) at a lower price per token.
DEFAULT_MODEL = "claude-sonnet-5"


@dataclass(frozen=True)
class ModelSpec:
    """What the app needs to know about a Claude model it can run.

    Attributes:
        id: API model identifier.
        label: Short display name.
        input_usd: Price per million input tokens (USD).
        output_usd: Price per million output tokens (USD).
        adaptive_thinking: ``True`` for models driven by adaptive thinking and
            an ``effort`` level. ``False`` (Haiku 4.5): no effort parameter,
            thinking is enabled with a token budget derived from the effort.
        pitch: One-line positioning shown to the admin.
    """

    id: str
    label: str
    input_usd: float
    output_usd: float
    adaptive_thinking: bool = True
    pitch: str = ""


#: Models the admin can pick, cheapest first. Prices are the Claude API list
#: prices used for the in-app estimate; the source of truth is
#: https://www.anthropic.com/pricing. Opus and Fable are deliberately left out:
#: judging and structuring customer feedback does not need them, and they would
#: cost 1.5x to 5x the reference run for no measured gain (see HOWHY, D18).
MODELS: dict[str, ModelSpec] = {
    spec.id: spec
    for spec in (
        ModelSpec(
            "claude-haiku-4-5", "Haiku 4.5", 1.00, 5.00, adaptive_thinking=False,
            pitch="Le plus rapide et le moins cher. Pas de niveau d'effort : l'effort devient un budget de réflexion.",
        ),
        ModelSpec(
            "claude-sonnet-5", "Sonnet 5", 2.00, 10.00,
            pitch="Référence : le meilleur équilibre qualité, coût et latence pour juger du texte.",
        ),
    )
}  # fmt: skip

#: USD per million tokens (input, output), by model id.
MODEL_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    m.id: (m.input_usd, m.output_usd) for m in MODELS.values()
}

#: Thinking budget (tokens) standing in for ``effort`` on models without it.
#: ``low`` disables thinking; the ceiling stays well under ``max_tokens``.
THINKING_BUDGETS: dict[Effort, int | None] = {"low": None, "medium": 2048, "high": 4096, "xhigh": 8192, "max": 12000}


@dataclass(frozen=True)
class Preset:
    """A named, defensible model configuration the admin can run and compare."""

    label: str
    rationale: str
    config: dict[str, dict[str, str]]


def _cfg(analyst: tuple[str, Effort], strategist: tuple[str, Effort], writer: tuple[str, Effort]) -> dict:
    pairs = {"analyst": analyst, "strategist": strategist, "writer": writer}
    return {agent: {"model": model, "effort": effort} for agent, (model, effort) in pairs.items()}


SONNET, HAIKU = "claude-sonnet-5", "claude-haiku-4-5"

#: Configurations worth comparing, each with the argument that justifies it.
PRESETS: dict[str, Preset] = {
    "reference": Preset(
        "Référence (Sonnet 5)",
        "Sonnet 5 partout, réflexion élevée pour le stratège dont les scores pilotent la suite. "
        "La configuration mesurée : environ 105 s et 0,16 € par run.",
        _cfg((SONNET, "medium"), (SONNET, "high"), (SONNET, "medium")),
    ),
    "writer_haiku": Preset(
        "Rédaction sur Haiku",
        "La rédaction est la tâche la plus cadrée (schéma strict, une feature à la fois) et la plus bavarde : "
        "la moitié des tokens de sortie. On garde Sonnet là où il faut du jugement.",
        _cfg((SONNET, "medium"), (SONNET, "high"), (HAIKU, "medium")),
    ),
    "all_haiku": Preset(
        "Plancher de coût (Haiku)",
        "Haiku partout : le coût minimal, pour mesurer ce que la qualité y perd, surtout sur la priorisation.",
        _cfg((HAIKU, "medium"), (HAIKU, "high"), (HAIKU, "medium")),
    ),
}

#: Token profile of the reference run ("Notifications & churn", 2026-09-26),
#: per agent (input, output). Used to show what a model choice would cost.
REFERENCE_TOKENS: dict[AgentKey, tuple[int, int]] = {
    "analyst": (4_843, 2_903),
    "strategist": (4_813, 4_623),
    "writer": (8_603, 7_721),
}


#: Default USD → EUR conversion used to report costs in euros. Override with
#: ``USD_TO_EUR`` to match your accounting rate.
DEFAULT_USD_TO_EUR = 0.86


class ConfigurationError(RuntimeError):
    """Raised when the application is missing a mandatory setting."""


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back on bad input."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back on bad input."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_effort(name: str, default: Effort) -> Effort:
    """Read an ``effort`` level, ignoring values the API would reject."""
    raw = (os.getenv(name) or "").strip().lower()
    if raw in ("low", "medium", "high", "xhigh", "max"):
        return raw  # type: ignore[return-value]
    return default


@dataclass(frozen=True)
class AgentEfforts:
    """Reasoning effort per agent.

    Effort trades depth of reasoning for latency and cost. The strategist
    gets the highest level because its scores drive every downstream
    decision; extraction and writing are well served by ``medium``.
    """

    analyst: Effort = "medium"
    strategist: Effort = "high"
    writer: Effort = "medium"


@dataclass(frozen=True)
class AgentModels:
    """Claude model per agent; ``None`` falls back on :attr:`Settings.model`."""

    analyst: str | None = None
    strategist: str | None = None
    writer: str | None = None


@dataclass(frozen=True)
class Settings:
    """Immutable application settings.

    Attributes:
        anthropic_api_key: Secret key for the Anthropic API. ``None`` means
            the app can only run in offline demo mode.
        model: Default Claude model identifier, for agents without their own.
        max_tokens: Output ceiling per request (thinking + answer).
        request_timeout_s: Per-request HTTP timeout, in seconds.
        max_retries: Automatic SDK retries on 408/409/429/5xx and network
            errors (exponential backoff).
        story_workers: Max number of user stories generated in parallel.
        efforts: Reasoning effort per agent.
        models: Claude model per agent (admin choice); ``None`` = ``model``.
        auth_mode: ``supabase`` (default, production) or ``local`` (SQLite
            users and storage, for development and tests only).
        supabase_url: Supabase project URL.
        supabase_key: Supabase *publishable* (anon) key. Safe on the server:
            Row Level Security decides what each signed-in user can read.
        local_db_path: SQLite file used when ``auth_mode == "local"``.
        local_dev_password: Password of the seeded local users.
        usd_to_eur: Conversion rate used for every euro figure.
        timezone: Timezone defining "today", "this week", "this month".
        anthropic_credits_usd: Total credits loaded on the Claude Console
            (USD). Used to display the estimated remaining balance.
    """

    anthropic_api_key: str | None
    model: str = DEFAULT_MODEL
    max_tokens: int = 16_000
    request_timeout_s: float = 180.0
    max_retries: int = 2
    story_workers: int = 4
    efforts: AgentEfforts = field(default_factory=AgentEfforts)
    models: AgentModels = field(default_factory=AgentModels)
    auth_mode: AuthMode = "supabase"
    supabase_url: str | None = None
    supabase_key: str | None = None
    local_db_path: str = ".data/local.db"
    local_dev_password: str | None = None
    usd_to_eur: float = DEFAULT_USD_TO_EUR
    timezone: str = "Europe/Paris"
    anthropic_credits_usd: float | None = None

    @property
    def supabase_configured(self) -> bool:
        """Whether both Supabase URL and key are present."""
        return bool(self.supabase_url and self.supabase_key)

    @property
    def has_api_key(self) -> bool:
        """Whether a (syntactically plausible) API key is available."""
        return bool(self.anthropic_api_key and self.anthropic_api_key.strip())

    @property
    def pricing(self) -> tuple[float, float] | None:
        """``(input, output)`` USD price per million tokens of the default model, if known."""
        return MODEL_PRICING_USD_PER_MTOK.get(self.model)

    @staticmethod
    def price_of(model: str) -> tuple[float, float] | None:
        """``(input, output)`` USD price per million tokens of ``model``, if known."""
        return MODEL_PRICING_USD_PER_MTOK.get(model)

    def model_for(self, agent: AgentKey) -> str:
        """Claude model used by ``agent``."""
        return getattr(self.models, agent) or self.model

    def run_config(self) -> dict[str, dict[str, str]]:
        """Model and effort of each agent, as recorded with every run."""
        return {a: {"model": self.model_for(a), "effort": getattr(self.efforts, a)} for a in AGENT_KEYS}

    def with_agent_config(self, config: Mapping[str, Mapping[str, str]]) -> Settings:
        """Copy with a model and effort per agent (unknown values are ignored)."""
        models = {a: config[a]["model"] for a in AGENT_KEYS if config.get(a, {}).get("model") in MODELS}
        efforts = {a: config[a]["effort"] for a in AGENT_KEYS if config.get(a, {}).get("effort") in EFFORTS}
        return replace(
            self,
            models=replace(self.models, **models),
            efforts=replace(self.efforts, **efforts),  # type: ignore[arg-type]
        )

    def estimated_run_usd(self) -> float | None:
        """Cost of the reference run's token profile with this configuration (``None`` if a price is unknown)."""
        total = 0.0
        for agent, (tokens_in, tokens_out) in REFERENCE_TOKENS.items():
            price = self.price_of(self.model_for(agent))
            if price is None:
                return None
            total += (tokens_in * price[0] + tokens_out * price[1]) / 1e6
        return total

    def with_api_key(self, api_key: str | None) -> Settings:
        """Return a copy using ``api_key`` (e.g. one typed in the UI).

        Blank values keep the current key, so an empty sidebar field never
        erases a key coming from the environment.
        """
        if api_key and api_key.strip():
            return replace(self, anthropic_api_key=api_key.strip())
        return self

    def require_api_key(self) -> str:
        """Return the API key or raise a :class:`ConfigurationError`."""
        if not self.has_api_key:
            raise ConfigurationError(
                "Aucune clé API Anthropic trouvée. Ajoutez ANTHROPIC_API_KEY "
                "dans votre fichier .env, saisissez-la dans la barre latérale, "
                "ou activez le mode démo."
            )
        return self.anthropic_api_key.strip()  # type: ignore[union-attr]


#: Values this module copied from Streamlit secrets into the environment.
_INJECTED: dict[str, str] = {}


def _flatten_secrets(secrets: Mapping[str, Any]) -> dict[str, str]:
    """Root-level scalars as-is, ``[section] key`` as ``SECTION_KEY`` — all upper-cased."""
    flat: dict[str, str] = {}
    for key, value in secrets.items():
        if isinstance(value, Mapping):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, str | int | float | bool):
                    flat[f"{key}_{sub_key}".upper()] = str(sub_value).strip()
        elif isinstance(value, str | int | float | bool):
            flat[str(key).upper()] = str(value).strip()
    return flat


def apply_secrets(secrets: Mapping[str, Any], environ: MutableMapping[str, str] | None = None) -> bool:
    """Copy Streamlit secrets into the environment the app reads from.

    * Accepts root-level keys (``SUPABASE_URL = "..."``), lower-case keys and
      sections (``[supabase]`` + ``url`` / ``key`` → ``SUPABASE_URL`` / ``SUPABASE_KEY``).
    * Variables set outside the app (shell, platform) keep precedence; values
      injected earlier from secrets are refreshed when the secrets change.
    * When anything changes, the cached :func:`get_settings` is invalidated,
      so secrets added *after* deployment are picked up without a reboot.

    Returns:
        Whether the environment changed.
    """
    env = os.environ if environ is None else environ
    changed = False
    for key, value in _flatten_secrets(secrets).items():
        if key in env and _INJECTED.get(key) != env[key]:
            continue  # defined outside the app: it wins
        if env.get(key) != value:
            env[key] = value
            changed = True
        _INJECTED[key] = value
    if changed:
        get_settings.cache_clear()
    return changed


def _supabase_url(raw: str | None) -> str | None:
    """Normalise a pasted project URL (trailing slash, ``/rest/v1`` suffix)."""
    url = (raw or "").strip().strip('"').rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build the settings once from the environment and cache them."""
    auth_mode = (os.getenv("AUTH_MODE") or "supabase").strip().lower()
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        max_tokens=_env_int("ANTHROPIC_MAX_TOKENS", 16_000),
        request_timeout_s=_env_float("ANTHROPIC_TIMEOUT_S", 180.0),
        max_retries=_env_int("ANTHROPIC_MAX_RETRIES", 2),
        story_workers=max(1, _env_int("STORY_WORKERS", 4)),
        efforts=AgentEfforts(
            analyst=_env_effort("EFFORT_ANALYST", "medium"),
            strategist=_env_effort("EFFORT_STRATEGIST", "high"),
            writer=_env_effort("EFFORT_WRITER", "medium"),
        ),
        auth_mode="local" if auth_mode == "local" else "supabase",
        supabase_url=_supabase_url(os.getenv("SUPABASE_URL")),
        supabase_key=(
            os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
        ).strip()
        or None,
        local_db_path=os.getenv("LOCAL_DB_PATH", ".data/local.db"),
        local_dev_password=(os.getenv("LOCAL_DEV_PASSWORD") or "").strip() or None,
        usd_to_eur=_env_float("USD_TO_EUR", DEFAULT_USD_TO_EUR),
        timezone=os.getenv("APP_TIMEZONE", "Europe/Paris"),
        anthropic_credits_usd=_env_float("ANTHROPIC_CREDITS_USD", 0.0) or None,
    )
