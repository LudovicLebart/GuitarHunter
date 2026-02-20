# Journal de Bord - Guitar Hunter AI

Ce journal suit les changements majeurs, les décisions d'architecture et les nouvelles fonctionnalités.

---

### **Date: 24/05/2024** (Session 9)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Ajustement de la largeur de l'image sur mobile:**
    - **Problème:** La largeur de l'image sur mobile (`w-32`) était trop étroite.
    - **Solution:** La largeur du conteneur de l'image est passée à `w-1/2` (50% de la largeur de la carte), offrant un meilleur équilibre visuel avec le bloc de prix qui occupe les 50% restants.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Cet ajustement répond à la demande de donner plus d'importance à l'image sur mobile, tout en conservant une disposition en deux colonnes compacte.

---

### **Date: 24/05/2024** (Session 8)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Refonte de la structure de la `DealCard` (Mobile First):**
    - **Problème:** La disposition précédente ne satisfaisait pas les besoins spécifiques de l'affichage mobile (image complète, compacité) et desktop (hiérarchie claire).
    - **Solution:** Une approche "Mobile First" avec deux structures distinctes a été implémentée :
        - **Mobile (`md:hidden`):** Un en-tête compact affiche l'image (largeur fixe `w-32`) et le bloc de prix côte à côte. Le titre et les détails suivent en dessous.
        - **Desktop (`hidden md:block`):** La disposition classique en deux colonnes est conservée, avec l'image "sticky" à gauche. Dans la colonne de droite, le bloc de prix est positionné au-dessus du titre pour une meilleure hiérarchie.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

2.  **Création du composant `PriceDisplay`:**
    - **Action:** La logique d'affichage du prix et du menu déroulant financier a été extraite dans un sous-composant `PriceDisplay`. Cela permet de l'utiliser à deux endroits différents dans le code (header mobile et colonne desktop) sans dupliquer la logique complexe.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

3.  **Retour à l'affichage complet des images:**
    - **Action:** Annulation du changement `object-cover` dans `ImageGallery.jsx`. Les images sont de nouveau affichées en entier (`object-contain`) pour ne perdre aucun détail de l'instrument.

#### 🤔 Raisonnement

- Cette solution hybride offre le meilleur des deux mondes : une expérience mobile optimisée pour la densité d'information et une expérience desktop riche et structurée. L'extraction du composant `PriceDisplay` maintient le code propre et maintenable malgré la duplication structurelle.

---

### **Date: 24/05/2024** (Session 6)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Uniformisation de l'affichage du bloc prix:**
    - **Problème:** Le bloc de prix pouvait encore dépasser de la carte sur certains écrans d'ordinateur lorsque le titre était long et que l'affichage était en mode "ligne" (côte à côte).
    - **Solution:** L'affichage a été uniformisé pour être identique sur mobile et desktop. Le bloc de prix est désormais **toujours** positionné en dessous du titre et aligné à gauche. Cela garantit qu'il dispose toujours de toute la largeur nécessaire et élimine tout risque de dépassement.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- La cohérence de l'interface est primordiale. En adoptant une disposition verticale unique, on simplifie la maintenance et on s'assure que le contenu critique (le prix et les détails financiers) est toujours lisible, quelle que soit la contrainte d'espace horizontal.

---

### **Date: 24/05/2024** (Session 5)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Ajustement de la taille du bouton de prix:**
    - **Problème:** Le bouton de prix, bien que fonctionnel, pouvait être rendu plus compact pour un meilleur équilibre visuel.
    - **Solution:** Plusieurs micro-ajustements ont été effectués : réduction du `padding`, de la taille de la police, de la taille de l'icône, de l'espacement interne et du rayon de la bordure.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Ce changement est un raffinement stylistique visant à perfectionner l'équilibre et l'harmonie des composants de l'interface.

---

### **Date: 24/05/2024** (Session 4)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Fusion du Bouton de Prix et du Toggle d'Expansion:**
    - **Problème:** Le bouton affichant le prix et le bouton pour déplier les détails financiers étaient deux éléments séparés, ce qui était moins intuitif et prenait plus de place.
    - **Solution:** Les deux éléments ont été fusionnés en un seul composant interactif. Le bouton de prix contient maintenant le montant et l'icône "chevron". L'ensemble du bloc est cliquable pour afficher/masquer les détails financiers.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Cette modification améliore l'expérience utilisateur en créant un point d'interaction unique et clair, ce qui est un standard de design d'interface.
- Elle permet également un gain d'espace marginal mais appréciable sur les petits écrans.

---

### **Date: 24/05/2024** (Session 3)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Refonte du Menu de Réanalyse:**
    - **Problème:** Le menu de réanalyse (Standard/Expert) était "détaché" de la carte lors du défilement (scroll) car il utilisait un `Portal`. De plus, il était trop volumineux avec du texte inutile.
    - **Solution:**
        - **Ancrage:** Le menu est maintenant rendu directement dans le DOM de la carte, positionné en absolu par rapport au bouton de réanalyse. Il suit donc parfaitement le défilelement de la page.
        - **Design Compact:** Le texte a été supprimé au profit d'icônes (`RefreshCw` et `BrainCircuit`) avec des info-bulles (`title`). Le menu est beaucoup plus discret et s'intègre mieux à l'interface.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- L'utilisation de `Portal` pour des menus contextuels liés à des éléments scrollables est souvent problématique sans une gestion complexe de la position. L'ancrage direct via CSS (`position: absolute`) est une solution plus robuste et plus simple ici.
- La réduction de la taille du menu améliore l'expérience utilisateur, en particulier sur mobile où l'espace est limité.

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
