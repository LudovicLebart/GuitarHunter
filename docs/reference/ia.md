# Pipeline IA — trois paliers, fournisseurs, prompts (référence)

> Vérifié le 2026-11-05 contre le commit `c499ca0` : `backend/analyzer.py` (833 lignes), `llm_clients.py` (600), `t1_prompt.py`, `t1_image_budget.py`, `t1_circuit_breaker.py`, `t1_photo_text.py`, `t3_claude_tools.py`, `llm_usage.py`, `taxonomy.py`, `config.py` (variables `T1_*`/`T3_*`), `prompts.json`. La stratégie, les mesures et les décisions sont dans `plans/STRATEGIE_IA.md` ; ce fichier décrit seulement **ce que fait le code**. La base de connaissances (marques, fiches) est en section 5. Le chat Claude est en section 6.

## Rôle

Transformer une annonce (titre, prix, description, lieu, jusqu'à 8 photos) en une analyse structurée : verdict, classification, marque, modèle, cinq scores de 0 à 10, marge estimée. Trois paliers de coût croissant : le Portier élimine vite, l'Analyste structure, l'Expert ne se déclenche que si l'enjeu le justifie.

## Fichiers

| Fichier | Rôle |
|---|---|
| `analyzer.py` | `DealAnalyzer` : cascade, routage, déclenchement de l'Expert, canonicalisation |
| `llm_clients.py` | `LLMClientsMixin` : appels Gemini, Anthropic, API compatibles OpenAI (Dell/Ollama, Qwen cloud) ; schémas du Portier |
| `t1_prompt.py` | Prompt du Portier (source unique, partagée avec les scripts de rejeu) |
| `t1_image_budget.py` | Réduit les photos pour tenir dans le contexte du Dell |
| `t1_circuit_breaker.py` | Coupe-circuit par fournisseur du Portier |
| `t1_photo_text.py` | Lecture du texte visible sur les photos (option, éteinte) |
| `t3_claude_tools.py` | Outil `lookup_brand` et consignes supplémentaires de l'Expert Claude (option, éteinte) |
| `taxonomy.py` | Canonicalisation de la classification, routage par famille |
| `llm_usage.py` | Une ligne `llm_usage` par appel de modèle |
| `prompts.json` | Prompts et taxonomie par défaut (chargés par `config.py`) |

## Entrée : `DealAnalyzer.analyze_deal(listing_data, firestore_config, force_expert, user_comment, user_email, bypass_active_search)`

`firestore_config` est en réalité la **configuration de l'utilisateur** (`users.config`, clé `analysisConfig`) ; le nom est hérité. Les ContextVar `llm_usage.current_deal_id` et `current_user_ref` sont posées pour que chaque appel de modèle soit rattaché à son annonce. Après la cascade, la classification est canonicalisée (voir plus bas). Une même instance de `DealAnalyzer` sert les 5 threads d'analyse d'un utilisateur : ses caches (modèles Gemini, index de taxonomie) sont protégés par un verrou.

Si `GEMINI_API_KEY` est absente, la cascade renvoie `{"verdict": "ERROR", …}`.

## La cascade

### Préparation
Au plus **8 photos** sont téléchargées une par une (`requests.get`, 10 s, redimensionnées à 2 048 px de côté au plus, RGBA/palette converties en RGB ; une URL `via.placeholder.com` ou un échec donne `None` sans erreur). Le prompt de base (`mainAnalysisPrompt`, taxonomie triée, exemples few-shot, bloc « Détails de l'annonce ») est construit une fois. Une correction utilisateur (`user_comment`) y est ajoutée.

### Palier 1 — Portier (sauté si `force_expert`)
1. Prompt du Portier (`t1_prompt.build_t1_gatekeeper_prompt`) : taxonomie compacte, règle de classification en chemin complet, instruction du Portier, bloc de connaissances (si activé), correction utilisateur, puis l'annonce en JSON dans `<annonce>` (toujours en dernier).
2. La chaîne `T1_PROVIDER_CHAIN` (défaut `local,qwen`) est essayée dans l'ordre. Un fournisseur dont le coupe-circuit est ouvert est sauté. Un échec réel compte pour le coupe-circuit (3 échecs de suite, pause de 600 s, le premier appel après la pause sert de test) ; une réponse vide passe au suivant sans compter comme panne.
   - **`local`** : `qwen3-vl:8b-instruct` sur le Dell via Ollama (`T1_LOCAL_BASE_URL`, défaut `http://100.94.33.54:11434/v1`), un appel à la fois (sémaphore de module, `T1_LOCAL_MAX_CONCURRENCY = 1`), 60 s, aucune nouvelle tentative, photos réduites par `fit_images_to_budget` (contexte 8 192, marge de réponse 600).
   - **`qwen`** : `T1_OBSERVATION_QWEN_MODEL` (défaut `qwen/qwen3.8-flash`) via TokenRouter, 60 s, 2 nouvelles tentatives, sans réduction de photos.
   - **`gemini`** : `gatekeeperModel` de la configuration (défaut `gemini-3.5-flash-lite`), avec schéma de réponse.
3. Contrat de réponse : `{status, reasoning, brand, classification}`. `status` ∈ `PEPITE`, `FAST_FLIP`, `LUTHIER_PROJ`, `CASE_WIN`, `COLLECTION`, `FAIR`, `BAD_DEAL`, `REJECTED_ITEM`, `REJECTED_SERVICE`. Avec le schéma strict des API compatibles OpenAI, les champs sortent dans l'ordre `status`, `reasoning`, `brand`, `classification` : le verdict est écrit **avant** le raisonnement.
4. Toute la chaîne en échec : verdict `ERROR_GATEKEEPER`, alerte (modèle retiré si l'erreur y ressemble, sinon échec du Portier ; une par jour et par fournisseur), puis résultat `GATEKEEPER_FAILED_SKIP` : le bot n'écrit rien et retentera l'annonce au cycle suivant. Une réponse sans verdict donne `ERROR`, traité de même.
5. Un verdict de rejet (`rejectionVerdicts` de la configuration, défaut `BAD_DEAL`, `REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA`, ou tout statut commençant par `REJECTED`) **arrête la cascade**. `FAIR` n'est pas un rejet.
6. **Routage par Recherche Active** (`analysisConfig.activeSearchFamilies`, vide = tout passe) : si la classification du Portier, normalisée par `routing_classification`, n'est ni une famille active ni dans une sous-branche, l'annonce devient `NOT_PROMOTED` et la cascade s'arrête. Seul un verdict `PEPITE` passe toujours. Un verdict d'erreur ne subit pas ce routage. Un scan d'URL manuel (`bypass_active_search`) l'ignore.
7. **Observation miroir** (`T1_OBSERVATION_ENABLED`, **éteinte** par défaut) : rejoue le prompt sur le fournisseur qui n'est pas le décideur, dans un thread, sans jamais influencer la décision ; résultats sous `qwenGatekeeper*` ou `flashliteGatekeeper*` dans `ai_analysis_raw`.
8. **Base de connaissances** (`T1_KNOWLEDGE_ENABLED`, **éteinte**) : si allumée, des fiches de marques sont injectées dans le prompt, et la trace `gatekeeperKnowledge` est conservée.

### Palier 2 — Analyste
Modèle `mainModel` (défaut `gemini-3.7-flash`), prompt de base + `analystVerbosityInstruction`, photos jointes, JSON forcé, température 0,1. Retourne verdict, scores, marque, modèle, marge, `confidence`… Un échec (`err_t2`) renvoie un résultat dont le verdict est celui du **Portier**, avec `model_used` terminé par « (Error) ».

### Palier 3 — Expert (conditionnel)
Déclenché par `expert_trigger_reason`, dans cet ordre (le premier qui correspond gagne) :
1. `force_expert` ;
2. prix > `proTriggerPriceThreshold` (1 000) et `deal_score` ≥ 4 ;
3. `deal_score` ≥ `proTriggerDealScoreThreshold` (8) ;
4. `deal_score` ≥ `proTriggerCombinedDealScore` (6) et `restoration_interest_score` ≥ `proTriggerRestoScoreThreshold` (7) ;
5. `authenticity_score` ≤ `proTriggerAuthScoreThreshold` (7) ;
6. `confidence` < `proTriggerConfidenceThreshold` (0,75) ;
7. verdict `COLLECTION`.

Fournisseur `T3_PROVIDER` : **`claude` par défaut** (`T3_CLAUDE_MODEL = claude-sonnet-5-5`, effort `high`, 16 000 tokens, 300 s, photos à 1 568 px, cache de prompt `5m`), ou `gemini` (`expertModel`/`proModel`, défaut `gemini-3.1-pro-preview`). Avec Claude, le modèle de la configuration est ignoré. Le prompt est le prompt de base suivi du contexte de l'Expert (`expertProContextInstruction`, rempli avec le verdict et le résumé du T2). La partie statique avant « Détails de l'annonce : » est envoyée comme bloc `system` mis en cache. Avec `T3_KNOWLEDGE_ENABLED` (**éteint**), l'outil `lookup_brand` (4 appels au plus par analyse, 3 tours d'outils) et des consignes de lecture des photos sont ajoutés.
Le résultat de l'Expert **remplace** celui de l'Analyste. Un échec de l'Expert **lève `RuntimeError`** : l'analyse est perdue, l'appelant la traite comme un échec.

### Sortie
`model_used` = chaîne des modèles (`portier -> analyste -> expert`) ; `tier3_trigger` ; `gatekeeperBrand`, `gatekeeperClassification`, `gatekeeperVerdict` (verdict brut du Portier, `MANUAL_RETRY` si le Portier a été sauté). L'analyse complète va dans `ai_analysis_raw`, les champs promus en colonnes (voir `donnees.md`).

## Clients de modèles (`llm_clients.py`)
- **Gemini** (`google.generativeai`) : `response_mime_type = application/json`, température 0,1, nouvelle tentative unique sur JSON invalide (avec consigne d'échappement). Réponse en tableau normalisée en objet. Pas de délai explicite sur l'appel.
- **Anthropic** : `messages.create` avec effort de raisonnement dans `extra_body`, JSON demandé par le prompt (suffixe), photos en JPEG qualité 90 étiquetées « Image N », cache de prompt sur le préfixe statique, boucle d'outils bornée, réponse coupée (`max_tokens`) = erreur sans nouvel essai, crédit épuisé = message dédié. Les tokens écrits au cache sont enregistrés à part.
- **Compatible OpenAI** : photos en JPEG base64, `response_format` JSON ou schéma strict ; l'énumération des chemins de classification n'est activée que par `T1_CLASSIFICATION_ENUM` (éteint).
- Chaque appel, réussi ou non, écrit **une ligne `llm_usage`** par tentative (`llm_usage.record`, jamais bloquant ; types d'erreur : `timeout`, `connection`, `model_unavailable`, `http`, `json`, `no_key`, `no_credit`, `other`), et déclenche l'alerte « modèle injoignable » en cas d'échec.

## Classification (`taxonomy.py`)
`canonicalize` ramène la valeur du modèle à un **chemin complet en dot-notation** : chemin exact, sinon nom de feuille unique, sinon chemin incomplet réparé par suffixe unique (au moins 2 segments), sinon `ambiguous`/`unknown`. Une valeur refusée devient `classification = None` et la valeur brute est gardée dans `classification_rejected`. Un nom nu de la branche `etui_housse` commençant par un nom d'instrument (« Guitare Acoustique ») n'est jamais résolu en étui. La taxonomie par défaut a trois racines : `guitare`, `amplificateur`, `etui_housse`. `matches_active_search_family` : égalité avec une famille, ou préfixe `famille.`.

## Prompts (`prompts.json`)
`main_analysis_prompt` (61 lignes : coupe-circuit de rejet, identification et marque, calculs financiers, plan de bataille, verdicts et seuils de la pépite, format JSON), `gatekeeper_verbosity_instruction`, `analyst_verbosity_instruction`, `expert_pro_context_instruction` (contient `{status}` et `{reasoning}`), `sold_backfill_instruction`, `rejection_verdicts`, `few_shot_examples`, `taxonomy_master`. Chacun peut être surchargé par utilisateur dans `analysisConfig`, avec repli sur ce fichier. **Dans l'interface (ConfigPanel), seuls `mainAnalysisPrompt`, `gatekeeperVerbosityInstruction`, `rejectionVerdicts` et les modèles (`gatekeeperModel`, `mainModel`, `expertModel`, `chatModel`) sont modifiables** ; les instructions de l'Analyste et de l'Expert ne le sont que par l'API. L'interface écrit d'ailleurs une clé `expertContextInstruction` que le backend ne lit pas (il lit `expertProContextInstruction`) : voir `revue/2026-frontend.md`.

## Autres entrées
- `analyze_deal_light` : un seul appel Analyste avec l'instruction de rattrapage des annonces vendues (`backfill_leger -> modèle`).
- Le chat de l'application n'utilise pas ce module (voir section 6).

## Configuration (valeurs par défaut du code)
`T1_PROVIDER_CHAIN = local,qwen` · `T1_GATEKEEPER_PROVIDER = qwen` (fournisseur « décideur » pour l'observation) · `T1_LOCAL_*` (voir plus haut) · `T1_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3`, `COOLDOWN_SECONDS = 600` · `T1_OBSERVATION_ENABLED`, `T1_KNOWLEDGE_ENABLED`, `T1_KNOWLEDGE_PHOTO_TEXT`, `T3_KNOWLEDGE_ENABLED`, `T1_CLASSIFICATION_ENUM` : **tous faux** · `T1_KNOWLEDGE_REQUIRE_REVIEW = true`, `T1_KNOWLEDGE_MAX_FICHES = 3` · `T3_PROVIDER = claude` · seuils `DEFAULT_PRO_*` listés plus haut.

## Pièges et invariants
- Le contexte Ollama du Dell doit rester à **8 192** ; à 4 096 le prompt est tronqué (voir `CLAUDE.md`). Tout rejeu du Portier doit reproduire la production (`QWEN_LOCAL_MAX_IMAGES=8`, `--temperature -1`).
- `ai_analysis_raw.gatekeeperVerdict` vaut `MANUAL_RETRY` après une analyse forcée : le verdict d'origine est dans `initial_verdict`.
- Les modèles ne sont pas interchangeables silencieusement : un modèle retiré par son fournisseur produit une alerte (une par jour), pas un repli automatique, sauf pour le Portier (chaîne).
- Un échec du Portier n'est jamais « fail-open » : l'annonce est sautée.

## Tests
`backend/test_analyzer.py` (cascade, caractérisation), `test_t1_image_budget.py`, `test_t1_photo_text.py`, `test_t3_brand_tool.py`. Aucun test n'appelle un vrai modèle.
