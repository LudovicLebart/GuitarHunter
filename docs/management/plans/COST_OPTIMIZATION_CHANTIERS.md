# Chantiers d'optimisation coûts & comparatifs modèles — Guitar Hunter (2026-09-07)

> Document de synthèse, pas un plan d'implémentation détaillé pour chaque chantier (certains
> en ont déjà un dédié, référencé ci-dessous). Objectif : rassembler toutes les conclusions et
> pistes issues de l'enquête coût Gemini de cette session (voir `JOURNAL.md` 2026-09-06/07),
> ajouter les nouvelles idées formulées par l'utilisateur, et les séparer en chantiers
> **distincts et indépendants** — chacun a ses propres motivations, son propre risque, et peut
> être priorisé/décidé séparément des autres. Aucun chantier ci-dessous n'est encore engagé
> au-delà de ce qui est explicitement marqué "codé".
>
> Soumis à l'avis de Claude Opus (voir section finale) avant toute décision de priorité.

---

## Vue d'ensemble — d'où vient ce document

L'enquête de cette session (`JOURNAL.md` 2026-09-06/07) a fermé la boucle sur le "pourquoi la
facture Gemini est si élevée" : un calcul bottom-up sur la période de facturation réelle
(1377 annonces, 1-6 septembre 2026) reconstruit la facture à 3,4% près (9,43$ estimés contre
9,76$ réels). **Mise à jour post-consultation Opus** : ce chiffre à 3,4% signifiait aussi que
le cache implicite Gemini ne mord probablement pas du tout (le calcul suppose le plein tarif
sur toute l'entrée) — voir Chantier 0, ajouté après coup, qui prend le pas sur tout le reste.
Ce qui semblait un mystère de coût par annonce était en réalité un problème de
**volume mal calibré** (95 annonces/jour mesurées 30 jours plus tôt vs ~229/jour sur la
période réelle facturée) — le modèle de coût par annonce était juste depuis le début. Cette
clôture ouvre la voie à des chantiers d'optimisation ciblés plutôt qu'à une chasse au fantôme.

---

## Chantier 0 — Deux leviers gratuits identifiés par Opus (à investiguer AVANT tout le reste)

**Ajouté après la consultation Opus (2026-09-07)** : absents du document initial, jugés par
Opus plus importants que les chantiers B et C réunis, sans aucun risque qualité.

**0.a — Expliquer le passage de 95 à ~229 annonces/jour.** Le coût est linéaire en volume : ce
facteur 2,4x explique à lui seul l'essentiel de l'écart entre l'estimation mensuelle
précédente (~12-14$) et la réalité (~82-87$). Cause non confirmée (backfill, ré-analyses en
masse, ou vraie hausse d'activité) — si une part notable des 1377 annonces de la période sont
des ré-analyses ou des doublons déjà vus, c'est un gain à deux chiffres en pourcentage sans
toucher à la qualité d'aucune analyse. Probablement la même cause que la hausse Firestore de
septembre (+41% lectures/+74% écritures, non expliquée) — une seule investigation répondrait
aux deux, et recadrerait le Chantier A.

**0.b — Vérifier que le caching implicite Gemini fonctionne réellement.** Le calcul bottom-up
qui colle à 3,4% de la facture réelle suppose le plein tarif sur 100% des tokens d'entrée — un
signe que le cache implicite ne mord probablement pas du tout, alors qu'il devrait (le prompt
de base ne change pas d'un appel à l'autre). Deux causes identifiées par Opus dans le code
réel :
- `backend/analyzer.py:97` : `json.dumps(taxonomy_data, indent=2, ensure_ascii=False)` **sans
  `sort_keys=True`** — le préfixe envoyé à Gemini n'est pas garanti identique octet pour octet
  entre threads/redémarrages, cassant le cache implicite. `GEMINI_PROMPT_CACHING_PLAN.md` §2.3
  demandait déjà ce correctif, jamais appliqué.
- `backend/analyzer.py:406` : `full_prompt_t3 = f"{context_t3}\n\n{base_prompt}"` — le Tier 3
  place le contexte **variable** (annonce en cours) *avant* le bloc statique (taxonomie/prompt
  de base), détruisant son propre préfixe cacheable. T1/T2 font l'inverse (statique d'abord,
  `analyzer.py:320`/`353`) et sont corrects.
- Correctif proposé : ajouter `sort_keys=True`, inverser l'ordre du prompt T3, et logger
  `usage_metadata.cached_content_token_count` (actuellement absent du log `[tokens]` déjà en
  place) pour mesurer objectivement l'effet plutôt que de le déduire.
- **Gain potentiel estimé par Opus : 30-40% sur le poste d'entrée texte, zéro risque qualité**
  (aucun changement de comportement du modèle, seulement de la mise en cache).

**Aucun code écrit pour ce chantier à ce stade** — nécessite validation utilisateur avant
d'être engagé, malgré son risque nul, par respect du protocole (aucune modification
`analyzer.py` sans plan validé).

---

## Chantier A — Migration Firestore → solution auto-hébergée ("rapatriement BD")

**Motivation** : Firestore pèse ~16-20% de la facture totale (16,16$/102,57$ en août 2026),
avec une tendance à la hausse sur les lectures/écritures (+41%/+74% en septembre, cause encore
non confirmée). Coût secondaire face à Gemini API (~80-85% de la facture) mais réel.

**État** : plan sommaire déjà rédigé, aucune implémentation. Voir
[`FIRESTORE_MIGRATION_PLAN.md`](FIRESTORE_MIGRATION_PLAN.md) et `TODO.md` section
"🗄️ Migration Firestore". Bloqué sur l'accessibilité réseau du serveur existant (IP fixe/port
forwarding ou tunnel) — condition préalable à toute la faisabilité (le serveur hébergerait
bot + Postgres + API/WS + frontend, à la place de Firestore + GitHub Pages). Firebase Auth et
Storage resteraient inchangés dans tous les scénarios.

**Indépendance** : ce chantier ne touche ni à l'IA (Gemini/Claude/Qwen) ni aux photos — un
chantier d'infrastructure pur, à ne pas mélanger avec les chantiers B/C/D/F ci-dessous.

---

## Chantier B — Séparer l'analyse image de la cascade Tier 1→2→3 (éviter la répétition)

**Rappel explicite de l'utilisateur (2026-09-07)** : ce chantier existe pour éviter que
**la même analyse d'image soit répétée** à travers la cascade — à traiter comme un chantier à
part, séparé des autres pistes de coût, et **motivé aussi par des raisons autres que le coût**
(ex : cohérence de la description photo entre Tiers et avec le chat, réutilisation pour le
projet satellite `NECK_RESET_VISION_PLAN.md`, tagging de vue par photo déjà envisagé au TODO).
Ne pas réduire ce chantier à une seule optimisation financière.

**Constat architectural actuel** (`backend/analyzer.py::_run_analysis_cascade`) : les Tiers 1,
2 et 3 reçoivent tous **les mêmes photos téléchargées**, re-facturées à 3 tarifs différents à
chaque fois qu'une annonce grimpe dans la cascade :
- Tier 1 (Portier, `gemini-3.5-flash-lite`) : 0,30$/2,50$ par M tokens — tourne sur 100% des
  annonces (971/1377 sur la période, 70%, s'arrêtent ici).
- Tier 2 (Analyste, `gemini-3.7-flash`) : 0,75$/3,75$ — 342/1377 (25%) vont jusque-là.
- Tier 3 (Expert Pro, `gemini-3.1-pro-preview`) : 2,00$/12,00$ — 64/1377 (5%) vont jusque-là,
  **payant les photos une 3ᵉ fois** au tarif le plus élevé.

Avec ~900 tokens/photo et une moyenne de 3,5 photos/annonce, chaque annonce qui atteint le
Tier 3 paie ~3150 tokens-image trois fois (une fois par Tier, à 3 tarifs croissants) alors que
le contenu visuel est strictement identique d'un Tier à l'autre.

**Piste envisagée** : séparer la perception (extraction d'une description visuelle riche,
faite **une seule fois**) du raisonnement (scoring/rapport par Tier, fait sur le texte de
cette description plutôt que sur les photos brutes à chaque étage). Deux variantes possibles,
à évaluer plutôt qu'à trancher ici :
1. **Extraction interne à Gemini** : le Tier 1 (qui voit déjà toutes les photos à coût
   marginal) produit, en plus de son verdict actuel, une description textuelle détaillée
   réutilisable par T2/T3 — proche de l'idée déjà notée au TODO ("Tagging des photos par le
   Tier 1"), mais élargie à une description complète plutôt qu'un simple tag de vue.
2. **Extraction externe** (mécanisme déjà validé dans le benchmark, candidat `hybrid`) :
   un modèle moins cher (Qwen ou autre) fait l'extraction visuelle, Gemini (T2/T3) raisonne
   ensuite uniquement sur le texte — mêmes garde-fous déjà posés pour `hybrid` (pas
   d'interprétation de marque à l'étape d'extraction, laissée au raisonneur).

**Risque à vérifier avant tout code** : la même réserve que pour `gemini_pro_compact` et le
tagging Tier 1 au TODO — un modèle qui ne "voit" qu'une description textuelle (au lieu des
photos elles-mêmes) à T2/T3 pourrait perdre en capacité de vérification fine (état réel des
frettes, cohérence d'un détail douteux). Les tests de reconnaissance visuelle fine faits sur
`NECK_RESET_VISION_PLAN.md` n'étaient pas concluants sur la fiabilité d'un modèle Flash-Lite à
distinguer des vues précises — un signal de prudence direct pour ce chantier. À valider par un
comparatif qualité (score juge) avant tout déploiement, pas seulement par une projection de
coût.

**Non fait à ce stade** : aucun code écrit pour ce chantier — reste au stade d'idée à évaluer.

**Correction Opus (2026-09-07) — la prémisse coût est confirmée mais la conclusion coût est
fausse.** Chiffré sur la période réelle (1377 annonces) : la redondance T2+T3 (photos déjà
payées une fois par T1) vaut ~1,36$/9,43$, soit 14% — mais la variante 1 (T1 produit la
description) fait payer cette description en **sortie** T1 à 2,50$/M sur les 1377 annonces,
dont 70% sont rejetées et n'en feront jamais rien : ~350 tokens de description → ~1,21$, plus
la réinjection en entrée T2/T3 (~0,15$). **Net ≈ 0, voire négatif.** La variante "T2 décrit
pour T3" est pire (sortie T2 à 3,75$/M pour économiser seulement 0,40$ de redondance T3).
**Conclusion d'Opus : ce chantier ne se justifie pas par le coût** — seulement par les raisons
produit déjà citées plus haut (cohérence, tagging, réutilisation neck-reset). À traiter comme
un chantier produit, jamais comme une économie, et le signal de prudence neck-reset reste
entier (voir "Risque à vérifier" ci-dessus).

---

## Chantier C — Chat : compression bullet-point par message (nouvelle piste, 2026-09-07)

**Constat confirmé par le run #421** : le chat (`geminiChatService.js`/`useDealChat.js`) pèse
~3,5% du coût de la période observée (0,33$/9,43$) mais utilise le même modèle que le Tier 3
(`gemini-3.1-pro-preview`, 12$/M tokens de sortie) et **repaye l'historique complet à chaque
tour** — une croissance non linéaire avec le nombre de tours, contrairement à la cascade
(coût constant par annonce).

**Nouvelle idée de l'utilisateur** : compresser chaque message du chat en liste à puces (même
principe que le candidat de benchmark `gemini_pro_compact`, mais appliqué en continu à la
conversation plutôt qu'en one-shot sur un rapport), et **ne réinjecter que cette version
compressée** dans l'historique envoyé à l'appel suivant — jamais le texte intégral en prose
que l'utilisateur a lu. Concrètement : `displayText` (ce que l'utilisateur voit dans l'UI)
resterait en prose intégrale, mais la version envoyée dans `parts` lors des tours suivants
serait la forme compressée, réduisant directement le terme `cumulative_text_chars` qui domine
la croissance du coût à mesure que la conversation s'allonge.

**Points à investiguer avant tout code** (aucun codé à ce stade) :
- **Où insérer la compression** : compresser immédiatement après chaque réponse modèle (appel
  supplémentaire, modèle bon marché type `gemini-3.5-flash-lite` — coût additionnel mais
  marginal) vs. compresser à la volée uniquement au moment de reconstruire l'historique pour
  l'appel suivant (pas de coût si la conversation ne continue jamais).
- **Risque de perte de nuance** : même réserve que `gemini_pro_compact` — un historique
  compressé en puces peut faire perdre au modèle des nuances nécessaires pour répondre
  correctement à une question de suivi qui dépend d'un détail fin d'un tour précédent.
- **Interaction avec le contexte injecté** : `buildRestorationPlanContextText` (checklist de
  restauration, invisible, injecté à chaque tour utilisateur) et les refs photo
  (`attachedImagePartIndices`, élision `elideOldChatPhotos`) devront rester cohérents avec un
  historique compressé — la compression ne doit s'appliquer qu'au texte conversationnel, pas
  à ces mécanismes déjà en place.
- **Mesure attendue** : si validé, gain proportionnellement croissant avec la longueur de
  conversation (le pire cas actuel, ex. la conversation Yamaha FG-332 à ~20 tours, est
  justement celui où l'économie serait la plus visible).

**Correction Opus (2026-09-07) — le vrai piège n'est pas la perte de nuance, c'est le cache.**
Le chat ne pèse que ~2$/mois (0,33$/6 jours) — une compression à 50% ne rapporte qu'~1$/mois,
sur le code le plus délicat du dépôt. Plus important : `useDealChat.js::logTokenUsage` logue
déjà `cachedContentTokenCount`, ce qui veut dire que le chat bénéficie potentiellement du cache
implicite Gemini (préfixe identique renvoyé à chaque tour). **Si la compression est recalculée
à la volée** à chaque reconstruction d'historique, le préfixe change à chaque tour et le cache
tombe à zéro — risque réel d'**augmenter** la facture plutôt que de la réduire. Vérifier ce log
avant d'écrire une ligne de ce chantier.

**Angle mort plus rentable, identifié par Opus** : `buildRestorationPlanContextText`
(`useDealChat.js:512`) réinjecte le plan de restauration complet à **chaque tour utilisateur**,
et `elideOldChatPhotos` n'élide que les photos (`inlineData`), jamais ce bloc de texte — une
conversation à 20 tours transporte donc 20 copies du plan. Dédupliquer ce bloc spécifique est
plus simple, plus sûr (aucun risque de cache, c'est un texte fixe pas recalculé par tour) et
probablement d'un gain supérieur à la compression bullet-point générale — à traiter en premier
si ce chantier est engagé.

**Si la compression est retenue malgré tout**, la version saine est quasi gratuite : dans
`executeTurn`, `addDealChatMessage` écrit déjà le même texte dans `parts` et `displayText` —
il suffirait de demander au modèle sa version en puces **dans le même appel** (pas d'appel
supplémentaire), de persister les puces dans `parts` (réinjecté, préfixe stable) et la prose
dans `displayText` (affiché à l'utilisateur), plutôt que de recompresser après coup à chaque
lecture d'historique (`buildApiHistory`).

---

## Chantier D — Comparatif fournisseurs vision externes (harnais de benchmark)

**État** : codé sur `claude/guitarhunter-benchmark-setup-h9q9gr`
(`backend/benchmark/candidates.py`, `judge.py`, `run_benchmark.py`, `dataset.json`), **pas
encore exécuté avec de vraies clés API**. 6 candidats enregistrés :
- `gemini` (Tier 2 prod), `gemini_pro` (Tier 3, plafond qualité de référence)
- `gemini_pro_compact` (Tier 3 forcé en puces + réécriture Flash-Lite — teste ~55%
  d'économie sur la sortie T3 sans perte de raisonnement)
- `gpt4o_mini` (en réalité `gpt-5-mini`, `gpt-4o-mini` retiré de l'API OpenAI depuis
  février 2026)
- `qwen` (`qwen/qwen3.8-flash` via TokenRouter, `qwen2.5-vl-72b-instruct` n'existant plus)
- `hybrid` (un seul appel Qwen en extracteur OCR/état physique SANS interprétation de marque,
  puis Gemini Tier 3 identifie et répond à partir de ce texte seul, sans jamais voir les
  photos — conçu après que Qwen a halluciné "marque budget OEM" sur un luthier artisanal
  québécois réel en interprétant, pas en lisant, son logo)
- `claude_sonnet` (ajouté dans le cadre de ce document, voir Chantier F)

Juge : Claude (`judge.py`), score binaire contre vérité terrain de lutherie.

**Reste à faire** : lancer `python -m backend.benchmark.run_benchmark` avec les vraies clés
(`GEMINI_API_KEY`, `OPENAI_API_KEY`, `TOKENROUTER_API_KEY`, `ANTHROPIC_API_KEY`) pour obtenir
des scores comparatifs réels — aucun run réel effectué depuis l'environnement de dev.

---

## Chantier E — Pool d'annonces partagé entre utilisateurs (déprioritisé)

**État** : gain réévalué fortement à la baisse le 2026-09-06 — audit réel
(`analyze_funnel_by_user.py`, run #408) : 7 utilisateurs enregistrés, un seul représentant
94,1% du volume, un second 5,8%, le reste quasi nul. Gain maximum théorique de la
déduplication plafonné à ~5,8% des appels Gemini, et seulement si les zones géographiques des
deux utilisateurs actifs se recoupent réellement (non vérifié). Refactor architecture
significatif (migration de données, règles Firestore, `firestoreService.js`, `bot.py`) pour un
gain plafonné bas avec la base utilisateurs actuelle.

**Note de cohérence avec le run #421** : le volume total mesuré sur la période de facturation
réelle (~229 annonces/jour) est ~2,4x plus élevé que le snapshot du run #408 (95/jour, 30
jours plus tôt) — la répartition par utilisateur n'a pas été recalculée sur cette période plus
récente et à plus fort volume ; si elle a significativement changé (nouvel utilisateur actif,
recoupement géographique accru), le plafond de 5,8% mériterait d'être revérifié avant de
classer ce chantier comme définitivement secondaire.

**À reléguer** derrière les chantiers à impact plus sûr tant que la base utilisateurs reste
aussi concentrée.

---

## Chantier F — Claude Sonnet 5 vs Gemini 3.1 Pro : coût et performance (nouveau, 2026-09-07)

**Motivation de l'utilisateur** : déception croissante envers la qualité perçue de Gemini
("je ne serais pas surpris que tu sois meilleur"). Comparatif demandé à la fois sur le coût et
sur la performance réelle pour les cas d'usage Guitar Hunter (analyse d'annonce, identification
d'instrument, raisonnement sur l'état/la valeur).

**Comparatif de coût (tarifs vérifiés 2026-09-07 via le skill `claude-api`)** :

| Modèle | Input $/M | Output $/M | Contexte |
|---|---|---|---|
| `gemini-3.1-pro-preview` (Tier 3 prod actuel) | 2,00$ | 12,00$ | — |
| `claude-sonnet-5` | 2,00$ | 10,00$ | 1M |

Entrée strictement identique, sortie ~17% moins chère chez Claude Sonnet 5. Tokenisation
image chez Claude ≈ (largeur×hauteur)/750 tokens (formule Anthropic documentée) — pour une
photo d'annonce moyenne mesurée sur ce projet (~650x960px, `compare_image_resolution_by_source.py`),
≈830 tokens/photo, du même ordre de grandeur que le calibrage Gemini (~900 tokens/photo,
`run_once.py`). Les deux fournisseurs sont donc comparables sur le poste image — la différence
de coût, si elle existe en pratique, viendrait surtout de la longueur de sortie et/ou de la
qualité du raisonnement (moins de ré-analyses/corrections manuelles nécessaires).

**Codé** : candidat `claude_sonnet` ajouté à `backend/benchmark/candidates.py` (vision native,
`thinking` désactivé pour une comparaison à budget de raisonnement équivalent aux autres
candidats), enregistré dans `CANDIDATES` et dans la liste `--models` par défaut de
`run_benchmark.py`. **Pas encore exécuté.**

**Portée à clarifier avant d'aller plus loin** : ce comparatif vise le rôle Tier 3 (Expert Pro)
en premier lieu — c'est le rôle le plus coûteux et le plus qualitatif de la cascade, et celui
où la déception de l'utilisateur envers Gemini semble la plus directement pertinente. Une
bascule éventuelle du Tier 2 (volume beaucoup plus élevé, 25% des annonces contre 5% pour T3)
serait une décision distincte, à ne considérer qu'après un signal clair sur T3 — la
taxonomie/prompts/few-shot de prod sont calibrés depuis des mois sur le comportement JSON
spécifique de Gemini, un changement de fournisseur pour le Tier 2 aurait un coût de bascule
qualité à revalider entièrement (déjà noté au TODO pour GPT-5-mini/Qwen, s'applique de la même
façon à Claude).

**Correction Opus (2026-09-07) — le harnais actuel ne peut pas répondre à la question posée,
et il est structurellement biaisé en faveur de Gemini.** Six problèmes identifiés, par ordre de
gravité :
1. **n=5** dans `dataset.json` — l'intervalle de confiance à 95% sur un score binaire à n=5 est
   de l'ordre de ±40 points ; un écart de 3/5 vs 4/5 ne veut rien dire. Il faut 30-50+ items.
2. **La vérité terrain EST la sortie de production Gemini** (`dataset.json` reprend les champs
   `aiAnalysis` déjà produits par Gemini) — comparer un candidat à Gemini contre les propres
   réponses de Gemini est circulaire et pénalise mécaniquement toute formulation différente.
3. **La règle 3 du juge** (`judge.py` : score 0 si un détail de la vérité terrain est omis)
   aggrave ce biais — un candidat qui n'énonce pas les scores au format Gemini ("8/10") se fait
   sanctionner pour ne pas imiter le format, pas pour une erreur de lutherie.
4. Une question du dataset fuite indirectement la réponse attendue (prix affiché mentionné
   alors que la vérité terrain porte sur l'écart prix/valeur).
5. **Le juge est un modèle Claude qui note un candidat Claude** — même sans biais réel, un
   résultat favorable serait invendable à un utilisateur déjà sceptique sans un juge croisé
   (Gemini notant aussi) et une mesure d'accord inter-juges.
6. **Les candidats sont appelés en texte libre**, sans le `system_instruction`/contrat JSON/
   taxonomie de production — le vrai risque d'un changement de fournisseur (conformité JSON,
   dérive de taxonomie, `_canonicalize_classification` existe justement parce que Gemini dérive
   déjà) n'est pas testé du tout.

**Plus fondamentalement** : la question de l'utilisateur ("Gemini se dégrade-t-il ?") est
**longitudinale**, pas comparative — un benchmark one-shot ne peut pas y répondre, il n'y a pas
de référence antérieure. Piste alternative identifiée par Opus, gratuite et déjà en place :
tracer dans le temps le taux de correction du Portier (`initialVerdict`/`initialModelUsed`,
déjà snapshotté à la création) et le taux d'acceptation des propositions de requalification via
le chat (`requalificationProposalState === 'applied'`, déjà persisté) — si ce taux monte, la
dégradation est établie sur données de production réelles ; sinon, c'est une impression.

**Reconstruction recommandée avant de comparer Claude et Gemini** : dataset à 30-50 annonces
avec vérité terrain écrite à la main par l'utilisateur (pas reprise de Gemini), grille de score
par axe plutôt que binaire (identification, état, valeur, hallucination), candidats appelés
avec le vrai prompt/contrat JSON de production, juge croisé sur plusieurs runs.

Sur le tableau de coût brut lui-même (2,00$/10,00$ vs 2,00$/12,00$), Opus le juge exact mais
peu significatif : 17% sur la sortie d'un tier qui ne représente que 5% des annonces (T3) pèse
moins que le facteur 2,4x sur le volume (Chantier 0.a). **Le choix de modèle T3 est une
décision de qualité, pas d'économie** — à ne pas présenter comme telle.

---

## Synthèse : indépendance des chantiers

| Chantier | Touche à | Dépend de | Bloqué par |
|---|---|---|---|
| 0 — Volume + caching implicite | `analyzer.py` (2 lignes) + investigation Firestore | Rien | Validation utilisateur (risque nul mais touche `analyzer.py`) |
| A — Firestore | Infra serveur | Chantier 0.a (recadre le diagnostic) | Accessibilité réseau du serveur |
| B — Dédup image inter-Tiers | `analyzer.py`, cascade Gemini | Rien des autres (mais partage une idée avec D/hybrid) | Validation qualité (net coût ≈ 0, à ne poursuivre que pour des raisons produit) |
| C — Compression chat | `geminiChatService.js`, `useDealChat.js` | Rien des autres | Vérifier `cachedContentTokenCount` avant tout code (risque d'augmenter la facture) |
| D — Benchmark fournisseurs externes | `backend/benchmark/` uniquement (isolé de la prod) | Rien | Exécution réelle (clés API) + dataset à refaire (voir F) |
| E — Pool partagé | `firestoreService.js`, `bot.py`, règles Firestore | Chantier 0.a (le split par utilisateur date d'avant la hausse de volume) | Priorité (gain plafonné bas) |
| F — Claude vs Gemini T3 | `backend/benchmark/` (candidat) puis potentiellement `analyzer.py` si validé | D (même harnais) | Dataset/juge à refaire avant toute conclusion (voir correction Opus) |

**Ordre recommandé par Opus** : 0 (gratuit, risque nul) → D+F ensemble mais seulement après
reconstruction du dataset/juge → C réduit à la dédup du plan de restauration → B pour ses
raisons produit uniquement → A → E (parking, à revérifier après 0.a).

---

## Consultation Claude Opus (rendue le 2026-09-07)

Consultation menée en aveugle sur le code réel du projet (pas seulement ce document), avec
consigne explicite de corriger son propre biais pro-Claude sur le Chantier F. Verdict global :
le document sous-estimait deux leviers gratuits et sans risque (Chantier 0, ajouté), surestimait
le gain coût du Chantier B (net ≈ 0, corrigé ci-dessus), identifiait un vrai risque sur le
Chantier C mais pas le bon (le cache implicite, pas la perte de nuance — corrigé ci-dessus), et
jugeait le harnais du Chantier F non concluant en l'état pour la question réellement posée par
l'utilisateur (dégradation dans le temps, pas comparaison one-shot — corrigé ci-dessus). Le
détail complet (citations fichier:ligne, calculs) est intégré dans chaque section concernée
plutôt que dupliqué ici. Aucune de ces corrections n'a encore été traduite en code — chaque
chantier reste à valider individuellement avant exécution.
