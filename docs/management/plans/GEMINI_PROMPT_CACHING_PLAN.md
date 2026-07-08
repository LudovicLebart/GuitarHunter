# Plan d'Implémentation : Caching de Contexte Gemini (Économie de Tokens)

**Objectif :** Réduire le coût en tokens des 3 appels Gemini par annonce (Portier / Analyste / Expert Pro) en exploitant le **context caching** de l'API Gemini sur les portions de prompt statiques et partagées entre utilisateurs (taxonomie, few-shot examples, contrat JSON, instructions par défaut), sans casser la possibilité pour un utilisateur de personnaliser ses prompts via le `ConfigPanel`.

**Modèle IA Recommandé pour l'exécution :** `Gemini 2.5 Pro` (refactor architecture backend multi-fichiers + décision de migration SDK).

---

## 0. Rappel du Fonctionnement du Caching Gemini

- **Caching implicite** : activé par défaut sur tous les modèles 2.5+ (nos 3 Tiers). Automatique, **aucun code requis**. Seuil minimum ~2048 tokens de préfixe commun. Ne matche que sur un **préfixe identique octet-pour-octet** entre appels — y compris entre utilisateurs différents partageant la même clé API, tant que le contenu est rigoureusement identique.
- **Caching explicite** (`client.caches.create()`, SDK `google-genai`) : réduction garantie de **90%** sur les tokens réutilisés (modèles 2.5+), mais facturation de **stockage** selon le `ttl`, et gestion manuelle du cycle de vie (création, refresh, expiration).
- **Scope par modèle** : un cache est lié à un modèle précis → il faut un cache distinct par Tier (Portier, Analyste, Expert Pro), puisque chacun utilise un `model_name` différent.

---

## 1. Constat sur le Code Actuel

- `analyzer.py::_construct_base_user_prompt()` place déjà le contenu statique (prompt principal + taxonomie + few-shot) **avant** les détails variables de l'annonce (titre, prix, description) — c'est le bon ordre pour maximiser le préfixe commun exploitable par le cache.
- `analyzer.py::analyze_deal()` lit `config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT)` **par utilisateur** depuis Firestore (`analysisConfig`). Dès qu'un seul utilisateur personnalise ce champ via le `ConfigPanel`, son préfixe diverge du défaut partagé et son cache diverge de celui des autres (sans affecter les autres utilisateurs — le matching se fait par contenu, pas par identité).
- Le projet dépend déjà de **deux SDK Gemini** : `google.generativeai` (legacy, utilisé actuellement dans `analyzer.py`) et `google-genai` (nouveau SDK unifié, présent dans `requirements.txt` mais inutilisé). Le caching explicite moderne (`client.caches.create()`) nécessite `google-genai`.

---

## 2. Étape 1 : Scinder le Contenu Statique du Contenu Éditable

**Actions (Agent) :**
1. Isoler dans la construction du prompt (`_construct_base_user_prompt` et les 3 blocs `full_prompt_t1/t2/t3`) :
   - **Bloc statique partagé** (candidat au cache) : `DEFAULT_TAXONOMY`, `DEFAULT_FEW_SHOT_EXAMPLES`, contrat JSON (`### FORMAT DE RÉPONSE JSON STRICT`), instructions par défaut de chaque Tier.
   - **Bloc éditable utilisateur** : ce que l'utilisateur peut réellement modifier via `PromptListEditor` (`mainAnalysisPrompt`, `gatekeeperVerbosityInstruction`, `analystVerbosityInstruction`, `expertProContextInstruction`).
2. Détecter si la valeur Firestore d'un utilisateur est **identique** à la constante `DEFAULT_*` correspondante (comparaison directe ou par hash) :
   - Si identique → utilisateur éligible au cache partagé par défaut.
   - Si différente → utilisateur en dehors du cache partagé (voir §5, Étape 4).
3. Garantir une **sérialisation canonique** du JSON taxonomie (`json.dumps(..., sort_keys=True)`, encodage UTF-8 stable) pour que le préfixe soit rigoureusement identique entre threads/utilisateurs/redémarrages — indispensable pour le matching implicite ET pour le hash de détection de personnalisation.

---

## 3. Étape 2 : Caching Implicite (Gain "Gratuit")

**Actions (Agent) :**
1. Vérifier/ajuster l'ordre d'assemblage pour que le bloc statique (§2) forme toujours le tout début du prompt envoyé, avant toute donnée variable (annonce, instruction spécifique au Tier si possible déplacée en fin de prompt plutôt qu'insérée au milieu).
2. Aucune création d'objet cache nécessaire — Google déduplique automatiquement côté serveur si le préfixe dépasse ~2048 tokens et reste identique entre appels rapprochés.
3. Logger le `usage_metadata` de chaque réponse Gemini (présence de `cached_content_token_count` ou équivalent) pour mesurer le taux de hit réel avant d'investir dans le caching explicite.

---

## 4. Étape 3 : Caching Explicite (Gain Garanti, par Tier)

**Actions (Agent) :**
1. Migrer les appels Gemini de `analyzer.py` du SDK legacy `google.generativeai` vers `google-genai` (impact : `_get_model`, `_call_gemini_json`, initialisation du client).
2. Créer un module `backend/gemini_cache.py` responsable de :
   - Créer 3 `CachedContent` partagés (un par Tier), contenant le bloc statique par défaut (taxonomie + few-shot + instruction par défaut du Tier).
   - Exposer une fonction `get_or_create_cache(tier_name, model_name, static_content) -> cache_name`, idempotente, qui recrée le cache s'il a expiré ou si le contenu par défaut a changé (ex : mise à jour de `prompts.json` au déploiement).
   - Référencer `cached_content=cache.name` dans les appels `generate_content` pour les utilisateurs éligibles (§2.2).
3. Pour un utilisateur ayant personnalisé une section : fallback silencieux vers l'envoi complet non-caché (comportement actuel, zéro régression) — pas de cache dédié dans une première version, sauf si un besoin réel est mesuré (voir §6).

---

## 5. Étape 4 : TTL & Fréquence d'Appel (Point d'Attention Critique)

C'est le point soulevé explicitement par l'utilisateur : un cache mal dimensionné peut coûter plus cher qu'il ne rapporte.

**Mécanique à respecter :**
- Le `ttl` d'un `CachedContent` (ex : `3600s` par défaut) **n'est pas prolongé automatiquement** par les appels qui le référencent — contrairement à un cache LRU classique. Sans action explicite, le cache expire au bout du TTL initial, qu'il ait été utilisé une fois ou cent fois entre-temps.
- Le maintenir "chaud" nécessite soit un **refresh explicite du TTL** (`client.caches.update(name=..., ttl=...)`), soit une **recréation** — les deux ont un coût (tokens d'entrée standard facturés à la création/mise à jour + stockage pendant le TTL).

**Règle de décision à implémenter :**
1. Croiser le TTL choisi avec `scanConfig.frequency` (fréquence de scan, déjà configurable par utilisateur, en minutes) :
   - Si l'intervalle entre deux scans (donc deux appels Gemini potentiels) est **très inférieur** au TTL → le cache reste chaud naturellement entre deux usages, le rafraîchir est rentable.
   - Si l'intervalle dépasse ou approche le TTL → le cache expire entre deux scans, sa recréation périodique n'apporte aucun bénéfice net (coût de recréation ≈ coût sans cache, plus le stockage en trop).
2. Dimensionner le TTL du cache partagé (§4) sur la **fréquence de scan la plus active parmi tous les utilisateurs éligibles** (le cache étant commun à tous ceux qui n'ont pas personnalisé leur prompt) — un seul utilisateur actif suffit à justifier de le maintenir chaud pour tout le monde.
3. Ajouter un job dans le `TaskScheduler` existant (`backend/services.py`) qui :
   - Rafraîchit le TTL des caches actifs (par Tier) à intervalle régulier (ex : toutes les 45 min si TTL = 1h), tant qu'au moins un scan a eu lieu depuis la dernière vérification.
   - Laisse expirer naturellement un cache si aucun utilisateur éligible n'a scanné depuis une période > TTL, plutôt que de payer un refresh pour rien.
4. Ne pas créer de cache dédié par utilisateur personnalisé (§4.3) sauf si sa fréquence de scan individuelle est suffisamment élevée par rapport à un TTL dédié pour amortir le coût de création/stockage — à évaluer seulement après mesure réelle (§6), pas en spéculatif.

---

## 6. Robustesse & Observabilité

- Toute erreur de cache (expiré, quota dépassé, échec de création/refresh) doit dégrader **silencieusement** vers l'envoi du prompt complet non-caché — cohérent avec la philosophie de double fallback déjà en place dans le projet (`ARCHITECTURE.md §4.4`).
- Logger pour chaque appel : Tier, cache utilisé (oui/non), tokens totaux vs tokens facturés au tarif réduit — pour valider le ROI réel avant d'étendre le mécanisme (ex : caches par utilisateur personnalisé).

---

## 7. Estimation Chiffrée du Coût (Avant / Après Caching)

Estimation illustrative basée sur le contenu réel de `prompts.json` (comptage de caractères) et les tarifs publics Gemini (juillet 2026). **Hypothèses explicites, à recalibrer avec des données réelles (§7.4)** :

| Paramètre | Valeur retenue |
|---|---|
| Ratio caractères→tokens | 4 car./token (approximation) |
| Bloc statique partagé (taxonomie + few-shot + prompt principal) | ~3 205 tokens (mesuré) |
| Tokens/photo | ~700 (2-3 tuiles de 258 tokens, formule officielle, résolution FB moyenne supposée) |
| Photos/annonce | 4 (donnée utilisateur) |
| Funnel Portier → Analyste | 60% (18/30) — **hypothèse** |
| Funnel Analyste → Expert Pro | 25% des 18 (→ 4 annonces) — **hypothèse** |
| Tarifs $/1M tokens (in/out) | Flash-Lite 0.10/0.40 · Flash 0.30/2.50 · Pro 1.25/10.00 |
| Réduction cache explicite | 90% sur la portion mise en cache (tarif officiel) |
| Stockage cache | ~2$/M tokens/heure (fourchette publique 1-4.50$ selon modèle) |

### 7.1 Coût par scan (30 annonces, 4 photos/annonce)

| | Sans cache | Avec cache explicite (hors stockage) |
|---|---|---|
| Coût/scan | **$0.137** | **$0.096** |
| Coût moyen/annonce | $0.0046 | $0.0032 |
| Réduction sur les tokens facturés | — | **~30%** |

Le gain plafonne à ~30% (et non 90%) car **les images ne sont jamais cachées** (uniques par annonce) et représentent la majorité des tokens d'entrée (~2 800 sur ~6 200 par appel) — seul le préambule statique (taxonomie/few-shot/prompt) bénéficie du tarif réduit.

### 7.2 Coût de stockage du cache

- 3 caches (un par Tier) ≈ 10 057 tokens au total → **~$0.48/jour** si maintenu 24h/24.
- Économie brute de tokens à fréquence de scan = 60 min (24 scans/jour, **1 seul utilisateur**) : **~$0.97/jour**.
- **Gain net : ~$0.49/jour pour un utilisateur seul** — rentable mais modeste.

### 7.3 Effet d'échelle (rejoint §5)

Le coût de stockage est **fixe et partagé** entre tous les utilisateurs n'ayant pas personnalisé leur prompt (un seul jeu de 3 caches pour tout le monde), alors que l'économie de tokens **scale linéairement avec le nombre d'utilisateurs actifs**. Avec 5 utilisateurs scannant à fréquence comparable : ~$4.85/jour d'économie brute pour le même $0.48/jour de stockage → **gain net ~$4.37/jour**. Le ROI du cache explicite s'améliore donc surtout avec le nombre d'utilisateurs partageant le prompt par défaut, pas avec le volume d'un seul.

### 7.4 Calibrer avec des données réelles (au lieu des hypothèses de funnel)

Les deux paramètres qui pèsent le plus sur cette estimation (taux de rejet Portier, taux de déclenchement Expert Pro) sont **des hypothèses**, alors que la donnée réelle existe déjà : chaque annonce stockée dans `guitar_deals` porte un champ `aiAnalysis.model_used` (ex : `"gemini-2.5-flash-lite -> gemini-2.5-flash -> gemini-2.5-pro"`, `DATA_FLOW.md §4`). Le nombre de maillons de cette chaîne indique exactement jusqu'où l'annonce est allée dans la cascade (1 = rejetée au Portier, 2 = arrêtée à l'Analyste, 3 = passée par l'Expert Pro) — il suffit de compter les occurrences de `" -> "` sur l'ensemble des annonces pour obtenir le vrai funnel, sans hypothèse.

**Constat en l'examinant** : le widget "Funnel d'Analyse (Tiers)" existe déjà dans `src/components/StatsView.jsx` (lignes 197-200), mais il contient actuellement des **valeurs partiellement figées en dur** plutôt que dérivées de `model_used` :
- `"Total Scrappé"` : `totalDeals * 4` (facteur arbitraire), `percentage` fixé à `100`.
- `"Passé Portier (T1)"` : compte `totalDeals` (suppose que 100% des annonces stockées ont passé le Portier), `percentage` fixé à `25` (incohérent avec le compte affiché).
- `"Certifié (T3 Pro)"` : `count` fixé à `2`, `percentage` fixé à `12` — valeurs manifestement de test/placeholder.
- Seul `"Qualifié (T2)"` est réellement calculé (`radarDeals.length + marketDeals.length`), mais via le verdict final plutôt que via `model_used`.

**Recommandation** : avant de figer les hypothèses de funnel de ce plan, corriger `StatsView.jsx` pour dériver les 3 compteurs directement du nombre de maillons de `aiAnalysis.model_used` sur les annonces réelles de l'utilisateur connecté — cela donnerait un funnel exact, affiché dans l'app, et réutilisable pour recalibrer §7.1. C'est un correctif de code ciblé (pas une nouvelle fonctionnalité), à traiter comme une tâche à part si validé.

---

## Phase de Test et Migration

1. Implémenter d'abord le caching implicite (§3) sans aucune création d'objet — mesurer le taux de hit sur quelques jours via les logs.
2. Si le taux de hit implicite est faible ou le volume d'appels le justifie, implémenter le caching explicite par Tier (§4) avec la règle TTL/fréquence (§5).
3. Valider sur un utilisateur "cobaye" à fréquence de scan élevée avant généralisation.
4. Documenter les résultats mesurés (tokens économisés, coût de stockage réel) dans `docs/management/JOURNAL.md`.
