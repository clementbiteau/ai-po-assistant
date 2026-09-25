"""Sign-in screen (the only thing an anonymous visitor ever sees)."""

from __future__ import annotations

import time

import streamlit as st

from auth import AuthError
from config import Settings
from ui import session
from ui.style import render_html
from ui.theme import theme_toggle

MAX_ATTEMPTS = 5
LOCKOUT_S = 60

_LOGIN_CSS = """
<style>
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display: none;}
.login-hero {border-radius: 18px; padding: 26px 28px 22px; color: #fff; margin: 4vh 0 14px;
  background: radial-gradient(900px 260px at 0% 0%, #6366F1 0%, transparent 60%),
              linear-gradient(135deg, #1E1B4B 0%, #312E81 45%, #4F46E5 100%);
  box-shadow: 0 10px 30px rgba(49,46,129,.25);}
.login-hero .eyebrow {font-size: .74rem; letter-spacing: .14em; text-transform: uppercase; opacity: .75;
  font-weight: 600;}
.login-hero h1 {color: #fff; font-size: 1.7rem; font-weight: 800; margin: 6px 0 4px; padding: 0;}
.login-hero p {opacity: .85; margin: 0; font-size: .95rem;}
.login-foot {font-size: .78rem; opacity: .6; text-align: center; margin-top: 10px;}
</style>
"""


def render_login(settings: Settings) -> None:
    """Render the sign-in card and handle the form submission.

    On success the page reruns into the application; failures are counted
    per session and trigger a short lockout to slow down brute force (on top
    of Supabase's own rate limiting).
    """
    render_html(_LOGIN_CSS)
    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        render_html(
            '<div class="login-hero"><div class="eyebrow">AI Product Owner Assistant</div>'
            "<h1>🧭 Connexion</h1><p>Accès réservé aux personnes invitées.</p></div>"
        )
        try:
            session.auth_service(settings)
        except AuthError as exc:
            st.error(exc.user_message, icon=":material/lock:")
            st.stop()

        locked_until = st.session_state.get("_locked_until", 0.0)
        remaining = int(locked_until - time.time())
        with st.container(border=True):
            with st.form("login", border=False):
                email = st.text_input("Email", placeholder="prenom.nom@entreprise.com", autocomplete="username")
                password = st.text_input("Mot de passe", type="password", autocomplete="current-password")
                submitted = st.form_submit_button(
                    "Se connecter", type="primary", icon=":material/login:", width="stretch", disabled=remaining > 0
                )
            if remaining > 0:
                st.warning(f"Trop de tentatives. Réessayez dans {remaining} s.", icon=":material/timer:")
            elif submitted:
                _attempt(settings, email, password)

            if settings.auth_mode == "local":
                st.caption("Mode local : `admin@local.dev` ou `demo@local.dev` + `LOCAL_DEV_PASSWORD`.")

        left, right = st.columns([1, 1], vertical_alignment="center")
        with left:
            theme_toggle("login")
        with right:
            render_html('<div class="login-foot">🔒 Supabase Auth · RLS PostgreSQL</div>')


def _attempt(settings: Settings, email: str, password: str) -> None:
    try:
        with st.spinner("Vérification…"):
            profile = session.sign_in(settings, email, password)
    except AuthError as exc:
        failures = st.session_state.get("_failures", 0) + 1
        st.session_state["_failures"] = failures
        if failures >= MAX_ATTEMPTS:
            st.session_state["_locked_until"] = time.time() + LOCKOUT_S
            st.session_state["_failures"] = 0
        st.error(exc.user_message, icon=":material/error:")
        return
    st.session_state["_failures"] = 0
    st.toast(f"Bienvenue {profile.email} 👋")
    st.rerun()
