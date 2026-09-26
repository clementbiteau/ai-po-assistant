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
.block-container {max-width: 1120px; padding-top: 7vh;}
.pitch {padding: 8px 28px 0 0;}
.pitch h1 {font-family: 'Newsreader', Georgia, serif; font-weight: 500; font-size: 3rem; line-height: 1.05;
  margin: 14px 0 16px; padding: 0; letter-spacing: -0.015em;}
.pitch h1 em {font-style: italic; color: var(--accent-text);}
.pitch p.lead {font-size: 1.05rem; line-height: 1.6; opacity: .85; max-width: 46ch; margin: 0 0 28px;}
.pitch ol {list-style: none; padding: 0; margin: 0; counter-reset: s;}
.pitch li {counter-increment: s; display: grid; grid-template-columns: 44px 1fr; padding: 12px 0;
  border-top: 1px solid var(--line); font-size: .95rem; line-height: 1.45;}
.pitch li::before {content: "0" counter(s); font-family: 'Geist Mono', ui-monospace, monospace; font-size: .74rem;
  color: var(--accent-text); padding-top: 3px;}
.pitch li b {font-weight: 600;}
.pitch .sub {opacity: .78;}
.form-head {font-family: 'Newsreader', Georgia, serif; font-size: 1.6rem; font-weight: 500; margin: 0 0 2px;}
.form-note {font-size: .86rem; opacity: .75; margin-bottom: 8px;}
.login-foot {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .68rem; letter-spacing: .12em;
  text-transform: uppercase; opacity: .7; text-align: right;}
</style>
"""

_PITCH = """
<div class="pitch">
  <div class="eyebrow">AI Product Owner Assistant</div>
  <h1>Du feedback client au <em>backlog priorisé</em>.</h1>
  <p class="lead">Emails, tickets, verbatims NPS, notes d'appel : trois agents Claude les transforment en
  priorités argumentées et en user stories prêtes pour le sprint.</p>
  <ol>
    <li><div><b>Analyser</b> <span class="sub">— thèmes, signaux et demandes isolées, preuves à l'appui.</span></div></li>
    <li><div><b>Prioriser</b> <span class="sub">— score RICE justifié et arbitrage MoSCoW.</span></div></li>
    <li><div><b>Rédiger</b> <span class="sub">— user stories et critères Gherkin, exportables dans Jira.</span></div></li>
  </ol>
</div>
"""


def render_login(settings: Settings) -> None:
    """Render the sign-in page and handle the form submission.

    On success the page reruns into the application; failures are counted
    per session and trigger a short lockout to slow down brute force (on top
    of Supabase's own rate limiting).
    """
    render_html(_LOGIN_CSS)
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        render_html(_PITCH)
    with right:
        with st.container(border=True):
            render_html('<div class="form-head">Connexion</div><div class="form-note">Accès sur invitation.</div>')
            try:
                session.auth_service(settings)
            except AuthError as exc:
                st.error(exc.user_message)
                st.stop()

            locked_until = st.session_state.get("_locked_until", 0.0)
            remaining = int(locked_until - time.time())
            with st.form("login", border=False):
                email = st.text_input("Email", placeholder="prenom.nom@entreprise.com", autocomplete="username")
                password = st.text_input("Mot de passe", type="password", autocomplete="current-password")
                submitted = st.form_submit_button(
                    "Se connecter", type="primary", width="stretch", disabled=remaining > 0
                )
            if remaining > 0:
                st.warning(f"Trop de tentatives. Réessayez dans {remaining} s.")
            elif submitted:
                _attempt(settings, email, password)
            if settings.auth_mode == "local":
                st.caption("Mode local : `admin@local.dev` ou `demo@local.dev` + `LOCAL_DEV_PASSWORD`.")

        foot_left, foot_right = st.columns([1, 1], vertical_alignment="center")
        with foot_left:
            theme_toggle("login")
        with foot_right:
            render_html('<div class="login-foot">Supabase Auth · PostgreSQL RLS</div>')


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
        st.error(exc.user_message)
        return
    st.session_state["_failures"] = 0
    st.toast(f"Connecté en tant que {profile.email}")
    st.rerun()
