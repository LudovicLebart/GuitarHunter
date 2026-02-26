# Rapport d'Analyse UI/UX - Guitar Hunter AI (Analyse Heuristique Profonde)

Suite à une réévaluation complète de l'interface basée sur l'ensemble des maquettes (ScreenShots V1), cette documentation va au-delà des simples problèmes de mise en page pour identifier les défauts majeurs d'ergonomie, d'architecture de l'information et de "Design System".

---

## 1. Défauts Structurels et de Layout (Rappel)

- **A. Le Panneau Latéral "Système" : Un Gouffre Spatial (Réf: screenshot_2)**
  La colonne latérale déséquilibre massivement la mise en page en s'accaparant ~20% de la largeur pour seulement afficher des statuts (Auth, Engine). **(Priorité: Démanteler et intégrer dans la Navbar).**
- **B. Hérésie Ergonomique des Filtres (Réf: screenshot_1)**
  La barre de recherche déborde, impliquant un scroll horizontal punitif sur Desktop. Les `select` natifs jurent avec le design. **(Priorité: Déplacer la taxonomie dans un tiroir "Sidebar Drawer").**
- **C. Images Minuscules sur Mobile (Réf: screenshot_12)**
  Le layout fractionne l'écran mobile, réduisant l'image (facteur clé de conversion) à une vignette. **(Priorité: Layout en Stack Vertical `w-full`).**

---

## 2. Nouveaux Défauts d'Ergonomie et d'Information (Deep Analysis)

### E. Typographie Agressive et Non Traitée (Titres)
- **Le Problème :** Les titres des annonces scrapées sont affichés à l'état brut. Très souvent, ils sont en TOUTES MAJUSCULES (ex: `AMPLI DE GUITARE CRATE DANS MONT-ST-HILAIRE, QC`). Sur une grille de plusieurs annonces, cet océan de majuscules est agressif pour l'œil et détruit la lisibilité (`screenshot_9`).
- **Solution Requise :** Implémenter un formateur de texte frontend (ex: CSS `text-transform: capitalize` ou une fonction JS) pour adoucir les titres et normaliser la casse avant l'affichage.

### F. Architecture Confuse du Bloc IA (Cognitive Load)
- **Le Problème :** L'information de l'Intelligence Artificielle est scindée de façon illogique.
    1. En haut du bloc, l'historique de routage des modèles (`GEMINI-2.5-FLASH-LITE -> GEMINI-2.5-FLASH`) prend une place énorme et très visible (violet + gras). C'est une donnée de "debug" inutile à un acheteur au quotidien.
    2. À l'extrême inverse, la barre de `CONFIANCE 90%` se retrouve tout en bas de la carte, isolée sous une ligne de séparation (`screenshot_1`). Elle est déconnectée du raisonnement IA textuel qui la justifie.
- **Solution Requise :** 
    - Cacher le routing des modèles LLM derrière un Tooltip au survol d'une discrète icône "✨ IA".
    - Remonter la barre de "Confiance" pour la coller immédiatement à la suite du "Raisonnement" (ou l'intégrer dans le badge de verdict avec une jauge circulaire).

### G. Manque de Lisibilité Immédiate de la "Marge" / du "Deal"
- **Le Problème :** Sur la vue liste `DealCard` classique, le prix demandé (ex: `225 $` dans un badge noir) est flottant. En dessous, l'évaluation IA (`Val: 200$`, `Max: 280$`) est écrite en très petits caractères. Contrairement à la modale détaillée (qui affiche une grande barre verte `Marge +100$`), la carte liste exige un **calcul mental** de l'utilisateur pour comprendre la rentabilité.
- **Solution Requise :** Le "Score Financier" (la marge estimée) doit être visuellement explicite dès la carte liste. Il faut un badge "+100$ Net" ou une surbrillance de la couleur de l'étiquette de prix si le ROI est excellent.

### H. Action Buttons : Faible Contraste et Hit-Zones
- **Le Problème :** La rangée de boutons utilitaires (Cœur, Refresh, Ban, Corbeille, Share) en bas des cartes ou modales utilise des icônes grises sur un fond gris très clair (`bg-slate-50`). Le contraste est bien en dessous des normes d'accessibilité. De plus, sur mobile, toucher ces petits cercles rapprochés est source de "Fat Finger errors".
- **Solution Requise :**
    - Agrandir les cibles cliquables (hit-zones à minimum 44x44px).
    - Augmenter significativement le contraste des icônes.
    - Remplacer le verbeux bouton "Voir sur Facebook" par une simple icône "F" bleue officielle.

---

## 3. Synthèse des Priorités (Roadmap UI/UX)

1. **Démanteler le panneau latéral** (Gains d'espace massifs).
2. **Refonte des Filtres en Drawer** (Supprime le scroll horizontal bloquant).
3. **Refonte Mobile Stack-Vertical** (L'image dicte la vente, elle doit être énorme).
4. **Correction du "Bruit Visuel" (Typographie & Bloc IA)** : Nettoyer les Majuscules, cacher les noms de LLM, fusionner la jauge de Confiance avec le verdict.
5. **Rendre le Profit Évident** : Afficher la "Marge Nette" visuellement sur chaque card liste.
