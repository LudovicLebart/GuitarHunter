# Guitar Hunter — Stratégie IA

**Version :** v6 — 2026-09-28 (remplace les versions précédentes ; ajoute la base de connaissances « univers des guitares », §3)
**Principe de lecture :** chaque projet est nommé par ce qu'il fait, pas par une lettre. Les tiers gardent leurs noms habituels : **T1 = le Portier** (premier tri), **T2 = l'Analyste**, **T3 = l'Expert**.
**Matériel :** Dell T5810, RTX 2060 Super 8 Go (Turing : fp16, pas de bf16 natif). Aucun achat de GPU prévu.

---

## Objectifs

Trois objectifs de même rang :
1. **Réduire la facture.** Rien n'est insignifiant : sur une facture qui descend vers 20 $/mois, 6 $ font 30 %.
2. **Apprendre** — la lutherie (mentor, fiches instrument) et le ML (élever un petit modèle au plus haut niveau possible).
3. **Le plaisir** : optimiser, découvrir, faire beaucoup avec peu.

Contrainte transversale : **ne perdre aucune pépite de plus qu'aujourd'hui.** Tout changement est mesuré avant bascule.

---

## La facture

| Étape | Facture/mois | Statut |
|---|---|---|
| Point de départ (Portier ≈ 60 %, Firestore ≈ 20 %) | 100 $ | — |
| Firestore → Postgres local | −20 $ | **fait** |
| Portier Gemini → Qwen cloud (−50 %) | −30 $ | **fait** (20/09) |
| **Aujourd'hui** | **≈ 50 $** | |
| Portier Qwen cloud → Qwen local | −30 $ | **validé en test** (27–28/09), bascule à préparer |
| **Cible intermédiaire** | **≈ 20 $** | |
| Analyste (T2) en local, partiellement ou totalement | jusqu'à −6 $ | projet de recherche |

À confirmer par le tableau de bord : la part réelle du Portier (le journal d'août disait ~34 % de la part Gemini, pas 60 % de la facture), et les postes encore non ventilés (chat, Expert).

Coût caché à surveiller : le Portier local accepte plus d'annonces que le cloud (40 % contre 32 % contre Qwen cloud ; 52 % contre 48 % contre Flash-Lite). Soit +10 à +25 % d'appels à l'Analyste, environ +0,6 à +1,5 $/mois. Ne remet pas en cause la bascule, mais rogne le gain.

---

## 1. Mesurer les coûts

### 1.1 Instrumentation par modèle et par action
- Table Postgres **`llm_usage`** : une ligne par appel LLM, bot **et** chat (modèle, action, annonce, photos, tokens d'entrée / en cache / de sortie / de raisonnement, latence).
- Actions du bot : `t1_gatekeeper`, `t1_shadow`, `t2_analyst`, `t3_expert`, `t2_backfill_light`, `audit_t2`. Actions du chat : `chat_turn`, `chat_photo_recall_replay`, `chat_followup_*`.
- **Correctif du 28/09 (`llm_usage_failures.patch`)** : jusqu'ici seuls les succès étaient enregistrés, donc `ok` était toujours vrai et le taux d'échec invisible. Désormais :
  - chaque échec produit une ligne `ok=false` avec **`error_type`** : `timeout`, `connection`, `model_unavailable` (modèle retiré, ajouté à l'intégration), `http`, `json`, `no_key`, `other` ;
  - le succès est enregistré **après** la lecture du JSON (un appel qui répond mais produit un JSON invalide, comme la boucle de répétition du local, compte comme un échec `json`, avec ses tokens puisqu'ils ont été consommés) ;
  - une ligne par tentative Gemini (chaque tentative est facturée) ;
  - le fournisseur local est étiqueté **`local`** (décision utilisateur à l'intégration, 2026-09-29 — et non `ollama` comme dans le patch d'origine) ;
  - **Intégré le 2026-09-29** (`4ac0ade`), fusionné avec le chantier T1 : l'enregistrement se fait dans les fonctions d'appel, plus au niveau de la chaîne (évite le double comptage).
- **Tableau de bord** (`cost_dashboard.py --from-db`) : détail modèle × action avec taux d'échec, types d'échec, latence P90 et coût mensuel ; `--by-deal N` pour les annonces les plus chères ; `--billing-csv` pour confronter à la facture réelle.

À vérifier avant de croire les coûts : tarifs de la table `PRICING` (surtout TokenRouter), remise du cache implicite Gemini.
Limite : « Demander conseil » et « Faire le point » apparaissent comme `chat_turn`.

### 1.2 Réductions à attaquer selon ce que montrera le tableau de bord
- **Chat** : photos à 1024 px, résumé glissant de l'historique au-delà de N tours, modèle bon marché par défaut et Pro à la demande.
- **Miroir Flash-Lite** : **fait**, `T1_OBSERVATION_ENABLED` désactivé par défaut le 28/09.
- **Expert (T3)** : vérifier combien de ses verdicts changent la décision finale ; mesurer la part de raisonnement dans sa sortie et régler `thinking_budget` si elle domine ; tester la sortie compacte réécrite par un modèle léger.

### 1.3 Écarté
Cache explicite Gemini (ROI négatif mesuré) ; « langage machine » ultra-compressé (un modèle facture des tokens, pas des caractères).

---

## 2. Le Portier en local

### 2.1 Résultats (branche `claude/qwen-gatekeeper-local-test-43pny7`)
- **Cause racine des premiers mauvais résultats** : le tag Ollama `qwen3-vl:8b` pointe vers la variante *Thinking*. Avec **`qwen3-vl:8b-instruct`** (même VRAM, ~7 Go) :
- **Contre Qwen cloud (n=142)** : accord 76,8 %, cas coûteux (le cloud accepte, le local rejette) 7,7 %, JSON valide 99,3 %, latence P90 **9,1 s contre 52 s** pour le cloud.
- **Contre Flash-Lite, l'étalon qui a validé la bascule de prod (n=117)** : accord 70,1 %, cas coûteux **12,8 %, identique à la référence acceptée**.
- Relecture des cas coûteux : la plupart sont un jugement plus sévère sur l'authenticité (logo incohérent avec la marque annoncée), 3 sont un ancien bug de scraping correctement signalé, 2–3 seulement sont de vraies confusions.
- **Fiabilité réelle de Qwen cloud** : 13 % d'échec en temps normal, 25 % avec les pannes des 23 et 25/09.

Conclusion : le local n'est plus seulement un secours, il devient **le Portier principal**, le cloud passant en secours.

### 2.2 Le prompt simplifié devient le prompt de prod du Portier
**État (2026-09-29) : EN PROD pour tous les fournisseurs** (`backend/t1_prompt.py`, source unique), sur décision utilisateur. **Le rejeu de non-régression décrit ci-dessous sur Qwen cloud et Flash-Lite n'a PAS été fait** (validé seulement sur le local, n=665) : à faire pour confirmer que les secours ne sont pas dégradés.
Les bons résultats ont été obtenus avec un prompt simplifié (moins de raisonnement demandé, sans les exemples conçus pour de gros modèles). Il doit devenir **le prompt du Portier pour tous les fournisseurs**, local et secours, pour que tout le monde juge avec les mêmes règles.
Condition avant bascule : rejouer ce prompt sur **Qwen cloud et Gemini Flash-Lite** (les secours) sur ~150 annonces, pour vérifier qu'il ne les dégrade pas. Coût de l'ordre de 0,50 $. Bonus probable : un prompt plus court coûte moins cher quand le secours sert.

### 2.3 Corriger le biais d'authenticité
Une incohérence entre le logo et la marque annoncée ne doit pas faire **rejeter** : un vendeur qui ne sait pas ce qu'il a est la source classique d'une bonne affaire (cas Yamaha Eterna). Consigne à ajouter au prompt : *incohérence de marque → ACCEPT avec signalement*, l'Analyste tranche.
Avant d'écrire la consigne : relire les ~10 cas concernés avec une seule question, « si c'était vrai, serait-ce une affaire ? ».
Preuve supplémentaire (rejeux du 2026-10-01) : la Jay Turser (logo Fender) et l'Olympia by Tacoma (logo Oscar Schmidt) étaient rejetées à chaque rejeu, avec ou sans base de connaissances, alors que leur verdict final était `FAIR` / `LUTHIER_PROJ`. C'est la piste la plus solide pour améliorer le Portier.
**MISE À JOUR (2026-10-02, soir) : la cause racine était la troncature du prompt, pas le prompt.** Le contexte Ollama du Dell était plafonné à 4096 tokens (l'option `num_ctx` via l'API `/v1` n'est pas honorée) : dès 4 photos le prompt était tronqué, et l'instruction du Portier perdue à 6-8 photos. Avec `OLLAMA_CONTEXT_LENGTH=8192` (service du Dell), les rejets absurdes disparaissent (0/25 contre ~10 %), le JSON invalide passe de 12,5 % à 1,3 %, au prix d'une latence ×2 (26 % du modèle sur CPU). Les tests de prompt ci-dessous sont à REFAIRE à 8192. Voir `JOURNAL.md`.
**Résultat du test (2026-10-02) : aucun gain démontré, consigne NON ajoutée (mesure faite avec un prompt tronqué).** Une variante d'une phrase (la contradiction est signalée, jamais un motif de rejet) rejoue 25 faux rejets connus sans écart au-delà du bruit du modèle (6/25 décisions changent entre deux passes identiques). Olympia est déjà acceptée sans base ; seuls Jay Turser et une Cort étaient rejetés pour cause de marque. Le problème dominant est un taux de rejets absurdes aléatoires du petit modèle, que la règle ne traite pas. Attention : l'instruction RÉELLEMENT active en prod est la surcharge `analysisConfig` de l'utilisateur (périmée : sans `FAIR`, sans « déjà vendu »), pas `prompts.json`. Voir `JOURNAL.md` 2026-10-02.

### 2.4 Chaîne de repli et fiabilité (recommandations Opus, validées)
1. **Instrumenter les échecs** — **fait** (livraison du 28/09 intégrée le 2026-09-29).
2. **`T1_PROVIDER_CHAIN`** : liste ordonnée configurable (`local,qwen,gemini`) remplaçant le fournisseur unique ; timeouts propres par fournisseur. **Fait** (défaut `local,qwen` depuis le 2026-09-29, en prod) ; timeouts propres par fournisseur non faits (60 s communs).
3. **Coupe-circuit en mémoire** : 3 échecs consécutifs → pause 5–10 min → un appel test pour réactiver. Les échecs `json` isolés (boucle de répétition) déclenchent un repli immédiat sur le fournisseur suivant sans compter comme panne. **Fait, sauf la dernière phrase** : le repli est immédiat, mais tout échec (`json` compris) compte dans le coupe-circuit — décision du 2026-09-29 de ne pas changer avant d'avoir une semaine de données `error_type`.
4. **Champ `gatekeeperProvider` par annonce** : savoir qui a vraiment décidé, pour attribuer une dérive. **Pas encore fait** (seul `llm_usage` dit qui a répondu).
5. **Fiabiliser le Dell** : Ollama en systemd, redémarrage automatique après coupure ou mise à jour, clés Tailscale sans expiration, `OLLAMA_KEEP_ALIVE` long contre les rechargements à froid.
6. **Concurrence** : un seul 8B tient en VRAM, Ollama sérialise les requêtes. Sans gravité avec 1 à 3 utilisateurs ; au-delà, traiter « file trop longue » comme une panne et passer au cloud.
7. **Suivi hebdomadaire** après bascule : taux de rejet par fournisseur, surveillance des marques obscures rejetées à tort.

Avec deux fournisseurs aux modes de panne complémentaires (le cloud échoue souvent un peu, le local rarement mais d'un bloc), le taux d'échec combiné devrait tomber sous 1 %.

---

## 3. La base de connaissances « univers des guitares »

### 3.1 Pourquoi, et pourquoi maintenant
Les erreurs résiduelles du Portier local viennent en partie d'un manque de culture : marques obscures rejetées (Yamaha Eterna), marque hallucinée (« FISHING GHOST » pour Squier), incertitude sur ce qui vaut la peine. Une base de connaissances injectée au bon moment corrige ça directement.
- **Les essais sont gratuits** : avec le Portier local, chaque version de la base se valide en rejouant les annonces de test sans aucun coût.
- **C'est une fondation partagée** : la même base servira l'Analyste, la normalisation des marques pour les comparables (§6), le mentor et les fiches instrument (§7).
- **Elle démarre maintenant et s'enrichit au fil de l'eau**, sans rien casser, grâce aux versions et au test de non-régression (§3.6).

Ce qu'elle ne corrige pas : la sévérité sur l'authenticité (~10 des 15 cas coûteux), qui relève d'une règle de jugement (§2.3). Les deux sont complémentaires.

### 3.2 Une base, deux portes d'entrée
- **Porte principale, par le nom** (`backend/guitar_knowledge.py`, livré) : on cherche dans le titre, la description et le texte lu sur les photos les alias connus des fiches, avec une tolérance légère aux fautes (« Fendr Stratocster » → Fender Stratocaster). Précis, déterministe, sans homonyme hors sujet. Les séries passent avant les marques (plus spécifiques), les fiches relues passent avant les autres.
- **Porte secondaire, par le sens** (embeddings bge-m3 + pgvector, plus tard) : seulement quand aucun nom n'a été trouvé (« vieille guitare japonaise, tête en forme de… ») ou pour ramener des passages riches (histoire d'une série, défauts connus). Peu utile au Portier, essentielle pour l'Analyste et le mentor.

Pourquoi la porte par le nom d'abord : un petit modèle croit ce qu'on lui injecte. Une fiche hors sujet (un homonyme, une marque de montres « Eterna ») est pire que pas de fiche du tout.

### 3.3 Ce que contient une fiche
Tables Postgres (ajoutées à `schema.sql`, créées au démarrage) :
- **`guitar_knowledge`** : une fiche par entité, de nature `company` (fabricant), `brand` (marque ou sous-marque), `line` (série de modèles : Stratocaster, Eterna, FG…), `factory` (usine : Matsumoku, FujiGen…) ou `luthier`. Champs : nom, description, maison mère ou fabricant, pays, années d'activité, pertinence (`guitars` / `accessories` / `unknown`), liens Wikidata et Wikipédia.
- **`guitar_knowledge_alias`** : tous les noms sous lesquels on peut la rencontrer (libellés multilingues, alias Wikidata, titres Wikipédia, noms sans suffixe « Guitars » / « Inc. », série sans le nom de la marque : « Eterna » pour « Yamaha Eterna »).
- **`guitar_knowledge_versions`** : l'historique des versions de la base, avec un drapeau `validated`.

Deux familles de colonnes qui ne se mélangent jamais :
- **importées** (réécrites à chaque import) : nom, description, parent, pays, années, pertinence, alias de source Wikidata/Wikipédia ;
- **curées par toi** (jamais touchées par l'import) : `tier` (entrée, milieu, haut, boutique), `hunt_notes` (séries recherchées, pièges, repères de datation), `made_by` (usines), `curated`, alias ajoutés à la main. C'est là qu'entre ta connaissance de lutherie. Vérifié en test : un réimport conserve intégralement ces champs.

### 3.4 Sources, par ordre d'intérêt
1. **Catégorie Wikipédia des fabricants de guitares**, dans une vingtaine de langues (en, fr, ja, de, es, it par défaut), sous-catégories par pays comprises. Route principale : Wikidata type les fabricants de façon incohérente (Music Man = « marque déposée », ESP = « entreprise »), une requête par type en raterait beaucoup.
2. **Wikidata** : fabricants dont le produit est une guitare ou une basse ; un saut vers leurs marques et filiales (Squier depuis Fender, Epiphone depuis Gibson) ; leurs séries de modèles. Licence CC0.
3. **Curation manuelle prioritaire** : les usines et marques japonaises des années 60 à 80 (Matsumoku, FujiGen, Teisco, Guyatone et les marques qu'elles fabriquaient), les séries recherchées, les pièges connus. C'est là que se cachent des pépites sous des noms obscurs.
4. **Guides et catalogues sous droits** (Gruhn, Blue Book, livres personnels) : usage personnel pour alimenter `hunt_notes`, jamais de copie en masse ni de redistribution.

Le scraping de tes propres annonces n'est **pas** une source de la base : il sert seulement à mesurer la couverture (§3.7).

### 3.5 Règles d'usage au Portier
- **Reconnaître, jamais condamner.** Les rejets par marque restent l'affaire de la liste noire explicite que tu contrôles ; la base ne doit pas ajouter de rejets implicites.
- **Injection courte** : au plus 3 fiches trouvées, formatées par `format_for_prompt()` (quelques centaines de tokens), précédées de la consigne « à utiliser pour reconnaître, jamais pour rejeter ».
- **Traçabilité** : enregistrer avec chaque décision du Portier la version de la base utilisée et les fiches injectées, pour pouvoir attribuer un changement de comportement.
- **Seule une version validée** (`validated = true`) est utilisée en prod.

### 3.6 Versions et non-régression
Chaque import ou lot de curation crée une nouvelle version, **non validée**. Avant de l'activer :
1. rejouer les annonces de référence (les 142 et 117 déjà utilisées) avec le Portier local, base activée ;
2. comparer aux résultats de la version précédente : cas coûteux, marques obscures désormais reconnues, nouveaux rejets éventuels (doivent être nuls) ;
3. si c'est au moins aussi bon : `UPDATE guitar_knowledge_versions SET validated = true WHERE version = N`.
Coût : 0 $, seulement du temps de calcul sur le Dell.

### 3.7 Étapes
| Étape | Contenu | Coût |
|---|---|---|
| 1. Premier import | `import_guitar_knowledge_wikidata.py --dry-run --json-out kb_preview.json`, relecture rapide de l'aperçu, puis import réel → version 1. | 0 $ |
| 2. Couverture | Croiser les marques des ~7 000 annonces analysées avec la base : lesquelles ne sont pas reconnues ? En sortir la liste à ajouter à la main. (Script à écrire.) | 0 $ |
| 3. Curation prioritaire | Usines japonaises, séries recherchées, marques fréquentes chez toi. Pré-remplissage possible par un modèle bon marché (quelques centimes), **toujours relu par toi**. | ~0 $ |
| 4. Branchement au Portier | Recherche avant l'appel, injection des fiches, traçabilité de la version. Derrière un interrupteur de configuration. | 0 $ |
| 5. Non-régression | Rejeu 142 + 117 en local, validation de la version. | 0 $ |
| 6. Extension | Analyste (même injection), normalisation des marques pour les comparables, porte par le sens (pgvector) pour l'Analyste et le mentor. | 0 $ |

### 3.8 Mesures
- **Couverture** : part des annonces où au moins une fiche est trouvée.
- **Justesse** : sur 50 correspondances tirées au hasard, part de fiches correctes (cible ≥ 95 % ; une fiche fausse coûte plus qu'une fiche manquante).
- **Effet sur le Portier** : cas coûteux et marques obscures sur les rejeux de référence, avant/après.

### 3.8 bis État réel et résultat de la mesure (2026-10-01)
- **Faits** : étapes 1 à 4 (import 878 fiches, 14 entrées manuelles sourcées, script de couverture, branchement derrière `T1_KNOWLEDGE_ENABLED`, éteint) et l'outillage de l'étape 5 (`compare_knowledge_effect.py`, rejeu `--with-knowledge`). La version 1 n'est **pas validée**.
- **Résultat de l'étape 5, honnête** : **aucun gain démontré**. Le rejeu sur les 142 + 117 n'a pas été refait tel quel ; la mesure a porté sur (a) un lot récent de 99 annonces (bruit du modèle 11/98 entre deux rejeux identiques, accord cloud 83,3 % → 90,5 % sur n=42, non concluant) et (b) 18 « faux rejets présumés » (rejetés par T1 puis reclassés, trace dans `initial_verdict`) : le Portier actuel en accepte déjà 14 sans base, effet net nul avec base. Les rejets restants viennent de réponses absurdes du modèle local et du biais « logo différent de la marque », pas d'un manque de connaissance.
- **Limite de la mesure** : on ne peut pas mesurer les faux rejets du Portier en général (une annonce rejetée ne passe pas au palier suivant) ; seuls les cas reclassés après analyse forcée ou chat servent de vérité terrain, et ils sont peu nombreux (26 au départ, 18 après retrait des étuis/amplis). Un `BAD_DEAL` d'origine peut provenir de l'ancien pré-filtre de prix.
- **Rejeu à température 0 + graine 42 (exécuté, même jour)** : bruit entre deux rejeux sans base 4/18 → **1/18** (l'échantillonnage causait l'essentiel du bruit ; Ollama/GPU reste non parfaitement reproductible). Sur 18 comparables / 16 injectés : 2 rejets nuisibles (Olympia by Tacoma — biais du logo ; Yamaha ERG121 — sortie absurde, fiche Yamaha vide) pour 2 vrais gains, accord 81,2 % → 81,2 %, seuil toléré 0 → **critère non tenu**. La mesure est désormais lisible mais ne montre toujours rien en faveur de la base : elle reste un outil d'audit, pas un composant du Portier.
- **Suite** : pistes plus prometteuses pour le Portier : §2.3 (consigne « incohérence de marque → accepter avec signalement », qui vise directement Olympia et Jay Turser, encore rejetés dans ce rejeu), second avis sur les rejets absurdes, fixer la température en prod, `gatekeeperProvider`. Toute nouvelle mesure doit se faire à température 0 + graine fixe.

### 3.9 Risques
| Risque | Parade |
|---|---|
| Homonymes et alias trop courts (« Aria », « Bass ») | Pas de fuzzy sous 5 caractères, liste de mots trop génériques ignorés, séries avant marques, curation des alias ambigus. |
| Fabricants d'accessoires (Kluson, cordes, micros) | Marqués `accessories` à l'import, jamais injectés. Vérifié en test. |
| Qualité inégale de Wikidata | Colonnes curées prioritaires, relecture de l'aperçu, mesure de justesse. |
| Dérive du Portier à chaque enrichissement | Versions + rejeu de non-régression obligatoire. |
| Politesse envers Wikimedia | User-Agent descriptif (renseigner `KB_CONTACT`), requêtes groupées, pauses, respect du Retry-After. |

---

## 4. Les yeux : décrire les photos en local

### 4.1 Principe
Faire décrire les photos par le Qwen local, en texte, pour que les modèles payants n'aient plus à les voir. Base indispensable du projet de recherche (§5).

### 4.2 Architecture par crops
1. **Détecteur de parties** (projet en cours, plan : [`PARTS_DETECTOR_AND_CROPS_PLAN.md`](PARTS_DETECTOR_AND_CROPS_PLAN.md)) : tête, manche, talon, corps, chevalet, sillet de chevalet, sillet de tête, rosace, micros, plaque/étiquette de série (10 classes figées le 2026-10-02). Les détecteurs zéro-shot (OWLv2, SAM, Gemini) ont été essayés et ne suffisent pas : d'où 150 images annotées à la main pour l'amorçage.
2. **Qwen-VL local** : décrit chaque crop **sans interpréter** (transcrire un logo, jamais « c'est une Gibson »), plus une vue d'ensemble.
3. **Repli photo entière** quand la détection est faible (instruments atypiques, luthiers, pièces abîmées).
4. **Perception à la demande** : le modèle qui raisonne pose des questions ciblées au modèle local (« photo 3 : fissure près du chevalet ? »), comme `request_photo_review` dans le chat.

Ce que les crops apportent : l'attention (le modèle sait où regarder), la résolution utile (pixels d'origine de la zone), moins de VRAM que 8 photos pleines, une requête juste pour la base de connaissances.
Ce qu'ils n'apportent pas : du détail absent d'une photo compressée, une vue que le vendeur n'a pas prise. **Ces limites valent aussi pour Gemini**, qui reçoit en plus la photo entière réduite ; sur les détails d'état, un petit modèle avec crops peut l'égaler ou le dépasser.

Décision utilisateur actée : **ne pas réduire la résolution ni le nombre d'images** pour gagner de la marge de contexte ; préserver le signal visuel.

### 4.3 Contrat de description (à figer)
Par image : `vue`, `qualite`, `texte_lu` (transcription exacte + confiance), `formes`, `materiel_visible`, `finition`, `etat` (observation, gravité visuelle, zone), `non_visible`. Enums fermés, schéma JSON strict.

---

## 5. Projet de recherche : un petit modèle pour l'Analyste (T2)

### 5.1 Pourquoi c'est faisable sur 8 Go
Ce qui empêche d'entraîner l'Analyste en local, ce sont les **images** (≥ 10–12 Go à l'entraînement). Avec les yeux (§4) et les comparables (§6), l'Analyste devient un **modèle texte** : annonce + description des crops + comparables → classification, scores, verdict.
- **Modèle texte 4B, QLoRA sur le Dell** : de l'ordre de 6–7 Go (à vérifier au premier run), une nuit par run, gratuit.
- **8B** : inférence sur le Dell ; entraînement sur GPU loué (quelques dollars) si le 4B plafonne.
- Encouragement : un 8B Instruct tient déjà le Portier en zero-shot ; la base de départ est plus solide que prévu.

### 5.2 Les données
- Rejouer l'Analyste ou l'Expert sur des milliers d'annonces n'est pas raisonnable (45–75 $ avec Flash, 225–375 $ avec Pro).
- **Croissance organique** : ~11 verdicts de l'Analyste par jour, ~330 par mois, déjà payés ; enrichis par tes confirmations (favoris, achats, repromotions) et les accords Analyste/Expert. Projet sur 6 à 12 mois.
- **À faire dès maintenant** : stocker chaque verdict de l'Analyste **avec son entrée complète** (description des photos, comparables), pour qu'il devienne un exemple d'entraînement sans surcoût.

### 5.3 La question centrale : le texte suffira-t-il ?
- **Tient bien** : rejeter un étui ou un accessoire, identifier quand le titre ou le logo lisible nomment l'instrument, l'état décrit par le vendeur.
- **À risque** : titres vagues où seule la tête révèle la marque ; défauts tus par le vendeur ; détails qui datent un modèle ; l'impression « copie » ; les modèles rares.

### 5.4 Étapes
1. **Étude de dépendance visuelle** (`study_visual_dependence.py`, 0 $) : compare ce que l'Analyste dit avoir vu au texte de l'annonce ; sépare état et identification ; ventile par verdict et **par partie de guitare** ; exporte 150 annonces stratifiées. Borne basse ; relire les exemples.
2. **Rejeu en texte seul** (~2 $) sur ces 150 : description par le Qwen local, Analyste rejoué sans photos. Classer chaque désaccord : information absente de la description (→ améliorer les yeux) ou mal interprétée (→ le modèle qui raisonne).
3. **Point de départ sans entraînement** du modèle texte local (4B et 8B), même entrée.
4. **Entraînement 4B sur le Dell**. Professeur = verdict final de la cascade + tes confirmations, jamais le Portier seul.
5. **8B sur GPU loué** si le 4B plafonne.
6. **Observation** 2 semaines : le modèle local juge en parallèle, sans décider.
7. **Routage** : le local décide quand il est confiant et que les parties ont été détectées ; le cloud garde le reste. Viser 70–80 % du volume.

Critère à chaque étape : zéro pépite perdue de plus que l'Analyste actuel ; 3 tirages sur les cas proches du seuil (non-déterminisme mesuré).

### 5.5 Ce qui restera au cloud
Culture des modèles rares, instruments atypiques où le détecteur échoue, jugement d'ensemble. Cas rares, souvent des pépites.

---

## 6. La valorisation par comparables

### 6.1 Principe
L'Analyste ne devine plus le marché de mémoire : on lui fournit **8 annonces comparables** avant l'appel, il estime en s'y ancrant et dit quand elles manquent (`valuation_basis`). Rend un Analyste moins cher, ou local, beaucoup moins risqué, et stabilise les estimations d'un appel à l'autre.

### 6.2 Recherche hybride
SQL pour l'exact (même famille, 18 mois, CAD, doublons exclus) ; embeddings bge-m3 sur CPU pour rapprocher les titres mal écrits ; re-classement par similarité, récence et état ; stockage **pgvector** dans le Postgres local.

### 6.3 Sources
1. **Toutes les annonces scannées** (~7 000, prix demandé), sans s'appuyer sur les dates de vente (peu fiables).
2. **Sources externes pour le haut de gamme** (> 400 $) : Reverb, détaillants canadiens, eBay terminées, après lecture de leurs conditions d'utilisation, ingestion hebdomadaire.
3. **Fiches de référence par modèle**, partagées avec le mentor.

### 6.4 Étapes
Carte de couverture (0 $) → index et recherche → rejeu de l'Analyste avec/sans comparables → sources externes → bascule.

### 6.5 Choix du fournisseur de l'Analyste avant le 1er janvier 2027
Gemini 3.7 Flash double de prix (1,50/7,50 $/M). Candidats évalués dans le rejeu, même entrée : Qwen3.8 Flash, Qwen3.7 Plus, un petit modèle OpenAI (vision à confirmer), Mistral Small 4. Critère secondaire : un fournisseur différent de celui du Portier, Gemini en repli.

---

## 7. Le mentor lutherie

### 7.1 Principe
Le chat de chaque annonce devient un mentor de réparation et d'histoire de l'instrument, **sourcé**. On n'envoie pas la bibliothèque : l'index local renvoie les 5–6 extraits pertinents (~un demi-cent par question), avec la consigne de citer et de dire quand les sources ne couvrent pas. Reste sur un modèle frontière : un apprenti sans professeur a besoin du raisonneur le plus fiable.

### 7.2 Corpus
frets.com, StewMac, manuels et specs constructeurs, livres personnels scannés (usage privé), Wikidata, **fiches de sécurité** rédigées à la main (truss rod, colles et chaleur, ponçage, nitro) toujours injectées sur un geste irréversible, et tes plans de restauration terminés.

### 7.3 Étapes
Prototype en ligne de commande (20 vraies questions) → intégration au chat → « Demander conseil » / « Faire le point » augmentés → **fiche instrument** générée une fois à l'achat.

### 7.4 Coût assumé
Le mentor ajoute des tokens au chat ; il se paie par l'apprentissage. À construire sur le chat déjà allégé.

---

## 8. Prochaines actions, dans l'ordre

1. ~~**Appliquer la livraison**~~ — **fait le 2026-09-29** (intégrée avec le chantier T1, revue de code corrigée, poussée sur `dev`). Reste : premier `--dry-run` de l'import sur le serveur.
2. **Tableau de bord** après une semaine : part réelle du Portier, chat, Expert, échecs par fournisseur.
3. **Portier local** (chaîne, coupe-circuit, prompt simplifié, bascule : **faits le 2026-09-29** ; restent le rejeu sur les secours, la consigne « incohérence de marque » et le durcissement du Dell) : rejouer le prompt simplifié sur les secours (~0,50 $), relire les cas « incohérence de marque » et ajouter la consigne, chaîne de repli et coupe-circuit, fiabiliser le Dell, basculer.
4. ~~**Base de connaissances**~~ — **fait et mesuré le 2026-10-01, fusionnée dans `dev` le 2026-10-02 : aucun gain démontré pour le Portier** (878 fiches + 14 curées, interrupteur `T1_KNOWLEDGE_ENABLED` éteint, version 1 non validée ; rejeu à température 0 : 2 rejets nuisibles contre 2 gains, accord 81,2 % → 81,2 %). Les rejets restants viennent de réponses absurdes du modèle et du biais « logo ≠ marque annoncée », pas d'un manque de culture. La base reste un outil d'audit et une fondation pour l'Analyste, les comparables et le mentor (§6-7), à réévaluer là, pas au Portier. Voir `JOURNAL.md` 2026-10-01.
5. **Étude de dépendance visuelle** (0 $), puis **rejeu en texte seul** (~2 $).
6. **Stocker l'entrée complète de chaque verdict de l'Analyste** (dataset du projet de recherche).
7. Selon le tableau de bord : chat, Expert.
8. **Comparables** : carte de couverture, puis rejeu avant fin 2026 pour choisir le fournisseur de l'Analyste.
9. **Mentor** dès que la porte par le sens de la base existe.

---

## 9. Livrables produits
- `livraison.patch` — un seul patch sur `dev`, qui regroupe :
  - l'enregistrement des échecs dans `llm_usage` (`ok=false`, `error_type`, succès enregistré après lecture du JSON, une ligne par tentative Gemini, étiquette `ollama`) ;
  - les tables `guitar_knowledge*` dans `schema.sql` ;
  - `backend/guitar_knowledge.py` — recherche par le nom (exacte + fautes de frappe) et mise en forme pour le prompt ;
  - `backend/scripts/import_guitar_knowledge_wikidata.py` — import Wikipédia + Wikidata, versionné, qui ne touche jamais aux champs curés ; `--dry-run`, `--json-out`, `--lookup` pour tester.
  Testé contre un vrai Postgres avec des réponses Wikimedia simulées (pas d'accès réseau à Wikimedia depuis l'environnement de test : le premier vrai import est à faire chez toi en `--dry-run`).
- `cost_dashboard.py` — tableau de bord : coûts, taux d'échec, types d'échec, latence P90.
- `study_visual_dependence.py` — étude de dépendance visuelle, échantillon stratifié pour le rejeu en texte seul.
- `llm_usage_tracking.patch` — instrumentation initiale (déjà intégrée à `dev`).
