"""Word-for-word customer feedback samples for one-click live demos.

Each sample deliberately mixes channels, tones, languages, duplicates,
bugs and genuine feature requests — exactly what lands in a PO's inbox.
All companies and people are fictitious.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedbackSample:
    """A ready-to-analyse feedback dump."""

    key: str
    label: str
    pitch: str
    text: str


NOTIFICATIONS_MIX = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[EMAIL] De : Sophie Marchand <s.marchand@logitrans.fr>
Objet : Trop de notifications = on rate l'essentiel (URGENT)
Date : lundi 8 septembre, 08:12

Bonjour,

Je me permets de vous écrire directement car la situation devient intenable. Mes 180 \
collaborateurs reçoivent en moyenne 60 à 80 notifications Orbit par jour. Résultat : \
plus personne ne les lit, et la semaine dernière nous avons raté une échéance client \
parce que l'alerte de retard était noyée au milieu de 40 mails "X a commenté une tâche".

Ce qu'il nous faudrait, c'est simple : un récapitulatif quotidien au lieu d'un mail par \
action, et la possibilité de choisir QUOI on reçoit (par projet, par type d'évènement). \
Aujourd'hui c'est tout ou rien.

Je vous le dis franchement : notre renouvellement est en mars, et en l'état je ne suis \
pas certaine de le défendre en comité de direction.

Sophie Marchand
Head of Operations — Logitrans

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ZENDESK #48213] Priorité : Normale — Statut : Ouvert
Sujet : notifs email en double depuis la MAJ
Client : Atelier Bévin (32 utilisateurs)

Depuis la mise à jour 4.2 de jeudi, chaque notification arrive deux fois dans ma boîte. \
Idem pour mes collègues. C'est vraiment pénible vu la quantité qu'on reçoit déjà...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NPS — Score 4/10] Utilisateur : chef de projet, compte Mid-Market (Kraft & Lemoine)
"Je passe la première heure de ma journée à trier les notifs Orbit. Mettez un résumé \
quotidien svp, et laissez-nous couper les notifs d'un projet quand on n'est plus dessus."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NPS — Score 9/10] Utilisateur : directrice PMO (Groupe Aldane)
"Super outil, le Gantt est top et l'équipe l'a adopté en 2 semaines. Il manque juste une \
vue de la charge de travail par personne : aujourd'hui je fais ça dans un Excel à côté \
pour savoir qui est surchargé."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[EMAIL] From: Lars Eriksen <lars.eriksen@nordvik-energy.no>
Subject: SSO requirement before security review

Hi team,

Our IT security review is scheduled for Q3. Procurement has made it clear: without SSO \
through Azure AD (SAML) and automatic deprovisioning of leavers, they will not sign the \
renewal for our 450 seats. We currently manage Orbit accounts manually and last month a \
former contractor still had access for three weeks — that is a finding for our auditors.

Can you share your roadmap on this?

Best regards,
Lars Eriksen — IT Manager, Nordvik Energy

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[SLACK #cs-feedback] Julie (Customer Success Manager) — mardi 14:32
Petit récap de ma semaine : 3 comptes Mid-Market (Logitrans, Kraft & Lemoine, Hexa \
Conseil) m'ont demandé de recevoir les alertes Orbit directement dans Slack / Teams \
plutôt que par email. Hexa dit que "l'email c'est là où les notifs vont mourir". \
Ça revient TRÈS souvent dans mes QBR.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ZENDESK #48240] Priorité : Basse — Statut : En attente
Sujet : rapport hebdo automatique ?
Client : Cabinet Rousseau & Associés (18 utilisateurs)

Bonjour, est-il possible de programmer l'envoi automatique d'un rapport d'avancement en \
PDF à notre direction chaque lundi ? Pour l'instant je fais des captures d'écran du \
tableau de bord. Merci !

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[APP STORE — ★★☆☆☆] "Bien sur ordi, bof sur mobile"
L'appli mobile plante systématiquement quand j'ouvre une pièce jointe PDF dans une \
tâche. Et impossible de mettre les notifications en sourdine le week-end, mon téléphone \
vibre le dimanche pour des commentaires sans importance.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ZENDESK #48302] Priorité : Basse — Statut : Résolu
Sujet : où est l'export Excel ???
J'ai cherché 20 minutes l'export Excel du reporting. Votre support m'a dit qu'il est \
dans "..." > "Plus d'options" > "Exporter". Sérieusement, personne ne peut trouver ça.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NOTE D'APPEL — Sales] Karim B., Account Executive — deal perdu : Ventura Group (300 sièges)
Raison principale de la perte : le concurrent propose une vue "capacité équipe" qui \
montre la charge de chaque personne semaine par semaine. Le DAF voulait arbitrer les \
recrutements avec. On était mieux placés sur le prix et le Gantt.
"""

ONBOARDING_MIX = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[INTERCOM — Chat] Visiteur en essai gratuit (jour 3) — Agence Pixel Nord
"Bonjour, j'ai invité mon équipe mais personne ne sait par où commencer. Il n'y a pas \
de modèle de projet ? On a abandonné l'essai de votre concurrent pour la même raison..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[EMAIL] De : Thomas Girard <t.girard@medisoft.fr>
Objet : Import depuis Jira / Trello

Bonjour,
Nous migrons 40 projets depuis Trello et 12 depuis Jira. Votre import CSV perd les \
pièces jointes, les commentaires et les assignations. Nous avons passé 3 jours à tout \
ressaisir à la main. Pour nos 5 autres filiales qui doivent migrer, c'est bloquant : un \
import natif Jira/Trello conditionne le déploiement groupe (≈ 900 licences).
Thomas Girard, DSI adjoint

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NPS — Score 6/10] Utilisateur : office manager (TPE, 8 utilisateurs)
"Outil puissant mais l'onboarding est un peu brutal. Une checklist de démarrage ou une \
visite guidée aiderait beaucoup."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ZENDESK #51877] Priorité : Haute — Statut : Ouvert
Sujet : Les invitations expirent trop vite
Mes invités reçoivent un lien qui a expiré au bout de 24h. La moitié de mon équipe \
était en congé. Merci de rallonger ou de permettre de renvoyer l'invitation en 1 clic.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[G2 REVIEW — ★★★★☆] "Great once set up"
"Once our workspace was configured it became our team's source of truth. But the first \
two weeks were painful: no templates, no sample project, and permissions are confusing \
(what's the difference between Member and Collaborator?)."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[SLACK #product-feedback] Nadia (Sales Engineer)
Sur les démos, 1 prospect sur 2 demande si on a des templates par métier (marketing, \
BTP, agence). On perd du temps à construire des projets d'exemple à la main avant chaque démo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ZENDESK #51902] Priorité : Normale
Sujet : Import CSV — dates inversées
Toutes nos dates au format JJ/MM/AAAA ont été importées en MM/JJ. 400 tâches à corriger.
"""

MOBILE_PERF_MIX = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[PLAY STORE — ★☆☆☆☆] Conducteur de travaux
"Sur les chantiers on n'a pas de réseau. L'appli est inutilisable hors ligne, impossible \
de cocher une tâche ou de prendre une photo pour le suivi. On repasse au papier."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[EMAIL] De : Claire Dumont <c.dumont@batipro-ouest.fr>
Objet : Mode hors ligne — renouvellement
Nos 220 compagnons travaillent sur des chantiers en zone blanche. Sans mode hors ligne \
avec synchronisation au retour du réseau, nous ne pourrons pas généraliser Orbit au-delà \
des bureaux d'études. Un concurrent spécialisé BTP nous a fait une offre.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ZENDESK #50110] Priorité : Haute
Sujet : Tableau de bord très lent
Le tableau de bord met plus de 12 secondes à charger sur notre espace (1 200 projets). \
Mes managers ont arrêté de l'ouvrir le matin.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NPS — Score 7/10] Utilisateur : chef d'équipe terrain
"Pratique pour la photo de fin d'intervention, mais j'aimerais pouvoir annoter la photo \
(flèche, entourer un défaut) directement dans l'appli."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[APP STORE — ★★★★★] "Enfin une appli simple"
"Rien à redire, je gère mes interventions en 2 clics. Top."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NOTE CSM] Compte Voltéo (Enterprise, 600 sièges) — QBR du 12/09
Deux irritants majeurs remontés : (1) la lenteur du tableau de bord sur les gros espaces \
(« on dirait un site des années 2000 ») ; (2) l'absence de signature client sur mobile \
pour valider la fin d'intervention — aujourd'hui ils impriment un PV papier.
"""

SAMPLES: dict[str, FeedbackSample] = {
    s.key: s
    for s in (
        FeedbackSample(
            key="notifications",
            label="Notifications & churn",
            pitch="Email client mécontent, tickets Zendesk, NPS, Slack CSM, note Sales — 10 sources, FR + EN.",
            text=NOTIFICATIONS_MIX,
        ),
        FeedbackSample(
            key="onboarding",
            label="Onboarding et migration",
            pitch="Essai gratuit, DSI bloqué par l'import Jira, reviews G2, remontées Sales Engineer.",
            text=ONBOARDING_MIX,
        ),
        FeedbackSample(
            key="mobile",
            label="Mobile terrain et performance",
            pitch="Conducteurs de travaux en zone blanche, dashboard lent, compte Enterprise en QBR.",
            text=MOBILE_PERF_MIX,
        ),
    )
}

#: Sample replayed by the offline demo mode (see ``demo_result.json``).
DEMO_SAMPLE_KEY = "notifications"
