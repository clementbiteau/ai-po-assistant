"""Live progress panel: what the running agent is thinking and has found so far.

Fed by :class:`agents.LiveUpdate` during a live run, and by a scripted
replay of the stored result in demo mode, so both look the same.
"""

from __future__ import annotations

import re

from agents import LiveUpdate, PipelineResult, StepName
from ui.style import esc, shorten

#: Characters of summarised reasoning kept on screen (the most recent ones).
THINKING_TAIL = 360
_GROUPS = {"theme": "Thèmes", "feature": "Features repérées", "scored": "Features notées"}
_AGENT_NAMES = {"analyst": "FeedbackAnalyst", "strategist": "PrioritizationStrategist"}


def thinking_tail(thinking: str, limit: int = THINKING_TAIL) -> str:
    """Last ``limit`` characters of the reasoning, markdown stripped, cut on a word boundary."""
    text = re.sub(r"\*\*(.+?)\*\*\s*", r"\1. ", thinking)  # section titles of the summary become sentences
    text = re.sub(r"[*#`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    return "…" + tail[tail.find(" ") + 1 :]


def live_html(update: LiveUpdate) -> str:
    """The live panel for one :class:`LiveUpdate`."""
    title = "Réflexion de l'agent" + (" · correction de la réponse" if update.attempt > 1 else "")
    thinking = thinking_tail(update.thinking)
    body = f'<div class="lt">{esc(thinking)}</div>' if thinking else '<div class="lt">Lecture en cours…</div>'
    for kind, group in _GROUPS.items():
        labels = [label for k, label in update.found if k == kind]
        if not labels:
            continue
        body += f'<div class="lg">{group} · {len(labels)}</div>'
        if kind == "scored":
            body += "".join(f'<div class="li">{esc(label)}</div>' for label in labels)
        else:
            body += "<div>" + "".join(f'<span class="chip {kind}">{esc(shorten(label, 48))}</span>' for label in labels)
            body += "</div>"
    return f'<div class="live"><div class="lh"><span class="dot"></span>{title}</div>{body}</div>'


def demo_updates(result: PipelineResult, step: StepName, frames: int = 6) -> list[LiveUpdate]:
    """Scripted live updates rebuilt from a stored result (demo replay).

    Items appear one by one; the stored summarised reasoning, when the result
    comes from a real run, is revealed progressively alongside.
    """
    if step == "analyst":
        found = [("theme", t.name) for t in result.analysis.themes]
        found += [("feature", f.title) for f in result.analysis.feature_requests]
    else:
        ordered = sorted(result.scored_features, key=lambda s: int(s.feature.id.lstrip("F") or 0))
        found = [
            ("scored", f"{s.feature.title} · impact {s.assessment.impact}/5 · effort {s.assessment.effort}/5")
            for s in ordered
        ]
    thinking = next((c.thinking for c in result.usage.calls if c.agent == _AGENT_NAMES[step] and c.thinking), "")
    frames = max(frames, len(found))
    return [
        LiveUpdate(
            step=step,
            attempt=1,
            thinking=thinking[: len(thinking) * (i + 1) // frames],
            found=tuple(found[: len(found) * (i + 1) // frames]),
        )
        for i in range(frames)
    ]
