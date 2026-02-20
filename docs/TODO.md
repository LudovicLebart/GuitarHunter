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

## 🚀 Améliorations Futures

- [ ] (Espace réservé pour les futures fonctionnalités)

---

## ✅ Terminé

- [x] Création de la structure de documentation (`docs/`).
- [x] Mise en place du `AI_BRIEFING.md`.
- [x] Refonte responsive de la `DealCard` (Mobile First).
