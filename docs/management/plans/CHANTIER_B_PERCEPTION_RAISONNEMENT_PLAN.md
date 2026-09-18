# Plan d'implémentation — Chantier B : séparer perception et raisonnement (2026-09-07)

**Statut :** ⚠️ en révision — la consultation Opus du 2026-09-07 (§8) a été menée sur une
**motivation mal formulée par erreur** (corrigée en §0, le même jour). **8.1 est désormais tranché**
(option large, T1 compris — voir §1) et **8.3 est acté comme travail à faire** (contrat de
perception complet, dérivé champ par champ du JSON de prod — voir §2 pour le niveau de précision
attendu). Restent à faire avant tout code : écrire ce contrat complet (8.3), couvrir les deux
chemins qui sautent T1 (conséquence de 8.1, voir §1), et les corrections de rédaction/périmètre
8.2/8.4/8.5/8.7/8.8. Formalise et étend `docs/management/plans/COST_OPTIMIZATION_CHANTIERS.md`
(Chantier B) suite à la demande explicite de l'utilisateur du 2026-09-07.

## 0. Correction de cadrage (2026-09-07, avant toute suite technique)

**Erreur de brief corrigée par l'utilisateur** : la première version de ce plan présentait le
Chantier B comme motivé par une "fiabilisation du Tier 3" — ce qui a orienté à tort la
consultation Opus (§8) vers la question "Gemini T3 a-t-il un vrai problème de perception ?".
**Ce n'est pas la bonne question.** Ce chantier et le Chantier F (`COST_OPTIMIZATION_CHANTIERS.md`)
répondent à **deux motivations complètement séparées**, à ne plus jamais recombiner :

- **Chantier B (ce document) = coût, pas fiabilité.** Objectif : trouver un modèle de perception
  visuelle moins cher que Gemini pour le travail que font déjà T1/T2 aujourd'hui — Qwen3.8-Flash,
  un GPT vision bon marché, ou une autre suggestion — **idéalement d'aussi bonne qualité que
  Gemini 3.1 Pro**, pas parce que Gemini se trompe. Aucun jugement de fiabilité sur Gemini
  là-dedans.
- **Chantier F (`COST_OPTIMIZATION_CHANTIERS.md`) = fiabilité du raisonnement Tier 3, pas coût.**
  Le reproche de l'utilisateur à Gemini 3.1 Pro : il "ne vérifie pas les données" — illustré par
  l'épisode du PDF de benchmark fabriqué (`COST_OPTIMIZATION_CHANTIERS.md`, section vérification
  du 2026-09-07). Objectif : remplacer Gemini 3.1 Pro par Claude Sonnet 5 au Tier 3, selon deux
  variantes à trancher (§1bis) — **indépendamment** de tout ce qui touche au coût de la
  perception.

L'incident Qwen/Guerrilla Guitars (§2) reste pertinent **uniquement** comme leçon pour le
garde-fou du modèle de perception bon marché — il ne dit rien sur Gemini et ne doit plus servir
d'argument pour ou contre l'existence d'un "problème T3" (§8.6 corrigé en conséquence).

---

## 1. Principe d'architecture

Séparer deux rôles aujourd'hui confondus dans chaque appel Gemini de la cascade :

- **Perception** (fait une seule fois) : décrire ce qui est visible sur les photos — formes,
  couleurs, texte lu (OCR), état/usure, matériel visible, et (nouveau, voir §3) localisation des
  parties de l'instrument.
- **Raisonnement** (fait par le Tier 3, qui reste responsable de la conclusion) : à partir de
  cette description texte (jamais des photos brutes), répondre aux questions qui comptent pour
  l'utilisateur — "Gibson ou copie ?", "quelle année ?", valeur, état structurel.

**Décision utilisateur sur 8.1 (2026-09-07) : option large retenue.** Les trois Tiers (T1 Portier
compris) passent à la description texte du modèle de perception bon marché plutôt que de voir les
photos eux-mêmes — pas seulement T3. Gain de coût maximal (touche 100% du volume, pas seulement
les 5% qui atteignent T3), au prix du risque plus élevé déjà identifié : le Portier s'appuie
aujourd'hui sur l'examen visuel direct du logo/plaque comme preuve prioritaire pour filtrer
(`prompts.json:331`) — son comportement sur 100% du volume dépend désormais entièrement de la
qualité de la description, pas seulement de son propre jugement visuel. À valider en priorité par
le benchmark avant tout déploiement (§5).

**Conséquence directe, à traiter avant le code (héritée de 8.1)** : puisque la perception précède
maintenant tous les Tiers, les deux chemins qui sautent T1 doivent chacun obtenir leur propre appel
de perception avant de continuer, sans quoi ils se retrouveraient sans photos ET sans description :
- `force_expert=True` (ré-analyse manuelle, `analyzer.py:318,346-347`) — doit déclencher un appel
  de perception dédié avant T2/T3 plutôt que de sauter directement dessus.
- `analyze_deal_light()` (`analyzer.py:214-215,226`) — même chose avant son appel T2 direct.

## 1bis. Lien avec le Chantier F (remplacement de Gemini 3.1 Pro par Claude Sonnet 5 au Tier 3)

Deux variantes d'intégration, à trancher séparément de tout le reste de ce plan — mais le choix
détermine si le Chantier B devient un prérequis du Chantier F ou reste totalement indépendant :

- **(a) Remplacement intégral** : Claude Sonnet 5 fait vision + raisonnement lui-même au Tier 3
  (appel multimodal natif, voit les photos directement, ne dépend d'aucune étape de perception
  externe). Dans ce cas, **le Chantier B ne conditionne pas le Chantier F** — les deux avancent
  indépendamment, chacun sur son propre axe (coût de la perception T1/T2 d'un côté, qualité du
  raisonnement T3 de l'autre).
- **(b) Remplacement partiel** : Claude Sonnet 5 ne fait que le raisonnement, à partir d'une
  description textuelle des photos produite par le modèle de perception bon marché de ce
  Chantier B. Dans ce cas, **le Chantier B devient un prérequis technique du Chantier F** — le
  même texte de perception alimenterait alors soit Gemini 3.1 Pro, soit Sonnet 5, ce qui permet
  au passage de comparer les deux raisonneurs sur un pied d'égalité (même entrée, seul le
  raisonnement diffère) plutôt que de confondre différence de raisonnement et différence de
  vision dans le résultat du benchmark.

**Pas encore tranché.** Les deux méritent d'être mesurées par le harnais de benchmark (candidat
`claude_sonnet` déjà codé pour (a), variante (b) à ajouter si retenue) avant de choisir — voir
`COST_OPTIMIZATION_CHANTIERS.md` Chantier F pour l'état d'avancement de cette comparaison.

## 2. Garde-fou — scope volontairement limité au logo pour l'instant

**Décision explicite de l'utilisateur (2026-09-07)** : la généralisation de ce garde-fou à toute
la couche de perception (au-delà du logo — bois, matériel, année...) a été envisagée puis
**reportée** : elle mérite une discussion détaillée à part, pas une extension actée en une ligne
dans ce plan. Pour cette itération, le garde-fou reste **scopé au logo**, conformément à la leçon
tirée de l'incident Qwen/Guerrilla Guitars (Qwen avait conclu "marque budget OEM" au lieu de
simplement décrire ce qu'il voyait).

**Précision du critère (2026-09-07)** : "ne pas interpréter" ne veut pas dire "décrire au minimum"
— c'est l'inverse. Le modèle de perception doit produire une description **aussi précise et
complète que possible** de ce qu'il voit sur le logo/l'étiquette (forme, police, couleurs, texte
exact lu, position, état d'usure du marquage) — **suffisante pour que le LLM de raisonnement en
aval puisse lui-même identifier l'instrument à partir de cette seule description**, sans jamais
que la perception fasse ce travail d'identification à sa place. Exemple concret (incident de
référence) : jamais "marque budget OEM" (jugement), mais quelque chose comme "logo doré appliqué
en lettres cursives inclinées, texte '[transcription exacte]', positionné au centre de la tête
juste sous le sillet, léger écaillage sur le bord gauche" (description) — assez riche pour que le
Tier 3, lui, puisse reconnaître ou non une marque connue à partir de ces détails.

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

**8.1 — TRANCHÉ (2026-09-07, §1) : option large retenue, T1 compris.** Reformulé ci-dessous pour
mémoire — l'objection technique originale, qui suit :
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

**8.3 — ACTÉ COMME TRAVAIL À FAIRE (2026-09-07, §2) : le contrat de sortie de perception doit être
dérivé du contrat JSON de prod, pas copié du prompt de benchmark.** Le contrat T3 de production exige des champs purement perceptuels que le
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

**8.6 — CORRIGÉ (2026-09-07, §0) : cette objection ne s'applique plus telle quelle.** Formulée à
l'origine contre une motivation "fiabiliser T3" que ce plan n'a en réalité jamais eue — la vraie
motivation du Chantier B est le coût de la perception, indépendante de toute question de fiabilité
de Gemini (§0). L'observation technique sous-jacente reste vraie et utile, reformulée sous la
bonne question : T3 (`gemini-3.1-pro-preview`) est le meilleur modèle vision du pipeline, et tous
les candidats de perception bon marché (§4) sont *a priori* plus faibles sur la vision pure — donc
**le vrai critère n'est pas "Gemini a-t-il un problème ?" mais "le candidat bon marché retenu
égale-t-il la qualité de perception actuelle, à un prix inférieur ?"**, exactement ce que mesure
déjà §5. Rien à rassembler comme "preuve d'échec" avant de commencer — le §5 (benchmark) est la
preuve à produire, pas un prérequis distinct.

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

**Verdict (mis à jour après décisions du 2026-09-07)** : 8.1 et 8.6 sont réglés (§1, §0). Reste
bloquant avant tout code : **8.3** — écrire le contrat de perception complet, champ par champ du
JSON de prod, avec le niveau de précision défini en §2 (décrire sans conclure, mais assez
richement pour que le raisonnement en aval reste possible) — et couvrir les deux chemins qui
sautent T1 (conséquence de 8.1, notée en §1). 8.2, 8.4, 8.5, 8.8 restent des corrections de
rédaction/périmètre à intégrer en écrivant le code. 8.7 (cohérence chat) à retrancher des
motivations affichées ou à ajouter explicitement au plan technique.
