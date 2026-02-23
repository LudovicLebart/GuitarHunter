# Plan : Entonnoir d'Analyse en 3 Niveaux (v2)
> ⚠️ Document de travail — à retravailler avant implémentation.

## Architecture Cible

```
PORTIER (flash-lite) ──► rejet ──► FIN
        │
        ▼ passe
ANALYSTE (flash) ──► JSON compact + scores numériques
        │
        ▼ si scores déclencheurs
EXPERT PRO (pro) ──► JSON complet + rapport Markdown enrichi
```

---

## Tier 1 : Portier (inchangé)
`gemini-2.5-flash-lite` — filtre le bruit, renvoie `{status, reasoning}`. Pas de changement.

---

## Tier 2 : Analyste (Flash — Condensé + Scores)

### Champ `analysis` (Compact) & Indices Numériques
Ici, on impose un format puce pour `analysis` et on génère 4 scores (deal, authenticity, condition, liquidity) de 0 à 10.
Voici à quoi ressemble la sortie exacte pour l'annonce réelle **"Vintage Supertone parlor"** (ID: 820764234329233) :

```json
{
  "verdict": "LUTHIER_PROJ",
  "reasoning": "Guitare vintage avec un manche tordu, idale pour un projet slide.",
  "classification": "Parlor Standard",
  
  "estimated_value": 350,
  "estimated_case_value": 0,
  "net_guitar_cost": 120,
  "resale_potential": 350,
  "estimated_gross_margin": 230,
  
  "analysis": "### LUTHIER_PROJ | Confiance : 85%\n- 🔍 **Visuel :** Supertone parlor vintage (annes 30-50). Finition sunburst use, pochoir hawaen intact. Le manche est tordu.\n- 💰 **Financier :** Achat 120$  Valeur restaure/slide ~350$ = **+230$ de marge**.\n- 🔧 **Travaux :** Nettoyage (Facile), vrification barrage (Moyen), montage cordes fortes pour slide (Moyen).\n- ⚠️ **Risques :** Le manche tordu est un dfaut majeur pour un jeu standard, l'instrument est rserv  une niche (slide).",
  
  "confidence": 0.85,
  "deal_score": 6,
  "authenticity_score": 9,
  "condition_score": 3,
  "liquidity_score": 4,
  "restoration_interest_score": 8,
  
  "summary": "Supertone parlor vintage \u00e0 120$. Parfaite pour le jeu en slide malgr\u00e9 un manche tordu. Potentiel de 230$ de marge apr\u00e8s nettoyage.",
  "pro_analysis_required": false
}
```
*Ici, `pro_analysis_required` est false (car deal_score < 7 et prix < 1000$). L'analyse s'arrête donc ici sans appeler l'Expert.*

### 5 Nouveaux Indices Numériques (0–10)

| Champ JSON | Description | Usage |
|---|---|---|
| `deal_score` | Attractivité globale (prix vs marge) | Tri frontend + déclencheur Pro |
| `authenticity_score` | Probabilité authenticité (10=certifié, 1=contrefaçon) | Déclencheur Pro + badge UI |
| `condition_score` | État visuel estimé (10=neuf, 1=épave) | Affichage étoiles UI |
| `liquidity_score` | Facilité de revente rapide (10=bestseller, 1=niche) | Aide à la décision |
| `restoration_interest_score` | Richesse pédagogique/challenge (10=neck reset+frettage, 1=nettoyage) | Détection des "projets jackpot" |

---

## Tier 3 : Expert Pro — Conditions de Déclenchement

Le modèle Pro est coûteux, il n'est déclenché que si **AU MOINS UNE** de ces conditions est remplie :

| Condition | Seuil Logique | Raison |
|---|---|---|
| Score attractivité fort | `deal_score >= 8` | Très forte opportunité financière |
| **Combo Jackpot (Marge + Défi)** | `deal_score >= 6` **ET** `restoration_interest_score >= 7` | Opportunité financière ET projet de lutherie très instructif |
| Authenticité douteuse | `authenticity_score <= 5` | Risque légal/financier à valider |
| Confiance faible | `confidence < 0.75` | L'Analyste (Flash) avoue ses doutes |
| Prix élevé | `prix extrait > 1000$` | Ticket d'entrée élevé, double vérification requise |
| Auto-signalement | `pro_analysis_required: true` | Décision explicite et souveraine de l'Analyste |

Quand déclenché : l'Expert Pro reçoit le JSON compact de l'Analyste en contexte et produit une analyse **complète et détaillée**, remplaçant les données.

---

## Fichiers à Modifier

| Fichier | Nature du changement |
|---|---|
| `backend/analyzer.py` | Refactoring `analyze_deal()` + nouvelle méthode `_extract_price()` |
| `prompts.json` | 2 nouvelles clés + mise à jour du `FORMAT JSON STRICT` |
| `config.py` | 5 nouvelles constantes, 1 clé dans `GEMINI_MODELS` |

### Détail : `analyzer.py`
1. Nouvelle méthode `_extract_price(price_str) -> int`
2. Tier 2 : ajouter `analyst_verbosity_instruction` à la fin du prompt
3. Lire `proModel` depuis config Firestore (fallback `DEFAULT_PRO_MODEL`)
4. Bloc Tier 3 conditionnel basé sur les conditions ci-dessus
5. Logs : `🛡️ Tier 1` / `🔍 Tier 2 (Analyste)` / `⭐ Tier 3 (Expert Pro)`
6. `model_used` : ex `"flash-lite + flash + pro"`, nouvelle clé `"tier": 2|3`

### Détail : `prompts.json`
- **`analyst_verbosity_instruction`** : impose le format puce compact + les 4 indices numériques
- **`expert_pro_context_instruction`** : contextualise avec le JSON de l'Analyste, demande rapport complet
- **`main_analysis_prompt`** : ajouter les 4 nouveaux champs au bloc `FORMAT DE RÉPONSE JSON STRICT`

### Détail : `config.py`
```python
# Dans GEMINI_MODELS :
"default_pro": "gemini-2.5-pro"

# Nouvelles constantes :
DEFAULT_ANALYST_INSTRUCTION       = prompts_data.get('analyst_verbosity_instruction', "")
DEFAULT_EXPERT_PRO_CONTEXT        = prompts_data.get('expert_pro_context_instruction', "")
DEFAULT_PRO_MODEL                 = "gemini-2.5-pro"
DEFAULT_PRO_CONFIDENCE_THRESHOLD  = 0.75
DEFAULT_PRO_PRICE_THRESHOLD       = 1000
DEFAULT_PRO_DEAL_SCORE_THRESHOLD  = 8
DEFAULT_PRO_RESTO_SCORE_THRESHOLD = 7
DEFAULT_PRO_AUTH_SCORE_THRESHOLD  = 5
```

---

## Clés Firestore Exposées (Configuration Dynamique)

| Clé | Type | Défaut |
|---|---|---|
| `analystVerbosityInstruction` | string | `DEFAULT_ANALYST_INSTRUCTION` |
| `expertProContextInstruction` | string | `DEFAULT_EXPERT_PRO_CONTEXT` |
| `proModel` | string | `gemini-2.5-pro` |
| `proTriggerPriceThreshold` | number | `1000` |
| `proTriggerConfidenceThreshold` | number | `0.75` |
| `proTriggerDealScoreThreshold` | number | `8` |
| `proTriggerRestoScoreThreshold` | number | `7` |
| `proTriggerAuthScoreThreshold` | number | `5` |

---

## Questions Ouvertes / Points à Affiner

- [ ] Les seuils de déclenchement (prix 1000$, deal_score 7, etc.) sont-ils les bons ?
- [ ] Faut-il exposer les seuils dans le ConfigPanel du frontend ?
- [ ] Le format puce pour `analysis` est-il suffisamment détaillé ?
- [ ] Ajouter `FAST_FLIP` comme verdict déclencheur du Tier 3 ?

---

## Plan de Vérification

1. Annonce "Squier 150$" → Tier 2 seul, `analysis` compact, 4 indices présents
2. Annonce "Gibson USA 1200$" → Tier 3 déclenché par prix
3. Annonce ambiguë → `authenticity_score <= 5` → Tier 3 déclenché
4. `force_expert=True` → bypass Portier → Analyste → évaluation Pro
