# Réflexion : Statistiques & KPIs (Impact Tier 3)

L'introduction de l'entonnoir d'analyse à 3 niveaux (Portier, Analyste, Expert) et des scores granulaires (0-10) ouvre de nouvelles perspectives pour le Dashboard.

## 1. Le Tunnel de Conversion (Funnel Analytics)
Ce graphique permet de visualiser l'efficacité du filtrage.
- **Volume Brut :** Nombre total d'annonces scrapées.
- **Filtrage Portier (Tier 1) :** % d'annonces rejetées immédiatement (bruit).
- **Potentiel Identifié (Tier 2) :** Volume traité par l'Analyste.
- **Le "Haut du Panier" (Tier 3) :** Volume ayant déclenché l'Expert Pro (les dossiers "Jackpot" ou "Haute-Fidélité").

## 2. Indicateurs Financiers (Predictions vs Réalité)
Basé sur les champs `net_guitar_cost` et `estimated_gross_margin`.
- **Marge Potentielle Totale :** Somme des marges estimées sur les deals `active` avec un `deal_score > 7`.
- ✅ **Marge Moyenne par Catégorie (implémenté 2026-08-06)** : `StatsView.jsx::categoryData` — proxy de "ROI par catégorie" basé sur `estimated_gross_margin` (pas de vrai ratio marge/coût, `net_guitar_cost` n'étant pas indexé). Catégorie résolue via une taxonomie simplifiée (exact + leaf uniquement, sans la recherche floue de `useDealsManager.js`).
- ✅ **Corrélation Prix/Score, "Sweet Spot" (implémenté 2026-08-06)** : `StatsView.jsx::priceScoreData` — score IA moyen (et marge moyenne) par tranche de prix (0-250$, 250-500$, 500-1000$, 1000-2000$, 2000$+).

## 3. Analyse Qualitative (Les 5 Scores)
Exploiter le JSON de l'Analyste pour une vue d'ensemble du marché :
- ✅ **Radar Chart "Profil de Marché" (fiabilisé 2026-08-06)** : Moyenne des 5 scores sur l'ensemble du flux (Authenticité, État, Liquidité, Deal, Restauration). Les 5 scores sont désormais tous indexés individuellement (`deals_index`, voir `ARCHITECTURE.md`/`DATA_FLOW.md`) — auparavant, seule leur moyenne l'était et `deal_score` y était silencieusement substitué, biaisant le Radar pour toute annonce non ouverte en entier par l'utilisateur.
- **Segmentation "Projets vs Flipping" :**
    - Volume de `LUTHIER_PROJ` (Restoration score élevé).
    - Volume de `PEPITE/FAST_FLIP` (Liquidity & Deal score élevés).

## 4. Performance & Vitesse (Rotation)
- **Time-to-Sold :** Temps écoulé entre l'entrée en base et le passage au statut `sold`.
- ✅ **Véracité IA (implémenté 2026-08-06)** : `StatsView.jsx::aiAccuracyData` — % d'annonces `sold` avec un score IA élevé (≥7/10) comparé au % dans l'ensemble du marché. Nuance : `sold` fusionne "vraiment vendue" et "supprimée par le vendeur" (`_perform_cleanup()`, voir `ARCHITECTURE.md`) — pas une mesure pure de succès de vente, mais le meilleur proxy disponible sans donnée de transaction réelle.
- ✅ **Vitesse de vente réelle vs Liquidité prédite → Explorateur de Corrélations (implémenté 2026-08-06, refondu 2026-08-17)** : `src/components/DealsExplorer.jsx` — nuage de points générique (un point = une annonce, sans moyenne ni regroupement) avec Axe X/Axe Y choisis librement parmi 8 métriques (les 5 scores IA, prix, marge estimée, délai de vente réel `soldTimestamp - publishTimestamp`), coloration optionnelle (Verdict/Source/Catégorie, groupes fixes) et filtre Ville, coefficient de corrélation de Pearson + régression recalculés pour la paire choisie. Répond directement à la question "l'IA prédit-elle correctement quelles annonces se vendront vite ?" — et, plus généralement, à toute question de corrélation entre deux métriques du marché. ⚠️ **La toute première version (par tranches Faible 0-4/Moyenne 5-7/Élevée 8-10, moyenne du score par tranche) produisait une droite quasi garantie par construction** — les tranches étant définies par ce même score, leur moyenne interne ne pouvait qu'augmenter avec l'ordre des tranches, peu importe la vraie relation avec la vitesse de vente (repéré par l'utilisateur : "les résultats prédits par l'IA forment une droite, c'est très suspect"). Une tentative intermédiaire (tranches par tertile de vitesse RÉELLE plutôt que de score, pour rester non-circulaire tout en gardant un format à 2 courbes) a ensuite été elle-même abandonnée : l'utilisateur a fait remarquer qu'un regroupement quel qu'il soit n'apportait rien face à la question posée en clair ("pour chaque vitesse de vente, quelle corrélation avec le score IA ?") — le nuage de points sur valeurs individuelles est la réponse directe, sans artefact de binning possible. Voir `JOURNAL.md` (2026-08-17) pour l'historique complet des trois versions.

## 5. Géographie des Opportunités
- ✅ **Implémenté 2026-08-06** : `StatsView.jsx::geoOpportunityData` — volume + marge moyenne des verdicts d'opportunité (`RADAR_GROUP`) par ville (`deal.location`), top 8. Barres plutôt qu'une heatmap cartographique (pas de nouvelle dépendance de cartographie pour un premier passage).

---

## 6. Nouveaux Prérequis de Données (Backend)
Pour alimenter ce dashboard en production, le backend Python devra être étendu pour récolter/générer les métadonnées suivantes :

- **`soldAt` (Timestamp) :**
  - **Besoin :** Indispensable pour calculer la "Vitesse de Rotation" (Time-to-Sold).
  - **Où :** Lors du passage au statut `sold` dans `cleanup_sold_listings`.
- **`brand` (String) :**
  - **Besoin :** Permettre le filtrage et le classement par marque (ex: "Top 5 marges par marque").
  - **Où :** À extraire explicitement par Gemini dans le JSON de l'Analyste (Tier 2).
- **`age_hours` (Number) ou `publishedAt` (Timestamp) :**
  - **Besoin :** Détecter les "Cold Deals" (annonces anciennes qui ont l'air bonnes sur le papier mais qui sont invendables en réalité).
  - **Où :** Estimation textuelle demandée à Gemini ou scraping de la date Facebook (plus complexe).
- **`discount_index` (Number) :**
  - **Besoin :** Calcul simplifié : `(Prix Demandé - Valeur Estimée) / Valeur Estimée`. Représente la décote immédiate ressentie.

## 7. Qualité IA : Erreurs du Portier (Implémenté 2026-07-11)

Axe absent de la réflexion initiale ci-dessus, ajouté suite à un cas concret : une annonce rejetée par le Portier (Tier 1) puis validée en Pépite après réanalyse manuelle. Plutôt qu'un axe purement financier ou de volume, celui-ci mesure la **fiabilité du filtre d'entrée lui-même** :
- **Erreurs Portier corrigées** : parmi les annonces initialement arrêtées au Portier seul, combien ont été réanalysées avec succès jusqu'à l'Analyste ou plus. Implémenté dans `StatsView.jsx` via `initialVerdict`/`initialModelUsed` (`ARCHITECTURE.md`).
- Complète l'échantillonnage manuel ponctuel déjà existant (`analyze_funnel_by_user.py --sample-size`, `GEMINI_PROMPT_CACHING_PLAN.md §8.2`) par un taux mesuré en continu, sans script à lancer.
- Limite actuelle : ne capture que les réanalyses **déclenchées manuellement** par l'utilisateur — ne détecte pas les faux positifs jamais revus.

## 8. Comparaison Multi-Plateforme (Implémenté 2026-08-06)

Axe apparu avec l'intégration de Kijiji (voir `ARCHITECTURE.md` § `bot.py::_run_kijiji_scan`) — permet de juger objectivement si une source apporte une vraie valeur ajoutée plutôt que du simple volume :
- **`StatsView.jsx::sourceComparisonData`** : volume, prix moyen, marge moyenne et taux d'opportunités (verdicts `RADAR_GROUP`), par source. Source dérivée du préfixe `kijiji_` de l'ID (même convention que le backend), pas du champ `link` (absent de l'index léger).

---

> [!IMPORTANT]
> **Influence du Tier 3 :** L'Expert Pro apporte une "Certification" des données. 
> Une statistique basée sur une analyse Tier 3 aura un indice de confiance bien plus élevé qu'une stat Tier 2. Le Dashboard affichera des badges "Certifié Expert" sur les KPIs financiers les plus critiques.
