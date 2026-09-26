# Tasks — AI Product Owner Assistant

> **Règle** : ce fichier est mis à jour **dès qu'une tâche est inscrite** (ajout dans « À faire » ou « En cours »)
> et **dès qu'elle est terminée** (déplacée dans « Terminé », avec la date). Il sert de passation entre les sessions.

Dernière mise à jour : 2026-09-26

---

## Référence absolue : la consigne de Thiga

Le texte intégral est en tête du [README](README.md#la-consigne-de-thiga--la-référence-du-projet). Toute tâche se vérifie d'abord contre lui.

- **Objectif** : un agent IA qui assiste un PO au quotidien : analyser les retours, prioriser, aider à rédiger les user stories.
- **9 fonctionnalités attendues** :
  - analyse : traiter les retours (emails, tickets, commentaires), repérer tendances et récurrences, extraire les demandes ;
  - priorisation : noter selon plusieurs critères, appliquer des méthodes (MoSCoW, RICE…), justifier les recommandations ;
  - rédaction : user stories selon les standards, critères d'acceptation, complexité relative.
- **Livrables** : code source, démonstration avec des cas concrets, documentation de l'approche et des choix, tests.
- **Présentation de 15 min** : démonstration 8-10 min, architecture 3-4 min, défis et solutions 2-3 min.
- **Aucune contrainte technique.**
- **Critères** : compréhension du PO, qualité technique, expérience utilisateur (simplicité, efficacité), complétude, présentation.

---

## Point de reprise (pour une nouvelle session)

**État au 2026-09-26 (soir)** : le POC couvre les 9 fonctionnalités attendues (les tendances dans le temps en partie) et les 4 livrables. Il est en ligne, la CI est au vert (76 tests, règles de sécurité testées sur PostgreSQL) et le dernier commit est poussé sur `main`.

- **À lire d'abord** : la consigne en tête du [README](README.md), puis `HOWHY.md` (le quoi, le comment, le pourquoi ; section 7 = adéquation à la consigne).
- **Dépôt** : `clementbiteau/ai-po-assistant` (public). Tout push sur `main` redéploie Streamlit Cloud (Python 3.12). `reload_guard.py` évite l'ancien « Reboot app » après un déploiement.
- **Déroulé de la présentation** (page privée, format 15 min de la consigne) : https://claude.ai/artifact/TxaWoGuHFrooBaLK7hhEV6
- **Produit fictif** : EwokAI. **Cas de démo** : « Notifications & churn » (le mode démo hors-ligne rejoue un vrai run Sonnet 5 du 26/09 : 110 s, 0,16 €).
- **Modèle** : Sonnet 5 partout, stratège en effort élevé. Haiku mesuré et écarté ; Opus et Fable écartés (D8, D18).

---

## En cours

_Aucune tâche en cours._

---

## À faire — prochaine session

### 1 · Ce qui reste (à discuter avec Clément en ouverture)
- [ ] **Vérifier l'app en ligne après le dernier déploiement** : barre latérale épurée (icônes soleil et lune), sections repliées, graphique des tokens en barres, guide affiché une seule fois, EwokAI partout, onglets pâles (Connecteurs, Admin).
- [ ] **Seul point partiel de la consigne : les tendances dans le temps.** Décider : le présenter comme feuille de route (historique via les connecteurs) ou ajouter une petite vue d'évolution entre deux runs.
- [ ] **Répéter la présentation** avec le déroulé (démo 8-10 min, architecture 3-4 min, défis 2-3 min) et ajuster les timings.

### 2 · Le petit manuel « What / How / Why » pour les lecteurs Thiga
- [ ] **Définir avec Clément** : le public (Renaud, Sébastien, Laura), le format (page, PDF, guide dans l'app) et la longueur.
- [ ] **Contenu pressenti** :
  - quoi : ce que fait l'assistant ;
  - comment : se connecter, parcourir un cas, lire la priorisation, exporter ;
  - pourquoi : les choix clés et les ajouts en pâle.

  Il doit rester court et renvoyer à `HOWHY.md` pour le détail.

### Actions côté Clément (configuration)
- [ ] **Rôles des invités** : passer renaud@thiga.test et sebastien@thiga.test en admin (Admin › Quotas, ou la requête SQL `update public.profiles set role = 'admin' where email in (...)`), avec un plafond (par exemple 3 € par jour) ; laura@thiga.test reste membre.
- [ ] **Envoyer les accès** aux invités : un mot de passe fort et unique par personne (`openssl rand -base64 12`).
- [ ] **Crédit API** : garder au moins 2 € de crédit restant (visible dans Admin) pour les runs des invités.
- [ ] Facultatif : supprimer d'éventuelles anciennes données synthétiques (`delete from public.runs where is_synthetic;`) et décider du sort du compte `test@thiga.com`.

### Backlog · améliorations possibles (hors consigne, à arbitrer)
- [ ] **Prénom affiché** : un champ « nom affiché » au profil (`profiles.display_name`), pour afficher « Clément » avec l'accent au lieu du prénom déduit de l'email.
- [ ] **Jeu d'évaluation** : une dizaine de dumps annotés (demandes attendues, bugs, verbatims), rejoués à chaque changement de prompt ou de modèle.
- [ ] **Résister à un rafraîchissement de page** : aujourd'hui, F5 déconnecte. Un run enregistré peut déjà être rouvert depuis *Admin › Runs* ; reste à garder la session et à recharger le dernier résultat automatiquement.
- [ ] **Bouton « Actualiser » dans Admin** : les chiffres de la console sont mis en cache 2 minutes par session.
- [ ] Optimisations, seulement si la mesure le justifie : entrée allégée pour le stratège, prompt caching (gain probablement faible). Haiku a été mesuré et écarté (D18).
- [ ] **Autres fournisseurs de modèles** (open source, etc.) : la consigne le permettrait, mais l'app s'appuie sur des fonctions de l'API Claude (format JSON strict, réflexion résumée, effort). À présenter comme piste, l'appel au modèle étant isolé dans `agents.py`.
- [ ] **Connecteurs réels** (phase 1 : Zendesk, Jira, Outlook / Gmail) : hors POC ; feuille de route visible dans l'onglet Connecteurs (D20).

### Repères techniques pour reprendre
- **Migrations Supabase**, toutes exécutées en production : `20260925000000_init.sql`, `20260926000000_agent_calls.sql`, `20260927000000_run_details.sql`.
- **Secrets Streamlit** : `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` (clé *publishable*), `ANTHROPIC_CREDITS_USD = "10"`, `EFFORT_STRATEGIST = "high"`.
- **Vérifier avant de pousser** : `ruff check .`, `ruff format --check .` et `pytest -q` (76 tests). Les règles de sécurité se testent avec `scripts/test_schema.sh` sur un PostgreSQL jetable.
- **Aperçu local** : le serveur d'aperçu n'a pas accès au dossier Documents (permission macOS). Il faut copier l'app et les paquets du `.venv` dans le dossier temporaire de la session, puis lancer en `AUTH_MODE=local` avec `--global.developmentMode false` (hors d'un dossier `site-packages`, Streamlit se croit en mode développement et refuse `--server.port`).
- **Tests d'interface** : les tests Streamlit (`AppTest`) ne savent pas afficher le guide ; ils le marquent « vu » avant la connexion.

---

## Terminé

### 2026-09-26
- [x] **Plus de formulaire fantôme dans le bandeau vert après la connexion** (vu par Clément). Cause : Streamlit associe les éléments d'un run à l'autre par position ; la colonne du formulaire restait affichée, estompée, dans le bandeau d'accueil tant que le premier run connecté n'était pas fini (plusieurs secondes pour un admin). La connexion et l'espace de travail ont désormais chacun leur emplacement, vidé au début de l'autre run ; le même défaut à la déconnexion (l'app estompée sous le formulaire) disparaît aussi. Reproduit puis vérifié sur une copie locale, couvert par un test.
- [x] Priorité « latence et adéquation » close : `max_tokens` et `STORY_WORKERS` écartés (sans effet sur la vitesse), effort du stratège mesuré et gardé en élevé, revue d'adéquation faite.
- [x] **Interface épurée** : bandeaux « Étape x sur 4 » retirés ; thèmes en lignes compactes ; graphiques, justifications, détails des stories, rédaction à la demande, détails techniques, autres signaux et phases 2-3 des connecteurs dans des sections repliées. Barre latérale réduite au compte, au thème (icônes soleil et lune dessinées en CSS), au mode démo et au nombre de stories ; contexte produit, « Sous le capot », quotas et crédit retirés (ces derniers restent dans Admin).
- [x] **Graphique « Tokens consommés par jour »** : il était tracé en aire, invisible avec des données sur un ou deux jours ; passé en barres (idem pour la dépense quotidienne).
- [x] **Consigne Thiga en tête du README** (texte intégral) **et de `tasks.md`** (résumé), comme référence absolue du projet.
- [x] Comptes invités créés par Clément : renaud@thiga.test, sebastien@thiga.test, laura@thiga.test.
- [x] **Doc et déroulé alignés sur la vraie consigne Thiga** : aucune contrainte technique (Streamlit et Claude sont des choix, plus « imposés »), MoSCoW explicitement demandé, adéquation revue sur les 9 fonctionnalités attendues et les 4 livrables (`HOWHY.md` sections 1 et 7). Seul point partiel : les tendances dans le temps. Déroulé refait au format réel : démo 8-10 min, architecture 3-4 min, défis 2-3 min, avec la correspondance aux critères du jury.
- [x] **Orbit renommé en EwokAI** : cas de démo, contexte produit, guide, docs, et dans le run de démo enregistré de façon cohérente (14/14 verbatims toujours exacts).
- [x] **Guide de démarrage une seule fois par utilisateur** : mémorisé dans les métadonnées du compte Supabase (en local, dans la base SQLite), testé.
- [x] **Données synthétiques** : requête de suppression définitive fournie à Clément (optionnelle, elles sont déjà ignorées partout).
- [x] **Données synthétiques retirées** de la console admin (générateur, bouton « Données de démo », interrupteur d'inclusion) : l'admin n'affiche que l'usage réel, et d'éventuelles anciennes lignes synthétiques restent ignorées partout.
- [x] **Onglets ajoutés en pâle** (Connecteurs, Admin) avec la légende « En pâle : ajouts au-delà de la consigne », ainsi que le réglage des modèles réservé à l'admin. Les cinq raisons de ces ajouts sont dans `HOWHY.md` (7.3).
- [x] **Fin des erreurs après déploiement** (`ImportError` qui exigeait « Reboot app ») : `reload_guard.py` recharge les modules modifiés sans redémarrer. Reproduit puis corrigé sur une copie locale, et couvert par un test.
- [x] **Déroulé de démo** pour l'entretien, en page privée : https://claude.ai/artifact/TxaWoGuHFrooBaLK7hhEV6. Version 3 au format réel de la consigne (15 min : démo, architecture, défis), avec la correspondance aux critères du jury, les questions probables, les plans B et les limites à assumer.
- [x] **Onglet Connecteurs** : 7 connecteurs en 3 phases (Zendesk, Jira en entrée et en sortie, Outlook / Gmail ; Slack / Teams, NPS, stores ; CRM), avec ce qu'ils apportent, l'autorisation, la fréquence et le canal d'arrivée. Aucune connexion active. Chaque source arrive sur un canal que le tri par règles connaît déjà (testé). Décision D20 dans `HOWHY.md`, glossaire complété (Connecteur, OAuth, Webhook).
- [x] **Démo = vrai run** : l'export du run « Référence » (Sonnet partout, 110 s, 0,16 €, 14/14 verbatims) remplace le résultat rédigé à la main. Les chiffres du rejeu viennent du résultat. Les tests utilisent un résultat de référence figé (`tests/fixtures/reference_result.json`).
- [x] Comparaison des stories : Sonnet 20 à 29 s, 5 scénarios, découpe claire ; Haiku 43 à 64 s, 2 stories sur 9 hors règle, points irréguliers. Verdict final dans `HOWHY.md` (D18) : Sonnet 5 partout.
- [x] Comparaison des modèles sur 5 runs : Haiku est 1,5 à 2,4 fois plus lent par agent, seulement 20 % moins cher par run (il écrit plus), et moins bon sur l'analyse (découpage, un verbatim retouché, une erreur de fait). Le top 3 et le SSO obligatoire tiennent partout. Décision : Sonnet 5 partout par défaut. Détail dans `HOWHY.md` (D18).
- [x] Haiku 4.5 vérifié en réel : format JSON strict et réflexion à budget fonctionnent, aucune correction nécessaire.
- [x] Migration `run_details` exécutée dans Supabase (Clément).
- [x] Opus retiré du catalogue et des configurations, jugé surdimensionné (Clément). Justification dans `HOWHY.md` (D18).
- [x] **Admin › Runs** : chaque analyse enregistre sa configuration, son cas, son classement et son résultat (table `run_details`, RLS testée). Liste des runs avec la latence par étape, le coût et le top 3 ; comparaison de deux runs (durée, coût, étapes, classement et verdict) ; réouverture d'un résultat passé.
- [x] **Choix du modèle Claude par agent (admin)** : 3 configurations argumentées (Référence, Rédaction sur Haiku, Plancher de coût) ou réglage à la main, avec le coût estimé. Haiku : effort traduit en budget de réflexion. Opus et Fable écartés (surdimensionnés). Coût calculé au prix de chaque modèle. Décisions D18 et D19 dans `HOWHY.md`.
- [x] Stratège remis en effort élevé dans les secrets Streamlit (Clément).
- [x] Test de l'effort du stratège : en `medium`, le run passe de 110,5 s à 100,2 s, dont seulement 6,3 s gagnées sur le stratège (49,9 → 43,6 s), soit l'ordre des variations d'un run à l'autre. Décision : garder `high`. Conclusion dans `HOWHY.md` (D8).
- [x] Streamlit Cloud passé en Python 3.12, aligné sur la CI.
- [x] Run de référence mesuré (« Notifications & churn », effort du stratège `high`) : 110,5 s au total = analyste 29,3 s + stratège 49,9 s + story la plus lente 31,3 s. Aucune correction. 0,163 €. Tokens de sortie : analyste 2 903, stratège 4 623, rédacteurs 7 721 pour 3 stories.
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
