# Journal d'Implémentation : Refonte Classification & UI "Expert"

## Objectif
Passer d'une classification binaire (Bon/Mauvais) à une classification granulaire orientée "Business" (Pépite, Flip, Projet, Casier) avec une UI hiérarchisée.

## État du Projet
- [ ] Phase 1 : Ingénierie du Prompt (Cerveau)
- [ ] Phase 2 : Adaptation Backend (Données)
- [ ] Phase 3 : Logique Frontend (Filtrage)
- [ ] Phase 4 : Interface Utilisateur (Affichage)

---

## Plan d'Action Détaillé

### Phase 1 : Ingénierie du Prompt (prompts.json)
L'IA doit apprendre les nouvelles règles de calcul et les nouvelles catégories.

1.  **Modifier `taxonomy_guitares`** : (Optionnel, si besoin de préciser les types d'étuis, mais probablement géré dans le prompt textuel).
2.  **Mettre à jour `verdict_rules`** : Définir strictement PEPITE, FAST_FLIP, LUTHIER_PROJ, CASE_WIN, etc.
3.  **Mettre à jour `main_analysis_prompt`** :
    *   Ajouter l'instruction de calcul "Règle de l'Étui".
    *   Ajouter l'instruction de calcul "Marge Brute".
    *   Forcer le nouveau format JSON de sortie.
4.  **Définir le nouveau Schéma JSON** :
    ```json
    {
      "verdict": "PEPITE",
      "reasoning": "...",
      "summary": "...",
      "classification": "Stratocaster",
      "confidence": 0.95,
      "specs": {
          "case_value": 50,
          "net_cost": 450,
          "resale_potential": 700,
          "profit_margin": 250,
          "repair_complexity": "MEDIUM"
      },
      "analysis": "..."
    }
    ```

### Phase 2 : Adaptation Backend (backend/analyzer.py)
Vérifier que le parser Python accepte et stocke la nouvelle structure sans erreur.

1.  **Vérification `analyzer.py`** : S'assurer que la méthode `_clean_json_response` et le stockage Firestore ne filtrent pas les nouveaux champs imbriqués (`specs`).
2.  **Script de Test Intermédiaire (Python)** :
    *   Créer un script `tests/test_prompt_logic.py` qui envoie une description statique à Gemini avec le NOUVEAU prompt pour valider qu'il respecte la logique (ex: une guitare à 100$ avec un étui à 100$ doit sortir en `CASE_WIN`).

### Phase 3 : Logique Frontend (src/hooks/useDealsManager.js)
Le frontend doit savoir trier ces nouvelles catégories.

1.  **Créer les Groupes de Température** :
    *   `RADAR` : [PEPITE, FAST_FLIP, LUTHIER_PROJ, CASE_WIN]
    *   `MARKET` : [COLLECTION, FAIR]
    *   `NOISE` : [BAD_DEAL, REJECTED_*, INCOMPLETE_DATA]
2.  **Mettre à jour `useDealsManager`** :
    *   Modifier `matchesVerdictFilter` pour supporter ces groupes.
    *   Ajouter une propriété `temperature` à chaque deal pour faciliter le rendu.

### Phase 4 : Interface Utilisateur (src/App.jsx & components)
Afficher les données riches.

1.  **Mettre à jour `DealCard.jsx`** :
    *   Afficher le badge "Marge" (ex: "+250$").
    *   Afficher l'icône "Luthier" si `repair_complexity` > LOW.
    *   Afficher le "Prix Net" (Prix - Étui).
2.  **Refondre `App.jsx`** :
    *   Remplacer la grille unique par 3 sections (Accordéons ou Sections fixes).
    *   Section "Radar" toujours ouverte.
    *   Section "Marché" repliable.
    *   Section "Bruit" en bas, repliée par défaut.

---

## Scripts de Test à Générer (À la demande)

1.  `scripts/inject_mock_deals.py` : Pour injecter des fausses annonces correspondant aux nouveaux verdicts (une PEPITE, un CASE_WIN, un BAD_DEAL) directement dans Firestore afin de développer l'UI sans attendre de vrais scans.
