# Plan de Réflexion : Détection Visuelle de l'État de l'Action / Besoin de Neck Reset

**Statut :** Réflexion R&D — aucune implémentation commencée. Ce document capture le raisonnement et le plan de match issus d'une session de brainstorming (2026-08-14), à valider/amender avant tout début de code.

**Objectif :** À partir des photos d'une annonce (Facebook/Kijiji), estimer un score de probabilité de "travaux structurels nécessaires" (action trop haute, besoin de neck reset), sans dépendre d'un CNN boîte noire qui risquerait d'apprendre la qualité de la photo plutôt que la géométrie réelle de la guitare.

**Lien avec Guitar Hunter :** Projet satellite, pensé pour s'intégrer plus tard dans le pipeline existant (en aval du filtrage texte/marque/prix déjà fait par les Tiers 1/2/3, §"Pipeline IA (3-Tiers)" de `CLAUDE.md`) — pas encore câblé, pas de dépendance actuelle avec `backend/analyzer.py`.

---

## 1. Principe directeur

Interdiction de principe d'un CNN "boîte noire" (type ResNet) entraîné à classer "bonne/mauvaise action" directement sur les photos scrapées. Risque identifié : sur des photos de qualité "poubelle" (angles aléatoires, compression JPEG, mauvais éclairage), un tel modèle a de fortes chances d'apprendre à corréler mauvaise photo ↔ mauvaise guitare (les vendeurs peu soigneux prennent souvent les deux) plutôt que d'apprendre la géométrie réelle.

**Approche retenue :** décomposer le problème en métriques géométriques interprétables, calculées après normalisation de l'image, plutôt qu'une classification opaque de bout en bout. **Contrainte de licence associée** (ajoutée après revue externe, §2ter) : les briques du pipeline doivent rester réellement open source/gratuites pour un usage produit — Ultralytics/YOLOv8 (AGPL) est écarté par défaut à ce titre, pas seulement pour des raisons techniques.

## 2. Architecture R&D envisagée (révisée après revue externe — voir §2ter)

**Phase 1 — Localisation et repérage géométrique**
- **Repérage principal, sans modèle entraîné** : le motif des frettes sert de mire de calibration naturelle — l'espacement suit la loi fixe du tempérament égal (`d·2^(-n/12)`). Détection de segments (LSD/M-LSD/DeepLSD) + ajustement RANSAC de ce motif identifie chaque frette d'un coup, donne l'échelle métrique locale, et un résidu de fit qui sert de critère d'abstention automatique. Zéro label, zéro licence à gérer, entièrement inspectable.
- **Repli si le motif de frettes n'est pas exploitable** (guitare trop petite/floue/angle défavorable) : détection de keypoints via un modèle entraîné — MMPose/RTMPose, DeepLabCut ou SLEAP (Apache/LGPL/BSD), pas YOLOv8-Pose (AGPL).
- **Homographie globale abandonnée comme étape obligatoire.** Les 6 keypoints initialement prévus sont quasi colinéaires (estimation dégénérée dans l'axe qu'on veut justement mesurer) et une guitare n'est pas un plan unique (cordes flottantes au-dessus de la touche, sillet en relief) — une rectification globale réintroduirait une dépendance à l'angle de prise de vue, l'exact confondeur que Phase 2 doit éviter. Remplacée par des mesures en unités locales (Phase 2), sauf pour le diagnostic d'angle de manche qui reste un cas à part (voir §5).

**Phase 2 — Extraction par mesures locales (remplace les ROI couleur/fréquence initiales)**
- *Hauteur d'action* (remplace Fretboard Shadowing) : ratio `(distance corde↔sommet de frette à la 12e frette) / (diamètre de la corde de Mi grave)` — la corde sert d'étalon métrique local (±12% d'incertitude connue), invariant à la perspective locale, sans dépendre d'une ombre ni d'un éclairage particulier. Extraction par filtres de crêtes adaptés aux structures fines (`scikit-image` `frangi`/`sato`/`meijering`) + squelettisation + fit robuste (Theil-Sen/RANSAC) — plus fiable que Hough Line Transform sur du JPEG compressé. **Sortie reformulée en classification grossière (basse/normale/haute/non mesurable), pas en mm continus** — la résolution réelle des photos (§3quater) ne permet pas de résoudre des écarts de l'ordre du mm de façon fiable.
- *Hauteur de sillet restante* (remplace Saddle Profiler) : même étalon (diamètres de corde), mesuré en hauteur exposée au-dessus du chevalet via un masque de segmentation (SAM 2.1) — géométrie, pas couleur, donc robuste aux sillets synthétiques noirs/Micarta qui cassaient le ratio de couleur initial.
- *Bombement / déformation* (remplace Bellying Scanner) : densité de bords haute fréquence abandonnée — corrélée à la compression JPEG et au grain du bois plus qu'à une vraie déformation, en contradiction avec le principe directeur §1. Deux remplaçants, chacun avec ses limites : (a) angle chevalet/table, nécessite une vue de profil (rare, §5) ; (b) détection de décollement de chevalet (ligne d'ombre à la jonction chevalet/table), signal binaire plus robuste et tolérant à plus d'angles. Le bombement pur reste probablement hors de portée sans contrôle de l'éclairage — objectif dégradé assumé plutôt que gonflé artificiellement.
- *Angle du manche* (nouveau, distinct de la hauteur d'action) : reproduction numérique de la méthode du luthier — fit Theil-Sen sur les sommets de frettes détectés, extrapolé jusqu'au chevalet. Nécessite une vue de profil ou 3/4 serré, rare dans les annonces — traité comme **signal bonus**, pas comme métrique principale (voir §5, découplage action/angle).

**Phase 3 — Intégration pipeline**
- Filtrage en entonnoir : inférence lourde uniquement sur les annonces déjà retenues par le texte (marque/modèle/prix), pas sur tout le flux scrapé.
- Stockage des vecteurs extraits uniquement (pas des images redressées) dans une base locale (PostgreSQL/SQLite).
- **Score de sortie révisé** : plus un score 0-100 toujours confiant, ni une estimation continue en mm. Sortie = **classification grossière** (basse/normale/haute) + option explicite **"non mesurable"**, éventuellement assortie d'un intervalle de confiance calibré (MAPIE — conformal prediction, licence BSD) si un raffinement continu s'avère utile plus tard. Décision actée après mesure de la résolution réelle disponible (§3quater) — comble aussi l'angle mort d'abstention relevé en revue externe.

**Stack envisagée :** prototypage en Python pur (OpenCV/scikit-image + modèles ci-dessus) en priorité ; portage LibTorch/C++ (dans l'esprit du portage MoneyBot, jugé non réutilisable tel quel — hors sujet RL vs vision, cf. historique de session) différé après validation de l'approche, et seulement si le débit d'inférence devient un vrai problème (peu probable vu le filtrage en amont).

## 2ter. Revue externe (Fable, 2026-08-19)

Une revue critique du plan a été demandée à un second modèle (Fable) pour challenger les choix techniques et proposer des alternatives open source/gratuites plus fiables. Conclusions principales, intégrées ci-dessus :
- Failles identifiées : homographie mal posée (points colinéaires, guitare non plane), Shadow Gap non calibrable sans contrôle de l'éclairage, Saddle Profiler non invariant à la couleur du sillet, Bellying Scanner probablement corrélé à la compression JPEG plutôt qu'à une vraie déformation, absence de référence d'échelle et de mécanisme d'abstention, licence AGPL d'Ultralytics incompatible avec l'objectif open source.
- Pas de verdict de faisabilité binaire rendu : l'architecture stratégique (métriques interprétables, deux datasets séparés, go/no-go) est jugée saine, mais la viabilité concrète dépend d'une donnée non encore mesurée — le taux réel de photos d'annonces exploitables (estimation à vue de nez, non mesurée : possiblement &lt;10%). D'où l'**Étape 0** ajoutée au plan de match (§4).

## 3. Le vrai enjeu identifié : le dataset, pas l'architecture

Deux besoins de données bien distincts, de difficulté très différente :

- **Dataset A — "où sont les pièces sur la photo"** (keypoints Phase 1) : n'importe quelle photo de guitare sert, pas besoin de défaut. **Déjà disponible gratuitement** : 700+ annonces acoustique/classique déjà scrapées et stockées dans Firebase Storage (upload systématique lors de `handle_deal_found()`, cf. `CLAUDE.md`) — meilleure source que du scraping générique, puisque c'est exactement la distribution réelle (mêmes plateformes, mêmes angles amateurs, même qualité JPEG) sur laquelle le modèle tournera en production. Reste à faire : script d'export (parcourir `guitar_deals`, filtrer acoustique/classique, récupérer les URLs Storage) + labellisation des keypoints — **automatisée en priorité (§3bis)**, le clic manuel (CVAT/labelme) devenant un simple repli en cas d'échec de validation. Complément possible si le volume/la diversité s'avère insuffisant : Roboflow Universe, bootstrap synthétique (rendus 3D + domain randomization). Réserve mineure : ces 700 annonces reflètent les critères de recherche déjà configurés (villes/marques/prix) — léger biais de sélection, probablement sans impact réel sur la diversité angle/forme/éclairage utile à Phase 1.

### 3bis. Labellisation automatisée des keypoints (Dataset A)

Rejet du clic manuel comme méthode par défaut (700+ images, aucune patience/temps disponible côté utilisateur) au profit d'un pipeline automatisé, gardé inspectable à chaque étage (cohérent avec le principe directeur §1 — pas de boîte noire) :

1. **Localisation grossière** : Florence-2 (MIT, Microsoft) ou OWLv2 (Apache-2.0) plutôt que Grounding DINO/Gemini Flash — open source, gratuits, tournent en local. Astuce de robustesse : prompter sur des concepts fréquents ("guitar headstock", "guitar bridge") plutôt que sur le vocabulaire ambigu de lutherie ("nut", "saddle"), puis descendre au point précis par position relative dans le crop.
2. **Segmentation précise** : SAM 2.1 (Apache-2.0, plus précis et plus léger que SAM 1 ; HQ-SAM si les contours fins du sillet comptent particulièrement) affine chaque zone en contour pixel-précis à partir de la boîte grossière — plus fiable qu'une coordonnée brute renvoyée par un VLM généraliste, qui n'est pas conçu pour la précision géométrique fine. Limite connue : les cordes/chevilles occluent partiellement le sillet de chevalet, SAM peut les inclure/exclure de façon incohérente d'une image à l'autre — à surveiller en validation (point 3).
3. **Validation par cohérence géométrique, pas par inspection visuelle** : les points extraits sont testés en ajustant le motif de fréquence des frettes (Phase 1) dessus — tout label dont le résidu dépasse un seuil est rejeté automatiquement. Erreur chiffrée en pixels, tri objectif "labels fiables / à corriger", remplace la simple "comparaison visuelle rapide" prévue initialement (une erreur de quelques pixels est invisible à l'œil sur une vignette mais fatale pour la mesure).
4. **Réduction du nombre de points à détecter par la géométrie connue** : la position des frettes suit une formule fixe (tempérament égal). Détecter fiablement seulement le sillet de tête + le sillet de chevalet permet de **calculer** la position théorique de la 12e frette plutôt que de la faire reconnaître visuellement — moins de points appris, moins d'erreurs cumulées.
5. **Repli si besoin** : chercher un modèle déjà entraîné sur des guitares (Roboflow Universe/HuggingFace) avant de fine-tuner depuis un backbone générique ; si la validation (point 3) échoue malgré tout, correction manuelle assistée (points auto-labellisés pré-remplis dans un outil comme Label Studio, l'humain corrige au lieu de labelliser à vide) plutôt que clic à froid.

- **Dataset B — "le signal visuel prédit la vraie mesure"** (calibration Phase 2) : le vrai goulot d'étranglement. Nécessite des paires (photo, mesure réelle mesurée à la main). Un label binaire "besoin de neck reset" est rare et coûteux (diagnostic d'expert) ; reformulé en métrique continue bon marché (hauteur de corde à la 12e frette, hauteur de sillet restante) mesurable par n'importe qui avec une jauge/règle sur n'importe quelle guitare, bonne ou mauvaise.

**Absence de magasins d'instruments usagés à Montréal** identifiée comme contrainte réelle — pivote la stratégie de collecte vers les luthiers/écoles de lutherie plutôt que le commerce de détail.

**Idée validée en session :** exploiter les guitares à manche vissé (ex. Art & Lutherie) de l'utilisateur — le "neck reset" s'y fait par changement de cale à la jonction (réversible), permettant de mesurer et photographier plusieurs configurations d'angle réel du manche dans une seule session, sur une guitare confirmée nécessiter une correction. Résout la limite du manche collé (où l'angle ne peut pas être modifié sans opération irréversible).

**Protocole de session affiné (après revue externe) — deux confusions distinctes, deux garde-fous distincts :**
- *Confusion "conditions de prise de vue"* (un signal qui ne reflèterait qu'une lumière/un angle particulier plutôt que l'action réelle) : couverte par la randomisation déjà prévue — plusieurs photos par réglage de cale, avec éclairage/distance/angle/focale volontairement variés autant que possible.
- *Confusion "apparence de cette guitare précise"* (un signal qui accrocherait sur le grain du bois ou la forme du chevalet de cette guitare-là plutôt que sur la géométrie) : **non résolue par la randomisation des conditions de prise de vue**, puisque bois/chevalet/cordes restent identiques sur toutes les photos d'une même guitare, quelles que soient les conditions. Seul un test **leave-one-guitare-out** (calibrer sur une guitare, vérifier que ça tient sur l'autre, jamais utilisée pour calibrer) peut la détecter — critère formalisé au jalon go/no-go (§4). Avec seulement 2 guitares ce n'est pas une validation statistique robuste, mais un garde-fou réel : si le signal s'effondre d'une guitare à l'autre, c'est un signe fort qu'il était illusoire.

**Sources gratuites complémentaires identifiées (revue externe), à coût nul :**
- **BlenderProc** (pipeline de rendu gratuit) + modèle 3D de guitare (Sketchfab/BlenderKit CC) : angle de manche et action paramétrables, génère des paires (image, mesure exacte connue) par milliers avec domain randomization — complète (pas ne remplace pas) les mesures réelles, qui restent indispensables pour valider le transfert simulation→réel.
- Forums de lutherie (Acoustic Guitar Forum, Unofficial Martin Guitar Forum) et vidéos YouTube de neck resets (frames avant/après avec mesures annoncées par le luthier) — paires photo/mesure hétérogènes mais gratuites et issues de vraies guitares défectueuses.

### 3ter. Élargissement au périmètre électrique (discussion 2026-08-19)

**Idée soulevée par l'utilisateur :** élargir le périmètre aux guitares électriques — beaucoup plus de volume (3000+ annonces vs 700+), et beaucoup de manches vissés (Fender-style notamment) accessibles pour reproduire l'expérience à la cale sur de nombreux instruments différents, attaquant directement le critère leave-one-guitare-out (§3) à moindre coût.

**Nuance essentielle établie en discussion :** la ligne de partage pertinente n'est **pas** acoustique vs électrique, mais **manche vissé (bolt-on) vs manche collé/set-neck** :
- *Manche vissé* (Fender-style, la plupart des Squier/Ibanez, Art & Lutherie côté acoustique) : la cale est un réglage routinier et réversible — pas un "neck reset" au sens structurel.
- *Manche collé/set-neck* : dovetail acoustique traditionnel, **mais aussi** Gibson Les Paul/SG, PRS set-neck, semi-hollow/hollow body (ES-335 et proches) — un vrai neck reset structurel s'y applique, comparable à celui d'une acoustique.

**Décision retenue :**
- **Dataset A** (keypoints) : élargi à toutes les guitares, électriques comprises — pur gain de volume/diversité, aucune dépendance au type de jonction (Phase 1 ne juge pas l'état de la guitare).
- **Dataset B** (calibration) : élargi de la même façon — la hauteur d'action mesurée reste une grandeur géométrique universelle, et les manches vissés électriques (beaucoup plus nombreux/accessibles que les 2 guitares actuelles) permettent de reproduire l'expérience à la cale sur de nombreux instruments pour renforcer le test leave-one-guitare-out.
- **Diagnostic produit** ("neck reset" spécifiquement) : reste conditionné au type de jonction, pas au type d'instrument. Nécessite un **classificateur modèle → type de jonction** (bolt-on/set-neck) en aval du score géométrique, alimenté à partir de `brand`/`model_name` déjà extraits par le pipeline IA existant (`aiAnalysis`) — nouveau point ouvert (§6). Sur manche vissé (électrique ou acoustique), une action haute signale un réglage à faible coût ; sur manche collé (électrique ou acoustique), elle peut signaler un vrai neck reset coûteux.
- Le filtre de collecte actuel (`ACOUSTIC_MARKERS` dans `backend/scripts/export_neck_reset_sample.py`, limité à acoustique/classique) n'a pas encore été élargi — l'Étape 0 en cours porte sur le périmètre initial ; l'élargissement électrique est une évolution documentée mais pas encore implémentée dans le script.

### 3quater. Résolution réelle des images collectées — conclusion définitive (2026-08-19)

L'Étape 0 initialement prévue (compter à la main sur 50 annonces combien ont une vue exploitable) a été remplacée par une vérification plus rigoureuse et quantitative : plutôt que "y a-t-il des gros plans", la vraie question est "la résolution d'une vue d'ensemble suffit-elle à distinguer les écarts d'action qu'on veut mesurer". Vérifiée empiriquement, pas supposée.

**Méthode et résultats :**
- Export réel (`backend/scripts/export_neck_reset_sample.py`, exécuté via `.github/workflows/run_script.yml` sur la branche dédiée `ops/run-script`) : **894 annonces acoustique/classique éligibles** (7 utilisateurs), échantillon de 50 — 47/50 photos à ~720×960px, 3/50 en vignette 261×261px.
- Inspection visuelle de 4 photos réelles de l'échantillon : la guitare occupe ~70-90% de la hauteur du cadre (meilleur que l'hypothèse initiale prudente), mais **2 des 4 photos regardées n'étaient même pas la guitare** (ampli, étui vide) — le nombre de photos par annonce surestime le nombre de vues réellement utiles.
- **Calcul de résolution effective** à ~1,36 mm/px (guitare ~1020mm réels sur ~750px) : l'espacement de frettes à la 12e case (~18mm réels) → ~13px, **suffisant pour la mire de calibration** (Phase 1, §2, tient). L'écart corde-frette qu'on veut mesurer pour l'action (~1-1,5mm de différence réelle entre normale et haute) → **~0,7-1,1px seulement**, en dessous du seuil de mesure fiable même avec détection sub-pixel soignée, sur des photos déjà visiblement compressées (60-150 Ko).
- **Cause racine tracée dans le code, pas supposée** : `backend/repository.py::upload_images_to_storage()` confirmé pass-through pur (aucun resize/recompression côté Guitar Hunter). Le plafond vient de Facebook lui-même — `backend/scraping/parser.py` lit `img.get_attribute("src")` du carrousel DOM, sans vérifier `srcset`. Une URL réelle capturée par l'utilisateur confirme un paramètre CDN explicite `stp=dst-jpg_s960x960_tt6` (plafond de 960px assumé côté Facebook, pas un hasard).
- **Contournement testé et fermé** : modification du paramètre de taille dans l'URL (`s960x960` → `s2048x2048`, ou suppression du paramètre) → **HTTP 403 "URL signature mismatch"** à chaque fois (testé en direct). Le token `oh=` signe l'URL entière, `stp` inclus — pas de manipulation possible.
- **Kijiji comparé et écarté comme alternative** : script dédié `backend/scripts/compare_image_resolution_by_source.py` (857 annonces Facebook éligibles vs 37 Kijiji, 15 mesurées de chaque) → Facebook 668×960px/93 Ko en moyenne, **Kijiji 640×798px/41 Ko en moyenne — légèrement pire**, malgré une source de données plus structurée (`__NEXT_DATA__` JSON). L'hypothèse "l'API structurée donne l'original" ne se vérifie pas dans les faits.
- **Aucun mode zoom/plein écran accessible** confirmé par l'utilisateur sur l'interface Facebook normale (desktop et mobile) pour obtenir une variante mieux résolue.

**Conclusion actée :** ~960px est la limite pratique réelle de ce qu'un accès anonyme permet de récupérer sur Facebook (et Kijiji ne fait pas mieux) — pas un artefact du pipeline Guitar Hunter, pas contournable par une modification du scraper. Le pipeline se conçoit **autour** de cette contrainte : la hauteur d'action passe d'une estimation continue en mm à une **classification grossière** (basse/normale/haute/non mesurable, §2 Phase 2/3) — objectif dégradé assumé, cohérent avec le principe directeur §1 (ne pas prétendre à une précision que les données ne permettent pas).

## 4. Plan de match

0. **Principe :** deux datasets distincts (A = keypoints, B = calibration), ne pas les confondre dans la collecte.

1. **✅ Étape 0 (close, 2026-08-19)** : remplacée par une vérification quantitative de la résolution réelle disponible plutôt qu'un comptage visuel — voir §3quater pour le détail complet et la conclusion (résolution insuffisante pour une mesure continue en mm, suffisante pour la mire de calibration ; sortie reformulée en classification grossière).

2. **Exploiter les 2 guitares de l'utilisateur immédiatement (Dataset B, coût nul, priorité)**
   - Guitare à manche vissé : mesurer l'état actuel (action 12e frette, hauteur de sillet) → photographier (protocole complet, §5, plusieurs conditions par réglage) → dévisser, tester 2-3 épaisseurs de cale → mesurer + photographier à chaque configuration.
   - Guitare à manche collé (si applicable) : même protocole photo/mesure sur l'état actuel ; variation de l'action via cales sous le sillet de chevalet possible (réversible), pas de variation d'angle du manche (irréversible sur ce type de jonction).

3. **Combler la généralisation** : mesurer/photographier d'autres guitares accessibles (propres guitares restantes, entourage) pour le test leave-one-guitare-out (§3) — pas juste "utile", mais un critère formel du jalon go/no-go (étape 6).

4. **Approcher un luthier ou une école de lutherie montréalaise** pour documenter de vrais neck resets en cours (avant/après, mesure réelle) en échange d'un accès aux résultats — source de cas positifs confirmés en volume, alternative identifiée à l'absence de magasins d'occasion locaux. Sources gratuites complémentaires en parallèle : forums de lutherie, vidéos YouTube de neck resets (§3).

5. **Construire Dataset A en parallèle** (faible priorité tant que B n'est pas validé) : script d'export des photos déjà stockées (Firebase Storage, 700+ annonces acoustique/classique) + pipeline de labellisation automatisée des keypoints (§3bis, Florence-2 + SAM 2.1 + validation géométrique). Clic manuel en repli uniquement si la validation échoue.

6. **Jalon go/no-go** : (a) ✅ résolution des photos jugée suffisante pour la mire de calibration (§3quater) — critère reformulé pour la mesure d'action, qui vise désormais une classification grossière plutôt qu'une valeur continue ; (b) qualité des keypoints auto-labellisés validée par résidu géométrique chiffré (§3bis point 3), pas par inspection visuelle ; (c) les métriques de Phase 2 (§2) calculées à la main/en script simple sur les données des étapes 2-4 corrèlent avec les vraies mesures **en validation croisée leave-one-guitare-out** (§3) — une corrélation qui ne tient que sur la guitare ayant servi à calibrer ne compte pas. Si (b) ou (c) ne tient pas, ne pas investir dans l'industrialisation.

7. **Industrialisation** (seulement après validation de l'étape 6) : entraînement du/des modèle(s) de repli, assemblage du pipeline complet avec sortie calibrée (MAPIE + abstention), portage C++/LibTorch si besoin de performance avéré.

## 5. Protocole photo retenu (par guitare/configuration mesurée)

1. Vue d'ensemble manche + corps dans le même cadre (sillet de tête → chevalet).
2. Gros plan sur le sillet de chevalet.
3. Gros plan sur la zone juste derrière le chevalet (table).
4. Gros plan sur la 12e frette avec cordes visibles.
5. (Optionnel, haute valeur si réalisable) Photo "en visée" depuis la tête le long du manche.

Chaque vue déclinée sur plusieurs conditions (angle, distance, éclairage, focale si possible) autant que réalisable par réglage de cale — couvre la confusion "conditions de prise de vue" (§3), mais **pas** la confusion "apparence de cette guitare précise", qui nécessite une deuxième guitare (§3, §4 point 3).

**Rareté de la vue de profil dans les vraies annonces (constat utilisateur, confirmé par la revue externe) :** l'essentiel des photos de vendeurs ne montre pas de vue de profil/en visée — la vue 5 ci-dessus reste l'exception, pas la norme. Conséquence directe sur l'ambition du pipeline (§2, Phase 2) : la **hauteur d'action** (mesure locale en diamètres de corde, tolérante à l'angle) reste exploitable sur une part significative des annonces ; l'**angle du manche par visée** et le **bombement via angle chevalet/table** restent de vraies vues de profil et ne seront mesurables que sur une minorité d'annonces bien photographiées — traités comme signaux bonus, pas comme piliers du score. Le protocole de collecte (vues 1-5 ci-dessus) reste néanmoins complet pour le Dataset B, où c'est l'utilisateur qui contrôle la prise de vue.

## 6. Points ouverts / non tranchés

- Modalités précises du contact luthier/école de lutherie (message à rédiger).
- Volume cible du Dataset B avant de juger le jalon go/no-go (§4 étape 6) concluant.
- Seuil de résidu géométrique acceptable pour valider un keypoint auto-labellisé (§3bis point 3) — à calibrer empiriquement.
- ~~Reformulation éventuelle du score de sortie (continu vs seuils)~~ **Tranché (§3quater) : classification grossière (basse/normale/haute/non mesurable)**, la résolution réelle des photos ne permettant pas une estimation continue en mm fiable.
- ~~Résultat de l'Étape 0~~ **Mesuré et documenté (§3quater, 2026-08-19)**.
- Classificateur modèle → type de jonction (bolt-on/set-neck), nécessaire pour élargir le diagnostic "neck reset" au périmètre électrique (§3ter) — pas encore conçu ni implémenté.
- Seuils précis de la classification grossière basse/normale/haute (en pixels ou en ratio corde/frette) — à calibrer sur le Dataset B une fois collecté (§4 étapes 2-3), la résolution disponible étant désormais connue (§3quater).
- Élargissement du filtre de collecte (`export_neck_reset_sample.py`, actuellement acoustique/classique) aux guitares électriques — décidé en principe (§3ter), pas encore codé.
