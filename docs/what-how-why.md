# What, How, Why

*Partie 1 · La réponse à la consigne*

> **En une phrase** : un assistant qui transforme un flot de retours clients (emails, tickets, NPS, notes d'appel…) en un backlog priorisé et justifié, puis en user stories prêtes pour Jira. Le PO garde la décision.

- **Essayer** : [L'application en ligne](https://ai-po-assistant.streamlit.app), accès sur invitation
- **Le code** : [github.com/clementbiteau/ai-po-assistant](https://github.com/clementbiteau/ai-po-assistant)
- **Le produit fictif** : EwokAI, une plateforme SaaS de gestion de projets (planning, Gantt, charge des équipes) pour PME et ETI

---

## 1. What : ce que fait l'assistant

### Le problème du PO

Le PO d'EwokAI ne manque pas d'idées : il en reçoit trop, par trop de canaux, sous des formes trop différentes. Un email de client mécontent, un ticket support, une note NPS, un message du CSM sur Slack, la remarque d'un commercial après un deal perdu. Tout paraît urgent, rien n'est comparable, et il faut pourtant décider de ce que l'équipe construira au prochain sprint.

### Trois temps, comme le travail du PO

1. **Analyser** : lire tous les retours, les regrouper en thèmes et en besoins, en gardant les preuves (des citations exactes).
2. **Prioriser** : estimer la valeur et le coût de chaque besoin, puis les classer avec RICE et MoSCoW, chaque note étant justifiée.
3. **Rédiger** : écrire les user stories des besoins prioritaires, avec des critères d'acceptation testables et une estimation de complexité.

Le PO garde la main : il peut corriger n'importe quelle estimation, et tout le classement se recalcule immédiatement.

### Le parcours dans l'application

Cinq onglets, dans l'ordre du travail : **Inbox → Analyse → Priorisation → User stories → Export**. Chaque onglet se termine par un bouton vers le suivant. Un guide de démarrage s'ouvre à la première connexion.

Trois cas clients sont prêts à l'emploi. Chacun contient un piège réaliste :

| Cas | Ce qu'il contient | Ce qu'il met à l'épreuve |
|---|---|---|
| Notifications & churn | 10 sources en français et en anglais : email de client mécontent, tickets, NPS, Slack du CSM, note d'un commercial | Un besoin porté par un seul client, mais dont dépend son renouvellement |
| Onboarding et migration | Essai gratuit, DSI bloquée par l'import depuis Jira, avis G2, remontées d'un avant-vente | Un déploiement de 900 licences que le tri par règles ne voit pas, mais que l'IA repère |
| Mobile terrain et performance | Conducteurs de travaux en zone sans réseau, tableau de bord lent, revue trimestrielle d'un grand compte | Distinguer une demande de fonctionnalité, un problème de performance et un simple compliment |

On peut aussi coller ses propres retours.

### Les neuf fonctionnalités attendues, et où les voir

| Attendu par la consigne | Ce que fait l'assistant | Onglet |
|---|---|---|
| Traiter les retours clients | Emails, tickets Zendesk, NPS, Slack, avis sur les stores, notes d'appel ; en français et en anglais | Inbox |
| Repérer les tendances et récurrences | Thèmes avec leur nombre de sources et leur tonalité ; un même besoin exprimé sur plusieurs canaux n'est compté qu'une fois | Analyse |
| Extraire les demandes | Chaque besoin est formulé comme un problème, avec les segments concernés, ses sources et des citations vérifiées | Analyse |
| Noter selon plusieurs critères | Reach, Impact, Confidence et Effort, chacun avec sa justification | Priorisation |
| Appliquer des méthodes (RICE, MoSCoW) | Score RICE, décision MoSCoW, et prise en compte des contraintes non négociables | Priorisation |
| Justifier les recommandations | Une justification par critère et un avis d'ensemble sur l'ordre à suivre | Priorisation |
| Générer des user stories | « En tant que… je veux… afin de… », avec contexte, hors périmètre, dépendances et questions ouvertes | User stories |
| Proposer des critères d'acceptation | 3 à 6 scénarios Gherkin (*Given / When / Then*), exportables pour les tests | User stories |
| Estimer la complexité relative | Effort de 1 à 5 dans RICE, et story points sur l'échelle de Fibonacci | User stories |

### Un exemple : le cas « Notifications & churn »

Dix sources sur six canaux donnent cinq thèmes et cinq besoins. Les quatorze citations présentées comme preuves sont toutes retrouvées mot pour mot dans les retours d'origine. Le backlog proposé :

| Ordre | Besoin | Score RICE | MoSCoW | La raison, en bref |
|---|---|---|---|---|
| 1 | Résumé quotidien et filtrage des notifications | 7 680 | Must | Touche 60 % des utilisateurs, fait gagner du temps chaque jour, effort modéré |
| 2 | SSO Azure AD et suppression automatique des comptes | 600 | Must | Non négociable : le renouvellement d'un client de 450 sièges en dépend |
| 3 | Vue de la charge de travail par personne | 2 400 | Should | Son absence a déjà fait perdre un deal |
| 4 | Notifications EwokAI dans Slack et Teams | 1 875 | Could | Demandé par les comptes les plus exposés au churn, mais plus coûteux et moins certain |
| 5 | Rapport d'avancement PDF automatique | 300 | Won't (pour l'instant) | Un contournement existe déjà |

Le SSO passe deuxième avec un score RICE bien plus faible que celui des besoins suivants : RICE mesure la portée, pas les obligations. C'est la contrainte non négociable qui le fait remonter. Avec RICE seul, il serait avant-dernier.

Les stories des trois premiers besoins sont rédigées d'office (de 5 à 8 points, 5 scénarios chacune) ; les autres le sont à la demande, en un clic.

---

## 2. How : comment ça marche

### Le parcours d'une analyse

![Le parcours d'un run, de l'Inbox au backlog : les étapes IA en vert, les étapes de code en blanc](img/parcours.svg)

Avant de lancer l'IA, l'application estime le coût du run et le compare au budget de l'utilisateur. Pendant le run, l'écran montre en direct ce que trouvent l'analyste et le stratège.

### Trois rôles spécialisés

| Rôle | Il reçoit | Il produit | Réflexion |
|---|---|---|---|
| **Analyste** | Les retours bruts et le contexte du produit | Une synthèse, des thèmes, des besoins formulés comme des problèmes, avec leurs sources et des citations ; les autres signaux (bugs, frictions, compliments) sont mis à part | Moyenne |
| **Stratège** | Les besoins de l'analyste | Pour chaque besoin : Reach, Impact, Confidence, Effort, chacun justifié ; les contraintes non négociables ; un avis sur l'ordre à suivre | Élevée : ses notes conditionnent toute la suite |
| **Rédacteur** (un par story, en parallèle) | Un besoin noté | La story, 3 à 6 scénarios, les story points, le hors périmètre, les dépendances, les questions ouvertes, une découpe si la story est trop grosse | Moyenne |

Chaque rôle a sa propre consigne (prompt), son format de réponse et son niveau de réflexion. On sait donc toujours quel rôle a produit quoi, et chacun se teste séparément.

> **Un agent ou trois ?**
>
> La consigne demande « un agent ». Pour le PO, c'est l'assistant : un seul outil, un seul parcours. À l'intérieur, le travail est confié à trois rôles spécialisés. Au sens strict, l'ensemble est un *workflow* : c'est le code qui enchaîne les étapes, et non l'IA qui décide elle-même de la suite.
>
> Ce choix est voulu. Le travail d'un PO suit des étapes connues (lire, juger, écrire). Un coût et une durée prévisibles, et la possibilité de tester chaque étape, comptent donc plus que l'autonomie. Un agent autonome prendrait son sens pour la suite : aller chercher lui-même les retours dans les outils, vérifier les doublons dans Jira, poser une question au PO quand un retour est ambigu.

### Les garde-fous

- **Des réponses au format imposé.** Chaque rôle répond dans une structure fixée à l'avance (un schéma JSON appliqué par l'API). Les échelles sont fermées : un Impact vaut forcément de 1 à 5, des story points sont forcément sur l'échelle de Fibonacci. L'interface ne peut pas casser sur une réponse inattendue.
- **Une validation, puis une seule correction.** Des règles métier vérifient chaque réponse (chaque besoin noté une fois, chaque scénario complet…). En cas d'erreur, elle est renvoyée à l'IA une fois, puis l'application s'arrête proprement avec un message clair.
- **Des preuves vérifiables.** Chaque citation est recherchée mot pour mot dans les retours d'origine. L'écran indique « vérifié dans la source » ou « possible paraphrase ».
- **Les retours sont traités comme des données.** Une instruction glissée dans un retour client (« ignore tes consignes… ») n'est pas suivie, et tout texte produit par l'IA est échappé avant l'affichage.
- **Le PO a le dernier mot.** Il corrige une estimation, le score et le classement se recalculent aussitôt.

### Un run en chiffres

Mesuré sur le cas « Notifications & churn », avec Claude Sonnet 5 :

| Durée | Coût | Citations exactes | Détail de la durée |
|---|---|---|---|
| Environ 110 s | Environ 0,16 € | 14 sur 14 | Analyste 29 s, stratège 50 s, puis les trois stories en parallèle (31 s pour la plus lente) |

Rédiger les stories en parallèle fait gagner près d'une minute : la durée totale est celle de l'analyste, du stratège et de la story la plus longue, et non la somme de toutes.

### L'architecture technique

| Couche | Choix | Rôle |
|---|---|---|
| Interface | Python et Streamlit | Les écrans, sans aucune logique métier |
| Logique métier | `agents.py` | Les trois rôles, les formats de réponse, le calcul des scores ; indépendant de l'interface, donc réutilisable dans une API ou un job de nuit |
| IA | API Claude (Sonnet 5) | Le modèle et le niveau de réflexion se règlent rôle par rôle |
| Comptes et données | Supabase (PostgreSQL) | Connexion sur invitation ; les droits sont appliqués dans la base elle-même (*Row Level Security*) |
| Qualité | 78 tests automatiques, intégration continue | Tests sans appel à l'IA (aucun coût), tests de l'interface, tests des règles de sécurité sur une vraie base PostgreSQL |

---

## 3. Why : pourquoi l'IA ici, et pas là

### La règle

**L'IA intervient là où il faut du jugement sur du texte libre. Le code intervient là où il faut un calcul, un format exact ou une décision que l'on doit pouvoir auditer.**

| Étape | Qui la fait | Pourquoi |
|---|---|---|
| Découper et trier l'Inbox (canal, urgence) | Des règles | Instantané, gratuit, explicable. Un tri grossier suffit pour voir l'urgent ; l'IA rattrape ensuite les nuances que les règles ratent. |
| Lire, regrouper, extraire les besoins | IA : l'analyste | Du texte libre, en deux langues, avec des formulations très variées : c'est du jugement sur du langage. |
| Vérifier les citations | Du code | Une IA peut reformuler une citation, voire l'inventer. Une recherche mot pour mot ne se trompe pas et ne coûte rien. |
| Estimer Reach, Impact, Confidence, Effort | IA : le stratège | Relier des preuves à une grille de notation demande du jugement, et ce jugement doit être justifié. |
| Calculer le score, le MoSCoW, l'ordre du backlog | Du code | Un calcul doit être exact, reproductible et corrigeable. Quand le PO change une estimation, tout se recalcule sans IA. |
| Rédiger la story et ses scénarios | IA : le rédacteur | De l'écriture en contexte : le bon persona, le bénéfice, les cas limites. |
| Mettre en forme le Gherkin, exporter | Du code | Un format exact : la syntaxe *Given / When / Then* est garantie par construction. |
| Estimer le coût d'un run, appliquer les budgets | Du code (une régression linéaire et des règles) | Une décision de dépense doit être prévisible et explicable. |

### Pourquoi RICE et MoSCoW ensemble

RICE chiffre, MoSCoW tranche. RICE seul sous-pondère les obligations : un SSO exigé par une DSI touche peu d'utilisateurs, mais sans lui le client part. D'où la règle : le MoSCoW découle du score RICE, relativement au meilleur score du lot, et une contrainte non négociable (sécurité, légal, contrat) force *Must*. Le backlog suit le MoSCoW, puis le score.

### Pourquoi Claude Sonnet 5

La consigne laisse le choix du modèle ; il a été fait par la mesure, sur le même cas :

- **Haiku 4.5**, le petit modèle, n'est ici ni plus rapide ni vraiment moins cher : il écrit beaucoup plus, ce qui le rend 1,5 à 2,4 fois plus lent par rôle, et seulement 20 % moins cher par run. Il découpe moins bien les besoins, a retouché une citation et commis une erreur de fait dans une synthèse.
- **Les modèles plus puissants** coûteraient 1,5 à 5 fois plus cher, pour une tâche qui applique une grille explicite.
- **Ce qui tient dans toutes les configurations** : le même trio de tête, et le SSO toujours reconnu comme non négociable. C'est l'effet du partage des rôles : le code calcule et applique les règles, donc le classement résiste au changement de modèle.

### Pourquoi ces outils

Aucune technologie n'était imposée. Python et Streamlit permettent de livrer vite une application de données interactive. Claude apporte des réponses au format garanti et un résumé de son raisonnement, affiché pendant le run. Supabase permet d'ouvrir l'application en ligne, en sécurité, à des relecteurs.

---

## 4. Limites connues et suites

- **Les tendances dans le temps.** L'assistant repère les récurrences dans un lot de retours, pas leur évolution d'une semaine à l'autre. Il faut pour cela un historique, que les connecteurs apporteraient (voir la partie 2).
- **Les estimations les plus fragiles** sont le Reach, déduit des mentions, et l'Effort, estimé sans connaître le code du produit : l'équipe technique doit le valider. Deux runs sur le même cas donnent des scores un peu différents ; le classement tient grâce aux règles, et les écarts fins s'arbitrent en revue.
- **Pas de mémoire du backlog.** L'assistant ne sait pas ce qui est déjà livré ou en cours. Une lecture de Jira comblerait ce manque.
- **Pas d'évaluation continue.** Pour faire évoluer les instructions données à l'IA sans risque, il faudrait un jeu de retours annotés, rejoué à chaque changement.

Le détail de chaque décision technique (ce qui a été choisi, ce qui a été écarté, à quel prix) est dans le [journal des décisions](decisions.md).
