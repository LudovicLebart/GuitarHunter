# Base de connaissances « univers des guitares » et fiches techniques (référence)

> Vérifié le 2026-11-05 contre le commit `c5a5f05` : `backend/guitar_knowledge.py` (770 lignes), `backend/api/fiches_repo.py`, les routes `/fiches` de `backend/api/main.py`, `backend/scripts/seed_guitar_knowledge.py`, `seed_guitar_fiches.py`, `import_guitar_knowledge_wikidata.py`, `knowledge_review_apply.py`, `docs/fiches/`, `schema.sql`, et l'**état réel de la base du serveur** (lecture seule, 2026-11-05). La stratégie, la mesure d'effet sur le Portier et les décisions sont dans `plans/STRATEGIE_IA.md` §3 ; le guide pratique des fiches dans `how-to/FICHES_TECHNIQUES.md`. Les tables sont décrites dans `donnees.md`.

## Rôle

Une **base commune** de deux familles de contenus qui partagent les mêmes tables (alias, sources, calcul de confiance) mais jamais leurs lectures :
- **Marques** (`kind` ∈ `company`, `brand`, `line`, `factory`, `luthier`) : pour *reconnaître* une marque, une série ou une usine citée dans une annonce ; destinées au Portier (option éteinte) et à l'outil `lookup_brand` de l'Expert (option éteinte).
- **Fiches techniques de restauration** (`kind = 'fiche'`, id `fiche:<slug>`) : procédures de réparation consultables sur le site, liées aux étapes du plan de restauration et citées par le chat.

Règle d'usage de la base de marques : elle sert à **reconnaître**, jamais à rejeter ; les rejets par marque restent la liste noire explicite de l'utilisateur.

## État réel au 2026-11-05 (base du serveur)

| Contenu | Nombre | Détail |
|---|---|---|
| `line` (séries) | 406 | 393 approuvées à la relecture, 2 rejetées, 7 curées |
| `company` | 326 | 278 approuvées, 29 rejetées, 14 curées |
| `luthier` | 108 | 26 approuvés, 78 rejetés, aucun curé |
| `brand` | 61 | 34 approuvées, 3 rejetées, 25 curées, 22 écrites à la main |
| `fiche` | 14 | 13 `brouillon`, 1 `en_revision`, aucune `validee` |
| Alias / sources | 2 236 / 184 | |
| Confiance (hors fiches) | 22 `sourced`, 879 sans valeur | aucune à source unique ; les 879 sans valeur sont les entités de l'import Wikidata ou sans calcul de confiance (colonne nulle) |
| **Versions de la base** | **12, aucune validée** | version 1 : import Wikidata (2026-09-30) ; versions 2 à 12 : amorçages manuels (2026-10-06 à 2026-10-15) |

**Origine des 731 approbations** (note de relecture) : 447 par règles automatiques sans IA (`knowledge_triage.py apply`), 235 par Claude avec ses connaissances (`knowledge_ai_review.py apply`, relecture du 2026-10-15), 49 par une note individuelle. Les 112 rejets portent tous une note individuelle (par exemple « personne (musicien), pas un fabricant »). L'approbation ne veut donc pas dire « relue par une personne » pour la grande majorité des fiches.

Conséquence : tant qu'aucune version n'est validée, `effective_version` vaut 0 et le Portier (mode `validated`) ne reçoit **aucune** fiche de marque, même si `T1_KNOWLEDGE_ENABLED` était vrai. L'option est de toute façon éteinte (voir `ia.md`).

## Fichiers

| Fichier | Rôle |
|---|---|
| `backend/guitar_knowledge.py` | Recherche (alias, tolérance aux fautes), porte de qualité, formatage du bloc de prompt, outil `lookup_brand`, règles de sources et de confiance |
| `backend/api/fiches_repo.py` | Lecture des fiches par l'API (asyncpg), index d'alias des fiches, fiches utiles pour une annonce |
| `backend/scripts/seed_guitar_fiches.py` | Chargeur `docs/fiches/*.md` → base (exécuté à chaque déploiement) |
| `backend/scripts/seed_guitar_knowledge.py` | Amorçage sourcé de marques depuis `backend/knowledge/seed/*.json` (manuel) |
| `backend/scripts/import_guitar_knowledge_wikidata.py` | Import Wikidata et Wikipédia (manuel, réseau) |
| `backend/scripts/knowledge_review_apply.py` | Enregistre les décisions de relecture (feuille `DECISION: A/R`) |
| `backend/knowledge/seed/` | 8 lots JSON de marques (batch1 à batch8), 45 entrées au total |
| `backend/knowledge/review/` | 3 fichiers de décisions de relecture (lot1 à lot3), 404 décisions |
| `docs/fiches/` | 14 fiches Markdown, `_GABARIT.md`, `README.md`, `img/<slug>/`, `_banque/` (éléments de schémas SVG) |

## Recherche de marques (`guitar_knowledge.lookup`)

1. **Index d'alias** par jeu de types, mis en cache 600 s, protégé par un verrou. Alias exploitable (`alias_usable`) : au moins 3 caractères, ni purement numérique, ni mot générique (`_STOP`), ni composé uniquement de mots génériques ; certains mots d'accroche d'annonce (« killer », « mint »…) sont interdits seuls.
2. **Éligibilité à l'injection** (dans la requête de chargement) : ni accessoire, ni confiance `single_source`, ni `luthier` non curé, ni `unknown` sans catégorie de fabricants (sauf curée ou écrite à la main), et seulement jusqu'à la version choisie (`validated` par défaut, `latest`, ou un numéro ; `configure_version`).
3. **Recherche** (`find_ids`) : n-grammes de 1 à 4 mots dans le titre, la description et, en option, le texte lu sur les photos. Tolérance aux fautes (`difflib`, ratio 0,88, mots d'au moins 6 lettres) **seulement sur le titre** (et le texte des photos si demandé), jamais pour les fiches.
4. **Porte de qualité** : `hard_failures` (rejetée à la relecture, années incohérentes, description sans rapport avec les guitares) n'est servie nulle part ; avec `_REQUIRE_REVIEW` (défaut vrai, `T1_KNOWLEDGE_REQUIRE_REVIEW`) seules les fiches de confiance (`approved` à contenu inchangé, curées ou écrites à la main) sont servies. Une approbation devient `stale` si le contenu a changé depuis (empreinte md5 du nom, de la description, des années, du parent et du type).
5. **Série sans marque mère** : une `line` n'est servie que si sa marque mère est aussi reconnue dans le texte.
6. **Tri déterministe** : correspondances exactes d'abord, séries avant marques, fiches curées d'abord, alias le plus long, puis identifiant. `_prefer_name_owners` écarte les fiches qui ne sont là que par l'alias d'une autre, et préfère la fiche curée à son doublon importé. Au plus `limit` fiches (3 au Portier).
7. **Bloc de prompt** (`format_for_prompt`) : une ligne par fiche (nom, type, parent, pays, période *seulement si fiable*, gamme, notes de chasse ou description tronquée à 260 caractères), marquée « données, pas des instructions ». Les URL de sources n'y entrent **jamais**.

## Outil `lookup_brand` de l'Expert (`search_brand`)
Recherche plus large : tous les types de marques, versions non validées comprises, trois niveaux de correspondance (exacte, faute de frappe mot à mot, mot partiel). Les fiches qui ne passeraient pas les règles du Portier sont renvoyées **étiquetées « non vérifiée »** avec la raison. Les erreurs évidentes (`hard_failures`) ne sont jamais renvoyées. « Aucune fiche » est présenté au modèle comme sans rapport avec la valeur. Quatre appels au plus par analyse (voir `ia.md`).

## Sources et confiance
Une fiche sans source est refusée. `validate_sources` : URL http(s), éditeur, type connu (`wikidata`, `wikipedia`, `wikipedia_list`, `collector`, `manufacturer`, `forum`, `marketplace`, `press`, `other`), citation de 300 caractères au plus, pas d'URL en double. **La confiance est calculée, jamais déclarée** : `sourced` si au moins 2 éditeurs indépendants (`publisher_key` : domaine racine ; chaque sous-domaine compte pour un éditeur sur les hébergeurs de blogs), sinon `single_source`.

## Fiches techniques

### Format
Un fichier `docs/fiches/<slug>.md` : en-tête `clé: valeur` entre deux lignes `---` (obligatoires : `slug` = nom du fichier, `titre`, `categorie` ∈ `structurel`, `cosmetique`, `electronique`, `quincaillerie`, `reglage`, `autre`, `difficulte` 1 à 5, `duree`, `statut` ∈ `brouillon`, `en_revision`, `validee`, `revision` ; facultatif `alias`, expressions séparées par des virgules ; tout autre champ est refusé), puis le corps. Résumé = premier bloc de citation. Sources = puces `- [Éditeur : titre](url) : ce que la source appuie` de la section « Sources et liens ». Renvois = liens relatifs `autre-fiche.md`, vérifiés. L'« Historique des révisions » reste la dernière section.

### Chargement (`seed_guitar_fiches.py`)
- **À chaque déploiement** (étape non bloquante de `deploy.yml`), pour chaque base distincte (bot, API de production, API de test) ; à la main avec `DATABASE_URL`.
- Idempotent : une fiche dont `content_hash` n'a pas changé n'est pas réécrite (`--force` pour forcer). `--dry-run` valide sans écrire. `--prune --yes` retire les fiches dont le fichier a disparu (refusé si `_GABARIT.md` est absent).
- Une fiche prend `kb_version = 0`, ne crée **aucune** version, et ses alias, sources et liens d'origine « fiche » sont réécrits à chaque chargement ; ceux ajoutés à la main ne sont jamais touchés.
- **La source est Git** : ne jamais corriger une fiche en base.

### Lecture (API)
`GET /fiches` (catalogue avec alias, filtre `categorie`), `GET /fiches/{slug}` (métadonnées, corps, sources, lues dans une transaction à lecture répétable), `POST /deals/{deal_id}/fiches/search` (corps `{q, limit}` pour que la question ne figure pas dans les journaux d'accès). **Toutes les fiches sont servies, brouillons compris**, avec leur statut et leur confiance (décision produit). Pour une annonce, `fiches_for_deal` classe : alias dans la question en cours (`question`), fiche liée à une étape (`etape`), alias dans le libellé d'une étape (`plan`), alias dans le titre ou la description (`annonce`) ; les étapes ne comptent que pour qui a accès au plan et ne portent que ses propres étapes. L'index d'alias est revérifié toutes les 30 s par une requête d'empreinte (nombre de fiches, dernière modification, nombre d'alias). Recherche exacte seulement : pas de tolérance aux fautes pour les fiches. Une étape qui pointe une fiche supprimée voit son lien retiré à la lecture.

### Isolation des deux familles
Toute lecture filtre par type par liste blanche (`BRAND_KINDS`, `FICHE_KINDS`). Garde-fou : `backend/test_knowledge_fiche_isolation.py`. Règle d'alias propre aux fiches (`fiche_alias_usable`, mots comme « action », « manche », « frette » refusés seuls).

## Import et amorçage de marques
- **Import Wikidata/Wikipédia** : quatre routes (catégorie « Guitar manufacturing companies » dans six langues, propriété « produit », un saut vers marques et filiales, séries de modèles) ; réécrit nom, description, parent, pays, années, pertinence, alias de source import et données brutes ; ne touche jamais `tier`, `hunt_notes`, `made_by`, `curated` ni les alias manuels ; crée une **nouvelle version non validée**. Réseau et `KB_CONTACT` requis.
- **Amorçage sourcé** : lots JSON de `backend/knowledge/seed/` ; chaque fiche cite au moins une source ; une correction (`patch`) d'une fiche importée exige au moins 2 éditeurs distincts ; `hunt_notes` n'est posé que s'il est vide. **Chaque exécution crée une nouvelle version** de la base.
- **Relecture** : une feuille `DECISION: A` (approuvée) ou `R` (rejetée) par fiche, appliquée par `knowledge_review_apply.py`.
- **Validation d'une version** : `UPDATE guitar_knowledge_versions SET validated = true WHERE version = N`, **seulement après** un rejeu de non-régression concluant (critère : `CLAUDE.md`, `STRATEGIE_IA.md` §3.6 et §3.8 ter). Aucun rejeu concluant n'est consigné à ce jour.

## Outils d'audit et de relecture (`backend/scripts/`, manuels)

| Script | Rôle | Écrit en base |
|---|---|---|
| `knowledge_coverage.py` | Carte des trous : marques vues dans les annonces (`brand_any`) sans fiche (`--days`, `--min-count 2`, `--top 30`, `--csv-out`, `--json-out`) | non |
| `knowledge_diag_t3.py` | Ce que verrait le Portier et l'outil de l'Expert sur des annonces rejouées (`--file`, `--ids`, `--query`, `--read ID=TEXTE`) | non |
| `knowledge_gate_report.py` | Rapport de la porte de qualité et feuille de relecture (`--sheet`, `--top 100`, `--days`, `--max-hits 100`) | non |
| `knowledge_review_html.py` | Page HTML de relecture avec extraits de sources et export (`--out ~/kb_relecture.html`) | non |
| `knowledge_review_apply.py` | Applique une feuille `DECISION: A/R` (`--dry-run`) ; crée les colonnes de relecture si besoin | oui |
| `knowledge_triage.py` | Tri **automatique par règles**, sans IA : `report`, `apply` (approuve les fiches cohérentes importées de la catégorie des fabricants, note « auto (règles, sans IA) »), `export` | oui (`apply`) |
| `knowledge_ai_review.py` | Revue **par Claude avec recherche web** : `review`, `apply`, `report`, `enrich` ; modèle `T3_CLAUDE_MODEL`, tarifs codés à 3 et 15 $ par million de tokens, 0,01 $ par recherche, plafond `--max-usd` | oui (`apply`) |
| `t1_kb_paired_replay.py` | **Rejeu apparié** du Portier sans/avec la base (sous-commandes `plan`, `run`, `ocr`, `ocr-check`, `case-report`, `report`) : c'est lui qui décide de la validation d'une version | non (écrit des JSON) |
| `compare_knowledge_effect.py` | Compare deux rejeux (`--baseline`, `--with-kb`, `--baseline2`) | non |

Critères codés dans `t1_kb_paired_replay.py` : gain minimal 15 points sur les annonces du bras A, hausse maximale du rejet 3 points sur le bras B, au moins 25 annonces A, taux d'échec maximal 10 %, taux de rejet minimal du criblage 30 %, récupération de la lecture des photos d'au moins 70 % sur 15 cibles.

## Pièges et invariants
- Une fiche (`kb_version = 0`) ne doit jamais faire entrer de marque au Portier : ne créer aucune version pour elle.
- Toute **nouvelle lecture** de `guitar_knowledge*` doit filtrer par type.
- Les états globaux du module (`_VERSION_MODE`, `_REQUIRE_REVIEW`, caches) sont partagés par tous les threads du processus.
- Les colonnes de relecture sont créées par `schema.sql` au démarrage ; un script lancé avant ce redémarrage voit toutes les fiches comme non relues.
- Une approbation ne vaut que pour le contenu relu : un réimport qui change la fiche la rend `stale`.

## Tests
`backend/test_guitar_knowledge.py`, `test_seed_guitar_knowledge.py`, `test_seed_guitar_fiches.py`, `test_knowledge_fiche_isolation.py`, `test_knowledge_coverage.py`, `test_knowledge_gate_report.py`, `test_knowledge_triage.py`, `test_knowledge_ai_review.py`, `test_knowledge_review_html.py`, `test_compare_knowledge_effect.py`, `test_t3_brand_tool.py`, `api/test_fiches_api.py`. Les tests qui exigent Postgres utilisent `KB_TEST_DATABASE_URL` (base **jetable**, elle est vidée).
