"""Authentication.

* :class:`SupabaseAuthService` — production: email + password against
  Supabase Auth. Accounts are created by an admin in the Supabase dashboard
  (sign-ups disabled), so only invited people get in.
* :class:`LocalAuthService` — development: users stored in SQLite with
  scrypt-hashed passwords.

The app **fails closed**: without a valid auth configuration, nothing but
an explanatory screen is rendered.

Each browser session owns its own service instance (and therefore its own
Supabase client and JWT). Never share one across sessions.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Protocol

from config import Settings
from store import (
    Profile,
    Repository,
    SQLiteRepository,
    StoreError,
    SupabaseRepository,
)

logger = logging.getLogger(__name__)


class AuthError(RuntimeError):
    """Sign-in or configuration failure; ``user_message`` is safe to display."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class AuthService(Protocol):
    """Sign-in / sign-out plus the repository bound to the signed-in user."""

    mode: str
    repository: Repository

    def sign_in(self, email: str, password: str) -> Profile: ...
    def sign_out(self) -> None: ...


def _validate_input(email: str, password: str) -> tuple[str, str]:
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 254:
        raise AuthError("Adresse email invalide.")
    if not password:
        raise AuthError("Mot de passe requis.")
    return email, password


class SupabaseAuthService:
    """Supabase Auth (email + password) with a per-session client."""

    mode = "supabase"

    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client
        from supabase.lib.client_options import SyncClientOptions

        self.client = create_client(url, key, options=SyncClientOptions(auto_refresh_token=True))
        self.repository: Repository = SupabaseRepository(self.client)

    def sign_in(self, email: str, password: str) -> Profile:
        """Authenticate and load the user's profile (role + quotas).

        Raises:
            AuthError: Wrong credentials, unconfirmed email, rate limit,
                network failure, or missing profile.
        """
        from supabase_auth.errors import AuthApiError, AuthRetryableError
        from supabase_auth.errors import AuthError as SupabaseAuthError

        email, password = _validate_input(email, password)
        try:
            response = self.client.auth.sign_in_with_password({"email": email, "password": password})
        except AuthApiError as exc:
            if exc.status == 429:
                raise AuthError("Trop de tentatives. Patientez quelques minutes.") from exc
            if exc.code == "email_not_confirmed":
                raise AuthError("Email non confirmé. Contactez l'administrateur.") from exc
            raise AuthError("Email ou mot de passe incorrect.") from exc
        except (AuthRetryableError, SupabaseAuthError) as exc:
            raise AuthError("Service d'authentification injoignable. Réessayez dans un instant.") from exc
        except Exception as exc:  # network errors from httpx
            logger.exception("Supabase sign-in failed")
            raise AuthError("Service d'authentification injoignable. Réessayez dans un instant.") from exc

        if response.user is None:
            raise AuthError("Email ou mot de passe incorrect.")
        try:
            return self.repository.get_profile(response.user.id)
        except StoreError as exc:
            self.sign_out()
            raise AuthError(exc.user_message) from exc

    def sign_out(self) -> None:
        """Revoke the session (best effort)."""
        try:
            self.client.auth.sign_out()
        except Exception:  # noqa: BLE001 — signing out must never crash the UI
            logger.warning("Supabase sign-out failed", exc_info=True)


class LocalAuthService:
    """SQLite-backed accounts for local development (``AUTH_MODE=local``).

    Seeds ``admin@local.dev`` (admin) and ``demo@local.dev`` (member, default
    quotas) with ``LOCAL_DEV_PASSWORD``.
    """

    mode = "local"
    ADMIN_EMAIL = "admin@local.dev"
    MEMBER_EMAIL = "demo@local.dev"

    def __init__(self, db_path: str, dev_password: str | None) -> None:
        if not dev_password:
            raise AuthError("Mode local : définissez LOCAL_DEV_PASSWORD dans votre .env.")
        self.repository: SQLiteRepository = SQLiteRepository(db_path)
        self.repository.ensure_user(self.ADMIN_EMAIL, dev_password, role="admin")
        self.repository.ensure_user(self.MEMBER_EMAIL, dev_password, role="member")

    def sign_in(self, email: str, password: str) -> Profile:
        """Check credentials against the local SQLite accounts."""
        email, password = _validate_input(email, password)
        profile = self.repository.authenticate(email, password)
        if profile is None:
            time.sleep(0.5)  # slow down brute force
            raise AuthError("Email ou mot de passe incorrect.")
        return profile

    def sign_out(self) -> None:
        """Nothing to revoke locally."""


def _is_privileged(key: str) -> bool:
    """True for keys that bypass RLS: ``sb_secret_…`` or a legacy JWT with role ``service_role``."""
    if key.startswith("sb_secret_"):
        return True
    try:
        payload = key.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return False
    return claims.get("role") == "service_role"


def build_auth_service(settings: Settings) -> AuthService:
    """Create the auth service for one browser session.

    Raises:
        AuthError: When the configuration is incomplete (fail closed).
    """
    if settings.auth_mode == "local":
        return LocalAuthService(settings.local_db_path, settings.local_dev_password)
    if not settings.supabase_configured:
        missing = [name for name, v in (("SUPABASE_URL", settings.supabase_url), ("SUPABASE_KEY", settings.supabase_key))
                   if not v]  # fmt: skip
        raise AuthError(
            f"Authentification non configurée — secret(s) manquant(s) : {', '.join(missing)}. "
            "Streamlit Cloud : Manage app › ⋮ › Settings › Secrets. En local : fichier .env. "
            "L'application reste verrouillée tant que ce n'est pas fait."
        )
    if not settings.supabase_url.startswith("https://"):  # type: ignore[union-attr]
        raise AuthError("SUPABASE_URL invalide : attendu https://<project-ref>.supabase.co")
    if settings.supabase_key.startswith(("sb_secret_", "eyJ")) and _is_privileged(settings.supabase_key):  # type: ignore[union-attr]
        raise AuthError(
            "SUPABASE_KEY est une clé secrète (service_role) : elle contourne la sécurité RLS. "
            "Utilisez la clé publishable (sb_publishable_…) ou anon, puis révoquez la clé exposée."
        )
    return SupabaseAuthService(settings.supabase_url, settings.supabase_key)  # type: ignore[arg-type]
