# Au-delà de la consigne

*Partie 2 · Les ajouts, et pourquoi ils sont là*

La consigne décrit un cœur : analyser, prioriser, rédiger. Ce cœur tient dans cinq onglets. Tout ce qui s'y ajoute suit deux règles :

1. **Ne pas alourdir le parcours du PO.** Un ajout n'entre dans le parcours que s'il sert directement le PO ; sinon, il est rangé à côté.
2. **Le rendre visible.** Dans l'application, ce qui dépasse la consigne est affiché en pâle (les onglets Connecteurs et Admin, le réglage des modèles), avec la légende « En pâle : ajouts au-delà de la consigne ». On distingue ainsi d'un coup d'œil le sujet et ses extensions.

---

## 1. Dans le parcours du PO

Ces ajouts ne sont pas en pâle : ils rendent les fonctionnalités demandées plus utiles au quotidien.

| Ajout | Ce qu'il apporte au PO | Où le voir |
|---|---|---|
| Tri instantané de l'Inbox | Le PO submergé voit d'abord l'urgent. Le canal et l'urgence de chaque message sont calculés par des règles, avant tout appel à l'IA, et le message d'accueil les résume (« 10 notifications, dont 5 en urgence »). | Inbox |
| Vérification des citations | Une preuve exacte à montrer aux parties prenantes. Une citation reformulée par l'IA est signalée. | Analyse |
| Correction des estimations | Le PO n'est pas tenu d'accepter les notes de l'IA : il en change une, et le score, le MoSCoW et l'ordre du backlog se recalculent. | Priorisation |
| Exports | Jira (CSV), Markdown, fichiers Gherkin `.feature` pour les tests, JSON : les stories entrent dans les outils de l'équipe. | Export |
| Progression en direct | Un run dure environ deux minutes. Le PO voit l'IA avancer (sa réflexion résumée, les thèmes et les besoins trouvés) au lieu d'un écran figé. | Pendant un run |
| Guide de démarrage | Une prise en main sans formation, proposée une seule fois par personne, et que l'on peut rouvrir à tout moment. | Première connexion |
| Mode démo hors ligne | Rejoue un vrai run enregistré, avec ses vrais résultats, si le réseau fait défaut. | Barre latérale |

---

## 2. Ouvrir l'application en ligne, en sécurité

L'application est en ligne, le code est public et chaque run consomme de l'argent réel. Sans les ajouts suivants, impossible de la confier à des relecteurs.

- **Une connexion sur invitation.** Les inscriptions sont fermées : seuls les comptes créés par l'administrateur peuvent se connecter. Sans configuration, l'application reste verrouillée. L'accès est bloqué une minute après cinq échecs.
- **Des droits appliqués dans la base.** Les règles sont écrites dans PostgreSQL (*Row Level Security*), pas dans l'interface. Un membre ne voit que ses propres runs, et ne peut ni modifier son budget ni se donner le rôle d'admin, même en appelant la base directement. Ces règles sont testées automatiquement à chaque modification du code.
- **Des budgets par utilisateur.** Chacun a un plafond par requête, par jour, par semaine et par mois. Avant un run, son coût est estimé (une régression linéaire sur les runs passés) et comparé au budget restant : un run trop cher est refusé avant d'avoir coûté quoi que ce soit. Pendant le run, le plafond est vérifié avant chaque appel à l'IA.

---

## 3. Piloter comme en production : la console Admin

Réservée aux administrateurs, elle ne montre que l'usage réel.

| Onglet | Ce qu'il montre | À quoi il sert |
|---|---|---|
| Usage et coûts | Dépense, tokens, runs bloqués, pour chaque rôle de l'IA et chaque utilisateur. Chaque graphique affiche la requête SQL qui le produit. | Savoir ce que coûte l'outil, et qui l'utilise |
| Runs | Chaque analyse avec sa configuration, sa durée par étape, son coût et son trio de tête. Deux runs se comparent côte à côte ; un résultat passé se rouvre sans relancer l'IA. | Défendre un choix de modèle par la mesure |
| Agents | Le journal de chaque appel à l'IA : durée, tokens, réflexion résumée, extrait de la réponse. | Comprendre ce que fait chaque rôle, et pourquoi |
| Prévisions | Le modèle qui estime le coût d'un run, et la projection de la dépense du mois. | Anticiper la facture |
| Quotas | Le rôle et les budgets de chaque utilisateur, modifiables dans un tableau. | Ouvrir l'outil à plus de monde, sans risque |

**Le réglage des modèles** (barre latérale, pour les admins) propose trois configurations argumentées, ou un réglage rôle par rôle, avec le coût estimé de chacune :

| Configuration | Analyste · Stratège · Rédacteur | L'hypothèse testée |
|---|---|---|
| Référence (par défaut) | Sonnet 5 partout, réflexion élevée pour le stratège | Le meilleur équilibre entre qualité, coût et durée |
| Rédaction sur Haiku | Sonnet 5 · Sonnet 5 · Haiku 4.5 | La rédaction est la tâche la plus cadrée, et celle qui écrit le plus |
| Plancher de coût | Haiku 4.5 partout | Ce que la qualité perd au prix minimal |

C'est ce réglage, avec l'onglet Runs, qui a permis de choisir Sonnet 5 sur des mesures plutôt qu'à l'intuition (partie 1, section 3). Autre exemple : passer le stratège en réflexion moyenne fait gagner 10 secondes sur 110, sans changer le trio de tête. Le gain est trop faible pour risquer la qualité des notes : la réflexion élevée est gardée.

---

## 4. Préparer la suite : l'onglet Connecteurs

Aujourd'hui, les retours sont collés à la main. L'onglet Connecteurs montre comment ils arriveraient seuls, en trois phases. Aucun connecteur n'est actif : le POC ne demande jamais d'identifiants d'un autre service.

| Phase | Connecteurs | Pourquoi dans cet ordre |
|---|---|---|
| 1 · Le socle | Zendesk, Jira (en entrée et en sortie), Outlook / Gmail | L'essentiel des retours arrive par le support et l'email ; le backlog part dans Jira |
| 2 · La voix du client élargie | Slack / Teams, outil NPS, App Store / Google Play | Plus de volume, des signaux plus courts |
| 3 · L'enjeu business | Salesforce / HubSpot | Relier chaque besoin au chiffre d'affaires : deal perdu, renouvellement |

- **Les connecteurs lèvent les deux principales limites de la partie 1.** Jira en entrée donne à l'assistant la mémoire du backlog existant. Des retours qui arrivent en continu constituent l'historique nécessaire pour suivre les tendances dans le temps.
- **Ils s'emboîtent dans l'existant.** Leurs messages portent les mêmes en-têtes que les cas de démonstration (`[ZENDESK #…]`, `[EMAIL]`…) : le tri par règles les classe sans changement, ce qu'un test vérifie.
- **Les principes de production sont posés** : accès en lecture seule et minimal, autorisations gérées côté serveur, données personnelles pseudonymisées avant l'envoi à l'IA (RGPD), dédoublonnage entre canaux, validation du PO avant tout envoi vers Jira.

---

## 5. Les cinq raisons, en résumé

1. **La transparence des coûts.** Chaque run est chiffré, avant et après. Un outil d'IA qui ne dit pas ce qu'il coûte ne passe pas en production.
2. **Gouverner les modèles et les rôles.** La durée, le coût et la qualité de chaque configuration sont visibles et comparables. Un choix de modèle se défend par des mesures.
3. **Un humain dans la boucle, aussi côté administration.** L'admin change un levier (modèle, niveau de réflexion), relance, compare, et garde ce qui marche.
4. **Une trajectoire du POC à la production.** Les connecteurs décrivent les étapes suivantes, dans un ordre justifié.
5. **Un actif réutilisable.** La logique métier est séparée de l'interface, testée et documentée. Elle peut servir dans une API, un traitement de nuit, ou pour un autre client aux besoins proches.

## 6. Ce qui a été volontairement laissé de côté

- **Des connecteurs actifs** : ils demanderaient des accès à de vrais outils, ce qui dépasse le cadre d'un POC.
- **Un agent autonome** : imprévisible en coût et en durée, pour un travail dont les étapes sont connues (partie 1, section 2).
- **Un modèle plus puissant** : plus cher, sans gain mesuré sur cette tâche.
- **D'autres fournisseurs d'IA** : possibles, l'appel au modèle étant isolé dans un seul fichier, mais l'application s'appuie sur des fonctions propres à l'API Claude (format de réponse garanti, résumé du raisonnement).
