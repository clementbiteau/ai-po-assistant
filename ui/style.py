"""Design tokens, global CSS and tiny HTML helpers shared by every screen.

Visual direction: editorial and restrained — warm beige paper, ink text, a
single deep-green accent, a serif for headlines (Newsreader), a neutral sans
for the interface (Geist) and a mono for figures and labels (Geist Mono).

Contrast: the light theme uses a beige background (not near-white) with
near-black text and lighter paper cards, so surfaces separate without glare.
Theme-dependent accents are CSS variables switched by ``ui/theme.py``, which
flags the page with ``data-po-theme="light|dark"``.

Chart colours were validated with a colour-vision-deficiency checker (OKLab
ΔE, lightness band, chroma floor, contrast) against both the light (#F4F1EA)
and dark (#151513) surfaces, so a single set works in both themes.
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

BRAND = "#14352C"  # deep green
ACCENT = "#1F6E57"  # green accent
# Categorical (identity) — fixed order: green, blue, ochre.
SERIES: tuple[str, str, str] = ("#228E6F", "#4271C8", "#B87612")
AGENT_COLORS: dict[str, str] = {
    "FeedbackAnalyst": SERIES[0],
    "PrioritizationStrategist": SERIES[1],
    "UserStoryWriter": SERIES[2],
}
# MoSCoW is ordinal: one green hue, darkest = most important; "Won't" is neutral.
MOSCOW_COLORS: dict[str, str] = {"Must": "#17664F", "Should": "#2F9477", "Could": "#6FAF98", "Won't": "#A29E94"}
MOSCOW_ORDER: list[str] = ["Must", "Should", "Could", "Won't"]
# Status (reserved: never reused as a series colour).
STATUS = {"good": "#2F9477", "warning": "#B87612", "critical": "#B3452C", "neutral": "#8A867D"}
#: Neutral ink for chart annotations, readable on light and dark surfaces.
CHART_TEXT = "#8A867D"
CONSOLE_BILLING_URL = "https://platform.claude.com/settings/billing"

CSS = """
<style>
:root {
  --accent: #1F6E57; --accent-text: #17664F; --accent-soft: rgba(31,110,87,.07); --accent-line: rgba(31,110,87,.26);
  --brand: #14352C; --surface: #FCFBF8; --surface-2: rgba(28,27,25,.035); --line: rgba(28,27,25,.14);
  --muted: .76;
}
html[data-po-theme="dark"] {
  --accent: #4FA98B; --accent-text: #6FBFA3; --accent-soft: rgba(111,191,163,.09);
  --accent-line: rgba(111,191,163,.28);
  --surface: rgba(255,255,255,.04); --surface-2: rgba(255,255,255,.03); --line: rgba(255,255,255,.12);
  --muted: .78;
}
.block-container {padding-top: 2rem; padding-bottom: 4rem; max-width: 1240px;}
footer {visibility: hidden;}
h1, h2, h3, h4 {letter-spacing: -0.005em;}
[data-testid="stMetricValue"] {font-family: 'Geist Mono', ui-monospace, monospace; font-weight: 500;
  letter-spacing: -0.02em;}
[data-testid="stMetricLabel"] p {font-size: .76rem; text-transform: uppercase; letter-spacing: .08em; opacity: .8;}
[data-testid="stMetric"] {background: var(--surface);}

/* ── Surfaces ─────────────────────────────────────────────────────────── */
.card {border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; background: var(--surface); height: 100%;}
.card .h {font-family: 'Newsreader', Georgia, serif; font-size: 1.12rem; font-weight: 500; margin: 0 0 8px;}
.muted {opacity: var(--muted); font-size: .88rem; line-height: 1.5;}
.chip {display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: .72rem; font-weight: 600;
  margin: 0 6px 6px 0; border: 1px solid transparent; white-space: nowrap; letter-spacing: .01em;}
.bar {height: 4px; border-radius: 99px; background: var(--line); margin-top: 12px; overflow: hidden;}
.bar > span {display: block; height: 100%; border-radius: 99px;}
.eyebrow {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .68rem; letter-spacing: .18em;
  text-transform: uppercase; opacity: .8;}

.summary {border-left: 2px solid var(--accent); padding: 4px 0 4px 18px; font-family: 'Newsreader', Georgia, serif;
  font-size: 1.22rem; line-height: 1.5;}
.quote {border-left: 1px solid var(--line); padding: 2px 0 2px 14px; margin: 8px 0;
  font-family: 'Newsreader', Georgia, serif; font-style: italic; font-size: 1.02rem;}
.kicker {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .68rem; letter-spacing: .14em;
  text-transform: uppercase; opacity: .72; margin: 18px 0 6px;}

.statement {border-radius: 12px; padding: 20px 22px; line-height: 1.75; font-size: 1.05rem;
  background: var(--accent-soft); border: 1px solid var(--accent-line);}
.statement .k {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .7rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--accent-text); font-weight: 500; margin-right: 8px;}

.moscow-col {border-radius: 12px; padding: 14px; background: var(--surface-2); border: 1px solid var(--line);
  min-height: 150px;}
.moscow-col .head {font-family: 'Newsreader', Georgia, serif; font-size: 1.1rem; display: flex;
  justify-content: space-between; align-items: baseline;}
.moscow-col .count {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .8rem; opacity: .75;}
.moscow-col .hint {font-size: .76rem; opacity: var(--muted); margin: 2px 0 8px;}
.mini {border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin-top: 8px; font-size: .86rem;
  background: var(--surface);}
.mini .s {opacity: .75; font-size: .74rem; margin-top: 3px; font-family: 'Geist Mono', ui-monospace, monospace;}

.formula {font-family: 'Geist Mono', ui-monospace, monospace; border: 1px solid var(--line);
  background: var(--surface); border-radius: 8px; padding: 9px 14px; font-size: .84rem; display: inline-block;}
.formula em {color: var(--accent-text); font-style: normal; font-weight: 600;}

/* ── Guidance ─────────────────────────────────────────────────────────── */
.intro {display: flex; gap: 14px; align-items: baseline; padding: 12px 16px; margin-bottom: 18px;
  border-radius: 10px; background: var(--accent-soft); border: 1px solid var(--accent-line);}
.intro .n {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .7rem; letter-spacing: .14em;
  text-transform: uppercase; color: var(--accent-text); font-weight: 500; white-space: nowrap;}
.intro .t {font-size: .92rem; line-height: 1.5;}

/* Process steps (admin agent journal) */
.steps {display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px;}
@media (max-width: 860px) {.steps {grid-template-columns: 1fr;}}
.step {border-top: 2px solid var(--line); padding-top: 10px;}
.step .n {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .72rem; opacity: .75;}
.step .t {font-weight: 600; margin-top: 4px;}
.step .d {font-size: .84rem; opacity: var(--muted); margin-top: 2px;}

/* Live progress panel (agent reasoning and findings while it runs) */
.live {border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin: 2px 0 12px;
  background: var(--surface-2);}
.live .lh {display: flex; align-items: center; gap: 8px; font-family: 'Geist Mono', ui-monospace, monospace;
  font-size: .68rem; letter-spacing: .14em; text-transform: uppercase; color: var(--accent-text); font-weight: 500;}
.live .dot {width: 7px; height: 7px; border-radius: 50%; background: var(--accent);
  animation: live-pulse 1.4s ease-in-out infinite;}
@keyframes live-pulse {0%, 100% {opacity: .25;} 50% {opacity: 1;}}
@media (prefers-reduced-motion: reduce) {.live .dot {animation: none;}}
.live .lt {font-size: .86rem; line-height: 1.55; font-style: italic; opacity: var(--muted); margin-top: 6px;}
.live .lg {font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; opacity: .78; margin: 10px 0 4px;}
.live .chip.theme {background: var(--surface); border-color: var(--line); opacity: .88;}
.live .chip.feature {color: var(--accent-text); background: var(--accent-soft); border-color: var(--accent-line);}
.live .li {font-size: .84rem; padding: 3px 0 3px 10px; border-left: 2px solid var(--accent-line); margin-top: 3px;}

/* ── Sidebar account ──────────────────────────────────────────────────── */
.brand {font-family: 'Newsreader', Georgia, serif; font-size: 1.45rem; font-weight: 500; margin: 0; line-height: 1.1;}
.userbox {border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px;
  background: var(--surface); font-size: .84rem;}
.userbox .mail {font-weight: 600; overflow-wrap: anywhere; margin-bottom: 4px;}
.qrow {display: flex; justify-content: space-between; font-size: .74rem; opacity: .88; margin-top: 9px;
  font-family: 'Geist Mono', ui-monospace, monospace;}

/* ── Admin ────────────────────────────────────────────────────────────── */
.admin-hero {border-radius: 14px; padding: 22px 26px; margin-bottom: 14px; color: #F2EEE4;
  background-color: #14352C; background-image: radial-gradient(rgba(242,238,228,.07) 1px, transparent 1.2px);
  background-size: 16px 16px;}
.admin-hero .eyebrow {color: #A9D3C3; opacity: 1;}
.admin-hero h2 {font-family: 'Newsreader', Georgia, serif; font-weight: 500; color: #F2EEE4; margin: 6px 0 2px;
  padding: 0; font-size: 1.7rem;}
.admin-hero p {margin: 0; opacity: .82; font-size: .92rem;}
.credit {border: 1px solid var(--line); border-radius: 12px; padding: 18px 22px; margin-bottom: 14px;
  background: var(--surface);}
.credit .big {font-family: 'Geist Mono', ui-monospace, monospace; font-size: 2rem; font-weight: 500;
  letter-spacing: -0.02em;}
.credit .row {display: flex; gap: 28px; flex-wrap: wrap; align-items: flex-end;}
.credit .lbl {font-size: .74rem; text-transform: uppercase; letter-spacing: .08em; opacity: .78;}
.credit .val {font-family: 'Geist Mono', ui-monospace, monospace; font-size: 1.05rem;}
.credit a {color: var(--accent-text);}
</style>
"""


def esc(value: Any) -> str:
    """HTML-escape any value (LLM output and user data are untrusted)."""
    return html.escape(str(value))


def chip(label: str, color: str, *, solid: bool = False, text: str = "#FFFFFF") -> str:
    """Return a small tag as HTML."""
    if solid:
        return f'<span class="chip" style="background:{color};color:{text}">{esc(label)}</span>'
    return f'<span class="chip" style="background:{color}1c;color:{color};border-color:{color}55">{esc(label)}</span>'


def moscow_chip(bucket: str) -> str:
    """MoSCoW tag with its ordinal colour (dark text on the light steps)."""
    text = "#1C1B19" if bucket in ("Could", "Won't") else "#FFFFFF"
    return chip(bucket, MOSCOW_COLORS[bucket], solid=True, text=text)


def shorten(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` characters with an ellipsis."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def addition_tabs_css(first_addition: int) -> str:
    """Pale style for the main tabs from position ``first_addition`` (1-based) onwards.

    The tabs the brief asks for keep full contrast; the ones added beyond it
    (connectors, admin console) read as secondary, with a legend at the end of
    the bar. Scoped to the main tab bar (``key="nav"``): nested tab bars are untouched.
    """
    tab = f'.st-key-nav > div > [role="tablist"] > [role="tab"]:nth-child(n+{first_addition})'
    return (
        "<style>"
        f"{tab} {{opacity: .5; font-style: italic;}}"
        f"{tab}:hover, {tab}:focus-visible {{opacity: .85;}}"
        f'{tab}[aria-selected="true"] {{opacity: .8;}}'
        # ::after already draws the bar's underline; ::before is free and `order` moves it to the end.
        '.st-key-nav > div > [role="tablist"]::before {content: "En pâle : ajouts au-delà de la consigne";'
        " order: 99; margin-left: auto; align-self: center; padding-left: 16px; white-space: nowrap;"
        " font-size: .72rem; font-style: italic; opacity: .55;}"
        ".addition {opacity: .6; font-style: italic;}"
        "</style>"
    )


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
