# Journal d'Implémentation : Refonte Classification & UI "Expert"

## Objectif
Passer d'une classification binaire (Bon/Mauvais) à une classification granulaire orientée "Business" (Pépite, Flip, Projet, Casier) avec une UI hiérarchisée, tout en restaurant la modularité du prompt pour la personnalisation.

## État du Projet
- [x] Phase 1 : Ingénierie du Prompt (Cerveau) - **Terminée**
- [x] Phase 2 : Adaptation Backend (Données) - **Terminée**
- [ ] Phase 3 : Logique Frontend (Filtrage)
- [x] Phase 4 : Interface Utilisateur (Affichage) - **Partiellement terminée**

---

## Plan d'Action Détaillé (Version Corrigée)

### Phase 1 : Ingénierie du Prompt (prompts.json) - **Mise à jour**
Restauration de la modularité du prompt et intégration des nouvelles règles.

1.  **Restaurer la Structure Modulaire de `prompts.json`** :
    *   Conserver les clés modulaires existantes : `persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`, `taxonomy_guitares`, `gatekeeper_verbosity_instruction`, `expert_context_instruction`.
    *   **Supprimer la clé `main_analysis_prompt`** car elle est redondante et source de confusion.
    *   **Ajouter une nouvelle clé `json_output_format`** qui définit la structure JSON exacte attendue, y compris le bloc `specs` avec `case_value`, `net_cost`, `resale_potential`, `profit_margin`, `repair_complexity`.
    *   **Mettre à jour le contenu** des clés modulaires (`persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`) pour être concis et refléter les nouvelles exigences (directives de calcul, nouveaux verdicts).
    *   **Mettre à jour `system_structure`** pour utiliser des placeholders pour toutes ces parties modulaires, y compris `{json_output_format}`.
    *   **Statut : Terminé.**

### Phase 2 : Adaptation Backend (backend/analyzer.py) - **Mise à jour**
Adapter le `DealAnalyzer` pour assembler le prompt dynamiquement et gérer le nouveau format.

1.  **Modifier `DealAnalyzer.__init__`** :
    *   Charger toutes les parties modulaires du prompt (`persona`, `verdict_rules`, etc.) et le template `system_structure` depuis `prompts.json` (ou depuis `firestore_config` si elles y sont stockées).
2.  **Refactoriser `_construct_user_prompt`** :
    *   Cette méthode prendra désormais toutes les parties modulaires et le template `system_structure`.
    *   Elle assemblera dynamiquement la chaîne de prompt finale en remplaçant les placeholders dans `system_structure` par le contenu des parties modulaires.
    *   S'assurer que `gatekeeper_verbosity_instruction` et `expert_context_instruction` sont appliquées correctement comme ajouts finaux au prompt assemblé, garantissant leur effet de concision.
3.  **Vérification `_clean_json_response`** : S'assurer que la méthode gère correctement le nouveau format JSON avec le bloc `specs`.
    *   **Statut : Terminé.**

### Phase 3 : Logique Frontend (src/hooks/useDealsManager.js) - **Inchangée pour l'instant**
La logique de filtrage et de comptage devrait déjà être compatible avec les nouveaux verdicts.

1.  **Créer les Groupes de Température** :
    *   `RADAR` : [PEPITE, FAST_FLIP, LUTHIER_PROJ, CASE_WIN]
    *   `MARKET` : [COLLECTION, GOOD_DEAL, FAIR]
    *   `NOISE` : [BAD_DEAL, REJECTED_ITEM, REJECTED_SERVICE, INCOMPLETE_DATA, ERROR, DEFAULT]
2.  **Mettre à jour `useDealsManager`** :
    *   Modifier `matchesVerdictFilter` pour supporter ces groupes.
    *   Ajouter une propriété `temperature` à chaque deal pour faciliter le rendu. (Cette étape sera affinée lors de la phase 4 si nécessaire).

### Phase 4 : Interface Utilisateur (src/App.jsx & components) - **Mise à jour**
Afficher les données riches et les nouvelles valeurs.

1.  **Mettre à jour `DealCard.jsx`** :
    *   Afficher le badge "Marge" (ex: "+250$").
    *   Afficher l'icône "Luthier" si `repair_complexity` > LOW.
    *   Afficher le "Prix Net" (Prix - Étui).
    *   **Ajouter l'affichage de la "Valeur de revente en l'état" (`estimated_value`) et de la "Valeur après restauration" (`specs.resale_potential`).**
    *   **Statut : Terminé.**
2.  **Refondre `App.jsx`** :
    *   Remplacer la grille unique par 3 sections (Accordéons ou Sections fixes).
    *   Section "Radar" toujours ouverte.
    *   Section "Marché" repliable.
    *   Section "Bruit" en bas, repliée par défaut.

---

## Scripts de Test à Générer (À la demande)

1.  `scripts/inject_mock_deals.py` : Pour injecter des fausses annonces correspondant aux nouveaux verdicts (une PEPITE, un CASE_WIN, un BAD_DEAL) directement dans Firestore afin de développer l'UI sans attendre de vrais scans.
2.  `tests/test_prompt_logic.py` : Pour valider que le prompt assemblé et le `DealAnalyzer` fonctionnent comme prévu avec les nouvelles règles et le format JSON.
