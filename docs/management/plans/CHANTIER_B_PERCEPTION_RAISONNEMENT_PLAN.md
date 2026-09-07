# Plan d'implémentation — Chantier B : séparer perception et raisonnement (2026-09-07)

**Statut :** ⚠️ **non prêt pour l'implémentation** (verdict Claude Opus, consultation du 2026-09-07,
voir §8) — décision d'architecture centrale non tranchée (§8.1) et absence de preuve que le
problème que ce chantier résout existe réellement en production (§8.6). Rien à coder tant que ces
deux points n'ont pas été arbitrés avec l'utilisateur. Formalise et étend
`docs/management/plans/COST_OPTIMIZATION_CHANTIERS.md` (Chantier B) suite à la demande explicite
de l'utilisateur du 2026-09-07.

**Rappel de portée (déjà acté au document de synthèse)** : ce chantier n'est **pas** motivé par
l'économie — Opus a chiffré le gain net à ≈0, voire négatif selon la variante. Il est motivé par
des raisons produit : cohérence de la description entre Tiers et avec le chat, réutilisation pour
`NECK_RESET_VISION_PLAN.md`, et — nouveau, discuté le 2026-09-07 — fiabiliser le Tier 3 comme
source d'analyse "complète, factuelle et vérifiable" (identification marque/authenticité/année)
en le déchargeant d'un travail de perception brute déjà fait en amont.

---

## 1. Principe d'architecture

Séparer deux rôles aujourd'hui confondus dans chaque appel Gemini de la cascade :

- **Perception** (fait une seule fois) : décrire ce qui est visible sur les photos — formes,
  couleurs, texte lu (OCR), état/usure, matériel visible, et (nouveau, voir §3) localisation des
  parties de l'instrument.
- **Raisonnement** (fait par le Tier 3, qui reste responsable de la conclusion) : à partir de
  cette description texte (jamais des photos brutes), répondre aux questions qui comptent pour
  l'utilisateur — "Gibson ou copie ?", "quelle année ?", valeur, état structurel.

## 2. Garde-fou — scope volontairement limité au logo pour l'instant

**Décision explicite de l'utilisateur (2026-09-07)** : la généralisation de ce garde-fou à toute
la couche de perception (au-delà du logo — bois, matériel, année...) a été envisagée puis
**reportée** : elle mérite une discussion détaillée à part, pas une extension actée en une ligne
dans ce plan. Pour cette itération, le garde-fou reste **exactement** celui déjà en place pour le
candidat `hybrid` du benchmark : le modèle de perception transcrit le texte d'un logo/étiquette
sans l'interpréter (ne conclut jamais une marque à partir d'un logo qu'il ne fait que lire),
conformément à la leçon tirée de l'incident Qwen/Guerrilla Guitars.

**Point ouvert, noté au `TODO.md`** : étendre ce garde-fou (bois, matériel, année, authenticité...)
est probablement nécessaire à terme pour la même raison de fond, mais à trancher dans une
discussion dédiée avant d'écrire quoi que ce soit — ne pas anticiper la portée exacte ici.

## 3. Localisation des parties — mesurée sur les candidats eux-mêmes, pas sur un pipeline externe

**Décision explicite de l'utilisateur (2026-09-07)** : ne **pas** réutiliser le pipeline OWLv2/
Dell de `NECK_RESET_VISION_PLAN.md` pour produire une vérité terrain de rectangles. Objectif
différent de celui de ce plan-là : ici, on veut voir **ce que les modèles candidats eux-mêmes
(Gemini, Qwen, Claude, GPT...) obtiennent** quand on leur demande d'identifier et de localiser les
parties visibles d'une guitare sur une photo — une mesure exploratoire de leur capacité brute,
pas une évaluation contre une référence externe précalculée. OWLv2 reste un outil propre à
`NECK_RESET_VISION_PLAN.md` (détection de présence/géométrie fine), sans lien avec ce chantier.

**Mécanisme retenu** : le harnais de benchmark (`backend/benchmark/`) demande à chaque candidat,
en plus de sa réponse habituelle, une liste des parties qu'il identifie sur la photo avec leur
localisation (ex. boîte englobante en coordonnées normalisées, ou a minima une description de
zone — la précision exacte du format dépend de ce que chaque candidat sait produire, à observer
plutôt qu'à présupposer). Les résultats bruts de chaque candidat sont ensuite visualisés
(rectangles superposés sur la photo) dans l'Artifact de validation, pour une **inspection directe
par l'utilisateur** — à ce stade, pas de notation automatique de cet axe, l'objectif est de voir
les écarts de capacité avant de décider s'il vaut la peine de le noter formellement.

## 4. Candidats pour le rôle de perception

Par ordre de simplicité/coût, à trancher par le benchmark (§5), pas par intuition :

1. **Réutiliser le Tier 1 actuel** (`gemini-3.5-flash-lite`) — voit déjà 100% des photos à coût
   marginal, zéro nouveau fournisseur. Risque connu : les tests `NECK_RESET_VISION_PLAN.md`
   n'étaient pas concluants sur sa fiabilité à distinguer des vues fines — à re-tester
   spécifiquement sur des indices d'authentification (pas seulement "quelle vue"), le signal
   existant ne permet pas de conclure ici par extrapolation.
2. **Qwen3.8-Flash** (0,14$/0,42$ par M tokens, vérifié 2026-09-07) — déjà intégré via
   TokenRouter dans le harnais de benchmark (candidat `hybrid`), le moins cher des candidats
   vision sérieux identifiés à ce jour.
3. **GPT** — pas de tarif/capacité vision vérifiés à ce jour pour un équivalent "mini" chez
   GPT-5.6 ; à vérifier avant de l'inclure sérieusement plutôt que deviner.

## 5. Validation avant tout changement de production

Aucun changement à `backend/analyzer.py` tant que :
- le dataset de benchmark reconstruit (30-50 annonces, vérité terrain confirmée par
  l'utilisateur — voir `sample_benchmark_dataset.py`) montre qu'un modèle de perception candidat
  atteint une qualité de description suffisante pour que le Tier 3, ne recevant que ce texte,
  conserve son niveau d'identification actuel (pas de régression sur l'axe identification du
  juge par rapport à la cascade actuelle où T3 voit les photos directement) ;
- le garde-fou (§2) est vérifié tenir en pratique (le juge doit sanctionner sévèrement toute
  fuite d'interprétation dans la sortie du modèle de perception, pas seulement dans celle du
  modèle de raisonnement).

## 6. Risques

- **Signal de prudence déjà documenté** (`NECK_RESET_VISION_PLAN.md`) : aucun modèle bon marché
  n'a encore été validé fiable sur de la reconnaissance visuelle fine appliquée à ce projet — ne
  pas déployer avant mesure.
- **Gain net ≈ 0 côté coût** (Opus, voir `COST_OPTIMIZATION_CHANTIERS.md` Chantier B) — ce plan
  ne doit jamais être présenté comme une économie à l'utilisateur ou en documentation, seulement
  comme un gain de cohérence/fiabilité produit.
- **Absence de vérité terrain pour l'axe localisation (§3)** : puisqu'aucune référence externe
  n'est calculée (décision explicite de ne pas utiliser OWLv2 ici), cet axe reste à l'inspection
  humaine tant qu'aucune notation formelle n'est décidée — ne pas confondre "on observe ce que les
  modèles produisent" avec "on a mesuré leur exactitude", ce sont deux étapes différentes.

## 7. Étapes concrètes (code)

1. `backend/scripts/sample_benchmark_dataset.py` — échantillonnage + manifeste (voir aussi
   `COST_OPTIMIZATION_CHANTIERS.md` Chantier F).
2. Extension du harnais de benchmark (`backend/benchmark/`) : chaque candidat produit, en plus de
   sa réponse habituelle, sa propre liste de parties identifiées + localisation.
3. Artifact de validation (photos + champs pré-remplis pour la vérité terrain d'identification +
   visualisation superposée des rectangles produits par chaque candidat, pour inspection directe).
4. `judge.py` — score par axe (identification/état/valeur/hallucination) ; l'axe localisation de
   parties reste hors notation automatique à ce stade (§3, §6).
5. **Seulement après (1)-(4) et un résultat favorable** : implémentation du candidat de
   perception retenu dans `backend/analyzer.py`, comme changement séparé et validé à part.

---

## 8. Consultation Claude Opus (rendue le 2026-09-07) — verdict : plan non prêt

Consultation menée en aveugle sur le code réel (même protocole que pour
`COST_OPTIMIZATION_CHANTIERS.md`), avec instruction explicite de respecter les deux décisions
utilisateur (garde-fou scopé logo, localisation mesurée sur les candidats sans OWLv2) sans les
remettre en cause. Verdict global : la gouvernance du plan (motivation, ordre benchmark→code,
refus de vendre comme économie) est saine, mais **une décision d'architecture centrale n'est pas
tranchée et rend le reste du document incohérent**, et §5 hérite silencieusement de défauts du
harnais déjà identifiés lors de la correction Chantier F. Points bloquants, par ordre :

**8.1 — Où s'insère la perception ? Non tranché, et §1 est auto-contradictoire selon la réponse.**
Les Tiers 1, 2 et 3 reçoivent aujourd'hui tous la même liste d'images construite une fois
(`analyzer.py:298-299`, passée telle quelle à `analyzer.py:326/359/417`). Si T1/T2 gardent les
photos, la perception n'est pas "faite une seule fois" (§1) — seul l'étage à 5% du volume (T3) en
bénéficie. Si T1/T2 ne les gardent plus, ça modifie le comportement du Portier — un filtre de
rejet sur 100% du volume dont le prompt actuel exige explicitement l'examen visuel du logo/plaque
comme preuve prioritaire (`prompts.json:331`) — sans qu'aucune ligne du plan n'aborde ce risque.
**Décision à prendre avec l'utilisateur avant tout code.** S'y ajoutent deux chemins non couverts
par le plan : `force_expert=True` saute purement T1 (`analyzer.py:318,346-347`) — si la perception
est produite par T1, T3 ne reçoit alors ni photos ni description dans le cas d'usage "ré-analyse
manuelle exigeante" ; et `analyze_deal_light()` attaque T2 directement avec les images sans passer
par T1 (`analyzer.py:214-215,226`). Et si l'insertion se fait après T1, il faut noter que T1 jette
déjà tout sauf 3 champs sur rejet (`analyzer.py:344-345`) — la perception y serait payée puis
jetée sur 70% des annonces, le mécanisme même du calcul "net ≈ 0" déjà établi.

**8.2 — Le garde-fou "exactement celui du candidat `hybrid`" fuit déjà, indépendamment de toute
généralisation.** Le prompt d'extraction `hybrid` (`candidates.py:203-204,209-211`) demande la
"qualité apparente de fabrication" et des "caractéristiques qui pourraient indiquer une origine"
— ce sont des consignes d'inférence/jugement, pas de transcription, du même type que l'incident
"marque budget OEM" qui a motivé le garde-fou. Ce n'est **pas** la généralisation reportée au
TODO (bois/matériel/année, hors périmètre logo) : c'est une incohérence interne au périmètre déjà
acté, à corriger dans le prompt réutilisé lui-même avant de s'en servir comme perception.

**8.3 — Le contrat de sortie de perception doit être dérivé du contrat JSON de prod, pas copié du
prompt de benchmark.** Le contrat T3 de production exige des champs purement perceptuels que le
prompt `hybrid` ne couvre pas : `color` (`prompts.json:302`, obligatoire dès qu'une photo montre
l'instrument), `finish_application`/`finish_texture` (énumérations fermées, `prompts.json:303-304`),
`visual_inspection` (`prompts.json:297`). Un T3 aveugle ne peut pas les remplir sans que la
perception les fournisse explicitement — travail non trivial, absent de §7. **Ajout nécessaire,
indépendant du garde-fou** : un champ de couverture explicite ("zone non observable/logo illisible/
tête hors cadre") pour que T3 distingue "non mentionné" de "non visible" plutôt que de halluciner
pour combler le vide.

**8.4 — §5 n'est pas mesurable avec le harnais tel quel — trois défauts hérités, pas résolus** :
(a) le juge ne reçoit que la réponse finale du candidat (`judge.py:49`), or le rapport de
perception `hybrid` est une variable locale jetée après usage (`candidates.py:229`) — impossible
de vérifier le garde-fou sur la perception sans changer le contrat de retour des candidats ; (b)
le candidat `gemini_pro` n'est **pas** la cascade de prod (appel unique texte libre, sans
`system_instruction`/taxonomie/few-shot, `candidates.py:53-64,72-76`) — "pas de régression vs la
cascade actuelle" (§5) suppose un candidat qui appelle réellement `DealAnalyzer`, absent de §7 ;
(c) la règle 3 du juge ("omission = score 0", `judge.py:39`) doit être réécrite, pas seulement
complétée — un pipeline médiat par la perception omettra mécaniquement des détails de formulation
et se ferait noter 0 partout à tort. S'ajoute une circularité résiduelle : "vérité terrain
**confirmée**" avec champs "**pré-remplis**" (§7.3) reste de l'ancrage sur la sortie Gemini de
prod sauf si la source du pré-remplissage est affichée/masquable et les cas modifiés-vs-confirmés-
tels-quels tracés séparément dans l'analyse. Enfin, "conserve son niveau actuel" n'a ni seuil ni
marge de non-infériorité ni nombre de runs fixés à l'avance — nécessaire avant de lancer quoi que
ce soit, sinon tout écart de quelques items sur n=40 sera un débat sans fin.

**8.5 — Localisation (§3) : le contenu doit rester libre (décision utilisateur, intacte), mais le
format ne peut pas l'être sans rendre le résultat illisible.** Les fournisseurs ont des
conventions de coordonnées différentes (Gemini : `[ymin,xmin,ymax,xmax]`/1000 ; pas de convention
native chez Claude/GPT) — sans contrat imposé, un rectangle mal placé à l'écran est indiscernable
d'une erreur de perception. Rien n'attribue non plus une boîte à une image précise (items à 2-10
photos, `dataset.json:48-59`). Et tous les candidats retournent un `str` unique
(`candidates.py:53-64,136-162,165-180`) — mélanger réponse notée et boîtes dans le même appel
contaminerait la mesure §5 par la règle du juge. **Correctif compatible à 100% avec la décision
utilisateur** : run séparé pour cet axe (pas dans l'appel noté), contrat de sortie strict mais
neutre sur le contenu (`{"parts":[{"image_index":0,"label":"<libre>","box":[x0,y0,x1,y1]}]}`,
coordonnées normalisées 0-1, origine coin haut-gauche), et mesurer le taux de conformité au format
par candidat comme donnée en soi. Obstacle pratique supplémentaire pour l'Artifact (§7.3) : la CSP
d'un Artifact publié bloque `storage.googleapis.com` pour les images (CDN non autorisé) — il faut
embarquer en `data:` URI, et au gabarit réel du projet (~90 Ko/photo, ×1,33 en base64, ~3,5
photos/annonce) 40 annonces dépasseraient le plafond de 16 Mo de l'Artifact ; prévoir un
redimensionnement (512px, q≈0,6) et/ou une pagination. `export_neck_reset_sample.py` couvre déjà
un besoin très proche (page HTML de revue humaine sur échantillon Firestore) — à réutiliser/
dériver plutôt que réinventer, de même pour `sample_benchmark_dataset.py` qui n'existe pas encore
malgré une référence prématurée en §5.

**8.6 — Angle mort le plus important : aucune preuve dans le dépôt que ce chantier résout un
problème réel.** T3 est le meilleur modèle vision du pipeline (`gemini-3.1-pro-preview`) ; tous
les candidats de perception (§4) sont des modèles plus faibles — le chantier remplace la
perception du modèle le plus fort par le résumé texte d'un modèle plus faible. Le seul incident
documenté (Qwen/Guerrilla) est une hallucination d'**interprétation** de Qwen, pas un échec de
perception de Gemini T3. Le seul signal externe disponible va dans l'autre sens (MMMU-Pro : Gemini
3.1 Pro devant Sonnet 5). **Avant tout code : rassembler 3-5 échecs T3 réels de production
imputables à la perception** (gisements déjà identifiés dans le projet : `initialVerdict`/
`initialModelUsed` snapshotté, `requalificationProposalState === 'applied'`) — si aucun ne se
confirme, ce chantier n'a pas de problème à résoudre et sa priorité doit être revue à la baisse.

**8.7 — Motivation "cohérence avec le chat" non tenue par le plan tel qu'écrit.** Le chat envoie
déjà les photos lui-même (`geminiChatService.js:202-214`) et son contexte texte n'injecte ni
`analysis` ni `visual_inspection` (`geminiChatService.js:36-62`) — le chat ne consomme aucune
perception aujourd'hui, et §7 ne prévoit pas de l'y brancher. À ajouter explicitement au plan
(injection dans `buildDealContextText`) ou à retirer des motivations affichées.

**8.8 — Correction de chiffrage (§6)** : le "net ≈ 0" cité ne couvre que la variante interne à
Gemini (T1 produit la description) et T2→T3 — pas la variante externe (Qwen/TokenRouter, §4
candidat 2), où plus aucun tier Gemini ne paie les photos. Ordre de grandeur recalculé sur la
période de référence (1377 annonces) : coût image actuel cascade ≈ 2,51$ (1,30$ T1 + 0,81$ T2 +
0,40$ T3) vs variante Qwen-perception ≈ 1,1-2,0$ selon la longueur de description — gain plausible
de 0,5-1,4$ sur 9,43$, modeste mais de **signe opposé** à ce que §6 affirmait pour cette variante
précise. La conclusion pratique ("ne jamais présenter comme une économie") reste valide, mais doit
s'appuyer sur ce chiffrage-ci pour la variante externe, pas sur celui du Chantier B générique.

**Verdict** : non prêt pour l'implémentation. Points 8.1, 8.3 et 8.6 sont des décisions à prendre
avec l'utilisateur avant toute chose ; 8.2, 8.4, 8.5, 8.8 sont des corrections de rédaction/
périmètre à intégrer une fois les décisions prises. Ordre de blocage recommandé : 8.6 (établir que
le problème existe) → 8.1 (où insérer) → 8.3 (contrat de perception) → reste.
