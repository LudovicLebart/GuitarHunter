# Liste des Tâches - Guitar Hunter AI

Ce document sert à suivre les tâches à accomplir, les bugs à corriger et les améliorations prévues.

**Consigne pour l'Assistant AI :**
- Consultez ce fichier au début de chaque session.
- Ajoutez-y les nouvelles tâches définies lors des discussions avec l'utilisateur.
- Marquez les tâches comme `[x]` une fois qu'elles sont terminées et validées.
- Déplacez les tâches terminées dans la section "Terminé" si la liste devient trop longue.

---

## 🚨 Priorité Haute (Bugs & Correctifs)

*(Aucun bug critique actuellement)*

---

## 🧹 Maintenabilité & Dette Technique

- [ ] **Supprimer le code mort — `backend/prompt_manager.py`**
    - *Détails :* La classe `PromptManager` (architecture "5 blocs") est un orphelin non instancié nulle part dans le code actif. Elle peut être supprimée sans impact.

- [ ] **Nettoyer les clés obsolètes de `prompts.json` et `config.py`**
    - *Détails :* Les clés `persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`, `system_structure` dans `prompts.json` et leurs constantes associées dans `config.py` (`PROMPT_INSTRUCTION`, `DEFAULT_VERDICT_RULES`, etc.) ne sont plus utilisées. Les supprimer allégera le code et évitera la confusion.

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

- [ ] **Forcer l'Analyse Visuelle Explicite (Clé `visual_inspection`)**
    - *Détails :* Ajouter une étape obligatoire dans le JSON de réponse : `"visual_inspection"`. L'IA devra décrire le logo, la forme de la tête et les détails visibles *avant* de rendre son verdict, pour mieux détecter les contrefaçons (Chibson, etc.).

- [ ] **Inverser la logique JSON (Chain of Thought)**
    - *Détails :* Modifier le format de réponse JSON pour demander les étapes de raisonnement (identification, état, calculs financiers) *avant* le champ `verdict`. Améliore la cohérence et réduit les hallucinations.

- [ ] **Implémenter le "Few-Shot Prompting"**
    - *Détails :* Ajouter une section `examples` dans `prompts.json` avec 2-3 exemples concrets d'analyses réussies (une vraie Gibson, une contrefaçon, une bonne affaire, une mauvaise) pour ancrer le comportement du modèle.

---

## 🚀 Améliorations Futures

- [ ] **Injection Dynamique de la Taxonomie (Optimisation tokens)**
    - *Détails :* N'envoyer à l'Expert que la branche de la taxonomie pertinente (identifiée par le Portier) plutôt que la taxonomie complète. Économise des tokens et améliore la précision.

- [ ] **Système de Feedback (Apprentissage)**
    - *Détails :* Stocker les rejets manuels avec leur motif pour constituer un dataset permettant d'affiner les futurs prompts ou de fine-tuner un modèle.

---

## ✅ Terminé

- [x] Création de la structure de documentation (`docs/`).
- [x] Mise en place du `AI_BRIEFING.md`.
- [x] Refonte responsive de la `DealCard` (Mobile First).
- [x] Analyse approfondie du système de prompts dynamiques (`docs/ARCHITECTURE.md` Section 4 mise à jour, Session 10).
