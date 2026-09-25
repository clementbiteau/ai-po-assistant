"""Design tokens, global CSS and tiny HTML helpers shared by every screen.

The CSS is theme-agnostic: surfaces use translucent overlays and inherit the
text colour, so every custom component looks right in both the light and
the dark Streamlit themes without knowing which one is active.
"""

from __future__ import annotations

import html
import re
from typing import Any

import streamlit as st

MOSCOW_COLORS: dict[str, str] = {"Must": "#DC2626", "Should": "#EA580C", "Could": "#2563EB", "Won't": "#9CA3AF"}
MOSCOW_ORDER: list[str] = ["Must", "Should", "Could", "Won't"]
MOSCOW_DOTS: dict[str, str] = {"Must": "🔴", "Should": "🟠", "Could": "🔵", "Won't": "⚪"}
AGENT_COLORS: dict[str, str] = {
    "FeedbackAnalyst": "#6366F1",
    "PrioritizationStrategist": "#0EA5E9",
    "UserStoryWriter": "#F59E0B",
}
#: Neutral text colour for chart annotations, readable on light and dark.
CHART_TEXT = "#8B93A7"
ACCENT = "#6366F1"

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1320px;}
footer {visibility: hidden;}
h1, h2, h3 {letter-spacing: -0.02em;}

.hero {border-radius: 18px; padding: 28px 32px; color: #fff; margin-bottom: 18px;
  background: radial-gradient(1200px 300px at 0% 0%, #6366F1 0%, transparent 60%),
              linear-gradient(135deg, #1E1B4B 0%, #312E81 45%, #4F46E5 100%);
  box-shadow: 0 10px 30px rgba(49,46,129,.25);}
.hero .eyebrow {font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; opacity: .75; font-weight: 600;}
.hero h1 {color: #fff; font-size: 2.1rem; font-weight: 800; margin: 6px 0 4px 0; padding: 0;}
.hero p.sub {opacity: .85; font-size: 1.02rem; margin: 0 0 18px 0;}
.flow {display: flex; align-items: stretch; gap: 10px; flex-wrap: nowrap;}
@media (max-width: 900px) {.flow {flex-wrap: wrap;} .flow .arrow {display: none;}}
.flow .node {flex: 1 1 0; min-width: 150px; position: relative; background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.18); border-radius: 12px; padding: 12px 14px; backdrop-filter: blur(4px);}
.flow .node.done {background: rgba(34,197,94,.16); border-color: rgba(134,239,172,.55);}
.flow .node .t {font-weight: 700; font-size: .86rem; padding-right: 18px;}
.flow .node .ok {position: absolute; top: 10px; right: 12px; color: #86EFAC; font-weight: 800;}
.flow .node .d {font-size: .8rem; opacity: .8; margin-top: 2px;}
.flow .arrow {align-self: center; opacity: .6; font-size: 1.2rem;}
.flow .io {flex: 0 0 auto; align-self: center; font-size: .8rem; padding: 6px 10px; border-radius: 999px;
  background: rgba(255,255,255,.12); border: 1px dashed rgba(255,255,255,.35);}

.card {border: 1px solid rgba(127,127,127,.22); border-radius: 14px; padding: 16px 18px;
  background: rgba(127,127,127,.04); height: 100%;}
.card .h {margin: 0 0 6px 0; font-size: 1rem; font-weight: 700;}
.card .muted, .muted {opacity: .68; font-size: .86rem;}
.chip {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .74rem; font-weight: 600;
  margin: 0 6px 6px 0; border: 1px solid transparent; white-space: nowrap;}
.bar {height: 6px; border-radius: 99px; background: rgba(127,127,127,.15); margin-top: 10px; overflow: hidden;}
.bar > span {display: block; height: 100%; border-radius: 99px;}

.summary {border-left: 4px solid #6366F1; background: rgba(99,102,241,.08); border-radius: 10px;
  padding: 14px 18px; font-size: 1.02rem; line-height: 1.55;}
.quote {border-left: 3px solid rgba(99,102,241,.45); padding: 4px 12px; margin: 6px 0; font-style: italic;
  background: rgba(99,102,241,.05); border-radius: 0 8px 8px 0; font-size: .92rem;}

.statement {border-radius: 14px; padding: 18px 20px; font-size: 1.08rem; line-height: 1.7;
  background: linear-gradient(135deg, rgba(99,102,241,.12) 0%, rgba(139,92,246,.08) 100%);
  border: 1px solid rgba(99,102,241,.25);}
.statement b {color: #6D6AF5; font-weight: 800;}
.kicker {font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; opacity: .6; font-weight: 700;
  margin: 14px 0 6px 0;}

.moscow-col {border-radius: 14px; padding: 12px; background: rgba(127,127,127,.05);
  border: 1px solid rgba(127,127,127,.16); min-height: 150px;}
.moscow-col .head {font-weight: 800; font-size: .95rem; display: flex; justify-content: space-between;
  align-items: center;}
.moscow-col .hint {font-size: .75rem; opacity: .65; margin-bottom: 8px;}
.mini {background: rgba(127,127,127,.06); border: 1px solid rgba(127,127,127,.2); border-radius: 10px;
  padding: 8px 10px; margin-top: 8px; font-size: .86rem;}
.mini .s {opacity: .65; font-size: .76rem; margin-top: 2px;}

.formula {font-family: 'JetBrains Mono', monospace; background: #111827; color: #E5E7EB; border-radius: 10px;
  padding: 10px 14px; font-size: .88rem; display: inline-block;}
.formula em {color: #A5B4FC; font-style: normal;}

.userbox {border: 1px solid rgba(127,127,127,.22); border-radius: 12px; padding: 10px 12px;
  background: rgba(127,127,127,.05); font-size: .86rem;}
.userbox .mail {font-weight: 700; overflow-wrap: anywhere;}
.qrow {display: flex; justify-content: space-between; font-size: .76rem; opacity: .8; margin-top: 8px;}
.admin-hero {border-radius: 16px; padding: 18px 22px; color: #fff; margin-bottom: 12px;
  background: linear-gradient(135deg, #0F172A 0%, #1E293B 55%, #334155 100%);}
.admin-hero h2 {color: #fff; margin: 0; font-size: 1.4rem;}
.admin-hero p {margin: 4px 0 0 0; opacity: .8; font-size: .92rem;}
</style>
"""


def esc(value: Any) -> str:
    """HTML-escape any value (LLM output and user data are untrusted)."""
    return html.escape(str(value))


def chip(label: str, color: str, *, solid: bool = False) -> str:
    """Return a coloured pill as HTML."""
    if solid:
        return f'<span class="chip" style="background:{color};color:#fff">{esc(label)}</span>'
    return f'<span class="chip" style="background:{color}1f;color:{color};border-color:{color}55">{esc(label)}</span>'


def moscow_chip(bucket: str) -> str:
    """MoSCoW pill with its canonical colour."""
    return chip(bucket, MOSCOW_COLORS[bucket], solid=True)


def shorten(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` characters with an ellipsis."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def camel_break(name: str) -> str:
    """Escape a CamelCase name and allow line breaks between its words."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", "<wbr>", esc(name))


def render_html(markup: str) -> None:
    """Render trusted markup (built with :func:`esc` for dynamic parts)."""
    st.markdown(markup, unsafe_allow_html=True)


def euros(value: float | None, *, digits: int = 2) -> str:
    """French-formatted euro amount (``1 234,56 €``); ``∞`` for no limit."""
    if value is None:
        return "∞"
    return f"{value:,.{digits}f} €".replace(",", " ").replace(".", ",")
