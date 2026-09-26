"""First-run guided onboarding: understand, pick a case, launch.

The dialog never runs the pipeline itself: it records the choice
(``pending_sample`` / ``pending_run``) and triggers a full rerun, so the run
happens in the Inbox with the usual progress display and quota checks.
"""

from __future__ import annotations

import streamlit as st

from config import Settings
from governance import CostEstimator
from samples import DEMO_SAMPLE_KEY, SAMPLES
from ui import session
from ui.style import euros, render_html

_STEPS = ("Le cas d'usage", "Les agents", "Choisir un cas", "Lancer")

_CSS = """
<style>
.ob-steps {display: flex; gap: 22px; margin: 0 0 18px; font-family: 'Geist Mono', ui-monospace, monospace;
  font-size: .7rem; letter-spacing: .12em; text-transform: uppercase;}
.ob-steps span {opacity: .55; padding-bottom: 6px; border-bottom: 1px solid transparent;}
.ob-steps span.on {opacity: 1; color: var(--accent-text); border-bottom: 2px solid var(--accent);}
.ob-title {font-family: 'Newsreader', Georgia, serif; font-size: 1.9rem; font-weight: 500; line-height: 1.15;
  margin: 0 0 8px;}
.ob-lead {opacity: .85; font-size: .98rem; line-height: 1.55; margin-bottom: 18px;}
.ob-card {border: 1px solid var(--line); border-radius: 10px; padding: 16px; height: 100%; background: var(--surface);}
.ob-card .n {font-family: 'Geist Mono', ui-monospace, monospace; font-size: .7rem; color: var(--accent-text);}
.ob-card .t {font-family: 'Newsreader', Georgia, serif; font-size: 1.2rem; margin: 6px 0 4px;}
.ob-card .d {font-size: .86rem; opacity: .8; line-height: 1.5;}
.ob-facts {display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 4px 0 6px;}
.ob-fact {border-top: 1px solid var(--line); padding-top: 8px;}
.ob-fact .v {font-family: 'Geist Mono', ui-monospace, monospace; font-size: 1.2rem;}
.ob-fact .l {font-size: .8rem; opacity: .78;}
.ob-quote {font-family: 'Newsreader', Georgia, serif; font-style: italic; font-size: 1.08rem; opacity: .9;
  border-left: 2px solid var(--accent); padding-left: 14px; margin: 14px 0 6px;}
</style>
"""


def _done() -> None:
    st.session_state["onboarded"] = True
    st.session_state["_ob_step"] = 0
    session.mark_onboarded()  # not shown again at the next sign-in


def _go(step: int) -> None:
    st.session_state["_ob_step"] = step


def reopen() -> None:
    """Callback for the sidebar "Guide de démarrage" button."""
    st.session_state["onboarded"] = False
    st.session_state["_ob_step"] = 0


@st.dialog("Bienvenue", width="large", on_dismiss=_done)
def onboarding_dialog(settings: Settings, top_n: int) -> None:
    """Three-step guided start."""
    step = st.session_state.get("_ob_step", 0)
    render_html(
        _CSS
        + '<div class="ob-steps">'
        + "".join(
            f'<span class="{"on" if i == step else ""}">0{i + 1} {label}</span>' for i, label in enumerate(_STEPS)
        )
        + "</div>"
    )
    if step == 0:
        _use_case()
    elif step == 1:
        _discover()
    elif step == 2:
        _choose()
    else:
        _launch(settings, top_n)


def _use_case() -> None:
    render_html(
        '<div class="ob-title">Vous êtes Product Owner chez EwokAI.</div>'
        '<div class="ob-lead">EwokAI est une startup SaaS qui édite une <b>plateforme de gestion de projets</b> : '
        "planification, diagrammes de Gantt, charge des équipes. Ses clients sont des PME et des ETI. Chaque "
        "semaine, les retours clients arrivent de partout : emails, tickets du support, enquêtes NPS, remontées "
        "des équipes Customer Success et Sales, avis sur les stores. Le PO est submergé : il doit tout lire, "
        "décider quoi construire en priorité et écrire des user stories exploitables par l'équipe.</div>"
        '<div class="ob-facts">'
        '<div class="ob-fact"><div class="v">10</div><div class="l">messages dans l\'inbox de démo</div></div>'
        '<div class="ob-fact"><div class="v">6</div><div class="l">canaux différents, 2 langues</div></div>'
        '<div class="ob-fact"><div class="v">5</div><div class="l">besoins cachés à faire émerger</div></div>'
        "</div>"
        '<div class="ob-quote">L\'assistant fait le travail de fond : lire, trier, prioriser, rédiger. '
        "Le PO garde la décision.</div>"
    )
    st.caption("EwokAI et tous les clients cités sont fictifs.")
    left, right = st.columns([1, 1])
    if left.button("Passer l'introduction", type="tertiary", key="ob_skip0"):
        _done()
        st.rerun()  # a full rerun is what closes a dialog
    right.button("Continuer", type="primary", width="stretch", on_click=_go, args=(1,), key="ob_next_uc")


def _discover() -> None:
    render_html(
        '<div class="ob-title">Trois agents, un backlog argumenté.</div>'
        '<div class="ob-lead">Chaque agent a une seule mission et un format de sortie strict. Le calcul des scores '
        "et le classement sont faits par du code, pas par l'IA : ils sont reproductibles et vous pouvez les "
        "corriger.</div>"
    )
    cols = st.columns(3)
    cards = [
        ("01", "Analyser", "Sépare les sources, isole les demandes, regroupe par thème et garde les verbatims."),
        ("02", "Prioriser", "Estime Reach, Impact, Confidence et Effort avec une justification, puis classe."),
        ("03", "Rédiger", "Écrit les user stories et leurs critères d'acceptation au format Gherkin."),
    ]
    for col, (n, title, text) in zip(cols, cards, strict=True):
        with col:
            render_html(f'<div class="ob-card"><div class="n">{n}</div><div class="t">{title}</div>'
                        f'<div class="d">{text}</div></div>')  # fmt: skip
    st.write("")
    left, right = st.columns([1, 1])
    left.button("Retour", type="tertiary", on_click=_go, args=(0,), key="ob_back0")
    right.button("Continuer", type="primary", width="stretch", on_click=_go, args=(2,), key="ob_next0")


def _choose() -> None:
    render_html(
        '<div class="ob-title">Choisissez un cas client.</div>'
        '<div class="ob-lead">Chaque jeu contient des retours réalistes, mot pour mot : emails, tickets, NPS, '
        "notes d'appel. Vous pourrez aussi coller les vôtres ensuite.</div>"
    )
    keys = list(SAMPLES)
    current = st.session_state.get("_ob_sample", DEMO_SAMPLE_KEY)
    choice = st.radio(
        "Cas client",
        keys,
        index=keys.index(current),
        format_func=lambda k: SAMPLES[k].label,
        captions=[SAMPLES[k].pitch for k in keys],
        label_visibility="collapsed",
        key="ob_sample_radio",
    )
    st.session_state["_ob_sample"] = choice
    st.write("")
    left, right = st.columns([1, 1])
    left.button("Retour", type="tertiary", on_click=_go, args=(1,), key="ob_back1")
    right.button("Continuer", type="primary", width="stretch", on_click=_go, args=(3,), key="ob_next1")


def _launch(settings: Settings, top_n: int) -> None:
    sample_key = st.session_state.get("_ob_sample", DEMO_SAMPLE_KEY)
    sample = SAMPLES[sample_key]
    estimate = CostEstimator().predict(len(sample.text), top_n)
    render_html(
        '<div class="ob-title">Lancez l\'analyse.</div>'
        f'<div class="ob-lead">Cas retenu : <b>{sample.label}</b>. Après le lancement, suivez les onglets '
        "dans l'ordre : Analyse, Priorisation, User stories, Export.</div>"
    )
    options: dict[str, str] = {}
    if sample_key == DEMO_SAMPLE_KEY:  # quick demo first, so it is pre-selected
        options["demo"] = "Démo rapide — résultat pré-calculé, instantané et sans coût"
    if settings.has_api_key:
        options["live"] = f"En direct avec Claude — 1 à 2 minutes, environ {euros(estimate.point_eur)}"
    if not options:
        st.info(
            "La démonstration instantanée n'existe que pour le cas « Notifications & churn », et aucune clé "
            "Anthropic n'est configurée pour une analyse en direct. Revenez en arrière pour choisir ce cas."
        )
    mode = st.radio("Mode", list(options), format_func=options.get, label_visibility="collapsed", key="ob_mode")
    st.write("")
    left, right = st.columns([1, 1])
    left.button("Retour", type="tertiary", on_click=_go, args=(2,), key="ob_back2")
    if right.button("Démarrer", type="primary", width="stretch", disabled=not options, key="ob_run"):
        st.session_state["pending_sample"] = sample_key
        st.session_state["pending_run"] = mode
        _done()
        st.rerun()
