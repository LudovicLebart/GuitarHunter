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

Après "C'est bon" ou "Validé" de l'utilisateur, mettre à jour :
- `docs/JOURNAL.md` — format : `[DATE] [MODÈLE] Action → Résultat`
- `docs/TODO.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_FLOW.md`

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
2. **Tier 2 — Analyste** (`gemini-2.5-flash`) : 5 scores numériques
3. **Tier 3 — Expert Pro** (`gemini-2.5-pro`) : analyse exhaustive (conditionnel)

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

---

## Fichiers Clés

| Fichier | Rôle |
|---------|------|
| `backend/main.py` | Point d'entrée, boucle principale, watchdog, dispatching commandes |
| `backend/bot.py` | `GuitarHunterBot` — orchestration globale |
| `backend/analyzer.py` | `DealAnalyzer` — pipeline 3-Tiers Gemini |
| `backend/scraping/` | `FacebookScraper` — Playwright + stealth mode |
| `backend/database.py` | `DatabaseService` — Firestore + Firebase Storage |
| `src/services/firestoreService.js` | Couche d'abstraction Firestore côté Frontend |
| `src/hooks/useDealsManager.js` | Hook central — tri, filtres, actions |
| `src/components/Dashboard.jsx` | Interface principale — vues Liste/Carte/Stats |
| `src/components/DealCard.jsx` | Carte d'annonce avec analyse IA |
| `docs/` | **Source de vérité prioritaire** |
