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
- **ROI Moyen Estimé :** Ratio Marge / Coût par catégorie de guitare.
- **Corrélation Prix/Score :** Identifier les "Sweet Spots" (ex: "Où se trouvent les guitares entre 500$ et 1000$ avec un score > 8 ?").

## 3. Analyse Qualitative (Les 5 Scores)
Exploiter le JSON de l'Analyste pour une vue d'ensemble du marché :
- **Radar Chart "Profil de Marché" :** Moyenne des 5 scores sur l'ensemble du flux (Authenticité, État, Liquidité, Deal, Restauration).
- **Segmentation "Projets vs Flipping" :**
    - Volume de `LUTHIER_PROJ` (Restoration score élevé).
    - Volume de `PEPITE/FAST_FLIP` (Liquidity & Deal score élevés).

## 4. Performance & Vitesse (Rotation)
- **Time-to-Sold :** Temps écoulé entre l'entrée en base et le passage au statut `sold`.
- **Véracité IA :** % d'annonces `sold` qui avaient un `deal_score > 7` (Validation de la pertinence de l'IA).

## 5. Géographie des Opportunités
- **Heatmap :** Répartition des "Pépites" par ville/secteur scrapé pour optimiser le rayon de recherche.

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

---

> [!IMPORTANT]
> **Influence du Tier 3 :** L'Expert Pro apporte une "Certification" des données. 
> Une statistique basée sur une analyse Tier 3 aura un indice de confiance bien plus élevé qu'une stat Tier 2. Le Dashboard affichera des badges "Certifié Expert" sur les KPIs financiers les plus critiques.
