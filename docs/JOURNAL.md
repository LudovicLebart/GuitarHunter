# Journal de Bord - Guitar Hunter AI

Ce journal suit les changements majeurs, les décisions d'architecture et les nouvelles fonctionnalités.

---

### **Date: 24/05/2024** (Session 2)

**Auteur:** Assistant AI

**Type:** Amélioration du Design Responsive (UI/UX)

#### 📝 Description des Changements

1.  **Amélioration de l'affichage de la `DealCard` sur mobile:**
    - **Problème:** Sur les écrans de petite taille, le bloc contenant les informations financières (`Prix`, `Valeur Estimée`, etc.) ne passait pas à la ligne et débordait de la carte, rendant l'interface inutilisable.
    - **Solution:** La structure de l'en-tête de la carte a été rendue "responsive" :
        - Sur les écrans `md` et plus, le titre et le bloc financier sont côte à côte.
        - Sur les petits écrans (mobile), le bloc financier passe automatiquement sous le titre, utilisant toute la largeur disponible et évitant tout dépassement.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

2.  **Simplification de l'affichage du prix:**
    - **Problème:** Pour gagner de la place sur mobile, l'affichage du prix pouvait être plus compact.
    - **Solution:**
        - La mention "Prix Demandé" a été supprimée.
        - La taille de la police du prix a été réduite (`text-xl` au lieu de `text-2xl`).
        - Le padding du conteneur du prix a été ajusté.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Ces changements sont cruciaux pour l'utilisabilité de l'application sur des appareils mobiles. Ils suivent les principes du "responsive design" en adaptant la disposition du contenu à la taille de l'écran.
- La simplification du prix contribue à une interface plus épurée et directe.

---

### **Date: 24/05/2024** (Session 1)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX) & Correction de bug

#### 📝 Description des Changements

1.  **Refonte du Module Financier sur la `DealCard`:**
    - **Problème:** Les indicateurs financiers clés (`estimated_value`, `net_guitar_cost`, etc.) étaient cachés sous des conditions trop restrictives (ex: uniquement si la marge était positive ou si l'annonce n'était pas rejetée).
    - **Solution:** Un nouveau module financier a été implémenté :
        - **Toujours visible:** Le prix demandé, la valeur estimée et le potentiel de revente sont maintenant toujours visibles si les données existent, même pour les annonces rejetées.
        - **Détails sur demande:** Un menu déroulant (toggle) a été ajouté pour afficher les détails techniques comme le **Coût Net** et la **Marge Brute**.
        - **Code couleur:** La marge brute est maintenant colorée (vert si positive, rouge si négative) pour une identification rapide de la rentabilité.
    - **Fichier modifié:** `src/components/DealCard.jsx`

2.  **Correction du Bug de Réanalyse "Expert":**
    - **Problème:** Lors d'un clic sur le bouton de réanalyse "Expert", l'indicateur de chargement (spinner) ne s'activait pas car le statut `analyzing_expert` n'était pas correctement géré par le frontend.
    - **Solution:** Le statut `analyzing_expert` a été ajouté aux listes de vérification `isAnalyzing` et `getModelName` dans la `DealCard`.
    - **Fichier modifié:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- La refonte du module financier a pour but de fournir à l'utilisateur un contexte complet sur **pourquoi** une annonce est jugée bonne ou mauvaise, même après qu'elle ait été rejetée.
- La correction du bug de réanalyse améliore le retour visuel pour l'utilisateur, confirmant que son action a bien été prise en compte.

---
