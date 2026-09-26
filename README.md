# AI Product Owner Assistant

> **Du feedback client brut au backlog priorisé, puis aux user stories prêtes pour Jira.**
> Emails, tickets, verbatims NPS, notes d'appel : l'assistant les analyse, classe les besoins avec RICE et MoSCoW en justifiant chaque note, et rédige les user stories avec leurs critères d'acceptation Gherkin. Le PO garde la décision.

Le produit de la démonstration, **EwokAI**, est fictif : une plateforme SaaS de gestion de projets dont le Product Owner est submergé de retours clients.

- **Essayer** : [L'application en ligne](https://ai-po-assistant.streamlit.app), accès sur invitation
- **En une page** : [L'essentiel](docs/essentiel.md), l'ensemble en quatre blocs de cinq points
- **Comprendre** : [What, How, Why](docs/what-how-why.md), ce que fait l'assistant, comment il marche, et pourquoi l'IA ici et pas là
- **Les ajouts** : [Au-delà de la consigne](docs/au-dela-de-la-consigne.md), ce qui dépasse la consigne et pourquoi
- **Pour un lecteur technique** : le [journal des décisions](docs/decisions.md), chaque choix, ce qui a été écarté et à quel prix

Stack (la consigne n'impose aucune technologie) : Python · Streamlit · API Claude (Sonnet 5) · Supabase (Auth + PostgreSQL / RLS) · DuckDB.

---

## En bref

![Le parcours d'un run, de l'Inbox au backlog : les étapes IA en vert, les étapes de code en blanc](docs/img/parcours.svg)

- **Trois rôles d'IA spécialisés**, orchestrés par le code : l'analyste lit et regroupe les retours, le stratège estime Reach, Impact, Confidence et Effort, les rédacteurs écrivent les stories en parallèle.
- **L'IA pour le jugement, le code pour le reste** : le tri de l'Inbox, la vérification des citations, le calcul des scores, le MoSCoW et la mise en forme Gherkin ne passent pas par l'IA.
- **Un run type** (cas « Notifications & churn ») : environ 110 s et 0,16 €, 14 citations sur 14 retrouvées mot pour mot dans la source.

---

## Structure du code

| Fichier | Rôle |
|---|---|
| [`app.py`](app.py) | Point d'entrée Streamlit : garde d'authentification, espace PO (5 onglets), Connecteurs, onglet Admin |
| [`agents.py`](agents.py) | Logique métier : contrats Pydantic, prompts, passerelle Claude, 3 agents, orchestrateur, scoring, plafond budgétaire |
| [`governance.py`](governance.py) | Quotas (requête / jour / semaine / mois), fenêtres calendaires, **modèles ML** de coût et de prévision |
| [`store.py`](store.py) | Persistance de l'usage : `SupabaseRepository` (RLS) ou `SQLiteRepository` (dev) |
| [`auth.py`](auth.py) | Authentification Supabase (email + mot de passe) ou locale, fermée par défaut |
| [`analytics.py`](analytics.py) | Requêtes SQL (DuckDB) de la console admin, affichées telles quelles dans l'UI |
| [`reload_guard.py`](reload_guard.py) | Recharge les modules modifiés par un déploiement sans redémarrer le serveur |
| [`ui/`](ui/) | Écrans : `login`, `onboarding` (guide), `greeting`, `live` (progression en direct), `runs` (Admin › Runs), `connectors`, `admin`, `theme` (bascule clair/sombre), `session`, `style` |
| [`supabase/`](supabase/) | Migrations SQL (tables, RLS, trigger ; journal des agents ; détails des runs) + tests des policies |
| [`config.py`](config.py) · [`exporters.py`](exporters.py) · [`samples.py`](samples.py) | Configuration, exports Jira / Markdown / Gherkin / JSON, feedbacks de démo |
| [`triage.py`](triage.py) | Tri instantané de l'Inbox par règles (canal, urgence), sans IA |
| [`connectors.py`](connectors.py) | Feuille de route des connecteurs (Zendesk, Jira, Outlook…), affichée dans l'onglet Connecteurs |
| [`docs/`](docs/) | Documentation : What, How, Why ; Au-delà de la consigne ; L'essentiel ; journal des décisions techniques |
| [`tests/`](tests/) | 78 tests hors ligne (LLM simulé, UI via `AppTest`) + tests SQL des policies RLS en CI |

`agents.py` ne dépend pas de Streamlit : le même pipeline peut tourner dans un job batch, une API ou un bot Slack.

---

## Démarrage local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # puis : AUTH_MODE=local et LOCAL_DEV_PASSWORD=<votre choix>
streamlit run app.py
```

En mode `local`, deux comptes sont créés dans une base SQLite : `admin@local.dev` (admin) et `demo@local.dev` (membre avec quotas). Sans clé Anthropic, le **mode démo hors ligne** rejoue un vrai run Claude enregistré (Sonnet 5, 26/09/2026) ; c'est un filet de sécurité pour les démos live quand le réseau lâche.

Trois jeux de feedbacks « mot pour mot » sont préchargés : *Notifications & churn*, *Onboarding et migration*, *Mobile terrain et performance*. À la première connexion, un **guide de démarrage en 4 étapes** (le cas d'usage, les agents, choisir un cas, lancer) démarre la démo. Chaque onglet se termine par un bouton vers le suivant.

---

## Mise en ligne (Supabase + Streamlit Community Cloud)

**1. Supabase (≈ 5 min)**
1. Créez un projet sur [supabase.com](https://supabase.com).
2. *SQL Editor* : exécutez **dans l'ordre** les fichiers de [`supabase/migrations/`](supabase/migrations/) (`20260925000000_init.sql`, `20260926000000_agent_calls.sql`, puis `20260927000000_run_details.sql`). Chaque fichier peut être relancé sans risque.
3. *Authentication › Sign In / Providers* : désactivez **Allow new users to sign up**.
4. *Authentication › Users › Add user* : créez votre compte et ceux des relecteurs (cochez *Auto Confirm User*).
5. Promouvez-vous admin (*SQL Editor*) :
   ```sql
   update public.profiles
   set role = 'admin', max_eur_per_request = null, daily_eur_limit = null,
       weekly_eur_limit = null, monthly_eur_limit = null
   where email = 'vous@exemple.com';
   ```
6. *Project Settings › API Keys* : copiez l'**URL** du projet et la clé **publishable** (anon).

**2. Streamlit Community Cloud (≈ 3 min)**
1. [share.streamlit.io](https://share.streamlit.io) › *Create app* › ce dépôt, branche `main`, fichier `app.py`.
2. *Advanced settings* : Python 3.12, puis collez vos secrets au format de [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example).
3. *Deploy*. Les nouveaux comptes reçoivent des quotas par défaut (0,50 € / requête, 2 € / jour, 5 € / semaine, 10 € / mois), ajustables dans l'onglet Admin.

---

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Clé API (sans clé : mode démo) |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Modèle utilisé par les 3 agents |
| `ANTHROPIC_MAX_TOKENS` | `16000` | Plafond de sortie par requête |
| `ANTHROPIC_TIMEOUT_S` | `180` | Timeout HTTP par requête |
| `ANTHROPIC_MAX_RETRIES` | `2` | Retries automatiques (429 / 5xx / réseau) |
| `STORY_WORKERS` | `4` | Stories rédigées en parallèle |
| `EFFORT_ANALYST` / `_STRATEGIST` / `_WRITER` | `medium` / `high` / `medium` | Profondeur de raisonnement par agent |
| `SUPABASE_URL` / `SUPABASE_KEY` | — | Projet Supabase et clé *publishable* (obligatoires en production) |
| `AUTH_MODE` | `supabase` | `local` = comptes SQLite pour le développement |
| `LOCAL_DEV_PASSWORD` | — | Mot de passe des comptes locaux |
| `USD_TO_EUR` | `0.86` | Taux utilisé pour tous les montants en € |
| `APP_TIMEZONE` | `Europe/Paris` | Calendrier des quotas jour / semaine / mois |
| `ANTHROPIC_CREDITS_USD` | — | Crédit chargé sur la Console Claude : affiche le **crédit restant estimé** dans l'onglet Admin |

Sur Streamlit Community Cloud, déclarez ces variables dans *Secrets* : elles sont exposées comme variables d'environnement.

---

## Qualité

```bash
pip install -r requirements-dev.txt
pytest -q                          # 78 tests : LLM simulé, UI via AppTest, aucune clé ni aucun coût
ruff check . && ruff format --check .
DATABASE_URL=postgresql://postgres@localhost:5432/scratch scripts/test_schema.sh   # migration + RLS
```

La CI GitHub Actions exécute le lint et les tests Python, puis applique la migration sur un PostgreSQL 16 éphémère et vérifie chaque policy RLS.

Couverture : formule RICE, seuils MoSCoW, ordre du backlog, rendu Gherkin, auto-correction de la passerelle, refus et troncatures, mapping des erreurs SDK, plafond budgétaire, quotas et fenêtres calendaires, régression et prévision, dépôt SQLite, requêtes SQL admin, authentification (y compris le *fail closed*), parcours UI connexion → membre → admin.
