# CLAUDE.md — Guitar Hunter AI

## Identité du Projet

**Guitar Hunter** — Bot de scraping et d'analyse IA d'annonces marketplace (Facebook).

- **Backend :** Python, Playwright, Google GenAI/Gemini, Schedule
- **Frontend :** React 18, Vite, TailwindCSS
- **Cloud :** Firebase (Firestore + Storage + Auth), ntfy.sh

> Source de vérité : lire tous les fichiers dans `docs/` avant d'agir. Ne lire le code source que si la doc ne suffit pas.

---

## Protocole de Travail (OBLIGATOIRE)

Toute tâche suit **3 étapes** dans cet ordre. Impossible de sauter une étape sans validation explicite.

### Étape 1 — Plan (NE PAS CODER)

Pour chaque nouvelle demande, répondre **uniquement** avec ce bloc et s'arrêter :

```
🚦 AIGUILLAGE ET PLAN D'ACTION
- Périmètre : [résumé court]
- Modèle Requis : [FLASH ou PRO]
- Le Plan : [étapes de ce que je vais faire]

👉 Valides-tu ce modèle et ce plan pour que j'exécute la tâche ?
```

Attendre le "Oui" ou "Go" de l'utilisateur. Aucune exception.

### Étape 2 — Code (NE PAS METTRE À JOUR LA DOC)

Une fois le plan validé, générer uniquement les diffs :

```javascript
// ... existing code ...
[CHANGEMENT ICI]
// ... existing code ...
```

Attendre la confirmation de fonctionnement par l'utilisateur avant de passer à l'étape 3.

### Étape 3 — Documentation (UNIQUEMENT après validation)

Après "C'est bon" ou "Validé" de l'utilisateur, mettre à jour (arborescence Diataxis) :
- `docs/management/JOURNAL.md` — format : `[DATE] [MODÈLE] Action → Résultat`
- `docs/management/TODO.md`
- `docs/reference/ARCHITECTURE.md`
- `docs/reference/DATA_FLOW.md`
- `docs/explanation/` — si la vision/stratégie évolue (`PROJECT_OVERVIEW.md`, `STATS_REFLEXION.md`)
- `docs/management/plans/` — pour les plans d'implémentation dédiés (ex : `MULTI_USER_PLAN.md`)

**Interdit** : utiliser `echo`, `sed`, `cat` en terminal pour modifier la doc. Utiliser les outils d'édition directs.

---

## Aiguillage des Modèles

| Modèle | Cas d'usage |
|--------|-------------|
| **[FLASH]** | Lecture, analyse doc, réponses simples, rédaction documentation |
| **[PRO]** | Génération de code complexe, refactoring, debug multi-fichiers, audit |

---

## Règles de Frugalité

- Interdit d'analyser l'intégralité du code source au démarrage.
- Lire `docs/` en priorité. Lire le code source seulement si la doc ne suffit pas.
- Interdit de réécrire des fichiers complets — fournir uniquement les blocs modifiés.
- Ne pas ajouter de features, refactoring, ou "améliorations" non demandées.
- Ne pas créer de fichiers non nécessaires.

---

## Architecture Clé

### Chemin Firestore (multi-tenant)
```
artifacts/{APP_ID}/users/{USER_ID}/
  ├── guitar_deals/     ← annonces analysées
  ├── commands/         ← bus de commandes Frontend → Backend
  └── (doc user)        ← botStatus, config, analysisConfig
```

### Statuts du Bot
`idle` | `scanning` | `paused` | `stopped`

### Pipeline IA (3-Tiers)
1. **Tier 1 — Portier** (`gemini-2.5-flash-lite`) : filtre rapide
2. **Tier 2 — Analyste** (`gemini-3.5-flash`, depuis 2026-07-09 — `gemini-2.5-flash` retiré par Google) : 5 scores numériques
3. **Tier 3 — Expert Pro** (`gemini-3.1-pro-preview`, depuis 2026-07-07) : analyse exhaustive (conditionnel)

### Commandes Backend
`REFRESH` | `ADD_CITY` | `ANALYZE_DEAL` | `CLEAR_LOGS` | `STOP_BOT` | `STOP_SCAN` | `START_BOT` | `SCAN_URL` | `CLEANUP`

---

## Points d'Attention Critiques

- Le backend Python tourne en **thread par utilisateur** avec watchdog de redémarrage (30s).
- Playwright n'est **pas thread-safe** — chaque thread crée sa propre instance de scraper localement.
- `getRefs(userId)` dans `firestoreService.js` lève une erreur si `userId` est absent (fail fast).
- Les images Facebook expirent → upload systématique vers **Firebase Storage** lors de `handle_deal_found`.
- `session_processed_ids` est isolé par thread via `threading.local()` pour éviter les collisions.
- Les prompts IA sont modifiables via Firestore (ConfigPanel) avec double fallback (`prompts.json`).
- **Piège logger (récurrent, trouvé 2026-07-09 dans `scraping/`, `analyzer.py`, `notifications.py`)** : seul le logger `bot.{user_id[:8]}` (créé dans `bot.py`, raccordé au `FirestoreHandler` de `logging_config.py`) est visible dans le LogViewer de l'app. Tout module qui logue via `logging.getLogger(__name__)` sans recevoir ce logger en paramètre est **invisible pour l'utilisateur**, même si les logs apparaissent bien côté serveur (stdout/journalctl). Tout nouveau module backend qui doit logger quelque chose d'observable par l'utilisateur doit accepter un paramètre `logger` optionnel (repli sur le logger de module) et le faire propager depuis `bot.py`/`analyzer.py` — ne jamais supposer qu'un `logger.info(...)` isolé sera visible.
- **`GEMINI_MODELS["default_analyst"]` (`config.py`) n'est pas réellement câblé** : `bot.py::_init_firestore_structure()` n'initialise que `gatekeeperModel`/`expertModel` dans le document Firestore d'un nouvel utilisateur, jamais `mainModel`. Le vrai défaut utilisé en pratique est le fallback codé en dur dans `analyzer.py::analyze_deal()` (`config.get('mainModel', '...')`) — à modifier en priorité si un modèle Tier 2 devient indisponible.
- **Facebook peut gater le prix/les photos pour une session non authentifiée** (comportement intermittent, cause exacte non confirmée) : le scraper est 100% anonyme (aucun `storage_state`/cookies persistants). Une fiche détail peut alors n'exposer que titre/description (balises `og:*`) sans prix ni carrousel photo, même après un reload. `handle_deal_found()` ne stocke pas ces annonces (0 image ET prix à 0$) plutôt que de figer une fiche vide — voir `TODO.md` pour la décision produit non tranchée (accepter la limitation vs session Facebook authentifiée).
- **Le LogViewer peut afficher les logs dans un ordre différent de leur émission réelle** : `FirestoreHandler` bufferise et envoie par lots toutes les 3s ; des logs émis à quelques centaines de ms d'écart peuvent recevoir un `timestamp` serveur identique/très proche, et leur ordre d'affichage n'est alors pas garanti. Ne pas déduire l'ordre d'exécution réel du code depuis l'ordre d'affichage du LogViewer sans vérifier le code source.
- **`BAD_DEAL` (verdict IA "Trop Cher") ≠ `REJECTED`** : `BAD_DEAL` garde `status: "analyzed"` (pas `"rejected"`) et est simplement masqué de la vue par défaut via son appartenance à `ARCHIVE_GROUP` (`src/constants.js`) — pas un vrai rejet de fond. Le pré-filtre de prix (`scanConfig.max_price`) dans `handle_deal_found()` réutilise ce même verdict plutôt que `REJECTED`, pour ne pas confondre "hors budget" avec "mauvaise annonce".

---

## Fichiers Clés

| Fichier | Rôle |
|---------|------|
| `main.py` (racine) | Point d'entrée, boucle principale, watchdog, dispatching commandes |
| `backend/bot.py` | `GuitarHunterBot` — orchestration globale |
| `backend/analyzer.py` | `DealAnalyzer` — pipeline 3-Tiers Gemini |
| `backend/scraping/` | `FacebookScraper` — Playwright + stealth mode |
| `backend/notifications.py` | `NotificationService` — email SMTP + ntfy.sh |
| `backend/logging_config.py` | `setup_logging()`/`FirestoreHandler` — logger par-utilisateur → LogViewer |
| `backend/database.py` | `DatabaseService` — Firestore + Firebase Storage |
| `src/services/firestoreService.js` | Couche d'abstraction Firestore côté Frontend |
| `src/hooks/useDealsManager.js` | Hook central — tri, filtres, actions |
| `src/components/Dashboard.jsx` | Interface principale — vues Liste/Carte/Stats |
| `src/components/DealCard.jsx` | Carte d'annonce avec analyse IA |
| `docs/` (Diataxis : `reference/`, `explanation/`, `management/`) | **Source de vérité prioritaire** |
