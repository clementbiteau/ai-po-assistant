"""Admin "Runs" tab: every run with its configuration, latency, cost and ranking.

The point is to defend model choices with evidence: pick two runs of the same
case, see what changed in latency and cost, and whether the prioritisation
held. The pure helpers (critical path, ranking match, verdict) carry no
Streamlit code, so they are unit-tested.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from agents import PipelineResult
from config import AGENT_KEYS, MODELS, Settings
from store import StoreError
from ui import session
from ui.style import AGENT_COLORS, render_html

EFFORT_FR = {"low": "faible", "medium": "moyen", "high": "élevé", "xhigh": "très élevé", "max": "max"}
AGENT_FR = {"analyst": "Analyste", "strategist": "Stratège", "writer": "Rédacteur"}
_AGENT_NAMES = {"analyst": "FeedbackAnalyst", "strategist": "PrioritizationStrategist", "writer": "UserStoryWriter"}
_STAGES = ["Analyste", "Stratège", "Stories"]


# ══════════════════════════════════════════════════════════════════════════
# Pure helpers
# ══════════════════════════════════════════════════════════════════════════


def model_label(model: str) -> str:
    """Short display name of a model id."""
    return MODELS[model].label if model in MODELS else model


def config_summary(config: dict[str, dict[str, str]] | None) -> str:
    """One line per run: ``Sonnet 5 (moyen) · Sonnet 5 (élevé) · Haiku 4.5 (moyen)``."""
    if not config:
        return "—"
    parts = []
    for agent in AGENT_KEYS:
        c = config.get(agent) or {}
        parts.append(f"{model_label(c.get('model', '?'))} ({EFFORT_FR.get(c.get('effort', ''), c.get('effort', '?'))})")
    return " · ".join(parts)


def critical_path(calls: pd.DataFrame) -> pd.DataFrame:
    """Per run: seconds spent by stage on the critical path, and corrections.

    The analyst and the strategist run one after the other (their retries
    included); the story writers run in parallel, so only the slowest counts.
    """
    columns = ["run_id", *_STAGES, "Corrections"]
    if calls.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for run_id, part in calls.groupby("run_id"):

        def seconds(agent: str, how: str, part: pd.DataFrame = part) -> float:
            durations = part.loc[part["agent"] == _AGENT_NAMES[agent], "duration_s"]
            return float(getattr(durations, how)()) if not durations.empty else 0.0

        rows.append(
            {
                "run_id": run_id,
                "Analyste": seconds("analyst", "sum"),
                "Stratège": seconds("strategist", "sum"),
                "Stories": seconds("writer", "max"),
                "Corrections": int((part["attempt"] > 1).sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _num(value: Any) -> float:
    """``value`` as a float, 0 when missing (runs recorded before the journal)."""
    return 0.0 if value is None or pd.isna(value) else float(value)


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"\w+", title.casefold()) if len(w) > 2}


def _similarity(a: str, b: str) -> float:
    """Title similarity: characters in common, or the short title's words all found in the long one."""
    ratio = SequenceMatcher(None, a.casefold(), b.casefold()).ratio()
    wa, wb = _words(a), _words(b)
    containment = len(wa & wb) / min(len(wa), len(wb)) if wa and wb else 0.0
    return max(ratio, containment)


def match_rankings(a: list[dict[str, Any]], b: list[dict[str, Any]], threshold: float = 0.5) -> list[dict[str, Any]]:
    """Pair the features of two runs by title (ids can differ between runs).

    Greedy best-first matching on title similarity; features left without a
    match appear on one side only. Rows follow run A's ranking, then B's
    unmatched features.
    """
    pairs = sorted(
        ((_similarity(fa["title"], fb["title"]), i, j) for i, fa in enumerate(a) for j, fb in enumerate(b)),
        reverse=True,
    )
    match_a: dict[int, int] = {}
    used_b: set[int] = set()
    for score, i, j in pairs:
        if score < threshold:
            break
        if i not in match_a and j not in used_b:
            match_a[i] = j
            used_b.add(j)
    rows = []
    for i, fa in enumerate(a):
        fb = b[match_a[i]] if i in match_a else None
        rows.append({"a": fa, "b": fb})
    rows.extend({"a": None, "b": fb} for j, fb in enumerate(b) if j not in used_b)
    return rows


def ranking_verdict(a: list[dict[str, Any]], b: list[dict[str, Any]], top: int = 3) -> str:
    """Plain-language verdict on whether the top of the ranking held between two runs."""
    if not a or not b:
        return "Classement non comparable : un des runs n'a pas de classement enregistré."
    rows = match_rankings(a, b)
    top_a = [r for r in rows if r["a"] and r["a"]["rank"] <= top]
    same_members = all(r["b"] and r["b"]["rank"] <= top for r in top_a) and len(top_a) == min(top, len(a))
    if same_members and all(r["a"]["rank"] == r["b"]["rank"] for r in top_a):
        return f"Même top {top}, dans le même ordre."
    if same_members:
        return f"Même top {top}, mais dans un ordre différent."
    left = [r["a"]["title"] for r in top_a if not (r["b"] and r["b"]["rank"] <= top)]
    entered = [
        r["b"]["title"] for r in rows if r["b"] and r["b"]["rank"] <= top and not (r["a"] and r["a"]["rank"] <= top)
    ]
    return f"Le top {top} change : sort « {', '.join(left)} », entre « {', '.join(entered) or '—'} »."


# ══════════════════════════════════════════════════════════════════════════
# Tab
# ══════════════════════════════════════════════════════════════════════════


def render_runs(settings: Settings, runs: pd.DataFrame) -> None:
    """List runs with their configuration; compare two; reopen a stored result."""
    st.markdown("#### Runs et choix des modèles")
    st.caption(
        "Chaque analyse complète est enregistrée avec sa configuration (modèle et effort de chaque agent), "
        "sa latence, son coût et son classement. Sélectionnez **deux runs du même cas** pour comparer : "
        "c'est la preuve d'un choix de modèle. Les modèles se règlent dans la barre latérale (réservé à l'admin)."
    )
    candidates = (
        runs[(runs["kind"] == "pipeline") & (runs["status"] != "blocked") & (~runs["is_synthetic"])]
        .sort_values("created_at", ascending=False)
        .head(50)
    )
    if candidates.empty:
        st.info("Aucune analyse réelle sur la période. Lancez-en une depuis l'Inbox : elle apparaîtra ici.")
        return
    ids = candidates["id"].tolist()
    try:
        repo = session.repository()
        details = repo.fetch_details(ids).set_index("run_id")
        path = critical_path(repo.fetch_calls(ids)).set_index("run_id")
    except StoreError as exc:
        st.error(exc.user_message)
        return

    table = _runs_table(candidates, details, path, settings.timezone)
    event = st.dataframe(
        table.drop(columns=["id"]),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row",
        key="adm_runs_table",
        column_config={
            "Durée (s)": st.column_config.NumberColumn(format="%.1f"),
            "Analyste (s)": st.column_config.NumberColumn(format="%.1f"),
            "Stratège (s)": st.column_config.NumberColumn(format="%.1f"),
            "Stories (s)": st.column_config.NumberColumn(
                format="%.1f", help="La plus lente, elles tournent en parallèle."
            ),
            "Coût (€)": st.column_config.NumberColumn(format="%.3f"),
        },
    )
    if not event.selection.rows:
        st.caption("Cochez une ligne pour la rouvrir, ou deux pour les comparer.")
        return
    # The table is newest first: reversed row order puts the oldest run first (A).
    chosen = table.iloc[sorted(event.selection.rows, reverse=True)]
    if len(chosen) == 1:
        _reopen_button(chosen.iloc[0], details)
        return
    _compare(chosen.head(2), details)
    if len(chosen) > 2:
        st.caption("Comparaison limitée aux deux runs les plus anciens de la sélection.")


def _runs_table(candidates: pd.DataFrame, details: pd.DataFrame, path: pd.DataFrame, tz: str) -> pd.DataFrame:
    def detail(run_id: str, column: str) -> Any:
        return details.at[run_id, column] if run_id in details.index else None

    def top3(run_id: str) -> str:
        ranking = detail(run_id, "ranking") or []
        return " > ".join(f["title"] for f in ranking[:3]) or "—"

    rows = []
    for _, run in candidates.iterrows():
        rid = run["id"]
        stage = path.loc[rid] if rid in path.index else None
        rows.append(
            {
                "id": rid,
                "Date": run["created_at"].tz_convert(tz).strftime("%d/%m %H:%M"),
                "Cas": detail(rid, "case_label") or ("Texte libre" if rid in details.index else "—"),
                "Configuration (analyste · stratège · rédacteur)": config_summary(detail(rid, "config")),
                "Statut": "réussi" if run["status"] == "success" else "échec",
                "Durée (s)": float(run["duration_s"]),
                "Analyste (s)": None if stage is None else stage["Analyste"],
                "Stratège (s)": None if stage is None else stage["Stratège"],
                "Stories (s)": None if stage is None else stage["Stories"],
                "Coût (€)": float(run["cost_eur"]),
                "Corrections": None if stage is None else int(stage["Corrections"]),
                "Top 3": top3(rid),
            }
        )
    return pd.DataFrame(rows)


def _reopen_button(row: pd.Series, details: pd.DataFrame) -> None:
    rid = row["id"]
    if rid not in details.index:
        st.caption("Ce run date d'avant le suivi détaillé : son résultat n'a pas été conservé.")
        return
    if st.button(f"Rouvrir le résultat du {row['Date']}", key=f"reopen_{rid}"):
        try:
            data = session.repository().fetch_result(rid)
        except StoreError as exc:
            st.error(exc.user_message)
            return
        if not data:
            st.warning("Aucun résultat complet pour ce run (il s'est arrêté avant la fin).")
            return
        st.session_state["reopen_result"] = PipelineResult.model_validate(data)
        st.rerun()


def _compare(chosen: pd.DataFrame, details: pd.DataFrame) -> None:
    a, b = chosen.iloc[0], chosen.iloc[1]
    st.markdown(f"##### Comparaison : A ({a['Date']}) contre B ({b['Date']})")
    if a["Cas"] != b["Cas"]:
        st.warning("Les deux runs ne portent pas sur le même cas : la comparaison du classement n'a pas de sens.")

    cols = st.columns(3)
    for col, label, key, digits, unit in (
        (cols[0], "Durée totale", "Durée (s)", 1, " s"),
        (cols[1], "Coût", "Coût (€)", 3, " €"),
    ):
        delta = float(b[key]) - float(a[key])
        share = f" ({delta / float(a[key]):+.0%})" if float(a[key]) else ""
        col.metric(label, f"{float(b[key]):.{digits}f}{unit}".replace(".", ","),
                   f"{delta:+.{digits}f}{unit}{share}".replace(".", ","), delta_color="inverse", border=True)  # fmt: skip
    cols[2].metric("Corrections (A → B)", f"{_num(a['Corrections']):.0f} → {_num(b['Corrections']):.0f}", border=True)
    render_html(
        f'<div class="muted" style="margin:4px 0 10px"><b>A</b> : {a["Configuration (analyste · stratège · rédacteur)"]}'
        f"<br><b>B</b> : {b['Configuration (analyste · stratège · rédacteur)']}</div>"
    )

    _stage_chart(chosen)

    ranking_a = details.at[a["id"], "ranking"] if a["id"] in details.index else []
    ranking_b = details.at[b["id"], "ranking"] if b["id"] in details.index else []
    st.markdown(f"**Classement** · {ranking_verdict(ranking_a or [], ranking_b or [])}")
    if ranking_a and ranking_b:
        st.dataframe(_ranking_table(ranking_a, ranking_b), hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        _reopen_button(a, details)
    with right:
        _reopen_button(b, details)


def _stage_chart(chosen: pd.DataFrame) -> None:
    """Horizontal stacked bars: seconds per stage on the critical path, one bar per run."""
    labels = ["A", "B"]
    data = pd.DataFrame(
        [
            {"Run": f"{labels[i]} · {row['Date']}", "Étape": stage, "Secondes": _num(row[f"{stage} (s)"])}
            for i, (_, row) in enumerate(chosen.iterrows())
            for stage in _STAGES
        ]
    )
    colors = [AGENT_COLORS[_AGENT_NAMES[a]] for a in AGENT_KEYS]
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadius=3, height=22)
        .encode(
            x=alt.X("sum(Secondes):Q", title="Secondes sur le chemin critique"),
            y=alt.Y("Run:N", title=None, sort=None),
            color=alt.Color(
                "Étape:N", scale=alt.Scale(domain=_STAGES, range=colors), legend=alt.Legend(orient="top", title=None)
            ),
            order=alt.Order("stage_order:Q"),
            tooltip=["Run", "Étape", alt.Tooltip("Secondes:Q", format=".1f")],
        )
        .transform_calculate(stage_order=f"indexof({_STAGES!r}, datum['Étape'])")
        .properties(height=alt.Step(40))
    )
    st.altair_chart(chart, width="stretch")


def _ranking_table(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for pair in match_rankings(a, b):
        fa, fb = pair["a"], pair["b"]
        rank_a = fa["rank"] if fa else None
        rank_b = fb["rank"] if fb else None
        rows.append(
            {
                "Feature": (fa or fb)["title"],
                "Rang A": rank_a,
                "Rang B": rank_b,
                "Écart": "—"
                if rank_a is None or rank_b is None
                else f"{rank_a - rank_b:+d}"
                if rank_a != rank_b
                else "=",
                "MoSCoW A → B": f"{fa['moscow'] if fa else '—'} → {fb['moscow'] if fb else '—'}",
                "RICE A": fa["rice"] if fa else None,
                "RICE B": fb["rice"] if fb else None,
                "Impact A → B": f"{fa['impact'] if fa else '—'} → {fb['impact'] if fb else '—'}",
                "Effort A → B": f"{fa['effort'] if fa else '—'} → {fb['effort'] if fb else '—'}",
            }
        )
    return pd.DataFrame(rows)
