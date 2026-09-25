"""Design tokens, global CSS and tiny HTML helpers shared by every screen.

Visual direction: editorial and restrained — warm paper surfaces, ink text,
a single deep-green accent, a serif for headlines (Newsreader), a neutral
sans for the interface (Geist) and a mono for figures and labels (Geist Mono).

The CSS is theme-agnostic: surfaces use translucent overlays and inherit the
text colour, so every custom component reads correctly in both the light and
the dark Streamlit themes without knowing which one is active.

Chart colours were validated with a colour-vision-deficiency checker (OKLab
ΔE, lightness band, chroma floor, contrast) against both the light
(#FBFAF7) and dark (#151513) surfaces, so a single set works in both themes.
"""

from __future__ import annotations

import html
import re
from typing import Any

import streamlit as st

# Categorical (identity) — fixed order, validated all-pairs in both themes.
SERIES: tuple[str, str, str] = ("#228E6F", "#4271C8", "#B87612")
AGENT_COLORS: dict[str, str] = {
    "FeedbackAnalyst": SERIES[0],
    "PrioritizationStrategist": SERIES[1],
    "UserStoryWriter": SERIES[2],
}
# MoSCoW is ordinal: one hue, darkest = most important; "Won't" is neutral.
MOSCOW_COLORS: dict[str, str] = {"Must": "#17664F", "Should": "#2F9477", "Could": "#6FAF98", "Won't": "#A29E94"}
MOSCOW_ORDER: list[str] = ["Must", "Should", "Could", "Won't"]
# Status (reserved: never reused as a series colour).
STATUS = {"good": "#2F9477", "warning": "#B87612", "critical": "#B3452C", "neutral": "#8A867D"}
ACCENT = "#228E6F"
#: Neutral ink for chart annotations, readable on light and dark surfaces.
CHART_TEXT = "#8A867D"
CONSOLE_BILLING_URL = "https://platform.claude.com/settings/billing"

CSS = """
<style>
.block-container {padding-top: 2rem; padding-bottom: 4rem; max-width: 1240px;}
footer {visibility: hidden;}
h1, h2, h3, h4 {letter-spacing: -0.01em;}
[data-testid="stMetricValue"] {font-family: 'Geist Mono', ui-monospace, monospace; font-weight: 500;
  letter-spacing: -0.02em;}
[data-testid="stMetricLabel"] p {font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; opacity: .7;}

/* ── Hero ─────────────────────────────────────────────────────────────── */
.hero {position: relative; overflow: hidden; border-radius: 14px; padding: 34px 38px 30px; margin-bottom: 20px;
  color: #F2EEE4; background-color: #14352C;
  background-image: radial-gradient(rgba(242,238,228,.075) 1px, transparent 1.2px);
  background-size: 16px 16px;}
.hero::after {content: ""; position: absolute; inset: auto -120px -160px auto; width: 420px; height: 420px;
  border-radius: 50%; border: 1px solid rgba(242,238,228,.12);}
.eyebrow {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .7rem; letter-spacing: .2em;
  text-transform: uppercase; opacity: .72;}
.hero .eyebrow {color: #A9D3C3; opacity: 1;}
.hero h1 {font-family: 'Newsreader', Georgia, serif; font-weight: 500; font-size: 2.6rem; line-height: 1.08;
  color: #F2EEE4; margin: 10px 0 10px; padding: 0; max-width: 20ch;}
.hero h1 em {font-style: italic; color: #A9D3C3;}
.hero p.sub {color: rgba(242,238,228,.74); font-size: 1rem; line-height: 1.55; max-width: 62ch; margin: 0 0 26px;}
.steps {display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; position: relative; z-index: 1;}
@media (max-width: 860px) {.steps {grid-template-columns: 1fr;} .hero h1 {font-size: 2rem;}}
.step {border-top: 1px solid rgba(242,238,228,.22); padding-top: 12px;}
.step .n {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .72rem; color: #A9D3C3; letter-spacing: .06em;}
.step .t {font-weight: 600; margin-top: 4px;}
.step .d {font-size: .84rem; opacity: .68; margin-top: 2px; line-height: 1.45;}
.step.done {border-top-color: #A9D3C3;}
.step.done .n::after {content: "  ·  terminé";}

/* ── Surfaces ─────────────────────────────────────────────────────────── */
.card {border: 1px solid rgba(127,127,127,.2); border-radius: 12px; padding: 18px 20px;
  background: rgba(127,127,127,.035); height: 100%;}
.card .h {font-family: 'Newsreader', Georgia, serif; font-size: 1.18rem; font-weight: 500; margin: 0 0 8px;}
.muted {opacity: .66; font-size: .88rem; line-height: 1.5;}
.chip {display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: .72rem; font-weight: 500;
  margin: 0 6px 6px 0; border: 1px solid transparent; white-space: nowrap; letter-spacing: .01em;}
.bar {height: 4px; border-radius: 99px; background: rgba(127,127,127,.16); margin-top: 12px; overflow: hidden;}
.bar > span {display: block; height: 100%; border-radius: 99px;}

.summary {border-left: 2px solid #228E6F; padding: 4px 0 4px 18px; font-family: 'Newsreader', Georgia, serif;
  font-size: 1.22rem; line-height: 1.5;}
.quote {border-left: 1px solid rgba(127,127,127,.45); padding: 2px 0 2px 14px; margin: 8px 0;
  font-family: 'Newsreader', Georgia, serif; font-style: italic; font-size: 1.02rem; opacity: .9;}
.kicker {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .68rem; letter-spacing: .16em;
  text-transform: uppercase; opacity: .55; margin: 18px 0 6px;}

.statement {border-radius: 12px; padding: 20px 22px; line-height: 1.75; font-size: 1.05rem;
  background: rgba(34,142,111,.06); border: 1px solid rgba(34,142,111,.22);}
.statement .k {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .7rem; letter-spacing: .14em;
  text-transform: uppercase; color: #2F9477; margin-right: 8px;}

.moscow-col {border-radius: 12px; padding: 14px; background: rgba(127,127,127,.04);
  border: 1px solid rgba(127,127,127,.16); min-height: 150px;}
.moscow-col .head {font-family: 'Newsreader', Georgia, serif; font-size: 1.15rem; display: flex;
  justify-content: space-between; align-items: baseline;}
.moscow-col .count {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .8rem; opacity: .6;}
.moscow-col .hint {font-size: .76rem; opacity: .6; margin: 2px 0 8px;}
.mini {border: 1px solid rgba(127,127,127,.18); border-radius: 8px; padding: 8px 10px; margin-top: 8px;
  font-size: .86rem; background: rgba(127,127,127,.03);}
.mini .s {opacity: .6; font-size: .74rem; margin-top: 3px; font-family: 'Geist Mono', ui-monospace, monospace;}

.formula {font-family: 'Geist Mono', ui-monospace, monospace; border: 1px solid rgba(127,127,127,.25);
  background: rgba(127,127,127,.05); border-radius: 8px; padding: 9px 14px; font-size: .84rem; display: inline-block;}
.formula em {color: #2F9477; font-style: normal; font-weight: 500;}

/* ── Guidance ─────────────────────────────────────────────────────────── */
.intro {display: flex; gap: 14px; align-items: baseline; padding: 12px 16px; margin-bottom: 18px;
  border-radius: 10px; background: rgba(34,142,111,.06); border: 1px solid rgba(34,142,111,.18);}
.intro .n {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .7rem; letter-spacing: .14em;
  text-transform: uppercase; color: #2F9477; white-space: nowrap;}
.intro .t {font-size: .92rem; line-height: 1.5;}

/* ── Sidebar account ──────────────────────────────────────────────────── */
.brand {font-family: 'Newsreader', Georgia, serif; font-size: 1.35rem; font-weight: 500; margin: 0;}
.userbox {border: 1px solid rgba(127,127,127,.2); border-radius: 10px; padding: 12px 14px;
  background: rgba(127,127,127,.04); font-size: .84rem;}
.userbox .mail {font-weight: 600; overflow-wrap: anywhere; margin-bottom: 4px;}
.qrow {display: flex; justify-content: space-between; font-size: .74rem; opacity: .78; margin-top: 9px;
  font-family: 'Geist Mono', ui-monospace, monospace;}

/* ── Admin ────────────────────────────────────────────────────────────── */
.admin-hero {border-radius: 14px; padding: 22px 26px; margin-bottom: 14px; color: #EDE9DF;
  background-color: #23221F; background-image: radial-gradient(rgba(237,233,223,.06) 1px, transparent 1.2px);
  background-size: 16px 16px;}
.admin-hero h2 {font-family: 'Newsreader', Georgia, serif; font-weight: 500; color: #EDE9DF; margin: 6px 0 2px;
  padding: 0; font-size: 1.7rem;}
.admin-hero p {margin: 0; opacity: .7; font-size: .92rem;}
.credit {border: 1px solid rgba(127,127,127,.2); border-radius: 12px; padding: 18px 22px; margin-bottom: 14px;
  background: rgba(127,127,127,.035);}
.credit .big {font-family: 'Geist Mono', ui-monospace, monospace; font-size: 2rem; font-weight: 500;
  letter-spacing: -0.02em;}
.credit .row {display: flex; gap: 28px; flex-wrap: wrap; align-items: flex-end;}
.credit .lbl {font-size: .74rem; text-transform: uppercase; letter-spacing: .08em; opacity: .62;}
.credit .val {font-family: 'Geist Mono', ui-monospace, monospace; font-size: 1.05rem;}
.credit a {color: #2F9477;}
</style>
"""


def esc(value: Any) -> str:
    """HTML-escape any value (LLM output and user data are untrusted)."""
    return html.escape(str(value))


def chip(label: str, color: str, *, solid: bool = False) -> str:
    """Return a small tag as HTML."""
    if solid:
        return f'<span class="chip" style="background:{color};color:#fff">{esc(label)}</span>'
    return f'<span class="chip" style="background:{color}17;color:{color};border-color:{color}45">{esc(label)}</span>'


def moscow_chip(bucket: str) -> str:
    """MoSCoW tag with its ordinal colour."""
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


def intro(step: str, text: str) -> None:
    """One-line guidance banner at the top of a tab (demo walkthrough)."""
    render_html(f'<div class="intro"><span class="n">{esc(step)}</span><span class="t">{text}</span></div>')


def euros(value: float | None, *, digits: int = 2) -> str:
    """French-formatted euro amount (``1 234,56 €``); ``illimité`` for no limit."""
    if value is None:
        return "illimité"
    return f"{value:,.{digits}f} €".replace(",", " ").replace(".", ",")


def dollars(value: float, *, digits: int = 2) -> str:
    """US dollar amount, as displayed in the Claude Console."""
    return f"{value:,.{digits}f} $".replace(",", " ").replace(".", ",")
