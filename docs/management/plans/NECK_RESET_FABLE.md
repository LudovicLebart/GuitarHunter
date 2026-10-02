
# Détection de risque de neck reset sur photos d'annonces

**Document de travail — v5**
Objectif : produire une **probabilité calibrée** de besoin de neck reset lors de l'analyse automatique d'annonces, à partir de 1–2 photos (face + dos typiquement) — avec le red flag comme cas d'usage minimal et l'intervalle de confiance comme forme honnête de la sortie (§10). Double objectif : l'outil lui-même, et une pièce du portfolio Guitar Hunter de création d'outils IA spécialisés (§11).

---

## 1. Contraintes et physique du problème

### 1.1 Le signal primaire est hors-plan

Le diagnostic canonique du neck reset repose sur des grandeurs perpendiculaires au plan d'une photo de face :

- Règle posée sur les frettes → doit atteindre le sommet du chevalet (acoustique) ;
- Action à la 12e frette combinée à la marge de réglage restante.

Ces grandeurs s'écrasent en projection frontale, indépendamment de la résolution. **Conséquence structurante : de face, il n'existe aucun signal direct de l'angle du manche.** Tout ce qui suit est donc une accumulation de signaux indirects (proxies), aucun n'étant suffisant seul.

### 1.2 Distribution des données de production

- Corpus scrapé : ~3500 annonces, taxonomie marque/modèle/année déjà extraite par le pipeline.
- Photos par annonce : typiquement 1 à 2, cadrage face et dos. Pas de profil exploitable, pas de contrôle de la prise de vue.
- Qualité : photos amateur, compression JPEG, flou, éclairage non contrôlé. Toute mesure fine en pixels doit être évaluée contre ce plancher de bruit.

### 1.3 Le faux positif structurel à assumer

Un saddle très bas (ou tout autre signe de compensation) admet deux causes indistinguables de face :

- **(a)** Angle de manche dégradé, compensation épuisée → le prochain geste d'entretien significatif est un reset. C'est la cible du red flag.
- **(b)** Manche sain, saddle abaissé volontairement pour une action basse (choix de setup). Faux positif.

Le système ne peut pas trancher (a)/(b) sur une photo frontale seule. Deux mitigations : le score composite (un cas (b) n'accumule normalement pas les autres signaux) et la sémantique du flag — annoncer un **risque**, pas un diagnostic.

---

## 2. Architecture générale : score de risque composite

Aucun verdict binaire issu d'un signal unique. À la place :

```
score = Σ (poids_i × signal_i) + prior_taxonomique
flag si score > seuil
```

Propriétés recherchées :

- **Interprétable** : chaque composant est nommable et vérifiable par un luthier ; le flag peut être accompagné de ses causes (« saddle rasé + bulge visible + modèle à risque »).
- **Annotable grossièrement** : chaque signal est une étiquette simple (présent / absent / incertain) sur le corpus existant.
- **Dégradable** : si un signal est indétectable sur une photo donnée (occlusion, cadrage), il contribue zéro sans casser le pipeline.
- **Calibrable** : les poids et le seuil se règlent sur le dataset de calibration (voir §8), pas à la main.

Le routage par famille (§3) précède le calcul : les signaux applicables et leurs poids dépendent du type de jonction de manche.

---

## 3. Routage par famille de guitare

La ligne de partage n'est pas acoustique/électrique mais **type de jonction manche-caisse**. La taxonomie marque/modèle déjà extraite permet de router avant toute analyse visuelle.

| Famille | Exemples | Neck reset applicable ? | Signal frontal principal |
|---|---|---|---|
| Acoustique manche collé | Martin, Gibson acoustiques, la plupart des classiques | Oui | Hauteur de saddle exposée |
| Électrique set-neck | Les Paul, SG, PRS set-neck, semi-hollow (ES-335 et proches) | Oui (reset structurel comparable à l'acoustique) | Hauteur du Tune-o-matic au-dessus de la table (thumbwheels à zéro = compensation épuisée) |
| Bolt-on | Fender-style, majorité des électriques | Non (se règle par shim) | Exclu du verdict neck reset |

Point clé : **le signal lui-même branche par famille, pas seulement le verdict.** Sur une set-neck il n'y a pas de saddle rasé ; l'équivalent est un TOM vissé au ras de la table, éventuellement cordes touchant l'arrière du chevalet. Appliquer la métrique acoustique à une set-neck produit du bruit.

Cas limites à traiter dans la table de routage : jonctions atypiques (Taylor NT — reset trivial par cales usinées, donc flag à pondérer très bas), manches traversants (pas de reset possible), archtops à chevalet flottant (hauteur réglable par molettes, la métrique saddle ne s'applique pas).

---

## 4. Localisation du chevalet : les cordes comme localisateur géométrique

Chaînon manquant identifié : produire un prompt fiable (point ou boîte) pour SAM 2.1 sur la région chevalet/saddle, l'open-vocab (OWLv2 testé) ayant échoué.

### 4.1 Principe

Les six cordes sont les features les plus détectables de l'image : lignes quasi parallèles, haute fréquence, fort contraste sur la table. Extraction classique sans entraînement :

1. Détection de segments de lignes (transformée de Hough probabiliste, ou LSD/FLD d'OpenCV, plus robustes sur photos réelles).
2. Filtrage : garder le faisceau de 4–6 lignes quasi parallèles, légèrement convergentes, de longueur dominante dans l'image.
3. Le **point de terminaison du faisceau côté caisse** est le saddle — non seulement la région du chevalet, mais le point de mesure précis.
4. Ce point (ou une boîte construite autour) sert de prompt à SAM 2.1 pour segmenter saddle et chevalet.

### 4.2 Bénéfices secondaires gratuits

- L'**espacement E-E au saddle** (étalon d'échelle, §5) tombe du même calcul : distance entre les deux lignes extrêmes à leur terminaison.
- L'**axe de la guitare** (direction du faisceau) permet de normaliser l'orientation avant toute mesure.
- Le point de terminaison côté manche donne le sillet de tête → localisation du manche et de la tête par prolongement, si besoin pour d'autres modules.
- La **droiture apparente du faisceau** est elle-même un signal faible (§6.5).

### 4.3 Modes d'échec attendus

- Cordes absentes ou partielles sur l'annonce (guitare vendue sans cordes) → fallback détecteur entraîné (§4.4) ou contribution nulle.
- Fond très texturé produisant des lignes parasites → le filtre « faisceau parallèle convergent » élimine l'essentiel ; valider empiriquement sur le corpus.
- Photos très obliques → la convergence du faisceau augmente ; tolérable tant que les terminaisons restent identifiables.

### 4.4 Fallback : petit détecteur entraîné

Si la voie géométrique s'avère insuffisante en couverture : détecteur léger (boxes suffisent comme prompts SAM) entraîné sur 300–500 annonces annotées **tirées du corpus scrapé lui-même** — avantage rare d'entraîner exactement sur la distribution de production. Une classe « chevalet » s'annote en 2–3 s/image. Attention licence : préférer RT-DETR ou RF-DETR (Apache 2.0) à Ultralytics YOLO (AGPL-3.0) si le pipeline a une quelconque vocation à être distribué.

---

## 5. Étalon d'échelle : espacement E-E au saddle

Pour convertir des pixels en grandeur physique, référence locale mesurée au même endroit que la grandeur cible (insensibilité à la perspective locale).

**Choix : espacement entre cordes extrêmes (E-E) au saddle, primaire. Diamètre de corde relégué en contrôle de cohérence.**

Arguments contre le diamètre de corde comme étalon primaire :

- Jauge installée inconnue sur une annonce : entre un tirant light et un medium, ±15–20 % d'erreur systématique, sans savoir quelle corde est mesurée.
- Sur une photo d'annonce, une corde fait 1–3 pixels de large : la mesure est dominée par la PSF, le sharpening et les artefacts JPEG, pas par le diamètre réel.

Arguments pour l'espacement E-E :

- Tout aussi local (même point de mesure), donc même insensibilité à la perspective.
- ~50× plus de pixels → rapport signal/bruit incomparable.
- Variance population étroite (~52–58 mm selon les modèles) ; la taxonomie peut affiner la valeur nominale par modèle quand elle est connue.
- Obtenu gratuitement par le pipeline cordes (§4.2).

---

## 6. Catalogue des signaux

Chaque signal : description, lisibilité de face/dos, mode de détection, fiabilité estimée. Tous contribuent au score, aucun ne décide seul.

### 6.1 Hauteur de saddle exposée (acoustique) — signal principal

- **Quoi** : hauteur de saddle visible au-dessus du chevalet. Saddle rasé au ras = compensation d'angle poussée à la limite.
- **Détection** : segmentation SAM du saddle et du chevalet à partir du prompt cordes, mesure de hauteur exposée normalisée par l'espacement E-E.
- **Alternative recommandée à la mesure : classification directe du crop** (rasé / normal / haut, 3 classes). Puisque la sortie visée est un flag et non des millimètres, un petit classifieur sur le crop saddle est probablement plus robuste que la chaîne métrique complète sur photos bruitées, et s'entraîne sur annotations grossières du corpus. Trancher métrique vs classification via l'expérience de calibration (§8).
- **Piège** : cas (b) du §1.3 — setup volontaire. Pondérer, ne jamais décider seul.

### 6.2 Hauteur du Tune-o-matic (set-neck) — équivalent du 6.1

- **Quoi** : TOM vissé au ras de la table, thumbwheels à zéro, éventuellement cordes frottant l'arrière du chevalet ou le tailpiece anormalement bas.
- **Détection** : même pipeline (cordes → crop chevalet), classifieur dédié à la famille.
- **Piège** : le tailpiece bas est aussi un choix de setup (« top wrap » chez certains joueurs) ; se concentrer sur le TOM lui-même.

### 6.3 Belly bulge (bombement de table derrière le chevalet)

- **Quoi** : déformation de la table sous tension, corrélée au vieillissement structurel qui accompagne souvent un besoin de reset.
- **Lisibilité de face** : indirecte mais réelle — distorsion des reflets sur le vernis autour du chevalet, courbure anormale de la ligne d'ombre des cordes, déformation apparente du pickguard.
- **Détection** : signal difficile à métrifier ; candidat naturel pour classification de crop (zone table autour du chevalet) avec annotations grossières. Fiabilité dépendante de l'éclairage — accepter un fort taux de « non évaluable ». **Attention à la cible d'apprentissage** : une table saine est voûtée par construction — le positif n'est pas « table non plate » mais la signature localisée bosse-derrière/creux-devant le chevalet (voir fiche §8.3).

### 6.4 Chevalet raboté, recollé ou remplacé

- **Quoi** : traces d'une compensation antérieure agressive ou d'une réparation — chevalet anormalement fin, arête modifiée, traces de colle, décoloration du contour (ancien chevalet plus grand), fentes au chevalet.
- **Détection** : classification du crop chevalet (même crop que 6.1). Un chevalet visiblement retravaillé indique que la marge de compensation a déjà été consommée par le passé.

### 6.5 Droiture du faisceau de cordes (signal faible, gratuit)

- **Quoi** : sur une face bien cadrée, une cassure ou courbure anormale de la ligne des cordes au niveau de la jonction manche-caisse peut trahir un manche qui « plonge ».
- **Détection** : sous-produit direct du pipeline §4 (résidu de la régression linéaire par corde).
- **Statut** : très sensible à la perspective et à la distorsion d'objectif ; poids faible, à valider ou éliminer en calibration.

### 6.6 Photos de dos — le talon (atout sous-exploité)

Les annonces contiennent quasi systématiquement une vue de dos où le talon est visible. Signaux :

- **Fissures ou craquelures de vernis autour du talon** : contrainte au joint, jeu naissant.
- **Ligne de joint visible / jeu au talon** : décollement en cours.
- **Trou de vapeur rebouché** (typiquement vers la 14e–15e frette, côté touche, visible parfois de dos au talon) ou traces de retouche de vernis au talon : **reset déjà effectué**. Information précieuse dans les deux sens — un reset ancien bien fait remet le compteur à zéro ; un reset récent sur une annonce peut aussi signaler un historique structurel chargé.
- **Détection** : localisation du talon par géométrie (prolongement de l'axe manche depuis la vue de dos, ou détecteur léger), puis classification de crop.

### 6.7 Prior taxonomique (marque × modèle × âge)

- **Quoi** : la probabilité a priori de besoin de reset varie énormément selon le modèle et l'époque. Une Gibson ou Martin des années 50–70 a une probabilité structurellement élevée ; certains modèles sont notoires. Une guitare de 2015 avec saddle bas signale plutôt un setup raté qu'un reset.
- **Détection** : aucune — la taxonomie est déjà extraite. Encodage : table (famille, décennie) → prior, initialisée à dire d'expert/littérature luthier, raffinée avec les données.
- **Statut** : ce prior vaut potentiellement plus que n'importe quel signal pixel. Il doit néanmoins rester un *prior* — jamais suffisant seul pour flaguer (sinon le système flague toutes les Martin vintage).

### 6.8 Exploitation de la parallaxe résiduelle : hauteur cordes-table par pose 3D

**Constat** : les photos d'annonces ne sont presque jamais parfaitement frontales. Une vue oblique d'angle θ projette la composante hors-plan avec un facteur ~sin(θ) — la parallaxe résiduelle **réintroduit partiellement la dimension perdue** (§1.1). Les photos réelles ne sont pas des faces dégradées mais des vues partiellement informatives.

**Chaîne de mesure — la rosace comme mire de calibration :**

1. La rosace est un **cercle de diamètre connu** (~100 mm sur dreadnought, valeur affinable par modèle via la taxonomie). Son image est une ellipse.
2. La pose d'un cercle de rayon connu à partir de son ellipse projetée est un problème classique résolu (*pose-from-ellipse*) : on obtient la **normale du plan de la table, l'échelle métrique et la distance**, sans EXIF (les plateformes strippent les métadonnées de toute façon) et sans calibration caméra préalable.
3. Contraintes de cohérence pour lever l'ambiguïté à deux solutions de l'ellipse et vérifier la pose : contour du corps (symétrie), progression géométrique des frettes (règle du 17,817) le long de l'axe manche.
4. Localisation de la rosace sans open-vocab : le pipeline cordes (§4) donne l'axe de la guitare ; la rosace est cherchée géométriquement sur cet axe (fit d'ellipse/Hough sur le contour interne, robuste car fort contraste du trou).

**Grandeur cible : hauteur des cordes au-dessus de la table juste devant le chevalet** — le proxy luthier standard (~11–13 mm sain sur dreadnought ; nettement moins = angle dégradé). Avantage décisif sur l'exposition du saddle : ce signal **résiste partiellement au faux positif §1.3.b** — saddle bas + hauteur cordes-table correcte (setup volontaire) se distingue de saddle bas + cordes frôlant la table (compensation épuisée).

**Limites et conséquences architecturales :**

- **Dégénérescence près de la face parfaite** : quand l'ellipse tend vers un cercle, l'erreur de pose explose. Conséquence architecturale : **fusion pondérée par incertitude, pas routage exclusif**. La classification de crop (§7) est toujours exécutée (robuste, sans condition de validité) ; la chaîne géométrique est toujours tentée, mais sa contribution au score est pondérée par ~1/σ² de la pose estimée (l'incertitude du pose-from-ellipse est estimable analytiquement et croît de façon prévisible quand l'obliquité θ→0). Près de la face parfaite son poids tend naturellement vers zéro — le routage n'est que le cas dégénéré de la fusion. **Réserve** : les deux chaînes observent la même région et partiellement le même phénomène — non indépendantes, leur somme naïve double-compte le signal. Acceptable pour un red flag (biais vers la sensibilité) ; pour un score calibré en probabilité, estimation conjointe requise (la régression logistique du score composite le fait implicitement si les deux features y entrent ensemble).
- **Électriques sans rosace** : mire alternative par famille (dimensions de chevalet/micros connues par modèle) ou chaîne acoustique-seulement — acceptable, l'acoustique étant le cœur du périmètre reset.
- Précision du fit d'ellipse sur photos compressées, occlusion partielle de la rosace par les cordes/pickguard : à quantifier sur datasetB (marqueur de pose vérité-terrain, §8.1).

---

## 7. Choix méthodologique : classification de crop vs régression métrique

Deux chaînes possibles une fois la région localisée :

1. **Métrique** : segmentation fine → hauteur en pixels → normalisation E-E → mm → seuil.
2. **Classification** : crop → classifieur N classes (ex. rasé / normal / haut).

La chaîne métrique est séduisante mais fragile sur photos d'annonces : chaque étage (segmentation, bord du saddle, étalon) ajoute du bruit, et l'écart entre « sain » et « limite » est de l'ordre de 2–3 mm. **Position par défaut : classification pour la production, métrique réservée au dataset de calibration contrôlé.** La calibration (§8) tranche : si le plancher de bruit de la chaîne métrique complète sur photos réalistes dépasse l'écart utile, la classification est le repli honnête.

---

## 8. Datasets et expérience de calibration

### 8.0 Règle de partage des rôles (principe verrouillé)

- **DatasetA — annonces scrapées (~3500)** : fournit la distribution de production, les images d'entraînement pour la localisation et les classifieurs de crops, et les données pour raffiner les priors taxonomiques. **Il ne contient aucune vérité terrain sur l'angle de manche : il ne peut jamais, à lui seul, valider la détection de neck reset.** Toute validation du lien signal↔angle passe par le datasetB.
- **DatasetB — banc d'essai à angle contrôlé** : guitares personnelles à manche vissé, photographiées avec angle de manche *imposé* par cales d'épaisseur connue. Fournit la vérité terrain angulaire et la courbe dose-réponse « angle réel → observables frontaux ».

### 8.1 DatasetB : protocole

Le manche vissé est ici un atout méthodologique : l'angle est une **variable contrôlée** (cales d'épaisseur connue), pas seulement observée. On obtient une relation causale angle→features, impossible à établir sur des set-necks.

**Plan factoriel par mesure :**

- Plusieurs guitares (leave-one-guitare-out pour toute validation) ;
- Plusieurs angles de manche par guitare (incréments de cale connus, couvrant du sain au dégradé) ;
- Par configuration : plusieurs angles de prise de vue, distances, conditions d'éclairage — **en balayant explicitement l'obliquité** (de la face quasi parfaite à l'oblique marqué) pour cartographier l'erreur de la chaîne pose 3D (§6.8) en fonction de θ ;
- **Marqueur de pose vérité-terrain** (ArUco ou damier) collé temporairement sur la table : donne la pose caméra↔table exacte, permet de quantifier l'erreur de la chaîne pose-from-ellipse et de fixer le seuil d'obliquité utilisable (les bolt-on n'ayant pas de rosace, le marqueur valide la géométrie ; la chaîne rosace elle-même sera validée sur les acoustiques accessibles) ;
- Recompression JPEG et redimensionnement aux niveaux observés dans le datasetA (reproduire la distribution de production, pas des photos studio) ;
- Mesures de référence à chaque configuration : angle imposé (cale), action à la 12e frette, hauteur de cordes au chevalet.

**Deux sweeps distincts (essentiel) :**

- **Sweep A — dégradation brute** : varier l'angle à réglage de chevalet fixe. Simule un angle qui se dégrade sans intervention.
- **Sweep B — dégradation compensée** : varier l'angle en recompensant l'action au chevalet à chaque pas. Simule la guitare « bien réglée pour son état » — le cas des faux positifs (§1.3.b).

Interprétation : un observable frontal qui répond au sweep **B** détecte l'angle malgré la compensation → **signal or**. Un observable qui ne répond qu'au sweep A mesure en réalité l'action, pas l'angle → utile mais de second rang, et piégeux sur guitares compensées.

**Pré-enregistrement** : avant les mesures, figer la liste des observables testés, le seuil de corrélation pour qu'un observable soit retenu, et les conclusions associées à chaque issue (y compris l'échec global). Grille de verdicts asymétrique, même discipline que les probes MoneyBot.

### 8.2 Limite de transfert du datasetB

La géométrie bolt-on n'a ni saddle exposé, ni belly bulge, ni chevalet acoustique. Le datasetB valide donc :
- la chaîne géométrique complète (pipeline cordes §4, étalon E-E §5, plancher de bruit métrique §7) ;
- les observables géométriques génériques (ligne/droiture du faisceau §6.5, action apparente, ombres de cordes).

Il ne valide pas les signaux spécifiquement acoustiques (6.1 saddle, 6.3 bulge, 6.4 chevalet retravaillé), dont la corrélation à l'angle reste à établir autrement (mesures ponctuelles sur acoustiques accessibles, verdicts d'expert sur photos du datasetA). Ne pas conclure plus large que ce que le banc mesure.

Spécimen positif confirmé disponible : une acoustique Yamaha (F310/FG d'entrée de gamme) acquise avec diagnostic établi de visu — saddle au minimum, belly bulge massif, injouable. À photographier sous toutes les obliquités et conditions d'éclairage avant toute réparation : c'est la seule vérité-terrain positive acoustique du protocole, et le test rétrospectif de référence pour le score composite (la photo d'annonce originale existe — le système, une fois monté, doit la flagger). Illustre aussi le prior taxonomique : table laminée d'entrée de gamme + âge = mode de défaillance belly connu et fréquent.

### 8.3 Fiche de mesure belly (vérité-terrain acoustique)

À remplir pour chaque acoustique mesurée physiquement (spécimen positif inclus). Objectif : distinguer le dôme de construction (normal — la plupart des tables sont voûtées, radius typique ~25–30 pieds : une règle en travers du grand lobe montre toujours du jour aux extrémités, même sur une guitare saine) du belly pathologique, dont la signature est le couple bosse localisée derrière le chevalet + creux devant le chevalet (rotation du chevalet sous tension).

Mesures par guitare (règle rigide + jauges d'épaisseur, à défaut cartes empilées) :

| # | Mesure | Position de la règle | Cordes tendues | Cordes détendues |
|---|---|---|---|---|
| 1 | Flèche max derrière le chevalet | Sens du grain, par-dessus le chevalet | ___ mm | ___ mm |
| 2 | Creux devant le chevalet (zone rosace↔chevalet) | Sens du grain, par-dessus le chevalet | ___ mm | ___ mm |
| 3 | Jour aux bords (référence dôme) | Travers du grand lobe, hors chevalet | ___ mm | ___ mm |
| 4 | Hauteur saddle exposée | — | ___ mm | — |
| 5 | Hauteur cordes-table devant chevalet | — | ___ mm | — |

Conditions à consigner systématiquement : humidité relative de la pièce (une table sur-humidifiée gonfle et mime un belly — biais saisonnier estival), température, date, jauge de cordes installée, temps depuis le dernier changement de tension.

Interprétation :
- Mesure 3 seule élevée, 1 et 2 modérées et symétriques → dôme de construction probable, pas un signal.
- Couple 1 élevé + 2 creusé → belly pathologique (rotation du chevalet).
- Écart tendu/détendu sur la mesure 1 : une bosse qui persiste détendue signale une déformation plastique/structurelle (bridge plate décollé ou déformé) — plus grave qu'une déformation élastique qui se relaxe.

Si possible, re-mesurer après quelques jours à HR contrôlée (~45–50 %) pour éliminer le faux belly hygrométrique.

Conséquence pour le signal visuel 6.3 : ce que le détecteur de bulge doit apprendre à repérer sur photo n'est pas « la table n'est pas plate » (vrai partout) mais la localisation de la déformation par rapport au chevalet — bosse derrière, creux devant. Les annotations du datasetA doivent encoder cette distinction, sinon le classifieur apprendra le dôme normal comme positif.

### 8.4 Questions tranchées par l'expérience

- Quels observables frontaux répondent réellement à l'angle (sweep B) vs à l'action (sweep A seulement) ? → fixe les poids initiaux du score, élimine les signaux morts.
- Quel est le plancher de bruit de la chaîne métrique complète (cordes → SAM → pixels → mm) ? Est-il < 2–3 mm ? → tranche métrique vs classification (§7).
- Quelle couverture/précision de localisation atteint le pipeline cordes (§4) ? → tranche géométrie vs détecteur entraîné.
- Si la corrélation globale est faible même en conditions contrôlées, le plafond d'information frontale est bas : le flag devra s'assumer sémantiquement comme « risque à vérifier » et non « probable » — c'est une conclusion utile en soi.

## 9. Roadmap suggérée

- Pipeline cordes → prompt SAM sur un échantillon du datasetA (~100 annonces). Métrique : taux de localisation correcte du saddle. (Zéro entraînement, débloque tout le reste.)
- DatasetB (§8.1) en parallèle : pré-enregistrement du protocole, puis acquisition (sweeps A et B) et analyse dose-réponse.
- Module d'estimation d'obliquité et d'incertitude : estimation de θ et de σ_pose par photo (ellipse de rosace + contraintes de cohérence), alimentant la pondération de la fusion (§6.8). Statistique descriptive sur le datasetA : distribution réelle des obliquités → quelle fraction du corpus donne un poids géométrique significatif.
- Crops chevalet/saddle en masse sur le corpus, annotation grossière 3 classes, entraînement du classifieur 6.1/6.2 (routé par famille).
- Signaux dos (talon) : localisation + classifieur, sur les annonces disposant d'une vue de dos.
- Prior taxonomique : table initiale à dire d'expert.
- Score composite → probabilité calibrée : étiquetage expert de 100–200 annonces, régression logistique sur les features, calibration isotonique, prédiction conforme (§10). Seuil du red flag dérivé de la probabilité, réglé pour privilégier la précision (un flag doit rester crédible).
- Itérations : belly bulge, droiture du faisceau, raffinement des priors avec les données accumulées.

## 10. De red flag à probabilité calibrée

Objectif révisé : la sortie visée n'est pas un flag binaire mais une probabilité fiable de besoin de neck reset.

### 10.0 La circularité des labels photo, et sa résolution en deux étages

Problème fondamental : un « verdict expert sur photos » a le même plafond d'information que le système lui-même — sans la guitare en main, personne ne peut confirmer un besoin de reset. Un label photo n'est pas une vérité-terrain sur le reset, c'est une vérité-terrain sur ce qu'un humain attentif conclut des photos. Résolution : découper la cible en deux étages, chacun avec sa vérité-terrain propre et honnête.

- **Étage 1 — le système reproduit le jugement photo expert.** Variable cible redéfinie : « un expert attentif, regardant ces photos, flaggerait-il cette annonce ? ». Pour cette question, les labels photo sont une vérité-terrain exacte, sans circularité — l'annotateur est la référence. Valeur propre : automatiser le triage attentif sur 3500+ annonces, infaisable à la main. C'est cet étage que calibrent les labels photo (échantillon aléatoire + active learning).
- **Étage 2 — mesurer la fiabilité du jugement photo lui-même.** Question : « quand le flag photo se déclenche, quelle fraction est un vrai reset ? » (valeur prédictive positive). Mesurable uniquement guitare en main. Source naturelle : la chasse elle-même — chaque visite d'annonce est un verdict physique gratuit. Protocole pré-enregistré : avant chaque visite, consigner la prédiction du système (et celle de l'annotateur) ; après inspection, le verdict réel. S'accumule sans effort dédié ; ~20–30 visites donnent une première estimation de la VPP, le chiffre dont le calcul d'espérance a besoin.

Biais assumé de l'étage 2 : on visite les annonces intéressantes → la VPP (précision du flag) est bien mesurée, le rappel (resets non flaggés) l'est mal. Compromis correct pour un outil d'achat : un reset raté coûte une visite pour rien, pas un mauvais achat.

Troisième voie — demander au vendeur : pour les candidates sérieuses, message avant déplacement demandant une photo de profil au chevalet, ou le test de la règle sur les frettes photographié. Coût quasi nul, transforme l'annonce en semi-vérité-terrain ; un refus est lui-même un signal. L'outil peut générer automatiquement la demande pour les annonces au-dessus d'un seuil de suspicion.

### 10.1 Division du travail datasetB / labels de production

La marche vers la probabilité n'est pas dans le modèle — elle est dans les labels, désormais structurés par les deux étages ci-dessus.

Division des rôles (à ne pas confondre) :
- Le datasetB établit le modèle de mesure (la vraisemblance) : « la feature X vaut Y quand l'angle réel est Z, avec incertitude σ ». C'est la physique du signal, validée en conditions contrôlées.
- Il ne contient structurellement ni la prévalence (fraction des annonces réelles nécessitant un reset — le taux de base sans lequel aucune probabilité n'existe : le même signal donne P=15 % ou P=60 % selon que le problème touche 5 % ou 30 % du marché), ni la distribution de production (la calibration est par définition spécifique à une distribution ; un modèle calibré sur photos contrôlées de guitares personnelles est décalibré sur photos vendeurs — analogue au problème point-in-time du moteur LLM MoneyBot).

Effet réel du datasetB sur le besoin de labels : il transforme « apprendre toute la correspondance photo→verdict » en « vérifier une chaîne physique validée + estimer la prévalence ». Le seuil diagnostique sur la grandeur mesurée vient du savoir luthier (ex. hauteur cordes-table < ~8 mm suspect), pas des labels. Reste l'échantillon aléatoire (~100 verdicts) pour la prévalence et la vérification de calibration — incompressible, mais un seul lot sert les deux.

En une ligne : datasetB = la physique (vraisemblance) ; labels datasetA = la population (prévalence et vérification de calibration). Les deux sont nécessaires, aucun ne substitue l'autre.

Pourquoi la prévalence est incontournable (et quand elle ne l'est pas) :
Illustration chiffrée (Bayes) — détecteur à 90 % de sensibilité et 90 % de spécificité, signal positif :
- Prévalence 5 % → P(reset | signal) ≈ 32 %
- Prévalence 30 % → P(reset | signal) ≈ 79 %

Même guitare, même photo, même signal : la probabilité varie du simple au double et demi selon la prévalence. Sans elle, le système ne peut produire qu'un score de suspicion relatif (classement des annonces entre elles), jamais un pourcentage.

Conséquence sur le besoin réel — deux modes d'usage distincts :
- **Mode classement** (« quelles annonces inspecter en priorité ») : le score relatif suffit, prévalence inutile. Prendre le top-N.
- **Mode décision absolue** (« P(reset)=70 %, coût reset ~400 $, prix demandé 250 $ → espérance négative, skip sans déplacement ») : exige une vraie probabilité, donc la prévalence. C'est le calcul d'espérance qui justifie l'effort.

Estimation de la prévalence :
- Échantillon aléatoire étiqueté (méthode propre) : ~100 annonces tirées au hasard — jamais les cas suspects — verdict expert sur photos ; proportion observée + intervalle binomial (~±6–8 pts à n=100). Piège : les labels d'active learning (cas incertains) sont biaisés par construction et ne peuvent servir ni ici ni pour la calibration.
- Stratification par taxonomie (la version utile) : la prévalence globale est presque une fiction — elle varie énormément par segment (Gibson 1965 vs Yamaha 2015). Estimer par strate (famille × décennie × gamme). Le prior taxonomique §6.7 est précisément un modèle de prévalence segmentée : les deux concepts fusionnent.
- Initialisation externe : statistiques d'ateliers, littérature luthier, forums — bruité mais gratuit, raffiné ensuite par les données.
- Boucle de rétroaction : chaque guitare réellement inspectée après flag met à jour la strate correspondante.

Chemin réaliste :
- **Étiquetage expert** — trois stratégies d'échantillonnage pour trois usages distincts :
  - **Aléatoire** (~100 annonces tirées au sort) → prévalence et vérification de calibration (un échantillon aléatoire couvre naturellement toute la gamme de scores : un seul lot sert les deux usages). Verdict : reset probable / improbable / indéterminable, vérité-terrain bruitée assumée.
  - **Cas incertains** (là où le système hésite, en boucle continue) → active learning : améliorer le détecteur lui-même. Chaque verdict porte sur un cas informatif par construction. Ne sert ni la prévalence ni la calibration (échantillon biaisé par construction).
  - **Les rares verdicts physiquement confirmés** (guitares achetées/inspectées) servent d'ancrage de qualité pour estimer le bruit du label expert photo.
- **Calibration du score composite** sur ce jeu : régression isotonique ou Platt scaling (le score composite §2 devient l'entrée, la probabilité calibrée la sortie).
- **Prédiction conforme par-dessus** : au lieu d'un point « 73 % », sortir un intervalle « P(reset) ∈ [55 %, 85 %] » avec garantie de couverture statistique. C'est la forme honnête avec peu de labels : la largeur de l'intervalle communique elle-même la quantité d'information disponible (photo quasi frontale → intervalle large ; oblique riche en signaux → intervalle resserré, en cohérence avec la fusion pondérée §6.8).
- La classe « indéterminable » est une sortie légitime du système, pas un échec — l'assumer explicitement dans l'interface.
- **Suivi de calibration** : courbe de fiabilité (reliability diagram) sur jeu de validation tenu à l'écart ; recalibration périodique à mesure que des verdicts confirmés s'accumulent (boucle de rétroaction des questions ouvertes).

## 11. Capacité de réussite par outil (évaluation honnête)

Le projet a un double objectif : l'outil lui-même, et un portfolio de création d'outils IA spécialisés (projet Guitar Hunter). La valeur portfolio est en partie indépendante du plafond diagnostique : un pipeline pré-enregistré qui démontre proprement que l'information frontale plafonne à X % est un livrable aussi défendable qu'un détecteur qui marche. Chaque module ci-dessous est conçu comme une pièce de portfolio autonome avec sa métrique de succès pré-enregistrée.

| Module | Probabilité de succès estimée | Risques principaux | Valeur portfolio |
|---|---|---|---|
| Pipeline cordes → localisation (§4) | Très élevée (~85–90 %) | Nylon (contraste faible), fonds texturés, guitares sans cordes | Géométrie computationnelle appliquée, zéro entraînement |
| Prior taxonomique (§6.7) | Quasi certaine | Qualité des tables expertes initiales | Faible seul, fort en intégration |
| Classifieur crop saddle 3 classes (§6.1) | Élevée | Qualité des crops en amont, ambiguïté d'annotation | Fine-tuning spécialisé — cœur de la démonstration visée |
| Signaux dos / talon (§6.6) | Moyenne | Qualité réelle des photos de dos, occlusions | Détection fine sur données difficiles |
| Chaîne pose-from-ellipse (§6.8) | Moyenne (théorie solide, intégration incertaine sur photos compressées) | Fit d'ellipse sur JPEG, occlusion rosace, dégénérescence frontale | Le module le plus différenciant s'il fonctionne — vision 3D monoscopique sans calibration |
| Belly sur photo (§6.3) | Faible-moyenne — bonus, pas fondation | Dépendance éclairage, fort taux « non évaluable » | Résultat négatif documenté acceptable |
| Probabilité calibrée bout-en-bout (§10) | Bornée par les labels, pas par la technique | Coût d'étiquetage expert, bruit des labels photo | Quantification d'incertitude rigoureuse (conforme) — rare dans les projets vitrine |

Séquence recommandée : construire dans l'ordre de certitude décroissante. Les modules sûrs établissent le socle et la crédibilité ; les modules spéculatifs sont tentés ensuite avec une métrique pré-enregistrée, et leurs échecs éventuels sont documentés comme des résultats mesurés, pas des trous. Le pré-enregistrement (même discipline que MoneyBot) est ce qui transforme chaque issue — succès ou échec — en pièce défendable.

## 12. Questions ouvertes

- Taux réel de présence/qualité des vues de dos dans le corpus (conditionne le poids des signaux §6.6).
- Traitement des classiques (cordes nylon : contraste moindre pour le pipeline Hough ; saddle souvent non compensé — mêmes métriques ?).
- Cas des annonces sans cordes ou avec cordes détendues.
- Faut-il exposer le détail des signaux dans le flag (explicabilité pour l'utilisateur final) ou un score opaque ?
- Boucle de rétroaction : possibilité de vérifier a posteriori certains verdicts (guitares achetées/inspectées) pour raffiner poids et priors.
- Validation des signaux spécifiquement acoustiques (saddle, bulge, chevalet retravaillé), hors périmètre du datasetB (§8.2) : mesures ponctuelles sur acoustiques accessibles ? verdicts d'expert sur photos du datasetA ? les deux ?
- Mode d'usage cible à trancher (§10) : classement relatif (top-N à inspecter — prévalence inutile, moins de labels) ou décision absolue par calcul d'espérance (probabilité + coûts de réparation + prix demandé — exige la prévalence) ? Le choix conditionne l'effort d'étiquetage.

