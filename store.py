"""Persistence of usage, profiles and quotas.

Two interchangeable implementations of the same :class:`Repository` contract:

* :class:`SupabaseRepository` — production. Every call is made with the
  signed-in user's JWT, so PostgreSQL Row Level Security (see
  ``supabase/migrations``) decides what they can read or write. The app
  never holds a service-role key.
* :class:`SQLiteRepository` — local development and tests (``AUTH_MODE=local``).
  Same behaviour, same tables, zero infrastructure.

No Streamlit import here.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from governance import Quota

RUN_COLUMNS = [
    "id", "user_id", "email", "created_at", "kind", "status", "model", "input_chars", "features_count",
    "stories_count", "input_tokens", "output_tokens", "cost_usd", "cost_eur", "duration_s", "error", "is_synthetic",
]  # fmt: skip
AGENT_COLUMNS = ["run_id", "agent", "calls", "input_tokens", "output_tokens", "cost_eur", "seconds"]
CALL_COLUMNS = [
    "run_id", "seq", "agent", "started_at", "duration_s", "attempt", "status", "stop_reason", "input_tokens",
    "output_tokens", "thinking", "output_excerpt", "error",
]  # fmt: skip
_NUMERIC = [
    "input_chars", "features_count", "stories_count", "input_tokens", "output_tokens", "cost_usd", "cost_eur",
    "duration_s", "calls", "seconds",
]  # fmt: skip


class StoreError(RuntimeError):
    """A persistence operation failed; ``user_message`` is safe to display."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


# ══════════════════════════════════════════════════════════════════════════
# Records
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AgentRecord:
    """Usage of one agent within a run."""

    agent: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_eur: float
    seconds: float


@dataclass(frozen=True)
class CallRecord:
    """One request sent to Claude within a run (admin agent journal)."""

    seq: int
    agent: str
    started_at: datetime
    duration_s: float
    attempt: int
    status: str  # "success" | "retry" | "error"
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    thinking: str = ""
    output_excerpt: str = ""
    error: str | None = None


@dataclass(frozen=True)
class RunRecord:
    """One Claude-backed execution, as persisted."""

    user_id: str
    kind: str  # "pipeline" | "story"
    status: str  # "success" | "error" | "blocked"
    model: str
    input_chars: int = 0
    features_count: int = 0
    stories_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cost_eur: float = 0.0
    duration_s: float = 0.0
    error: str | None = None
    is_synthetic: bool = False
    created_at: datetime | None = None
    agents: tuple[AgentRecord, ...] = ()
    calls: tuple[CallRecord, ...] = ()
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def row(self) -> dict[str, Any]:
        """Column values for the ``runs`` table (JSON-serialisable)."""
        created = (self.created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": created.isoformat(),
            "kind": self.kind,
            "status": self.status,
            "model": self.model,
            "input_chars": int(self.input_chars),
            "features_count": int(self.features_count),
            "stories_count": int(self.stories_count),
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "cost_usd": round(float(self.cost_usd), 6),
            "cost_eur": round(float(self.cost_eur), 6),
            "duration_s": round(float(self.duration_s), 2),
            "error": (self.error or None) and self.error[:500],
            "is_synthetic": bool(self.is_synthetic),
        }

    def call_rows(self) -> list[dict[str, Any]]:
        """Rows for the ``agent_calls`` table."""
        return [
            {
                "run_id": self.id,
                "seq": int(c.seq),
                "agent": c.agent,
                "started_at": c.started_at.astimezone(timezone.utc).isoformat(),
                "duration_s": round(float(c.duration_s), 3),
                "attempt": int(c.attempt),
                "status": c.status,
                "stop_reason": c.stop_reason,
                "input_tokens": int(c.input_tokens),
                "output_tokens": int(c.output_tokens),
                "thinking": (c.thinking or "")[:6000],
                "output_excerpt": (c.output_excerpt or "")[:2000],
                "error": (c.error or None) and c.error[:500],
            }
            for c in self.calls
        ]

    def agent_rows(self) -> list[dict[str, Any]]:
        """Rows for the ``run_agents`` table."""
        return [
            {
                "run_id": self.id,
                "agent": a.agent,
                "calls": int(a.calls),
                "input_tokens": int(a.input_tokens),
                "output_tokens": int(a.output_tokens),
                "cost_eur": round(float(a.cost_eur), 6),
                "seconds": round(float(a.seconds), 2),
            }
            for a in self.agents
        ]


@dataclass(frozen=True)
class Profile:
    """A user as seen by the app: identity, role and quotas."""

    id: str
    email: str
    role: str
    quota: Quota

    @property
    def is_admin(self) -> bool:
        """Whether the user can open the admin console."""
        return self.role == "admin"


def _typed_runs(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=RUN_COLUMNS)
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True, format="ISO8601")
    for column in set(_NUMERIC) & set(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    frame["is_synthetic"] = frame["is_synthetic"].astype(bool)
    frame["email"] = frame["email"].fillna("—")
    return frame


def _typed_calls(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=CALL_COLUMNS)
    frame["started_at"] = pd.to_datetime(frame["started_at"], utc=True, format="ISO8601")
    for column in ("seq", "attempt", "input_tokens", "output_tokens", "duration_s"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame.sort_values(["run_id", "seq"]).reset_index(drop=True)


def _typed_agents(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=AGENT_COLUMNS)
    for column in set(_NUMERIC) & set(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame


def _quota_from(row: dict[str, Any]) -> Quota:
    def num(key: str) -> float | None:
        value = row.get(key)
        return None if value is None else float(value)

    return Quota(
        max_eur_per_request=num("max_eur_per_request"),
        daily_eur=num("daily_eur_limit"),
        weekly_eur=num("weekly_eur_limit"),
        monthly_eur=num("monthly_eur_limit"),
    )


def _quota_row(quota: Quota) -> dict[str, float | None]:
    return {
        "max_eur_per_request": quota.max_eur_per_request,
        "daily_eur_limit": quota.daily_eur,
        "weekly_eur_limit": quota.weekly_eur,
        "monthly_eur_limit": quota.monthly_eur,
    }


# ══════════════════════════════════════════════════════════════════════════
# Contract
# ══════════════════════════════════════════════════════════════════════════


class Repository(Protocol):
    """Everything the app needs to persist and analyse usage."""

    def get_profile(self, user_id: str) -> Profile: ...
    def list_profiles(self) -> list[Profile]: ...
    def update_profile(self, user_id: str, role: str, quota: Quota) -> None: ...
    def record_run(self, run: RunRecord) -> None: ...
    def insert_runs(self, runs: Sequence[RunRecord]) -> int: ...
    def purge_synthetic(self) -> int: ...
    def user_costs_since(self, user_id: str, since: datetime) -> list[tuple[datetime, float]]:
        """Real (non-synthetic) spend of one user — the basis of quota checks."""
        ...

    def fetch_usage(self, since: datetime) -> tuple[pd.DataFrame, pd.DataFrame]: ...
    def fetch_calls(self, run_ids: Sequence[str]) -> pd.DataFrame:
        """Agent journal (one row per Claude request) for the given runs."""
        ...

    def total_real_cost_usd(self) -> float:
        """All-time API spend of real runs (USD) — basis of the remaining-credit estimate."""
        ...


# ══════════════════════════════════════════════════════════════════════════
# Supabase
# ══════════════════════════════════════════════════════════════════════════


class SupabaseRepository:
    """:class:`Repository` backed by Supabase (PostgREST + RLS).

    Args:
        client: A ``supabase.Client`` **already signed in** as the end user.
            It must be private to one browser session — never cached globally.
    """

    PAGE = 1000
    BATCH = 500

    def __init__(self, client: Any) -> None:
        self.client = client

    @contextmanager
    def _errors(self, action: str) -> Iterator[None]:
        try:
            yield
        except StoreError:
            raise
        except Exception as exc:  # postgrest.APIError, httpx errors…
            raise StoreError(f"Base de données indisponible ({action}). Réessayez dans un instant.") from exc

    def get_profile(self, user_id: str) -> Profile:
        """Fetch one profile (RLS: own profile, or any if admin)."""
        with self._errors("lecture du profil"):
            data = self.client.table("profiles").select("*").eq("id", user_id).limit(1).execute().data
        if not data:
            raise StoreError("Profil introuvable. Demandez à un administrateur de vérifier votre compte.")
        row = data[0]
        return Profile(id=row["id"], email=row.get("email") or "", role=row["role"], quota=_quota_from(row))

    def list_profiles(self) -> list[Profile]:
        """All visible profiles (everyone for an admin)."""
        with self._errors("liste des profils"):
            data = self.client.table("profiles").select("*").order("email").execute().data
        return [Profile(r["id"], r.get("email") or "", r["role"], _quota_from(r)) for r in data]

    def update_profile(self, user_id: str, role: str, quota: Quota) -> None:
        """Change a role and quotas (admin only — enforced by RLS)."""
        with self._errors("mise à jour du profil"):
            data = (
                self.client.table("profiles")
                .update({"role": role, **_quota_row(quota)})
                .eq("id", user_id)
                .execute()
                .data
            )
        if not data:
            raise StoreError("Modification refusée : droits administrateur requis.")

    def record_run(self, run: RunRecord) -> None:
        """Persist one run and its per-agent breakdown."""
        self.insert_runs([run])

    def insert_runs(self, runs: Sequence[RunRecord]) -> int:
        """Batch insert (used for real runs and for the synthetic data set)."""
        from postgrest.types import ReturnMethod  # supabase dependency, imported lazily

        run_rows = [r.row() for r in runs]
        children = {
            "run_agents": [a for r in runs for a in r.agent_rows()],
            "agent_calls": [c for r in runs for c in r.call_rows()],
        }
        with self._errors("enregistrement de l'usage"):
            # `minimal`: no read-back, so inserting never depends on SELECT rights.
            for i in range(0, len(run_rows), self.BATCH):
                self.client.table("runs").insert(run_rows[i : i + self.BATCH], returning=ReturnMethod.minimal).execute()
            for table, rows in children.items():
                for i in range(0, len(rows), self.BATCH):
                    self.client.table(table).insert(rows[i : i + self.BATCH], returning=ReturnMethod.minimal).execute()
        return len(run_rows)

    def fetch_calls(self, run_ids: Sequence[str]) -> pd.DataFrame:
        """Agent journal for the given runs (RLS: own runs, or all for admins)."""
        rows: list[dict[str, Any]] = []
        ids = list(run_ids)
        with self._errors("lecture du journal des agents"):
            for i in range(0, len(ids), 80):  # keep the query string short
                chunk = ids[i : i + 80]
                rows.extend(self.client.table("agent_calls").select("*").in_("run_id", chunk).execute().data)
        return _typed_calls(rows)

    def purge_synthetic(self) -> int:
        """Delete synthetic runs (admin only — enforced by RLS)."""
        with self._errors("purge des données de démo"):
            data = self.client.table("runs").delete().eq("is_synthetic", True).execute().data
        return len(data or [])

    def user_costs_since(self, user_id: str, since: datetime) -> list[tuple[datetime, float]]:
        """``(created_at, cost_eur)`` of a user's *real* runs since ``since`` (quota basis)."""
        rows = self._paginate(
            lambda q: (
                q.select("created_at,cost_eur")
                .eq("user_id", user_id)
                .eq("is_synthetic", False)
                .gte("created_at", since.isoformat())
            )
        )
        return [(pd.Timestamp(r["created_at"]).to_pydatetime(), float(r["cost_eur"])) for r in rows]

    def fetch_usage(self, since: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Runs (+ email) and per-agent rows visible to the caller since ``since``."""
        rows = self._paginate(
            lambda q: q.select("*, profiles(email), run_agents(*)").gte("created_at", since.isoformat())
        )
        runs, agents = [], []
        for row in rows:
            agents.extend(row.pop("run_agents", None) or [])
            row["email"] = (row.pop("profiles", None) or {}).get("email")
            runs.append(row)
        return _typed_runs(runs), _typed_agents(agents)

    def total_real_cost_usd(self) -> float:
        """All-time spend of real runs visible to the caller (all runs for an admin)."""
        rows = self._paginate(lambda q: q.select("cost_usd").eq("is_synthetic", False))
        return float(sum(float(r["cost_usd"] or 0) for r in rows))

    def _paginate(self, build: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        start = 0
        with self._errors("lecture de l'usage"):
            while True:
                page = (
                    build(self.client.table("runs"))
                    .order("created_at", desc=False)
                    .range(start, start + self.PAGE - 1)
                    .execute()
                    .data
                )
                out.extend(page)
                if len(page) < self.PAGE:
                    return out
                start += self.PAGE


# ══════════════════════════════════════════════════════════════════════════
# SQLite (local development & tests)
# ══════════════════════════════════════════════════════════════════════════

_SQLITE_SCHEMA = """
create table if not exists profiles (
    id text primary key, email text unique not null, role text not null default 'member',
    password_hash text, max_eur_per_request real, daily_eur_limit real, weekly_eur_limit real,
    monthly_eur_limit real, created_at text not null
);
create table if not exists runs (
    id text primary key, user_id text not null references profiles(id), created_at text not null,
    kind text not null, status text not null, model text not null, input_chars integer, features_count integer,
    stories_count integer, input_tokens integer, output_tokens integer, cost_usd real, cost_eur real,
    duration_s real, error text, is_synthetic integer not null default 0
);
create index if not exists runs_user_created on runs(user_id, created_at);
create table if not exists run_agents (
    run_id text not null references runs(id) on delete cascade, agent text not null, calls integer,
    input_tokens integer, output_tokens integer, cost_eur real, seconds real, primary key (run_id, agent)
);
create table if not exists agent_calls (
    run_id text not null references runs(id) on delete cascade, seq integer not null, agent text not null,
    started_at text not null, duration_s real, attempt integer, status text, stop_reason text,
    input_tokens integer, output_tokens integer, thinking text, output_excerpt text, error text,
    primary key (run_id, seq)
);
"""

#: Same defaults as the Supabase migration.
DEFAULT_MEMBER_QUOTA = Quota(max_eur_per_request=0.50, daily_eur=2.00, weekly_eur=5.00, monthly_eur=10.00)


def hash_password(password: str, salt: bytes | None = None) -> str:
    """scrypt hash, ``salt$hash`` hex-encoded (local mode only)."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check of a password against :func:`hash_password` output."""
    if not stored or "$" not in stored:
        return False
    salt_hex, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), stored)


class SQLiteRepository:
    """:class:`Repository` on a local SQLite file, plus local user accounts.

    Access rules mirror the Supabase RLS policies at the application level,
    which is acceptable because this backend is for single-machine dev only.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) if str(path) == ":memory:" else None
        with self._conn() as con:
            con.executescript(_SQLITE_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = self._memory or sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("pragma foreign_keys = on")
        try:
            yield con
            con.commit()
        except sqlite3.Error as exc:
            con.rollback()
            raise StoreError("Base locale indisponible.") from exc
        finally:
            if self._memory is None:
                con.close()

    # ── local accounts ───────────────────────────────────────────────────
    def ensure_user(self, email: str, password: str, role: str = "member", quota: Quota | None = None) -> str:
        """Create a local user if missing; return its id."""
        with self._conn() as con:
            row = con.execute("select id from profiles where email = ?", (email.lower(),)).fetchone()
            if row:
                return row["id"]
            user_id = str(uuid.uuid4())
            q = quota if quota is not None else (Quota() if role == "admin" else DEFAULT_MEMBER_QUOTA)
            con.execute(
                "insert into profiles values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, email.lower(), role, hash_password(password), *_quota_row(q).values(),
                 datetime.now(timezone.utc).isoformat()),
            )  # fmt: skip
            return user_id

    def authenticate(self, email: str, password: str) -> Profile | None:
        """Return the profile when the credentials are valid."""
        with self._conn() as con:
            row = con.execute("select * from profiles where email = ?", (email.strip().lower(),)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return Profile(row["id"], row["email"], row["role"], _quota_from(dict(row)))

    # ── Repository ───────────────────────────────────────────────────────
    def get_profile(self, user_id: str) -> Profile:
        """Fetch one profile."""
        with self._conn() as con:
            row = con.execute("select * from profiles where id = ?", (user_id,)).fetchone()
        if row is None:
            raise StoreError("Profil introuvable.")
        return Profile(row["id"], row["email"], row["role"], _quota_from(dict(row)))

    def list_profiles(self) -> list[Profile]:
        """All profiles."""
        with self._conn() as con:
            rows = con.execute("select * from profiles order by email").fetchall()
        return [Profile(r["id"], r["email"], r["role"], _quota_from(dict(r))) for r in rows]

    def update_profile(self, user_id: str, role: str, quota: Quota) -> None:
        """Change a role and quotas."""
        values = _quota_row(quota)
        with self._conn() as con:
            con.execute(
                "update profiles set role = ?, max_eur_per_request = ?, daily_eur_limit = ?, "
                "weekly_eur_limit = ?, monthly_eur_limit = ? where id = ?",
                (role, *values.values(), user_id),
            )

    def record_run(self, run: RunRecord) -> None:
        """Persist one run."""
        self.insert_runs([run])

    def insert_runs(self, runs: Sequence[RunRecord]) -> int:
        """Batch insert runs and their agent rows."""
        with self._conn() as con:
            for run in runs:
                row = run.row()
                row["is_synthetic"] = int(row["is_synthetic"])
                con.execute(
                    f"insert into runs ({', '.join(row)}) values ({', '.join('?' * len(row))})", tuple(row.values())
                )
                for table, rows in (("run_agents", run.agent_rows()), ("agent_calls", run.call_rows())):
                    for child in rows:
                        con.execute(
                            f"insert into {table} ({', '.join(child)}) values ({', '.join('?' * len(child))})",
                            tuple(child.values()),
                        )
        return len(runs)

    def fetch_calls(self, run_ids: Sequence[str]) -> pd.DataFrame:
        """Agent journal for the given runs."""
        ids = list(run_ids)
        if not ids:
            return _typed_calls([])
        rows: list[dict[str, Any]] = []
        with self._conn() as con:
            for i in range(0, len(ids), 500):  # SQLite caps bound parameters
                chunk = ids[i : i + 500]
                query = f"select * from agent_calls where run_id in ({', '.join('?' * len(chunk))})"
                rows.extend(dict(r) for r in con.execute(query, tuple(chunk)).fetchall())
        return _typed_calls(rows)

    def purge_synthetic(self) -> int:
        """Delete synthetic runs."""
        with self._conn() as con:
            return con.execute("delete from runs where is_synthetic = 1").rowcount

    def user_costs_since(self, user_id: str, since: datetime) -> list[tuple[datetime, float]]:
        """``(created_at, cost_eur)`` of a user's *real* runs since ``since`` (quota basis)."""
        with self._conn() as con:
            rows = con.execute(
                "select created_at, cost_eur from runs where user_id = ? and created_at >= ? and is_synthetic = 0",
                (user_id, since.astimezone(timezone.utc).isoformat()),
            ).fetchall()
        return [(datetime.fromisoformat(r["created_at"]), float(r["cost_eur"] or 0)) for r in rows]

    def total_real_cost_usd(self) -> float:
        """All-time spend of real runs (USD)."""
        with self._conn() as con:
            value = con.execute("select coalesce(sum(cost_usd), 0) from runs where is_synthetic = 0").fetchone()[0]
        return float(value)

    def fetch_usage(self, since: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
        """All runs (+ email) and agent rows since ``since``."""
        cutoff = since.astimezone(timezone.utc).isoformat()
        with self._conn() as con:
            runs = [
                dict(r)
                for r in con.execute(
                    "select r.*, p.email from runs r join profiles p on p.id = r.user_id where r.created_at >= ?",
                    (cutoff,),
                ).fetchall()
            ]
            agents = [
                dict(r)
                for r in con.execute(
                    "select a.* from run_agents a join runs r on r.id = a.run_id where r.created_at >= ?", (cutoff,)
                ).fetchall()
            ]
        return _typed_runs(runs), _typed_agents(agents)
