# Plan d'implémentation — Leaf Hunter, extension de Guitar Hunter

> Plan rédigé par Opus à partir de la doc et des fichiers clés du dépôt. Les éléments marqués « à vérifier » n'ont pas été confirmés dans le code.
>
> **État d'avancement (2026-11-22)** : décisions par défaut du §8 validées par l'utilisateur (réserve sur le rayon de distance, à revoir). **Phases 0, 1, 1b, 2, 3 et 4 faites** (tranche utile complète, non déployée ; phases 2 à 4 sur la branche de session `ccr-53ac32f1-id7v2n`, pas de PR) (bibliothèque pure, 73 tests, passage à blanc validé sur les vrais sites, non déployé). **Écarts par rapport au plan** : `beautifulsoup4` non ajouté (JSON-LD lu avec `json` + regex) ; lecture des fiches ajoutée en phase 1b (la liste tronque la description Kijiji et n'en donne aucune chez AutoHebdo) ; le trim Kijiji vient de `cartrim` (champ `values`). **Décision prise (2026-11-22)** : batterie 24 kWh remplacée = drapeau `battery_24_replaced`, pas un rejet. Suivi des cases : `docs/management/TODO.md`, section « Leaf Hunter ».
> Convention du dépôt : à déposer dans `docs/management/plans/LEAF_HUNTER_PLAN.md`. Aucune annonce réelle, URL ni identifiant ne doit être versionné (dépôt public).

## Résumé exécutif
1. **Option B recommandée** : nouvelles tables `vehicle_deals`, `user_vehicle_matches`, `user_vehicle_state`, `vehicle_price_history`, ajoutées sans toucher aux tables guitares. Infrastructure partagée réutilisée : `users.config` (clé `leafConfig`), `commands` (types `LEAF_*`), `logs`, `cities`, `llm_usage` (actions `leaf_t1/t2/t3`), `scrape_runs` (sources `leaf_*`).
2. Un discriminant `vertical` dans `guitar_deals` est écarté : des dizaines de requêtes à filtrer (index, nettoyage, réanalyse, doublons, chat…), risque de régression élevé.
3. Scraping en HTTP simple, sans Playwright : Kijiji (`__NEXT_DATA__`, objets `AutosListing`) et AutoHebdo (JSON-LD). CarGurus et AutoTrader reportés (blocage, conditions d'utilisation).
4. **Le code calcule, l'IA extrait** : SOH par regex, autonomie hivernale, comparaison au marché. Chaque champ IA doit citer un extrait réel de l'annonce, sinon « inconnu ».
5. Pipeline : Portier = règles déterministes (+ Qwen local optionnel) ; Analyste = Gemini Flash ; Expert = Sonnet 5.5 seulement pour les candidats forts ou sur demande.
6. Backend : module `backend/leaf/` appelé depuis la boucle `main.py`, logger enfant `bot.{uid8}.leaf`, double interrupteur (`leafConfig.enabled=false` par défaut + variable `LEAF_ENABLED`).
7. Frontend : route `#leaf` (comme `#fiches`), bascule « Guitares | Leaf » dans la Navbar, page `LeafPage` chargée à la demande.
8. Tranche minimale utile (phases 1 à 4) : scraping → Postgres → liste → ntfy, sans IA. L'IA vient ensuite.
9. Zéro régression : ajouts SQL idempotents, noms d'actions et de sources distincts, tests ajoutés à `deploy.yml`.

## 1. Décision d'architecture
- **Option A (discriminant `vertical`)** : un seul pipeline, mais 80 % de colonnes guitares vides pour une Leaf, et toutes les lectures existantes à filtrer. Rejetée.
- **Option B (retenue)** : tables dédiées + infrastructure partagée + petit module `backend/leaf/`. Pas de classe de base « Vertical » imposée à `GuitarHunterBot` (refactoring non demandé).
- **Option C (app/base séparée)** : duplique auth, déploiement, haute disponibilité. Rejetée.
- Migration : uniquement des `CREATE TABLE/INDEX IF NOT EXISTS`. Retour arrière = supprimer les 4 tables. `leafConfig` absent = désactivé.

## 2. Scraping
- **Kijiji** : recherche à l'échelle de la province, mot-clé « nissan leaf », filtre prix, tri par date, 1 à 3 pages ; filtre géographique en local par GPS (rayon propre à Leaf, 150 km par défaut). Parseur existant généralisé par un paramètre `prefixes` (comportement guitare inchangé). Identifiants `leaf_kijiji_<id>`.
- **AutoHebdo** : JSON-LD `ItemList`, année tirée de l'URL `my_YYYY`, km depuis `mileageFromOdometer`. Ville/GPS absents de la liste : compléter via la fiche seulement pour les annonces retenues (à vérifier).
- **Normalisation** (fonctions pures) : année, trim, km, capacité batterie inférée (2018 = 40 kWh ; 2016-2017 = 30 kWh sauf 2016 S « 24 possible »), SOH annoncé par regex avec preuve, drapeaux accident, mentions CHAdeMO / pneus d'hiver / pompe à chaleur / câble.
- **Doublons** : règle propre aux véhicules (VIN, sinon année + trim + km ±1 % + distance ≤ 10 km). On **marque** `duplicate_of` plutôt que de jeter.
- **Politesse** : ≥ 2 s entre requêtes, passage toutes les 2 h (plancher 60 min), arrêt au premier 403/429.
- **CarGurus / AutoTrader** : ne pas automatiser. Alternative : `LEAF_SCAN_URL` avec saisie manuelle prix/km/année/trim.
- **Facebook Marketplace** : possible plus tard (phase optionnelle).

## 3. Pipeline IA
- **Niveau 1 (gratuit)** : règles déterministes (24 kWh certain, accident/pièces, SOH annoncé < 80 %). Qwen3-VL local en option quand les règles ne tranchent pas. Si le Dell est indisponible, on ne rejette pas.
- **Niveau 2 (Gemini Flash)** : extraction en JSON strict, chaque champ `{value, evidence, confidence}`. Garde-fou : une citation absente du texte force « inconnu » (`ai_unsupported_claim`) ; la regex l'emporte sur l'IA (`ai_conflict`) ; déductions par photo plafonnées à `medium`.
- **Scores calculés en code** : `battery_score` (barème sur le SOH ; inconnu = « à mesurer avec LeafSpy »), `winter_fit` (autonomie nominale × SOH × facteur de froid, comparée à 50 km × marge 1,5), équipement d'hiver, `price_fit` (régression prix ~ année + km sur les annonces vues, dès 15 comparables), risque.
- **Verdicts** : `CANDIDAT_FORT`, `A_VERIFIER`, `BATTERIE_DOUTEUSE`, `TROP_CHER`, `HORS_CRITERES`, `INCOMPLET`.
- **Niveau 3 (Sonnet 5.5)** : sur `CANDIDAT_FORT` ou à la demande. Produit le verdict argumenté, les **questions à poser au vendeur**, les points d'inspection, un prix plafond sourcé. Les scores calculés lui sont fournis comme faits.
- **Prompts** : section `leaf` dans `prompts.json`, surchargeables dans `leafConfig.analysisConfig.prompts`.
- **Coûts** : chaque appel enregistré dans `llm_usage` (actions `leaf_t*`, distinctes de `t1_gatekeeper`) ; plafond quotidien et alerte ntfy. Volume attendu faible (non mesuré).

## 4. Backend
- `LeafHunter` instancié à côté du bot guitare, job planifié avec verrou anti-chevauchement, exceptions toujours capturées.
- Commandes `LEAF_REFRESH`, `LEAF_SCAN_URL`, `LEAF_ANALYZE`, `LEAF_CLEANUP` ; échec clair si Leaf est désactivé.
- Config `users.config.leafConfig` : `enabled`, `scanConfig` (fréquence, années, prix min/max, km max, ville de référence, rayon, sources), `analysisConfig`, `notify`. Valeurs par défaut : prix min 1 500 $, plafond 7 500 $, budget visé 6 000 $, km max 150 000.
- Logger enfant passé explicitement à chaque module (piège connu), préfixe `[Leaf]`.
- Notifications ntfy : nouvelle annonce, baisse de prix, candidat fort, santé du scraper. Sujet séparé `LEAF_NTFY_TOPIC` (hors dépôt).
- Nettoyage périodique des annonces vendues. Photos : URL distantes en MVP (pas de Firebase Storage).

## 5. API et base
- Tables : `vehicle_deals` (champs typés : année, trim, km, kWh, SOH + preuve, scores, drapeaux, VIN, source, GPS…), `user_vehicle_matches`, `user_vehicle_state` (favori, rejet, notes, checklist, inspection), `vehicle_price_history`, index et trigger `pg_notify`.
- Dépôt de données côté bot (`backend/leaf/repository.py`) et côté API (`backend/api/leaf_repo.py`, **autonome** pour ne pas casser le déploiement de l'API de prod).
- Endpoints : `GET /leaf/deals`, `GET /leaf/deals/{id}`, favori/rejet/notes, historique de prix, `/leaf/market`, `/leaf/runs`. Accès limité à Ludovic possible via une liste blanche d'uid dans `.env`.
- Tests dans le style existant, avec **données synthétiques** uniquement ; nouveaux modules ajoutés au job `tests` de `deploy.yml`.

## 6. Frontend
- `useLeafRoute` (hash `#leaf`), `LeafPage` en chargement paresseux, bascule dans la Navbar.
- Hooks et fonctions `leaf*` dans `apiService.js` ; ne pas passer par `DealsContext`.
- Réutilisation : `ImageGallery`, `CollapsibleSection`, `LogViewer`, `CitiesContext`, `SimpleMarkdown`.
- Composants propres : liste/tableau (année/trim, km, SOH, autonomie hivernale, prix vs marché, ville, drapeaux, verdict), fiche détaillée avec preuves et historique de prix, questions au vendeur copiables, checklist d'inspection, mémo LeafSpy, panneau de config, graphique marché, scan d'URL.
- Mobile : cartes empilées avec les colonnes clés.

## 7. Phases livrables
| # | Phase | Validation | Effort | Modèle |
|---|---|---|---|---|
| 0 | Décisions et plan formel | Réponses aux questions du §8 | S | FLASH |
| 1 | Bibliothèque pure Leaf (normalisation, filtres, règles, scoring, sources) + `--dry-run` | Tests verts ; dry-run sans écriture | M | PRO |
| 2 | Schéma et dépôts de données | Tests sur Postgres jetable ; tests guitare inchangés | M | PRO |
| 3 | Intégration au bot (scan, stockage, ntfy) | Un passage local crée les lignes et les logs `[Leaf]` ; `LEAF_ENABLED=false` = comportement actuel | M | PRO |
| 4 | API + page Leaf minimale (**fin de la tranche utile**) | `npm test` et `pytest` verts ; liste affichée en local | M-L | PRO |
| — | Déploiement dev puis prod | **Confirmation explicite requise** | — | — |
| 5 | IA niveaux 1 et 2 avec garde-fou des preuves | Rejeu sur 20-30 annonces : 0 champ sans preuve accepté ; coût lu dans `llm_usage` | L | PRO |
| 6 | Expert et questions au vendeur | Déclenchement seulement sur seuil ou demande | M | PRO |
| 7 | Marché, historique, nettoyage, temps réel | Vendues marquées ; `price_fit` après 15 comparables | M | PRO |
| 8 | Options : Facebook véhicules, URL manuelles, chat Leaf | Selon décisions | L | PRO |
| 9 | Documentation | Relecture | S | FLASH |

## 8. Risques et décisions ouvertes
**Risques (défaut proposé)** : régression guitare (ajouts seulement, double interrupteur) ; IA qui invente (calcul en code, citations obligatoires, « inconnu » par défaut) ; sources fragiles (`scrape_runs` + alertes) ; conditions d'utilisation (HTTP simple, délais, pas de CarGurus/AutoTrader) ; dépôt public (aucune donnée réelle) ; piège du logger ; API de prod (module autonome) ; dette Firebase→Postgres (ne rien ajouter côté Firestore/Storage) ; coût (niveau 2 après les règles, plafond quotidien) ; disponibilité du Dell (règles suffisantes).

**Questions pour Ludovic (recommandation)** :
1. Une seule base d'utilisateurs ? (oui)
2. Leaf visible par tous ou par toi seul ? (toi seul)
3. Généraliser à d'autres véhicules maintenant ? (non, noms « vehicle » suffisent)
4. Expert Sonnet 5.5 ou Opus ? (Sonnet, Opus à la demande plus tard)
5. Sujet ntfy séparé ? (oui)
6. Photos dans Firebase Storage ? (non en MVP)
7. Ville de référence et rayon ? (150 km par défaut)
8. Fréquence des passages ? (2 h)
9. Facebook Marketplace pour les autos, et à quelle phase ?
10. Seuils SOH ? (85 % visé, 80 % de rejet)

## 9. Documentation à mettre à jour
`docs/management/plans/LEAF_HUNTER_PLAN.md`, `docs/reference/ARCHITECTURE.md`, `DATA_FLOW.md`, `STATE_MODELS.md`, `CLAUDE.md` (commandes `LEAF_*`, actions `leaf_t*`, préfixe `leaf_`), `docs/management/TODO.md`, journal hebdomadaire + index, `docs/explanation/PROJECT_OVERVIEW.md`, option `docs/how-to/LEAF_HUNTER.md`.

## Non vérifié (à confirmer pendant les phases)
Forme exacte des `AutosListing` (VIN, type de vendeur) ; compatibilité de `build_search_url` avec la catégorie autos `c174` ; ville/GPS absents du JSON-LD AutoHebdo ; couplage de `MapView`, `VerdictBadge`, `ImageGallery`, `LogViewer` aux guitares ; correspondance entre les bases (bot, API prod, staging) ; classement de `scrape_health` par source.

## Référence fonctionnelle
Prototype autonome : `leaf_hunter.py` (Kijiji + AutoHebdo, filtres, SQLite de dédup, baisses de prix, ntfy), à absorber dans la phase 1.
