"""Instant, rule-based triage of the inbox — deliberately *not* AI.

Before any model is called, the raw dump is split into messages, each one is
tagged with its channel and flagged as urgent when explicit signals are
present (an "URGENT" subject, a high-priority ticket, a detractor NPS score,
a 1-2 star review, a renewal / legal / lost-deal mention).

Why rules here: it is instantaneous, free, fully explainable and good enough
to *sort* an inbox — the nuanced reading is the FeedbackAnalyst's job. This
mirrors how real support tools pre-route tickets before a human (or an AI)
looks at them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEPARATOR = re.compile(r"^\s*[━─=_\-]{8,}\s*$", re.MULTILINE)
_HEADER = re.compile(r"^\s*\[([^\]]+)\]\s*(.*)$")

#: Header keyword → display channel (first match wins).
_CHANNELS: tuple[tuple[str, str], ...] = (
    ("zendesk", "Ticket support"),
    ("intercom", "Chat"),
    ("email", "Email"),
    ("nps", "Enquête NPS"),
    ("slack", "Slack interne"),
    ("app store", "Avis store"),
    ("play store", "Avis store"),
    ("g2", "Avis store"),
    ("review", "Avis store"),
    ("note", "Note d'appel"),
)

_URGENT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\burgent\b", "marqué urgent"),
    (r"priorit[ée]\s*:\s*haute", "ticket priorité haute"),
    (r"renouvellement|renewal|r[ée]silier|churn", "renouvellement en jeu"),
    (r"deal perdu|lost deal|perte du deal", "deal perdu"),
    (r"proc[ée]dure|mise en demeure|legal action|lawyer|avocat|auditor|audit", "risque légal ou audit"),
    (r"security review|revue de s[ée]curit[ée]|rgpd|gdpr", "exigence sécurité ou conformité"),
)


@dataclass(frozen=True)
class InboxItem:
    """One message of the raw dump, as displayed in the Inbox."""

    channel: str
    title: str
    snippet: str
    urgent: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def _channel(tag: str) -> str:
    low = tag.lower()
    return next((label for key, label in _CHANNELS if key in low), "Message")


def _title(tag: str, header_rest: str, body: list[str]) -> str:
    for line in body:
        match = re.match(r"^\s*(objet|subject|sujet)\s*:\s*(.+)$", line, re.IGNORECASE)
        if match:
            return match.group(2).strip()
    if header_rest:
        return header_rest.strip(" —-")
    return tag.strip()


def _snippet(body: list[str], limit: int = 170) -> str:
    skip = re.compile(r"^\s*(de|from|objet|subject|sujet|date|client|priorit[ée])\s*:", re.IGNORECASE)
    text = " ".join(line.strip() for line in body if line.strip() and not skip.match(line))
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _urgency(tag: str, text: str) -> tuple[str, ...]:
    reasons = [label for pattern, label in _URGENT_PATTERNS if re.search(pattern, text, re.IGNORECASE)]
    nps = re.search(r"nps[^\]]*score\s*(\d+)\s*/\s*10", tag, re.IGNORECASE)
    if nps and int(nps.group(1)) <= 4:
        reasons.append(f"NPS détracteur ({nps.group(1)}/10)")
    stars = re.search(r"(★+)(☆*)", tag)
    if stars and len(stars.group(1)) <= 2:
        reasons.append(f"avis {len(stars.group(1))}/5")
    return tuple(dict.fromkeys(reasons))


def split_messages(raw: str) -> list[str]:
    """Split a dump into messages: separator lines first, then ``[TAG]`` headers, then paragraphs."""
    text = (raw or "").strip()
    if not text:
        return []
    if _SEPARATOR.search(text):
        parts = _SEPARATOR.split(text)
    elif len(re.findall(r"^\s*\[[^\]]+\]", text, re.MULTILINE)) >= 2:
        parts = re.split(r"(?m)^(?=\s*\[[^\]]+\])", text)
    else:
        parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def triage(raw: str) -> list[InboxItem]:
    """Turn a raw feedback dump into inbox items, urgent ones first (stable order otherwise)."""
    items: list[InboxItem] = []
    for message in split_messages(raw):
        lines = message.splitlines()
        header = _HEADER.match(lines[0]) if lines else None
        tag, rest = (header.group(1), header.group(2)) if header else ("", "")
        body = lines[1:] if header else lines
        reasons = _urgency(tag, message)
        items.append(
            InboxItem(
                channel=_channel(tag) if tag else "Message",
                title=_title(tag, rest, body) or "Sans titre",
                snippet=_snippet(body),
                urgent=bool(reasons),
                reasons=reasons,
            )
        )
    return sorted(items, key=lambda item: not item.urgent)
