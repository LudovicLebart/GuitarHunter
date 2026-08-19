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

- **Dataset A — "où sont les pièces sur la photo"** (keypoints Phase 1) : n'importe quelle photo de guitare sert, pas besoin de défaut. **Déjà disponible gratuitement** : 700+ annonces acoustique/classique déjà scrapées et stockées dans Firebase Storage (upload systématique lors de `handle_deal_found()`, cf. `CLAUDE.md`) — meilleure source que du scraping générique, puisque c'est exactement la distribution réelle (mêmes plateformes, mêmes angles amateurs, même qualité JPEG) sur laquelle le modèle tournera en production. Reste à faire : script d'export (parcourir `guitar_deals`, filtrer acoustique/classique, récupérer les URLs Storage) + labellisation des keypoints — **automatisée en priorité (§3bis)**, le clic manuel (CVAT/labelme) devenant un simple repli en cas d'échec de validation. Complément possible si le volume/la diversité s'avère insuffisant : Roboflow Universe, bootstrap synthétique (rendus 3D + domain randomization). Réserve mineure : ces 700 annonces reflètent les critères de recherche déjà configurés (villes/marques/prix) — léger biais de sélection, probablement sans impact réel sur la diversité angle/forme/éclairage utile à Phase 1.

### 3bis. Labellisation automatisée des keypoints (Dataset A)

Rejet du clic manuel comme méthode par défaut (700+ images, aucune patience/temps disponible côté utilisateur) au profit d'un pipeline automatisé, gardé inspectable à chaque étage (cohérent avec le principe directeur §1 — pas de boîte noire) :

1. **Localisation grossière** : un détecteur ouvert (Grounding DINO, ou Gemini Flash en repli — sortie JSON structurée, même mécanique que le pipeline 3-Tiers existant) repère approximativement les zones (tête, chevalet).
2. **Segmentation précise** : SAM (Segment Anything) affine chaque zone en contour pixel-précis à partir de la boîte grossière — plus fiable qu'une coordonnée brute renvoyée par un VLM généraliste, qui n'est pas conçu pour la précision géométrique fine.
3. **Extraction déterministe** : les points clés (coins/extrémités) sont calculés depuis le contour par OpenCV classique — pas d'IA à cette étape.
4. **Réduction du nombre de points à détecter par la géométrie connue** : la position des frettes suit une formule fixe (tempérament égal). Détecter fiablement seulement le sillet de tête + le sillet de chevalet permet de **calculer** la position théorique de la 12e frette plutôt que de la faire reconnaître visuellement — moins de points appris, moins d'erreurs cumulées.
5. **Repli si besoin** : chercher un modèle déjà entraîné sur des guitares (Roboflow Universe/HuggingFace) avant de fine-tuner depuis un backbone générique ; si la validation (§4 point 5) échoue malgré tout, correction manuelle assistée (points auto-labellisés pré-remplis dans CVAT, l'humain corrige au lieu de labelliser à vide) plutôt que clic à froid.

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

4. **Construire Dataset A en parallèle** (faible priorité tant que B n'est pas validé) : script d'export des photos déjà stockées (Firebase Storage, 700+ annonces acoustique/classique) + pipeline de labellisation automatisée des keypoints (§3bis). Clic manuel (CVAT/labelme) en repli uniquement si la validation échoue.

5. **Jalon go/no-go** : (a) valider la qualité des keypoints auto-labellisés sur un petit échantillon (comparaison visuelle rapide, pas de clic précis) avant de labelliser à l'échelle ; (b) calculer les 3 métriques (saddle ratio, belly variance, shadow delta) à la main/en script simple sur les données des étapes 1-3, avant tout entraînement de modèle, et vérifier la corrélation avec les vraies mesures. Si l'un ou l'autre ne tient pas, ne pas investir dans l'industrialisation.

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
