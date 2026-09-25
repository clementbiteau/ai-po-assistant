"""Time-aware welcome message that fades in, then fades out."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from ui.style import esc, render_html

_CSS = """
<style>
@keyframes po-greet {
  0%   {opacity: 0; transform: translateY(6px); max-height: 140px;}
  8%   {opacity: 1; transform: none;}
  82%  {opacity: 1; max-height: 140px; margin-bottom: 18px;}
  100% {opacity: 0; max-height: 0; margin-bottom: 0; padding-top: 0; padding-bottom: 0; border-width: 0;}
}
.greet {animation: po-greet 7s ease-in-out forwards; overflow: hidden; margin-bottom: 18px;
  padding: 16px 20px; border-radius: 12px; border: 1px solid rgba(34,142,111,.22); background: rgba(34,142,111,.06);}
.greet .hello {font-family: 'Newsreader', Georgia, serif; font-size: 1.6rem; font-weight: 500; line-height: 1.2;}
.greet .line {font-size: .95rem; opacity: .78; margin-top: 4px;}
@media (prefers-reduced-motion: reduce) {.greet {animation: none;}}
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


def render_greeting(email: str, messages: int, urgent: int, fallback_tz: str) -> None:
    """Show the welcome banner once per session (it animates out by itself)."""
    if st.session_state.get("_greeted"):
        return
    st.session_state["_greeted"] = True
    hello = f"{salutation(_local_now(fallback_tz))} {display_name(email)} !"
    plural = "s" if messages > 1 else ""
    urgent_txt = f", dont <b>{urgent} en urgence</b>" if urgent else ""
    render_html(
        _CSS + f'<div class="greet"><div class="hello">{esc(hello)}</div>'
        f'<div class="line">Ravi de te revoir. Tu as <b>{messages} notification{plural}</b> dans ton inbox'
        f"{urgent_txt}.</div></div>"
    )
