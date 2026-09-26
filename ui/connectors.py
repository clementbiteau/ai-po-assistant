"""The "Connecteurs" tab: where the PO would plug their tools in production.

Nothing here is live. The tab shows the integration roadmap (what each
connector brings, how it authorises, how often it syncs, in which order they
ship) so the path from POC to production is concrete. The "Connecter"
buttons stay disabled: the POC never asks for third-party credentials.
"""

from __future__ import annotations

import streamlit as st

from connectors import PHASES, Connector, by_phase
from triage import channel_for
from ui.style import ACCENT, STATUS, chip, esc, render_html

_DIRECTION = {"in": "Entrée", "out": "Sortie", "both": "Entrée et sortie"}

_CSS = """
<style>
.flow {display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 4px 0 18px;}
.flow .n {border: 1px solid var(--line); background: var(--surface); border-radius: 8px; padding: 8px 12px;
  font-size: .86rem;}
.flow .n b {display: block; font-size: .7rem; letter-spacing: .12em; text-transform: uppercase;
  color: var(--accent-text); font-weight: 500; font-family: 'Geist Mono', ui-monospace, monospace;}
.flow .a {opacity: .5;}
.conn-h {font-family: 'Newsreader', Georgia, serif; font-size: 1.2rem; font-weight: 500; margin: 0 0 4px;}
.conn-cat {font-size: .76rem; opacity: var(--muted); margin-bottom: 8px;}
.conn-d {font-size: .88rem; line-height: 1.5; margin: 6px 0 10px;}
.conn-m {display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: .78rem;}
.conn-m span:nth-child(odd) {opacity: .7;}
</style>
"""


def render_connectors() -> None:
    """Integration roadmap: flow, connectors by phase, production principles."""
    render_html(_CSS)
    st.caption(
        "En production, les retours arriveraient seuls depuis vos outils, et le backlog validé partirait dans Jira. "
        "Aucun connecteur n'est actif dans ce POC."
    )
    steps = [
        ("Connecteurs", "Zendesk, email, Slack…"),
        ("Tri par règles", "canal, urgence, doublons"),
        ("Agents Claude", "analyse, RICE, stories"),
        ("Validation PO", "estimations corrigées"),
        ("Jira", "stories et critères"),
    ]
    render_html(
        '<div class="flow">'
        + '<span class="a">→</span>'.join(f'<div class="n"><b>{esc(t)}</b>{esc(d)}</div>' for t, d in steps)
        + "</div>"
    )

    for phase, connectors in by_phase().items():
        title, why = PHASES[phase]
        if phase == 1:
            st.markdown(f"#### {title}")
            st.caption(why)
            _cards(connectors)
        else:
            with st.expander(f"{title} · {', '.join(c.name for c in connectors)}"):
                st.caption(why)
                _cards(connectors)

    with st.expander("Principes pour la production"):
        st.markdown(
            "- **Lecture seule et accès minimal** : chaque connecteur ne lit que ce dont il a besoin "
            "(une boîte partagée, un canal, une vue de tickets).\n"
            "- **Jetons dans un coffre-fort** : les autorisations OAuth sont gérées côté serveur, jamais saisies ni "
            "stockées dans l'application.\n"
            "- **Données personnelles pseudonymisées** avant l'envoi à Claude (RGPD) : noms et emails remplacés, "
            "entreprise et rôle conservés.\n"
            "- **Dédoublonnage** : un même client qui écrit au support et en parle à son CSM ne compte qu'une fois.\n"
            "- **Le PO garde la main** : rien ne part dans Jira sans sa validation."
        )


def _cards(connectors: list[Connector]) -> None:
    cols = st.columns(3)
    for i, connector in enumerate(connectors):
        with cols[i % 3], st.container(border=True):
            _card(connector)


def _card(connector: Connector) -> None:
    direction = chip(_DIRECTION[connector.direction], ACCENT if connector.direction != "in" else STATUS["neutral"])
    arrives = channel_for(connector.header_tag) if connector.header_tag else "—"
    render_html(
        f'<div class="conn-h">{esc(connector.name)}</div>'
        f'<div class="conn-cat">{esc(connector.category)}</div>{direction}'
        f'<div class="conn-d">{esc(connector.brings)}</div>'
        '<div class="conn-m">'
        f"<span>Connexion</span><span>{esc(connector.auth)}</span>"
        f"<span>Synchronisation</span><span>{esc(connector.cadence)}</span>"
        f"<span>Arrive comme</span><span>{esc(arrives)}</span>"
        "</div>"
    )
    st.button(
        "Connecter",
        key=f"connect_{connector.key}",
        disabled=True,
        width="stretch",
        help="Disponible au passage en production : aucune connexion n'est active dans le POC.",
    )
