# Liste des Tâches - Guitar Hunter AI

Ce document sert à suivre les tâches à accomplir, les bugs à corriger et les améliorations prévues.

**Consigne pour l'Assistant AI :**
- Consultez ce fichier au début de chaque session.
- Ajoutez-y les nouvelles tâches définies lors des discussions avec l'utilisateur.
- Marquez les tâches comme `[x]` une fois qu'elles sont terminées et validées.
- Déplacez les tâches terminées dans la section "Terminé" si la liste devient trop longue.

---

## 🚨 Priorité Haute (Bugs & Correctifs)

- [ ] **Problème de la double connexion API (Feature future) :**
    - *Détails :* À lister si le besoin s'en fait sentir.

---

## 🧹 Maintenabilité & Dette Technique

- [x] **Supprimer le code mort — `backend/prompt_manager.py`**
    - *Détails :* La classe `PromptManager` (architecture "5 blocs") est un orphelin non instancié nulle part dans le code actif. Elle peut être supprimée sans impact.

- [x] **Nettoyer les clés obsolètes de `prompts.json` et `config.py`**
    - *Détails :* Les clés `persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`, `system_structure` dans `prompts.json` et leurs constantes associées dans `config.py` (`PROMPT_INSTRUCTION`, `DEFAULT_VERDICT_RULES`, etc.) ne sont plus utilisées. Les supprimer allégera le code et évitera la confusion.

- [x] **Migrer les commandes "legacy" vers la collection `commands`**
    - *Détails :* Certaines commandes (Refresh, Cleanup, Reanalyze All, Scan URL) fonctionnent encore en modifiant des champs dans le document `users/{id}` (`forceRefresh`, `scanSpecificUrl`), tandis que d'autres (Analyze Deal, Clear Logs) utilisent la nouvelle collection Firestore `commands`. Il faut unifier l'architecture autour de la collection `commands` pour faciliter la traçabilité.

- [ ] **Rendre la vérification de disponibilité du scraper plus robuste**
    - *Détails :* La fonction `check_listing_availability` dans `backend/scraping/core.py` cherche le texte exact "Cette annonce n’est plus disponible". C'est fragile et sujet aux changements d'interface ou de langue de Facebook.

---

## 🎨 Interface Utilisateur (UI/UX)

- [ ] **Revoir l'affichage du bloc de prix**
    - *Détails :* Continuer d'affiner le composant `PriceDisplay` dans `DealCard.jsx`. Objectif : affichage clair, compact et informatif sur mobile et desktop.

- [ ] **Ajouter un bouton de sauvegarde explicite pour les prompts**
    - *Détails :* Actuellement, chaque `onBlur` sur un champ du `PromptListEditor` déclenche une sauvegarde immédiate dans Firestore. Envisager un bouton "Sauvegarder" avec confirmation pour éviter les sauvegardes accidentelles. *(Note: le bug de corruption causé par l'onBlur est corrigé — Session 11. Cet item reste pertinent pour l'UX.)*

---

## 🧠 Système de Prompts & IA

### 🔴 Fiabilité de l'Éditeur de Prompts

- [ ] **Ajouter une validation des prompts avant sauvegarde**
    - *Détails :* L'éditeur ne vérifie pas si l'utilisateur a cassé la structure JSON attendue dans `mainAnalysisPrompt`. Implémenter une détection de la présence du bloc `### FORMAT DE RÉPONSE JSON STRICT` et afficher un avertissement si absent. Ajouter un bouton "Réinitialiser cette section" par prompt.
    - *Risque actuel :* Un prompt cassé rend toutes les analyses de l'IA non parsables silencieusement.

### 🟡 Architecture des Prompts

- [ ] **Découper `mainAnalysisPrompt` en sections éditables indépendantes**
    - *Détails :* Le prompt principal est actuellement un bloc monolithique. Le structurer en sous-sections indépendantes dans Firestore et dans l'UI : `Persona & Objectifs`, `Règles de Verdicts`, `Format JSON`. Permet une édition chirurgicale sans risque de tout casser. C'est le retour à l'architecture "5 blocs" de `PromptManager`, mais correctement branchée cette fois.

- [ ] **Rendre la Taxonomie modifiable via l'interface**
    - *Détails :* `DEFAULT_TAXONOMY` est chargée statiquement depuis `prompts.json` au démarrage de Python. Stocker `taxonomy_guitares` dans Firestore sous `analysisConfig.taxonomy` et l'injecter dynamiquement dans `analyzer.py`. Exposed dans le `ConfigPanel` avec un éditeur JSON dédié.

### 🟢 Qualité des Analyses IA

*(Les améliorations de qualité telles que l'analyse visuelle, le Chain-of-Thought et le Few-Shot ont été implémentées et fusionnées avec succès).*

- [ ] **Entonnoir d'analyse en 3 niveaux (Portier → Analyste → Expert Pro)**
    - *Plan de travail :* [`docs/FUNNEL_PLAN.md`](./FUNNEL_PLAN.md) — **Finalisé et validé (Session 16).**
    - *Objectif :* Ajouter un Tier 2 (Analyste Flash, condensé + 5 scores numériques) et un Tier 3 (Expert Pro, déclenché par seuils intelligents Score + Prix) pour optimiser la consommation de tokens et la précision des analyses.
    - *Fichiers impactés :* `backend/analyzer.py`, `prompts.json`, `config.py`.

---

## 📊 Statistiques & Dashboard

- [ ] **Mettre en place le moteur de statistiques (Impact Tier 3)**
    - *Plan de travail :* [`docs/STATS_REFLEXION.md`](./STATS_REFLEXION.md)
    - *Objectif :* Exploiter les 5 scores et le funnel pour générer des KPIs financiers (ROI, Marges) et qualitatifs (Profil de marché, Vitesse de rotation).
    - *Sous-tâches :* 
        - [ ] Créer une fonction d'agrégation côté Backend ou Cloud Function.
        - [ ] Concevoir les composants graphiques sur le Frontend (Charts).

---

## 🚀 Améliorations Futures

- [ ] **Injection Dynamique de la Taxonomie (Optimisation tokens)**
    - *Détails :* N'envoyer à l'Expert que la branche de la taxonomie pertinente (identifiée par le Portier) plutôt que la taxonomie complète. Économise des tokens et améliore la précision.

- [ ] **Système de Feedback (Apprentissage)**
    - *Détails :* Stocker les rejets manuels avec leur motif pour constituer un dataset permettant d'affiner les futurs prompts ou de fine-tuner un modèle.

- [ ] **Expansion du Scope (Amps & Étuis) — Luthier-Centric**
    - *Plan de travail :* [`brain/implementation_plan.md`](../.gemini/antigravity/brain/1d3a056c-c92e-4244-83d4-139947813fff/implementation_plan.md)
    - *Objectif :* Intégrer les amplificateurs et les étuis dans la taxonomie et l'analyse IA sans perdre le persona "Maître Luthier". Valoriser la liquidité des amplis modernes et l'apport de valeur des housses/étuis pour le "flipping".
    - *Fichiers impactés :* `prompts.json`, `analyzer.py`, `useDealsManager.js`.

---

## ✅ Terminé

- [x] Création de la structure de documentation (`docs/`).
- [x] Mise en place du `AI_BRIEFING.md`.
- [x] Refonte responsive de la `DealCard` (Mobile First).
- [x] Analyse approfondie du système de prompts dynamiques (`docs/ARCHITECTURE.md` Section 4 mise à jour, Session 10).
- [x] Nettoyage et restructuration de la racine du projet (Session 15).
- [x] Get user validation 🚦 [/] Validé
- [/] Update documentation (JOURNAL, TODO, ARCHITECTURE) 🚦 [/] En cours
- [x] Externalisation des verdicts de rejet de `analyzer.py` vers configuration dynamique via Firestore/UI (Session 15).
- [x] Refonte du système de nettoyage des annonces vendues (Soft Delete, Scraper robuste JS DOM, Badges UI) (Session 16).
