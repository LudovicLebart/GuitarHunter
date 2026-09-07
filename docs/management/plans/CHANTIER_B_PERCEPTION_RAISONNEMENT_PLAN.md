# Plan d'implémentation — Chantier B : séparer perception et raisonnement (2026-09-07)

**Statut :** plan formalisé, aucun code de production touché. Formalise et étend
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
