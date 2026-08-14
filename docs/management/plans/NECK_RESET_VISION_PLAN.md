# Plan de Réflexion : Détection Visuelle de l'État de l'Action / Besoin de Neck Reset

**Statut :** Réflexion R&D — aucune implémentation commencée. Ce document capture le raisonnement et le plan de match issus d'une session de brainstorming (2026-08-14), à valider/amender avant tout début de code.

**Objectif :** À partir des photos d'une annonce (Facebook/Kijiji), estimer un score de probabilité de "travaux structurels nécessaires" (action trop haute, besoin de neck reset), sans dépendre d'un CNN boîte noire qui risquerait d'apprendre la qualité de la photo plutôt que la géométrie réelle de la guitare.

**Lien avec Guitar Hunter :** Projet satellite, pensé pour s'intégrer plus tard dans le pipeline existant (en aval du filtrage texte/marque/prix déjà fait par les Tiers 1/2/3, §"Pipeline IA (3-Tiers)" de `CLAUDE.md`) — pas encore câblé, pas de dépendance actuelle avec `backend/analyzer.py`.

---

## 1. Principe directeur

Interdiction de principe d'un CNN "boîte noire" (type ResNet) entraîné à classer "bonne/mauvaise action" directement sur les photos scrapées. Risque identifié : sur des photos de qualité "poubelle" (angles aléatoires, compression JPEG, mauvais éclairage), un tel modèle a de fortes chances d'apprendre à corréler mauvaise photo ↔ mauvaise guitare (les vendeurs peu soigneux prennent souvent les deux) plutôt que d'apprendre la géométrie réelle.

**Approche retenue :** décomposer le problème en métriques géométriques interprétables, calculées après normalisation de l'image, plutôt qu'une classification opaque de bout en bout.

## 2. Architecture R&D envisagée (3 phases)

**Phase 1 — Localisation et normalisation géométrique**
- Détection de points clés (type YOLOv8-Pose) : extrémités du sillet de tête, bords de la touche à la 12e frette, extrémités du sillet de chevalet.
- Homographie (OpenCV) pour redresser l'image (manche vertical, table vue de face) — rend les mesures en pixels comparables d'une annonce à l'autre.

**Phase 2 — Extraction par ROI (Region of Interest)**
- *Saddle Profiler* : ratio de surface claire (os/tusq) vs foncée (bois) sur un crop serré du sillet de chevalet → détecte un sillet limé à l'excès.
- *Bellying Scanner* : densité des bords haute fréquence (Canny/Sobel) juste derrière le chevalet → détecte une déformation de la table.
- *Fretboard Shadowing* : écart (Hough Line Transform) entre la corde de Mi grave et son ombre à hauteur de la 12e frette → proxy de la hauteur d'action.

**Phase 3 — Intégration pipeline**
- Filtrage en entonnoir : inférence lourde uniquement sur les annonces déjà retenues par le texte (marque/modèle/prix), pas sur tout le flux scrapé.
- Stockage des vecteurs extraits uniquement (pas des images redressées) dans une base locale (PostgreSQL/SQLite).
- Score de sortie : probabilité 0-100 de "travaux structurels", affiché dans le dashboard — pas de verdict binaire.

**Stack envisagée :** prototypage en Python pur (OpenCV + ultralytics) en priorité ; portage LibTorch/C++ (dans l'esprit du portage MoneyBot) différé après validation de l'approche, et seulement si le débit d'inférence devient un vrai problème (peu probable vu le filtrage en amont).

## 3. Le vrai enjeu identifié : le dataset, pas l'architecture

Deux besoins de données bien distincts, de difficulté très différente :

- **Dataset A — "où sont les pièces sur la photo"** (keypoints Phase 1) : n'importe quelle photo de guitare sert, pas besoin de défaut. Sources : Roboflow Universe (datasets communautaires existants), scraping large de photos diverses, labellisation manuelle légère (CVAT/labelme) avec transfer learning depuis un backbone pré-entraîné, bootstrap synthétique possible (rendus 3D + domain randomization).

- **Dataset B — "le signal visuel prédit la vraie mesure"** (calibration Phase 2) : le vrai goulot d'étranglement. Nécessite des paires (photo, mesure réelle mesurée à la main). Un label binaire "besoin de neck reset" est rare et coûteux (diagnostic d'expert) ; reformulé en métrique continue bon marché (hauteur de corde à la 12e frette, hauteur de sillet restante) mesurable par n'importe qui avec une jauge/règle sur n'importe quelle guitare, bonne ou mauvaise.

**Absence de magasins d'instruments usagés à Montréal** identifiée comme contrainte réelle — pivote la stratégie de collecte vers les luthiers/écoles de lutherie plutôt que le commerce de détail.

**Idée validée en session :** exploiter les guitares à manche vissé (ex. Art & Lutherie) de l'utilisateur — le "neck reset" s'y fait par changement de cale à la jonction (réversible), permettant de mesurer et photographier plusieurs configurations d'angle réel du manche dans une seule session, sur une guitare confirmée nécessiter une correction. Résout la limite du manche collé (où l'angle ne peut pas être modifié sans opération irréversible).

## 4. Plan de match

0. **Principe :** deux datasets distincts (A = keypoints, B = calibration), ne pas les confondre dans la collecte.

1. **Exploiter les 2 guitares de l'utilisateur immédiatement (Dataset B, coût nul, priorité)**
   - Guitare à manche vissé : mesurer l'état actuel (action 12e frette, hauteur de sillet) → photographier (protocole complet, §5) → dévisser, tester 2-3 épaisseurs de cale → mesurer + photographier à chaque configuration.
   - Guitare à manche collé (si applicable) : même protocole photo/mesure sur l'état actuel ; variation de l'action via cales sous le sillet de chevalet possible (réversible), pas de variation d'angle du manche (irréversible sur ce type de jonction).

2. **Combler la généralisation** : mesurer/photographier d'autres guitares accessibles (propres guitares restantes, entourage) pour vérifier que la relation signal↔mesure ne dépend pas de l'apparence d'une seule guitare (bois/chevalet/finition).

3. **Approcher un luthier ou une école de lutherie montréalaise** pour documenter de vrais neck resets en cours (avant/après, mesure réelle) en échange d'un accès aux résultats — source de cas positifs confirmés en volume, alternative identifiée à l'absence de magasins d'occasion locaux.

4. **Construire Dataset A en parallèle** (faible priorité tant que B n'est pas validé) : dataset Roboflow Universe existant + scraping large + labellisation légère.

5. **Jalon go/no-go** : calculer les 3 métriques (saddle ratio, belly variance, shadow delta) à la main/en script simple sur les données des étapes 1-3, avant tout entraînement de modèle, et vérifier la corrélation avec les vraies mesures. Si le signal ne corrèle pas, ne pas investir dans l'industrialisation.

6. **Industrialisation** (seulement après validation de l'étape 5) : entraînement du modèle de keypoints, assemblage du pipeline complet, portage C++/LibTorch si besoin de performance avéré.

## 5. Protocole photo retenu (par guitare/configuration mesurée)

1. Vue d'ensemble manche + corps dans le même cadre (sillet de tête → chevalet).
2. Gros plan sur le sillet de chevalet.
3. Gros plan sur la zone juste derrière le chevalet (table).
4. Gros plan sur la 12e frette avec cordes visibles.
5. (Optionnel, haute valeur si réalisable) Photo "en visée" depuis la tête le long du manche.

Chaque vue déclinée sur plusieurs angles/éclairages — utile pour la robustesse du futur détecteur de keypoints, mais ne remplace pas le besoin de guitares visuellement différentes pour la généralisation (§3).

## 6. Points ouverts / non tranchés

- Modalités précises du contact luthier/école de lutherie (message à rédiger).
- Volume cible du Dataset B avant de juger l'étape 5 concluante.
- Reformulation éventuelle du score de sortie (continu vs seuils) une fois la corrélation réelle connue.
