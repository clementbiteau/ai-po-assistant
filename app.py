"""Streamlit frontend of the AI Product Owner Assistant.

This file only handles presentation and user interaction. All business
logic (agents, scoring, prompts, API calls) lives in ``agents.py``;
configuration lives in ``config.py``; exports in ``exporters.py``.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from agents import (
    AgentBudgetError,
    AgentError,
    PipelineEvent,
    PipelineResult,
    POAssistantPipeline,
    ProductContext,
    ScoredFeature,
    UserStory,
    backlog_order,
    score_portfolio,
)
from config import Settings, get_settings
from exporters import to_feature_files, to_jira_csv, to_json, to_markdown
from governance import evaluate_quota
from samples import DEMO_SAMPLE_KEY, SAMPLES
from store import Profile, StoreError
from ui import session
from ui.admin import render_admin
from ui.login import render_login
from ui.style import (
    CHART_TEXT,
    CSS,
    MOSCOW_COLORS,
    MOSCOW_DOTS,
    MOSCOW_ORDER,
    camel_break,
    chip,
    esc,
    euros,
    moscow_chip,
    render_html,
    shorten,
)
from ui.theme import theme_toggle

# ══════════════════════════════════════════════════════════════════════════
# Page setup & design tokens
# ══════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="AI Product Owner Assistant",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEMO_RESULT_PATH = Path(__file__).parent / "data" / "demo_result.json"

MOSCOW_HINTS: dict[str, str] = {
    "Must": "Non négociable pour ce cycle",
    "Should": "Important, planifier ensuite",
    "Could": "Si la capacité le permet",
    "Won't": "Pas ce cycle — à revisiter",
}
SENTIMENT_STYLE: dict[str, tuple[str, str]] = {
    "critical": ("Critique", "#DC2626"),
    "negative": ("Négatif", "#EA580C"),
    "neutral": ("Neutre", "#6B7280"),
    "positive": ("Positif", "#16A34A"),
}
SIGNAL_GROUPS: list[tuple[str, str, str]] = [
    ("bug", "🐞 Bugs", "À router vers la QA / le support"),
    ("ux_friction", "🧩 Frictions UX", "Quick fixes de design"),
    ("question", "❓ Questions", "Besoin de doc / d'onboarding"),
    ("praise", "💚 Points forts", "À préserver et à valoriser"),
]
AGENTS_META: list[tuple[str, str, str, str]] = [
    ("analyst", "FeedbackAnalyst", "🔎", "Extrait patterns, thèmes et feature requests"),
    ("strategist", "PrioritizationStrategist", "📊", "Score RICE justifié + MoSCoW"),
    ("writer", "UserStoryWriter", "📝", "User stories + critères Gherkin"),
]
TABS = ["📥 Inbox", "🔎 Analyse", "📊 Priorisation", "📝 User Stories", "📦 Export"]
ADMIN_TAB = "🛡️ Admin"

# ══════════════════════════════════════════════════════════════════════════
# State
# ══════════════════════════════════════════════════════════════════════════


def init_state() -> None:
    """Initialise session keys once per browser session."""
    defaults: dict[str, Any] = {
        "feedback_text": SAMPLES[DEMO_SAMPLE_KEY].text,
        "result": None,
        "run_id": 0,
        "nav": TABS[0],
        "api_key_input": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    if pending := st.session_state.pop("pending_nav", None):
        st.session_state.nav = pending


def load_sample(key: str) -> None:
    """Callback: put a sample in the text area."""
    st.session_state.feedback_text = SAMPLES[key].text


def clear_input() -> None:
    """Callback: empty the text area."""
    st.session_state.feedback_text = ""


def editor_key() -> str:
    """Key of the RICE editor, unique per run so edits never leak across runs."""
    return f"rice_editor_{st.session_state.run_id}"


def store_result(result: PipelineResult) -> None:
    """Save a fresh result and jump to the analysis tab."""
    st.session_state.result = result
    st.session_state.run_id += 1
    # The tabs widget is already rendered in this run: switch on the next one.
    st.session_state.pending_nav = TABS[1]


def current_result() -> PipelineResult | None:
    """Return the stored result, re-hydrated if the code was reloaded.

    Streamlit re-imports modules when sources change (dev hot-reload, redeploy).
    Objects already in the session then belong to the *previous* Pydantic
    classes and would fail validation; a dump/validate round-trip fixes that.
    """
    result = st.session_state.result
    if result is not None and not isinstance(result, PipelineResult):
        result = PipelineResult.model_validate(result.model_dump())
        st.session_state.result = result
    return result


@st.cache_data(show_spinner=False)
def load_demo_result() -> PipelineResult:
    """Load the pre-computed offline demo run (validated against the schemas)."""
    return PipelineResult.model_validate_json(DEMO_RESULT_PATH.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════════
# Human-in-the-loop RICE overrides
# ══════════════════════════════════════════════════════════════════════════

EDITABLE_TO_FIELD: dict[str, str] = {
    "Reach %": "reach_percent",
    "Impact": "impact",
    "Confidence": "confidence",
    "Effort": "effort",
    "Mandatory": "is_mandatory",
}


def rice_inputs_frame(result: PipelineResult) -> pd.DataFrame:
    """AI-estimated RICE inputs, one row per feature, in a stable order."""
    rows = [
        {
            "ID": s.feature.id,
            "Feature": s.feature.title,
            "Reach %": s.assessment.reach_percent,
            "Impact": s.assessment.impact,
            "Confidence": s.assessment.confidence,
            "Effort": s.assessment.effort,
            "Mandatory": s.assessment.is_mandatory,
        }
        for s in sorted(result.scored_features, key=lambda s: s.feature.id)
    ]
    return pd.DataFrame(rows)


def effective_scoring(result: PipelineResult) -> tuple[list[ScoredFeature], set[str]]:
    """Apply the PO's edits (if any) and re-score deterministically.

    Returns:
        The re-ranked features and the ids of features the PO modified.
    """
    base = rice_inputs_frame(result)
    edits = st.session_state.get(editor_key(), {}).get("edited_rows", {})
    by_id = {s.feature.id: s for s in result.scored_features}
    pairs, modified = [], set()
    for position, row in base.iterrows():
        scored = by_id[row["ID"]]
        changes = edits.get(position, edits.get(str(position), {}))
        update: dict[str, Any] = {}
        for column, field in EDITABLE_TO_FIELD.items():
            if column in changes and changes[column] is not None:
                value = changes[column]
                update[field] = bool(value) if field == "is_mandatory" else int(value)
        if update:
            original = scored.assessment.model_dump()
            if any(original[k] != v for k, v in update.items()):
                modified.add(scored.feature.id)
        pairs.append((scored.feature, scored.assessment.model_copy(update=update)))
    return score_portfolio(pairs, result.context.active_users), modified


# ══════════════════════════════════════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════════════════════════════════════


def render_account(settings: Settings, profile: Profile) -> None:
    """Signed-in user, quota gauges, theme toggle and sign-out."""
    try:
        used = session.consumption(settings)
    except StoreError:
        used = None
    role = chip("admin", "#7C3AED", solid=True) if profile.is_admin else chip("membre", "#6366F1")
    gauges = ""
    if used is not None:
        for label, spent, limit in (
            ("Aujourd'hui", used.day_eur, profile.quota.daily_eur),
            ("Semaine", used.week_eur, profile.quota.weekly_eur),
            ("Mois", used.month_eur, profile.quota.monthly_eur),
        ):
            ratio = min(spent / limit, 1.0) if limit else 0.0
            color = "#DC2626" if ratio >= 0.9 else "#F59E0B" if ratio >= 0.7 else "#22C55E"
            gauges += (
                f'<div class="qrow"><span>{label}</span><span>{euros(spent)} / {euros(limit)}</span></div>'
                f'<div class="bar" style="margin-top:3px"><span style="width:{ratio * 100:.0f}%;background:{color}">'
                "</span></div>"
            )
    per_request = euros(profile.quota.max_eur_per_request)
    render_html(
        f'<div class="userbox"><div class="mail">{esc(profile.email)}</div>{role}'
        f'<div class="qrow"><span>Max / requête</span><span>{per_request}</span></div>{gauges}</div>'
    )
    left, right = st.columns([1.25, 1], vertical_alignment="center", gap="small")
    with left:
        theme_toggle("sidebar")
    with right:
        if st.button("Sortir", icon=":material/logout:", type="tertiary", key="logout", help="Se déconnecter"):
            session.sign_out()
            st.rerun()


def render_sidebar(base_settings: Settings, profile: Profile) -> tuple[Settings, ProductContext, int, bool]:
    """Account, connection, product context and generation options."""
    with st.sidebar:
        st.markdown("### 🧭 PO Copilot")
        st.caption("Du feedback brut au backlog Jira priorisé.")
        render_account(base_settings, profile)

        st.markdown("##### Connexion")
        if base_settings.has_api_key:
            st.badge("Clé API chargée depuis l'environnement", icon=":material/verified:", color="green")
        else:
            st.text_input(
                "Clé API Anthropic",
                key="api_key_input",
                type="password",
                placeholder="sk-ant-…",
                help="Utilisée uniquement pendant cette session, jamais stockée.",
            )
        settings = base_settings.with_api_key(st.session_state.api_key_input)
        demo_mode = st.toggle(
            "Mode démo hors-ligne",
            value=not settings.has_api_key,
            help="Rejoue un run pré-calculé sur l'exemple 🔔 — idéal si le réseau lâche en démo live.",
        )
        st.caption(f"Modèle : `{settings.model}` · thinking adaptatif")

        st.divider()
        st.markdown("##### Contexte produit")
        defaults = ProductContext()
        context = ProductContext(
            product_name=st.text_input("Produit", value=defaults.product_name),
            product_description=st.text_area("Description", value=defaults.product_description, height=90),
            active_users=int(
                st.number_input(
                    "Utilisateurs actifs / mois",
                    min_value=100,
                    max_value=10_000_000,
                    value=defaults.active_users,
                    step=500,
                    help="Ancre le « R » de RICE : Reach = % de la base touchée × ce nombre.",
                )
            ),
            strategic_goal=st.text_area(
                "Objectif stratégique du trimestre",
                value=defaults.strategic_goal,
                height=80,
                help="L'Impact est évalué au regard de cet objectif.",
            ),
            language=st.segmented_control(
                "Langue des livrables",
                options=["fr", "en"],
                default="fr",
                required=True,
                format_func=lambda code: {"fr": "🇫🇷 Français", "en": "🇬🇧 English"}[code],
            ),
        )

        st.divider()
        st.markdown("##### Génération")
        top_n = st.slider(
            "User stories générées d'office",
            min_value=1,
            max_value=6,
            value=3,
            help="Dans l'ordre du backlog (MoSCoW puis RICE). Les autres restent générables à la demande.",
        )

        st.divider()
        with st.expander("⚙️ Sous le capot"):
            st.markdown(
                "- **3 agents spécialisés**, un contrat Pydantic chacun\n"
                "- **Structured outputs** natifs : JSON validé par schéma\n"
                "- **Le LLM estime, le code calcule** : score RICE & MoSCoW déterministes\n"
                "- **Auto-correction** : 1 retry guidé si la sortie viole une règle métier\n"
                "- Stories rédigées **en parallèle**"
            )
    return settings, context, top_n, demo_mode


# ══════════════════════════════════════════════════════════════════════════
# Header
# ══════════════════════════════════════════════════════════════════════════


def render_hero(result: PipelineResult | None) -> None:
    """Hero banner with the agent pipeline as a visual flow."""
    done = " done" if result else ""
    check = '<span class="ok">✓</span>' if result else ""
    nodes = []
    for _key, name, icon, desc in AGENTS_META:
        nodes.append(
            f'<div class="node{done}">{check}<div class="t">{icon} {camel_break(name)}</div>'
            f'<div class="d">{esc(desc)}</div></div>'
        )
    flow = (
        '<div class="io">📨 Feedbacks bruts</div><div class="arrow">→</div>'
        + '<div class="arrow">→</div>'.join(nodes)
        + '<div class="arrow">→</div><div class="io">🎫 Backlog Jira</div>'
    )
    render_html(
        '<div class="hero"><div class="eyebrow">AI Product Owner Assistant · POC</div>'
        "<h1>Du feedback client au backlog priorisé.</h1>"
        '<p class="sub">Emails, tickets Zendesk, NPS, notes d\'appel… trois agents IA les transforment en '
        "priorités RICE justifiées et en user stories Gherkin prêtes pour le sprint.</p>"
        f'<div class="flow">{flow}</div></div>'
    )


def render_kpis(result: PipelineResult, scored: list[ScoredFeature]) -> None:
    """Top KPI strip, visible once a run exists."""
    musts = sum(1 for s in scored if s.moscow == "Must")
    cols = st.columns(6)
    cols[0].metric("Sources", result.analysis.sources_count, border=True)
    cols[1].metric("Thèmes", len(result.analysis.themes), border=True)
    cols[2].metric("Features", len(scored), border=True)
    cols[3].metric("Must have", musts, border=True)
    cols[4].metric("Stories", len(result.stories), border=True)
    cost = result.usage.estimated_cost_usd
    cols[5].metric(
        "Run",
        f"{result.usage.wall_clock_s:.0f} s",
        delta=f"≈ {cost:.3f} USD" if cost is not None else None,
        delta_color="off",
        delta_arrow="off",
        border=True,
        help="Durée totale et coût API estimé du run.",
    )
    if result.is_demo:
        st.info(
            "**Mode démo** : résultats pré-calculés sur l'exemple 🔔 « Notifications & churn ». "
            "Ajoutez une clé API pour analyser vos propres feedbacks en direct.",
            icon=":material/play_circle:",
        )


# ══════════════════════════════════════════════════════════════════════════
# Tab 1 · Inbox
# ══════════════════════════════════════════════════════════════════════════


def render_inbox(settings: Settings, profile: Profile, context: ProductContext, top_n: int, demo_mode: bool) -> None:
    """Sample picker, raw input and the run button."""
    st.markdown("#### Chargez un exemple en 1 clic")
    cols = st.columns(len(SAMPLES))
    for col, sample in zip(cols, SAMPLES.values(), strict=True):
        with col, st.container(border=True):
            st.markdown(f"**{sample.icon} {sample.label}**")
            st.caption(sample.pitch)
            st.button(
                "Charger",
                key=f"load_{sample.key}",
                on_click=load_sample,
                args=(sample.key,),
                icon=":material/download:",
                width="stretch",
            )

    st.markdown("#### …ou collez vos feedbacks bruts")
    st.text_area(
        "Feedbacks",
        key="feedback_text",
        height=360,
        label_visibility="collapsed",
        placeholder="Collez ici un mélange d'emails, tickets Zendesk, verbatims NPS, notes d'appel…",
    )
    text = st.session_state.feedback_text or ""
    words = len(text.split())
    st.caption(f"{len(text):,} caractères · {words:,} mots".replace(",", " "))

    left, mid, _ = st.columns([2.2, 1, 3])
    run = left.button(
        "Lancer les 3 agents",
        type="primary",
        icon=":material/rocket_launch:",
        width="stretch",
        disabled=not text.strip(),
    )
    mid.button("Effacer", on_click=clear_input, type="tertiary", icon=":material/delete:")

    if not run:
        return
    if demo_mode:
        run_demo(text)
    else:
        run_live(text, settings, profile, context, top_n)


def run_demo(text: str) -> None:
    """Replay the pre-computed run with the same progress UX as a live run."""
    if text.strip() != SAMPLES[DEMO_SAMPLE_KEY].text.strip():
        st.warning(
            "Le mode démo rejoue uniquement l'exemple 🔔 « Notifications & churn ». "
            "Chargez-le, ou désactivez le mode démo et renseignez une clé API.",
            icon=":material/info:",
        )
        return
    result = load_demo_result()
    with st.status("Les agents travaillent… (démo)", expanded=True) as status:
        script = [
            ("🔎 **FeedbackAnalyst** — segmentation de 10 sources, 6 canaux…", 0.6),
            ("✅ **FeedbackAnalyst** — 5 thèmes · 5 features candidates · 4 autres signaux", 0.5),
            ("📊 **PrioritizationStrategist** — estimation Reach · Impact · Confidence · Effort…", 0.8),
            ("✅ **PrioritizationStrategist** — N°1 : Maîtrise et regroupement des notifications", 0.4),
            ("📝 **UserStoryWriter** — rédaction de 3 user stories en parallèle…", 0.8),
            ("✅ **UserStoryWriter** — 3 user stories prêtes pour Jira", 0.2),
        ]
        for line, pause in script:
            st.write(line)
            time.sleep(pause)
        status.update(label="Analyse terminée (démo)", state="complete", expanded=False)
    store_result(result)
    st.rerun()


def check_quota(settings: Settings, profile: Profile, input_chars: int, stories: int) -> float | None:
    """Estimate the run cost and apply the user's quotas.

    Returns:
        The hard budget in USD to enforce during the run (``None`` = no cap).

    Raises:
        QuotaBlocked: When the run must not start (already displayed + logged).
    """
    try:
        used = session.consumption(settings, force=True)
        estimate = session.cost_estimator().predict(input_chars, stories)
    except StoreError as exc:
        st.error(f"Vérification du quota impossible : {exc.user_message}", icon=":material/database:")
        raise QuotaBlocked from exc
    decision = evaluate_quota(profile.quota, used, estimate.point_eur)
    if not decision.allowed:
        st.error(decision.reason, icon=":material/block:")
        session.record_usage(settings, None, kind="pipeline", status="blocked", input_chars=input_chars,
                             stories_count=stories, error=decision.reason)  # fmt: skip
        raise QuotaBlocked
    st.caption(
        f"💶 Coût estimé : **{euros(estimate.point_eur, digits=3)}** (P90 {euros(estimate.upper_eur, digits=3)}) · "
        f"plafond de ce run : {euros(decision.budget_eur)}"
    )
    return None if decision.budget_eur is None else decision.budget_eur / settings.usd_to_eur


class QuotaBlocked(RuntimeError):
    """The run was refused by the quota policy."""


def run_live(text: str, settings: Settings, profile: Profile, context: ProductContext, top_n: int) -> None:
    """Run the real multi-agent pipeline with quota checks and live progress."""
    try:
        budget_usd = check_quota(settings, profile, len(text), top_n)
    except QuotaBlocked:
        return
    labels = {key: f"{icon} **{name}**" for key, name, icon, _ in AGENTS_META}
    pipeline: POAssistantPipeline | None = None
    started = time.perf_counter()
    with st.status("Les agents travaillent…", expanded=True) as status:

        def on_event(event: PipelineEvent) -> None:
            mark = {"running": "", "done": "✅ ", "error": "❌ "}[event.status]
            st.write(f"{mark}{labels[event.step]} — {event.message}")
            if event.status == "running":
                status.update(label=f"{labels[event.step].replace('**', '')} en cours…")

        try:
            pipeline = POAssistantPipeline(settings, on_event=on_event, budget_usd=budget_usd)
            result = pipeline.run(text, context, top_n=top_n)
        except AgentError as exc:
            status.update(label="Le pipeline s'est arrêté", state="error", expanded=True)
            show_agent_error(exc)
            _record_failure(settings, pipeline, started, len(text), top_n, exc)
            return
        except Exception as exc:  # noqa: BLE001 — last-resort guard for the demo
            status.update(label="Erreur inattendue", state="error", expanded=True)
            st.error("Une erreur inattendue est survenue. Détails techniques ci-dessous.")
            st.exception(exc)
            _record_failure(settings, pipeline, started, len(text), top_n, exc)
            return
        status.update(label="Analyse terminée", state="complete", expanded=False)
    session.record_usage(
        settings, result.usage, kind="pipeline", status="success", input_chars=len(text),
        features_count=len(result.scored_features), stories_count=len(result.stories),
    )  # fmt: skip
    store_result(result)
    st.toast("Backlog prêt ! Direction l'onglet Analyse.", icon="🎉")
    st.rerun()


def _record_failure(
    settings: Settings, pipeline: POAssistantPipeline | None, started: float, chars: int, stories: int, exc: Exception
) -> None:
    """Log the tokens already spent by a failed run: they count towards quotas too."""
    usage = pipeline.usage_report(time.perf_counter() - started) if pipeline else None
    status = "blocked" if isinstance(exc, AgentBudgetError) else "error"
    message = exc.user_message if isinstance(exc, AgentError) else type(exc).__name__
    session.record_usage(settings, usage, kind="pipeline", status=status, input_chars=chars,
                         stories_count=stories, error=message)  # fmt: skip


def show_agent_error(exc: AgentError) -> None:
    """Display a typed pipeline error with actionable context."""
    details = []
    if exc.agent:
        details.append(f"Agent : `{exc.agent}`")
    if exc.request_id:
        details.append(f"Request ID : `{exc.request_id}`")
    if exc.retryable:
        details.append("Erreur temporaire — relancer devrait fonctionner.")
    st.error(exc.user_message + ("\n\n" + " · ".join(details) if details else ""), icon=":material/error:")


# ══════════════════════════════════════════════════════════════════════════
# Tab 2 · Analysis
# ══════════════════════════════════════════════════════════════════════════


def render_analysis(result: PipelineResult) -> None:
    """Executive summary, themes, feature candidates and other signals."""
    analysis = result.analysis
    render_html(f'<div class="summary">{esc(analysis.executive_summary)}</div>')
    st.write("")
    render_html(" ".join(chip(c, "#4F46E5") for c in analysis.channels))

    st.markdown("#### Thèmes récurrents")
    max_mentions = max((t.mention_count for t in analysis.themes), default=1) or 1
    cols = st.columns(3)
    for i, theme in enumerate(sorted(analysis.themes, key=lambda t: t.mention_count, reverse=True)):
        label, color = SENTIMENT_STYLE.get(theme.sentiment, ("—", "#6B7280"))
        width = int(100 * theme.mention_count / max_mentions)
        with cols[i % 3]:
            render_html(
                f'<div class="card" style="margin-bottom:12px"><div class="h">{esc(theme.name)}</div>'
                f"{chip(label, color)}{chip(f'{theme.mention_count} mention(s)', '#4B5563')}"
                f'<div class="muted">{esc(theme.description)}</div>'
                f'<div class="bar"><span style="width:{width}%;background:{color}"></span></div></div>'
            )

    st.markdown("#### Feature requests isolées")
    st.caption("Formulées comme des problèmes utilisateurs, dédoublonnées, avec verbatims exacts comme preuve.")
    for feature in analysis.feature_requests:
        with st.expander(f"**{feature.id} · {feature.title}** — {feature.mention_count} mention(s) · {feature.theme}"):
            left, right = st.columns([3, 2])
            with left:
                render_html('<div class="kicker">Problème</div>')
                st.write(feature.problem_statement)
                render_html('<div class="kicker">Résultat attendu</div>')
                st.write(feature.desired_outcome)
                render_html('<div class="kicker">Verbatims</div>')
                render_html("".join(f'<div class="quote">« {esc(q)} »</div>' for q in feature.evidence_quotes))
            with right:
                render_html('<div class="kicker">Segments</div>')
                render_html(" ".join(chip(s, "#7C3AED") for s in feature.user_segments))
                render_html('<div class="kicker">Sources</div>')
                for source in feature.sources:
                    st.caption(f"• {source}")

    if analysis.other_signals:
        st.markdown("#### Autres signaux — hors roadmap, à router")
        cols = st.columns(len(SIGNAL_GROUPS))
        for col, (kind, title, hint) in zip(cols, SIGNAL_GROUPS, strict=True):
            items = [s for s in analysis.other_signals if s.type == kind]
            with col, st.container(border=True):
                st.markdown(f"**{title}** · {len(items)}")
                st.caption(hint)
                for item in items:
                    st.markdown(f"- {item.summary}", help=f"« {item.quote} »")


# ══════════════════════════════════════════════════════════════════════════
# Tab 3 · Prioritisation
# ══════════════════════════════════════════════════════════════════════════

RUBRIC_MD = """
| Niveau | **Impact** (par utilisateur touché) | **Effort** (1 squad, design → QA) |
|---|---|---|
| 5 | Massive — bloque adoption / renouvellement | XL — > 1 trimestre, infra / réglementaire |
| 4 | High — gain majeur, débloque un workflow clé | L — 1-2 mois, transverse ou intégration tierce |
| 3 | Medium — amélioration nette du quotidien | M — ~1 sprint, nouvel écran / entité |
| 2 | Low — nice-to-have, contournements OK | S — 1-2 semaines, périmètre contenu |
| 1 | Minimal — cosmétique / cas limite | XS — < 1 semaine, config ou UI |

**Confidence** : 100 % = plusieurs sources + impact chiffré · 80 % = convergence qualitative · 50 % = signal isolé.
**Reach** = % des utilisateurs actifs touchés sur un trimestre × taille de la base.
**MoSCoW** : relatif au meilleur score du lot — Must ≥ 60 %, Should ≥ 30 %, Could ≥ 10 %, sinon Won't.
Une contrainte non négociable (sécurité, légal, contrat) force **Must**.
"""


def render_prioritization(result: PipelineResult, scored: list[ScoredFeature], modified: set[str]) -> None:
    """RICE table, value/effort matrix, MoSCoW board and justifications."""
    head_left, head_right = st.columns([3, 1], vertical_alignment="center")
    with head_left:
        render_html(
            '<span class="formula">RICE = <em>Reach</em> × <em>Impact</em> × <em>Confidence</em> ÷ <em>Effort</em></span>'
        )
    with head_right, st.popover("Grille de scoring", icon=":material/rule:", width="stretch"):
        st.markdown(RUBRIC_MD)

    st.write("")
    render_html(f'<div class="summary">💡 {esc(result.portfolio_insight)}</div>')
    st.write("")

    # Ranked table ------------------------------------------------------
    best = max((s.rice_score for s in scored), default=1.0) or 1.0
    table = pd.DataFrame(
        [
            {
                "#": s.rank,
                "ID": s.feature.id,
                "Feature": ("✏️ " if s.feature.id in modified else "") + s.feature.title,
                "MoSCoW": f"{MOSCOW_DOTS[s.moscow]} {s.moscow}",
                "RICE": s.rice_score,
                "Reach": s.reach_users,
                "Impact": s.assessment.impact,
                "Confidence": s.assessment.confidence,
                "Effort": s.assessment.effort,
            }
            for s in scored
        ]
    )
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "ID": st.column_config.TextColumn(width="small"),
            "Feature": st.column_config.TextColumn(width="medium"),
            "MoSCoW": st.column_config.TextColumn(width="small"),
            "RICE": st.column_config.ProgressColumn(
                "Score RICE", min_value=0, max_value=best, format="%.0f", width="medium"
            ),
            "Reach": st.column_config.NumberColumn("Reach (users)", format="%d"),
            "Impact": st.column_config.NumberColumn(format="%d / 5"),
            "Confidence": st.column_config.NumberColumn(format="%d %%"),
            "Effort": st.column_config.NumberColumn(format="%d / 5"),
        },
    )

    # Human in the loop -------------------------------------------------
    with st.expander("✏️ Ajuster les estimations de l'IA (human-in-the-loop)", expanded=bool(modified)):
        st.caption(
            "L'IA propose, le PO dispose : modifiez une estimation, le score, le classement, "
            "le MoSCoW et les exports sont recalculés instantanément."
        )
        st.data_editor(
            rice_inputs_frame(result),
            key=editor_key(),
            hide_index=True,
            width="stretch",
            disabled=["ID", "Feature"],
            column_config={
                "Reach %": st.column_config.NumberColumn(min_value=0, max_value=100, step=1, format="%d %%"),
                "Impact": st.column_config.SelectboxColumn(options=[1, 2, 3, 4, 5], required=True),
                "Confidence": st.column_config.SelectboxColumn(options=[50, 80, 100], required=True),
                "Effort": st.column_config.SelectboxColumn(options=[1, 2, 3, 4, 5], required=True),
                "Mandatory": st.column_config.CheckboxColumn("Contrainte (force Must)"),
            },
        )
        if modified:
            st.caption(f"{len(modified)} estimation(s) modifiée(s) : {', '.join(sorted(modified))}")
            if st.button("Revenir aux estimations de l'IA", icon=":material/undo:", type="tertiary"):
                st.session_state.pop(editor_key(), None)
                st.rerun()

    # Charts ----------------------------------------------------------------
    chart_left, chart_right = st.columns(2)
    frame = pd.DataFrame(
        [
            {
                "label": f"{s.feature.id} · {s.feature.title}",
                "short": shorten(f"{s.feature.id} · {s.feature.title}", 34),
                "id": s.feature.id,
                "rice": s.rice_score,
                "moscow": s.moscow,
                "impact": s.assessment.impact,
                "effort": s.assessment.effort,
                "reach": s.reach_users,
            }
            for s in scored
        ]
    )
    color = alt.Color(
        "moscow:N",
        title="MoSCoW",
        scale=alt.Scale(domain=MOSCOW_ORDER, range=[MOSCOW_COLORS[m] for m in MOSCOW_ORDER]),
        legend=alt.Legend(orient="bottom"),
    )
    with chart_left, st.container(border=True):
        st.markdown("**Classement RICE**")
        bar_base = alt.Chart(frame).encode(
            y=alt.Y("short:N", sort=list(frame["short"]), title=None, axis=alt.Axis(labelLimit=240, labelFontSize=12)),
            x=alt.X("rice:Q", title="Score RICE", axis=alt.Axis(format="~s")),
        )
        bars = bar_base.mark_bar(cornerRadiusEnd=6).encode(
            color=alt.Color(
                "moscow:N",
                scale=alt.Scale(domain=MOSCOW_ORDER, range=[MOSCOW_COLORS[m] for m in MOSCOW_ORDER]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Feature"),
                alt.Tooltip("rice:Q", title="RICE", format=",.0f"),
                alt.Tooltip("moscow:N", title="MoSCoW"),
            ],
        )
        values = bar_base.mark_text(align="left", dx=6, fontWeight="bold", fontSize=12, color=CHART_TEXT).encode(
            text=alt.Text("rice:Q", format=",.0f")
        )
        st.altair_chart((bars + values).properties(height=alt.Step(40)), width="stretch")
    with chart_right, st.container(border=True):
        st.markdown("**Matrice valeur / effort**")
        base = alt.Chart(frame)
        left_quadrants = pd.DataFrame(
            [{"x": 0.6, "y": 5.6, "t": "⚡ Quick wins"}, {"x": 0.6, "y": 0.4, "t": "🧩 Fill-ins"}]
        )
        right_quadrants = pd.DataFrame(
            [{"x": 5.4, "y": 5.6, "t": "🎯 Big bets"}, {"x": 5.4, "y": 0.4, "t": "🕳️ Money pits"}]
        )
        points = base.mark_circle(opacity=0.8, stroke="#fff", strokeWidth=2).encode(
            x=alt.X(
                "effort:Q",
                title="Effort →",
                scale=alt.Scale(domain=[0.5, 5.5]),
                axis=alt.Axis(values=[1, 2, 3, 4, 5], format="d"),
            ),
            y=alt.Y(
                "impact:Q",
                title="Impact →",
                scale=alt.Scale(domain=[0.2, 5.8]),
                axis=alt.Axis(values=[1, 2, 3, 4, 5], format="d"),
            ),
            size=alt.Size("reach:Q", scale=alt.Scale(range=[120, 900]), legend=None),
            color=color,
            tooltip=[
                alt.Tooltip("label:N", title="Feature"),
                alt.Tooltip("impact:Q", title="Impact"),
                alt.Tooltip("effort:Q", title="Effort"),
                alt.Tooltip("reach:Q", title="Reach", format=","),
                alt.Tooltip("rice:Q", title="RICE", format=",.0f"),
            ],
        )
        labels = base.mark_text(dx=20, align="left", fontWeight="bold", fontSize=12, color=CHART_TEXT).encode(
            x="effort:Q", y="impact:Q", text="id:N"
        )
        rules = alt.Chart(pd.DataFrame({"x": [3]})).mark_rule(strokeDash=[4, 4], color="#CBD5E1").encode(x="x:Q")
        hrule = alt.Chart(pd.DataFrame({"y": [3]})).mark_rule(strokeDash=[4, 4], color="#CBD5E1").encode(y="y:Q")
        quad_text = alt.layer(
            *[
                alt.Chart(data)
                .mark_text(color="#94A3B8", fontSize=11, fontWeight="bold", align=align)
                .encode(x="x:Q", y="y:Q", text="t:N")
                for data, align in ((left_quadrants, "left"), (right_quadrants, "right"))
            ]
        )
        st.altair_chart((rules + hrule + quad_text + points + labels).properties(height=300), width="stretch")

    # MoSCoW board ------------------------------------------------------
    st.markdown("#### Tableau MoSCoW")
    cols = st.columns(4)
    for col, bucket in zip(cols, MOSCOW_ORDER, strict=True):
        items = [s for s in scored if s.moscow == bucket]
        cards = (
            "".join(
                f'<div class="mini"><b>{esc(s.feature.id)}</b> · {esc(s.feature.title)}'
                f'<div class="s">RICE {s.rice_score:,.0f}{" · 🔒 contrainte" if s.assessment.is_mandatory else ""}</div></div>'
                for s in items
            )
            or '<div class="s" style="color:#9CA3AF;font-size:.8rem;margin-top:8px">—</div>'
        )
        with col:
            render_html(
                f'<div class="moscow-col" style="border-top:4px solid {MOSCOW_COLORS[bucket]}">'
                f'<div class="head"><span>{bucket}</span>{chip(str(len(items)), MOSCOW_COLORS[bucket])}</div>'
                f'<div class="hint">{MOSCOW_HINTS[bucket]}</div>{cards}</div>'
            )

    # Justifications ----------------------------------------------------
    st.markdown("#### Pourquoi ces scores ?")
    st.caption("Chaque estimation cite le niveau de la grille et la preuve qui la justifie.")
    for s in scored:
        a = s.assessment
        with st.expander(f"#{s.rank} · {s.feature.id} · {s.feature.title} — RICE {s.rice_score:,.0f} · {s.moscow}"):
            rows = [
                ("🎯 Reach", f"{a.reach_percent} % → {s.reach_users:,} users".replace(",", " "), a.reach_rationale),
                ("💥 Impact", f"{a.impact} / 5", a.impact_rationale),
                ("🔬 Confidence", f"{a.confidence} %", a.confidence_rationale),
                ("🛠️ Effort", f"{a.effort} / 5", a.effort_rationale),
            ]
            for label, value, why in rows:
                c1, c2, c3 = st.columns([1.1, 1, 5])
                c1.markdown(f"**{label}**")
                c2.markdown(f"`{value}`")
                c3.write(why)
            if a.is_mandatory:
                st.warning(f"**Contrainte non négociable → Must.** {a.mandatory_reason}", icon=":material/lock:")


# ══════════════════════════════════════════════════════════════════════════
# Tab 4 · User stories
# ══════════════════════════════════════════════════════════════════════════


def render_story(story: UserStory, scored: ScoredFeature) -> None:
    """One story, laid out like a refined Jira ticket."""
    title_col, badge_col = st.columns([4, 1.4], vertical_alignment="center")
    with title_col:
        st.markdown(f"### {story.jira_summary}")
    with badge_col:
        render_html(
            f'<div style="text-align:right">{moscow_chip(scored.moscow)}'
            f"{chip(f'{story.story_points} pts', '#4F46E5')}{chip(f'RICE {scored.rice_score:,.0f}', '#0F766E')}</div>"
        )
    render_html(" ".join(chip(f"#{label}", "#6B7280") for label in story.labels))

    render_html(
        f'<div class="statement"><b>As a</b> {esc(story.persona)},<br><b>I want to</b> {esc(story.goal)},<br>'
        f"<b>so that</b> {esc(story.benefit)}.</div>"
    )

    left, right = st.columns([1, 1.35], gap="large")
    with left:
        render_html('<div class="kicker">Contexte</div>')
        st.write(story.context)
        sections = [
            ("🚫 Hors périmètre", story.out_of_scope),
            ("🔗 Dépendances", story.dependencies),
            ("❓ Questions ouvertes pour le PO", story.open_questions),
        ]
        for title, items in sections:
            if items:
                render_html(f'<div class="kicker">{title}</div>')
                st.markdown("\n".join(f"- {item}" for item in items))
        if story.split_suggestion:
            render_html('<div class="kicker">✂️ Découpage suggéré</div>')
            st.info(story.split_suggestion, icon=":material/call_split:")
    with right:
        render_html(
            f'<div class="kicker">Critères d\'acceptation · {len(story.acceptance_criteria)} scénarios Gherkin</div>'
        )
        st.code(story.to_gherkin_feature(), language="gherkin", wrap_lines=True)
        st.download_button(
            "Télécharger le .feature",
            data=story.to_gherkin_feature(),
            file_name=f"{story.feature_id.lower()}.feature",
            mime="text/plain",
            icon=":material/download:",
            key=f"dl_feature_{story.feature_id}",
        )


def render_stories(
    result: PipelineResult, scored: list[ScoredFeature], settings: Settings, profile: Profile, demo_mode: bool
) -> None:
    """Story picker, story detail and on-demand generation."""
    by_id = {s.feature.id: s for s in scored}
    ordered = [s.feature.id for s in backlog_order(scored) if s.feature.id in result.stories]
    ordered += [fid for fid in result.stories if fid not in ordered]

    if ordered:
        choice = st.pills(
            "User stories (ordre du backlog)",
            options=ordered,
            default=ordered[0],
            required=True,
            key=f"story_pick_{st.session_state.run_id}",
            format_func=lambda fid: f"{fid} · {by_id[fid].moscow} · {by_id[fid].feature.title}",
        )
        with st.container(border=True):
            render_story(result.stories[choice], by_id[choice])
    else:
        st.info("Aucune user story générée pour l'instant.")

    missing = [s for s in scored if s.feature.id not in result.stories]
    if not missing:
        return
    st.markdown("#### Générer une story à la demande")
    pick_col, button_col = st.columns([3, 1], vertical_alignment="bottom")
    target_id = pick_col.selectbox(
        "Feature",
        options=[s.feature.id for s in missing],
        format_func=lambda fid: f"{fid} · {by_id[fid].moscow} · {by_id[fid].feature.title}",
    )
    disabled = demo_mode or not settings.has_api_key
    if button_col.button("Rédiger", icon=":material/edit_note:", width="stretch", disabled=disabled):
        try:
            budget_usd = check_quota(settings, profile, 0, 1)
        except QuotaBlocked:
            return
        pipeline = POAssistantPipeline(settings, budget_usd=budget_usd)
        started = time.perf_counter()
        with st.spinner(f"UserStoryWriter rédige {target_id}…"):
            try:
                story = pipeline.writer.run(by_id[target_id], result.context)
            except AgentError as exc:
                show_agent_error(exc)
                usage = pipeline.usage_report(time.perf_counter() - started)
                session.record_usage(settings, usage, kind="story", status="error", stories_count=1,
                                     error=exc.user_message)  # fmt: skip
                return
        usage = pipeline.usage_report(time.perf_counter() - started)
        session.record_usage(settings, usage, kind="story", status="success", stories_count=1)
        # `result` is a scored view; persist into the session's source of truth.
        st.session_state.result.stories[target_id] = story
        st.toast(f"Story {target_id} ajoutée au backlog", icon="📝")
        st.rerun()
    if disabled:
        st.caption("Disponible avec une clé API (hors mode démo).")


# ══════════════════════════════════════════════════════════════════════════
# Tab 5 · Export
# ══════════════════════════════════════════════════════════════════════════


def render_export(result: PipelineResult) -> None:
    """Download cards and run telemetry."""
    slug = result.context.product_name.lower().replace(" ", "-") or "backlog"
    exports = [
        (
            "🎫 Jira (CSV)",
            "Import natif Jira : summary, priorité, story points, labels, description + Gherkin.",
            to_jira_csv(result),
            f"{slug}-jira-import.csv",
            "text/csv",
        ),
        (
            "📄 Rapport Markdown",
            "Synthèse complète à coller dans Confluence ou Notion.",
            to_markdown(result),
            f"{slug}-backlog-report.md",
            "text/markdown",
        ),
        (
            "🥒 Gherkin (.feature)",
            "Toutes les stories au format BDD (Cucumber, Behave).",
            to_feature_files(result),
            f"{slug}-stories.feature",
            "text/plain",
        ),
        (
            "🧾 JSON typé",
            "Résultat brut validé par schéma, pour toute automatisation.",
            to_json(result),
            f"{slug}-result.json",
            "application/json",
        ),
    ]
    cols = st.columns(4)
    for col, (title, desc, data, filename, mime) in zip(cols, exports, strict=True):
        with col, st.container(border=True, height="stretch"):
            st.markdown(f"**{title}**")
            st.caption(desc)
            st.download_button(
                "Télécharger",
                data=data,
                file_name=filename,
                mime=mime,
                icon=":material/download:",
                width="stretch",
                key=f"dl_{filename}",
            )

    with st.expander("Comment importer dans Jira ?"):
        st.markdown(
            "1. **Jira › Paramètres › Système › Import externe › CSV**\n"
            "2. Chargez le fichier, encodage **UTF-8**\n"
            "3. Mappez *Summary*, *Issue Type*, *Priority*, *Labels*, *Description* et *Story Points* "
            "(ou *Story point estimate* selon votre projet)\n"
            "4. Les critères Gherkin arrivent dans la description, dans un bloc `noformat`."
        )

    st.markdown("#### Observabilité du run")
    usage = result.usage
    rows = [
        {
            "Agent": name,
            "Appels": u.calls,
            "Tokens in": u.input_tokens,
            "Tokens out": u.output_tokens,
            "Latence cumulée (s)": round(u.seconds, 1),
        }
        for name, u in usage.per_agent.items()
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    cost = f" · coût estimé ≈ {usage.estimated_cost_usd:.3f} USD" if usage.estimated_cost_usd is not None else ""
    st.caption(
        f"Modèle `{result.model}` · {usage.total_tokens:,} tokens · {usage.wall_clock_s:.1f} s de bout en bout{cost} "
        f"· généré le {result.generated_at}"
    )


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════


def empty_state(message: str) -> None:
    """Placeholder shown in result tabs before the first run."""
    with st.container(border=True):
        st.markdown(f"#### 🌱 {message}")
        st.caption("Chargez un exemple dans l'onglet **📥 Inbox** puis lancez les agents.")


def main() -> None:
    """Application entry point: auth gate, then the PO workspace (+ admin console)."""
    session.load_secrets_into_env()
    render_html(CSS)
    base_settings = get_settings()

    profile = session.current_profile()
    if profile is None:
        render_login(base_settings)
        return

    init_state()
    tabs = [*TABS, ADMIN_TAB] if profile.is_admin else TABS
    if st.session_state.get("nav") not in tabs:
        st.session_state.nav = TABS[0]
    settings, context, top_n, demo_mode = render_sidebar(base_settings, profile)

    result = current_result()
    render_hero(result)

    scored: list[ScoredFeature] = []
    modified: set[str] = set()
    view: PipelineResult | None = None
    if result is not None:
        scored, modified = effective_scoring(result)
        view = result.model_copy(update={"scored_features": scored})
        render_kpis(result, scored)

    containers = st.tabs(tabs, key="nav", on_change="rerun")
    inbox, analysis_tab, prio_tab, stories_tab, export_tab = containers[:5]
    with inbox:
        render_inbox(settings, profile, context, top_n, demo_mode)
    if profile.is_admin:
        with containers[5]:
            render_admin(settings, profile)

    if result is None or view is None:
        for tab, what in zip(
            (analysis_tab, prio_tab, stories_tab, export_tab),
            ("L'analyse", "Le scoring RICE", "Les user stories", "Les exports Jira"),
            strict=True,
        ):
            with tab:
                empty_state(f"{what} apparaîtr{'ont' if what.startswith('Les') else 'a'} ici.")
        return
    with analysis_tab:
        render_analysis(result)
    with prio_tab:
        render_prioritization(result, scored, modified)
    with stories_tab:
        render_stories(view, scored, settings, profile, demo_mode)
    with export_tab:
        render_export(view)


main()
