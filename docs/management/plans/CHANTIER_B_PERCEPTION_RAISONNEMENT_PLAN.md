# Plan d'implémentation — Chantier B : séparer perception et raisonnement (2026-09-07)

**Statut :** consolidé après 3 passages Claude Opus (voir §8 pour l'historique complet — texte
intégral conservé dans l'historique git, pas ici). Ce document remplace les versions précédentes
qui empilaient des sections de correction sans jamais réécrire les parties opérantes — d'où des
contradictions relevées à chaque relecture. Reste un point non vérifié par Opus (la règle de
décision §0 et le protocole de benchmark §5 réécrits ici) — à confirmer avant d'écrire le code.

---

## 0. Motivation et règle de décision

**Chantier B teste si un modèle de vision moins cher que Gemini peut faire, à partir des photos,
le travail de perception que font aujourd'hui T1/T2/T3** — pas parce que Gemini se trompe (ça,
c'est le Chantier F, séparé, voir §1bis), mais pour voir si on peut payer moins cher pour un
résultat équivalent ou meilleur.

Le chantier sert plusieurs objectifs à la fois — coût, cohérence de l'analyse entre Tiers et avec
le chat, réutilisation pour `NECK_RESET_VISION_PLAN.md`, tagging de vue par photo — **mesurés
séparément, jamais agrégés en un score unique** : ils "servent des desseins différents" (décision
explicite de l'utilisateur). Un chantier peut réussir sur un axe et échouer sur un autre sans que
ça se compense.

**Règle de décision unique (remplace les trois règles contradictoires des versions précédentes)** :
chaque axe mesuré est classé dans une des trois catégories suivantes, et une seule détermine si on
déploie :

| Catégorie | Axes | Effet |
|---|---|---|
| **Verrou** | Pas de régression sur l'identification (§5) ; garde-fou anti-interprétation respecté (§2) | **Bloque le déploiement si non satisfait.** Aucune exception. |
| **Étiquette de prix** | Coût réel du chantier ($/mois) | **Ne bloque pas.** Chiffré et présenté à l'utilisateur, qui décide en connaissance de cause même si le delta est défavorable. |
| **Informatif** | Localisation de parties (§3), tagging, réutilisation neck-reset, cohérence chat | **Ne bloque jamais.** Mesuré et rapporté, sans effet sur la décision de déploiement du cœur T1/T2/T3. |

Le rapport de benchmark (§7) doit produire une ligne par axe dans ce tableau, jamais un score
composite.

---

## 1. Architecture

Séparer deux rôles aujourd'hui confondus dans chaque appel Gemini de la cascade :

- **Perception** (faite une seule fois par annonce) : décrire ce qui est visible sur les photos —
  formes, couleurs, texte lu (OCR), état/usure, matériel visible.
- **Raisonnement** (fait par chaque Tier, qui reste responsable de sa conclusion) : à partir de
  cette description texte (jamais des photos brutes), répondre aux questions qui comptent —
  filtrage (T1), scoring (T2), rapport complet (T3).

**Option retenue : large, T1 compris.** Les trois Tiers passent à la description texte plutôt que
de voir les photos eux-mêmes — pas seulement T3. Gain de coût maximal (100% du volume, pas
seulement les 5% qui atteignent T3), au prix d'un risque plus élevé : le Portier s'appuie
aujourd'hui sur l'examen visuel direct du logo/plaque comme preuve prioritaire pour filtrer
(`prompts.json:331`) — son comportement sur 100% du volume dépendra désormais entièrement de la
qualité de la description. C'est exactement l'axe **verrou** que §5 doit valider en priorité.

**Chemins d'appel** (4 sites, tous via `_run_analysis_cascade` — `bot.py:410/1089/1311`,
`backend/scripts/reanalyze_sold_deals.py:108`) :
- `force_expert=True` (ré-analyse manuelle, `analyzer.py:318`) n'a **pas** besoin d'un appel de
  perception dédié — si le point d'insertion de la perception est placé avant cette ligne, ce
  chemin l'obtient automatiquement.
- `analyze_deal_light()` (`analyzer.py:189-231`) est **exclu du chantier** : il existe
  spécifiquement pour être bon marché sur de l'historique déjà vendu, et son prompt interdit déjà
  tout texte libre. Lui ajouter une perception payante contredirait sa raison d'être — reste sur
  photos.

**Repli obligatoire** : contrairement à T1/T2/T3 qui ont chacun un fail-open existant
(`analyzer.py:328-331/361-362/419-422`), l'étage de perception n'a aujourd'hui aucune redondance.
Sous l'option large, une panne du fournisseur choisi (probablement externe, §4) aveuglerait 100%
du pipeline. **À construire dès le premier code** : si l'appel de perception échoue, retomber sur
l'envoi direct des photos au Tier concerné (comportement actuel), jamais un blocage silencieux. Le
code candidat porté doit aussi avoir un timeout explicite (absent aujourd'hui sur le chemin
OpenAI-compatible, `candidates.py:165-180`), puisque l'appel est sur le chemin synchrone du scan
(`bot.py:410`).

**Point d'insertion technique** : ne pas ajouter de drapeau dans `analyzer.py`. Extraire
`analyzer.py:298-299` (construction de la liste d'images) en une méthode dédiée
(`_prepare_visual_parts(listing_data)`) — refactoring pur, comportement strictement inchangé côté
prod. Le harnais de benchmark peut alors substituer cette méthode localement (sous-classe ou
monkeypatch propre au test) pour brancher la perception, sans jamais toucher au comportement de
production avant une décision de déploiement.

## 1bis. Lien avec le Chantier F (remplacement de Gemini 3.1 Pro par Claude Sonnet 5 au Tier 3)

Chantier séparé (`COST_OPTIMIZATION_CHANTIERS.md`), motivé par la fiabilité du raisonnement plutôt
que le coût de la perception — voir §0. Deux variantes d'intégration à trancher séparément :

- **(a) Remplacement intégral** : Sonnet 5 fait vision + raisonnement lui-même au Tier 3.
  Indépendant du Chantier B.
- **(b) Remplacement partiel** : Sonnet 5 ne fait que le raisonnement, à partir de la description
  produite par ce Chantier B — dans ce cas, B devient un prérequis technique de F, et permet de
  comparer Gemini/Sonnet 5 sur le seul raisonnement (même entrée texte des deux côtés).

Pas encore tranché — à mesurer par le harnais (candidat `claude_sonnet` déjà codé pour (a)) avant
de choisir.

---

## 1ter. Élargissement du Chantier F aux 3 Tiers (2026-09-09) — enseignements de l'enquête caching Gemini

**Le champ de test et d'évaluation du Chantier F s'élargit** : jusqu'ici scopé au seul Tier 3
(`gemini-3.1-pro-preview` → Claude Sonnet 5), il couvre désormais les **3 Tiers** (Portier,
Analyste, Expert Pro) — motivé par ce qui suit, mesuré sur la branche `dev` en marge de ce
chantier (`JOURNAL.md`/`GEMINI_PROMPT_CACHING_PLAN.md §9` sur `dev`, non fusionné ici).

**Ce qu'on a mesuré côté Gemini (les 3 Tiers actuels)** :
- Le cache implicite Gemini (`§0` de ce document, mécanisme équivalent côté Gemini au caching
  Claude ci-dessous) a un seuil minimum de préfixe commun **dépendant du modèle** : 4096 tokens
  pour toute la famille Gemini 3/3.1 (Flash 3.5-3.8 et Pro 3.1 Preview — nos 3 Tiers), contre 2048
  sur l'ancienne génération 2.5.
- Le bloc statique partagé (taxonomie + few-shot + prompt principal, `prompts.json`) mesure
  aujourd'hui **~4712 tokens** (remesuré le 2026-09-09, corrige l'estimation de ~3205 tokens du
  `GEMINI_PROMPT_CACHING_PLAN.md §7.1`, devenue obsolète après plusieurs enrichissements de la
  taxonomie) — au-dessus du seuil, ce qui explique que le cache morde un peu sur T2/T3.
- **Mesure réelle en production (2026-09-08, 20776 logs Firestore scannés)** : Tier 2
  (`gemini-3.7-flash`) 17,5% des appels cachés ; **Tier 3 (`gemini-3.1-pro-preview`, notre cible
  actuelle du Chantier F) 0% sur 11 appels** — mais un diagnostic de timing a montré que c'est
  cohérent avec une simple variance d'échantillon au taux de T2 (~2 hits attendus), pas une
  preuve de dysfonctionnement ; **Tier 1 (`gemini-3.5-flash-lite`, Portier) 0% sur 78 appels**,
  malgré l'espacement entre appels le plus serré des 3 — anomalie statistiquement significative,
  cause non confirmée (comportement Flash-Lite possiblement différent/plus restrictif).
- Le cache implicite Gemini est un mécanisme **opportuniste/best-effort côté serveur** : aucun
  objet persistant, taux de hit partiel même sur un Tier éligible, pas de garantie.

**Ce qui rend l'élargissement à Claude pertinent pour les 3 Tiers, pas seulement T3** : le caching
Claude (`cache_control`, prefix match) est **explicite et vérifiable** — un `cache_control` sur le
bloc statique donne un hit garanti tant que le TTL n'a pas expiré, avec un signal direct
(`usage.cache_read_input_tokens`) pour savoir si ça marche, contrairement au best-effort Gemini
qu'on vient de mettre des jours à diagnostiquer indirectement via les logs. Seuils minimums par
modèle : 512 tokens (Opus 5, Fable 5/5.1), 1024 tokens (Sonnet 5), 4096 tokens (Haiku 4.5 — le
plus proche du rôle "Portier" bon marché). Notre bloc statique (~4712 tokens) passe tous ces
seuils. Économiquement, le cache explicite Claude n'a **pas de coût de stockage au repos**
(contrairement au cache explicite Gemini, facturé à l'heure qu'il serve ou non) — seulement un
surcoût à l'écriture (1,25×/2× selon TTL) et une réduction à la lecture (~0,1×), ce qui change
complètement le calcul de rentabilité qu'on avait fait côté Gemini (`GEMINI_PROMPT_CACHING_PLAN.md
§9`, marginal/négatif à cause du stockage).

**Conséquence concrète pour le protocole de benchmark (§5)** : instrumenter le candidat
`claude_sonnet` (et tout futur candidat Anthropic pour T1/T2) avec `cache_control` sur le bloc
statique dès l'écriture du contrat de perception/raisonnement — en respectant le même ordre
statique-puis-dynamique déjà noté comme piège en §6 — plutôt que d'ajouter le caching après coup.
Élargir aussi la mesure tokens/coût/latence (§7, point 5) aux 3 Tiers, avec une colonne dédiée
`cache_read_input_tokens`/`cache_creation_input_tokens` pour vérifier objectivement le hit rate
Claude par Tier, comparable au taux Gemini mesuré ci-dessus.

---

## 2. Garde-fou de perception — scope logo, prédicats observables uniquement

**Scope** : limité au logo pour cette itération (généralisation à d'autres indices visuels —
bois, matériel, année — reportée à une discussion dédiée, notée au `TODO.md`).

**Critère de précision** : "ne pas interpréter" ne veut pas dire "décrire au minimum" — c'est
l'inverse. La description doit être **aussi précise et complète que possible** sur ce qui est
objectivement observable (forme, police, couleurs, texte exact lu, position, usure du marquage),
**suffisante pour que le raisonneur en aval identifie lui-même l'instrument**, sans que la
perception conclue à sa place. Jamais "marque budget OEM" (jugement) ; toujours quelque chose comme
"logo doré en lettres cursives inclinées, texte '[transcription exacte]', centré sous le sillet,
léger écaillage à gauche" (description).

**Règle opérationnelle pour distinguer observation de jugement** : n'autoriser que des prédicats
objectivement vérifiables par un tiers regardant la même photo (couleur exacte, forme géométrique,
texte transcrit, présence/absence d'un défaut visible) — bannir tout adjectif évaluatif ("qualité",
"soigné", "artisanal", "bon marché", "qui pourrait indiquer une origine"). Le prompt `hybrid` du
benchmark, dont ce garde-fou s'inspire, **fuit déjà sur ce point** (`candidates.py:203-204,209-211`
demande la "qualité apparente de fabrication" et des caractéristiques "qui pourraient indiquer une
origine") — à corriger dans ce prompt avant de le réutiliser comme base de perception.

**Champ de couverture obligatoire** : chaque zone/élément que la perception ne peut pas voir
clairement doit être signalé explicitement ("logo illisible", "tête hors cadre") plutôt que
laissé sans mention — pour que le raisonneur distingue "non observable" de "non mentionné par
oubli" plutôt que de halluciner pour combler le vide.

---

## 3. Localisation des parties — axe informatif, mesuré sur les candidats eux-mêmes

Ne **pas** réutiliser le pipeline OWLv2/Dell de `NECK_RESET_VISION_PLAN.md` comme vérité terrain —
objectif différent : voir ce que les modèles candidats eux-mêmes obtiennent quand on leur demande
de localiser les parties visibles, exploratoire, pas comparé à une référence externe.

Run **séparé** de l'appel noté par le juge (jamais mélangé avec la réponse d'identification, pour
ne pas contaminer l'axe verrou). Contrat de sortie neutre sur le contenu mais strict sur le format
(`{"parts":[{"image_index":0,"label":"<libre>","box":[x0,y0,x1,y1]}]}`, coordonnées normalisées
0-1, origine coin haut-gauche) — sans quoi un rectangle mal placé à l'écran est indiscernable d'une
erreur de perception. Le taux de conformité au format est lui-même une donnée utile par candidat.

Axe **informatif** (§0) : ne doit **jamais** entrer dans le contrat de perception de production
(§7) — il gonflerait le seul poste qui compte pour l'axe étiquette-de-prix.

---

## 4. Candidats pour le rôle de perception

1. **Réutiliser le Tier 1 actuel** (`gemini-3.5-flash-lite`) — voit déjà 100% des photos à coût
   marginal, zéro nouveau fournisseur. Risque connu : signal de prudence `NECK_RESET_VISION_PLAN.md`
   sur sa fiabilité à distinguer des vues fines, à re-tester spécifiquement sur des indices
   d'authentification.
2. **Qwen3.8-Flash** (0,14$/0,42$ par M tokens, vérifié 2026-09-07) — déjà intégré via TokenRouter
   dans le harnais (candidat `hybrid`), le moins cher des candidats sérieux identifiés à ce jour.
3. **GPT** — tarif/capacité vision d'un équivalent "mini" chez GPT-5.6 non vérifiés à ce jour ; à
   vérifier avant de l'inclure plutôt que deviner.

**Perceveur ≠ raisonneur** dans le protocole de test (§5) : le candidat de perception (ex. Qwen)
produit la description, un raisonneur **distinct** (représentatif de la prod, pas nécessairement
le même modèle) la consomme. Tester un modèle qui se résume à lui-même répond à une question sans
rapport avec le déploiement envisagé.

---

## 5. Protocole de validation

**Deux bras, tous deux fidèles à la prod autant que possible** :
- **Bras A (référence)** : cascade actuelle sur photos, via `DealAnalyzer.analyze_deal()` appelé
  tel quel — aucune modification d'`analyzer.py` requise pour ce bras.
- **Bras B (candidat)** : cascade alimentée par la perception, via `_prepare_visual_parts()`
  substituée localement au harnais (§1, point d'insertion technique) — pas de drapeau en prod.

**Limite de fidélité assumée** : les prompts/config de prod sont modifiables par utilisateur en
Firestore (ConfigPanel), et l'environnement de dev n'a pas d'accès Firestore réel (`CLAUDE.md`).
Le bras A/B tournera sur les défauts de `prompts.json`, pas sur la config Firestore réelle d'un
compte qui l'aurait personnalisée — limite documentée, pas résolue ici.

**Vérité terrain structurée** (pas de la prose) : puisque la cascade de prod répond en JSON
(`response_mime_type: application/json`, `analyzer.py:61`), la vérité terrain du dataset doit être
structurée champ par champ (identification, année, authenticité, état, valeur, `color`,
`finish_application`, `finish_texture`) pour être comparable — une vérité terrain en prose ne peut
pas juger un candidat qui répond en JSON structuré.

**Protocole de mesure de l'axe verrou (identification)** — traduction opérationnelle du critère
utilisateur ("la description doit permettre au raisonneur de tirer les mêmes conclusions, voire de
meilleures, que s'il avait vu la photo lui-même") :
1. Pour chaque item du dataset, exécuter le bras A et le bras B, **avec le raisonneur de
   production** (pas seulement un modèle faible — un test uniquement sur un raisonneur faible ne
   dit rien du déploiement réel, qui remplace l'entrée du meilleur modèle vision du pipeline).
   Optionnellement, répéter avec un raisonneur bon marché pour information, mais **le verrou se
   juge sur le raisonneur de prod**.
2. Juger A et B séparément par axe (identification/état/valeur/hallucination), avec une règle de
   juge réécrite : la règle actuelle ("omission d'un détail = score 0", `judge.py:39`) pénalise
   mécaniquement toute reformulation et doit être remplacée par un jugement sur l'exactitude des
   affirmations faites, pas sur l'exhaustivité de la formulation.
3. B "suffit" sur l'axe identification si son score égale ou dépasse celui de A, avec une marge de
   non-infériorité et un nombre de runs fixés **avant** le lancement (ni le juge ni les candidats
   n'ont de température fixable de façon fiable — répéter plusieurs fois par item est nécessaire
   pour distinguer un vrai écart du bruit).
4. Le rapport de perception de chaque candidat doit être persisté (pas jeté après usage comme
   aujourd'hui, `candidates.py:229`) et jugé séparément sur le respect du garde-fou (§2) — un
   candidat qui "devine" plutôt que de couvrir explicitement une zone non visible doit être
   pénalisé sur cet axe précis, indépendamment de son score d'identification.
5. Échantillonner aussi des annonces **rejetées** par T1 (pas seulement des annonces déjà
   acceptées comme dans `dataset.json` actuel) pour mesurer un taux de faux rejet/faux passage du
   Portier sous perception — c'est l'axe verrou le plus à risque de l'option large (§1) et le seul
   que le dataset actuel ne peut pas mesurer.

**Protocole de mesure de l'axe étiquette-de-prix (coût)** : ne pas imposer de longueur cible a
priori. Faire varier la consigne de longueur par paliers (ex. ~150/350/700/1400 tokens, en
consigne souple dans le prompt, jamais en coupe dure qui tronquerait au milieu d'une phrase et
biaiserait la qualité) et **mesurer la longueur réellement produite** comme covariable observée
(pas la longueur nominale demandée) — puis analyser le taux de passage du test d'ablation en
fonction de cette longueur observée. Instrumenter les trois chemins d'appel candidats
(Gemini/OpenAI-compat/Anthropic, `candidates.py:63/159-162/180`, aujourd'hui tous jetés) pour
capturer tokens/coût/latence réels par palier. Confronter le point de bascule mesuré au point mort
déjà chiffré (~1385 tokens/annonce sur la population actuelle — à recalculer une fois l'échantillon
étendu aux rejets T1, cf. point 5 ci-dessus, car le mix réel de population change ce chiffre).

**Décision finale** : verrou satisfait (identification + garde-fou) → coût affiché comme étiquette
de prix, quel qu'il soit → déploiement possible, décision finale de l'utilisateur informée par le
chiffre. Verrou non satisfait → pas de déploiement, quels que soient les autres axes.

---

## 6. Risques

- **Signal de prudence déjà documenté** (`NECK_RESET_VISION_PLAN.md`) : aucun modèle bon marché
  n'a encore été validé fiable sur de la reconnaissance visuelle fine sur ce projet — ne pas
  déployer avant mesure.
- **Coût potentiellement défavorable** : le point mort mesuré (~1385 tokens/annonce sur la
  population de référence) peut ne pas être atteignable sans perdre en qualité — c'est
  explicitement une issue possible et acceptable du benchmark (axe étiquette-de-prix, §0), pas un
  échec du plan.
- **Nouveau point de défaillance unique** : un fournisseur de perception externe sur le chemin
  synchrone de 100% du scan (§1) — repli obligatoire à construire, pas optionnel.
- **Piège de cache déjà vécu** : la description est dynamique par annonce — elle doit être ajoutée
  **après** le bloc statique (prompt + taxonomie + few-shot) dans chaque prompt de Tier, jamais
  avant, exactement la régression déjà corrigée pour T3 (`analyzer.py:410-415`, Chantier 0.b). À
  respecter dès l'écriture du contrat de perception, sinon le gain image serait annulé par la
  perte de cache.
- **Régression invisible au score du juge** : le vrai risque de régression porte autant sur les
  champs à énumération fermée (`finish_application`/`finish_texture`, utilisés en comparaison
  stricte dans un filtre utilisateur réel, `src/hooks/useDealsManager.js:454-455`,
  `src/components/FilterDrawer.jsx:56-57`) que sur le texte libre noté par le juge — la vérité
  terrain structurée (§5) couvre ce risque, un jugement en prose seule ne le verrait pas.

---

## 7. Étapes concrètes (code)

**Corrections immédiates, indépendantes du reste (aucun résultat de benchmark requis)** :
1. Supprimer le champ `visual_inspection` (`prompts.json:297`) — demandé, stocké, lu par personne
   dans `src/` — gain de sortie gratuit.
2. Extraire `_prepare_visual_parts()` d'`analyzer.py:298-299` (refactor pur, zéro changement de
   comportement).
3. Corriger `analyzer.py:282` (`firestore_config.get('analysisConfig', {})` sans garde `or {}`,
   contrairement à `analyze_deal`) pour que le harnais puisse appeler `analyze_deal` avec un
   `firestore_config` minimal sans lever.

**Instrumentation du harnais (prérequis technique du protocole §5)** :
4. Contrat de retour des candidats : `str` → `{answer, perception_report, usage}` — touche les
   entrées de `CANDIDATES` (`candidates.py`).
5. Capturer tokens/coût/latence réels sur les trois chemins d'appel (aujourd'hui jetés).
6. Timeout explicite sur le chemin OpenAI-compatible (`candidates.py:165-180`).
7. `judge.py` : score par axe, réécriture de la règle d'omission (§5), passe de jugement séparée
   sur le rapport de perception (respect du garde-fou §2).

**Dataset** :
8. ✅ **Codé** (2026-09-07) : `backend/scripts/sample_benchmark_dataset.py` (dérivé
   d'`export_neck_reset_sample.py`, même pattern lecture-seule via `ops/run-script`) : 30-50
   annonces, mix Tier atteint **incluant des rejets T1**, vérité terrain structurée par champ
   (pas prose) — pas reprise telle quelle de la sortie Gemini de prod, seulement un point de
   départ. Non exécuté (pas d'accès Firestore depuis ce sandbox).
9. ✅ **Codé et publié** (2026-09-07) : interface de validation —
   [Banc d'Essai](https://claude.ai/code/artifact/87151727-77d7-42f7-a6aa-31d70d37de35)
   (Artifact, capacité `db`). Photos + champs pré-remplis (identification/authenticité/état/
   valeur, calqués sur le contrat JSON de prod, `finish_application`/`finish_texture` en menus
   déroulants avec les valeurs fermées exactes de `prompts.json`) + confirmation par fiche +
   suivi de progression + filtres par strate. **Vide pour l'instant** : lit `deals`/`meta` depuis
   sa base — à peupler une fois l'étape 8 exécutée en prod (`write_db` batch depuis le manifeste
   JSON + upload des photos en `data:` URI dans une sous-collection `deals/{id}/photos`, la
   capacité `assets` de l'Artifact n'étant pas disponible sur ce compte). Une fiche d'exemple non
   modifiable s'affiche en l'absence de données, pour montrer le rendu final sans risquer de
   confirmer par erreur une donnée fictive. Rectangles de localisation (axe informatif, §3) pas
   encore intégrés à cette interface — à ajouter une fois le format de sortie des candidats fixé
   (§7 étape 2, déjà codé côté harnais).

**Contrat de perception (8.3)** :
10. ✅ **Codé** (2026-09-07) : `backend/benchmark/perception_contract.py` — contrat de sortie
    dérivé champ par champ du JSON de prod réel (`color`, `finish_application`, `finish_texture`
    aux mêmes valeurs fermées que `prompts.json` ; `logo_transcription` sous le garde-fou §2 ;
    `condition_notes` factuel, jamais de score ; `unclear_or_hidden_areas` comme champ de
    couverture explicite). Champs qui demandent une connaissance de lutherie (`brand`,
    `model_name`, `production_year`, `country_of_origin`, `classification`) volontairement
    **exclus** du contrat — ça reste le travail du raisonneur, jamais de la perception.
    Intégré au harnais via deux nouveaux candidats (`perception_qwen`, `perception_flash_lite`,
    `backend/benchmark/candidates.py`) qui appliquent ce contrat puis font raisonner Gemini
    Tier 3 sur le texte seul — couvre les deux options de perception les plus simples de §4
    (Qwen3.8-Flash / réutilisation du modèle T1). **Portée volontairement limitée au
    benchmark** : aucun de ces candidats ne touche `analyzer.py`/`prompts.json` de production.
    Testé par 6 cas unitaires isolés (JSON valide, fences markdown, réponse non structurée,
    entrée vide/`None`, présence de tous les champs dans le prompt du raisonneur) — succès.
    **Reste à faire, hors périmètre de ce contrat lui-même** : le couvrir pour T1 **et** T2 (pas
    seulement l'oracle T3 actuel des candidats `hybrid`/`perception_*`) suppose un candidat qui
    appelle réellement la cascade `DealAnalyzer` à 3 étages plutôt qu'un unique appel Tier 3 —
    c'est le travail du protocole de mesure fidèle à la prod (§5, toujours non fait, cf. 9.4(b)).
11. **Regroupé avec l'étape 12 ci-dessous, pas fait séparément.** La réécriture des trois
    instructions de prod (`prompts.json`) pour un consommateur texte-only n'a de sens qu'au
    moment où le candidat retenu est effectivement implémenté dans `analyzer.py` — la faire
    maintenant, avant tout résultat de benchmark, reviendrait à modifier le comportement réel du
    Portier/Analyste/Expert sur la seule base d'une intuition, exactement ce que §7 étape 12
    interdit explicitement. Reste un point ouvert pour ce moment-là : ces prompts sont éditables
    par utilisateur en Firestore, la migration des comptes existants n'est pas résolue ici.

**Chat — différé explicitement, pas dans ce premier passage.** La cible reste "une perception,
plusieurs consommateurs" (§0, axe informatif "cohérence chat"), mais trois frictions réelles du
code existant méritent leur propre mini-plan plutôt qu'une ligne ajoutée à 8.3 : le chat envoie
déjà les photos lui-même (`geminiChatService.js:202-214`) donc la perception s'**ajouterait** au
coût existant, pas ne le remplacerait ; `buildDealContextText` n'est appelé qu'au premier message
et persisté verbatim (`useDealChat.js:490,514,520-528`) — une ré-analyse ultérieure ne serait
jamais reflétée dans une conversation déjà ouverte (le dépôt a déjà un contournement pour un bug
analogue, `pendingRequalificationNoteRef`, `useDealChat.js:235-241`, réutilisable le moment venu) ;
et `elideOldChatPhotos` n'élide que les photos, jamais le texte (`useDealChat.js:116-144`), donc la
description serait rejouée intégralement à chaque tour — le même piège déjà identifié pour
`buildRestorationPlanContextText` (`COST_OPTIMIZATION_CHANTIERS.md` Chantier C).

**Implémentation finale** :
12. **Seulement après un résultat favorable sur l'axe verrou (§0/§5)** : remplacer
    `_prepare_visual_parts()` par la vraie logique de perception en production, comme changement
    séparé et validé à part.

---

## 8. Historique des consultations Opus (résumé)

Trois passages Claude Opus le 2026-09-07, texte intégral conservé dans l'historique git de ce
fichier (commits `0087f2a`, `f144434`, `fde0204`, `e03f818`, `495f6d4`) plutôt que dupliqué ici.

- **Passage 1** : plan jugé non prêt sur la base d'une motivation mal formulée ("fiabiliser T3")
  — erreur de brief corrigée par l'utilisateur avant le passage 2 (Chantier B = coût, séparé du
  Chantier F = fiabilité). A aussi identifié : l'architecture d'insertion de la perception non
  tranchée, le garde-fou `hybrid` déjà fuyant, le contrat de sortie à dériver du JSON de prod, le
  critère de rollout non mesurable avec le harnais existant.
- **Passage 2** (après décision "option large, T1 compris" + précision du garde-fou) : cadrage
  encore contradictoire entre motivation "coût seul" et les raisons produit archivées ailleurs ;
  critère de suffisance ("aussi précise que possible") non mesurable sans un test d'ablation
  formel ; absence de budget de tokens alors que c'est la variable qui décide de la rentabilité
  (point mort chiffré à ~1385 tokens/annonce) ; critère de validation auto-contradictoire dans son
  ordonnancement (exige de toucher `analyzer.py` avant le benchmark, que le plan interdisait par
  ailleurs).
- **Passage 3** (après résolution : objectifs multiples non agrégés, test d'ablation formalisé,
  budget déduit du benchmark) : les décisions n'avaient pas été propagées dans les sections
  opérantes du plan, créant nommément de nouvelles contradictions (règle de déploiement à trois
  versions concurrentes ; test d'ablation biaisé dans les deux sens — en faveur de B si le
  raisonneur testé est trop faible, contre B par la règle de jugement d'omission ; aucun mécanisme
  réaliste pour contrôler la longueur de description ; trois frictions réelles non anticipées sur
  l'intégration chat ; exception d'instrumentation plus large que nécessaire).

Ce document (réécriture consolidée du 2026-09-07) intègre les trois passages directement dans les
sections opérantes ci-dessus, avec une règle de décision unique (§0) et un protocole de benchmark
qui répond explicitement aux biais identifiés au passage 3 (§5). **Non encore revérifié par un
quatrième passage Opus** — à la demande de l'utilisateur, on passe à l'écriture du code plutôt que
de continuer les allers-retours.
