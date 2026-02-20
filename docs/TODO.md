# Liste des Tâches - Guitar Hunter AI

Ce document sert à suivre les tâches à accomplir, les bugs à corriger et les améliorations prévues.

**Consigne pour l'Assistant AI :**
- Consultez ce fichier au début de chaque session.
- Ajoutez-y les nouvelles tâches définies lors des discussions avec l'utilisateur.
- Marquez les tâches comme `[x]` une fois qu'elles sont terminées et validées.
- Déplacez les tâches terminées dans la section "Terminé" si la liste devient trop longue.

---

## 🚨 Priorité Haute (Bugs & Correctifs)

- [ ] **Corriger le bug relatif aux classifications de Taxonomie**
    - *Détails :* Il semble y avoir des incohérences ou des erreurs dans la manière dont les guitares sont classifiées selon la taxonomie définie. À investiguer dans `backend/analyzer.py` et les prompts.

- [ ] **Corriger le bug de compte des Guitares par taxonomie et vérifier les filtres**
    - *Détails :* Les compteurs dans la barre de filtres (ex: "Fender (3)") ne semblent pas correspondre à la réalité ou ne se mettent pas à jour correctement. Vérifier la logique de comptage dans `src/hooks/useDealsManager.js`.

## 🎨 Interface Utilisateur (UI/UX)

- [ ] **Revoir l'affichage du bloc de prix**
    - *Détails :* Continuer d'affiner le composant `PriceDisplay` dans `DealCard.jsx`. L'objectif est d'avoir un affichage clair, compact et informatif qui s'adapte parfaitement au mobile et au desktop.

## 🧠 Système de Prompts & IA

- [ ] **Inverser la logique JSON (Chain of Thought)**
    - *Détails :* Modifier le format de réponse JSON attendu pour demander les étapes de raisonnement (identification, état, calculs) *avant* le verdict final. Cela améliorera la cohérence des décisions de l'IA.

- [ ] **Implémenter le "Few-Shot Prompting"**
    - *Détails :* Ajouter une section `examples` dans `prompts.json` contenant 2-3 exemples concrets d'analyses réussies (une vraie Gibson, une fausse, une bonne affaire, une mauvaise) pour guider le modèle.

- [ ] **Forcer l'Analyse Visuelle Explicite**
    - *Détails :* Ajouter une étape obligatoire dans le JSON de réponse : `"visual_inspection"`. L'IA devra décrire le logo, la forme de la tête et les détails visibles *avant* de rendre son verdict, pour mieux détecter les contrefaçons.

- [ ] **Rendre la Taxonomie modifiable via l'interface**
    - *Détails :* Actuellement, la taxonomie est chargée statiquement depuis `prompts.json`. Il faudrait permettre de l'éditer dans le `ConfigPanel` et de la stocker dans Firestore, comme les autres prompts.

- [ ] **Ajouter une validation des prompts**
    - *Détails :* L'éditeur de prompts ne vérifie pas si l'utilisateur a cassé la structure JSON attendue. Ajouter un avertissement ou un mécanisme de "reset to default" par section serait utile.

## 🚀 Améliorations Futures

- [ ] **Système de Feedback (Apprentissage)** : Stocker les rejets manuels avec leur motif pour affiner les futurs prompts ou fine-tuner un modèle.
- [ ] **Injection Dynamique de la Taxonomie** : N'envoyer à l'Expert que la branche de la taxonomie pertinente (identifiée par le Portier) pour économiser des tokens.

---

## ✅ Terminé

- [x] Création de la structure de documentation (`docs/`).
- [x] Mise en place du `AI_BRIEFING.md`.
- [x] Refonte responsive de la `DealCard` (Mobile First).
- [x] Analyse approfondie du système de prompts dynamiques.
