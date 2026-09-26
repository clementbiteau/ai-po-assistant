"""Catalog of the connectors a production version would offer.

In the POC, feedback is pasted by hand. In production it would flow in from
the tools where it already lives (support desk, mailbox, chat, surveys,
stores, CRM), and the backlog would flow out to Jira. This module describes
that roadmap as data, so the "Connecteurs" tab, the docs and the tests share
one source of truth. No Streamlit import here, and no connector is live: the
POC never asks for, stores or uses third-party credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Direction = Literal["in", "out", "both"]


@dataclass(frozen=True)
class Connector:
    """One integration of the production roadmap.

    Attributes:
        key: Stable identifier.
        name: Product name(s), as the PO knows them.
        category: What kind of tool it is.
        direction: ``in`` brings feedback in, ``out`` pushes the backlog out.
        brings: What it imports or exports, in the PO's words.
        header_tag: Tag prefixed to each imported item (``[ZENDESK #123]``…), so the
            existing triage rules (``triage.py``) classify it unchanged. Empty for
            connectors that bring no customer feedback.
        auth: How the connection would be authorised.
        cadence: How often data would sync.
        phase: Delivery order (1 = first), argued in :data:`PHASES`.
    """

    key: str
    name: str
    category: str
    direction: Direction
    brings: str
    header_tag: str
    auth: str
    cadence: str
    phase: int


CONNECTORS: tuple[Connector, ...] = (
    Connector(
        "zendesk", "Zendesk", "Support client", "in",
        "Tickets du support : sujet, description, priorité, client, statut. Les bugs y sont signalés en premier.",
        "ZENDESK", "OAuth 2.0, lecture seule", "Temps réel (webhook)", 1,
    ),
    Connector(
        "jira", "Jira", "Backlog produit", "both",
        "En sortie : création des stories avec leurs critères Gherkin. En entrée : le backlog existant, pour ne pas "
        "re-prioriser ce qui est déjà prévu ou livré.",
        "", "OAuth 2.0 (Atlassian)", "À la demande, après validation du PO", 1,
    ),
    Connector(
        "mail", "Outlook / Gmail", "Messagerie", "in",
        "Emails clients d'une boîte partagée (par exemple feedback@) : réclamations, demandes, retours de comptes clés.",
        "EMAIL", "OAuth 2.0 (Microsoft 365 ou Google), lecture seule", "Toutes les heures", 1,
    ),
    Connector(
        "chat", "Slack / Microsoft Teams", "Messagerie d'équipe", "in",
        "Messages d'un canal dédié (par exemple #feedback-clients) où Sales et Customer Success relaient ce qu'ils entendent.",
        "SLACK", "Application OAuth, canaux choisis uniquement", "Temps réel (événements)", 2,
    ),
    Connector(
        "nps", "Outil NPS (Typeform, Delighted…)", "Enquêtes", "in",
        "Réponses aux enquêtes : note de 0 à 10 et commentaire libre. Les détracteurs remontent en priorité.",
        "NPS", "Clé d'API ou webhook", "Quotidien", 2,
    ),
    Connector(
        "stores", "App Store / Google Play", "Avis mobiles", "in",
        "Avis publics sur l'application mobile : note, texte, version de l'app.",
        "APP STORE", "Clé d'API des consoles développeur", "Quotidien", 2,
    ),
    Connector(
        "crm", "Salesforce / HubSpot", "CRM", "in",
        "Notes d'appel et motifs de deals perdus : ce qui a fait perdre une vente, avec la taille du compte.",
        "NOTE D'APPEL", "OAuth 2.0, lecture seule", "Quotidien", 3,
    ),
)  # fmt: skip

#: Why each phase comes in that order.
PHASES: dict[int, tuple[str, str]] = {
    1: (
        "Phase 1 · Le socle",
        "Là où arrive l'essentiel des retours (support, email) et là où part le backlog (Jira). "
        "Jira en lecture donne aussi à l'outil la mémoire de ce qui est déjà prévu.",
    ),
    2: (
        "Phase 2 · La voix du client élargie",
        "Messages internes, enquêtes et avis publics : plus de volume, des signaux plus courts.",
    ),
    3: (
        "Phase 3 · L'enjeu business",
        "Le CRM relie chaque besoin à du chiffre d'affaires (deal perdu, renouvellement), ce qui renforce le Reach et l'Impact.",
    ),
}


def by_phase() -> dict[int, list[Connector]]:
    """Connectors grouped by delivery phase, in phase order."""
    return {phase: [c for c in CONNECTORS if c.phase == phase] for phase in sorted(PHASES)}
