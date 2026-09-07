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
9,76$ réels). Ce qui semblait un mystère de coût par annonce était en réalité un problème de
**volume mal calibré** (95 annonces/jour mesurées 30 jours plus tôt vs ~229/jour sur la
période réelle facturée) — le modèle de coût par annonce était juste depuis le début. Cette
clôture ouvre la voie à des chantiers d'optimisation ciblés plutôt qu'à une chasse au fantôme.

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

---

## Synthèse : indépendance des chantiers

| Chantier | Touche à | Dépend de | Bloqué par |
|---|---|---|---|
| A — Firestore | Infra serveur | Rien des autres | Accessibilité réseau du serveur |
| B — Dédup image inter-Tiers | `analyzer.py`, cascade Gemini | Rien des autres (mais partage une idée avec D/hybrid) | Validation qualité (risque de perte de nuance) |
| C — Compression chat | `geminiChatService.js`, `useDealChat.js` | Rien des autres | Validation qualité (risque de perte de nuance) |
| D — Benchmark fournisseurs externes | `backend/benchmark/` uniquement (isolé de la prod) | Rien | Exécution réelle (clés API) |
| E — Pool partagé | `firestoreService.js`, `bot.py`, règles Firestore | Rien | Priorité (gain plafonné bas) |
| F — Claude vs Gemini T3 | `backend/benchmark/` (candidat) puis potentiellement `analyzer.py` si validé | D (même harnais) | Exécution réelle (clés API) |

Aucun chantier n'en bloque un autre — ils peuvent être décidés et exécutés dans n'importe quel
ordre, chacun avec sa propre validation.

---

## Consultation Claude Opus

Ce document a été soumis à Claude Opus pour un second avis avant toute priorisation — voir
l'entrée correspondante dans `JOURNAL.md` (2026-09-07) pour sa réponse.
