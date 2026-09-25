"""Time-aware welcome banner, dismissible with a close button."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from ui.style import esc, render_html

_KEY = "greet_box"
_CSS = """
<style>
@keyframes po-greet-in {from {opacity: 0; transform: translateY(6px);} to {opacity: 1; transform: none;}}
.st-key-greet_box {animation: po-greet-in .6s ease-out both; border-radius: 14px; padding: 18px 16px 18px 24px;
  margin-bottom: 18px; color: #FFFCF9; background-color: #1B0442;
  background-image: radial-gradient(rgba(255,252,249,.07) 1px, transparent 1.2px); background-size: 16px 16px;}
.st-key-greet_box .hello {font-family: 'Kanit', sans-serif; font-size: 1.55rem; font-weight: 500; line-height: 1.2;
  color: #FFFCF9;}
.st-key-greet_box .line {font-size: .96rem; color: rgba(255,252,249,.86); margin-top: 4px;}
.st-key-greet_box .line b {color: #FF9BBB; font-weight: 600;}
.st-key-greet_box button {color: rgba(255,252,249,.8) !important; min-height: 2rem;}
.st-key-greet_box button:hover {color: #FFFCF9 !important; background: rgba(255,252,249,.1) !important;}
@media (prefers-reduced-motion: reduce) {.st-key-greet_box {animation: none;}}
</style>
"""


def display_name(email: str) -> str:
    """``clement.biteau@x.com`` → ``Clement``."""
    local = (email or "").split("@")[0]
    first = re.split(r"[._\-+0-9]", local)[0]
    return first.capitalize() or "toi"


def salutation(now: datetime) -> str:
    """Bonjour (morning), Bon après-midi (afternoon), Bonsoir (evening and night)."""
    if 5 <= now.hour < 12:
        return "Bonjour"
    if 12 <= now.hour < 18:
        return "Bon après-midi"
    return "Bonsoir"


def _local_now(fallback_tz: str) -> datetime:
    for tz in (getattr(st.context, "timezone", None), fallback_tz):
        if tz:
            try:
                return datetime.now(ZoneInfo(tz))
            except ZoneInfoNotFoundError:
                continue
    return datetime.now()


def _dismiss() -> None:
    st.session_state["_greet_dismissed"] = True


def render_greeting(email: str, messages: int, urgent: int, fallback_tz: str) -> None:
    """Welcome banner with live inbox counts; stays until the user closes it (per session)."""
    if st.session_state.get("_greet_dismissed"):
        return
    hello = f"{salutation(_local_now(fallback_tz))} {display_name(email)} !"
    plural = "s" if messages > 1 else ""
    urgent_txt = f", dont <b>{urgent} en urgence</b>" if urgent else ""
    render_html(_CSS)
    with st.container(key=_KEY):
        text_col, close_col = st.columns([24, 1], vertical_alignment="top")
        with text_col:
            render_html(
                f'<div class="hello">{esc(hello)}</div>'
                f'<div class="line">Ravi de te revoir. Tu as <b>{messages} notification{plural}</b> dans ton inbox'
                f"{urgent_txt}.</div>"
            )
        with close_col:
            st.button("", icon=":material/close:", type="tertiary", key="greet_close", help="Fermer",
                      on_click=_dismiss)  # fmt: skip
