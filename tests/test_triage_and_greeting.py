"""Rule-based inbox triage and the time-aware greeting."""

from __future__ import annotations

from datetime import datetime

from samples import SAMPLES
from triage import split_messages, triage
from ui.greeting import display_name, salutation


def test_demo_inbox_is_split_and_urgent_first() -> None:
    items = triage(SAMPLES["notifications"].text)
    assert len(items) == 10
    urgent = [i for i in items if i.urgent]
    assert len(urgent) == 5
    assert items[: len(urgent)] == urgent  # urgent first
    channels = {i.channel for i in items}
    assert {"Email", "Ticket support", "Enquête NPS", "Slack interne", "Avis store", "Note d'appel"} <= channels
    sso = next(i for i in items if "SSO" in i.title)
    assert sso.urgent and "exigence sécurité ou conformité" in sso.reasons


def test_detractor_and_low_rating_rules() -> None:
    nps = triage("[NPS — Score 3/10] Utilisateur\nBof.\n\n[NPS — Score 9/10] Utilisateur\nTop.")
    assert [i.urgent for i in nps] == [True, False]
    assert triage("[APP STORE — ★☆☆☆☆] Nul\nÇa plante.")[0].reasons == ("avis 1/5",)


def test_plain_pasted_text_falls_back_to_paragraphs() -> None:
    assert len(split_messages("Premier retour.\n\nDeuxième retour.\n\nTroisième.")) == 3
    assert triage("") == []


def test_greeting_parts() -> None:
    assert display_name("clement.biteau.mars@gmail.com") == "Clement"
    assert display_name("admin@local.dev") == "Admin"
    assert salutation(datetime(2026, 9, 25, 8)) == "Bonjour"
    assert salutation(datetime(2026, 9, 25, 14)) == "Bon après-midi"
    assert salutation(datetime(2026, 9, 25, 21)) == "Bonsoir"
    assert salutation(datetime(2026, 9, 25, 2)) == "Bonsoir"
