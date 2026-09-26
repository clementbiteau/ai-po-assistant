# Tasks — AI Product Owner Assistant

> **Règle** : ce fichier est mis à jour **dès qu'une tâche est inscrite** (ajout dans « À faire » ou « En cours »)
> et **dès qu'elle est terminée** (déplacée dans « Terminé », avec la date). Il sert de passation entre les sessions.

Dernière mise à jour : 2026-09-26

---

## En cours

_Aucune tâche en cours._

---

## À faire — prochaine session

### Priorité 1 · Latence et adéquation au use case (le « point 3 »)
- [ ] **Mesurer un run de référence** : 3 runs en direct sur « Notifications & churn », puis une requête SQL sur `agent_calls` pour obtenir la durée par agent, la part des corrections (tentative 2), les tokens et le coût par run. Vérifier au passage qu'un run reste sous le plafond de 0,50 € par requête du compte relecteur.
- [ ] **Effort du stratège** : si c'est l'étape la plus lente, comparer `EFFORT_STRATEGIST` en `high` et en `medium` sur la durée et la stabilité du classement RICE.

Écartés : `max_tokens` (plafond de sécurité, sans effet sur la vitesse) et `STORY_WORKERS` (les 3 stories tournent déjà en parallèle).

### Priorité 2 · Démo
- [ ] **Remplacer le résultat de démo rédigé à la main par un vrai run** : lancer en direct le cas « Notifications & churn », télécharger *Export › JSON typé*, l'enregistrer sous `data/demo_result.json`, puis commit.
- [ ] **Vérifier en ligne**, après redéploiement : accueil vide, onboarding avec démo rapide présélectionnée, tri instantané replié, bandeau d'accueil fermable, palette vert et beige dans les deux thèmes.

### Priorité 3 · Améliorations proposées
- [ ] **Prénom affiché** : ajouter un champ « nom affiché » au profil (Supabase `profiles.display_name`, éditable dans *Admin › Quotas*), pour afficher « Clément » avec l'accent au lieu du prénom déduit de l'email.
- [ ] **Jeu d'évaluation** : une dizaine de dumps annotés (demandes attendues, bugs, verbatims) pour mesurer la qualité à chaque changement de prompt.
- [ ] **Résister à un rafraîchissement de page** : aujourd'hui, F5 déconnecte l'utilisateur et fait disparaître l'analyse affichée. Les dépenses, elles, restent en base. Piste : garder la session et recharger le dernier résultat.
- [ ] **Bouton « Actualiser » dans Admin** : les chiffres de la console sont mis en cache 2 minutes par session.
- [ ] Optimisations secondaires, à ne faire que si la mesure le justifie : modèle plus léger (Haiku 4.5) pour le rédacteur, entrée allégée pour le stratège, prompt caching (gain probablement faible).
- [ ] Connecteurs d'entrée (Zendesk, messagerie, outil NPS, Slack). Hors POC, à présenter comme roadmap.

### Actions côté Clément (configuration)
- [ ] *Admin › Quotas* : relever les limites du compte relecteur `test@thiga.com` pour le jour de l'entretien, une fois le coût d'un run connu.

---

## Terminé

### 2026-09-26
- [x] Streaming vérifié en ligne sur un vrai run (« tout marche très bien »). Premier run réel : 0,163 €, bien sous le plafond de 0,50 € par requête.
- [x] Retour à la palette vert et beige (accent vert profond, fond beige, titres Newsreader), à la demande de Clément : la charte Thiga faisait trop voyant. Fond beige plutôt que quasi blanc pour éviter l'éblouissement ; couleurs des graphiques revalidées sur les deux fonds.

### 2026-09-25
- [x] Revue d'adéquation à la consigne : section 7 de `HOWHY.md` (demandes couvertes, écarts assumés, ajouts et leur place dans la présentation, verdict).
- [x] Streaming de la progression : pendant l'analyste et le stratège, la réflexion résumée et les éléments trouvés (thèmes, features, features notées) s'affichent en direct. Rejoué aussi en mode démo. Tests ajoutés, décision D17 dans `HOWHY.md`.
- [x] Supabase : inscriptions publiques désactivées.
- [x] Streamlit › Secrets : `ANTHROPIC_CREDITS_USD = "10"` ajouté.
- [x] Supabase : compte relecteur `test@thiga.com` créé (rôle membre).
- [x] Supabase : migration `agent_calls` exécutée (journal des agents actif en production).
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
