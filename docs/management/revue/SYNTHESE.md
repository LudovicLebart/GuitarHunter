# Synthèse des constats de la passe « deepdocument » (2026-11-06)

101 constats répartis en 11 fichiers (`R-<section>-<n>`). Cette page les classe pour la phase suivante (analyse, revues de code, corrections). Les gravités sont celles des fichiers d'origine ; plusieurs sont marquées « à confirmer » parce qu'elles reposent sur la lecture du code, non sur un essai. Rien n'a été corrigé pendant la passe.

| Fichier | Constats |
|---|---|
| `2026-donnees.md` | 8 |
| `2026-bot.md` | 10 |
| `2026-scraping.md` | 12 |
| `2026-ia.md` | 11 |
| `2026-connaissances.md` | 7 |
| `2026-api.md` | 12 |
| `2026-frontend.md` | 10 |
| `2026-restauration-pieces.md` | 6 |
| `2026-exploitation.md` | 11 |
| `2026-scripts.md` | 7 |
| `2026-plans-todo.md` | 7 |

## Lot 1 — À traiter en premier (sécurité, confidentialité, perte silencieuse)
1. **R-8-1** — photos d'annonces et fichiers de travail non suivis et non ignorés : un `git add -A` (que deux skills du projet exécutent) les publierait sur le dépôt **public**. Correction : `.gitignore` (quelques lignes).
2. **R-6-1** — le scan d'une adresse accepte n'importe quelle URL, visitée par le navigateur du serveur (à confirmer par un essai contrôlé).
3. **R-6-2** — une URL de photo ajoutée à une annonce partagée est téléchargée par le serveur et montrée à tous.
4. **R-6-3, R-6-4** — configuration de compte non validée ; chat Claude utilisable comme passerelle sans quota (coût).
5. **R-6-5 / R-1-2** — fil de chat commun à tous les utilisateurs d'une annonce (haute dès le premier utilisateur réel supplémentaire).
6. **R-3-2** — un blocage anti-bot fait marquer des annonces « vendues » à tort.
7. **R-4-1, R-4-2** — ré-analyse en file avec des URL Facebook périmées ; échec de l'Analyste enregistré comme analyse finale.

## Lot 2 — Fiabilité de l'exploitation
- **R-9-1** — déploiement vert même si le redémarrage d'un service échoue (aucune vérification `/health`).
- **R-2-1** — planificateur `schedule` global partagé entre threads utilisateur.
- **R-9-2, R-9-3, R-9-4, R-9-6** — un seul environnement (`dev` déploie en production), unités systemd hors dépôt, secret Tailscale recopié sur le serveur, dépendances non figées.
- **R-9-5** — 22 fichiers de test sur 66 hors de la CI, dont 5 inexécutables.
- **R-10-1, R-10-2** — onze scripts sur Firestore figé ; l'export de migration pourrait écraser la production s'il est relancé.

## Lot 3 — Bugs moyens et cohérence
- Scraping : **R-3-1** (`import time` local qui plante), autres constats de `2026-scraping.md`.
- Bot, IA, connaissances, restauration/pièces, frontend : voir chaque fichier ; aucun n'est classé haute en dehors de ceux ci-dessus.
- **R-9-8, R-9-9, R-9-10** — watchdog HA sans condition d'état du bot, dépendance Firestore résiduelle, journal bruyant « Scan config updated ».

## Lot 4 — Hygiène, code mort, documentation
- Code mort et scripts périmés : R-10-3 à R-10-6 (essais manuels nommés `test_*`, `migrate_images.py`, reliquat de `run_once.py`).
- Documentation : R-10-7, R-11-1 à R-11-7 ; les mentions de scripts absents sont inventoriées dans `reference/scripts.md`.

## Écarts relevés en clôture (section 12)
- **Liens relatifs** de `docs/` et `CLAUDE.md` : tous résolus (les 9 « cassés » détectés sont des exemples de gabarit : `img/<slug>/…`, `autre-fiche.md`, `url`).
- **Fichiers cités par la doc mais absents** :
  - `ARCHITECTURE.md` et `DATA_FLOW.md` citent encore `repository.py`, `firestoreService.js`, `BotControls.jsx`, `reanalyze_sold_deals.py` et six scripts supprimés ; ils gardent 79 et 32 mentions de Firestore (historique non trié). `DATA_FLOW.md` porte un bandeau d'avertissement et un tableau d'état par section.
  - `CLAUDE.md` (tableau « Fichiers Clés ») cite `src/components/DealCard.jsx` : c'est désormais un dossier `src/components/DealCard/` (`DealCardActions.jsx`, `DealCardImage.jsx`, …). À corriger par l'utilisateur, `CLAUDE.md` n'ayant pas été touché pendant la passe.
  - `COUVERTURE.md` cite `front.md`, qui n'existe pas (la référence s'appelle `frontend.md`) — à vérifier lors du prochain passage.
- **Reste à faire** (hors passe) : trier les mentions historiques de Firestore dans `ARCHITECTURE.md` et `DATA_FLOW.md` ; purger `TODO.md` (R-11-3) ; relire en entier les 21 plans et les branches actives ; lecture ligne à ligne des scripts ; essais contrôlés pour les constats « à confirmer ».
