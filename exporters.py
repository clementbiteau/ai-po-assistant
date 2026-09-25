"""Export formats for a :class:`~agents.PipelineResult`.

* Jira CSV — importable as-is through *Jira › Settings › System › External
  System Import › CSV* (one row per story, wiki-markup description).
* Markdown — a full report to paste in Confluence / Notion.
* Gherkin ``.feature`` bundle — drop-in for BDD tooling (Cucumber, Behave).
* JSON — the raw, typed result for any downstream automation.
"""

from __future__ import annotations

import csv
import io

from agents import PipelineResult, ScoredFeature, UserStory, backlog_order

JIRA_PRIORITY: dict[str, str] = {
    "Must": "Highest",
    "Should": "High",
    "Could": "Medium",
    "Won't": "Low",
}

_MAX_LABELS = 4


def _jira_description(story: UserStory, scored: ScoredFeature) -> str:
    """Render a story description in Jira wiki markup."""
    a = scored.assessment
    lines = [
        "h3. User story",
        f"*As a* {story.persona}, *I want to* {story.goal}, *so that* {story.benefit}.",
        "",
        "h3. Contexte",
        story.context,
        "",
        "h3. Acceptance criteria",
        "{noformat}",
        story.to_gherkin_feature().rstrip(),
        "{noformat}",
        "",
        "h3. Priorisation",
        "||RICE||Reach||Impact||Confidence||Effort||MoSCoW||",
        f"|{scored.rice_score:,.0f}|{scored.reach_users:,}|{a.impact}/5|{a.confidence}%|{a.effort}/5|{scored.moscow}|",
    ]
    if story.out_of_scope:
        lines += ["", "h3. Hors périmètre", *[f"* {item}" for item in story.out_of_scope]]
    if story.dependencies:
        lines += ["", "h3. Dépendances", *[f"* {item}" for item in story.dependencies]]
    if story.open_questions:
        lines += ["", "h3. Questions ouvertes", *[f"* {item}" for item in story.open_questions]]
    if story.split_suggestion:
        lines += ["", "h3. Découpage suggéré", story.split_suggestion]
    lines += ["", "h3. Verbatims clients", *[f"bq. {q}" for q in scored.feature.evidence_quotes]]
    return "\n".join(lines)


def _stories_in_backlog_order(result: PipelineResult) -> list[tuple[UserStory, ScoredFeature]]:
    """Pair each story with its scored feature, in delivery order."""
    by_id = {s.feature.id: s for s in result.scored_features}
    ordered_ids = [s.feature.id for s in backlog_order(result.scored_features)]
    ordered_ids += [fid for fid in result.stories if fid not in ordered_ids]
    return [(result.stories[fid], by_id[fid]) for fid in ordered_ids if fid in result.stories]


def to_jira_csv(result: PipelineResult) -> bytes:
    """Build a Jira-importable CSV (UTF-8 with BOM so Excel opens it cleanly)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(["Summary", "Issue Type", "Priority", "Story Points", *(["Labels"] * _MAX_LABELS), "Description"])
    for story, scored in _stories_in_backlog_order(result):
        labels = [label.replace(" ", "-") for label in story.labels][:_MAX_LABELS]
        labels += [""] * (_MAX_LABELS - len(labels))
        writer.writerow(
            [
                story.jira_summary,
                "Story",
                JIRA_PRIORITY[scored.moscow],
                story.story_points,
                *labels,
                _jira_description(story, scored),
            ]
        )
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def to_feature_files(result: PipelineResult) -> str:
    """Concatenate every story as a Gherkin feature, separated by comments."""
    blocks = [
        f"# {scored.feature.id} · {scored.moscow} · RICE {scored.rice_score:,.0f}\n{story.to_gherkin_feature()}"
        for story, scored in _stories_in_backlog_order(result)
    ]
    return "\n".join(blocks)


def to_markdown(result: PipelineResult) -> str:
    """Render the whole analysis as a shareable Markdown report."""
    ctx, analysis = result.context, result.analysis
    md = [
        f"# Synthèse feedbacks & backlog — {ctx.product_name}",
        "",
        f"_Généré le {result.generated_at} avec `{result.model}` · objectif : {ctx.strategic_goal}_",
        "",
        "## Résumé exécutif",
        analysis.executive_summary,
        "",
        f"**{analysis.sources_count} sources** analysées ({', '.join(analysis.channels)}).",
        "",
        "## Thèmes",
        *[f"- **{t.name}** ({t.mention_count} mentions, {t.sentiment}) — {t.description}" for t in analysis.themes],
        "",
        "## Priorisation RICE",
        "",
        "| # | Feature | Reach | Impact | Confidence | Effort | RICE | MoSCoW |",
        "|---|---|---:|---:|---:|---:|---:|---|",
        *[
            f"| {s.rank} | {s.feature.id} · {s.feature.title} | {s.reach_users:,} | {s.assessment.impact} "
            f"| {s.assessment.confidence}% | {s.assessment.effort} | **{s.rice_score:,.0f}** | {s.moscow} |"
            for s in result.scored_features
        ],
        "",
        f"> {result.portfolio_insight}",
        "",
        "## User stories",
    ]
    for story, scored in _stories_in_backlog_order(result):
        md += [
            "",
            f"### {scored.feature.id} · {story.jira_summary}",
            f"`{scored.moscow}` · `RICE {scored.rice_score:,.0f}` · `{story.story_points} pts`",
            "",
            f"**As a** {story.persona}, **I want to** {story.goal}, **so that** {story.benefit}.",
            "",
            story.context,
            "",
            "```gherkin",
            story.to_gherkin_feature().rstrip(),
            "```",
        ]
    signals = analysis.other_signals
    if signals:
        md += ["", "## Autres signaux (bugs, frictions, retours positifs)", ""]
        md += [f"- **{s.type}** — {s.summary}" for s in signals]
    return "\n".join(md) + "\n"


def to_json(result: PipelineResult) -> str:
    """Serialise the full typed result."""
    return result.model_dump_json(indent=2)
