"""Admin console: SQL usage analytics, ML cost models and per-user quotas.

Visible only to profiles with ``role = 'admin'`` — and even if the tab were
exposed by mistake, Row Level Security would return only the caller's own
rows: the database is the real gatekeeper, not the UI.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import analytics as sql
from config import Settings
from governance import CostEstimator, Quota, consumption_from_runs, forecast_spend
from store import Profile, StoreError
from ui import session
from ui.runs import render_runs
from ui.style import (
    ACCENT,
    AGENT_COLORS,
    CHART_TEXT,
    CONSOLE_BILLING_URL,
    SERIES,
    STATUS,
    dollars,
    euros,
    render_html,
)

_CACHE_TTL_S = 120
_ROLES = ["member", "admin"]


# ══════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════


def _invalidate() -> None:
    st.session_state.pop("_admin_cache", None)


def _load(days: int) -> tuple[pd.DataFrame, pd.DataFrame, list[Profile]]:
    """Usage + profiles, cached per session for two minutes."""
    cache = st.session_state.get("_admin_cache")
    if cache and cache[0] == days and time.monotonic() - cache[1] < _CACHE_TTL_S:
        return cache[2]
    repo = session.repository()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    runs, agents = repo.fetch_usage(since)
    data = (runs, agents, repo.list_profiles())
    st.session_state["_admin_cache"] = (days, time.monotonic(), data)
    return data


def _profiles_frame(profiles: list[Profile]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": p.id,
                "email": p.email,
                "role": p.role,
                "max_eur_per_request": p.quota.max_eur_per_request,
                "daily_eur_limit": p.quota.daily_eur,
                "weekly_eur_limit": p.quota.weekly_eur,
                "monthly_eur_limit": p.quota.monthly_eur,
            }
            for p in profiles
        ],
        columns=["id", "email", "role", "max_eur_per_request", "daily_eur_limit", "weekly_eur_limit",
                 "monthly_eur_limit"],
    ).astype({"max_eur_per_request": float, "daily_eur_limit": float, "weekly_eur_limit": float,
              "monthly_eur_limit": float})  # fmt: skip


def _show_sql(query: sql.Query, tz: str) -> None:
    with st.expander("Voir la requête SQL"):
        st.code(sql.render_sql(query, tz), language="sql")


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════


def render_admin(settings: Settings, me: Profile) -> None:
    """Render the whole admin console."""
    render_html(
        '<div class="admin-hero"><div class="eyebrow">Administration</div><h2>Console d\'administration</h2>'
        "<p>Consommation Claude en euros, prévisions de coûts et quotas par utilisateur.</p></div>"
    )

    days = st.segmented_control(
        "Période", [30, 60, 90], default=60, required=True, format_func=lambda d: f"{d} jours", key="adm_days"
    )

    try:
        runs, agents, profiles = _load(int(days))
    except StoreError as exc:
        st.error(exc.user_message)
        return

    # Real usage only. Rows flagged `is_synthetic` (from a data generator since
    # removed) are ignored everywhere, like they always were for quotas.
    runs = runs[~runs["is_synthetic"]]
    agents = agents[agents["run_id"].isin(runs["id"])]
    profiles_df = _profiles_frame(profiles)

    if runs.empty:
        st.info("Aucun usage enregistré sur la période. Lancez une analyse depuis l'Inbox : elle apparaîtra ici.")

    usage_tab, runs_tab, agents_tab, ml_tab, quota_tab = st.tabs(
        ["Usage et coûts", "Runs", "Agents", "Prévisions", "Quotas"]
    )
    with usage_tab:
        _usage_section(settings, runs, agents, profiles_df)
    with runs_tab:
        render_runs(settings, runs)
    with agents_tab:
        _agents_section(settings, runs)
    with ml_tab:
        _ml_section(settings, runs, agents, profiles_df, profiles)
    with quota_tab:
        _quota_section(settings, me, profiles, runs)


# ══════════════════════════════════════════════════════════════════════════
# Usage & costs
# ══════════════════════════════════════════════════════════════════════════


def _credit_block(settings: Settings) -> None:
    """Estimated Anthropic credit left, from the app's own usage log."""
    credit = session.credit_status(settings)
    if credit is None:
        st.info(
            "Pour suivre le crédit Anthropic restant, ajoutez dans les secrets le montant chargé sur la Console, "
            'par exemple `ANTHROPIC_CREDITS_USD = "10"`. '
            f"Le solde exact reste consultable dans la [Console Claude › Facturation]({CONSOLE_BILLING_URL})."
        )
        return
    width = f"{credit.ratio_left * 100:.0f}%"
    render_html(
        '<div class="credit"><div class="row">'
        f'<div><div class="lbl">Crédit Anthropic restant (estimé)</div><div class="big">{dollars(credit.remaining_usd)}</div></div>'
        f'<div><div class="lbl">Chargé</div><div class="val">{dollars(credit.loaded_usd)}</div></div>'
        f'<div><div class="lbl">Consommé via l\'app</div><div class="val">{dollars(credit.spent_usd, digits=3)}</div></div>'
        "</div>"
        f'<div class="bar" style="margin-top:14px"><span style="width:{width};background:{ACCENT}"></span></div>'
        '<div class="muted" style="margin-top:10px">Estimation calculée à partir des tokens de chaque run réel. '
        f'Solde exact : <a href="{CONSOLE_BILLING_URL}" target="_blank">Console Claude › Facturation</a>.</div>'
        "</div>"
    )  # fmt: skip


def _usage_section(settings: Settings, runs: pd.DataFrame, agents: pd.DataFrame, profiles_df: pd.DataFrame) -> None:
    tz = settings.timezone
    kpi = sql.run(sql.KPIS, runs=runs, agents=agents, profiles=profiles_df, tz=tz).iloc[0]
    daily = sql.run(sql.DAILY_TOKENS, runs=runs, agents=agents, profiles=profiles_df, tz=tz)
    today = datetime.now(ZoneInfo(tz)).date()
    forecast = forecast_spend(daily[["day", "cost_eur"]] if not daily.empty else daily, today)

    _credit_block(settings)
    cols = [*st.columns(3), *st.columns(3)]
    cols[0].metric("Dépense du mois", euros(float(kpi["spend_eur"])), border=True)
    cols[1].metric(
        "Projection fin de mois", euros(forecast.month_end_projection_eur), border=True,
        help="Tendance linéaire sur 28 jours (onglet Prévisions ML).",
    )  # fmt: skip
    cols[2].metric("Runs réussis", int(kpi["successful_runs"]), border=True)
    cols[3].metric("Utilisateurs actifs", int(kpi["active_users"]), border=True)
    cols[4].metric("Coût moyen / run", euros(float(kpi["avg_run_eur"]), digits=3), border=True)
    cols[5].metric("Runs bloqués (quota)", int(kpi["blocked_runs"]), border=True)
    _show_sql(sql.KPIS, tz)

    with st.container(border=True):
        st.markdown("**Dépense quotidienne par agent (€)**")
        by_agent = sql.run(sql.DAILY_BY_AGENT, runs=runs, agents=agents, profiles=profiles_df, tz=tz)
        if by_agent.empty:
            st.caption("Pas de données.")
        else:
            chart = (
                alt.Chart(by_agent)
                .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b")),
                    y=alt.Y("sum(cost_eur):Q", title="€", stack="zero"),
                    color=alt.Color(
                        "agent:N",
                        title=None,
                        legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=list(AGENT_COLORS), range=list(AGENT_COLORS.values())),
                    ),  # fmt: skip
                    tooltip=[
                        alt.Tooltip("day:T", format="%d/%m/%Y"),
                        "agent:N",
                        alt.Tooltip("cost_eur:Q", format=".3f"),
                    ],
                )
                .properties(height=260)
            )
            st.altair_chart(chart, width="stretch")
        _show_sql(sql.DAILY_BY_AGENT, tz)

    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown("**Tokens consommés par jour**")
        if daily.empty:
            st.caption("Pas de données.")
        else:
            tokens = daily.melt(id_vars="day", value_vars=["input_tokens", "output_tokens"], var_name="type")
            tokens["type"] = tokens["type"].map({"input_tokens": "Entrée", "output_tokens": "Sortie"})
            chart = (
                alt.Chart(tokens)
                .mark_area(opacity=0.75, interpolate="monotone")
                .encode(
                    x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b")),
                    y=alt.Y("value:Q", title="tokens", stack="zero", axis=alt.Axis(format="~s")),
                    color=alt.Color(
                        "type:N",
                        title=None,
                        legend=alt.Legend(orient="top"),
                        scale=alt.Scale(range=[SERIES[0], SERIES[1]]),
                    ),
                    tooltip=[alt.Tooltip("day:T", format="%d/%m/%Y"), "type:N", alt.Tooltip("value:Q", format=",")],
                )  # fmt: skip
                .properties(height=250)
            )
            st.altair_chart(chart, width="stretch")
        _show_sql(sql.DAILY_TOKENS, tz)
    with right, st.container(border=True):
        st.markdown("**Consommation par utilisateur (mois en cours)**")
        by_user = sql.run(sql.BY_USER, runs=runs, agents=agents, profiles=profiles_df, tz=tz)
        if by_user.empty:
            st.caption("Pas de données.")
        else:
            by_user["quota_used"] = by_user["quota_used"].astype(float)
            chart = (
                alt.Chart(by_user)
                .mark_bar(cornerRadiusEnd=5)
                .encode(
                    y=alt.Y("email:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)),
                    x=alt.X("spend_eur:Q", title="€ ce mois-ci"),
                    # No monthly limit (admins) → neutral grey instead of an invisible bar.
                    color=alt.condition(
                        "isValid(datum.quota_used)",
                        alt.Color(
                            "quota_used:Q",
                            title="% quota mensuel",
                            scale=alt.Scale(
                                domain=[0, 0.7, 0.9],
                                range=[STATUS["good"], STATUS["warning"], STATUS["critical"]],
                                clamp=True,
                            ),
                            legend=alt.Legend(format="%", orient="top"),
                        ),
                        alt.value(STATUS["neutral"]),
                    ),
                    tooltip=[
                        "email:N",
                        "role:N",
                        "runs:Q",
                        alt.Tooltip("spend_eur:Q", format=".2f"),
                        alt.Tooltip("quota_used:Q", format=".0%"),
                        "blocked:Q",
                    ],
                )  # fmt: skip
                .properties(height=alt.Step(30))
            )
            st.altair_chart(chart, width="stretch")
        _show_sql(sql.BY_USER, tz)


# ══════════════════════════════════════════════════════════════════════════
# Agents — process visualisation and per-run journal
# ══════════════════════════════════════════════════════════════════════════

_STATUS_FR = {"success": "succès", "retry": "corrigé ensuite", "error": "échec", "blocked": "bloqué"}
_AGENT_ORDER = ["FeedbackAnalyst", "PrioritizationStrategist", "UserStoryWriter"]


def _run_label(row: pd.Series, tz: str) -> str:
    when = row["created_at"].tz_convert(tz).strftime("%d/%m %H:%M")
    kind = "pipeline complet" if row["kind"] == "pipeline" else "story à la demande"
    return (
        f"{when} · {row['email']} · {kind} · {_STATUS_FR.get(row['status'], row['status'])} · "
        f"{euros(float(row['cost_eur']), digits=3)}"
    )


def _agents_section(settings: Settings, runs: pd.DataFrame) -> None:
    tz = settings.timezone
    st.markdown("#### Journal des agents")
    st.caption(
        "Chaque lancement enchaîne les agents : FeedbackAnalyst, puis PrioritizationStrategist, puis les "
        "UserStoryWriter en parallèle. Chaque ligne du journal est une requête envoyée à Claude, avec sa durée, "
        "ses tokens et la **réflexion résumée** renvoyée par l'API (jamais le raisonnement brut)."
    )
    candidates = runs[runs["status"] != "blocked"].sort_values("created_at", ascending=False).head(60)
    if candidates.empty:
        st.info("Aucun lancement sur la période. Les runs en direct apparaîtront ici avec leur journal complet.")
        return
    labels = {row["id"]: _run_label(row, tz) for _, row in candidates.iterrows()}
    run_id = st.selectbox("Lancement", list(labels), format_func=labels.get, key="adm_run_pick")
    run = candidates[candidates["id"] == run_id].iloc[0]
    try:
        calls = session.repository().fetch_calls([run_id])
    except StoreError as exc:
        st.error(exc.user_message)
        return

    cols = st.columns(5)
    cols[0].metric("Utilisateur", run["email"].split("@")[0], border=True)
    cols[1].metric("Durée totale", f"{float(run['duration_s']):.1f} s", border=True)
    cols[2].metric("Requêtes", len(calls), border=True)
    cols[3].metric("Tokens", f"{int(run['input_tokens'] + run['output_tokens']):,}".replace(",", " "), border=True)
    cols[4].metric("Coût", euros(float(run["cost_eur"]), digits=3), border=True)
    if calls.empty:
        st.info(
            "Pas de journal détaillé pour ce lancement : il date d'avant l'activation du journal, "
            "ou il s'est arrêté avant le premier appel."
        )
        return

    _process_flow(calls)
    _timeline(calls, tz)

    table = pd.DataFrame(
        {
            "#": calls["seq"].astype(int),
            "Agent": calls["agent"],
            "Début": calls["started_at"].dt.tz_convert(tz).dt.strftime("%H:%M:%S"),
            "Durée (s)": calls["duration_s"].round(1),
            "Tentative": calls["attempt"].astype(int),
            "Statut": calls["status"].map(_STATUS_FR).fillna(calls["status"]),
            "Fin (API)": calls["stop_reason"].fillna("—"),
            "Tokens entrée": calls["input_tokens"].astype(int),
            "Tokens sortie": calls["output_tokens"].astype(int),
        }
    )
    st.dataframe(table, hide_index=True, width="stretch")

    st.markdown("**Détail par requête**")
    for _, call in calls.iterrows():
        title = (
            f"#{int(call['seq'])} · {call['agent']} · tentative {int(call['attempt'])} · "
            f"{float(call['duration_s']):.1f} s · {_STATUS_FR.get(call['status'], call['status'])}"
        )
        with st.expander(title):
            left, right = st.columns([1.1, 1], gap="large")
            with left:
                render_html('<div class="kicker" style="margin-top:0">Réflexion (résumé fourni par Claude)</div>')
                st.markdown(call["thinking"] or "_Aucune réflexion renvoyée pour cette requête._")
            with right:
                render_html('<div class="kicker" style="margin-top:0">Sortie (extrait du JSON)</div>')
                st.code(call["output_excerpt"] or "—", language="json", wrap_lines=True, height=260)
                if call["error"]:
                    st.warning(f"Motif : {call['error']}")

    with st.expander("Latence par agent sur la période"):
        _latency_by_agent(runs)


def _process_flow(calls: pd.DataFrame) -> None:
    """The three agents as a left-to-right flow with their call counts, time and tokens."""
    cells = []
    for i, name in enumerate(_AGENT_ORDER, start=1):
        part = calls[calls["agent"] == name]
        if part.empty:
            continue
        span = (part["started_at"].max() - part["started_at"].min()).total_seconds() + float(
            part.loc[part["started_at"].idxmax(), "duration_s"]
        )
        parallel = " en parallèle" if len(part) > 1 and name == "UserStoryWriter" else ""
        tokens = int(part["input_tokens"].sum() + part["output_tokens"].sum())
        cells.append(
            f'<div class="step" style="border-top-color:{AGENT_COLORS[name]}"><div class="n">0{i} — {name}</div>'
            f'<div class="t">{len(part)} requête{"s" if len(part) > 1 else ""}{parallel}</div>'
            f'<div class="d">{span:.1f} s · {tokens:,} tokens</div></div>'.replace(",", " ")
        )
    render_html(
        '<div class="steps" style="margin: 8px 0 14px; color: inherit">'
        + "".join(cells).replace('class="n"', 'class="n" style="color:inherit;opacity:.65"')
        + "</div>"
    )


def _timeline(calls: pd.DataFrame, tz: str) -> None:
    """Gantt-style timeline of the requests of one run."""
    origin = calls["started_at"].min()
    data = calls.assign(
        start=(calls["started_at"] - origin).dt.total_seconds(),
        label=calls.apply(lambda c: f"#{int(c['seq'])} {c['agent']}", axis=1),
        status_fr=calls["status"].map(_STATUS_FR).fillna(calls["status"]),
    )
    data["end"] = data["start"] + data["duration_s"]
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadius=3, height=16)
        .encode(
            x=alt.X("start:Q", title="Secondes depuis le lancement"),
            x2="end:Q",
            y=alt.Y("label:N", sort=list(data["label"]), title=None, axis=alt.Axis(labelLimit=220)),
            color=alt.Color(
                "agent:N",
                title=None,
                scale=alt.Scale(domain=_AGENT_ORDER, range=[AGENT_COLORS[a] for a in _AGENT_ORDER]),
                legend=alt.Legend(orient="top"),
            ),
            opacity=alt.condition("datum.status === 'success'", alt.value(1.0), alt.value(0.45)),
            tooltip=[
                alt.Tooltip("label:N", title="Requête"),
                alt.Tooltip("duration_s:Q", title="Durée (s)", format=".1f"),
                alt.Tooltip("input_tokens:Q", title="Tokens entrée", format=","),
                alt.Tooltip("output_tokens:Q", title="Tokens sortie", format=","),
                alt.Tooltip("status_fr:N", title="Statut"),
            ],
        )
        .properties(height=alt.Step(30))
    )
    with st.container(border=True):
        st.markdown("**Chronologie du lancement**")
        st.altair_chart(chart, width="stretch")
        st.caption("Barres pâles : réponse rejetée par la validation puis corrigée, ou échec.")


def _latency_by_agent(runs: pd.DataFrame) -> None:
    ids = runs.loc[runs["status"] != "blocked", "id"].tolist()[-400:]
    try:
        calls = session.repository().fetch_calls(ids)
    except StoreError as exc:
        st.error(exc.user_message)
        return
    if calls.empty:
        st.caption("Pas encore de journal sur la période.")
        return
    stats = (
        calls.groupby("agent")["duration_s"]
        .agg(requêtes="count", p50=lambda x: x.quantile(0.5), p95=lambda x: x.quantile(0.95))
        .reindex([a for a in _AGENT_ORDER if a in set(calls["agent"])])
        .reset_index()
    )
    stats["tokens moyens"] = (
        calls.assign(t=calls["input_tokens"] + calls["output_tokens"])
        .groupby("agent")["t"]
        .mean()
        .reindex(stats["agent"])
        .values
    )
    st.dataframe(
        stats.round({"p50": 1, "p95": 1, "tokens moyens": 0}),
        hide_index=True,
        width="stretch",
        column_config={
            "agent": "Agent",
            "p50": st.column_config.NumberColumn("Médiane (s)", format="%.1f"),
            "p95": st.column_config.NumberColumn("95e centile (s)", format="%.1f"),
            "tokens moyens": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.caption(
        "Les UserStoryWriter tournant en parallèle, la durée d'un lancement ≈ analyste + stratège + la plus lente des stories."
    )


# ══════════════════════════════════════════════════════════════════════════
# ML
# ══════════════════════════════════════════════════════════════════════════


def _ml_section(
    settings: Settings, runs: pd.DataFrame, agents: pd.DataFrame, profiles_df: pd.DataFrame, profiles: list[Profile]
) -> None:
    tz = settings.timezone
    drivers = sql.run(sql.COST_DRIVERS, runs=runs, agents=agents, profiles=profiles_df, tz=tz)
    training = drivers.assign(status="success", kind="pipeline")
    model = CostEstimator().fit(training)
    report = model.report

    st.markdown("#### 1 · Prédire le coût d'un run *avant* de le lancer")
    st.caption(
        "Régression linéaire (moindres carrés ordinaires) sur les runs réussis : le coût est piloté par les tokens "
        "lus (taille de l'input) et écrits (nombre de stories). Utilisée pour bloquer un run qui dépasserait un "
        "quota **avant** de dépenser le moindre centime."
    )
    b0, b1, b2 = report.coefficients
    left, right = st.columns([1.35, 1], gap="large")
    with left, st.container(border=True):
        m1, m2, m3 = st.columns(3)
        m1.metric("Runs d'entraînement", report.n)
        m2.metric("R²", f"{report.r2:.2f}".replace(".", ",") if report.r2 is not None else "—")
        m3.metric("Erreur moy. (MAE)", euros(report.mae_eur, digits=3) if report.mae_eur is not None else "—")
        render_html(
            f'<span class="formula">coût = <em>{b0:.3f}</em> € + <em>{b1:.4f}</em> €·kcar '
            f"× taille + <em>{b2:.3f}</em> € × stories</span>"
        )
        if report.source == "prior":
            st.caption(
                f"Moins de 8 runs réussis : estimation *a priori* (calibrée sur le run de référence). n={report.n}"
            )
        elif not drivers.empty:
            drivers["predicted"] = model.predict_frame(drivers)
            limit = float(max(drivers["cost_eur"].max(), drivers["predicted"].max()) * 1.05)
            points = (
                alt.Chart(drivers)
                .mark_circle(size=64, opacity=0.75, color=ACCENT, stroke="#FFFFFF", strokeWidth=0.8)
                .encode(
                    x=alt.X("predicted:Q", title="Coût prédit (€)", scale=alt.Scale(domain=[0, limit])),
                    y=alt.Y("cost_eur:Q", title="Coût réel (€)", scale=alt.Scale(domain=[0, limit])),
                    tooltip=[
                        "email:N",
                        alt.Tooltip("input_chars:Q", format=","),
                        "stories_count:Q",
                        alt.Tooltip("cost_eur:Q", format=".3f"),
                        alt.Tooltip("predicted:Q", format=".3f"),
                    ],
                )  # fmt: skip
            )
            diagonal = (
                alt.Chart(pd.DataFrame({"x": [0, limit], "y": [0, limit]}))
                .mark_line(strokeDash=[5, 4], color=CHART_TEXT)
                .encode(x="x:Q", y="y:Q")
            )
            st.altair_chart((diagonal + points).properties(height=280), width="stretch")
        _show_sql(sql.COST_DRIVERS, tz)
    with right, st.container(border=True):
        st.markdown("**Simulateur**")
        chars = st.slider("Taille des feedbacks (caractères)", 1_000, 30_000, 6_000, step=500, key="sim_chars")
        stories = st.slider("User stories générées", 1, 6, 3, key="sim_stories")
        estimate = model.predict(chars, stories)
        s1, s2 = st.columns(2)
        s1.metric("Coût estimé", euros(estimate.point_eur, digits=3))
        s2.metric("Borne haute (P90)", euros(estimate.upper_eur, digits=3))
        member_limits = [
            p.quota.max_eur_per_request for p in profiles if not p.is_admin and p.quota.max_eur_per_request
        ]
        if member_limits:
            limit = min(member_limits)
            verdict = "le run passe" if estimate.point_eur <= limit else "le run serait bloqué"
            st.caption(f"Avec la limite par requête la plus stricte ({euros(limit)}) : {verdict}.")

    st.markdown("#### 2 · Anticiper la facture du mois")
    daily = sql.run(sql.DAILY_TOKENS, runs=runs, agents=agents, profiles=profiles_df, tz=tz)
    today = datetime.now(ZoneInfo(tz)).date()
    forecast = forecast_spend(daily[["day", "cost_eur"]] if not daily.empty else daily, today)
    budget = sum(p.quota.monthly_eur or 0.0 for p in profiles if not p.is_admin)
    f1, f2 = st.columns(2)
    f3, f4 = st.columns(2)
    f1.metric("Dépensé ce mois", euros(forecast.month_to_date_eur), border=True)
    f2.metric("Projection fin de mois", euros(forecast.month_end_projection_eur), border=True)
    f3.metric("Évolution sur 30 j", f"{forecast.slope_eur_per_day * 30:+.2f} € / jour".replace(".", ","), border=True,
              help="De combien la dépense quotidienne évolue en 30 jours (pente de la régression × 30).")  # fmt: skip
    f4.metric("Plafond cumulé des membres", euros(budget), border=True,
              help="Somme des quotas mensuels des profils non-admin : exposition maximale.")  # fmt: skip
    with st.container(border=True):
        _forecast_chart(forecast.frame, today)
        st.caption("Tendance linéaire sur les 28 derniers jours, bande de prédiction à 80 % (±1,28 σ des résidus).")


def _forecast_chart(frame: pd.DataFrame, today: date) -> None:
    data = frame.copy()
    data["day"] = pd.to_datetime(data["day"])
    band = (
        alt.Chart(data)
        .mark_area(opacity=0.18, color=ACCENT)
        .encode(
            x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b")),
            y=alt.Y("lower:Q", title="€ / jour"),
            y2="upper:Q",
        )
    )
    bars = (
        alt.Chart(data[~data["is_forecast"]])
        .mark_bar(color=STATUS["neutral"], opacity=0.55, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x="day:T",
            y="actual:Q",
            tooltip=[alt.Tooltip("day:T", format="%d/%m"), alt.Tooltip("actual:Q", format=".2f")],
        )
    )
    fitted = (
        alt.Chart(data[~data["is_forecast"]]).mark_line(color=ACCENT, strokeWidth=2).encode(x="day:T", y="fitted:Q")
    )
    projected = (
        alt.Chart(data[data["is_forecast"]])
        .mark_line(color=ACCENT, strokeWidth=2, strokeDash=[6, 4])
        .encode(
            x="day:T",
            y="fitted:Q",
            tooltip=[alt.Tooltip("day:T", format="%d/%m"), alt.Tooltip("fitted:Q", format=".2f")],
        )
    )
    now_rule = (
        alt.Chart(pd.DataFrame({"day": [pd.Timestamp(today)]}))
        .mark_rule(color=CHART_TEXT, strokeDash=[2, 3])
        .encode(x="day:T")
    )
    st.altair_chart((band + bars + fitted + projected + now_rule).properties(height=260), width="stretch")


# ══════════════════════════════════════════════════════════════════════════
# Quotas
# ══════════════════════════════════════════════════════════════════════════

_QUOTA_COLUMNS = {
    "max_eur_per_request": "€ / requête",
    "daily_eur": "€ / jour",
    "weekly_eur": "€ / semaine",
    "monthly_eur": "€ / mois",
}


def _quota_section(settings: Settings, me: Profile, profiles: list[Profile], runs: pd.DataFrame) -> None:
    st.markdown("#### Limites de consommation par utilisateur")
    st.caption(
        "Vide = illimité. La limite **par requête** est comparée au coût *estimé* avant le lancement, puis appliquée "
        "comme plafond dur pendant l'exécution. Les limites **jour / semaine / mois** portent sur les runs réels "
        "(hors données synthétiques), en calendrier " + settings.timezone + "."
    )
    now = datetime.now(timezone.utc)
    real = runs[~runs["is_synthetic"]] if not runs.empty else runs
    rows = []
    for p in profiles:
        mine = real[real["user_id"] == p.id] if not real.empty else real
        used = consumption_from_runs(
            zip(mine["created_at"].dt.to_pydatetime(), mine["cost_eur"], strict=True) if not mine.empty else [],
            now, settings.timezone,
        )  # fmt: skip
        rows.append(
            {
                "id": p.id,
                "Email": p.email,
                "Rôle": p.role,
                **{label: getattr(p.quota, field) for field, label in _QUOTA_COLUMNS.items()},
                "Conso jour": used.day_eur,
                "Conso semaine": used.week_eur,
                "Conso mois": used.month_eur,
            }
        )
    original = pd.DataFrame(rows)
    money = st.column_config.NumberColumn(min_value=0.0, max_value=10_000.0, step=0.1, format="%.2f €")
    spent = st.column_config.NumberColumn(format="%.2f €", disabled=True)
    edited = st.data_editor(
        original,
        key="adm_quota_editor",
        hide_index=True,
        placeholder="∞",
        width="stretch",
        column_order=["Email", "Rôle", *_QUOTA_COLUMNS.values(), "Conso jour", "Conso semaine", "Conso mois"],
        disabled=["Email", "Conso jour", "Conso semaine", "Conso mois"],
        column_config={
            "Rôle": st.column_config.SelectboxColumn(options=_ROLES, required=True),
            **{label: money for label in _QUOTA_COLUMNS.values()},
            "Conso jour": spent,
            "Conso semaine": spent,
            "Conso mois": spent,
        },
    )

    changes = []
    for (_, before), (_, after) in zip(original.iterrows(), edited.iterrows(), strict=True):
        fields = ["Rôle", *_QUOTA_COLUMNS.values()]
        if any(not _same(before[f], after[f]) for f in fields):
            changes.append(after)

    left, right = st.columns([1, 3], vertical_alignment="center")
    save = left.button(f"Enregistrer ({len(changes)})", type="primary", disabled=not changes, width="stretch")
    right.caption("Les modifications s'appliquent dès le prochain run des utilisateurs concernés.")
    if not save:
        return
    for row in changes:
        if row["id"] == me.id and row["Rôle"] != "admin":
            st.error("Vous ne pouvez pas retirer votre propre rôle admin (risque de verrouillage).")
            return
    repo = session.repository()
    try:
        for row in changes:
            quota = Quota(**{field: _num(row[label]) for field, label in _QUOTA_COLUMNS.items()})
            repo.update_profile(row["id"], row["Rôle"], quota)
    except StoreError as exc:
        st.error(exc.user_message)
        return
    _invalidate()
    st.session_state.pop("adm_quota_editor", None)
    session.refresh_profile()
    st.toast(f"{len(changes)} profil(s) mis à jour")
    st.rerun()


def _num(value: object) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return round(float(value), 4)


def _same(a: object, b: object) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return _num(a) == _num(b)
