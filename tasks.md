# Tasks — AI Product Owner Assistant

> **Règle** : ce fichier est mis à jour **dès qu'une tâche est inscrite** (ajout dans « À faire » ou « En cours »)
> et **dès qu'elle est terminée** (déplacée dans « Terminé », avec la date). Il sert de passation entre les sessions.

Dernière mise à jour : 2026-09-25

---

## En cours

_Aucune tâche en cours._

---

## À faire — prochaine session

### Priorité 1 · Latence, optimisation, adéquation au use case (le « point 3 »)
- [ ] **Mesurer la latence réelle** d'un run en direct via *Admin › Agents* : durée par agent (médiane, 95e centile), part des corrections (tentative 2), tokens par agent. Identifier le goulot.
- [ ] **Évaluer les leviers d'optimisation**, en mesurant avant et après :
  - effort par agent (`EFFORT_*`) ;
  - `max_tokens` ;
  - progression en streaming dans l'interface ;
  - parallélisme des stories (`STORY_WORKERS`) ;
  - réduction de l'entrée du stratège ;
  - prompt caching (gain probablement faible : les prompts système sont courts) ;
  - modèle plus léger pour les tâches simples.
- [ ] **Revue critique « est-ce que ça correspond au use case ? »**
  - Rappel de la consigne : startup SaaS de gestion de projets, PO submergé, 3 modules (analyse, RICE justifié, user stories Gherkin), Streamlit, Claude.
  - Lister les écarts assumés : Sonnet 5 au lieu de 3.5 Sonnet (retiré), seuils MoSCoW relatifs, résultat de démo rédigé à la main.
  - Lister les extensions hors consigne et leur justification : authentification, quotas, admin, journal des agents.

### Priorité 2 · Démo
- [ ] **Remplacer le résultat de démo rédigé à la main par un vrai run** : lancer en direct le cas « Notifications & churn », télécharger *Export › JSON typé*, l'enregistrer sous `data/demo_result.json`, puis commit.
- [ ] **Vérifier en ligne**, après redéploiement : accueil vide, onboarding avec démo rapide présélectionnée, tri instantané replié, bandeau d'accueil fermable, couleurs Thiga dans les deux thèmes.

### Priorité 3 · Améliorations proposées
- [ ] **Prénom affiché** : ajouter un champ « nom affiché » au profil (Supabase `profiles.display_name`, éditable dans *Admin › Quotas*), pour afficher « Clément » avec l'accent au lieu du prénom déduit de l'email.
- [ ] **Jeu d'évaluation** : une dizaine de dumps annotés (demandes attendues, bugs, verbatims) pour mesurer la qualité à chaque changement de prompt.
- [ ] Connecteurs d'entrée (Zendesk, messagerie, outil NPS, Slack). Hors POC, à présenter comme roadmap.

### Actions côté Clément (configuration, à confirmer)
- [ ] Supabase › SQL Editor : exécuter `supabase/migrations/20260926000000_agent_calls.sql` (journal des agents).
- [ ] Supabase › Authentication › General configuration : désactiver « Allow new users to sign up ».
- [ ] Streamlit › Secrets : ajouter `ANTHROPIC_CREDITS_USD = "10"` (crédit restant estimé).
- [ ] Supabase › Authentication › Users : créer les comptes relecteurs (cocher *Auto Confirm User*).

---

## Terminé

### 2026-09-25
- [x] Accueil épuré : inbox **vide par défaut**, avec une invite à choisir un cas prêt à l'emploi ou à coller ses propres retours.
- [x] Onboarding : **démo rapide présélectionnée** à l'étape « Lancer ».
- [x] Inbox chargée en vue compacte : cas en cours, bouton « Changer de cas », **tri instantané et texte brut dans des sections repliables, fermées par défaut**.
- [x] Bandeau d'accueil adapté à une inbox vide.
- [x] Charte Thiga (indigo, framboise, Kanit, Inter), mode clair plus contrasté, bandeau d'accueil fermable par une croix.
- [x] Journal des agents (*Admin › Agents*) : chronologie, tokens, réflexion résumée ; table `agent_calls` avec RLS.
- [x] Vérification automatique des verbatims (mot pour mot dans la source).
- [x] Tri instantané de l'Inbox par règles (canal, urgence) ; bandeau d'accueil selon l'heure.
- [x] Étape « Le cas d'usage » dans l'onboarding, alignée sur la consigne.
- [x] `HOWHY.md` : architecture, décisions, sécurité, limites, glossaire.
- [x] Refonte du design, onboarding en plusieurs étapes, suppression des emojis, suivi du crédit API.
- [x] Authentification Supabase et RLS, quotas par utilisateur, console admin (SQL DuckDB, régression et prévision), thème clair / sombre.
- [x] Dépôt GitHub, CI (lint, tests, schéma et RLS), déploiement Streamlit Cloud.
- [x] POC initial : 3 agents, RICE et MoSCoW, user stories Gherkin, exports Jira.
