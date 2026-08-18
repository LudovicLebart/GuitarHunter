# Journal de Bord - Guitar Hunter AI

[2026-08-17] [PRO] Feature : backfill léger des scores IA sur les ventes corrompues, armé et poussé sur `dev` → Résultat :
- **Contexte** : suite au constat que l'Explorateur de Corrélations ne trace que 46 ventes sur 3000+ en base — cause identifiée : ~2216 annonces vendues restent avec un `aiAnalysis` corrompu par le bug `ArrayUnion` (2026-08-12), jamais récupéré au-delà du verdict (`initialVerdict`, 1313/3529 déjà recouvertes). La ré-analyse prévue (`reanalyze_sold_deals.py`, cascade complète 3-Tiers) n'a jamais été déclenchée (~20-25$ estimés).
- **Demande utilisateur : un script dédié moins coûteux**, soit modèle plus léger, soit JSON réduit aux données manquantes en se basant sur les analyses existantes. Clarifié avec l'utilisateur : JSON réduit avec un vrai appel Gemini par annonce (pas d'imputation statistique à partir d'annonces similaires, qui aurait contaminé le graphique de corrélation IA/vitesse de vente tout juste corrigé pour ne plus être circulaire).
- **`prompts.json` + `config.py`** : nouvelle instruction `sold_backfill_instruction` — JSON strictement limité aux champs structurés (5 scores, classification, marge, verdict, marque/modèle/couleur), aucun champ de texte libre (`analysis`/`reasoning`/`summary`/`visual_inspection`).
- **`backend/analyzer.py::analyze_deal_light()`** (nouveau) : un seul appel au modèle Analyste (T2) — ni Portier (l'annonce est déjà vendue, inutile de la re-filtrer), ni risque de déclencher l'Expert Pro (T3, coûteux, inutile pour de l'historique). `model_used` tagué `"backfill_leger -> {modèle}"` (2 maillons synthétiques) plutôt qu'un nom de modèle seul — sinon `StatsView.jsx::modelChainTokens` (qui compte les maillons pour détecter qu'une annonce a atteint le Tier 2) sous-compterait ces annonces dans le Funnel alors qu'elles ont bien été scorées.
- **`backend/scripts/backfill_sold_scores.py`** (nouveau, ne remplace pas `reanalyze_sold_deals.py`) : même patron que ce dernier (idempotent, verrou PID, n'écrit que `aiAnalysis`) mais appelle `analyze_deal_light()`. **N'écrit jamais `timestamp`** dans l'index — demande explicite de l'utilisateur : ces annonces ne doivent pas apparaître dans "Volume de Scraping Quotidien" (`StatsView.jsx::dailyVolumeData`) comme si elles avaient été scrapées/analysées aujourd'hui. Vérifié : le patron d'écriture existant (`reanalyze_sold_deals.py`) ne touchait déjà pas ce champ, le nouveau script hérite du même garde-fou plutôt que de le supposer.
- **`run_once.py`** : armé (`ACTIVE = True`) — lance `backfill_sold_scores.py` en **arrière-plan détaché** (`subprocess.Popen(..., start_new_session=True)`), même patron qu'une tentative similaire du 2026-08-12 pour `reanalyze_sold_deals.py` (jamais réellement déployée, remplacée avant push par la récupération gratuite du verdict). Job potentiellement long (~2216 appels Gemini), largement au-delà du timeout de 10 min du step SSH — détaché, survit à la fin du step et au redémarrage du service. Poussé via `/git-push-dev` (`dev` uniquement, pas de double déclenchement dev+master à gérer ici).
- **Non vérifiable en conditions réelles depuis cet environnement de dev** : ni l'appel Gemini, ni le contenu de `backfill_sold_scores.log` (accès SSH requis). Résultat à vérifier après coup, puis `run_once.py` à repasser à `ACTIVE = False` dans un commit séparé (protocole `CLAUDE.md`).

---

[2026-08-17] [PRO] Fix : piste 2 du bug "détection VENDU incomplète" — vérification du titre en plus des badges → Résultat :
- **Demande utilisateur, après un état des lieux des 3 pistes du bug ouvert le 2026-07-19** : piste 1 (filtre pré-IA) et piste 3 (Portier T1) étaient codées mais piste 2 (vérification du titre par `check_listing_availability()`) restait ouverte — seule vraie lacune du bug d'origine.
- **Cause** : `check_listing_availability()` (Facebook **et** Kijiji, même trou vérifié dans les deux fichiers) ne détectait qu'un badge de statut au texte **exact** ("vendu", "sold" — regex ancrée `^vendu$`, volontairement stricte pour ne pas confondre ce badge avec un mot présent ailleurs dans la page). Un vendeur qui édite son titre pour signaler la vente sans supprimer l'annonce ("VENDU - Fender Strat 62") passait donc au travers de la vérification périodique.
- **`backend/sold_markers.py` (nouveau)** : `SOLD_MARKERS` + `find_sold_marker()`, factorisés hors de `bot.py::handle_deal_found()` (qui les dupliquait en local) pour être réutilisés aussi par les deux scrapers — même pattern que `taxonomy.py`/`cities.py`.
- **`backend/scraping/core.py` et `backend/scraping/kijiji/core.py`** : `check_listing_availability()` extrait désormais `og:title` (déjà utilisé ailleurs dans ces fichiers, fiable même quand Facebook gate le prix/les photos pour une session non authentifiée) et vérifie par **sous-chaîne** (pas la regex ancrée des badges) s'il contient un marqueur de vente. Repli optimiste conservé en cas d'échec d'extraction (cohérent avec le reste de la fonction).
- **Validation** : syntaxe Python vérifiée sur les 4 fichiers ; les deux scrapers importent proprement la nouvelle dépendance (testé en installant le paquet `playwright`, sans les navigateurs) ; `bot.py` ne conserve plus aucune référence à l'ancienne liste locale. **Non testé en conditions réelles** (pas d'accès Playwright/réseau Facebook/Kijiji depuis l'environnement de dev) — à valider par l'utilisateur, comme la piste 3 l'était déjà.
- **`TODO.md`** : les 3 pistes du bug sont désormais toutes codées ; item parent passé de `[ ]` à `[/]` (piste 1 confirmée en production, pistes 2 et 3 en attente de confirmation).

---

[2026-08-17] [FLASH] Réflexion : score de liquidité enrichi multi-facteurs (couleur, style, catégorie, prix) → Résultat :
- **Contexte** : après avoir testé l'Explorateur de Corrélations en conditions réelles (r ≈ -0,27 sur 46 ventes, score liquidité × délai réel — corrélation dans le bon sens mais faible), l'utilisateur a proposé de croiser plusieurs facteurs (couleur, style, catégorie de taxonomie, tranche de prix — explicitement pas la ville, jugée non reproductible géographiquement) pour mieux prédire quelle guitare se vend vite, en vue d'enrichir le score global de l'annonce (`deal_score`).
- **Avis donné, aucun code écrit** : idée valide en principe, mais réserve sur l'échantillon — 46 ventes est déjà mince pour 2 variables, le fragmenter en sous-groupes couleur × style × catégorie × prix produirait des cellules de 1-2 annonces (bruit, pas signal). Recommandation en 2 phases : (1) tester chaque facteur individuellement via l'Explorateur existant (outillé pour ça sans nouveau code) avant toute combinaison ; (2) seulement si un signal réel émerge, chantier séparé de réinjection dans le pipeline IA backend — plus lourd qu'un ajout de graphique, à traiter à part.
- **Consigné comme piste à l'étude, non engagée** : `docs/explanation/STATS_REFLEXION.md` §4 (nouvelle entrée 🔭) et `docs/management/TODO.md` § Statistiques & Dashboard (nouvel item `[ ]`) — aucun développement déclenché, en attente d'une décision de l'utilisateur sur la phase 1.

---

[2026-08-17] [PRO] Feature : graphique liquidité remplacé par un Explorateur de Corrélations à axes dynamiques (`DealsExplorer.jsx`) → Résultat :
- **Enchaînement dans la même session** : le nuage de points + Pearson (entrée suivante, round 1) a été jugé illisible par l'utilisateur (« je ne trouve pas ça lisible... on a cassé la ligne réelle »), qui voulait retrouver le format à 2 courbes. Un round 2 (tranches par tertile de vitesse RÉELLE plutôt que par score, pour rester non-circulaire) a été implémenté et poussé (commit `76e7d3f`) — mais l'utilisateur a ensuite demandé « pourquoi être revenu à ces groupes ? », ne comprenant pas l'intérêt de regrouper. **Question posée en termes simples : « pour chaque vitesse de vente, quelle corrélation avec le score IA ? quel est l'intérêt de grouper ou d'avoir un nuage de points ? »** Réponse honnête : aucun — un nuage de points sur les valeurs individuelles EST la réponse directe à cette question ; le regroupement du round 2 réglait un problème de lisibilité d'exécution (mauvais rendu du round 1), pas un vrai besoin de regrouper. Le round 2 est donc resté un détour, pas la solution.
- **Demande complémentaire de l'utilisateur, dans la foulée** : un graphique dynamique où choisir librement quelles données afficher (ex. vitesse de vente par score IA, couleur, ville...), avec 1 ou 2 axes configurables — au-delà du seul cas liquidité.
- **`src/components/DealsExplorer.jsx` (nouveau)** : nuage de points générique remplaçant le graphique liquidité dédié. Sélecteurs **Axe X / Axe Y** parmi 8 métriques (`deal_score`/`authenticity_score`/`condition_score`/`liquidity_score`/`restoration_interest_score`, prix, marge estimée, délai de vente réel — ce dernier restreint le nuage aux ventes avec délai connu, comme l'ancien graphique dédié). Corrélation de Pearson + droite de régression recalculées pour la paire d'axes choisie (même formule que le round 1, généralisée à n'importe quelle paire).
- **Couleur limitée à 3 dimensions catégorielles à cardinalité FIXE** (Verdict réduit à Opportunité/Marché neutre/Rejeté via `RADAR_GROUP`/`MARKET_GROUP`, Source Facebook/Kijiji, Catégorie réduite à Guitare/Amplificateur/Étui via la racine de taxonomie) plutôt qu'un détail complet (9 verdicts, 8 catégories) : la palette daltonisme-sûre du design system (skill `dataviz`) ne garantit une séparation fiable entre points d'un nuage (contrainte *all-pairs*, plus stricte qu'une simple paire adjacente) que sur ses 3 premiers slots — au-delà, il faut replier sur "Autre" ou faceter. Plutôt qu'un "top N + Autres" dynamique, qui violerait la règle "la couleur suit l'entité, jamais son rang" (un filtre changeant le nombre de séries repeindrait les survivants), chaque dimension est réduite à des groupes déjà établis ailleurs dans l'app. Couleurs (`#3987e5`/`#d95926`/`#199e70`) validées via `scripts/validate_palette.js --mode dark --pairs all --surface "#0f172a"` avant intégration — toutes en échec sur un premier choix "intuitif" (vert/gris/rouge), corrigées avec les 3 premiers slots de la palette de référence du skill.
- **Ville : filtre dédié, pas une couleur** — cardinalité ouverte (des dizaines de villes possibles), structurellement inadaptée à une palette catégorielle fixe ; un filtre ("montre-moi juste Montréal") sert d'ailleurs mieux le besoin réel qu'un code couleur à 40 teintes illisibles.
- **`StatsView.jsx`** : suppression de `liquiditySpeedData` (round 2, tertiles) et de son rendu `LineChart`, remplacés par `<DealsExplorer deals={analysisDeals} />`. Imports Recharts devenus inutilisés (`LineChart`, `Line`, `Legend`) retirés.
- **Validation** : `npm run build` OK. Vérifié via harness Playwright sur données mockées variées (verdicts/sources/villes/prix) — axes par défaut, chacune des 3 options de couleur, et le filtre ville, tous lisibles et fonctionnels (captures).
- **Non encore validé en conditions réelles par l'utilisateur** (« il faut que je teste, je ne suis pas convaincu ») — poussé sur `dev` pour test en conditions réelles avant confirmation finale.

#### Raisonnement
Round 2 illustre un piège de communication, pas de code : une critique ("pas lisible, tu as cassé la ligne réelle") a été interprétée comme "reviens au format précédent" alors que le format précédent (tranches) n'était pas ce que l'utilisateur voulait préserver — c'était la lisibilité en général, que le round 1 n'avait simplement pas bien exécutée. Il a fallu que l'utilisateur reformule la question sous-jacente en termes simples ("pour chaque vitesse de vente, quelle corrélation avec le score IA ?") pour révéler que le regroupement n'avait jamais été une exigence, seulement une hypothèse de correction non vérifiée avant implémentation. Lesson générale : quand un retour utilisateur motive un choix de design, vérifier explicitement ce que l'utilisateur veut préserver plutôt que d'inférer un format cible à partir de ce qu'il rejette.

---

[2026-08-17] [PRO] Fix : graphique liquidité prédite — la droite affichée était un artefact du binning, pas un signal → Résultat :
- **Symptôme signalé par l'utilisateur** : « les résultats prédits par l'IA forment une droite, c'est très suspect » sur le graphique « La liquidité prédite par l'IA se confirme-t-elle ? ». Question complémentaire : avons-nous une valeur spécifique sur la liquidité (pas seulement des tranches) ?
- **Diagnostic confirmé** : oui, `liquidity_score` est une valeur précise par annonce (0-10), indexée individuellement (`ls`, `repository.py::_update_deal_index()`). Mais l'ancien graphique (`liquiditySpeedData`) regroupait les ventes en 3 tranches fixes (Faible 0-4/Moyenne 5-7/Élevée 8-10) puis traçait la MOYENNE du score IA **au sein de chaque tranche** comme "prédiction" — un calcul circulaire, puisque ces tranches sont elles-mêmes définies par ce même score. Trois points nécessairement croissants et régulièrement espacés (0-40 / 50-70 / 80-100 par construction) produisent une droite quasi garantie, indépendamment de toute vraie relation entre score et vitesse de vente réelle.
- **Solution** : remplacé par un nuage de points sur les valeurs individuelles (un point = une vente, score IA en abscisse, délai réel en jours en ordonnée) et un coefficient de corrélation de Pearson (`r`) calculé sur ces valeurs brutes, avec une droite de régression en tendance (pas une moyenne par tranche). Un `r` proche de 0 ne peut plus être masqué par un artefact de binning. Interprétation affichée en clair (corrélation faible/modérée/forte, seuils de Cohen, et sens attendu ou non).
- **`LIQUIDITY_TIERS` supprimé** (n'était utilisé que par ce graphique).
- **Bug trouvé et corrigé pendant le développement** : le tooltip par défaut de Recharts sur un `ComposedChart` à axe X numérique partagé (`dataKey="x"`) affichait une ligne technique parasite `x : 9` en plus du délai — remplacé par un tooltip personnalisé (`content={...}`) affichant uniquement "Score prédit" et "Délai réel".
- **Validation** : calcul de corrélation testé unitairement (relation parfaite positive/négative → r=±1 ; Y constant → r indéfini, distinct de r=0 ; n<3 → pas de calcul ; jeu de données bruité reproduisant le cas réel → r faible correctement détecté, là où l'ancien système à 3 tranches aurait quand même affiché une fausse droite). Rendu vérifié via Playwright sur données mockées (45 ventes, relation bruitée volontairement imparfaite) : nuage de points dispersé, tendance en pointillé légèrement descendante cohérente avec `r = -0.25` affiché, tooltip propre. `npm run build` OK. Skill `dataviz` suivi (nuage de points = forme correcte pour une relation entre deux variables continues ; palette réutilisant les couleurs déjà en usage dans `StatsView.jsx`, aucune nouvelle teinte introduite).

[2026-08-17] [PRO] Résultats de l'audit des villes en production (`run_once.py`, deux runs) → Résultat :
- **Poussé via `/git-push-dev-master`** — `dev` (run #335) et `master` (run #336) ont chacun exécuté `audit_cities.py` en écriture. Aucune erreur, `regions_conflict()` a été validé sur un vrai cas non anticipé : `'beloeil'` recouvre `Beloeil, QC` (Québec) **et** `Beloeil, WAL` (Wallonie, Belgique) — les deux régions ont bien empêché la fusion.
- **`dev`** : 4492 annonces, 10 villes à graphies multiples, 128 uniformisées. **`master`** : 4492 annonces, 16 villes à graphies multiples, 324 uniformisées — un 3e variant (`'Longueuil'`, sans virgule ni région) apparu entre les deux runs.
- **Root cause du décalage, non un défaut d'idempotence du script** : `/git-push-dev-master` pousse sur `dev` puis `master` très rapidement, déclenchant deux workflows GitHub Actions quasi simultanés sur la même base de production (confirmé : le job `deploy` de `master` a démarré *avant* celui de `dev`, malgré l'ordre des push). Le bot en direct a continué de scanner et d'écrire des annonces pendant la fenêtre — avec l'ancien `bot.py` jusqu'au redémarrage du service à la fin de chaque déploiement — d'où la 3e graphie apparue entre les deux lectures. `audit_cities.py` lui-même ne fait que choisir parmi les valeurs déjà présentes ; il n'invente jamais de nouvelle graphie.
- **Leçon retenue, à appliquer à toute future action `run_once.py` en écriture** : un script "idempotent" ne l'est que pour un jeu de données figé — pas pour une base en production sous trafic continu pendant que deux déploiements se chevauchent. Aucun risque de corruption ici (le pire cas est une réécriture redondante vers la même valeur cible), mais le rapport d'audit d'un des deux runs peut être partiellement obsolète au moment où il est lu.
- **`run_once.py` repassé à `ACTIVE = False`** dans ce commit, immédiatement après lecture des deux rapports (protocole `CLAUDE.md`).

[2026-08-16] [PRO] Revue de code de la session : 8 trouvailles, dont 3 régressions introduites le jour même → Résultat :
- **Demande utilisateur : revue de toute la session** (`5200eba..HEAD`). 9 trouvailles remontées, 8 confirmées après vérification manuelle de chacune (la 9e — `audit_cities.py` sans chemin vers la production — était un constat exact, traité séparément en armant `run_once.py`).
- **Régression 1 — le bug des étuis survivait dans `StatsView.jsx`**, le seul fichier non migré vers `utils/taxonomy.js`. Sa copie locale `normalizeTaxKey` supprimait les points : `normalizeTaxKey("guitare.electrique") === normalizeTaxKey("Guitare Electrique")` (vérifié). **La canonicalisation des 356 annonces l'a même aggravé** en généralisant les chemins complets en base — une vraie guitare était étiquetée « Étui / Housse » dans « Marge par catégorie ». `StatsView` délègue désormais au module partagé ; `normalizeTaxKey`, `buildTaxonomyPathsByKey`, `TYPE_LABELS` et l'import `prompts.json` supprimés (la duplication documentée depuis le 2026-08-06 disparaît avec).
- **Régression 2 — libellés cassés par les chemins canoniques** : `classification.split(' ').slice(-1)[0]` (graphique « Vitesse de vente par type ») supposait un nom de feuille ; avec `guitare.electrique.solid_body.Double_Cut.SG` (aucun espace) il affichait le chemin technique entier, et « Paul » pour « Les Paul ». Remplacé par `formatClassificationLabel`.
- **Régression 3 — le correctif des villes n'en était qu'à moitié un** : `bot.py` écrivait `c['name']` (« Montréal ») alors que Facebook écrit « Montréal, QC ». Les deux producteurs divergeaient encore, la base se serait refragmentée au prochain scan, et `format_city_label()` — écrit précisément pour cette réconciliation — n'était **jamais appelé**. Corrigé conformément à l'option A : `_build_city_display_names()` reprend la région d'une graphie déjà connue, lue depuis l'index léger (aucune lecture de `guitar_deals`).
- **5 autres correctifs** : `_update_deal_index()` relit lui-même `manualClassification` (`rebuild_index`, `reanalyze_sold_deals` et `recover_initial_verdict` ne la passaient pas et réécrivaient `c` avec la valeur de l'IA en laissant `mc: true` — l'UI affichait « corrigé » sur une catégorie qui ne l'était plus) ; `handleSetClassification` invalide `loadedDeals` (cache écrit une seule fois qui PRIME dans la fusion, donc une 2e correction ou l'annulation restait invisible jusqu'au rechargement) ; recherche de catégories insensible aux accents (taper « étui », l'exemple du placeholder lui-même, ne renvoyait rien) ; index de taxonomie mémorisé au lieu d'être reconstruit à chaque annonce ; `audit_cities.py` refuse d'uniformiser deux graphies aux régions différentes (`regions_conflict()`).
- **Bug rattrapé pendant l'implémentation** : `_build_city_display_names()` utilisait `normalize_city_key` sans import — mon motif de remplacement visait une ligne inexistante dans `bot.py`. `NameError` au premier scan Kijiji, détecté par vérification après édition plutôt que par le typage.
- **Validation** : 8 assertions villes (dont `regions_conflict` sur `Paris, IDF` vs `Paris, ON`), 11 cas de taxonomie en non-régression, les deux audits contre Firestore simulé (dry-run muet, idempotence, corrections manuelles intouchées), `npm run build` OK.
- **`run_once.py` armé sur l'audit des VILLES, en écriture** (`dry_run=False`) — la lecture seule préalable a été proposée à l'utilisateur, qui a choisi l'écriture directe : le rapport détaillé (graphies fusionnées ville par ville) est produit dans les mêmes logs, simplement lu après coup. Poussé via `/git-push-dev-master`, donc le job se déclenche **deux fois** (`dev` puis `master`) — sans effet au 2e passage, le script étant idempotent. À repasser à `ACTIVE = False` dans un commit séparé.

[2026-08-16] [PRO] Normalisation exécutée en production : 356 classifications réécrites → Résultat :
- **Run GitHub Actions #333 (`dry_run=False`, 76s)** — les prédictions de l'assouplissement se vérifient exactement : `leaf` 326 → **347** (+21 termes d'étui libérés par la règle restreinte), `partial_path` **7** (chemins tronqués réparés), `ambiguous` 31 → **10**, `unknown` 50 → **43**. **356 annonces normalisées** en chemin canonique (document + index).
- **Vérification qualitative** : `Housse_Souple`, `Gigbag Standard`, `ATA Road Case`, `Etui_Rigide`, `Luxe / Reinforced` et les chemins tronqués (`electrique.solid_body.*`, `accessoire_etui.protection.*`) ont tous **disparu** de la liste des valeurs non résolvables — c'est la confirmation en conditions réelles que les deux correctifs visaient juste.
- **Défaut rattrapé avant le déploiement** : le nouveau cas `partial_path` manquait dans la liste des motifs du récapitulatif — les annonces auraient bien été normalisées mais la ligne aurait été **absente du rapport**, laissant croire à tort que la réparation des chemins partiels n'avait rien donné. Corrigé et couvert par le banc de test simulé avant l'envoi.
- **Reste 53 annonces non résolues, et c'est un plancher assumé** : 10 réellement ambiguës (des étuis nommés `Guitare Electrique`/`Guitare Acoustique`/`Basse` — corrigeables d'un clic via `ClassificationEditor`) et 43 `unknown`, dont **41 sont des placeholders de l'IA** (`Inconnu`, `REJECTED_ITEM`, `NULL`, `N/A`, `Toy Guitar`) posés sur des annonces qui ne sont pas des instruments (pianos, Guitar Hero, câbles, table de mixage, cours de guitare) — le Portier a fait son travail, il n'y a rien à réparer.
- **2 cas résiduels non couverts par la réparation** (non corrigés, volume négligeable) : `guitare.acoustique_acier.formes_standard.Dreadnought Standard` — un niveau **intermédiaire** manquant, alors que la réparation ne retire que des segments de **tête** ; et `Travel / Mini`, probable dérive de `Baby / Mini`. Élargir la réparation à une correspondance par sous-séquence couvrirait ces cas mais augmenterait le risque de faux positifs pour 2 annonces : écarté.
- **`run_once.py` repassé à `ACTIVE = False`** dans ce commit, immédiatement après lecture du rapport (protocole `CLAUDE.md`).

[2026-08-16] [PRO] Résultats de l'audit en production + assouplissement de la résolution → Résultat :
- **Audit exécuté en lecture seule (run GitHub Actions #332, `dry_run=True`, ~7s)** — 4453 annonces sur 7 utilisateurs : `empty` 4027 (90,4 %), `leaf` 326 (7,3 %), `unknown` 50 (1,1 %), `ambiguous` 31 (0,7 %), `exact_path` 19 (0,4 %), 328 normalisables.
- **Constat principal : 90 % des annonces n'ont AUCUNE classification** — ce sont les rejets du Portier (T1), qui ne renvoie que verdict + raison. L'inventaire réellement classé est donc de ~426 annonces, pas 4453, dont **345 (81 %) résolvent correctement**. Le problème portait sur ~81 annonces : à cette échelle, la correction manuelle est viable et la ré-analyse Gemini n'est pas nécessaire.
- **Erreur de ma règle d'ambiguïté, révélée par l'audit** : les 31 « ambiguës » étaient TOUTES dans la branche `etui_housse`, mais seules 9 l'étaient réellement (`Guitare Electrique` ×7, `Guitare Acoustique` ×2 — dont les titres confirment qu'il s'agit bien d'étuis : « Yorkville Guitar **Cases** », « Fender G&G Deluxe **case** », « ESP LTD Hardshell Guitar **Case** »). Les 22 autres (`Housse_Souple`, `Gigbag Standard`, `Luxe / Reinforced`, `Etui_Rigide`, `ATA Road Case`) sont des **termes d'étui purs, sans la moindre ambiguïté** : ma règle excluait toute la branche au lieu des seuls noms reprenant un nom d'instrument. **Restreinte** : un nom nu de contenant n'est refusé que s'il commence par une racine d'instrument, déduite dynamiquement de la taxonomie.
- **Réparation des chemins partiels (nouveau, `partial_path`)** : l'audit a aussi montré que l'IA produit des chemins presque bons — racine oubliée (`electrique.solid_body.Double_Cut.SG`), niveau intermédiaire sauté (`guitare.acoustique_acier.Travel.Baby / Mini`, sans `specialites`), racine obsolète (`accessoire_etui.protection.…`). Ils sont désormais étendus vers l'unique chemin canonique qui s'y termine, en retirant au besoin les premiers segments ; un résultat non unique est refusé plutôt que deviné. ≈8 annonces récupérées.
- **Les 50 `unknown` restants sont en réalité deux populations** : ~41 placeholders de l'IA (`Inconnu`, `REJECTED_ITEM`, `NULL`, `N/A`, `Toy Guitar`) posés sur des annonces qui ne sont pas des instruments (pianos, Guitar Hero, câbles, table de mixage) — rien à réparer, le Portier a fait son travail ; et ~8 chemins partiels, désormais récupérés (ci-dessus).
- **Validation** : 24 cas de test construits à partir des **valeurs réelles remontées par l'audit**, verts côté backend, et **parité front/back vérifiée sur les 23 mêmes valeurs** via un banc Playwright comparant les deux implémentations une à une. Une attente de test était fausse (`ATA Road Case` vit sous `Flight_Case`, pas `Etui_Rigide`) — c'est le test qui a été corrigé, pas le code. `npm run build` OK.
- **Option (c) « heuristique étui sur le titre » abandonnée** : avec ≈9 annonces réellement ambiguës restantes, quelques clics dans l'app suffisent — inutile de prendre le risque d'une devinette sur le titre.
- **`run_once.py`** : repassé à `ACTIVE = False` immédiatement après l'audit (protocole), puis ré-armé pour cette 2e exécution **en écriture** (`dry_run=False`) qui normalisera les 328 + ≈27 récupérées.

[2026-08-16] [PRO] Audit + normalisation des classifications existantes (gratuit, sans Gemini) → Résultat :
- **Question de l'utilisateur après le correctif de classification : « les erreurs existantes seront-elles corrigées ? »** — non, pas automatiquement. Le correctif agit à la **lecture**, aucune donnée n'a été réécrite : une valeur déjà résolvable (chemin complet ou nom de feuille unique) s'affiche et se filtre correctement, une valeur **ambiguë** cesse d'être rangée dans la mauvaise catégorie mais bascule dans « Autres » sans que la bonne soit retrouvée, et une annonce que l'IA a réellement mal classée reste mal classée (aucune logique de résolution ne peut deviner qu'elle a tort).
- **Décision : mesurer avant de dépenser.** Le nombre d'annonces concernées (3 ou 3000) commande le choix entre correction manuelle et ré-analyse Gemini payante — et il était inconnu.
- **`backend/scripts/audit_classifications.py` (nouveau)** : une seule passe qui (1) **audite** — répartition par type de résolution (`exact_path`/`leaf`/`ambiguous`/`unknown`/`empty`/`manual`) + top des valeurs non résolvables avec exemples de titres, et (2) **normalise gratuitement** — réécrit en chemin canonique (document + index) les valeurs qui se résolvent déjà sans ambiguïté. Ne corrige aucune erreur de classement : il uniformise ce qui est déjà juste et chiffre ce qui ne l'est pas. Les annonces portant une correction manuelle (`manualClassification`) sont comptées à part et jamais touchées — les inclure dans les « à réparer » gonflerait le chiffre qui doit décider de la suite.
- **Testé contre un Firestore simulé** (stubs de `DatabaseService`/`FirestoreRepository`, jeu de 8 annonces couvrant les 6 cas) faute d'accès Firestore en dev : vérifié qu'un `--dry-run` n'écrit rien, que seules les valeurs résolvables sont réécrites (document **et** index synchronisés), qu'une valeur ambiguë/inconnue et une correction manuelle ne sont jamais touchées, et qu'un **2e passage n'écrit plus rien** (idempotence — le job de déploiement se déclenche sur `dev` puis `master`).
- **`run_once.py` : `ACTIVE = True`, mais en `dry_run=True`** (choix explicite de l'utilisateur, à qui les deux options ont été proposées) — **aucune écriture en base sur cette exécution** : on regarde d'abord les chiffres, la normalisation se fera lors d'un déploiement ultérieur. Résultat à lire dans les logs GitHub Actions, puis **`ACTIVE = False` dans un commit séparé immédiatement après** (protocole `CLAUDE.md`).
- **Étape suivante non engagée, à trancher chiffres en main** : (a) correction manuelle des cas ambigus, (b) ré-analyse Gemini ciblée des seules annonces non résolvables, (c) heuristique gratuite « titre contenant étui/case/housse → `etui_housse.*` », appliquée uniquement aux annonces déjà en échec de résolution. L'option (c) reste une heuristique et ne sera pas déclenchée sans accord explicite.

[2026-08-16] [PRO] Fix : des étuis classés comme guitares — taxonomie stricte + correction manuelle → Résultat :
- **Symptôme signalé** : un étui ("Fender G&G Deluxe Case Pour Stratocaster Telecaster") affiché en « Guitare Electrique », un chemin technique brut parfois affiché à la place du nom (`guitare.electrique.lespaul`), et aucun moyen de corriger. Hypothèse de l'utilisateur : le JSON de sortie n'est pas assez contraint — **exacte, et le diagnostic s'est révélé pire que prévu**.
- **Cause racine (bug de résolution, pas seulement d'affichage)** : `normalize()` supprimant TOUS les caractères non alphanumériques, `"Guitare Electrique"` (feuille de `etui_housse.Etui_Rigide`) et `"guitare.electrique"` (chemin de branche) produisaient la **même clé** `guitareelectrique`. Les chemins complets étant testés en premier dans `useDealsManager.js`, tout étui désigné par son nom de feuille était résolu en instrument — donc **mal filtré et mal compté dans les stats**, pas seulement mal étiqueté. Confirmé en reproduisant la collision hors application.
- **Piège découvert par les tests, à retenir** : la première correction (préserver le point, indexer par nom de feuille) ne faisait que **déplacer le bug** — `"Guitare Electrique"` devenait une feuille unique de `etui_housse`, donc une vraie guitare aurait été classée comme étui. Corrigé en indexant chaque nœud sous **deux clés** (nom de feuille ET chemin complet privé de ses points) : un nom nu désignant plusieurs nœuds distincts est alors détecté comme ambigu quel que soit le sens voulu par l'IA. S'y ajoute `AMBIGUOUS_LEAF_BRANCHES` (`etui_housse`), dont les feuilles portent des noms génériques d'instruments — un nom nu y est bien plus probablement l'instrument, seul le chemin complet permet de classer un étui.
- **`src/utils/taxonomy.js` (nouveau)** : résolution/affichage de la taxonomie en source unique, consommée par `useDealsManager` (filtres/compteurs), `DealCard` (affichage) et `ClassificationEditor` (correction). Supprime au passage la duplication de l'index taxonomie entre le hook et le `FilterDrawer`. **Résiduel `guitare.basse` corrigé au passage** (`solid_body`/`specialites`, partagés entre branches, sont désormais ambigus au lieu de résoudre vers la dernière branche parcourue) — voir `TODO.md`.
- **`backend/taxonomy.py` (nouveau) + `analyzer.py`** : canonicalisation serveur en **un point unique** — `analyze_deal()` devient l'enveloppe de `_run_analysis_cascade()` et post-traite le résultat final, plutôt que de patcher les 5 sorties de la cascade (dont aucune ne peut alors être oubliée). Une valeur ambiguë ou hors taxonomie est écartée (`classification: None` + `classification_rejected` pour diagnostic) plutôt que stockée telle quelle : une annonce non classée se corrige à la main, une annonce mal rangée passe inaperçue.
- **`prompts.json`** : le **chemin complet en dot-notation** devient obligatoire (le nom seul est structurellement ambigu), et la distinction objet/contenant est explicitée — un étui pour Stratocaster reste un étui. Rappel : le prompt ne garantit rien, `analyzer.py` faisant un `json.loads()` brut sans `response_schema` ; c'est la validation serveur qui fait garde-fou (même leçon que `finish_application` le 2026-08-01).
- **Correction manuelle (option A, tranchée avec l'utilisateur)** : `ClassificationEditor.jsx` dans la modale d'analyse écrit un chemin complet dans un champ **dédié** `manualClassification`, qui prime sur l'IA. Champ dédié plutôt qu'écriture dans `aiAnalysis.classification` : une ré-analyse remplace `aiAnalysis` en entier, la correction serait perdue au premier « Ré-analyser » (même famille de piège que le bug `ArrayUnion` du 2026-08-12). `repository.py::_update_deal_index()` relit `manualClassification` avant chaque réécriture d'index (`c`/`mc`), sinon filtres, compteurs et stats seraient silencieusement revenus à la valeur de l'IA pendant que le document complet, lui, gardait la correction.
- **Conséquence assumée** : une annonce dont l'IA renvoie un nom générique tombe désormais dans « Autres » plutôt que dans une mauvaise catégorie, et l'UI la marque « ambiguë » pour inviter à la corriger.
- **Validation** : 12 cas côté backend et **les 12 mêmes attendus côté frontend** (parité des deux implémentations vérifiée explicitement, banc Playwright), `npm run build` OK. Bancs de test supprimés, non commités. **Non testé** : l'appel Gemini réel (pas d'accès API depuis l'environnement de dev) — l'effet du durcissement du prompt sur les nouvelles analyses reste à valider par l'utilisateur.
- **Pas de backfill** : les annonces existantes (noms de feuille, chemins complets, valeurs mélangées) sont résolues correctement à la lecture ; seules celles dont la valeur est réellement ambiguë basculent en « Autres » jusqu'à correction manuelle ou ré-analyse.

[2026-08-16] [PRO] Feature : recherche globale — matching de la taxonomie + autocomplétion de catégories → Résultat :
- **Demande utilisateur :** traiter les deux volets restants de la tâche `TODO.md` § UI/UX "Améliorer la recherche globale" (les seuls encore ouverts depuis le progrès du 2026-07-31 sur `brand`/`model_name`/`color`).
- **Volet 1 — la recherche texte libre matche désormais la taxonomie résolue de l'annonce** (`useDealsManager.js::matchesTypeFilter`) : taper "acoustique", "parlor" ou "amplificateur" remonte les annonces classées dans cette branche même quand le mot n'apparaît nulle part dans le titre/marque/modèle. Le chemin de taxonomie était déjà résolu quelques lignes plus bas pour le filtre de type — il est maintenant résolu **une seule fois** et sert aux deux usages, donc aucun coût de résolution supplémentaire.
- **Nouveau helper `normalizeLoose()`** (accents et ponctuation neutralisés, **séparations de mots conservées**) utilisé pour cette comparaison, au lieu du `normalize()` existant qui supprime les espaces. Distinction délibérée et critique : `normalize()` est fait pour comparer des identifiants de taxonomie entre eux, alors qu'ici on compare une saisie utilisateur à du texte libre — l'utiliser aurait recréé exactement le faux positif déjà corrigé sur `findPathFuzzy` le 2026-08-01 ("cordes guitare" → "cordesguitare" contient "sg"). Effet de bord bienvenu : la recherche devient insensible aux accents ("electrique" trouve "électrique") et à la ponctuation ("les paul" trouve "Les-Paul").
- **Volet 2 — autocomplétion de catégories** (`src/components/SearchSuggestions.jsx`, nouveau) : les catégories dont le libellé matche la saisie sont proposées sous la barre, avec leur fil d'Ariane parent (deux feuilles homonymes existent dans des branches différentes) et leur nombre d'annonces. Tri : libellé commençant par la saisie d'abord, puis catégories contenant réellement des annonces, puis les plus larges. Le matching porte sur le **libellé propre du nœud**, pas sur son chemin complet — sinon taper "guitare" proposerait les ~100 nœuds de la branche.
- **Décision produit tranchée avec l'utilisateur (option A) :** sélectionner une suggestion **coche la catégorie dans `selectedTypePaths`** (même mécanisme que les cases du `FilterDrawer` : filtre persisté dans `uiFilters`, compté dans le badge de filtres actifs, soumis à la logique anti-chaîne) plutôt que d'injecter du texte dans `searchQuery`. Le champ de recherche est vidé dans la foulée — laisser le texte le ferait cumuler avec le filtre et masquerait presque tout.
- **Navigation clavier** (↓ ↑ Entrée Échap) exportée depuis le composant lui-même (`createSuggestionKeyHandler`) plutôt qu'écrite dans `Dashboard.jsx` : le comportement clavier reste solidaire du composant qu'il pilote, et devient testable sans monter tout le Dashboard. Entrée ne coche une catégorie que si l'utilisateur est explicitement descendu dans la liste — sinon la touche garde son sens de "je valide ma recherche texte".
- **Dette évitée** : le libellé de catégorie devient un helper partagé (`constants.js::formatTaxonomyLabel`) consommé par le `FilterDrawer` **et** l'autocomplétion, au lieu d'une copie locale — la même catégorie s'affiche identiquement dans les deux surfaces. (À rapprocher de la duplication déjà assumée dans `StatsView.jsx::resolveCategoryLabel`, elle non touchée.)
- **Validation** : `npm run build` OK. Banc de test temporaire (hook réel + composant réel, `firestoreService` mocké via un alias Vite) piloté par Playwright — **18/18 cas passent**, dont la non-régression "sg" (la vraie Gibson SG remonte, l'annonce "cordes guitare" non), le matching taxonomie sans le mot dans le titre, la sélection d'une suggestion (case cochée + champ vidé + filtre appliqué) et la navigation clavier. Fichiers de test supprimés après coup, non commités.
- **Non vérifié en conditions réelles** : le banc de test montait le hook et `SearchSuggestions`, pas le `Dashboard` complet avec ses contextes (pas de credentials Firebase dans l'environnement de dev) — le câblage Dashboard est couvert par le build et le handler partagé, mais le rendu final (notamment sur mobile) reste à valider par l'utilisateur.
- **Constat annexe, non corrigé** : `npm run lint` est cassé en amont — le dépôt ne contient aucun fichier de configuration ESLint (`ESLint couldn't find a configuration file`), alors que le script `lint` existe dans `package.json`. Pré-existant, sans lien avec ce changement.

[2026-08-16] [FLASH] Nettoyage documentaire : suppression de `CONTEXT_REPRISE.md`, retrait des placeholders vides de `TODO.md`, vérification de l'état réel des tâches UI/UX et Stats → Résultat :
- **`docs/management/CONTEXT_REPRISE.md` supprimé** : fichier de reprise généré le 2026-07-06 par `/save-and-compact`, portant lui-même la mention « À supprimer après lecture post-/compact ». Son contenu était périmé (état git du 2026-07-06) et intégralement redondant — la feature "partage sans authentification" qu'il décrivait est documentée dans `ARCHITECTURE.md`/`DATA_FLOW.md`, et ses 6 tâches ouvertes figurent toutes déjà dans `TODO.md`. Aucune référence à ce fichier ailleurs dans le dépôt (vérifié).
- **2 placeholders vides retirés de `TODO.md`** : « Problème de la double connexion API — *À lister si le besoin s'en fait sentir* » (§ Priorité Haute) et « Problème à documenter… — *Détails : …* » (§ Maintenabilité). Deux entrées sans contenu qui n'ont jamais été renseignées depuis leur création.
- **1 tâche obsolète archivée** : « Bouton "Discuter sur Gemini" » (branche `feature/discuter-gemini`, en attente de validation depuis le 2026-07-31) — abandonnée de fait le jour même par le **chat Gemini intégré** (`DealChatPanel.jsx`, Firebase AI Logic), qui la remplace et est validé en production. Déplacée dans `TODO_ARCHIVE.md` avec la raison de l'abandon (l'itération presse-papier/hand-off ne pouvait pas transmettre les photos).
- **Vérification demandée par l'utilisateur (UI/UX "je pense que c'est fait", Stats "à vérifier")** — lecture ciblée du code, résultat : **une seule des 6 tâches UI/UX était réellement close** (celle archivée ci-dessus). Les autres sont confirmées ouvertes, avec une note de vérification datée ajoutée dans `TODO.md` pour éviter de re-vérifier : sauvegarde des prompts encore en `onBlur` (`ConfigPanel.jsx`), fallback "ancienne architecture" villes toujours présent (`firestoreService.js::onCitiesUpdate`), recherche globale sans taxonomie ni autocomplétion (`useDealsManager.js::matchesTypeFilter`), 7 boutons toujours en place dans la modale (`DealCardActions.jsx`). Côté Stats, les 3 items restants (`discount_index`, "Cold Deals", badges "Certifié Expert") sont confirmés **non implémentés** — zéro occurrence dans `src/`/`backend/`/`prompts.json`, le seul "Certifié" existant étant l'étiquette de l'étape Funnel `Certifié (Expert T3)`.
- **Fusion du doublon "Dashboard Analytics & Statistiques"** (demande utilisateur, même session) : l'entrée `[/]` de la section UI/UX faisait doublon avec toute la section `📊 Statistiques & Dashboard`, nettement plus détaillée. Sa seule information propre (l'état du moteur de calcul, fonctionnel et branché sur les données réelles) a été reportée dans la tâche `[/] Mettre en place le moteur de statistiques`, qui devient le point de suivi unique. Un renvoi vers cette section remplace l'entrée retirée côté UI/UX.
- **Branche** : travail rebasé sur `origin/dev`, qui était **3 commits en avance sur `master`** (refonte du graphique liquidité en 2 courbes, clarification des 3 sections de stats, journalisation du bug `ArrayUnion`) — le point de départ de la session pointait sur `master`. `run_once.py` vérifié à `ACTIVE = False` au passage (protocole `CLAUDE.md`).

[2026-08-13] [PRO] Refonte du graphique Liquidité prédite vs Vitesse de vente réelle (2 courbes) → Résultat :
- **Retour utilisateur sur la clarification précédente** : le bar chart (une seule barre = délai réel, la "prédiction" n'apparaissant qu'en étiquette d'axe X) ne montrait pas explicitement la prédiction de l'IA — attente explicite de deux séries visibles simultanément, "probablement en courbes".
- **Première proposition écartée** : axes doubles (score prédit à gauche, délai réel à droite) — jugée contre-intuitive par l'utilisateur, car il faudrait lire des courbes qui *divergent* comme un signal positif.
- **Solution retenue** : `StatsView.jsx::liquiditySpeedData` calcule désormais deux séries sur une échelle unique 0-100 — le score de liquidité prédit (×10) et une "vitesse réelle" normalisée par tranche (100 = tranche la plus rapide à se vendre, 0 = la plus lente, calculée relativement aux tranches affichées). `LineChart` à un seul axe Y, deux courbes (`predictedScore`/`realSpeed`) : si la prédiction est fiable, les courbes se suivent (même sens) plutôt que de s'écarter — lecture intuitive. Tooltip affiche en plus le délai réel concret (h/j) et le nombre de ventes par tranche.
- **Validation** : `npm run build` OK. Constante `LIQUIDITY_TIER_COLORS` devenue inutile (coloration par `<Cell>` remplacée par les couleurs de trait des `<Line>`), supprimée.

[2026-08-13] [FLASH] Clarification de 3 sections de stats peu compréhensibles → Résultat :
- **Demande utilisateur :** "Score moyen par tranche de prix" (ex-Sweet Spot), "Véracité IA" et "Vitesse de vente réelle vs Liquidité prédite" jugées peu claires — ni la description, ni le graphique.
- **Root cause identifiée** : ces 3 croisements dépendent tous du score IA (Tier 2+), présent sur une toute petite fraction de l'inventaire (~87/3979 annonces au moment du diagnostic) — la confusion tenait autant à l'absence de contexte sur la taille d'échantillon qu'au wording lui-même.
- **Solution (`StatsView.jsx`, pas de changement de logique de calcul hors garde-fous mineurs)** : titres reformulés en questions directes ("Score IA élevé = vendu plus souvent ?", "La liquidité prédite par l'IA se confirme-t-elle ?"), sous-titres explicitant l'intention de chaque croisement, nombre d'observations affiché directement dans le libellé de chaque barre, avertissement ⚠️ conditionnel si l'échantillon total reste trop petit (<20 ventes tracées pour Véracité IA / Liquidité, <30 annonces pour Sweet Spot).
- **Validation** : `npm run build` OK.

[2026-08-12] [PRO] Fix critique : corruption `aiAnalysis` par `mark_deal_as_sold()` (ArrayUnion) + récupération gratuite → Résultat :
- **Symptôme** : régression stats signalée par l'utilisateur après le backfill de l'index léger (voir entrée suivante) — "Vitesse de vente par type de guitare" collapsé sur un seul type, Score IA Moyen incohérent (ex: "1/100").
- **Root cause** : `repository.py::mark_deal_as_sold()` écrivait `update_data['aiAnalysis'] = firestore.ArrayUnion([...])` sur un champ qui est un objet `{verdict, classification, scores...}` partout ailleurs dans le code (jamais un tableau). Cette écriture remplace silencieusement `aiAnalysis` par un tableau ne contenant que la note de vente, détruisant verdict/scores/classification d'origine. **Bug préexistant** (pas introduit cette session) mais rendu visible pour la première fois par le backfill de l'index, qui a propagé la corruption des documents bruts vers l'index léger jusque-là épargné.
- **Fix** : `mark_deal_as_sold()` écrit désormais la note de vente dans un nouveau champ dédié `soldNotes` (`ArrayUnion`), sans plus jamais toucher `aiAnalysis`.
- **Récupération** : ~3529 annonces vendues historiques trouvées avec `aiAnalysis` corrompu, aucun backup Firestore actif. Décision utilisateur explicite : récupérer d'abord ce qui est gratuit/instantané avant d'envisager le coûteux ("récupérons déjà ce que l'on peut", puis correction explicite quand une ré-analyse Gemini avait été proposée par erreur en premier lieu — "non tu disais qu'on pourrait récupérer 1300 annonces sans reanalyse"). `backend/scripts/recover_initial_verdict.py` (nouveau, aucun appel Gemini) reconstruit un `aiAnalysis` minimal `{verdict, model_used, reasoning}` depuis `initialVerdict` (champ figé à la création, jamais touché par ce bug) — ne récupère que le verdict, pas classification/scores/marge. Exécuté en production via `run_once.py` (protocole habituel) : **1313 annonces récupérées** sur les ~3529 corrompues.
- **`backend/scripts/reanalyze_sold_deals.py`** (nouveau, construit mais **non déclenché**) : ré-analyse Gemini complète du reste (~2216 annonces) via le pipeline normal (sans `force_expert`, qui forcerait aussi le Tier 3 pour chaque annonce — inutilement coûteux), en utilisant `storageImageUrls` (permanentes) plutôt que `imageUrls` (expirées). Verrou best-effort par fichier PID (déploiement déclenché sur `dev` et `master`, quasi simultané). **Reporté par décision explicite de l'utilisateur** ("on va laisser la reanalyse pour le moment") — coût estimé ~20-25$, plusieurs heures.
- **`run_once.py::ACTIVE`** repassé à `False` dans un commit séparé une fois le résultat de la récupération confirmé (protocole `CLAUDE.md` § Points d'Attention Critiques).

[2026-08-12] [PRO] Fix : régression stats après backfill (Score IA Moyen dilué + deltas de temps négatifs) → Résultat :
- **Score IA Moyen affichait des valeurs incohérentes** (ex: "1/100") : `averageScore` (`StatsView.jsx`) divisait la somme des scores par le nombre total d'annonces de l'inventaire au lieu du nombre d'annonces réellement scorées (Tier 2+) — biais énorme puisque seule une fraction de l'inventaire atteint ce palier. Fix : diviser par `scoredDeals.length`.
- **Barre négative sur le croisement Vitesse/Liquidité** : `soldTimestamp.seconds - publishTimestamp.seconds` pouvait être négatif sur données corrompues (voir entrée précédente), faussant fortement les moyennes sur petits échantillons. Fix : garde `d.soldTimestamp.seconds > d.publishTimestamp.seconds` ajoutée dans `sellTimeStats`, `sellSpeedByType` et `liquiditySpeedData`.

[2026-08-12] [PRO] Fix + exécution : backfill des scores IA via `run_once.py` en production → Résultat :
- **Premier essai (commit `3bc439d`) échoué** : `run_once.py` appelait `from backend.scripts.rebuild_index import rebuild`, mais `python3 backend/scripts/run_once.py` (invoqué depuis la racine par `deploy.yml`) n'ajoute que le dossier du script à `sys.path`, pas la racine du repo — `ModuleNotFoundError: No module named 'backend'`. Aucun impact (étape non bloquante, service redémarré normalement) — diagnostiqué via les logs GitHub Actions (`get_job_logs`, run #319).
- **Correctif** : `sys.path.insert(0, os.getcwd())` en tête de `run_once.py`, même pattern que `rebuild_index.py` utilise déjà pour son propre cas. Repoussé (commit `a616777`).
- **Résultat confirmé en production (run #321, ~6 min)** : `rebuild_index.rebuild()` a parcouru 7 utilisateurs, réindexé 4218 annonces au total (`8maOirmL5...`: 33, `EqiopsYIYDZ...`: 206, `wbPlgZgkW2...`: 3979). Service redémarré avec succès. `ACTIVE` repassé à `False` dans la foulée (protocole `CLAUDE.md` § Points d'Attention Critiques).
- **Méthode de vérification** : lecture directe des logs GitHub Actions via les outils MCP GitHub (`actions_list`/`actions_get`/`get_job_logs`) disponibles dans cette session — pas besoin d'accès Firestore ni de mécanisme de logs additionnel (proposition écartée d'un commun accord avec l'utilisateur).

[2026-08-06] [PRO] Feature : Script de maintenance ponctuel exécuté au déploiement (`run_once.py`) → Résultat :
- **Contexte** : l'environnement de dev n'a aucun accès à Firestore (pas de `.env`/`serviceAccountKey.json`) — impossible d'y exécuter `backend/scripts/rebuild_index.py` pour backfiller les nouveaux champs `ds`/`as`/`ls`/`rs` (voir entrée précédente). Demande utilisateur : un mécanisme réutilisable pour ce genre de besoin, pas un contournement ponctuel.
- **Solution** : `backend/scripts/run_once.py` (nouveau) — script gardé par un flag `ACTIVE` au niveau module (no-op par défaut), exécuté à chaque déploiement dans `.github/workflows/deploy.yml` (job `deploy`, après l'installation des dépendances Python, avant le redémarrage du service — seul contexte où les credentials Firebase sont en place). Étape non bloquante (`|| echo "⚠️ ..."`).
- **Protocole documenté** (`CLAUDE.md` § Points d'Attention Critiques) : activer + écrire l'action → déployer → vérifier les logs GitHub Actions → repasser `ACTIVE = False` immédiatement dans un commit séparé. Le job se déclenche sur push `master` **et** `dev`, donc une action ici s'exécute généralement deux fois de suite — n'y écrire que des actions idempotentes.
- **Premier usage** : `ACTIVE = True`, `run()` appelle `rebuild_index.rebuild()` pour backfiller les scores IA individuels. **État temporaire non refermé** — voir `TODO.md` § État opérationnel temporaire, à repasser `ACTIVE = False` une fois confirmé.

[2026-08-06] [PRO] Fix architecture : indexation des 5 scores IA individuels + déscopage complet de StatsView → Résultat :
- **Demande utilisateur (2 tours successifs)** : (1) contester que les stats ("Statistiques calculées sur 92 annonces") dépendent de l'onglet de filtre actif — "ce sont des statistiques générales" ; (2) refuser la limite technique initialement proposée (nouveau croisement vitesse/liquidité fiable seulement sur les deals déjà chargés en entier, à cause du scroll) — "je ne veux pas que les stats dépendent du scrolling, c'est une erreur de conception. Il faut le corriger pour l'ensemble."
- **Root cause commune aux deux demandes** : `StatsView.jsx` mélangeait deux échelles de données — la plupart des graphiques (compteur, Funnel, Radar, Marques, Couleurs, Volume) utilisaient `enrichedDeals` (l'onglet de verdict actuellement sélectionné dans le Dashboard, qui exclut `ARCHIVE_GROUP` sous "Toutes" : `BAD_DEAL`/`REJECTED_ITEM`/.../`SOLD`), tandis que Temps de Vente/Vitesse par type et les 5 croisements ajoutés en amont utilisaient déjà `enrichedAllDeals` (inventaire complet). Racine plus profonde pour le Radar Chart : `deal_score`/`authenticity_score`/`liquidity_score`/`restoration_interest_score` n'étaient **jamais indexés individuellement** dans `deals_index` — seule leur moyenne (`is`) l'était, et `useDealsManager.js` substituait silencieusement cette moyenne à `deal_score` pour toute annonce non chargée en entier (`loadedDeals`), biaisant le Radar et rendant tout croisement par score dépendant du scroll de l'utilisateur.
- **Solution backend** : `backend/repository.py::_update_deal_index()` indexe désormais `ds`/`as`/`ls`/`rs` (les 4 scores manquants), en plus de `cs` (condition_score) déjà indexé.
- **Solution frontend** : `useDealsManager.js` mappe ces 4 nouveaux champs correctement (`deal_score: entry.ds`, etc.), corrigeant l'alias vers la moyenne. `StatsView.jsx` : un seul jeu de données (`analysisDeals` = inventaire complet, `allDeals` en priorité sur `deals` filtré) utilisé partout — plus aucune dépendance à l'onglet actif ni au scroll. Le hint "Scroll pour charger les deals" du Radar, devenu faux, est retiré. Nouveau croisement **Vitesse de vente réelle vs `liquidity_score` prédit** (tranches Faible/Moyenne/Élevée), désormais calculable sur l'inventaire complet grâce à l'indexation.
- **Migration requise** : `backend/scripts/rebuild_index.py` (déjà multi-utilisateur, réutilise `_update_deal_index()` sans modification nécessaire) doit être lancé une fois en production pour backfiller `ds`/`as`/`ls`/`rs` sur les annonces déjà analysées — non exécutable depuis l'environnement de dev (pas d'accès Firestore). D'ici son exécution, seules les nouvelles analyses/ré-analyses ont ces champs.
- **Validation** : `npm run build` OK, rendu vérifié via Playwright + données mockées simulant un onglet filtré très restreint (ex: seulement `PEPITE`) vs l'inventaire complet — confirmé que le compteur et tous les graphiques reflètent bien l'inventaire complet, pas l'onglet simulé. Fichiers de test non commités.

[2026-08-06] [PRO] Feature : Statistiques croisées dans StatsView (Sweet Spot, catégories, source, géo) → Résultat :
- **Demande utilisateur :** tirer de vraies statistiques croisées (plusieurs dimensions combinées) des données déjà présentes, plutôt que des distributions simples déjà existantes (marque, couleur).
- **5 croisements ajoutés, tous à partir de l'index léger déjà chargé (`deals_index`), sans lecture Firestore supplémentaire :**
  1. Sweet Spot Prix × Score — score IA moyen par tranche de prix (0-250$ à 2000$+).
  2. Marge moyenne par catégorie — taxonomie résolue via une table exact+leaf simplifiée (`resolveCategoryLabel()`, sans la recherche floue de `useDealsManager.js`).
  3. Véracité IA — % de score élevé (≥7/10) parmi les annonces vendues vs l'ensemble du marché.
  4. Facebook vs Kijiji — volume, prix moyen, marge moyenne, taux d'opportunités par source (préfixe `kijiji_` de l'ID).
  5. Géographie des opportunités — volume/marge des verdicts `RADAR_GROUP` par ville.
- **Ces 3 premiers croisements comblent des items jamais implémentés de `docs/explanation/STATS_REFLEXION.md`** (§2 Sweet Spot/ROI catégorie, §4 Véracité IA, §5 Géographie) — voir ce fichier pour le détail produit, mis à jour en conséquence.
- **Validation** : pas de credentials Firebase dans l'environnement de dev — testé avec un jeu de données factices (120 deals mockés) rendu via un entry point Vite temporaire + Playwright (screenshot), confirmant l'absence d'erreur console et un rendu cohérent avec le style existant. `npm run build` passe sans erreur. Fichiers de test supprimés après validation (non commités).

[2026-08-06] [FLASH] Fix : Intervalle du nettoyage des annonces vendues réduit à 6h (anciennement 24h) → Résultat :
- **Demande utilisateur :** réduire la latence entre la suppression réelle d'une annonce et sa détection par le bot, pour améliorer la précision des stats de vitesse de vente (`soldAt`).
- **Solution :** `backend/services.py::TaskScheduler._setup_schedules()` — `schedule.every(24).hours.do(self.cleanup_func)` → `schedule.every(6).hours.do(self.cleanup_func)`.

[2026-08-06] [PRO] Fix : détection des annonces vendues (piste 3 du prompt Portier) + bug cleanup Kijiji → Résultat :
- **Demande utilisateur :** implémenter la piste 3 restante du bug "détection VENDU incomplète" (instruction explicite au Portier) et s'assurer qu'une annonce déjà analysée puis supprimée soit bien considérée comme vendue.
- **Piste 3 :** `prompts.json::gatekeeper_verbosity_instruction` instruit désormais le Portier (T1) de rejeter (`REJECTED_ITEM`) toute annonce dont le titre/description signale explicitement une vente déjà conclue ("VENDU", "SOLD", "deal closed"...), même si l'annonce est encore en ligne. Filet de sécurité IA complémentaire au filtre pré-IA `SOLD_MARKERS` existant, qui est volontairement contourné pour un scan manuel (`is_manual_scan=True`) — ce garde-fou côté Portier reste donc le seul filet sur ce chemin.
- **Bug trouvé en creusant la demande "annonce supprimée = vendue"** : `backend/bot.py::_perform_cleanup()` (job de nettoyage périodique) instanciait toujours `FacebookScraper` pour vérifier la disponibilité de **toutes** les annonces actives, y compris Kijiji. Une URL Kijiji ne contenant jamais `/marketplace/item/`, `FacebookScraper.check_listing_availability()` la classait systématiquement en "redirection détectée = supprimée" — chaque annonce Kijiji active aurait donc été marquée vendue à tort au prochain cycle. Corrigé : les annonces sont désormais groupées par source (préfixe `kijiji_` de l'ID) et vérifiées avec le bon scraper (`FacebookScraper`/`KijijiScraper`), factorisé dans `_check_listings_availability(scraper, listings)`.
- **Non testé en conditions réelles** (pas d'accès réseau Facebook/Kijiji/Playwright ni Gemini depuis l'environnement de dev) — à valider par l'utilisateur : prochain cycle de nettoyage (Kijiji non marqué vendu à tort) et une réanalyse manuelle sur une annonce dont le titre contient "VENDU".

[2026-08-06] [FLASH] Documentation : Archivage des tâches terminées de TODO.md → Résultat :
- **Constat :** `TODO.md` avait atteint 557 lignes, mélangeant tâches ouvertes et terminées, devenu difficile à consulter.
- **Solution :** création de `docs/management/TODO_ARCHIVE.md` — déplacement de toutes les tâches `[x]` (contenu et contexte technique intégralement conservés) vers ce nouveau fichier, classées par section d'origine. `TODO.md` réduit à 557 → 141 lignes, ne conservant que les tâches ouvertes (`[ ]`/`[/]`) et un lien vers l'archive. Doublon corrigé au passage : l'entrée "notifications ntfy de pépite" existait en double (une ouverte, une fermée) — confirmée réglée par l'utilisateur, archivée.

[2026-08-01] [PRO] Feature : couleur/finition/longueur de manche extraites par l'IA + filtres → Résultat :
- **Demande utilisateur :** `color` n'était en pratique presque jamais rempli malgré son existence ; il manquait la finition (peinture/vernis/teinture, brillant/satiné, sunburst...) et la longueur d'échelle du manche. Les finitions devaient être filtrables.
- **Diagnostic couleur :** `analyzer.py` ne touche jamais ce champ (aucune logique qui le filtre/écrase côté backend) — l'IA ne le renseignait quasiment jamais en pratique, l'instruction ("Couleur/finition exacte...") étant noyée sans insistance particulière dans un schéma JSON de 20+ champs, contrairement à l'identification de marque (déjà durcie explicitement en 2026-07-09 — examen systématique logo/plaque/numéro de série).
- **Solution :** `color` durci sur le même modèle (obligatoire dès qu'une photo montre l'instrument). `finish_application`/`finish_texture` ajoutés en **listes fermées** dans `prompts.json` (ex: "Peinture opaque"/"Vernis-Laque transparente"/"Teinture"/"Naturel-Brut" ; "Brillant"/"Satiné-Soyeux"/"Mat") plutôt qu'en texte libre — décision délibérée pour rester filtrables de façon fiable sans reproduire le problème de fuzzy-matching déjà rencontré sur la taxonomie. `neck_scale_length` rempli uniquement si déductible du modèle identifié ou visuellement évident, jamais deviné ("Inconnue" sinon). Indexation `fa`/`ft` dans `deals_index` (`backend/repository.py::_update_deal_index()`, même pattern que `b`/`mn`/`co`). Deux nouveaux filtres "Finition"/"Brillance" dans `FilterDrawer.jsx`. Fiche Technique (`DealAnalysisModal.jsx`) enrichie des 3 nouveaux champs. Pas de backfill — champs vides sur l'historique, remplis pour les nouvelles analyses seulement.
- **Bug trouvé par `/code-review` (2 exécutions indépendantes convergentes, corrigé) :** le filtre comparait `finish_application`/`finish_texture` en égalité stricte (`!==`), alors qu'`analyzer.py` fait un `json.loads()` brut sans `response_schema`/contrainte d'énum — une valeur qui dérive légèrement du texte exact demandé (espacement, casse) aurait rendu le filtre correspondant muet (zéro résultat) sans erreur visible, malgré un affichage correct dans la Fiche Technique. Exactement la classe de bug déjà rencontrée sur la taxonomie (`findPathFuzzy`). Corrigé par une comparaison sur chaînes normalisées (`normalize()`, même helper que la taxonomie) plutôt qu'un `!==` brut — tolère la variance de formatage sans réintroduire la recherche par sous-chaîne (non pertinente ici, valeurs courtes et fermées).
- **Résiduel identifié, non corrigé (même revue) :** les options de `FilterDrawer.jsx` dupliquent à la main la liste fermée du prompt plutôt que d'être dérivées dynamiquement (contrairement à `TAXONOMY_TREE`/`taxonomy_master`) — risque de dérive silencieuse si la liste change côté prompt. Nécessiterait de restructurer `prompts.json` pour que le texte d'instruction IA et les options de filtre partagent une source unique — refactor plus large que ce correctif, voir `TODO.md`.

[2026-08-01] [PRO] Feature : joindre une photo depuis le chat Gemini (prise sur place ou galerie) → Résultat :
- **Demande utilisateur :** pouvoir attacher une nouvelle photo (prise sur place chez le vendeur, ou choisie dans la galerie) à n'importe quel message du chat Gemini d'une annonce — pas seulement les photos déjà scrapées, envoyées uniquement sur le premier message.
- **Solution :** `geminiChatService.js::fileToInlinePart()` (redimensionnement/compression canvas partagé avec le chemin existant, `blobToInlinePart()` factorisé) ; `useDealChat.js::sendMessage(text, imageFile)` accepte une image optionnelle (message photo seule sans texte autorisé) ; `firestoreService.js::addDealChatMessage(..., attachedImagePartIndex)` référence l'index de la photo dans `parts[]` (pas de duplication du base64) ; `DealChatPanel.jsx` — bouton trombone, aperçu avant envoi, miniature dans la bulle.
- **Itération sur le sélecteur caméra/galerie (2 tests réels de l'utilisateur)** : `capture="environment"` sur l'`<input type="file">` force l'ouverture directe de l'appareil photo sur plusieurs navigateurs mobiles (confirmé) et son absence force à l'inverse la galerie/fichiers (confirmé) — aucune combinaison unique ne propose fiablement les deux. Résolu avec deux inputs cachés séparés, déclenchés par un petit menu "Prendre une photo" / "Choisir depuis la galerie" (même style que le menu Ré-analyser de `DealCardActions.jsx`).
- **4 bugs trouvés par `/code-review` et corrigés dans la foulée :**
  1. **Bug réel confirmé, régression sur le fix anti-chaîne (voir entrée ci-dessous)** — la purge défensive à l'hydratation (`useDealsManager.js`) avait la condition ancêtre/descendant inversée : gardait le chemin le plus large, jetait le plus spécifique.
  2. **Bug réel confirmé** — `fileToInlinePart()` non protégé par `try/catch` dans `sendMessage` : une photo non décodable laissait `sending` bloqué à `true` indéfiniment (chat verrouillé jusqu'au rechargement). `try/catch` ajouté, parallélisé avec `buildDealImageParts()` au passage (I/O indépendants).
  3. **Inefficacité confirmée** — la photo jointe était stockée deux fois en base64 (`parts[].inlineData` + un premier champ `attachedImage` séparé). Remplacé par la référence d'index `attachedImagePartIndex` ci-dessus.
  4. **Bug confirmé par test réel de l'utilisateur** — `capture="environment"` retirait l'option galerie (voir ci-dessus).

[2026-08-01] [PRO] Fix : Filtres de type multi-sélection sans effet quand toute une lignée est cochée → Résultat :
- **Symptôme signalé :** cocher plusieurs niveaux d'une même lignée de taxonomie (ex: Guitare + Acoustique + Formes Standard + Parlor) réaffichait toutes les guitares, comme si le filtre n'avait aucun effet.
- **Root cause (confirmée par un second avis, agent Opus indépendant) :** `matchesTypeFilter` (`useDealsManager.js`) matche un deal dès qu'**au moins un** chemin sélectionné est préfixe de son chemin résolu (OR). Avec "guitare" (racine) présent dans la sélection en plus de "Parlor", "guitare" seul suffit déjà à matcher toutes les guitares — les cases plus profondes deviennent des no-ops.
- **Solution :** `toggleTypePath` maintient la sélection en anti-chaîne — cocher un chemin retire ses ancêtres ET descendants déjà cochés (drill-down), en gardant la multi-sélection entre branches non apparentées (Parlor + Baby/Mini simultanément reste possible). Purge défensive de la sélection persistée en Firestore à l'hydratation. `FilterDrawer.jsx` : l'auto-expand d'une catégorie tient compte de ses descendants sélectionnés, pour que la case cochée reste visible après la purge de ses parents.
- **Deux fausses pistes explorées avant la vraie cause** (corrigées au passage, non responsables du symptôme principal) : `findPathFuzzy` (résolution de `classification` IA non exacte, ex: "Fender Stratocaster") préférait d'abord le chemin le plus profond, ce qui laissait un leaf court (`"SG"`) matcher tout texte contenant "s"+"g" à la jonction de deux mots (ex: "corde**s g**uitare", `normalize()` supprimant les espaces) ; puis la clé la plus longue trouvée en sous-chaîne, ce qui faisait dominer la branche `etui_housse` (leafs "Guitare Electrique"/"Guitare Acoustique"/"Basse" repris tels quels des types d'instruments). Durci : exclusion des clés courtes (< 5 caractères) et de la branche `etui_housse` de la recherche floue.
- **Résiduel identifié, non corrigé :** `guitare.basse` partage des noms de catégories avec `guitare.electrique`/`guitare.acoustique_acier` (`solid_body`, `specialites`) dans `leafPaths` — collision par écrasement (dernière branche traversée gagne). Voir `TODO.md`.
- **Feature (même session) :** badge `counts[currentVerdict]` ajouté sur le bouton fermé du sélecteur de statut (`VerdictDropdown`, `Dashboard.jsx`) — le total n'était visible auparavant que dans le menu déroulé.

[2026-07-21] [FLASH] Feature : Précision sur l'obligation de configuration initiale dans l'aide → Résultat :
- **`src/components/HelpOverlay.jsx`** : Ajout d'une "Étape 0 : Configuration Initiale" dans le Guide de Prise en Main, pour rappeler aux nouveaux utilisateurs que le bot ne démarrera pas tant qu'ils n'auront pas configuré leurs villes et fréquence dans les paramètres.

[2026-07-21] [FLASH] Fix : Enregistrement de l'email lors de la mise à jour de session pour les anciens comptes → Résultat :
- **`src/hooks/useAuth.js`** : La fonction `ensureUserDoc` met dorénavant systématiquement à jour le champ `email` à chaque connexion. Cela corrige l'absence de l'adresse email dans la liste du Dashboard Admin pour les anciens utilisateurs.

[2026-07-21] [PRO] Feature & Fix : Actions d'administration Dashboard + Droits Firestore → Résultat :
- **Contexte** : Ajout des fonctionnalités permettant à l'administrateur de mettre en pause, modifier la fréquence et supprimer des utilisateurs depuis l'UI du Dashboard Admin, ainsi que l'affichage de leurs villes et de la limite d'annonces.
- **`src/components/AdminDashboard.jsx`** : Implémentation des boutons et logique pour mettre à jour (`updateDoc`, `deleteDoc`) le statut du bot (`botStatus: 'paused'`), la fréquence de scan et supprimer un document utilisateur. Ajout d'une récupération dynamique du nombre de villes (`collection('cities')`).
- **`firebase/firestore.rules`** : Correction du blocage d'écriture. L'admin disposait d'un accès en lecture seule via `collectionGroup`. Les règles du path direct `/artifacts/{appId}/users/{userId}` ont été modifiées pour autoriser expressément `read` et `write` si `isAdmin()`, y compris sur ses sous-collections.

[2026-07-21] [PRO] Fix : Données manquantes dans StatsView & message d'erreur UI → Résultat :
- **Cause :** Les annonces vendues étaient cachées par défaut sur l'onglet "Toutes". De plus, le graphique de vitesse de vente exigeait `count >= 2` et la classification IA (absente pour les vieilles annonces), affichant un message confus sur les timestamps.
- **Correction `Dashboard.jsx` & `StatsView.jsx` :** Passage de `allDeals` à `StatsView` pour forcer le calcul sur toutes les annonces vendues (2049) peu importe l'onglet. Suppression de la limite `>= 2` observations pour le graphique de vitesse, et correction du texte d'erreur pour pointer l'absence de classification IA au lieu des dates.

[2026-07-20] [PRO] Feature : Dates de publication et de vente en fallback pour stats complètes → Résultat :
- **Cause :** L'absence de dates `published_at_ts` ou de détection de vente fiable laissait des "trous" dans les statistiques de l'UI (notamment le temps de vente).
- **`parser.py` :** Si l'âge de l'annonce n'est pas lisible ou absent, le bot utilise désormais la date et l'heure exactes du scraping (`time.time()`) comme `published_at_ts` par défaut.
- **`bot.py` & `repository.py` :** L'identification d'une annonce vendue est durcie. Si le bot détecte le mot "Vendu" dans une annonce **déjà existante** en base, il la marque officiellement comme `sold` et enregistre le `soldTimestamp` à la date de détection (SERVER_TIMESTAMP). Le script de `cleanup_sold_listings` utilise également la date de sa propre exécution (suppression) comme `soldTimestamp`.

[2026-07-20] [PRO] Fix : Plantage silencieux du scan + Erreur JSON de l'Expert Pro → Résultat :
- **Cause du plantage silencieux :** Lors du lancement manuel d'un scan, le backend recevait la commande, passait en `scanning`, mais plantait instantanément sans log. Le bug venait d'une `KeyError` sur l'attribut `name` des villes scrapées.
- **Correction `bot.py` :** Utilisation de `.get('name')` pour éviter un crash et ignore gracieusement l'absence d'attribut `name` ou une liste de villes vide (log d'avertissement au lieu de crasher).
- **Note (2026-07-20) :** Le correctif de `bot.py` a dû être ré-appliqué lors d'une session de vérification (il avait été perdu du code source malgré cette documentation). Les autres correctifs de cette date étaient bien présents.
- **Cause de l'erreur JSON Expert Pro :** L'API Gemini (en mode `application/json`) renvoyait l'erreur `Expecting ',' delimiter` car l'IA oubliait d'échapper des guillemets sur des champs longs comme le résumé de l'analyse, ce qui faisait planter `json.loads` et passer le verdict Expert Pro en fallback T2.
- **Correction `analyzer.py` :** Implémentation d'un mécanisme de `Retry` (1 tentative supplémentaire) dans `_call_gemini_json()`. En cas d'erreur `JSONDecodeError`, le script rajoute automatiquement un prompt strict (`CRITICAL: The previous JSON output was invalid...`) au modèle pour forcer un formatage JSON robuste et valide lors de la seconde tentative.

[2026-07-21] [PRO] Feature : StatsView — Volume de Scraping Quotidien (FB) → Résultat :
- **Contexte** : Réflexion en cours sur une extension LeBonCoin (voir options d'extraction face à DataDome, non tranchée). Avant toute décision, besoin de visualiser le volume réel actuel scrapé sur Facebook (jugé "extrêmement bas" par l'utilisateur).
- **`src/components/StatsView.jsx`** : Nouveau `useMemo` `dailyVolumeData` — regroupe `enrichedDeals` par jour sur les 14 derniers jours à partir de `timestamp.seconds`, déjà exposé en temps réel par l'index Firestore (`deals_index` → `useDealsManager.js`) pour 100% des annonces, pas seulement celles chargées en lazy loading. Aucune lecture Firestore supplémentaire. Nouveau panneau `BarChart` (recharts, même style que les graphiques existants) + StatCard "Moyenne/jour".
- **Suivi requis** : audit du scraper Facebook (mesures anti-bot actuelles/faiblesses) demandé par l'utilisateur, à traiter dans une session suivante.

[2026-07-21] [PRO] Fix : Traitement multi-villes gaspillé + absence de comptage des échecs de scan → Résultat :
- **Contexte** : Audit du scraper FB demandé par l'utilisateur suite au constat d'un volume très bas (max 5 annonces/jour sur 22 villes). L'utilisateur a écarté l'hypothèse du matching de ville strict comme cause principale, mais a identifié lui-même un gaspillage concret : une annonce d'une autre ville autorisée trouvée pendant le scan d'une ville X était fetchée en entier (fiche détail complète) puis jetée par le filtre STRICT de `run_scan()`, sans jamais être enregistrée — perdue si elle n'était pas reservie plus tard, ou refetchée intégralement une seconde fois si elle l'était.
- **`backend/scraping/core.py::scan_marketplace()`** : retourne désormais un dict (`deals`, `anti_bot_blocked`, `rejected_out_of_list`, `total_cards_seen`) au lieu d'une simple liste, via une nouvelle méthode `_scan_result()` utilisée à tous les points de sortie.
- **`backend/bot.py::run_scan()`** : le filtre STRICT (mode `distance=0`) passe d'un filtrage binaire (ville recherchée / rejet) à une logique à 3 voies — ville recherchée (inchangé), **autre ville autorisée de la liste (traitée immédiatement au lieu d'être jetée)**, hors liste (rejeté comme avant). Alimente `session_processed_ids` dès ce moment-là, évitant un refetch complet si Facebook la ressert au tour de cette autre ville.
- **`backend/bot.py::handle_deal_found()`** : retourne désormais un code de statut à chaque sortie (`scrape_failed`, `sold_marker`, `already_rejected`, `duplicate_unchanged`, `rejected_prefilter`, `processed`) au lieu de `None` partout — permet à `run_scan()` d'agréger un résumé de cycle loggé en fin de scan (visible LogViewer), demandé explicitement par l'utilisateur ("il faudrait aussi comptabiliser les échecs").
- **Non testé en conditions réelles** (pas d'accès Playwright/Facebook depuis cet environnement) — validation en prod à la charge de l'utilisateur avant ce commit de documentation.

[2026-07-21] [PRO] Fix : Curseur "Logs à 500" inopérant + notification de scan manuel enrichie → Résultat :
- **Symptôme signalé** : Le curseur "Limite Temporaire de Logs" (`ConfigPanel.jsx`) affichait bien 500 localement, mais la valeur restait à 100 côté Firestore/console.
- **`src/components/ConfigPanel.jsx` (`LogsConfigSection`)** : La sauvegarde ne se déclenchait que sur `onBlur` — un `<input type="range">` manipulé à la souris ne perd pas nécessairement le focus après un glisser-déposer si l'utilisateur ne clique pas ensuite sur un autre champ, donc `saveConfig()` n'était jamais appelé. Ajout de `onMouseUp`/`onKeyUp` (déclenchement fiable en fin d'interaction souris/clavier, sans debounce nécessaire car ils ne se déclenchent qu'une fois par interaction).
- **Contexte notification** : Question de l'utilisateur — un scan d'URL manuel indique-t-il déjà si l'annonce existait ? Non : `notify_scan_url_finished()` envoyait un message générique ("scan terminé") sans jamais distinguer nouveau/doublon/rejeté/vendu.
- **`backend/bot.py::scan_specific_url()`** : capture désormais le code de statut retourné par `handle_deal_found(..., is_manual_scan=True)` (introduit lors du fix multi-villes) et le transmet à la notification.
- **`backend/notifications.py::notify_scan_url_finished()`** : message adapté par code de statut (`processed`, `duplicate_unchanged`, `already_rejected`, `marked_sold`, `rejected_prefilter`, `scrape_failed`, `sold_marker`, ou échec de récupération si l'annonce n'a jamais pu être scrapée). Ajout d'un lien direct vers l'annonce dans Guitar Hunter (`?dealId={id}`, même schéma que `notify_deal()` pour les Pépites) dans l'email, en plus du lien Facebook original.
- **Non testé en conditions réelles** (pas d'accès Playwright/Facebook/SMTP depuis cet environnement) — à valider en prod par l'utilisateur.

[2026-07-21] [PRO] Fix : Timeout systématique "Erreur filtre prix" pendant le scan → Résultat :
- **Symptôme signalé** : Log récurrent `WARNING - Erreur filtre prix: Timeout 10000ms exceeded.` observé souvent en production.
- **Cause** : `backend/scraping/core.py::_apply_filters()` attendait `page.wait_for_load_state("networkidle", timeout=10000)` après validation du prix maximum. Facebook Marketplace (SPA avec trafic de fond permanent — notifications, chat, polling) n'atteint quasiment jamais un vrai silence réseau, donc cet appel expirait quasi systématiquement, gaspillant 10s par ville (~3-4 min/cycle sur 22 villes).
- **`backend/scraping/core.py`** : `wait_for_load_state("networkidle", ...)` remplacé par `wait_for_load_state("domcontentloaded", ...)` — se déclenche dès que le DOM est prêt, sans dépendre de l'arrêt total du trafic réseau. `time.sleep(3)` conservé juste après pour laisser le re-render se stabiliser.
- **Non testé en conditions réelles** (pas d'accès Playwright/Facebook depuis cet environnement) — à valider en prod par l'utilisateur.

[2026-07-21] [PRO] Feature : Scripts de calibration LeBonCoin (étape 1 du chantier d'extension) → Résultat :
- **Contexte** : Suite à la réflexion sur l'extension LeBonCoin (protégée par DataDome), décision de tester une approche Playwright "douce" (mêmes mesures stealth que le scraper Facebook, sans contournement actif type SSL Pinning/TLS spoofing) avant tout développement plus poussé — cf. options A-F évaluées, F écartée pour risque juridique/maintenance disproportionnés vu l'usage personnel/non-commercial.
- **`backend/scripts/leboncoin_login_once.py`** (nouveau) : script à lancer une fois en fenêtre visible — connexion manuelle à un compte LeBonCoin réchauffé par navigation préalable, sauvegarde de la session (`storage_state`) dans un fichier local non commité.
- **`backend/scripts/leboncoin_probe.py`** (nouveau) : charge cette session, ouvre une recherche LeBonCoin (rotation UA/viewport + flags stealth identiques à `FacebookScraper`), détecte explicitement un blocage (redirection `captcha-delivery.com`, HTTP 403/429, titre de page suspect). Aucune écriture Firestore — script de test uniquement, pas encore intégré à `bot.py`/`run_scan()`.
- **Limite assumée** : aucune extraction de contenu (titre/prix/photos) tentée — la structure DOM réelle de LeBonCoin n'a pas pu être vérifiée depuis l'environnement de développement (aucun accès réseau LeBonCoin possible ici). Si la sonde passe, elle sauvegarde le HTML complet localement pour permettre d'écrire des sélecteurs fiables à l'étape suivante, une fois un résultat réel observé par l'utilisateur.
- **`.gitignore`** : ajout de `backend/scripts/leboncoin_storage_state.json` (session/cookies, équivalent à des identifiants) et des artefacts de debug (`leboncoin_probe_*.png/html`).
- **Non testé en conditions réelles** (aucun accès réseau LeBonCoin depuis cet environnement) — calibration à la charge de l'utilisateur.

[2026-07-21] [PRO] Fix : leboncoin_login_once.py non furtif → fenêtre de login jamais chargée → Résultat :
- **Symptôme signalé** : Premier test de calibration — la fenêtre ouverte par `leboncoin_login_once.py` ne chargeait pas `leboncoin.fr`, obligeant l'utilisateur à se connecter dans un autre navigateur (jamais capturé par Playwright). La session sauvegardée était donc anonyme, invalidant le premier test (403 immédiat non concluant sur l'hypothèse "compte réchauffé").
- **Cause probable** : `leboncoin_login_once.py` lançait Chromium sans aucune des mesures de furtivité déjà présentes dans `leboncoin_probe.py` (pas de flags anti-détection, pas de rotation UA/viewport) — la fenêtre de login elle-même était probablement bloquée par DataDome avant que la connexion manuelle ait pu avoir lieu.
- **`backend/scripts/leboncoin_login_once.py`** : alignement sur les mêmes flags Chromium (`--disable-blink-features=AutomationControlled`, etc.) et la même rotation UA/viewport que `leboncoin_probe.py`.
- **Non testé en conditions réelles** — nouvelle tentative de calibration à la charge de l'utilisateur.

[2026-07-21] [PRO] Feature : Calibration LeBonCoin réussie + première extraction (JSON __NEXT_DATA__) → Résultat :
- **Résultat de calibration** : avec une vraie session authentifiée (login corrigé pour utiliser les mêmes mesures stealth que la sonde), une recherche LeBonCoin charge **sans blocage DataDome**. L'approche Playwright "douce" (sans SSL Pinning/TLS spoofing) est donc viable, au moins à ce stade — le premier test bloqué (403 immédiat) était un faux négatif dû à une session anonyme testée par erreur.
- **Découverte clé** : LeBonCoin (Next.js) embarque les résultats de recherche en JSON structuré dans `<script id="__NEXT_DATA__">` (`props.pageProps.searchData.ads`) — bien plus robuste que des sélecteurs CSS. Confirmé sur un vrai fichier HTML fourni par l'utilisateur (35 annonces, 110 au total pour la recherche).
- **`backend/scripts/leboncoin_probe.py`** : nouvelle fonction `extract_ads()` — parse ce JSON et retourne une liste blanche stricte de champs (`id`, `title`, `price`, `description`, `url`, `published_at`, `location.{city,zipcode,lat,lng}`, `image_urls`). Le bloc `owner` (pseudo/user_id/store_id vendeur, présent dans le JSON brut) est **délibérément exclu** — conforme à la règle "pas de données personnelles" fixée dès le départ de ce chantier. Résultats affichés en console + sauvegardés dans un JSON local (`leboncoin_probe_results.json`, gitignore) — toujours aucune écriture Firestore.
- **Testé** : `extract_ads()` validé directement contre le fichier HTML réel fourni par l'utilisateur (35/35 annonces extraites correctement, aucun champ `owner` présent dans le résultat).
- **Limite restante** : le `body` (description complète) est vide sur la page de résultats — nécessitera de visiter chaque fiche détail à l'étape suivante, non fait à ce stade.

[2026-07-21] [PRO] Feature : Filtrage ville(s)/catégorie/prix/tri pour la sonde LeBonCoin → Résultat :
- **Bug corrigé** : le filtre de prix envoyait `price=min-{max}` (le mot "min" en dur) au lieu du vrai format `price={min}-{max}` (deux nombres) — confirmé via une vraie URL fournie par l'utilisateur.
- **`backend/scripts/leboncoin_probe.py`** : nouveaux paramètres `--category` (défaut `30`, Instruments de musique), `--locations` (multi-villes via virgule — valeur brute à copier depuis une recherche manuelle sur leboncoin.fr, format non deviné/reconstruit car il varie selon que la ville a un code postal unique ou non), `--min-price`, `--owner-type` (`private`/`pro`). `sort=time&order=desc` (annonces les plus récentes en premier) désormais systématique, cohérent avec l'objectif du projet.
- **Vérifié** : construction d'URL testée en isolation contre 2 vraies URLs fournies par l'utilisateur (recherche à 1 ville puis à 2 villes) — reproduction identique caractère pour caractère.
- **Décision produit (utilisateur)** : extraction de la description complète non poursuivie (jugée peu utile en pratique) — photos/titre/prix suffisent.

[2026-07-22] [PRO] Feature : Module `backend/scraping_leboncoin/` (classe LeboncoinScraper) + revue de code (8 bugs corrigés) → Résultat :
- **Contexte** : Restructuration de la logique de `leboncoin_probe.py` en module réutilisable, avec deux ajouts demandés par l'utilisateur : pagination fiable (`max_pages` déjà présent dans le JSON `__NEXT_DATA__`) et comportement anti-prévisibilité — une session qui ouvre/attend un temps fixe/ferme à l'identique à chaque cycle est elle-même un signal comportemental détectable dans la durée (pas seulement le challenge JS initial).
- **`backend/scraping_leboncoin/core.py`** (nouveau) : classe `LeboncoinScraper` — session Playwright réutilisable sur plusieurs recherches (pas de fermeture systématique), pagination via `max_pages`, délais aléatoires, scroll/mouvement de souris simulés (sans besoin fonctionnel, juste comportemental). `leboncoin_login_once.py` importe désormais ses constantes UA/viewports depuis ce module plutôt que de les dupliquer.
- **`/code-review` (haute exigence, 8 angles + vérification 1-vote)** : 10 findings retenus (8 confirmés, 2 plausibles). Corrigés :
  1. Faux positifs de blocage — `responses` (réponses réseau) n'était jamais vidée entre pages de pagination, un vieux 403 d'une ressource tierce (pub/tracker) sur la page 1 pouvait faire échouer à tort la détection sur la page 3. Fix : `responses.clear()` en début de chaque itération.
  2. `--min-price` seul silencieusement ignoré (`build_url` n'ajoutait le filtre prix que si `max_price > 0`). Fix : déclenché dès qu'une borne est fournie, borne absente laissée vide (`price=50-` / `price=-200`).
  3. Crash `TypeError` si `searchData.ads` vaut `null` en JSON (clé présente mais valeur nulle, hors du `try/except` existant). Fix : garde-fou explicite.
  4. `leboncoin_probe.py --repeat` : une exception en cours de boucle faisait perdre les résultats déjà collectés (jamais écrits sur disque). Fix : sauvegarde déplacée dans le `finally`.
  5. Échec d'extraction et "0 résultat normal" retournaient la même forme, indiscernables pour l'appelant. Fix : raison explicite `"extraction_failed: ..."` retournée au lieu de `None`.
  6. `max_pages_limit=0` traité comme "pas de limite" (test de vérité sur un entier, faux pour 0). Fix : test `is not None`.
  7. Log de pagination affichait "page 1/1" même quand la recherche a plusieurs pages (dénominateur affiché avant d'être connu). Fix : n'affiche le total qu'une fois réellement connu.
  8. Capture d'écran (blocage) et dump HTML (échec d'extraction) — présents dans l'ancien script, disparus lors de la restructuration en module. Restaurés.
- **2 findings plausibles non corrigés dans le code** (jugements d'architecture, notés dans `TODO.md`) : duplication de mesures anti-bot avec `FacebookScraper` (base commune à envisager, surtout si des règles anti-détection communes — ex: plage horaire humaine — sont appliquées aux deux scrapers) ; réécriture complète de `leboncoin_probe.py` (zone grise sur la règle CLAUDE.md "pas de réécriture de fichier complet", scope explicitement approuvé par l'utilisateur).
- **Testé** : `build_url` et `extract_ads` corrigés revérifiés en isolation contre le vrai fichier HTML fourni précédemment (35 annonces, `max_pages=4`) et plusieurs cas de bornes de prix (min seul / max seul / les deux / aucun). **Non testé en conditions réelles Playwright/DataDome** depuis cet environnement.

[2026-07-22] [PRO] Fix : Timeout Playwright sur page.goto() en conditions réelles → Résultat :
- **Symptôme signalé** : `playwright._impl._errors.TimeoutError: Page.goto: Timeout 30000ms exceeded` lors d'un test réel — la page semblait pourtant se charger normalement à l'œil.
- **Cause** : `page.goto()` utilisait le défaut Playwright `wait_until="load"`, qui attend que **toutes** les ressources de la page (pubs, trackers, scripts tiers) aient fini de charger — même famille de piège que le fix `networkidle` du scraper Facebook (`_apply_filters`), une SPA avec du trafic de fond permanent ne déclenche jamais cet événement.
- **`backend/scraping_leboncoin/core.py::search()`** : `page.goto(url, timeout=30000)` → `page.goto(url, timeout=0, wait_until="domcontentloaded")`. `timeout=0` (convention Playwright "pas de timeout") répond à la demande explicite de l'utilisateur — la page ne se ferme plus jamais automatiquement, fermeture manuelle à sa charge. `wait_until="domcontentloaded"` (au lieu de `"load"`) devrait faire aboutir la navigation rapidement dans la plupart des cas sans même nécessiter d'attente longue.
- **Non testé en conditions réelles** — validation à la charge de l'utilisateur.

[2026-07-22] [PRO] Fix : Sonde LeBonCoin validée en conditions réelles — page persistante + boucle interactive → Résultat :
- **Blocage réel observé** : après ~4 tests dans la journée, un `--repeat 3` a déclenché un 403 sur `auth.leboncoin.fr/user` accompagné d'un slider DataDome visible à l'écran — mais la page se fermait automatiquement avant que l'utilisateur ait pu tenter de le résoudre à la main.
- **`backend/scraping_leboncoin/core.py::search()`** : ne ferme plus jamais la page elle-même (ni en cas de succès, ni de blocage, ni d'échec d'extraction) — un onglet unique (`self.page`, créé via `_get_page()`) est désormais réutilisé pour toutes les recherches de la session, au lieu d'un nouvel onglet ouvert puis fermé à chaque appel. Seule `close_session()` ferme réellement le navigateur.
- **`backend/scripts/leboncoin_probe.py`** : `--repeat` (nombre fixe défini au lancement) remplacé par une boucle interactive — après chaque recherche, l'utilisateur choisit `[Entrée]` relancer la même recherche, `[n]` nouveaux paramètres, ou `[q]` quitter. Une seule fenêtre ouverte du lancement du script jusqu'à la sortie explicite ; plus aucune fermeture/réouverture entre deux tests.
- **Testé et validé en conditions réelles par l'utilisateur** : pagination, extraction et boucle interactive fonctionnent comme prévu — l'onglet reste ouvert et est réutilisé entre recherches, fermeture uniquement sur `q`.

[2026-07-22] [PRO] Fix : Fenêtre fermée automatiquement malgré la demande + simulation de navigation silencieuse → Résultat :
- **Symptôme signalé** : après le fix du timeout `page.goto()`, la fenêtre du navigateur se fermait quand même en fin de script — le `timeout=0` ne portait que sur le chargement de la page, pas sur la fin du script. Également : aucun scroll/mouvement de souris visible pendant les tests, alors que `_simulate_browsing()` est censé en produire.
- **`backend/scripts/leboncoin_probe.py`** : ajout d'un `input("Appuie sur Entrée pour fermer...")` juste avant `scraper.close_session()` dans le `finally` — la fenêtre reste ouverte tant que l'utilisateur ne valide pas lui-même, au lieu d'une fermeture automatique imposée en fin de script.
- **`backend/scraping_leboncoin/core.py::_simulate_browsing()`** : le `except` loguait en `debug` (invisible au niveau `INFO` utilisé par le script) — passé en `warning` pour qu'un échec silencieux du scroll/mouvement de souris soit désormais visible et diagnosticable.
- **Non testé en conditions réelles** — validation à la charge de l'utilisateur.

[2026-07-19] [PRO] Fix : MapView — zoom reset au clic mobile → Résultat :
- **Cause :** Le `useEffect` de création des marqueurs dépendait de `selectedDealId`, ce qui déclenchait un `fitBounds()` à chaque sélection d'annonce sur mobile.
- **`src/components/MapView.jsx`** : Split en 2 effets indépendants. Effet 1 `[map, deals, onDealSelect]` crée les marqueurs + `fitBounds` (une seule fois à chaque changement de dataset). Effet 2 `[selectedDealId, map]` met uniquement à jour `scale`/`strokeWeight` via `markerByIdRef` — aucun fitBounds déclenché au clic. Ajout de `markerByIdRef` (Map dealId → marker).

[2026-07-19] [PRO] Fix + Feature : StatsView — Profil Moyen vide, Distribution marques biaisée, Temps de vente figé + nouveau graphique → Résultat :
- **Radar "Profil Moyen" vide :** `totalFilteredDeals` ne contenait que les champs de l'index léger (scores IA absents). Fix : `enrichedDeals` = fusion index + cache `loadedDeals` (lazy). `loadedDeals` exposé depuis `useDealsManager` et transmis par `Dashboard.jsx` via prop.
- **Distribution marques → tout dans "Autres" :** Fallback titre limité à 5 marques + troncature `split(' ')[0]` trop agressive. Fix : liste de 25+ marques QC connues dans le fallback titre, invalidation stricte des valeurs génériques (`"Inconnue"`, `"n/a"`…), "Autres" relégué en dernier hors top 6, coloration différenciée via `Cell`.
- **Temps de vente figé à 48h :** Calcul réel `soldTimestamp - publishTimestamp` (en heures ou jours selon durée). Subtitle indique le nombre de deals tracés (actuellement 1 deal → 59j).
- **Nouveau graphique "Vitesse de vente par type de guitare" :** Délai moyen de vente par `classification`, trié plus rapide → plus lent, gradient émeraude, min 2 observations par type.

[2026-07-19] [PRO] Fix : Filtre pré-IA annonces "VENDU" → Résultat :
- **`backend/bot.py`** : Ajout d'un filtre `SOLD_MARKERS` (`vendu`, `sold`, `deal closed`, `plus disponible`, `no longer available`) dans `handle_deal_found()`, vérifié sur titre + 200 premiers chars de description. Rejet **avant** `session_processed_ids.add()` (annonce non marquée comme traitée → re-détectable si le vendeur corrige son titre). Bypass par `is_manual_scan=True`. Log `⏩` visible dans le LogViewer. Aucun token Gemini consommé pour ces rejets.
- **`docs/management/TODO.md`** : Entrée ajoutée avec les 3 pistes de correction ; piste 1 (filtre pré-IA) marquée ✅ implémentée.



[2026-07-19] [PRO] Fix : Code review 48h — 4 correctifs appliqués → Résultat :
- **`backend/scraping/parser.py`** : Ajout du cas `"il y a X mois"` dans `parse_french_date()` (formule Facebook fréquente, sans ce cas les annonces de 1-3 mois n'avaient pas de `publishTimestamp` et tombaient en fond de tri). Remplacement du regex mois générique `[a-zûé]+` par la liste exhaustive des 12 mois français pour éviter les faux positifs sur des mots inattendus.
- **`backend/repository.py`** : Transformation de `purge_rejected_images()` — passage d'un `.limit(200)` unique à une boucle `while True / break si len(docs) < BATCH_SIZE` pour épuiser un arriéré potentiel si la purge n'a pas tourné pendant plusieurs jours.
- **`src/hooks/useDealsManager.js`** : Ajout d'un `useRef fetchingIdsRef` (Set) pour tracker les IDs en cours de fetch et éviter les double-appels réseau lors de scrolls rapides ou re-renders consécutifs. Libération des IDs dans `.finally()` pour couvrir succès et erreur.
- **`scripts/build_deals_index.py`** : Ajout d'un warning explicite (`print`) si `ListingParser` est `None` suite à un `ImportError`, avec la commande correcte pour lancer le script depuis la racine du projet.

[2026-07-18] [PRO 3.1] Fix : Tableau de bord vide suite Ã  la mise en place du Lazy Loading â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : L'utilisateur ne voyait plus aucune annonce sur son tableau de bord aprÃ¨s la migration vers l'index allÃ©gÃ©.
- **Diagnostic** : Le nouveau script de migration `build_deals_index.py` crÃ©ait un index lÃ©ger qui retirait intentionnellement le champ `reasoning` de l'IA (trop volumineux) pour Ã©conomiser l'espace. Or, `useDealsManager.js` vÃ©rifiait encore la prÃ©sence de `analysis.reasoning` pour certifier qu'une annonce n'Ã©tait pas une erreur IA.
- **`src/hooks/useDealsManager.js`** : Suppression stricte de la dÃ©pendance Ã  `analysis.reasoning` dans `matchesVerdictFilter` et `verdictCounts`. Les filtres s'appuient dÃ©sormais uniquement sur le verdict et les classifications prÃ©sentes dans l'index. Le tableau de bord affiche de nouveau toutes les annonces et profite de la fluiditÃ© et des Ã©conomies du Lazy Loading.

[2026-07-18] [PRO] Fix : Partage d'annonces (Analyse IA tronquÃ©e) â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : Lorsqu'un utilisateur partageait une annonce, le lien gÃ©nÃ©rÃ© affichait une version rÃ©duite sans le verdict ni l'analyse complÃ¨te de l'IA.
- **`src/services/firestoreService.js`** : Mise Ã  jour de `createSharedDeal` pour qu'il puise correctement le verdict, l'analyse (`reasoning`) et les scores depuis l'objet imbriquÃ© `deal.aiAnalysis` (au lieu de les chercher Ã  la racine de `deal`). Les liens partagÃ©s affichent dÃ©sormais l'intÃ©gralitÃ© du travail de l'Expert IA.

[2026-07-18] [PRO] Feature : Notification (ntfy + email) Ã  la fin d'un scan d'URL manuel â†’ RÃ©sultat :
- **Contexte** : Demande d'Ãªtre informÃ© de la fin d'une requÃªte de scan d'URL.
- **`backend/notifications.py`** : Ajout de la mÃ©thode statique `notify_scan_url_finished(url, user_email, logger)` qui envoie un ntfy et un email au demandeur.
- **`backend/bot.py`** : Appel de la notification dans le bloc `try/finally` de `scan_specific_url` une fois le scraper temporaire terminÃ©.

[2026-07-18] [PRO] Refactor : Optimisation massive des coÃ»ts de lecture Firestore via Sharded Index Document et Lazy Loading â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : CoÃ»ts de lecture Firestore astronomiques (~15$/mois pour 40 millions de lectures) causÃ©s par le chargement intÃ©gral des 2748 annonces au dÃ©marrage.
- **Architecture d'Index Document ShardÃ© (`deals_index/`)** : CrÃ©ation d'un index allÃ©gÃ© contenant uniquement les mÃ©tadonnÃ©es de filtrage/tri/compteurs (10 propriÃ©tÃ©s, ~100 octets/annonce) divisÃ© uniformÃ©ment en 20 chunks pour Ã©viter la limite Firestore d'indexation par document (INDEX_ENTRIES_COUNT_LIMIT_EXCEEDED).
- **Frontend (`src/services/firestoreService.js`, `src/hooks/useDealsManager.js`)** : Hydratation initiale sur l'Ã©couteur d'index (seulement 20 lectures Firestore). Les annonces complÃ¨tes (images, description, analyse IA longue) sont tÃ©lÃ©chargÃ©es par paquets de 30 uniquement lorsqu'elles entrent dans la zone visible de l'Ã©cran (Lazy Loading avec cache local rÃ©utilisable).
- **Backend (`backend/repository.py`)** : Maintien chirurgical de l'index en dot-notation Ã  chaque crÃ©ation, modification ou suppression d'annonce, sans aucune lecture Firestore supplÃ©mentaire.
- **Migration (`scripts/build_deals_index.py`)** : Script de migration exÃ©cutÃ© avec succÃ¨s pour peupler initialement l'index de toutes les annonces existantes et injecter les `chunkId` correspondants.
- **Optimisation Backend additionnelle (`backend/repository.py`)** : Ciblage strict de `status == 'analyzed'` dans `get_active_listings()`, et limitation de la tÃ¢che de purge `purge_rejected_images` via `limit(200)` pour rÃ©duire les lectures de maintenance.

[2026-07-15] [PRO] Fix : 4 bugs remontÃ©s (vendues non identifiÃ©es, bruit non catÃ©gorisÃ©, favoris polluÃ©s) + persistance des filtres par utilisateur â†’ RÃ©sultat :
- **Contexte** : 5 points remontÃ©s par l'utilisateur. Investigation (docs + code frontend/backend + agent Explore sur `bot.py`/`analyzer.py`/`core.py`) avant tout code, conformÃ©ment au protocole.
- **Annonce vendue non identifiÃ©e (frontend)** : `DealCard.jsx` n'affichait **aucun** indicateur pour `deal.status === 'sold'` (ni badge, ni opacitÃ©) â€” le badge de verdict d'origine restait affichÃ© tel quel. Ajout d'un badge "Vendu" (icÃ´ne `Ban`) + opacitÃ© rÃ©duite (`opacity-60 saturate-50`), dans la carte ET la modale, indÃ©pendamment du verdict.
- **Annonces "dans le bruit" sans label (frontend)** : cause identifiÃ©e en lisant `analyzer.py` â€” un double-Ã©chec IA (Tier 1 **et** Tier 2 en erreur) produit un verdict `ERROR_GATEKEEPER` avec un `reasoning` non vide. Ce verdict Ã©chappait Ã  la fois au filtre `isError` de `useDealsManager.js` (qui ne dÃ©tectait que `DEFAULT`/`ERROR` littÃ©raux ou reasoning vide) et Ã  `ARCHIVE_GROUP` (`constants.js`) â†’ il atterrissait dans la vue "Toutes" avec le badge par dÃ©faut trompeur ("Analyse..."). `isError` Ã©largi pour couvrir tout verdict absent de la taxonomie connue (`NEW_VERDICTS`/`LEGACY_VERDICTS`/`ARCHIVE_GROUP`), pas seulement les valeurs littÃ©rales `DEFAULT`/`ERROR`.
- **Favoris incluant du bruit (frontend)** : `matchesVerdictFilter` retournait `deal.isFavorite` sans filtrer le verdict pour le cas `FAVORITES`. Exclusion dÃ©sormais des verdicts archivÃ©s (`REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA`, `REJECTED`) et des erreurs, en gardant `BAD_DEAL` ("trop cher" confirmÃ© comme favori lÃ©gitime par l'utilisateur). Le compteur `verdictCounts.FAVORITES` (2 emplacements) corrigÃ© pour rester cohÃ©rent avec la liste affichÃ©e.
- **Annonces supprimÃ©es de Facebook encore visibles (backend, diagnostiquÃ©, non corrigÃ©)** : le bot dÃ©tecte dÃ©jÃ  les annonces supprimÃ©es par le vendeur (404, redirection vers l'accueil Marketplace dans `check_listing_availability`, `backend/scraping/core.py`) â€” fusionnÃ©es avec la dÃ©tection de vente (`status: 'sold'`, pas de statut "supprimÃ©" distinct). Le nettoyage (`cleanup_sold_listings`) tourne automatiquement toutes les 24h (`schedule.every(24).hours`, `backend/services.py`) â†’ latence normale jusqu'Ã  24h, pas un bug. Le "ralentissement du chargement" perÃ§u vient probablement plutÃ´t du fait qu'`onDealsUpdate` charge **toute** la collection `guitar_deals` (y compris vendues/rejetÃ©es, jamais purgÃ©es) Ã  chaque connexion. Ces deux constats ajoutÃ©s au `TODO.md`, non corrigÃ©s (dÃ©cision produit Ã  trancher : rÃ©duire l'intervalle ? filtrer/paginer cÃ´tÃ© serveur ?).
- **Persistance des filtres par utilisateur (Firestore)** : `useBotConfig.js` â€” nouvel Ã©tat `uiFilters` (lu depuis le doc utilisateur au mÃªme titre que `scanConfig`/`analysisConfig`) + `saveUiFilters` (Ã©criture debouncÃ©e 800ms). `DealsContext.jsx` relaie vers `useDealsManager`, qui hydrate une seule fois au premier chargement puis sauvegarde automatiquement Ã  chaque changement (`filterType`, niveaux 1-4, condition, prix, `sortMode`) â€” la recherche texte libre n'est pas persistÃ©e.
- **VÃ©rifiÃ©** : build/console propres (`npm run dev`), rendu de la page de login OK. Non testÃ© en conditions rÃ©elles avec des annonces (nÃ©cessite authentification) â€” confirmÃ© fonctionnel par l'utilisateur avant push.

[2026-07-14] [PRO] Fix : DÃ©filement fixe (3 scrolls) limitant le nombre d'annonces scrapÃ©es par ville â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : l'utilisateur constate que beaucoup d'annonces ne sont pas listÃ©es dans l'app, malgrÃ© 12 villes configurÃ©es et un `max_ads` rÃ©glÃ© Ã  50.
- **Cause confirmÃ©e par lecture du code (pas d'accÃ¨s aux logs de prod depuis cet environnement)** : `run_scan()` (`bot.py`) applique `max_ads` **par ville** (pas globalement) â€” avec 12 villes ce n'est donc pas le plafond limitant. Le vrai goulot : `ScraperConfig.scroll_iterations` Ã©tait fixÃ© en dur Ã  3 (`backend/scraping/config.py`), non exposÃ© dans Firestore/`ConfigPanel`. `scan_marketplace()` ne scrollait que 3 fois avant de lire les cartes d'annonces chargÃ©es dans le DOM (`backend/scraping/core.py`) â€” ce plafond Ã©tait atteint bien avant `max_ads`, quel que soit le volume rÃ©el de rÃ©sultats Facebook pour une ville donnÃ©e.
- **Piste Ã©cartÃ©e par l'utilisateur** : le matching strict de localisation (`is_city_allowed()`, mode `distance=0`) est un choix assumÃ©, pas un bug â€” non modifiÃ©.
- **`backend/scraping/config.py`** : `scroll_iterations` (fixe) â†’ `max_scroll_iterations` (garde-fou, dÃ©faut 20).
- **`backend/scraping/core.py::scan_marketplace()`** : scroll dynamique â€” la boucle s'arrÃªte dÃ¨s que le nombre de cartes chargÃ©es atteint `max_ads`, ou stagne sur 2 itÃ©rations consÃ©cutives (fin de liste rÃ©elle), sinon continue jusqu'au plafond de sÃ©curitÃ©.
- **Non testÃ© en conditions rÃ©elles depuis cet environnement** (pas d'accÃ¨s Ã  un compte Facebook/Playwright live) â€” seule la syntaxe Python a Ã©tÃ© vÃ©rifiÃ©e avant de committer ; validation en prod Ã  la charge de l'utilisateur.

[2026-07-14] [PRO] Feature : Note d'intÃ©rÃªt IA par annonce + choix de tri (Date / IntÃ©rÃªt) â†’ RÃ©sultat :
- **Contexte** : Demande utilisateur â€” pouvoir dÃ©partager les annonces qui ne sont pas des "PÃ©pites" selon leur intÃ©rÃªt, plutÃ´t que de les subir dans l'ordre chronologique imposÃ© par `onDealsUpdate` (`firestoreService.js`).
- **`src/constants.js`** : nouvelle fonction `computeInterestScore(aiAnalysis)` â€” moyenne des 5 scores IA dÃ©jÃ  existants (`deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, `restoration_interest_score`). Purement client-side, aucun nouveau champ Firestore/backend.
- **`src/hooks/useDealsManager.js`** : nouvel Ã©tat `sortMode` (`'date'` par dÃ©faut, `'interest'` en option), exposÃ© via `filterProps`. `filteredDeals` retriÃ© par note dÃ©croissante en mode `'interest'`, avec repli sur l'ordre par date pour les annonces sans scores (erreurs, `PENDING`).
- **`src/components/FilterDrawer.jsx`** : nouvelle section "Trier par" en tÃªte du tiroir de filtres (options "Plus rÃ©centes" / "Plus intÃ©ressantes (note IA)").
- **`src/components/Dashboard.jsx`** : relais `sortMode`/`setSortMode` entre `useDealsManager` et `FilterDrawer` (clÃ© `sort`, sans mapping `'all'`/`'ALL'` contrairement aux autres filtres).
- **`src/components/DealCard.jsx`** : badge "Note X.X/10" affichÃ© Ã  cÃ´tÃ© du badge de verdict, absent si aucun score disponible.
- **VÃ©rification** : `npm run build` (Vite) passe sans erreur aprÃ¨s les 5 modifications.

[2026-07-13] [PRO] Fix : Menu "RÃ©-analyser" (options de rescan) de la carte annonce inaccessible au survol sur desktop â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : sur l'interface ordinateur, les options du menu RÃ©-analyser (Scan Standard, Luthier Expert, Avec commentaire...) disparaissent souvent avant qu'on puisse cliquer dessus ; quand on y arrive, rien ne se passe (ni rescan lancÃ©, ni popup de commentaire). Meilleur fonctionnement sur mobile.
- **Cause confirmÃ©e** : mÃªme famille de bug que le fix Navbar du 2026-07-11 (ci-dessous), mais sur un gap **vertical** cette fois. Le conteneur `.relative` qui gÃ¨re `onMouseEnter`/`onMouseLeave` (`DealCard.jsx`) n'englobe que le bouton RefreshCw (40Ã—40px) ; le menu dÃ©roulant Ã©tait positionnÃ© avec `bottom-full mb-2` (carte) / `top-full mt-2` (modale) â€” un `margin`, donc hors de la boÃ®te du conteneur survolÃ©. En traversant ce vide (~8px), le curseur sortait de `:hover` avant d'atteindre le menu, qui se dÃ©montait en plein trajet. Si ce dÃ©montage survenait pendant le clic (mousedown/mouseup), le clic ne touchait plus rien â€” d'oÃ¹ le second symptÃ´me.
- **`src/components/DealCard.jsx`** : `margin` remplacÃ© par `padding` sur un wrapper englobant (`pb-2`/`pt-2` au lieu de `mb-2`/`mt-2`), avec le style visuel du menu dÃ©placÃ© dans un `<div>` interne â€” le gap fait dÃ©sormais partie de la zone survolÃ©e, comme pour la Navbar. AppliquÃ© aux deux emplacements dupliquÃ©s : footer de carte (rendu direct) et `renderActionButtons` (utilisÃ© par la modale d'analyse IA).
- **Fix vÃ©rifiÃ© avant/aprÃ¨s** : reproduction isolÃ©e (HTML/Tailwind servi en local, hors app, sans dÃ©pendance Firebase) â€” la version "margin" se ferme bien quand le curseur traverse le gap, empÃªchant tout clic ; la version "padding" reste ouverte dans la mÃªme zone et le clic dÃ©clenche bien l'action. Non testÃ© en conditions rÃ©elles dans l'app (nÃ©cessite authentification) â€” Ã  confirmer par l'utilisateur.

[2026-07-11] [PRO] Fix : Menu dÃ©roulant du statut bot (Navbar) inaccessible au survol sur desktop â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : sur l'interface ordinateur, les boutons du menu (Scanner maintenant, VÃ©rifier Stocks, Stop Scan/Start Bot) affichÃ© au survol du statut bot disparaissent dÃ¨s que la souris se dÃ©place vers eux.
- **Cause confirmÃ©e par reproduction isolÃ©e (HTML/CSS + Playwright, mouvement de souris simulÃ© hors application)** : le conteneur `.group` (`Navbar.jsx`) qui dÃ©clenche l'affichage au survol n'a que la largeur du texte de statut ("Scan en cours", "En attente"...), nettement plus Ã©troit que le menu affichÃ© en dessous (jusqu'Ã  4 boutons + sÃ©parateur). Un dÃ©placement en diagonale vers un bouton excentrÃ© (gauche/droite du centre) sort de la zone `:hover` avant d'atteindre le menu, qui redevient invisible/non cliquable en plein trajet â€” reproduit et confirmÃ© de faÃ§on dÃ©terministe, pas un problÃ¨me de souris/OS particulier.
- **`src/components/Navbar.jsx`** : ajout de `justify-center lg:min-w-[190px]` au conteneur `.group` (calibrÃ© sur la largeur max du menu Ã  4 boutons), pour que sa zone de survol couvre dÃ©jÃ  toute la largeur du menu Ã  toute hauteur. LimitÃ© Ã  `lg:` (desktop) pour ne pas Ã©largir inutilement la barre de navigation sur mobile.
- **Fix vÃ©rifiÃ© avant implÃ©mentation** : reproduction du bug puis du fix dans un fichier HTML/CSS isolÃ© (classes Ã©quivalentes, sans dÃ©pendance Firebase), via Playwright â€” Ã©chec de clic confirmÃ© sur les boutons excentrÃ©s avant le fix, succÃ¨s sur les 4 boutons aprÃ¨s.

[2026-07-11] [PRO] Fix : Cause racine de l'absence d'emails "PÃ©pite" trouvÃ©e + pipeline de dÃ©ploiement fragilisÃ© au passage â†’ RÃ©sultat :
- **Cause confirmÃ©e** : le secret GitHub `DOT_ENV` ne contenait jamais `SMTP_USER`/`SMTP_PASSWORD` depuis la mise en place de la feature â€” `.env.example` les documentait comme modÃ¨le, mais jamais reportÃ©s dans le vrai secret. Ni un bug de code (le fix logger du 2026-07-09 Ã©tait correct mais insuffisant pour ce diagnostic), ni des identifiants Gmail rÃ©voquÃ©s. ConfirmÃ© par investigation en direct avec l'utilisateur : `WorkingDirectory` du service `guitare-hunter` vÃ©rifiÃ© correct, `.env` dÃ©ployÃ© confirmÃ© prÃ©sent et Ã  jour (timestamp du dÃ©ploiement), mais `grep -o '^[A-Z_]*=' ~/GuitareHunter/.env` ne listait aucune clÃ© `SMTP_`.
- **Bug dÃ©couvert en corrigeant** : aprÃ¨s ajout des lignes SMTP au secret, 2 dÃ©ploiements consÃ©cutifs ont Ã©chouÃ© (`bash: erreur de syntaxe prÃ¨s du symbole inattendu Â« ) Â»`) sur les jobs `deploy-frontend` ET `deploy` (SSH). Cause : `.github/workflows/deploy.yml` interpolait `${{ secrets.DOT_ENV }}`/`${{ secrets.FIREBASE_SERVICE_ACCOUNT_KEY }}` littÃ©ralement dans les scripts bash (`echo "${{ secrets.X }}" > .env`) â€” un simple guillemet dans la valeur du secret casse la chaÃ®ne bash et fait Ã©chouer tout le dÃ©ploiement, quel que soit le contenu voulu.
- **`deploy.yml` durci** : `DOT_ENV` transmis via `env:` au step `Create .env file` (rÃ©fÃ©rencÃ© `"$DOT_ENV"`, plus jamais interpolÃ© littÃ©ralement). Pour le job `deploy` (SSH, `appleboy/ssh-action`), `DOT_ENV`/`FIREBASE_SERVICE_ACCOUNT_KEY` transmis via le paramÃ¨tre `envs:` de l'action plutÃ´t qu'interpolÃ©s dans le script distant. `echo >` remplacÃ© par `printf '%s' >` pour l'Ã©criture des fichiers. Rend le pipeline robuste Ã  n'importe quel caractÃ¨re dans les secrets, sans avoir Ã  les Ã©diter avec prÃ©caution.
- **Outils utilisÃ©s pour le diagnostic** : LogViewer (curseur "Limite Temporaire de Logs" du `ConfigPanel`, jusqu'Ã  500 lignes â€” pas 100, contrairement Ã  l'idÃ©e reÃ§ue de l'utilisateur), historique des runs GitHub Actions (`mcp__github__actions_list`/`get_job_logs`) pour confirmer succÃ¨s/Ã©chec et timestamps de dÃ©ploiement, vÃ©rifications directes sur le serveur (`systemctl show`, `grep` sur `.env`).

[2026-07-11] [PRO] Fix : `schedule.run_pending()` non protÃ©gÃ© dans la boucle watchdog globale (risque de crash process-wide) â†’ RÃ©sultat :
- **Contexte** : Revue du commit "Dashboard Administrateur â€” Phase 1" (voir entrÃ©e suivante) Ã  la demande de l'utilisateur ("vÃ©rifie que Ã§a ne pose pas de problÃ¨mes"). Ce commit ajoute `schedule.every().day.at("03:00").do(run_admin_stats_job, ...)` et un appel `schedule.run_pending()` dans la boucle watchdog globale de `main.py`.
- **Risque identifiÃ©** : `backend/services.py::TaskScheduler` utilise le scheduler **global partagÃ©** de la librairie `schedule` (pas d'instance dÃ©diÃ©e) â€” chaque thread utilisateur y enregistre ses jobs (`scan`/`cleanup`/`purge`) sur la mÃªme liste. Jusqu'ici, `schedule.run_pending()` n'Ã©tait appelÃ© que depuis la boucle interne de chaque thread utilisateur (`main.py:82`), protÃ©gÃ©e par un `except Exception` qui logue et continue. Le nouvel appel dans la boucle watchdog globale n'Ã©tait protÃ©gÃ© que par `except KeyboardInterrupt` â€” comme `run_pending()` exÃ©cute *tous* les jobs dus (pas seulement `admin_stats`), une exception non gÃ©rÃ©e dans le job planifiÃ© de n'importe quel utilisateur aurait fait planter tout le process, tous utilisateurs confondus, via le mÃ©canisme censÃ© les protÃ©ger d'une panne isolÃ©e.
- **`main.py`** : Ajout d'un `try/except Exception` dÃ©diÃ© autour de l'appel, mÃªme pattern que la boucle par-utilisateur (log + continue, pas d'interruption du watchdog).

[2026-07-11] [PRO] Feature : Dashboard Administrateur â€” Phase 1 (Monitoring, lecture seule) â†’ RÃ©sultat :
- **`backend/scripts/set_admin_claim.py`** : Script one-shot (Admin SDK) pour poser le custom claim `admin: true` sur un compte Firebase. Usage : `python backend/scripts/set_admin_claim.py --email admin@example.com` (option `--revoke` pour retrait).
- **`firebase/firestore.rules`** : Ajout de la fonction `isAdmin()` (`request.auth.token.admin == true`) + rÃ¨gles `collectionGroup('users')` et `collectionGroup('guitar_deals')` autorisant la lecture cross-utilisateurs uniquement pour l'admin. Nouvelle collection `admin_stats/{docId}` en lecture admin, Ã©criture interdite au client (Admin SDK only). Les rÃ¨gles d'isolation utilisateur existantes sont inchangÃ©es.
- **`backend/admin_stats.py`** : Job quotidien calculant, par utilisateur, le volume `guitar_deals` des derniÃ¨res 24h, le funnel Tier 1â†’2â†’3 et le coÃ»t Gemini estimÃ©. RÃ©utilise les constantes et formules de `analyze_funnel_by_user.py`. Ã‰crit dans `artifacts/{APP_ID}/admin_stats/latest`.
- **`main.py`** : IntÃ©gration du job `run_admin_stats_job` dans la boucle watchdog via `schedule.every().day.at("03:00")` (singleton global, une seule fois quel que soit le nombre de threads utilisateur).
- **`src/hooks/useAuth.js`** : Nouveau state `isAdmin` initialisÃ© via `firebaseUser.getIdTokenResult()` Ã  chaque changement d'Ã©tat d'auth. VÃ©rification dÃ©fensive cÃ´tÃ© client (la vraie protection reste les rÃ¨gles Firestore). ExposÃ© dans le return du hook.
- **`src/components/Navbar.jsx`** : Bouton `ShieldCheck` affichÃ© uniquement si `isAdmin === true`. Nouvelle prop `onOpenAdmin`.
- **`src/components/Dashboard.jsx`** : Import et montage conditionnel de `AdminDashboard` via `showAdmin` state.
- **`src/components/AdminDashboard.jsx`** : Nouveau composant â€” tableau des utilisateurs (email, UID, botStatus, villes, frÃ©quence de scan, dernier login), enrichi par les stats de coÃ»t/volume du snapshot `admin_stats/latest` (non-bloquant si absent). Bouton RafraÃ®chir.
- **Phase 2 non livrÃ©e** : Actions privilÃ©giÃ©es (`DISABLE_USER`, `SEND_EMAIL`, `STOP_BOT` admin, journal d'audit) restent planifiÃ©es dans `ADMIN_DASHBOARD_PLAN.md`.

[2026-07-11] [PRO] Fix : STOP_SCAN/STOP_BOT/START_BOT Ã©chouaient toujours ("Erreur lors de l'envoi de la commande") â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : clic sur "Interrompre le scan" â†’ alerte `Erreur STOP_SCAN: Erreur lors de l'envoi de la commande.`
- **Cause** : `src/components/Navbar.jsx` appelle `triggerStopScan()`/`triggerStopBot()`/`triggerStartBot()` (`firestoreService.js`) directement, sans passer par `useBotConfig.js` (qui fournit correctement `user.uid` pour Refresh/Cleanup/Reanalyze). Ces 3 appels n'avaient aucun argument `userId` â†’ `getRefs(undefined)` lÃ¨ve une erreur (fail fast, voir CLAUDE.md), catchÃ©e par `addCommand()` et remplacÃ©e par le message gÃ©nÃ©rique `"Erreur lors de l'envoi de la commande."` â€” masquant la vraie cause Ã  l'utilisateur comme dans les logs.
- **`Navbar.jsx`** : `user` rÃ©cupÃ©rÃ© via `useAuth()` (dÃ©jÃ  importÃ© pour `signOut`, mais jamais destructurÃ©) et passÃ© en `user?.uid` aux 3 appels.
- **Non couvert par les tests/lint** : bug uniquement visible Ã  l'usage (clic bouton), invisible en compilation puisque `userId` est un paramÃ¨tre optionnel cÃ´tÃ© JS.

[2026-07-11] [PRO] Feature : Stat "Erreurs Portier corrigÃ©es" (StatsView) â†’ RÃ©sultat :
- **Contexte** : Suite Ã  un cas rÃ©el observÃ© par l'utilisateur (une annonce rejetÃ©e par le Portier, rÃ©analysÃ©e manuellement, rÃ©vÃ©lÃ©e comme une PÃ©pite), constat que `dev` disposait dÃ©jÃ  d'un outil de diagnostic ponctuel (`analyze_funnel_by_user.py --sample-size`, Â§8.2 de `GEMINI_PROMPT_CACHING_PLAN.md`) mais rien d'automatisÃ©/permanent dans l'app pour suivre ce taux d'erreur dans le temps.
- **`backend/repository.py::create_new_deal()`** : deux nouveaux champs figÃ©s Ã  la crÃ©ation, jamais rÃ©Ã©crits par les rÃ©analyses ultÃ©rieures (contrairement Ã  `aiAnalysis`) : `initialVerdict` (verdict du tout premier passage IA) et `initialModelUsed` (chaÃ®ne `model_used` du premier passage, ex: `"gemini-2.5-flash-lite"` si arrÃªtÃ© au Portier seul).
- **`src/components/StatsView.jsx`** : nouvelle stat sous le Funnel â€” parmi les annonces dont la chaÃ®ne `initialModelUsed` ne compte qu'un seul maillon (= arrÃªtÃ©es au Portier seul, jamais passÃ©es Ã  l'Analyste), compte celles dont la chaÃ®ne `aiAnalysis.model_used` **actuelle** compte 2 maillons ou plus (= rÃ©analysÃ©es avec succÃ¨s depuis). Affichage : `X/Y (Z%)`.
- **Pourquoi pas une simple comparaison de `verdict`** : `BAD_DEAL` peut provenir soit d'un vrai rejet Portier, soit d'un verdict lÃ©gitime de l'Analyste (Tier 2) aprÃ¨s analyse complÃ¨te ("trop cher") â€” les confondre aurait faussÃ© la stat. La longueur de chaÃ®ne `model_used` lÃ¨ve l'ambiguÃ¯tÃ© sans dÃ©pendre du texte du verdict (qui est configurable par l'utilisateur via `rejectionVerdicts`).
- **Limite assumÃ©e** : pas de backfill â€” seules les annonces crÃ©Ã©es aprÃ¨s ce dÃ©ploiement auront `initialVerdict`/`initialModelUsed` ; la stat dÃ©marre Ã  0/0.
- **Branche** : rebase (fast-forward) de `claude/claude-md-literate-ovyt5p` sur `dev` avant implÃ©mentation (18 commits de retard sur `master`, incluant le fix du faux positif Portier "acoustique 12 cordes" â€” voir `GEMINI_PROMPT_CACHING_PLAN.md Â§8.2`).

[2026-07-09] [FLASH] Ajout : Script de test manuel du pipeline de notifications â†’ RÃ©sultat :
- `backend/scripts/test_notification.py` : dÃ©clenche une notification factice (verdict `PEPITE`) sans attendre un vrai scan, avec le vrai logger par-utilisateur (raccordÃ© au LogViewer). Usage : `python3 backend/scripts/test_notification.py` (utilise `USER_ID_TARGET` du `.env` et l'email Firebase Auth associÃ© par dÃ©faut ; `--user-id`/`--email` pour surcharger).
- **Raison** : Suite au signalement "plus d'email reÃ§u, seulement des ntfy", permet de diagnostiquer directement la cause (SMTP mal configurÃ© vs identifiants Gmail rÃ©voquÃ©s) sans dÃ©pendre du hasard d'un scan qui trouve une vraie PÃ©pite.

[2026-07-09] [PRO] Fix : Logs de `notifications.py` et `analyzer.py` invisibles dans le LogViewer (mÃªme bug que le scraper) â†’ RÃ©sultat :
- **Contexte** : Signalement "plus d'email reÃ§u, seulement des ntfy". Investigation de l'historique Git de `notifications.py`/`bot.py`/`deploy.yml` â€” aucun changement de code rÃ©cent ne touche l'envoi d'email ou les identifiants SMTP, et la rÃ©solution de l'email utilisateur fonctionne (confirmÃ© par les logs). RÃ©gression probablement externe (identifiants Gmail rÃ©voquÃ©s/expirÃ©s, ou variable d'environnement serveur manquante) â€” non confirmable tant que l'erreur rÃ©elle restait invisible.
- **Cause** : `notifications.py` et `analyzer.py` loguaient via `logging.getLogger(__name__)` (loggers de module), jamais raccordÃ©s au logger par-utilisateur `bot.{user_id}` â€” mÃªme bug que celui dÃ©jÃ  corrigÃ© pour `backend/scraping/` (voir plus bas).
- **`analyzer.py`** : `DealAnalyzer.__init__` accepte un `logger` optionnel ; les 18 appels `logger.x()` de la classe basculÃ©s sur `self.logger.x()`. `bot.py` passe `logger=self.logger` aux 2 instanciations.
- **`notifications.py`** : `NtfyNotifier.send()`/`EmailNotifier.send()`/`NotificationService.notify_deal()`/`notify_model_error()` acceptent tous un paramÃ¨tre `logger` optionnel, propagÃ© depuis `bot.py` et `analyzer.py`.
- **Bonus** : `EmailNotifier.send()` logue dÃ©sormais explicitement quand l'envoi est bloquÃ© par une config SMTP manquante (avant : un seul warning au tout premier chargement du module, jamais revu ensuite â€” ratait donc silencieusement chaque tentative suivante).

[2026-07-09] [PRO] Fix : `gemini-2.5-flash` (Tier 2 â€” Analyste) n'est plus disponible chez Google (404) â†’ RÃ©sultat :
- RemplacÃ© par `gemini-3.5-flash` partout oÃ¹ codÃ© en dur : `backend/analyzer.py` (fallback runtime `config.get('mainModel', ...)` â€” probable cause directe du 404 en prod, puisque `mainModel` n'est jamais initialisÃ© dans la structure Firestore crÃ©Ã©e pour un nouvel utilisateur), `config.py::GEMINI_MODELS` (`default_analyst` + retrait de la liste `available`), `src/components/ConfigPanel.jsx` (liste de repli + valeur par dÃ©faut du `<select>`), `src/hooks/useBotConfig.js` (Ã©tat initial React ET bouton "RÃ©initialiser par dÃ©faut", qui rÃ©Ã©crivait encore le modÃ¨le mort dans Firestore).
- **Suivi requis** : comme pour l'Expert Pro en 2026-07-07, resÃ©lection manuelle du modÃ¨le Analyste dans ParamÃ¨tres â†’ IA si la config Firestore existante a dÃ©jÃ  `mainModel` enregistrÃ© Ã  l'ancienne valeur (non migrÃ©e rÃ©troactivement).

[2026-07-09] [PRO] Feature : Ne pas stocker un scraping ratÃ© + rejet automatique des annonces hors budget â†’ RÃ©sultat :
- **`bot.py::handle_deal_found()`** : garde-fou en tout dÃ©but de fonction â€” si `imageUrls` est vide ET prix Ã  0$ (scraping manifestement ratÃ©), aucune Ã©criture Firestore ni appel IA ; l'annonce reste absente de la base et sera retraitÃ©e comme nouvelle Ã  la prochaine session/scan, au lieu de figer une fiche vide comme "dÃ©jÃ  traitÃ©e".
- **Plafond de prix dÃ©fensif** : vÃ©rification de `scanConfig.max_price` cÃ´tÃ© code, indÃ©pendante du filtre de prix Facebook (observÃ© en prod : peut Ã©chouer avec `Timeout 10000ms exceeded` sur le champ de saisie, sans vÃ©rification a posteriori jusqu'ici). RÃ©utilise le verdict `BAD_DEAL` existant ("Trop Cher") plutÃ´t qu'un nouveau statut dÃ©diÃ© â€” `status` reste `analyzed`, pas `rejected`, pour ne pas confondre "hors budget" avec un vrai rejet (mot-clÃ©/IA).
- **`src/constants.js`** : `BAD_DEAL` dÃ©placÃ© de `MARKET_GROUP` vers `ARCHIVE_GROUP` â€” masquÃ© de la vue par dÃ©faut via le mÃ©canisme de filtrage existant (`matchesVerdictFilter`), toujours consultable via son propre filtre "Trop Cher" dÃ©jÃ  prÃ©sent dans le menu dÃ©roulant. Aucune nouvelle logique de statut/filtre Ã  construire.
- S'applique uniformÃ©ment Ã  `scan_marketplace()` et `scan_specific_url()` (demande explicite de l'utilisateur : pas d'exemption pour le scan manuel d'URL).
- **Raison** : Ã‰viter de figer des fiches vides comme "dÃ©jÃ  traitÃ©es" (bloquant tout nouveau scraping futur), et donner un moyen de filtrer les annonces valides mais hors budget sans les traiter comme du bruit/rejet de fond.

[2026-07-09] [PRO] Fix : Crash pipeline IA si Gemini rÃ©pond avec un tableau JSON au lieu d'un objet â†’ RÃ©sultat :
- **SymptÃ´me** : `TypeError: list indices must be integers or slices, not str` sur `result_t3["model_used"] = ...` (Tier 3 â€” Expert Pro), observÃ© en prod pendant la vÃ©rification du fix images ci-dessous â€” bloquait toute analyse tant qu'il n'Ã©tait pas corrigÃ©.
- **`backend/analyzer.py::_call_gemini_json()`** : normalise dÃ©sormais tout rÃ©sultat de type liste (`[{...}]`) en `dict` (premier Ã©lÃ©ment si c'est un dict, sinon `{}`) avant de le retourner â€” correction unique Ã  la source plutÃ´t qu'un patch sur le seul Tier touchÃ© ; protÃ¨ge aussi T1 (Portier) et T2 (Analyste), qui partagent cette mÃ©thode utilitaire et avaient la mÃªme fragilitÃ© latente.

[2026-07-09] [PRO] Fix : Logs du scraper invisibles dans le LogViewer (mauvais logger) â†’ RÃ©sultat :
- **Cause racine** : `backend/scraping/core.py`, `parser.py` et `city_finder.py` loguaient via `logging.getLogger(__name__)` (loggers de module `scraping.core`/`scraping.parser`/`scraping.city_finder`), jamais raccordÃ©s au logger par-utilisateur `bot.{user_id}` (seul logger avec un `FirestoreHandler` attachÃ©, alimentant la collection lue par `LogViewer.jsx`). Aucun log du scraper â€” y compris les diagnostics `[DIAG]` ajoutÃ©s pendant l'investigation du bug images ci-dessous â€” n'a jamais Ã©tÃ© visible dans l'app, faussant tout le diagnostic jusqu'ici.
- **`FacebookScraper.__init__`** : nouveau paramÃ¨tre optionnel `logger` (repli sur le logger de module pour scripts autonomes/tests). Les 49 appels `logger.x()` de la classe basculÃ©s sur `self.logger.x()`.
- **`ListingParser.parse_listing_card()`/`parse_details_page()`** : paramÃ¨tre `logger` optionnel ajoutÃ© et propagÃ© depuis `core.py`.
- **`city_finder.py`** : `find_city_id_and_coords()` utilise dÃ©sormais `scraper.logger` (dÃ©jÃ  reÃ§u en paramÃ¨tre) au lieu d'un logger de module â€” import `logging` devenu inutile, retirÃ©.
- **`bot.py`** : les 5 instanciations de `FacebookScraper` passent `logger=self.logger` â€” isolation multi-tenant prÃ©servÃ©e (un thread = un scraper = un logger, pas de logger global partagÃ© entre utilisateurs).
- **Raison** : Sans ce correctif, impossible de vÃ©rifier depuis l'app si les correctifs scraping (voir entrÃ©e suivante) fonctionnaient rÃ©ellement â€” la dÃ©couverte de ce bug a dÃ©bloquÃ© le reste de l'investigation.

[2026-07-09] [PRO] Fix : Fiche dÃ©tail Facebook dÃ©gradÃ©e â†’ titre/prix/images manquants sur certaines annonces (SCAN_URL) â†’ RÃ©sultat :
- **SymptÃ´me initial** : Sur l'annonce "Guitare Ã©lectrique Aria Pro 2" (Granby), seule la premiÃ¨re miniature Ã©tait rÃ©cupÃ©rÃ©e ; investigation Ã©tendue ensuite au prix (0$) et aux images (0), rapportÃ©es comme "intermittentes" (certaines annonces fonctionnent).
- **`backend/scraping/core.py`** : 1Ã¨re version (`_recover_degraded_page`) basÃ©e sur l'absence de carrousel photo interactif (`ListingParser.has_photo_carousel()`) pour dÃ©clencher un reload â€” remplacÃ©e aprÃ¨s une code review dÃ©diÃ©e par un dÃ©clencheur non ambigu : "0 image extraite aprÃ¨s parsing" (l'absence de carrousel donnait un faux positif systÃ©matique sur toute annonce Ã  une seule photo lÃ©gitime, qui n'a par nature aucun bouton "photo suivante"). Nouvelle mÃ©thode `_parse_details_with_reload_retry()`/logique dÃ©diÃ©e dans `scan_specific_url()` : rÃ©-extraction complÃ¨te (titre/prix/localisation incluses, pas seulement les images) avec comparaison avant/aprÃ¨s reload (on ne garde le reload que s'il apporte strictement plus d'images).
- **Code review dÃ©diÃ©e (`/code-review` niveau high)** : a rÃ©vÃ©lÃ© que le premier correctif (`_recover_degraded_page()`) ne revÃ©rifiait jamais si le reload avait rÃ©ellement rÃ©parÃ© la page â€” son retour n'Ã©tait que le contrÃ´le d'URL (`_is_valid_detail_page`), donc un reload sans effet Ã©tait quand mÃªme considÃ©rÃ© comme un succÃ¨s et la page toujours dÃ©gradÃ©e Ã©tait parsÃ©e comme valide. 8 autres pistes (reuse, simplification, efficacitÃ©, altitude, conventions) explorÃ©es en parallÃ¨le via sous-agents ; 2 confirmÃ©es comme critiques, corrigÃ©es dans la foulÃ©e.
- **Diagnostic enrichi** (`parser.py::parse_details_page`) : quand 0 image est retenue, logue dÃ©sormais le nombre total d'`<img>` trouvÃ©es dans `div[role='main']` (avant filtrage taille) et leurs dimensions â€” confirmÃ© en prod (une fois le bug de logging ci-dessous corrigÃ©) : `0 <img>` dans le DOM, ni avant ni aprÃ¨s reload. Ã‰carte dÃ©finitivement l'hypothÃ¨se d'un filtre `>300Ã—300px` trop strict.
- **Cause probable, non rÃ©solue** : le scraper ne s'authentifie jamais sur Facebook (aucune session/cookies persistants dans tout le backend, vÃ©rifiÃ©). Facebook semble parfois (comportement confirmÃ© intermittent par l'utilisateur) servir une version limitÃ©e de la fiche dÃ©tail aux sessions anonymes â€” titre/description (balises `og:*`) disponibles, prix et carrousel photo absents du DOM. DÃ©cision produit Ã  trancher : accepter la limitation (couverte par le garde-fou "scraping ratÃ©" ci-dessus) ou implÃ©menter une session Facebook authentifiÃ©e (risque de bannissement du compte selon les CGU FB, gestion sÃ©curisÃ©e des secrets) â€” voir `TODO.md`.
- **Raison** : Plusieurs itÃ©rations ont Ã©tÃ© nÃ©cessaires car chaque diagnostic partiel masquait la cause suivante â€” le vrai verrou a Ã©tÃ© le bug de logging (entrÃ©e suivante), qui empÃªchait toute observation rÃ©elle du comportement en prod jusqu'Ã  sa correction.

[2026-07-07] [PRO] Fix : Job `deploy-frontend` rejetÃ© par Git (`gh-pages` non fast-forward) â†’ RÃ©sultat :
- **SymptÃ´me** : `git push origin gh-pages` Ã©choue dans le job CI avec `! [rejected] gh-pages -> gh-pages (fetch first)`.
- **Cause** : Des dÃ©ploiements manuels (`npm run deploy`) faits en parallÃ¨le pendant la session ont fait diverger la branche `gh-pages` de l'Ã©tat attendu par le job CI, dont le `git push` normal n'est pas `--force`.
- **`.github/workflows/deploy.yml`** : Ajout de `force_orphan: true` sur l'Ã©tape `peaceiris/actions-gh-pages@v4` â€” republie systÃ©matiquement un commit unique et propre sur `gh-pages`, sans jamais dÃ©pendre ni tenir compte de son Ã©tat prÃ©cÃ©dent (adaptÃ© Ã  une branche de build, sans historique utile Ã  prÃ©server).
- **Raison** : `gh-pages` ne contient que des artefacts de build ; `force_orphan` est le pattern recommandÃ© pour ce cas prÃ©cis et rend le dÃ©ploiement CI totalement insensible Ã  d'Ã©ventuels dÃ©ploiements manuels intercalÃ©s.

[2026-07-07] [PRO] Feature : Mise Ã  jour des modÃ¨les Gemini + commentaire personnalisÃ© sur rÃ©analyse + alerte modÃ¨le indisponible â†’ RÃ©sultat :
- **`config.py`** : `GEMINI_MODELS["available"]` nettoyÃ© (retrait de `gemini-1.5-flash`/`gemini-1.5-pro`, gÃ©nÃ©ration obsolÃ¨te). Ajout de `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3.1-pro-preview`. `default_expert` (Tier 3 â€” contre-analyses) â†’ `gemini-3.1-pro-preview` (choix utilisateur : prÃ©fÃ©rÃ© Ã  `gemini-3.5-flash` malgrÃ© son statut Preview, jugement qualitÃ© > stabilitÃ©).
- **`src/components/ConfigPanel.jsx`** : Liste de repli alignÃ©e sur `config.py`.
- **Important** : La config Firestore d'un utilisateur existant n'est Ã©crite qu'une fois Ã  la crÃ©ation du compte (`ensure_initial_structure` prÃ©serve les docs existants) â€” le nouveau dÃ©faut ne s'applique pas rÃ©troactivement, resÃ©lection manuelle requise dans le panneau IA.
- **`backend/analyzer.py`** : `analyze_deal()` accepte `user_comment` (injectÃ© en prioritÃ© dans le prompt de base, ex: "Tu as identifiÃ© une PRS mais c'est une GWD") et `user_email` (pour l'alerte modÃ¨le indisponible ci-dessous).
- **`backend/bot.py`** : `analyze_single_deal(payload)` lit `payload['userComment']` ; `user_email` transmis aux 3 points d'appel de `analyze_deal`.
- **`src/services/firestoreService.js`**, **`useDealsManager.js`**, **`Dashboard.jsx`** : `userComment` relayÃ© de bout en bout jusqu'Ã  la commande Firestore `ANALYZE_DEAL`.
- **`src/components/DealCard.jsx`** : Nouvelle option "Avec commentaire..." dans les deux dropdowns "RÃ©-analyser" (carte + modale â€” code dupliquÃ© existant, non refactorisÃ©), ouvrant une modale dÃ©diÃ©e (textarea) qui lance une rÃ©analyse Expert avec le commentaire inclus.
- **`backend/notifications.py`** : Nouvelle fonction `notify_model_error(model_name, error, user_email)` (email + ntfy).
- **`backend/analyzer.py`** : `_call_gemini_json` dÃ©tecte les erreurs "modÃ¨le introuvable" (404/not found/not supported) et dÃ©clenche l'alerte, throttlÃ©e Ã  1Ã—/24h par modÃ¨le (`self._model_error_last_notified`).
- **DÃ©couverte technique** : Le SDK Python `google.generativeai` (utilisÃ© par `analyzer.py`) Ã©met dÃ©sormais un `FutureWarning` explicite â€” support totalement terminÃ©, remplacÃ© par `google-genai`. Migration non faite ici (hors pÃ©rimÃ¨tre, refactor plus large), Ã  planifier sÃ©parÃ©ment.
- **Raison** : Le Portier/Analyste (Tier 1/2) restent sur leurs modÃ¨les 2.5 actuels (stables, non concernÃ©s par la demande) ; seul l'Expert Pro (contre-analyses) a Ã©tÃ© mis Ã  jour vers le modÃ¨le jugÃ© le plus puissant.

[2026-07-07] [PRO] Incident : Site en panne suite Ã  l'automatisation du dÃ©ploiement frontend (`TypeError onAuthStateChanged`) â†’ RÃ©sultat :
- **SymptÃ´me** : AprÃ¨s le premier push dÃ©clenchant le nouveau job `deploy-frontend`, le site entier plantait sur tous les appareils avec `TypeError: Cannot read properties of undefined (reading 'onAuthStateChanged')`.
- **Cause** : `src/services/firebase.js` lit `import.meta.env.VITE_FIREBASE_*`, injectÃ©es au build depuis `.env` (fichier local, non versionnÃ©). Le job CI `deploy-frontend` buildait sans ce fichier â†’ `firebaseConfig` entiÃ¨rement `undefined` â†’ `initializeApp()` Ã©choue (catchÃ©, juste loggÃ©) â†’ `auth` reste `undefined` â†’ premier appel `auth.onAuthStateChanged(...)` plante.
- **RÃ©paration immÃ©diate** : `npm run deploy` relancÃ© manuellement en local (avec le vrai `.env`) pour restaurer le site.
- **Correctif permanent (`.github/workflows/deploy.yml`)** : Ajout d'une Ã©tape "Create .env file" dans `deploy-frontend`, Ã©crivant `secrets.DOT_ENV` avant `npm run build` â€” mÃªme mÃ©canisme dÃ©jÃ  utilisÃ© par le job backend. Ã‰chec explicite (`exit 1`) si le secret est absent, plutÃ´t qu'un build silencieusement cassÃ©.
- **Raison** : Le job frontend ajoutÃ© la veille n'avait pas repris l'injection de secrets dÃ©jÃ  en place cÃ´tÃ© backend â€” angle mort dÃ©couvert seulement une fois le dÃ©ploiement automatique rÃ©ellement dÃ©clenchÃ© en production.

[2026-07-07] [PRO] Fix : Viewport mobile fixe (475px) au lieu de device-width â†’ RÃ©sultat :
- **`index.html`** : `<meta name="viewport" content="width=device-width, initial-scale=1.0">` â†’ `<meta name="viewport" content="width=475">`. Sans effet sur desktop (balise ignorÃ©e hors navigateurs mobiles).
- **MÃ©canisme** : Au lieu de forcer un mappage 1:1 CSS/Ã©cran (`device-width`) et de devoir cacher des Ã©lÃ©ments du `Navbar` pour tenir dans ~375px, le viewport logique est fixÃ© Ã  475px â€” le navigateur mobile calcule alors automatiquement un zoom (`visualViewport.scale` â‰ˆ 0.79 sur un Ã©cran de 375px) pour l'adapter Ã  l'Ã©cran rÃ©el. Rien n'est plus cachÃ© ni coupÃ©, juste rendu proportionnellement plus petit.
- **VÃ©rifiÃ©** : `document.documentElement.clientWidth` = 475, `scrollWidth` = `clientWidth` partout (nav compris) â†’ zÃ©ro dÃ©bordement. Les 4 boutons du Navbar (Filtres, Aide, ParamÃ¨tres, DÃ©connexion) restent tous visibles et cliquables. TestÃ© via Ã©mulateur mobile (Chrome DevTools respecte la balise viewport comme un vrai appareil) â€” confirmation sur tÃ©lÃ©phone rÃ©el en attente.
- **Raison** : L'utilisateur a proposÃ© cette approche aprÃ¨s avoir constatÃ© que le fix prÃ©cÃ©dent (masquer des boutons sous 640px) rÃ©glait le dÃ©bordement mais rendait l'interface "trop petite"/cramped ; fixer un viewport logique plus large et laisser le navigateur zoomer automatiquement est plus simple et n'oblige Ã  cacher aucune fonctionnalitÃ©.

[2026-07-07] [PRO] Automatisation du dÃ©ploiement frontend (GitHub Pages) â†’ RÃ©sultat :
- **DÃ©couverte** : Le fix mobile de la veille testÃ© sur le site en ligne (`ludoviclebart.github.io`) ne montrait aucun changement. Cause : le dÃ©ploiement frontend Ã©tait **manuel** (`npm run deploy`) et n'avait pas Ã©tÃ© refait depuis le **2026-05-06** â€” 2 mois de retard, indÃ©pendant du CI backend (qui ne dÃ©ploie que le service Python via SSH).
- **Action immÃ©diate** : `npm run deploy` exÃ©cutÃ© manuellement pour publier la version Ã  jour (commit `6acd749` sur `gh-pages`).
- **`.github/workflows/deploy.yml`** : Nouveau job `deploy-frontend`, indÃ©pendant et parallÃ¨le au job backend existant, dÃ©clenchÃ© sur les mÃªmes branches (`master`, `dev`). `npm ci` â†’ `npm run build` â†’ publication de `dist/` sur `gh-pages` via `peaceiris/actions-gh-pages@v4` (`GITHUB_TOKEN` intÃ©grÃ©, pas de nouveau secret).
- **PrÃ©requis** : Repo GitHub â†’ Settings â†’ Actions â†’ General â†’ "Workflow permissions" sur "Read and write permissions", sinon le push vers `gh-pages` Ã©choue malgrÃ© le `permissions: contents: write` du job.
- **Raison** : Le dÃ©ploiement manuel avait permis un dÃ©calage de 2 mois entre le code et le site en ligne sans que Ã§a se remarque â€” source du "Ã§a n'a pas marchÃ©" alors que le correctif mobile Ã©tait dÃ©jÃ  en place dans le code.

[2026-07-06] [PRO] Fix : DÃ©bordement horizontal en mode mobile (Dashboard) â†’ RÃ©sultat :
- **`index.css`** : Ajout de `overflow-x: hidden` sur `html, body, #root` â€” filet de sÃ©curitÃ© empÃªchant tout Ã©lÃ©ment fautif de crÃ©er un scroll horizontal.
- **`src/components/Dashboard.jsx`** (`VerdictDropdown`) : Le conteneur du bouton avait `relative shrink-0` (largeur indÃ©finie) avec un enfant `w-full` â€” cas ambigu en CSS. RemplacÃ© par `flex-1 sm:flex-none min-w-0` sur le conteneur, avec troncature propre (`truncate`) du libellÃ© au lieu de dÃ©pendre du `w-full`.
- **`src/components/Dashboard.jsx`** (barre Recherche & Actions, lignes ~372-413) : Les deux groupes de boutons (Statut/Favoris, Vue/Compteur/Croix) tenaient sur une seule ligne en mobile (`flex-row justify-between`), ce qui Ã©crasait la croix "Effacer les filtres". Passage Ã  `flex-col sm:flex-row` pour empiler les deux groupes sous 640px.
- **`src/components/Dashboard.jsx`** et **`src/components/Navbar.jsx`** : Les deux menus dÃ©roulants en `position: absolute` (filtre Statut, menu hover du bot) n'avaient aucune limite de largeur liÃ©e au viewport â€” mÃªme invisibles, ils pouvaient dÃ©passer l'Ã©cran et gonfler la largeur scrollable de la page. Ajout de `max-w-[calc(100vw-2rem)]`.
- **VÃ©rifiÃ©** : build Vite propre, page de connexion testÃ©e en viewport mobile (375px) â€” `document.documentElement.scrollWidth === window.innerWidth`, aucune erreur console. Le rendu du Dashboard authentifiÃ© reste Ã  confirmer par l'utilisateur (mur d'authentification, pas de session de test disponible).
- **Raison** : Aucune contention `overflow-x` n'existait nulle part dans l'app â€” la page se dimensionnait sur l'Ã©lÃ©ment le plus large (carte, dropdown, menu cachÃ©) plutÃ´t que sur la largeur de l'Ã©cran, donnant l'impression d'une page "Ã  plat" sans conteneur englobant.

[2026-07-06] [PRO] Feature : Double appartenance "PÃ©pite" + fix critique notifications â†’ RÃ©sultat :
- **Bug critique corrigÃ© (`backend/notifications.py`)** : `notify_deal()` rÃ©fÃ©renÃ§ait `HIGH_PRIORITY_VERDICTS` (variable commentÃ©e) et `profit` (jamais dÃ©fini dans cette fonction) â†’ `NameError` systÃ©matique Ã  chaque PÃ©pite trouvÃ©e. Comme `bot.py::run_scan()` n'a pas de `except` sur sa boucle des villes (seulement un `finally`), ce crash interrompait le scan des villes restantes dÃ¨s qu'une PÃ©pite Ã©tait dÃ©tectÃ©e. `HIGH_PRIORITY_VERDICTS` rÃ©activÃ©, `profit` recalculÃ© localement.
- **`prompts.json`** (`main_analysis_prompt`) : Nouveau champ IA `also_qualifies_pepite` (boolÃ©en). L'IA le met Ã  `true` quand le verdict principal est `FAST_FLIP`/`LUTHIER_PROJ`/`CASE_WIN`/`COLLECTION` ET que les critÃ¨res PÃ©pite sont aussi remplis (Marge > 100% et > 150$ OU Marge > 30% et modÃ¨le iconique).
- **`backend/notifications.py`** : `notify_deal()` dÃ©clenche aussi la notification (prioritÃ© haute) quand `also_qualifies_pepite` est vrai, mÃªme si le verdict principal n'est pas `PEPITE`. Sujet/corps mentionnent "(Aussi PÃ©pite â­�)".
- **`src/hooks/useDealsManager.js`** : `matchesVerdictFilter` fait apparaÃ®tre ces annonces aussi dans le filtre "PÃ©pites" ; `verdictCounts` les compte aussi dans ce compteur (sans dupliquer le total `ALL`).
- **`src/components/DealCard.jsx`** : Badge secondaire "ðŸ’Ž Aussi PÃ©pite" affichÃ© Ã  cÃ´tÃ© du badge du verdict principal (carte + modale).
- **Bug annexe corrigÃ© (`backend/notifications.py`)** : `NtfyNotifier.send()` plantait silencieusement (`UnicodeEncodeError`, catchÃ©e) sur les titres contenant Ã©mojis/accents â€” headers HTTP en Latin-1 uniquement. CorrigÃ© via encodage RFC 2047 (`email.header.Header`, `maxlinelen=998` pour Ã©viter le repliement multi-ligne invalide en HTTP), conformÃ©ment Ã  la documentation officielle ntfy.sh.
- **Raison** : Un projet de lutherie ou un case win peut Ãªtre *aussi* exceptionnellement rentable ; le figer dans une seule catÃ©gorie le rendait invisible du filtre/notifications "PÃ©pites". Le bug de notification dÃ©couvert au passage minait directement l'objectif du bot (scan interrompu Ã  chaque vraie trouvaille).

[2026-07-06] [PRO] Doc : Migration de `docs/` vers la structure Diataxis â†’ RÃ©sultat :
- **RÃ©organisation** (`git mv`, historique prÃ©servÃ©) : `docs/management/` (`JOURNAL.md`, `TODO.md`, `plans/MULTI_USER_PLAN.md`), `docs/reference/` (`ARCHITECTURE.md`, `DATA_FLOW.md`, `STATE_MODELS.md`, `UI_UX_ANALYSIS.md`), `docs/explanation/` (`PROJECT_OVERVIEW.md`, `STATS_REFLEXION.md`).
- **`CLAUDE.md`** : Ã‰tape 3 et tableau "Fichiers ClÃ©s" mis Ã  jour vers les nouveaux chemins ; correction de la rÃ©fÃ©rence erronÃ©e `backend/main.py` â†’ `main.py` (racine, vrai point d'entrÃ©e).
- **`AI_BRIEFING.md`** : Chemins de l'Ã‰tape 3 alignÃ©s sur la nouvelle arborescence.
- **`docs/management/TODO.md`** : Lien relatif vers `STATS_REFLEXION.md` corrigÃ© (`../explanation/STATS_REFLEXION.md`).
- **Skill partagÃ© `~/.claude/skills/document/SKILL.md`** : GÃ©nÃ©ralisÃ© â€” ne rÃ©fÃ©rence plus une convention figÃ©e (ex-MoneyBot) ; lit dÃ©sormais le `CLAUDE.md`/`AGENTS.md` du projet courant pour suivre sa convention documentaire exacte, avec repli heuristique (Diataxis ou fichiers plats) si rien n'est prÃ©cisÃ©.
- **Raison** : Le skill `/document` appliquait par erreur la convention Diataxis propre Ã  MoneyBot lors d'une session Guitar Hunter (qui Ã©tait encore Ã  plat). Aligner Guitar Hunter sur Diataxis et rendre le skill gÃ©nÃ©rique Ã©vite ce dÃ©calage pour tous les projets.

[2026-07-06] [PRO] Fix : Images sans rapport (vÃ©hicules, bateaux...) dans les annonces â†’ RÃ©sultat :
- **`backend/scraping/parser.py`** : `ListingParser.parse_details_page()` accepte dÃ©sormais un paramÃ¨tre `fb_id` et exclut du rÃ©sultat toute image entourÃ©e d'un lien `<a href="/marketplace/item/{AUTRE_ID}/...">` â€” ces vignettes appartiennent au bloc "Suggestions" que Facebook affiche systÃ©matiquement sous la description de l'annonce, pas aux vraies photos du produit.
- **`backend/scraping/core.py`** : Ajout de `_is_valid_detail_page()` (garde-fou dÃ©tectant une redirection vers `/login`, un captcha, ou une URL ne correspondant plus Ã  l'annonce ciblÃ©e) utilisÃ© dans `scan_marketplace()` et `scan_specific_url()` avant l'extraction des dÃ©tails ; log `debug` temporaire de l'URL de la fiche dÃ©tail chargÃ©e (`[DIAG]`) conservÃ© pour un diagnostic futur.
- **`backend/scraping/test_core.py`** (nouveau) : 4 tests unitaires couvrant `_is_valid_detail_page` (page valide, redirection feed, redirection login, ID diffÃ©rent).
- **Diagnostic rÃ©el** : reproduit sur une annonce publique (`.../marketplace/item/1680540959879684/`) â€” 19 images extraites avant correctif (16 Ã©taient des suggestions d'autres annonces : voiture, bateau, meubles...) contre 3 aprÃ¨s correctif (toutes les vraies photos du produit).
- **Raison** : Le filtre initial se basait uniquement sur la taille de l'image (>300Ã—300px) et le domaine CDN (`scontent`), ce qui capturait aussi les vignettes du bloc "Suggestions" â€” visible surtout sur les annonces ayant peu de vraies photos (le plafond de collecte n'Ã©tant alors pas atteint par les vraies photos seules).

[2026-07-05] [PRO] Feature : Partage d'annonce sans authentification â†’ RÃ©sultat :
- **`firebase/firestore.rules`** : Ajout d'une rÃ¨gle de lecture publique sur la collection `shared_deals/{dealId}`. Ã‰criture rÃ©servÃ©e aux utilisateurs authentifiÃ©s.
- **`firebase.json`** : Correction d'un espace parasite dans le chemin des rÃ¨gles Firestore (empÃªchait `firebase deploy --only firestore:rules`).
- **`src/services/firestoreService.js`** : Ajout de `createSharedDeal(deal)` (snapshot public dans `shared_deals/`) et `getSharedDeal(dealId)` (lecture sans auth).
- **`src/components/DealCard.jsx`** : `handleShare` Ã©crit d'abord le snapshot dans Firestore, puis gÃ©nÃ¨re un lien `?shareId={deal.id}` au lieu de `?dealId=`.
- **`src/components/SharedDealPage.jsx`** : Nouveau composant public affichant titre, prix, localisation, images, scores IA, analyse et lien FB â€” sans login requis.
- **`src/App.jsx`** : DÃ©tection de `?shareId=` avant le mur d'auth â†’ rendu de `SharedDealPage` directement.
- **Raison** : Un destinataire qui reÃ§oit un lien partagÃ© ne doit pas Ãªtre forcÃ© Ã  crÃ©er un compte pour consulter l'annonce.

[2026-05-06] [PRO] Refonte Aide UX & Robustesse Internationale â†’ RÃ©sultat :
- **`src/components/HelpOverlay.jsx`** : Refonte totale du guide de prise en main. Transition vers un guide technique en 4 Ã©tapes (Cibles, Vigilance, Lancement, Analyse) avec explications prÃ©cises sur le "Rayon 0" (Recherche Stricte) et la frÃ©quence de scan. Isolation des rÃ©glages IA dans une section "Expertise AvancÃ©e".
- **`src/components/ConfigPanel.jsx`** : Ajout d'un bouton **"Lancer le Scan"** direct pour dÃ©clencher la recherche aprÃ¨s configuration. Simplification radicale de l'ajout de villes : suppression du formulaire secondaire, l'ajout se fait dÃ©sormais directement via le bouton "+" du champ de recherche principal.
- **`backend/bot.py`** : Correction d'une `NameError` critique (`city_coords`) lors de l'ajout automatique de ville.
- **`backend/scraping/city_finder.py`** : Hardening de la recherche de villes Facebook. Support des versions internationales (Lieu/Location/Lugar), dÃ©tection des alias d'URL (non-numÃ©riques), et nettoyage forcÃ© du champ de recherche (`Ctrl+A -> Backspace`).
- **Raison** : AmÃ©liorer l'onboarding utilisateur, clarifier les paramÃ¨tres vitaux de scan et assurer que le bot peut s'exporter sur n'importe quel marchÃ© (Bordeaux, Paris, etc.) sans friction technique.


[2026-05-06] [PRO] Robustesse Auth & Scraping: Fix duplication et sÃ©curisation sessions â†’ RÃ©sultat :
- **`src/hooks/useAuth.js`** : Centralisation de l'onboarding via `ensureUserDoc` (DRY). Propagation des erreurs Firestore vers l'UI dans `onAuthStateChanged` (Status Warning).
- **`backend/scraping/core.py`** : SÃ©curisation du `finally` (fix `page` non-dÃ©finie) et clarification du pÃ©rimÃ¨tre de `get_city_id_and_coords` (gÃ©ocodage dÃ©lÃ©guÃ© Ã  Nominatim).
- **Raison** : Ã‰liminer la dette technique de duplication et amÃ©liorer le feedback utilisateur en cas d'erreur de permissions Firestore.

[2026-05-06] [PRO] Correctifs VisibilitÃ© UI & GÃ©o-localisation Paris â†’ RÃ©sultat :
- **`src/components/Navbar.jsx`** : AmÃ©lioration de la visibilitÃ© du bouton d'aide (ajout du label "Aide" sur Desktop et augmentation du contraste).
- **`src/components/Dashboard.jsx`** : ImplÃ©mentation d'un bandeau d'erreur global et correction d'une `ReferenceError` (contexte mal dÃ©structurÃ©).
- **`backend/bot.py` & `core.py`** : Fiabilisation de l'ajout de ville. PrioritÃ© aux coordonnÃ©es extraites de Facebook et Ã©largissement de la recherche Nominatim pour supporter **n'importe quelle ville dans le monde** (suppression des restrictions rÃ©gionales). ImplÃ©mentation du scraping automatisÃ© de l'ID de ville Facebook via le sÃ©lecteur de lieu.
- **`src/components/MapView.jsx`** : Correction de l'interaction avec les InfoWindows (suppression du `mouseout` agressif) et restauration/styling du bouton de fermeture.
- **`src/components/ConfigPanel.jsx`** : Ajout de consignes textuelles pour guider l'utilisateur dans l'ajout de nouvelles villes.
- **Raison** : RÃ©soudre les points de friction utilisateur et assurer la stabilitÃ© de l'interface aprÃ¨s l'ajout des nouveaux mÃ©canismes de feedback.

[2026-05-05] [FLASH] IntÃ©gration de la Documentation Utilisateur â†’ RÃ©sultat :
- **`src/components/HelpOverlay.jsx`** : CrÃ©ation d'un guide interactif premium dÃ©taillant le Radar IA (scores Gemini), les Verdicts (badges), les Commandes (Refresh/Cleanup) et les Notifications (Email/Ntfy).
- **`src/components/Navbar.jsx`** : Ajout du bouton d'aide (`HelpCircle`) Ã  cÃ´tÃ© des paramÃ¨tres.
- **`src/components/Dashboard.jsx`** : Gestion de l'Ã©tat d'affichage de l'aide et rendu de l'overlay.
- **Raison** : AmÃ©liorer l'autonomie de l'utilisateur final et clarifier les fonctionnalitÃ©s de l'IA et du systÃ¨me d'alertes.

[2026-05-05] [PRO] Audit multi-tenant & correctifs onboarding â†’ RÃ©sultat :
- **`src/hooks/useAuth.js`** : Initialisation automatique du document utilisateur Firestore lors du `signUp` ET du `onAuthStateChanged` (session persistante), garantissant que le backend dÃ©couvre tout utilisateur actif mÃªme s'il existait dÃ©jÃ .
- **`backend/bot.py`** : Assouplissement du gÃ©ocodage Nominatim (suppression de la restriction stricte Canada) permettant l'ajout de villes internationales comme Paris.
- **`main.py`** : 
    - **Watchdog** : Correction d'un bug critique oÃ¹ le `firestore_handler` n'Ã©tait pas recrÃ©Ã© lors d'un redÃ©marrage de thread, coupant les logs.
    - **Performance** : Passage de la commande `ADD_CITY` en asynchrone pour ne plus geler le bot pendant le scraping/gÃ©ocodage.
    - **HygiÃ¨ne** : ImplÃ©mentation du nettoyage automatique des bots pour les utilisateurs supprimÃ©s de Firestore.
- **`src/components/Navbar.jsx`** : Ajout d'un tooltip sur le point de statut "Auth" pour afficher les messages d'erreur (ex: "Dossier Python introuvable").
- **`src/components/LogViewer.jsx`** : Correction de l'envoi de l'UID lors de la suppression des logs.

[2026-05-05] [PRO] Onboarding Dynamique & Isolation du Logging â†’ RÃ©sultat :
- **`main.py`** : ImplÃ©mentation de `discover_users` (scan cyclique toutes les 30s) et `start_user_bot`. Transition d'une liste statique vers un mode multi-tenant rÃ©actif.
- **`backend/logging_config.py`** : Isolation du logging par utilisateur. Les logs de chaque bot sont dÃ©sormais dirigÃ©s vers leur propre collection Firestore (`bot.XXXX`) sans interfÃ©rer avec le logger racine ou les autres utilisateurs.
- **Watchdog** : Surveillance active des threads par UID. RedÃ©marrage automatique en cas de crash.
- **Raison** : Permettre l'ajout de nouveaux utilisateurs Ã  chaud sans redÃ©marrage serveur et garantir l'Ã©tanchÃ©itÃ© des logs en production.

[2026-05-05] [PRO] Restauration des fonctionnalitÃ©s d'authentification Frontend â†’ RÃ©sultat :
- **`src/hooks/useAuth.js`** : RÃ©implÃ©mentation de `signUp` (createUserWithEmailAndPassword) et `resetPassword` (sendPasswordResetEmail).
- **`src/components/LoginPage.jsx`** : Refonte de l'interface pour inclure les modes Inscription et RÃ©initialisation de mot de passe, avec gestion des messages de succÃ¨s et d'erreur.
- **Raison** : Correction de la disparition des boutons suite Ã  une sÃ©curisation trop stricte (Task 1.2) et perte d'accÃ¨s utilisateur.

[2026-04-10] [PRO] Ajout des notifications email par utilisateur (SMTP Gmail) â†’ RÃ©sultat :
- Task 1.4 : `firestoreService.js:migrateOldDataToNewUser` â†’ Email admin â†’ `VITE_ADMIN_EMAIL` env var, flag `migrationDone`, try/catch granulaire par Ã©tape (config âœ… / villes âœ… / annonces âœ…).

**PHASE 2 â€” Robustesse Backend [6 Tasks]**
- Task 2.1 : `main.py` â†’ `try/except` autour de `GuitarHunterBot()` pour chaque user. Ã‰checs isolÃ©s par user sans crash global.
- Task 2.2 : `main.py` â†’ Boucle watchdog `while True` (30s interval) redÃ©marre threads morts. Capteur de crashes `t.is_alive()`.
- Task 2.3 : `bot.py` + `main.py` â†’ `threading.Semaphore(MAX_CONCURRENT_BROWSERS)` partagÃ©. Chaque `FacebookScraper` acquis/libÃ©rÃ©. Limite navigateurs simultanÃ©s.
- Task 2.4 : `main.py` â†’ `threading.Lock()` sur `in_flight_command_ids`, `.discard()` au lieu de `.remove()` pour Ã©viter `KeyError`.
- Task 2.5 : `bot.py` â†’ `session_processed_ids` â†’ `@property` sur `threading.local()`. IsolÃ© par thread, `.clear()` au lieu de `= set()`.
- Task 2.6 : `bot.py` â†’ Logger par user `logging.getLogger(f"bot.{user_id[:8]}")`, tous les `logger.` remplacÃ©s par `self.logger.`.

**Code Review â€” 3 Rondes validÃ©es**
- Ronde 1 (Exactitude) : 1 bug Firestore rules trouvÃ© et corrigÃ© (document parent).
- Ronde 2 (CohÃ©rence) : ChaÃ®ne useAuth â†’ AuthContext â†’ LoginPage OK. SÃ©maphore propagÃ© correctement.
- Ronde 3 (Edge Cases) : Acceptables. Watchdog sans backoff reste backlog.

**Variables d'Environnement Ã  ajouter**
```
VITE_ADMIN_EMAIL=ton@email.com
MAX_CONCURRENT_BROWSERS=3
```

[2026-03-21] [PRO] Action : Raffinement Login & Data Migration V2 â†’ RÃ©sultat : (1) **Frontend** : Ajout du mode Inscription (`signUp`) dans `LoginPage.jsx` avec autocomplÃ©tion pour gestionnaires de mots de passe. (2) **Migration** : ImplÃ©mentation de `migrateOldDataToNewUser` dans `firestoreService.js` pour copier automatiquement les donnÃ©es de l'ID historique vers le compte `ludovic.lebart@gmail.com` lors de sa premiÃ¨re connexion (si profil vide). (3) **SÃ©curitÃ©** : Isolation stricte garantie par `getRefs(userId)`.

[2026-03-21] [PRO] Action : ImplÃ©mentation du systÃ¨me Multi-Utilisateurs â†’ RÃ©sultat : (1) **Backend** : `config.py` supporte `USER_IDS_TARGET` (liste d'UIDs sÃ©parÃ©s par virgule, rÃ©trocompatible `USER_ID_TARGET`). `bot.py` reÃ§oit `app_id` et `user_id` comme paramÃ¨tres explicites. `main.py` lance un thread `main_loop` indÃ©pendant par utilisateur. (2) **Frontend** : `useAuth.js` migrÃ© vers Firebase Auth email/password. `AuthContext.jsx` et `LoginPage.jsx` crÃ©Ã©s. `firestoreService.js` dynamisÃ© via `getRefs(userId)`. Tous les hooks propagent `user.uid`. `App.jsx` affiche `LoginPage` si non connectÃ©. (3) Build Vite validÃ© (exit code 0).


[2026-03-05] [PRO] Action : Fiabilisation des comparaisons de prix et anti-spam Ntfy â†’ RÃ©sultat : (1) CrÃ©ation d'une fonction `_normalize_price` dans `bot.py` pour comparer sereinement les prix (ex: "150$" vs " 150.0") et Ã©viter les fausses "mises Ã  jour". (2) ImplÃ©mentation d'un filtre dans `notifications.py` (`notify_deal`) pour ne dÃ©clencher une alerte de "Baisse de Prix" que si la baisse est de plus de 5% ou de plus de 50$.

[2026-03-05] [PRO] Action : DÃ©tection et intÃ©gration visuelle des Baisses de Prix â†’ RÃ©sultat : (1) Backend (`bot.py`, `repository.py`) mis Ã  jour pour Ã©craser le prix Firestore et conserver l'ancien prix (`original_price`) lors d'une baisse. (2) Les annonces subissant une baisse repassent dÃ©sormais au travers du pipeline de l'IA avec le nouveau prix. (3) Frontend (`DealCard.jsx`) mis Ã  jour pour afficher un badge vert vif Â« Baisse -XX$ Â» si le prix a chutÃ©, visible sur la miniature et dans la modale IA.

[2026-03-05] [PRO] Action : ImplÃ©mentation complÃ¨te de la sÃ©lection 3-Tiers et correction Gemini 2.5 Pro â†’ RÃ©sultat : (1) Correction du bug oÃ¹ l'Expert Pro Ã©tait Ã©crasÃ© vers Flash Ã  cause d'une omission dans l'UI. (2) Ajout du modÃ¨le `gemini-2.5-pro` Ã  la liste des modÃ¨les disponibles dans l'interface. (3) Ajout d'un 3Ã¨me menu dÃ©roulant dans le `ConfigPanel` pour configurer le modÃ¨le de l'Analyste (Tier 2 - `mainModel`) de maniÃ¨re indÃ©pendante du Portier (Tier 1) et de l'Expert (Tier 3). (4) Mise Ã  jour du hook `useBotConfig.js` pour gÃ©rer les 3 modÃ¨les avec les bonnes valeurs par dÃ©faut du backend.

[2026-02-28] [PRO] Action : ImplÃ©mentation de la redirection par `dealId` et amÃ©lioration du partage â†’ RÃ©sultat : (1) Le composant `Dashboard.jsx` lit dÃ©sormais le paramÃ¨tre `dealId` de l'URL au chargement, sÃ©lectionne l'annonce correspondante et force l'affichage en mode "Carte" (`MapView`). (2) Le bouton de partage dans `DealCard.jsx` gÃ©nÃ¨re un lien vers l'application avec le `dealId` de l'annonce, permettant un partage direct et une ouverture de la modale de dÃ©tail. (3) La logique de sÃ©lection de l'annonce depuis l'URL a Ã©tÃ© dÃ©placÃ©e de `useDealsManager.js` vers `Dashboard.jsx` pour une meilleure gestion de l'Ã©tat de l'interface.


[2024-07-30] [PRO] Action : ImplÃ©mentation d'une stratÃ©gie de rotation d'IP (Proxies) â†’ RÃ©sultat : (1) Ajout d'une liste `PROXIES` dans `config.py` pour centraliser la configuration. (2) Modification de `FacebookScraper` (`backend/scraping/core.py`) pour sÃ©lectionner alÃ©atoirement un proxy de la liste Ã  chaque instanciation d'un navigateur Playwright. (3) La rotation est effective car le bot instancie un scraper temporaire pour chaque tÃ¢che, garantissant une nouvelle IP pour chaque scan de ville ou action manuelle.

[2024-07-30] [FLASH] Action : Analyse du diagnostic de dÃ©tection du scraper par Facebook â†’ RÃ©sultat : Le diagnostic est validÃ©. Le projet a dÃ©jÃ  implÃ©mentÃ© la plupart des contre-mesures (session persistante, randomisation User-Agent/Viewport, jitter, intÃ©gration du tÃ©lÃ©chargement d'images, flags Playwright furtifs) documentÃ©es dans les Sessions 35 et 29. Une stratÃ©gie de rotation d'IP reste une amÃ©lioration potentielle.

[2026-02-27] [FLASH] Action : Optimisation Mobile du LogViewer â†’ RÃ©sultat : ForÃ§age de l'affichage en plein Ã©cran (`inset-0`, `rounded-none`) sur les petits Ã©crans pour Ã©viter la perte de visibilitÃ© de la console. Le comportement flottant est conservÃ© pour les Ã©crans larges (`sm:`).

[2026-02-27] [FLASH] Action : Correction de la lisibilitÃ© de la console (LogViewer) et du ConfigPanel â†’ RÃ©sultat : Passage d'un fond semi-transparent (`bg-slate-900/95`) Ã  un fond totalement opaque (`bg-slate-950`). Suppression du `backdrop-blur` qui causait des interfÃ©rences visuelles lors de la superposition sur des images ou des cartes.

[2026-02-27] [FLASH] Action : Correction du blocage du scroll sur mobile â†’ RÃ©sultat : Suppression des contraintes `min-height: 100%` et `overflow-x: hidden` sur les Ã©lÃ©ments racines dans `index.css`, `App.jsx` et `Dashboard.jsx`. Le dÃ©filement vertical natif et le geste de rafraÃ®chissement ("pull-to-refresh") sont dÃ©sormais fonctionnels sur mobile.

[2026-02-26] [FLASH] Action : Restauration du Bouton de Partage â†’ RÃ©sultat : Ajout de l'icÃ´ne `Share2` et de la fonction `handleShare` dans `DealCard.jsx`. Le bouton supporte dÃ©sormais le partage natif (API `navigator.share`) et la copie automatique dans le presse-papier avec confirmation visuelle ("Lien copiÃ© !") en cas de fallback.

[2026-02-26] [FLASH] Action : Correction Critique du Scroll â†’ RÃ©sultat : Restauration du dÃ©filement vertical en supprimant `overflow: hidden` de `index.css`. Ajout de `overflow-x-hidden` sur le `body` et le `Dashboard` pour empÃªcher les dÃ©calages horizontaux tout en conservant une expÃ©rience fluide sur PC et Mobile.

[2026-02-26] [FLASH] Action : Extraction de la Date de Mise en Ligne â†’ RÃ©sultat : ImplÃ©mentation du sÃ©lecteur `abbr[aria-label]` dans `ListingParser` pour capturer l'Ã¢ge de l'annonce. Le champ `published_at_raw` est dÃ©sormais propagÃ© dans `listing_data` et stockÃ© dans Firestore.

[2026-02-26] [FLASH] Action : Raffinement des Prompts pour les Lots (Bundles) â†’ RÃ©sultat : Mise Ã  jour de `prompts.json` (directives Portier et Prompt Principal). L'IA autorise dÃ©sormais explicitement les instruments vendus avec des accessoires mineurs (micros, cÃ¢bles, supports). Le verdict `REJECTED_ITEM` est dÃ©sormais restreint aux annonces vendant *uniquement* des accessoires non autorisÃ©s.

[2026-02-26] [PRO] Action : Finalisation du Dashboard (Radar & Marques) & Ajout de Champs IA â†’ RÃ©sultat : (1) IntÃ©gration de la librairie `recharts` dans le frontend. (2) Remplacement des placeholders dans `MockupStatsView.jsx` par un **Radar Chart** affichant le profil moyen des 5 scores Gemini et un **Bar Chart** pour la distribution du Top 5 des marques. Les donnÃ©es sont calculÃ©es dynamiquement depuis l'inventaire filtrÃ©. (3) Backend : Ajout des clÃ©s `brand`, `model_name`, `production_year`, et `country_of_origin` au dictionnaire JSON attendu dans `main_analysis_prompt` (`prompts.json`), enrichissant considÃ©rablement la granularitÃ© future de l'analyse IA.

[2026-02-26] [PRO] Action : Audit approfondi des Statistiques et du Tunnel de Conversion â†’ RÃ©sultat : VÃ©rification du code de `MockupStatsView.jsx`. (1) Le **Tunnel de Conversion** Ã  3 niveaux est dÃ©jÃ  fonctionnel et alimentÃ© par les donnÃ©es rÃ©elles de Firestore. (2) Les **KPIs Financiers** (Marge latente, ROI, Score moyen) sont calculÃ©s dynamiquement. (3) Identification des manques : le Radar Chart (nÃ©cessite Recharts) et la distribution par Marque (nÃ©cessite extraction `brand` backend) restent Ã  implÃ©menter. Mise Ã  jour de la `TODO.md` pour reflÃ©ter cet Ã©tat d'avancement supÃ©rieur aux attentes.

[2026-02-26] [PRO] Action : ImplÃ©mentation d'une Protection Anti-Botting (Stealth) Globale â†’ RÃ©sultat : Correction du blocage par Facebook lors du rescraping massif. (1) **Randomisation** : Injection de User-Agents tournants et de Viewports alÃ©atoires dans `FacebookScraper` (`core.py`). (2) **FurtivitÃ© Playwright** : Ajout de flags spÃ©cifiques (`AutomationControlled`, `infobars`) pour masquer l'automatisation. (3) **DÃ©tection de Blocage** : Interruption propre en cas de redirection vers `/login` ou CAPTCHA. (4) **Rotation & Jitter** : Le script `migrate_images.py` redÃ©marre maintenant le navigateur toutes les 15 requÃªtes et utilise des dÃ©lais alÃ©atoires (jitter) pour simuler un comportement humain. Test `--dry-run` validÃ© avec succÃ¨s.

[2026-02-26] [PRO] Action : Raffinement des Interactions Cartographiques (Tooltip & Pins) â†’ RÃ©sultat : Ajout d'InfoWindows enrichies au survol (PC) et au clic (Mobile) sur les marqueurs Google Maps. Les bulles incluent dÃ©sormais une miniature, le titre, le score IA et la valeur estimÃ©e dans un design Dark Theme. Le marqueur sÃ©lectionnÃ© est dÃ©sormais visuellement identifiÃ© par une taille supÃ©rieure.

[2026-02-26] [PRO] Action : Optimisation de l'ExpÃ©rience Mobile (Overlay & Navigation) â†’ RÃ©sultat : (1) Correction de l'affichage de l'annonce sur mobile : elle s'affiche dÃ©sormais en "Full-Screen Overlay" par-dessus la carte au lieu de la compresser, garantissant une lisibilitÃ© maximale. (2) Inversion de la logique de clic sur mobile : le premier clic sur un pin ouvre l'InfoWindow, le clic sur la bulle ouvre l'annonce complÃ¨te.

[2026-02-26] [PRO] Action : AmÃ©lioration UX de la DealCard et de la Modale IA â†’ RÃ©sultat : (1) Le bouton de rÃ©-analyse est devenu un menu dÃ©roulant dynamique offrant les options "Scan Standard" et "Luthier Expert", gÃ©rÃ© par `useState` pour supporter le survol (PC) et le clic (Mobile). (2) Factorisation de la barre d'actions complÃ¨te (Favori, Scan, Rejeter, Suppression, Facebook) pour l'injecter directement dans l'en-tÃªte de la Modale d'Expertise IA, offrant une paritÃ© fonctionnelle totale entre les vues.

[2026-02-26] [PRO] Action : Correction UI Mobile du Menu des Verdicts (Mockup V2) â†’ RÃ©sultat : Le composant `VerdictDropdown` s'Ã©crasait et coupait le texte sÃ©lectionnÃ© sur les petits Ã©crans. Application de `whitespace-nowrap` sur le bouton principal et dÃ©finition d'une largeur fixe (`w-56`) avec `truncate` sur les options du menu dÃ©roulant dans `MockupDashboard.jsx` pour garantir un affichage propre sur une seule ligne.

[2026-02-26] [PRO] Action : Correction du Responsive Design et RÃ©solution de la "Double Navbar" Mobile (Mockup V2) â†’ RÃ©sultat : Le rendu mobile souffrait d'un overflow horizontal causÃ© par la Navbar V1 qui restait active en arriÃ¨re-plan avec une largeur minimale incompressible. (1) DÃ©sactivation conditionnelle de la Navbar V1 dans `App.jsx` lorsque le Mockup V2 est ouvert, Ã©liminant la "bande blanche" sur mobile. (2) Refonte du container de recherche/filtres dans `MockupDashboard` en utilisant un layout `grid-cols-1 md:flex` pour forcer un empilement vertical propre des Ã©lÃ©ments (Recherche, Favoris, Vues, Bouton X) sur petits Ã©crans. (3) Application de `whitespace-nowrap` sur l'indicateur de statut du bot dans `MockupNavbar` pour empÃªcher le texte de se casser sur deux lignes, et ajustement global des marges internes (padding) pour maximiser l'espace utile sur smartphone.

[2026-02-26] [PRO] Action : RÃ©solution de l'erreur Greenlet (Cannot switch to a different thread) sur le backend â†’ RÃ©sultat : L'implÃ©mentation de tÃ¢ches de scraping en arriÃ¨re-plan (ex: REFRESH, SCAN_URL) gÃ©nÃ©rait des crashs asynchrones car l'instance Playwright globale (`self.scraper`) du thread principal ne pouvait pas Ãªtre partagÃ©e avec les threads secondaires. La solution a Ã©tÃ© de retirer le contexte Playwright global dans le bot (`bot.py`) et la boucle principale (`main.py`). DÃ©sormais, chaque action appelant le Scraper (comme `run_scan`, `scan_specific_url` ou `cleanup_sold_listings`) instancie son propre scraper temporaire (`temp_scraper = FacebookScraper()`) localement et le libÃ¨re `finally: temp_scraper.close_session()`. Cette architecture garantit l'isolation absolue des navigateurs Chromium par thread.

[2026-02-25] [PRO] Action : Raffinement final de l'UI V2 (Modale IA, Barre de Filtres, Map Centering, Raccourci Favoris) â†’ RÃ©sultat : (1) Restauration de la section "Analyse DÃ©taillÃ©e" dans la Modale IA : Le Markdown complet (`aiAnalysis.analysis`) s'affiche maintenant correctement avec saut de ligne grÃ¢ce Ã  `whitespace-pre-wrap` au lieu de l'ancien `aiAnalysis.reasoning` tronquÃ©. (2) Rapatriement du statut "Favoris" dans la V2 avec un double accÃ¨s : option intÃ©grÃ©e au sommet de `VerdictDropdown` + crÃ©ation d'un bouton fixe "CÅ“ur" adjacent pour un accÃ¨s ultra-rapide en un clic. (3) Dynamisme de la Carte : IntÃ©gration de la logique `fitBounds` dans `MapView.jsx` pour que la Google Map se centre et zoome automatiquement sur les annonces visibles selon les filtres actifs, avec une sÃ©curitÃ© anti-zoom extrÃªme pour les annonces solitaires.

[2026-02-25] [PRO] Action : Finalisation de l'UI/UX du Mockup V2 (Responsive, Modale IA, Barre de Filtres) â†’ RÃ©sultat : (1) Modale IA Plein Ã‰cran : Le bloc d'expertise IA collapsible a Ã©tÃ© remplacÃ© par une modale "glassmorphism" (`z-[100]`) permettant une lecture trÃ¨s confortable sur Desktop sans dÃ©former la DealCard. (2) Nettoyage Dashboard : Le compteur de rÃ©sultats et le bouton "Effacer tous les filtres" (maintenant stylisÃ© en bouton carrÃ© dynamique rouge) ont Ã©tÃ© consolidÃ©s Ã  l'intÃ©rieur de la barre de filtres principale. (3) Hauteur des cartes : RÃ©duction de la hauteur des images de `400px` Ã  `280px` pour afficher la carte entiÃ¨re sur les Ã©crans de PC portables sans scroller. (4) Correction Navbar Mobile : RÃ©solution du dÃ©bordement horizontal (`overflow-x-hidden`) en contraignant la largeur de la toolbar.
[2026-02-25] [FLASH] Action : IntÃ©gration de la galerie ImageGallery et donnÃ©es rÃ©elles dans le Mockup V2 â†’ RÃ©sultat : Remplacement du dÃ©filement horizontal basique par le composant robuste ImageGallery. Support natif du plein Ã©cran, des flÃ¨ches de navigation et de l'affichage vertical intÃ©gral (object-contain). Extraction de vÃ©ritables URLs Facebook depuis Firestore pour un rendu rÃ©aliste.

[2026-02-25] [PRO] Action : Finalisation Responsive et Logique Taxonomique Mockup V2 â†’ RÃ©sultat : (1) Correction Mobile : Le status interactif du bot reste toujours visible sur `MockupNavbar` (points info annexes masquÃ©s), et ajout d'un bouton "Fermer" sur les DealCards en vue carte sur petit Ã©cran pour Ã©viter les blocages. (2) Comptage Taxonomie : Mise Ã  jour de `buildDealCounts` pour que chaque item `FAKE_DEALS` itÃ¨re sur son chemin entier de `classification` (`ex: electrique.ampli.combo`) pour remplir parfaitement l'arbre Ã  4 niveaux. (3) UX : Retrait des choix multiples "Toutes" redondants dans les sous-niveaux de filtres. (4) Alignement du Dropdown de filtres sur les "Nouveaux Verdicts" V2 via `ALL_FILTERS_CONFIG`.

[2026-02-25] [PRO] Action : Raffinement UX approfondi du Mockup V2 â†’ RÃ©sultat : (1) Tiroir de filtres : Transformation de `MockupFilterDrawer` en un accordÃ©on imbriquÃ© en cascade Ã  4 niveaux avec badges dynamiques de comptage d'annonces. (2) Barre d'actions (`MockupDashboard`) : Remplacement du dÃ©filement horizontal des verdicts par un composant `VerdictDropdown` compact. (3) Recherche : Ajout du filtrage interactif (text/location) avec bouton de rÃ©initialisation interne. (4) Carte : ImplÃ©mentation du mode "Split-Screen" (`MockupMapView`) et du bouton toggle Liste/Carte. (5) ContrÃ´les UI (`MockupNavbar`) : IntÃ©gration de la vÃ©ritable logique `BotControls` interactive au survol, et ajout des boutons d'actions manuelles (VÃ©rification et Rescan) Ã  la racine de la Toolbar. Le prototype Mockup V2 est achevÃ© et valide toutes les recommandations heuristiques UX de l'analyse prÃ©cÃ©dente.

[2026-02-25] [PRO] Action : ImplÃ©mentation du filtre Drawer en cascade Ã  4 niveaux â†’ RÃ©sultat : `MockupFilterDrawer.jsx` entiÃ¨rement rÃ©Ã©crit avec un arbre de taxonomie `TAXONOMY_TREE` Ã  4 niveaux de profondeur. Comportement : tous les groupes sont repliÃ©s par dÃ©faut (accordÃ©on). Chaque niveau s'affiche et s'ouvre automatiquement dÃ¨s qu'un choix est fait au niveau parent (Niveau 1 : Type d'instrument, Niveau 2 : Sous-catÃ©gorie contextuelle, Niveau 3 : ModÃ¨le/Type, Niveau 4 : Marque/DÃ©tail). La sÃ©lection d'un niveau parent rÃ©initialise automatiquement tous les niveaux enfants. Le titre du groupe indique le contexte (ex : "Sous-catÃ©gorie Â· Ã‰lectrique"). Les clÃ©s de filtres dans `MockupDashboard.jsx` ont Ã©tÃ© mises Ã  jour (`level1/level2/level3/level4`). "Verdict IA" retirÃ© du Drawer (couvert par les onglets rapides en haut de la grille).


[2026-02-25] [PRO] Action : CrÃ©ation du Mockup Complet UI V2 â†’ RÃ©sultat : Prototype interactif Dark Mode complet accessible via le bouton "Mockup V2" dans la Navbar.
 Composants crÃ©Ã©s : `MockupDealCard.jsx` (image full-width, marge affichÃ©e, bloc IA collapsible, titres normalisÃ©s, hit-zones 44px), `MockupNavbar.jsx` (statuts systÃ¨me compacts, boutons Filtres et ParamÃ¨tres, bouton quitter), `MockupFilterDrawer.jsx` (volet latÃ©ral coulissant avec 4 niveaux de filtres dynamiques et taxonomie en cascade â€” les sous-catÃ©gories s'adaptent automatiquement au type sÃ©lectionnÃ©, sans bouton Appliquer), `MockupDashboard.jsx` (assemblage complet : 8 fausses annonces, filtrage live via `useMemo`, onglets verdicts rapides, 3 sections Radar/MarchÃ©/Archives, bouton "Effacer les filtres"). IntÃ©gration du vrai `ConfigPanel` ouvert via le bouton âš™ï¸�. Le `App.jsx` bascule entre l'interface rÃ©elle et le Mockup V2 via un `useState` sans modifier les donnÃ©es ni les hooks Firestore.

[2026-02-25] [PRO] Action : Extension de l'analyse UI/UX (Deep Heuristic Evaluation) â†’ RÃ©sultat : Analyse des dÃ©tails qualitatifs au-delÃ  du simple layout.

[2026-02-25] [PRO] Action : RÃ©vision de l'analyse UI/UX suite aux retours utilisateurs â†’ RÃ©sultat : Mise Ã  jour de `docs/UI_UX_ANALYSIS.md` pour se concentrer sur les dÃ©fauts structurels critiques : 1) DÃ©mantÃ¨lement du panneau latÃ©ral (Aside) qui gaspille 20% de la largeur. 2) Refonte des filtres horizontaux qui dÃ©bordent en un "Drawer" latÃ©ral. 3) Correction de la DealCard Mobile pour forcer l'image en pleine largeur (`w-full`). 4) Nettoyage des boutons d'action (remplacement des textes par des icÃ´nes comme FB). Le `TODO.md` a Ã©tÃ© rÃ©Ã©crit avec ces nouvelles prioritÃ©s absolues.

[2026-02-25] [PRO] Action : Analyse approfondie de l'UI/UX et ajout de `docs/UI_UX_ANALYSIS.md` â†’ RÃ©sultat : Validation de la structure d'interface actuelle (Dashboard SaaS, code couleur sÃ©mantique). DÃ©finition de 4 axes prioritaires documentÃ©s dans le TODO pour un design Premium : Dark Mode, Micro-interactions visuelles, Refonte par "Tiroir" de la taxonomie des filtres, IntÃ©gration d'un panneau de statistiques.

[2026-02-25] [PRO] Action : ImplÃ©mentation du stockage pÃ©renne des images via Firebase Storage â†’ RÃ©sultat : Les URLs CDN de Facebook expirent aprÃ¨s 1-3 jours, rendant les images des annonces archivÃ©es inaccessibles. (Action 1) Init du bucket Storage dans `backend/database.py` : passage du `storageBucket` Ã  `firebase_admin.initialize_app()` et exposition de `self.bucket`. (Action 2) Ajout de `FIREBASE_STORAGE_BUCKET` et `IMAGE_RETENTION_REJECTED_DAYS` (30j) dans `config.py`. (Action 3) Le `FirestoreRepository` passe le bucket aux mÃ©thodes `upload_images_to_storage()` (upload + URL publique) et `purge_rejected_images()` (purge lifecycle). (Action 4) Le bot (`bot.py`) uploade systematiquement les images avant de sauvegarder chaque annonce et expose `purge_rejected_images()` pour le scheduler. (Action 5) Le frontend (`DealCard.jsx`) utilise `storageImageUrls || imageUrls` comme fallback. (Action 6) CrÃ©ation du script one-shot `backend/scripts/migrate_images.py` pour migrer les annonces existantes (test validitÃ© URL, re-scraping si expirÃ©e, upload Storage). (Action 7) Branchement de la purge lifecycle au `TaskScheduler` (`services.py`) via `purge_func=` â€” job hebdomadaire automatique. (Action 8) Correction du dry-run du script de migration : Playwright ne se lanÃ§ait pas inutilement, seulement un HTTP HEAD pour tester la validitÃ© des URLs. (Action 9) Ajout de `run.bat` et du workflow `.agent/workflows/run-venv.md` pour forcer l'usage du venv.

[2026-02-24] [FLASH] Action : Ajout de la taxonomie aux annonces rejetÃ©es par le Portier â†’ RÃ©sultat : Les annonces immÃ©diatement rejetÃ©es (BAD_DEAL, REJECTED_ITEM) ne possÃ©daient pas de champ `classification`, empÃªchant leur filtrage par type dans l'UI. (Action 1) Modification de `gatekeeper_verbosity_instruction` dans `prompts.json` pour exiger la classification dans le JSON de sortie du Portier (Tier 1). (Action 2) Mise Ã  jour de `backend/analyzer.py` pour extraire cette classification et l'inclure dans le payload de retour lors du coupe-circuit. Ce correctif affine l'expÃ©rience utilisateur lors de l'exploration des archives rejetÃ©es.

[2026-02-24] [PRO] Action : Simplification de la taxonomie des accessoires et durcissement des rejets â†’ RÃ©sultat : L'IA laissait passer les pÃ©dales et les supports de guitare en les amalgamant sous la clÃ© racine `accessoire_etui`. (Action 1) Renommage de la clÃ© racine de la taxonomie `accessoire_etui` en `etui_housse` et suppression du niveau imbriquÃ© `protection` pour aplatir la structure. (Action 2) Modification stricte du prompt du Portier (Tier 1) et du prompt principal pour ordonner le rejet immÃ©diat (`REJECTED_ITEM`) de tout accessoire n'Ã©tant pas un Ã©tui rigide ou une housse (ex: pÃ©dales, supports, ficelles, micros).

[2026-02-24] [PRO] Action : Correction de la profondeur de filtrage et de la justification des rejets (Frontend) â†’ RÃ©sultat : (Bug 1) Le filtre de taxonomie (FilterBar) n'affichait que 3 niveaux, empÃªchant la sÃ©lection des feuilles (ex: `Parlor`) suite Ã  l'ajout des catÃ©gories racines (`guitare`, `ampli`, etc.). Ajout d'un 4Ã¨me niveau `level4Filter` dans `useDealsManager.js` et `FilterBar.jsx` pour restaurer la granularitÃ© complÃ¨te. (Bug 2) Les annonces rejetÃ©es par l'Intelligence Artificielle restaient affichÃ©es avec le statut trompeur "Analyse en cours...". Modification de `DealCard.jsx` pour afficher la justification rÃ©elle (`deal.aiAnalysis.reasoning`) ou une phrase de rejet par dÃ©faut.



[2026-02-24] [PRO] Action : CrÃ©ation d'un point central de mise Ã  jour `set_status` (avec `threading.Lock()`) activÃ© â†’ RÃ©sultat : RÃ©solution du bug "En attente" pendant le scan. Le statut `botStatus` repassait Ã  `idle` prÃ©maturÃ©ment quand des threads parallÃ¨les (comme le nettoyage en arriÃ¨re-plan) se terminaient pendant qu'un scan principal tournait. CrÃ©ation d'un point central de mise Ã  jour `set_status` dans `GuitarHunterBot` avec `threading.Lock()` et un suivi des tÃ¢ches actives par nom (`_active_tasks`). Le statut `idle` n'est confirmÃ© sur Firestore que si l'ensemble des processus sont terminÃ©s, avec prÃ©servation de la prioritÃ© du statut `scanning` sur `cleaning` pour l'interface UI.

[2026-02-24] [PRO] Action : Ajout d'un sondage Firestore pendant les pauses et rÃ©Ã©criture de `delete_all_logs` â†’ RÃ©sultat : RÃ©paration de deux bugs. (Bug 1) RÃ©veil du bot en pause : La boucle d'attente dans `main.py` ne sondait pas Firestore, rendant le bot sourd Ã  toute commande (REFRESH, SCAN_URL, etc.) sauf START_BOT. Correction : ajout d'un sondage Firestore toutes les 5s avec `bot.sync_and_apply_config()`. Toute commande actionnable interrompt maintenant la pause et est traitÃ©e immÃ©diatement aprÃ¨s le rÃ©veil. (Bug 2) Suppression des logs : RÃ©Ã©criture de `delete_all_logs` dans `repository.py` pour utiliser `list()` afin de forcer la consommation du stream Firestore avant chaque batch, ajout d'un garde-fou `max_iterations` et de logs de diagnostic amÃ©liorÃ©s.

[2026-02-24] [FLASH] Action : Identification d'un bug de rÃ©veil du bot â†’ RÃ©sultat : Ajout au `TODO.md` : le bot en pause (`paused`) ignore la commande `REFRESH` (Rescan All) mais rÃ©agit au `SCAN_URL`.

[2026-02-24] [PRO] Session 27 : Robustesse de la dÃ©tection d'indisponibilitÃ© du scraper (`check_listing_availability`). Passage d'une vÃ©rification textuelle stricte Ã  une analyse Regex (insensible Ã  la casse, mots entiers `\b`) incluant le franÃ§ais et l'anglais ("vendu", "sold", "expired"). Ajout de l'inspection des attributs ARIA et vÃ©rification stricte de la visibilitÃ© CSS (`display: none`, `opacity: 0`) vis `window.getComputedStyle` pour Ã©liminer les faux positifs (Ã©lÃ©ments cachÃ©s ou mots partiels comme "revendu").

[2026-02-24] [FLASH] Session 26 (Bug Report) : Identification d'un problÃ¨me de pÃ©rennitÃ© des images. Les URLs Facebook CDN expirent (paramÃ¨tre `oe` dans l'URL). Les annonces valides perdent leur visibilitÃ© visuelle aprÃ¨s quelques jours. Ajout au `TODO.md`.

[2026-02-24] [PRO] Session 26 : AmÃ©lioration du Pilotage du Bot (Commandes AvancÃ©es & UI). (Action 1) Ajout de la commande `STOP_SCAN` avec `scan_stop_event` indÃ©pendant pour interrompre un scraping sans tuer le bot. (Action 2) Refonte sÃ©mantique de `STOP_BOT` : le bot entre dans une boucle de pause de 12h (interruptible) au lieu de s'Ã©teindre totalement. (Action 3) Ajout de `START_BOT` pour rÃ©veiller le bot instantanÃ©ment de sa pause. (Action 4) Extraction et refonte de l'interface des contrÃ´les : crÃ©ation du composant `<BotControls />` hybride avec indicateur de statut dynamique intÃ©grÃ© dans le panneau latÃ©ral "SystÃ¨me".

[2026-02-24] [FLASH] Session 25 : Correction "Mode Hors Ligne" du Bot. Automatisation du dÃ©ploiement des fichiers ignorÃ©s par Git via GitHub Secrets (`DOT_ENV` et `FIREBASE_SERVICE_ACCOUNT_KEY`). Mise Ã  jour de `deploy.yml` pour recrÃ©er dynamiquement `.env` Ã  la racine et `serviceAccountKey.json` dans `backend/config/` sur le serveur.

[2026-02-24] [FLASH] Session 24 : Correction du flux de dÃ©ploiement GitHub Actions (`deploy.yml`). (Action 1) Correction de la casse de la branche `dev` (Ã©tait `Dev`). (Action 2) Remplacement de la rÃ©initialisation forcÃ©e sur `master` par une logique dynamique utilisant `${{ github.ref_name }}`. (Action 3) Ajout de logs dÃ©taillÃ©s et d'une gestion d'erreur robuste pour le redÃ©marrage du service `guitare-hunter`. (Action 4) Audit complet de la documentation (`docs/`).

[2026-02-24] [FLASH] Session 23 : Correction du rejet systÃ©matique des Ã©tuis/housses par le Portier et le Coupe-Circuit. (Action 1) Mise Ã  jour de `prompts.json` : retrait de la condition d'exclusion sur les "accessoires bas de gamme (gigbag fin seul)" dans `main_analysis_prompt` â€” Les amplis, Ã©tuis et housses (mÃªme simples) sont maintenant tous acceptÃ©s. Mise Ã  jour de `gatekeeper_verbosity_instruction` : retrait du rejet des "accessoires nuls", ajout explicite des guitares, amplis, Ã©tuis et housses comme objets acceptÃ©s. (Action 2) Standardisation des 3 instructions de verbositÃ© (`gatekeeper`, `analyst`, `expert_pro`) de `string` â†’ `array of strings` pour la compatibilitÃ© avec l'Ã©diteur ligne-par-ligne du ConfigPanel. Mise Ã  jour de `backend/analyzer.py` : ajout de `join("\n")` si l'instruction reÃ§ue est une liste.

[2026-02-24] [PRO] Session 22 : RÃ©solution du conflit de casse Git (`Dev` vs `dev`) empÃªchant le dÃ©ploiement sur `gh-pages`. Suppression de la branche `Dev` distante, nettoyage des rÃ©fÃ©rences locales, et succÃ¨s de `npm run deploy`. ExÃ©cution du workflow `/git-push-dev-master` pour synchroniser et achever la session.

[2026-02-24] [FLASH] Session 21 (suite) : Correctif TypeError prix int â†’ cast `str()` dans `analyzer.py` avant `extract_price_from_text`. CrÃ©ation de `backend/scripts/migrate_firestore_prompts.py` (audit racine + injection clÃ©s Tier2/3 + nettoyage obsolÃ¨tes, mode `--dry-run`). Ajout commande `STOP_BOT` : handler `threading.Event` dans `main.py`, `triggerStopBot()` dans `firestoreService.js`, bouton Power dans `LogViewer.jsx`.

[2026-02-24] [FLASH] Session 21 : ImplÃ©mentation du Funnel 3-Tiers + Refacto DRY â†’ `analyzer.py` restructurÃ© avec `_call_gemini_json` (mutualisation des appels API), prompt de base construit une seule fois. Cascade T1 (Flash-Lite) â†’ T2 (Flash, format compact + 5 scores) â†’ Carrefour Logique â†’ T3 (Pro, conditionnel). Seuils ajoutÃ©s dans `config.py`. Nouvelles instructions `analyst_verbosity_instruction` et `expert_pro_context_instruction` ajoutÃ©es dans `prompts.json` et init Firestore (`bot.py`). 4 rondes de vÃ©rification, 4 bugs corrigÃ©s. Push `dev`.

[2026-02-23] [FLASH] RÃ©flexion Statistiques â†’ Conceptualisation des KPIs basÃ©s sur les scores du Tier 2/3 et archivage dans `docs/STATS_REFLEXION.md`.

[2026-02-23] [FLASH] Action : Conception de l'entonnoir d'analyse Ã  3 niveaux et crÃ©ation de `docs/FUNNEL_PLAN.md` â†’ RÃ©sultat : StratÃ©gie validÃ©e pour rÃ©duire les coÃ»ts (Tier 2 compact) tout en augmentant la profondeur (Tier 3 Expert Pro conditionnel). Introduction de 5 scores numÃ©riques et d'une logique de dÃ©clenchement "Jackpot" (Marge + DÃ©fi).
[2026-02-23] [FLASH] Action : CrÃ©ation de `backend/scripts/fetch_deal.py` â†’ RÃ©sultat : Outil fonctionnel pour inspecter les annonces rÃ©elles dans la structure Firestore imbriquÃ©e (`artifacts/{app}/users/{user}/...`).
[2026-02-23] [FLASH] Action : Mise Ã  jour de `docs/ARCHITECTURE.md` â†’ RÃ©sultat : Documentation de la structure multi-tenant de la base de donnÃ©es.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` â†’ RÃ©sultat : Assainissement du titre de la notification (suppression des sauts de ligne `\n`) pour Ã©viter des erreurs HTTP `Invalid header value` lors de l'envoi Ã  `ntfy.sh`.
[2026-02-22] [PRO] Action : Modification de `src/App.jsx` â†’ RÃ©sultat : Le lecteur rÃ©cupÃ¨re dÃ©sormais l'ID d'annonce via le lien `deals` complet (et plus `filteredDeals`), Ã©vitant que la carte ne s'ouvre pas si l'annonce est archivÃ©e/filtrÃ©e.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` â†’ RÃ©sultat : Le lien cliquable des notifications `ntfy` renvoie dÃ©sormais vers la carte du deal sur le frontend (`?dealId=...`) au lieu de l'annonce Facebook FB.
[2026-02-23] [FLASH] Action : Audit final et synchronisation des branches â†’ RÃ©sultat : Documentation (Journal, Todo, Architecture, Data Flow) auditÃ©e et synchronisÃ©e. Fusion de la branche `dev` vers `master` et push remote.

Ce journal suit les changements majeurs, les dÃ©cisions d'architecture et les nouvelles fonctionnalitÃ©s.

---

---

### **Date: 23/02/2026** (Session 19)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Entonnoir v2)

#### ðŸ“� Description des Changements
- **Raffinage des dÃ©clencheurs Tier 3 (Expert Pro) :**
    - Couplage intelligent du prix et du score : le passage Ã  l'Expert Pro pour les objets > 1000$ ne se fait que si le `deal_score` est >= 4 (Ã©vite d'analyser en profondeur des objets chers mais inintÃ©ressants).
    - Durcissement des contrÃ´les d'authenticitÃ© : dÃ©clenchement systÃ©matique de l'Expert si `authenticity_score` <= 7.
    - Ajout d'un dÃ©clencheur spÃ©cifique pour les verdicts `COLLECTION`.
- **Mise Ã  jour de `docs/FUNNEL_PLAN.md` :** Documentation complÃ¨te de la logique de cascade.

#### ðŸ¤” Raisonnement
L'objectif est d'Ã©conomiser les appels au modÃ¨le Pro (plus coÃ»teux) en s'assurant qu'il n'intervient que sur des annonces ayant un rÃ©el potentiel ou prÃ©sentant un risque technique/historique nÃ©cessitant une haute prÃ©cision.

---

### **Date: 23/02/2026** (Session 18)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Scores & PÃ©dagogie)

#### ðŸ“� Description des Changements
- **Enrichissement du Tier 2 (Analyste) :**
    - Introduction d'un systÃ¨me de notation sur 10 pour 5 indices : `deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, et `restoration_interest_score`.
    - Ajout du `restoration_interest_score` : Ce score Ã©value la valeur "pÃ©dagogique" ou le dÃ©fi technique d'un projet de lutherie, permettant d'identifier des "PÃ©pites de restauration" mÃªme si la marge financiÃ¨re pure est moindre.
- **Logique "Jackpot" :** CrÃ©ation d'un dÃ©clencheur Expert Pro si `deal_score` >= 6 ET `restoration_interest_score` >= 7.

#### ðŸ¤” Raisonnement
Le projet "Guitar Hunter" n'est pas qu'une question de profit immÃ©diat, c'est aussi un projet luthier-centric. Valoriser l'intÃ©rÃªt technique des rÃ©parations permet de ne pas rater des instruments rares ou complexes qui enrichissent l'expertise du MaÃ®tre Luthier.

---

### **Date: 23/02/2026** (Session 17)

**Auteur:** Assistant AI

**Type:** Refonte SystÃ¨me (Commandes & Base de donnÃ©es)

#### ðŸ“� Description des Changements
- **Migration des "Legacy Commands" vers la collection `commands` :**
    - Modification du Frontend (`src/services/firestoreService.js`) pour que les actions manuelles (Refresh, Cleanup, Reanalyze All, Scan URL) crÃ©ent des documents dans la collection `commands` au lieu de modifier des champs d'horodatage sur la racine du document utilisateur.
    - Simplification du Backend (`backend/services.py` & `backend/bot.py`) : Le `ConfigManager` a Ã©tÃ© Ã©purÃ© de toute la logique complexe de vÃ©rification d'horodatage. La boucle principale (`main.py`) gÃ¨re dÃ©sormais de maniÃ¨re unifiÃ©e toutes les commandes entrantes (avec statut `pending`, `completed`, `failed`).
    - Nettoyage du Backend (`backend/repository.py`) : L'ancienne mÃ©thode `consume_command` qui supprimait les champs du document utilisateur a Ã©tÃ© supprimÃ©e suite Ã  la nouvelle architecture.

#### ðŸ¤” Raisonnement
Cette unification de l'architecture autour de la collection `commands` facilite grandement la traÃ§abilitÃ©. Auparavant, le bot devait surveiller 4 champs (`forceRefresh`, `forceCleanup`, `forceReanalyzeAll`, `scanSpecificUrl`) greffÃ©s sur le document utilisateur. Maintenant, chaque commande, quelle que soit sa nature, suit un flux de vie identique (crÃ©ation â†’ attente â†’ traitement â†’ terminÃ©/erreur), ce qui rend le systÃ¨me beaucoup plus robuste et prÃ©visible.

---

### **Date: 23/02/2026** (Session 16)

**Auteur:** Assistant AI

**Type:** Refonte SystÃ¨me (Scraping & Frontend)

#### ðŸ“� Description des Changements
- **Robustesse du Scraper Playwright :**
    - Modification de `check_listing_availability` dans `backend/scraping/core.py` pour utiliser l'Ã©valuation JavaScript native du DOM (`page.evaluate`). La dÃ©tection des marqueurs "Vendu", "Sold" ou "plus disponible" ne repose plus sur des cibles CSS volatiles, mais scanne les textes rendus et visibles du `div[role="main"]`.
    - Timeout de navigation augmentÃ© Ã  30 secondes pour compenser la lenteur applicative de Facebook sans dÃ©clencher de "faux positifs" de suppressions.
- **Sauvegarde de l'Historique (Soft Delete) :**
    - La fonction de nettoyage `cleanup_sold_listings` bascule exclusivement sur le taggage Firestore avec `status: 'sold'`, abandonnant le comportement `Hard Delete` non-dÃ©sirÃ©.
- **Transparence de l'UI Frontend (`DealCard.jsx` & Filtrage) :**
    - L'Ã©tat `sold` rÃ©duit dÃ©sormais l'opacitÃ© visuelle de l'annonce et applique un badge contextuel bloquant.
    - Correction du "FantÃ´me d'Analyse" : Les annonces liquidÃ©es avant qu'une IA ne rende un verdict (`DEFAULT`) ne tentent plus d'afficher "Analyse en cours..." mais explicitement "Non AnalysÃ© (Vendu)".
    - Correction du badge Compteur (`SOLD`) dans la barre de filtre pour comptabiliser les annonces vendues sans qu'elles ne soient exclues prÃ©maturÃ©ment par l'absence d'une classe d'instruments.

#### ðŸ¤” Raisonnement
Le cycle complet de vie d'une annonce doit garantir zÃ©ro perte de donnÃ©es. Les annonces vendues constituent une mine d'or pour Ã©valuer le "Velocity Pricing" d'un luthier ou d'un revendeur. En prÃ©servant ces documents Firestore de faÃ§on Ã©lÃ©gante, l'application mÃ»rit vers une plateforme d'analyse de marchÃ© long terme, et non plus un simple scanner Ã©phÃ©mÃ¨re.

---

### **Date: 22/02/2026** (Session 15 - Soir)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'Architecture & RÃ©solution de Dette Technique

#### ðŸ“� Description des Changements
- **Externalisation des verdicts de rejet (Coupe-circuit) :**
    - La liste des verdicts provoquant l'arrÃªt immÃ©diat de l'analyse (`BAD_DEAL`, `REJECTED_ITEM`...) a Ã©tÃ© retirÃ©e du code Python (`backend/analyzer.py`).
    - Elle est dÃ©sormais stockÃ©e dans `prompts.json` par dÃ©faut et gÃ©rÃ©e dynamiquement via Firestore (`analysisConfig.rejectionVerdicts`).
    - Ajout d'une interface d'Ã©dition (liste de textes) dans `ConfigPanel.jsx` (section "Intelligence Artificielle").

#### ðŸ¤” Raisonnement
Cette modification rÃ©sout une dette technique identifiÃ©e. Auparavant, si la taxonomie des verdicts venait Ã  Ã©voluer, le backend devait Ãªtre recompilÃ©. Maintenant, l'utilisateur a un contrÃ´le total sur les conditions de "coupe-circuit" directement depuis l'interface web, rendant le systÃ¨me de filtrage (Portier) 100% pilotÃ© par les donnÃ©es.

---

### **Date: 22/02/2026** (Session 15 - AprÃ¨s-midi)

**Auteur:** Assistant AI

**Type:** Nettoyage & Organisation du Projet

#### ðŸ“� Description des Changements
- **DÃ©pollution de la racine :** Suppression des scripts de diagnostic et de setup obsolÃ¨tes (`diagnose_firestore.py`, `populate_cities.py`, `test_notification.py`, `verify_setup.py`) et de l'ancien journal (`implementation_journal.md`).
- **Restructuration des fichiers de configuration :**
    - CrÃ©ation de `backend/resources/` et dÃ©placement de `city_coordinates.json`.
    - CrÃ©ation de `firebase/` et dÃ©placement de `firestore.rules`.
    - CrÃ©ation de `backend/config/` et dÃ©placement de `serviceAccountKey.json`.
- **Mise Ã  jour des rÃ©fÃ©rences :** Correction des chemins d'accÃ¨s dans `config.py` (backend), `src/components/MapView.jsx` (frontend) et `tests/check_baseline.py`.

#### ðŸ¤” Raisonnement
Une racine propre facilite la navigation dans le projet et sÃ©pare clairement les fichiers de configuration, les ressources de donnÃ©es et le code source. La mise Ã  jour des imports garantit que les deux environnements (Python et React) continuent de fonctionner sans interruption.

---

### **Date: 22/02/2026** (Session 15 - Matin)

**Auteur:** Assistant AI

**Type:** Analyse Technique & Audit de DonnÃ©es

#### ðŸ“� Description des Changements
- **Audit de la base de donnÃ©es (Le mystÃ¨re des annonces invisibles) :**
    - **ProblÃ¨me :** L'utilisateur a remarquÃ© un Ã©cart de ~300 annonces entre le total Firestore (486) et les annonces visibles (84 + 91).
    - **Investigation :** CrÃ©ation de scripts d'audit (`inspect_db_stats.py`, `inspect_rejection_reasons.py`) pour analyser les documents `status: 'rejected'`.
    - **DÃ©couverte :** 287 annonces portent le verdict `REJECTED` (ancienne nomenclature v1). 20 proviennent du prÃ©-filtre Javascript, le reste (267) provient des modÃ¨les Gemini (anciennes analyses).
    - **Cause de l'invisibilitÃ© :** Le frontend (`matchesVerdictFilter`) masque totalement les documents ayant un statut global `rejected`. Dans la nomenclature v2, le "bruit" est classÃ© `REJECTED_ITEM` avec un statut global `analyzed`, ce qui les rend comptabilisable dans l'UI alors que la v1 les annihilait visuellement.
- **Analyse du systÃ¨me de nettoyage (Sold Listings) :**
    - Documentation du fonctionnement de `cleanup_sold_listings`. Identification de la fragilitÃ© de la dÃ©tection (basÃ©e sur du texte strict) et du risque de perte d'historique dÃ» au "Hard Delete".

#### ðŸ¤” Raisonnement
Il est crucial de conserver l'historique des ventes pour de futures statistiques (Price History / Velocity). Le passage au "Soft Delete" est validÃ© comme prochaine Ã©tape majeure.

---

### **Date: 20/02/2026** (Session 14 - Suite 2)

**Auteur:** Assistant AI

**Type:** Correction de Bug (Frontend / Firestore)

#### ðŸ“� Description des Changements
- **Fix Bug #3 â€” Le bouton "Reset" corrompait Firestore :**
    - **ProblÃ¨me :** Bien que la sauvegarde champ par champ ait Ã©tÃ© corrigÃ©e hier (utilisation de la notation par point `updateDoc` avec `analysisConfig.mainAnalysisPrompt`), la fonction `handleResetDefaults` envoyait encore l'objet imbriquÃ© entier `{ analysisConfig: { ... } }`. Cela entraÃ®nait un fallback de `firestoreService` sur l'ancienne mÃ©thode `setDoc` qui Ã©crasait silencieusement la racine du document.
    - **Solution :** Refonte de `handleResetDefaults` dans `useBotConfig.js` pour construire un objet plat utilisant la notation par point avant de l'envoyer Ã  `updateUserConfig`. La rÃ©initialisation utilise dÃ©sormais la mÃªme mÃ©thode d'Ã©criture chirurgicale que les sauvegardes manuelles.

#### ðŸ¤” Raisonnement
Cette asymÃ©trie entre la sauvegarde ligne-par-ligne et la rÃ©initialisation globale Ã©tait un reste de l'ancienne architecture. Maintenant, toutes les opÃ©rations de mise Ã  jour utilisent systÃ©matiquement la notation par point de Firestore pour garantir l'intÃ©gritÃ© des autres donnÃ©es du document.

---

### **Date: 20/02/2026** (Session 14 - Suite)

**Auteur:** Assistant AI

**Type:** Nettoyage de Dette Technique

#### ðŸ“� Description des Changements
- **Suppression du code mort :** Le fichier `backend/prompt_manager.py`, qui contenait l'ancienne architecture de prompts Ã  5 blocs inutilisÃ©e, a Ã©tÃ© retirÃ© du projet (via `git rm`).
- **Nettoyage des configurations obsolÃ¨tes :** Les anciennes clÃ©s (`persona`, `verdict_rules`, `system_structure`, etc.) ont Ã©tÃ© supprimÃ©es de `prompts.json` et de `config.py` pour allÃ©ger le code et Ã©viter toute confusion future.

#### ðŸ¤” Raisonnement
Le projet Ã©volue avec succÃ¨s vers un systÃ¨me d'analyse IA en cascade et paramÃ©trable. Supprimer le code inactif (le vieux `PromptManager` monolithique) et nettoyer les rÃ©sidus dans les configurations garantit que l'architecture reste claire et facile Ã  comprendre pour les futures itÃ©rations.

---

### **Date: 20/02/2026** (Session 14)

**Auteur:** Assistant AI

**Type:** Audit Complet du Projet (Full Stack)

#### ðŸ“� Description des Changements

1.  **Analyse globale des flux de donnÃ©es et de l'architecture :**
    - RÃ©alisation d'un audit de bas en haut (Scrapers -> Core Logic -> IA -> Base de donnÃ©es -> Frontend).
    - Mise Ã  jour de `docs/TODO.md` avec de nouvelles prioritÃ©s de pointe (dette technique cachÃ©e).
    - Mise Ã  jour de `docs/ARCHITECTURE.MD` pour reflÃ©ter la situation rÃ©elle des flux de commandes.

2.  **Identifications ClÃ©s (Dette Technique ajoutÃ©e au TODO) :**
    - **Architecture de Commandes Hybride :** Le backend Ã©coute Ã  la fois des champs horodatÃ©s sur `users/{id}` (legacy) et des documents dans la collection `commands` (nouveau). Cela crÃ©e une complexitÃ© inutile.
    - **Logique de Rejet HardcodÃ©e :** Le composant `DealAnalyzer` filtre les annonces en lisant en dur une liste de "verdicts de rejet" (`BAD_DEAL`, `REJECTED_ITEM`, etc.). Si la taxonomie en frontend/prompts Ã©volue, le backend devient aveugle sans mise Ã  jour du code source.
    - **FragilitÃ© du Scraper :** La dÃ©tection d'une annonce vendue sur Playwright se fie Ã  une expression exacte ("Cette annonce nâ€™est plus disponible"), ce qui est trÃ¨s cassable.

#### ðŸ¤” Raisonnement

- Il est vital de de temps Ã  autre "dÃ©zoomer" de la rÃ©solution de bugs isolÃ©s pour analyser les tendances de l'architecture. Ces dÃ©couvertes empÃªchent qu'un simple changement de configuration (ex: renommage d'un statut dans l'UI) ne fasse tomber tout le backend silencieusement.

---
### **Date: 20/02/2026** (Session 13)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de la Configuration / PrÃ©paration au DÃ©ploiement

#### ðŸ“� Description des Changements

1.  **Uniformisation de la gestion des IDs dans le Frontend :**
    - **ProblÃ¨me :** Les constantes `PYTHON_USER_ID` et `APP_ID` Ã©taient codÃ©es en dur dans `src/services/firestoreService.js`, crÃ©ant une redondance avec les variables d'environnement dÃ©jÃ  prÃ©sentes dans `.env` et configurÃ©es dans `vite.config.js`.
    - **Solution :** Remplacement des valeurs en dur par `process.env.USER_ID_TARGET` et `process.env.APP_ID_TARGET`.
    - **BÃ©nÃ©fice :** La configuration est dÃ©sormais centralisÃ©e dans le fichier `.env`, facilitant le dÃ©ploiement et la maintenance.

#### ðŸ¤” Raisonnement

- Le passage aux variables d'environnement est une bonne pratique indispensable avant un dÃ©ploiement, assurant que le code reste agnostique de l'environnement et que les identifiants clÃ©s peuvent Ãªtre gÃ©rÃ©s de maniÃ¨re sÃ©curisÃ©e et centralisÃ©e.

---

### **Date: 20/02/2026** (Session 12)

**Auteur:** Assistant AI

**Type:** Correction de Bugs (PrioritÃ© Haute)

#### ðŸ“� Description des Changements

1.  **Fix Bug #1 â€” Classifications "Autre" (Frontend + Backend) :**
    - **ProblÃ¨me :** L'IA inventait des libellÃ©s libres (ex: "Fender Stratocaster") qui ne correspondaient pas exactement aux clÃ©s de la taxonomie (ex: "Stratocaster"). La fonction `normalize` ne permettait pas de trouver ces classifications.
    - **Solution :**
        - Rendu l'instruction de classification plus stricte dans `prompts.json` (demande la valeur exacte d'une feuille de la taxonomie).
        - Ajout d'une fonction `findPathFuzzy` dans `useDealsManager.js` pour tolÃ©rer les variations (recherche par sous-chaÃ®ne normalisÃ©e).

2.  **Fix Bug #2 â€” Compteurs de filtres incorrects (Frontend) :**
    - **ProblÃ¨me :** La boucle de comptage dans `useDealsManager.js` n'incrÃ©mentait que les 3 premiers niveaux (`path[0]`, `path[1]`, `path[2]`). Sur une taxonomie Ã  4 niveaux, la feuille finale n'Ã©tait jamais comptÃ©e, affichant des badges erronÃ©s.
    - **Solution :** Remplacement des affectations dures par une boucle `path.forEach(segment => ...)` pour incrÃ©menter dynamiquement tous les niveaux du chemin de la taxonomie.

#### ðŸ¤” Raisonnement

- Ces deux bugs impactaient fortement l'expÃ©rience utilisateur (mauvais comptage, difficultÃ© Ã  filtrer les guitares). En durcissant le backend (prompt) tout en assouplissant le frontend (fuzzy match), on maximise les chances que la classification fonctionne mÃªme sur les anciennes annonces.

---

### **Date: 20/02/2026** (Session 11)

**Auteur:** Assistant AI

**Type:** Correction de Bug Critique (Frontend / Firestore)

#### ðŸ“� Description des Changements

1.  **Correction du bug de corruption silencieuse de `analysisConfig` dans Firestore :**
    - **ProblÃ¨me :** La fonction `updateUserConfig` dans `firestoreService.js` utilisait systÃ©matiquement `setDoc` avec `merge: true`. Ce comportement merge uniquement au niveau racine du document Firestore. Passer un objet `{ analysisConfig: { mainAnalysisPrompt: [...] } }` **remplaÃ§ait intÃ©gralement** le sous-objet `analysisConfig`, effaÃ§ant silencieusement `gatekeeperModel`, `expertModel`, `gatekeeperVerbosityInstruction` et `expertContextInstruction`.
    - **Impact :** Chaque `onBlur` sur un `PromptListEditor` corrompait Firestore. La corruption causait Ã©galement une race condition qui annulait le Reset.
    - **Solution :** `updateUserConfig` dÃ©tecte maintenant si les clÃ©s passÃ©es contiennent une notation par points (ex: `'analysisConfig.mainAnalysisPrompt'`) :
        - **Dot-notation** â†’ `updateDoc` : Ã©criture chirurgicale sur le champ exact, sans toucher les champs frÃ¨res.
        - **Objet complet** (ex: Reset) â†’ `setDoc` + `merge: true` : comportement inchangÃ© pour les resets complets.
    - **Fichiers modifiÃ©s :** `src/services/firestoreService.js`

#### ðŸ¤” Raisonnement

- `updateDoc` de Firestore accepte nativement la notation par points pour cibler des sous-champs prÃ©cis. C'est l'outil prÃ©vu pour ce cas d'usage. Le code utilisait dÃ©jÃ  `unflatten` pour "deviner" l'intention, mais ce n'est pas suffisant car `setDoc + merge` ne merge pas en profondeur.

---

### **Date: 20/02/2026** (Session 10)

**Auteur:** Assistant AI

**Type:** Audit de Documentation & Analyse Approfondie

#### ðŸ“� Description des Changements

1.  **Audit complet du systÃ¨me de prompts :**
    - Analyse exhaustive de tous les fichiers impliquÃ©s dans le pipeline de prompts, du backend (`config.py`, `analyzer.py`, `services.py`) au frontend (`useBotConfig.js`, `firestoreService.js`, `ConfigPanel.jsx`).
    - Identification et documentation du code mort : la classe `PromptManager` dans `backend/prompt_manager.py` est un orphelin non instanciÃ©, vestige d'une ancienne architecture "5 blocs". Les clÃ©s `persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`, `system_structure` dans `prompts.json` et leurs constantes associÃ©es dans `config.py` sont obsolÃ¨tes.
    - Validation du format de `prompts.json` : syntaxiquement valide.

2.  **Mise Ã  jour de `docs/ARCHITECTURE.md` (Section 4 â€” SystÃ¨me de Prompts) :**
    - Remplacement de la description gÃ©nÃ©rale par une analyse technique dÃ©taillÃ©e avec inventaire des fichiers, diagrammes de flux de donnÃ©es rÃ©els (Backend + Frontend), tableau des prompts modifiables par l'utilisateur, documentation du mÃ©canisme de fallback, et inventaire de la dette technique.

#### ðŸ¤” Raisonnement

- La documentation prÃ©cÃ©dente donnait une vue d'ensemble correcte mais imprÃ©cise. L'ajout du tableau de fichiers avec leur statut (actif/orphelin) et des diagrammes de flux en texte brut offre une rÃ©fÃ©rence fiable pour les futurs dÃ©veloppements, notamment pour le nettoyage du code mort.

---

### **Date: 23/02/2026** (Session 9)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Ajustement de la largeur de l'image sur mobile:**
    - **ProblÃ¨me:** La largeur de l'image sur mobile (`w-32`) Ã©tait trop Ã©troite.
    - **Solution:** La largeur du conteneur de l'image est passÃ©e Ã  `w-1/2` (50% de la largeur de la carte), offrant un meilleur Ã©quilibre visuel avec le bloc de prix qui occupe les 50% restants.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Cet ajustement rÃ©pond Ã  la demande de donner plus d'importance Ã  l'image sur mobile, tout en conservant une disposition en deux colonnes compacte.

---

### **Date: 23/02/2026** (Session 8)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Refonte de la structure de la `DealCard` (Mobile First):**
    - **ProblÃ¨me:** La disposition prÃ©cÃ©dente ne satisfaisait pas les besoins spÃ©cifiques de l'affichage mobile (image complÃ¨te, compacitÃ©) et desktop (hiÃ©rarchie claire).
    - **Solution:** Une approche "Mobile First" avec deux structures distinctes a Ã©tÃ© implÃ©mentÃ©e :
        - **Mobile (`md:hidden`):** Un en-tÃªte compact affiche l'image (largeur fixe `w-32`) et le bloc de prix cÃ´te Ã  cÃ´te. Le titre et les dÃ©tails suivent en dessous.
        - **Desktop (`hidden md:block`):** La disposition classique en deux colonnes est conservÃ©e, avec l'image "sticky" Ã  gauche. Dans la colonne de droite, le bloc de prix est positionnÃ© au-dessus du titre pour une meilleure hiÃ©rarchie.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

2.  **CrÃ©ation du composant `PriceDisplay`:**
    - **Action:** La logique d'affichage du prix et du menu dÃ©roulant financier a Ã©tÃ© extraite dans un sous-composant `PriceDisplay`. Cela permet de l'utiliser Ã  deux endroits diffÃ©rents dans le code (header mobile et colonne desktop) sans dupliquer la logique complexe.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

3.  **Retour Ã  l'affichage complet des images:**
    - **Action:** Annulation du changement `object-cover` dans `ImageGallery.jsx`. Les images sont de nouveau affichÃ©es en entier (`object-contain`) pour ne perdre aucun dÃ©tail de l'instrument.

#### ðŸ¤” Raisonnement

- Cette solution hybride offre le meilleur des deux mondes : une expÃ©rience mobile optimisÃ©e pour la densitÃ© d'information et une expÃ©rience desktop riche et structurÃ©e. L'extraction du composant `PriceDisplay` maintient le code propre et maintenable malgrÃ© la duplication structurelle.

---

### **Date: 23/02/2026** (Session 6)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Uniformisation de l'affichage du bloc prix:**
    - **ProblÃ¨me:** Le bloc de prix pouvait encore dÃ©passer de la carte sur certains Ã©crans d'ordinateur lorsque le titre Ã©tait long et que l'affichage Ã©tait en mode "ligne" (cÃ´te Ã  cÃ´te).
    - **Solution:** L'affichage a Ã©tÃ© uniformisÃ© pour Ãªtre identique sur mobile et desktop. Le bloc de prix est dÃ©sormais **toujours** positionnÃ© en dessous du titre et alignÃ© Ã  gauche. Cela garantit qu'il dispose toujours de toute la largeur nÃ©cessaire et Ã©limine tout risque de dÃ©passement.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- La cohÃ©rence de l'interface est primordiale. En adoptant une disposition verticale unique, on simplifie la maintenance et on s'assure que le contenu critique (le prix et les dÃ©tails financiers) est toujours lisible, quelle que soit la contrainte d'espace horizontal.

---

### **Date: 23/02/2026** (Session 5)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Ajustement de la taille du bouton de prix:**
    - **ProblÃ¨me:** Le bouton de prix, bien que fonctionnel, pouvait Ãªtre rendu plus compact pour un meilleur Ã©quilibre visuel.
    - **Solution:** Plusieurs micro-ajustements ont Ã©tÃ© effectuÃ©s : rÃ©duction du `padding`, de la taille de la police, de la taille de l'icÃ´ne, de l'espacement interne et du rayon de la bordure.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Ce changement est un raffinement stylistique visant Ã  perfectionner l'Ã©quilibre et l'harmonie des composants de l'interface.

---

### **Date: 23/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Fusion du Bouton de Prix et du Toggle d'Expansion:**
    - **ProblÃ¨me:** Le bouton affichant le prix et le bouton pour dÃ©plier les dÃ©tails financiers Ã©taient deux Ã©lÃ©ments sÃ©parÃ©s, ce qui Ã©tait moins intuitif et prenait plus de place.
    - **Solution:** Les deux Ã©lÃ©ments ont Ã©tÃ© fusionnÃ©s en un seul composant interactif. Le bouton de prix contient maintenant le montant et l'icÃ´ne "chevron". L'ensemble du bloc est cliquable pour afficher/masquer les dÃ©tails financiers.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Cette modification amÃ©liore l'expÃ©rience utilisateur en crÃ©ant un point d'interaction unique et clair, ce qui est un standard de design d'interface.
- Elle permet Ã©galement un gain d'espace marginal mais apprÃ©ciable sur les petits Ã©crans.

---

### **Date: 24/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** Correction de bugs (PrioritÃ© Haute)

#### ðŸ“� Description des Changements

1.  **Correction de la commande `STOP_BOT` (Backend):**
    - **ProblÃ¨me:** La commande `STOP_BOT` via l'interface UI (ou Firestore) passait le statut du bot Ã  `stopped` mais le programme Python continuait son scan ou nettoyage en cours (boucles synchrones Playwright/Firebase longues).
    - **Solution:** J'ai passÃ© l'instance `threading.Event()` (`stop_event`) depuis `main.py` jusque dans `GuitarHunterBot` (`bot.py`) et `FacebookScraper` (`core.py`). Des vÃ©rifications `if self.stop_event.is_set(): return/break` ont Ã©tÃ© ajoutÃ©es dans les points stratÃ©giques des boucles de dÃ©filement (`page.mouse.wheel`), d'analyse d'annonces, de nettoyage des vendues (`cleanup_sold_listings`) et des rÃ©analyses en attente.
    - **Fichiers modifiÃ©s:** `main.py`, `backend/bot.py`, `backend/scraping/core.py`.

2.  **Correction de la suppression des logs cÃ´tÃ© client (Frontend):**
    - **ProblÃ¨me:** Le bouton "Vider la base de donnÃ©es" du `LogViewer.jsx` ne produisait aucun effet. Les logs Ã©coutÃ©s correspondaient Ã  un "userIdTarget" et un "appId" codÃ©s en dur (`00737242777130596039`, `c_5d118e71...`). 
    - **Solution:** Standardisation via des variables d'environnement. Ajout de `VITE_APP_ID_TARGET` et `VITE_USER_ID_TARGET` dans `.env` cÃ´tÃ© React, de faÃ§on Ã  ce que le `LogViewer` se base dynamiquement sur la mÃªme configuration ciblÃ©e que le Backend Python et Firebase.
    - **Fichiers modifiÃ©s:** `src/components/LogViewer.jsx`, `.env`.

#### ðŸ¤” Raisonnement

- **Stop Bot rÃ©actif :** Pour que "l'arrÃªt d'urgence" fonctionne, il fallait sortir le code d'une simple vÃ©rification entre deux cycles du scheduler (ancienne mÃ©thode) et propager un kill-switch asynchrone jusque dans les boucles de scraping internes. L'objet `threading.Event()` est parfait pour Ã§a, agissant comme un drapeau partagÃ© et thread-safe.
- **Dette Technique (Logs) :** Le code frontend pour les logs Ã©tait restÃ© sur un ancien jet de POC oÃ¹ je dÃ©veloppais avec mes propres IDs personnels (Session 1 Ã  5). La standardisation avec `.env` aligne le `LogViewer` sur le reste de l'application.

---

### **Date: 23/02/2026** (Session 3)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Refonte du Menu de RÃ©analyse:**
    - **ProblÃ¨me:** Le menu de rÃ©analyse (Standard/Expert) Ã©tait "dÃ©tachÃ©" de la carte lors du dÃ©filement (scroll) car il utilisait un `Portal`. De plus, il Ã©tait trop volumineux avec du texte inutile.
    - **Solution:**
        - **Ancrage:** Le menu est maintenant rendu directement dans le DOM de la carte, positionnÃ© en absolu par rapport au bouton de rÃ©analyse. Il suit donc parfaitement le dÃ©filelement de la page.
        - **Design Compact:** Le texte a Ã©tÃ© supprimÃ© au profit d'icÃ´nes (`RefreshCw` et `BrainCircuit`) avec des info-bulles (`title`). Le menu est beaucoup plus discret et s'intÃ¨gre mieux Ã  l'interface.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- L'utilisation de `Portal` pour des menus contextuels liÃ©s Ã  des Ã©lÃ©ments scrollables est souvent problÃ©matique sans une gestion complexe de la position. L'ancrage direct via CSS (`position: absolute`) est une solution plus robuste et plus simple ici.
- La rÃ©duction de la taille du menu amÃ©liore l'expÃ©rience utilisateur, en particulier sur mobile oÃ¹ l'espace est limitÃ©.

---

### **Date: 23/02/2026** (Session 2)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration du Design Responsive (UI/UX)

#### ðŸ“� Description des Changements

1.  **AmÃ©lioration de l'affichage de la `DealCard` sur mobile:**
    - **ProblÃ¨me:** Sur les Ã©crans de petite taille, le bloc contenant les informations financiÃ¨res (`Prix`, `Valeur EstimÃ©e`, etc.) ne passait pas Ã  la ligne et dÃ©bordait de la carte, rendant l'interface inutilisable.
    - **Solution:** La structure de l'en-tÃªte de la carte a Ã©tÃ© rendue "responsive" :
        - Sur les Ã©crans `md` et plus, le titre et le bloc financier sont cÃ´te Ã  cÃ´te.
        - Sur les petits Ã©crans (mobile), le bloc financier passe automatiquement sous le titre, utilisant toute la largeur disponible et Ã©vitant tout dÃ©passement.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

2.  **Simplification de l'affichage du prix:**
    - **ProblÃ¨me:** Pour gagner de la place sur mobile, l'affichage du prix pouvait Ãªtre plus compact.
    - **Solution:**
        - La mention "Prix DemandÃ©" a Ã©tÃ© supprimÃ©e.
        - La taille de la police du prix a Ã©tÃ© rÃ©duite (`text-xl` au lieu de `text-2xl`).
        - Le padding du conteneur du prix a Ã©tÃ© ajustÃ©.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Ces changements sont cruciaux pour l'utilisabilitÃ© de l'application sur des appareils mobiles. Ils suivent les principes du "responsive design" en adaptant la disposition du contenu Ã  la taille de l'Ã©cran.
- La simplification du prix contribue Ã  une interface plus Ã©purÃ©e et directe.

---

### **Date: 23/02/2026** (Session 1)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX) & Correction de bug

#### ðŸ“� Description des Changements

1.  **Refonte du Module Financier sur la `DealCard`:**
    - **ProblÃ¨me:** Les indicateurs financiers clÃ©s (`estimated_value`, `net_guitar_cost`, etc.) Ã©taient cachÃ©s sous des conditions trop restrictives (ex: uniquement si la marge Ã©tait positive ou si l'annonce n'Ã©tait pas rejetÃ©e).
    - **Solution:** Un nouveau module financier a Ã©tÃ© implÃ©mentÃ© :
        - **Toujours visible:** Le prix demandÃ©, la valeur estimÃ©e et le potentiel de revente sont maintenant toujours visibles si les donnÃ©es existent, mÃªme pour les annonces rejetÃ©es.
        - **DÃ©tails sur demande:** Un menu dÃ©roulant (toggle) a Ã©tÃ© ajoutÃ© pour afficher les dÃ©tails techniques comme le **CoÃ»t Net** et la **Marge Brute**.
        - **Code couleur:** La marge brute est maintenant colorÃ©e (vert si positive, rouge si nÃ©gative) pour une identification rapide de la rentabilitÃ©.
    - **Fichier modifiÃ©:** `src/components/DealCard.jsx`

2.  **Correction du Bug de RÃ©analyse "Expert":**
    - **ProblÃ¨me:** Lors d'un clic sur le bouton de rÃ©analyse "Expert", l'indicateur de chargement (spinner) ne s'activait pas car le statut `analyzing_expert` n'Ã©tait pas correctement gÃ©rÃ© par le frontend.
    - **Solution:** Le statut `analyzing_expert` a Ã©tÃ© ajoutÃ© aux listes de vÃ©rification `isAnalyzing` et `getModelName` dans la `DealCard`.
    - **Fichier modifiÃ©:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- La refonte du module financier a pour but de fournir Ã  l'utilisateur un contexte complet sur **pourquoi** une annonce est jugÃ©e bonne ou mauvaise, mÃªme aprÃ¨s qu'elle ait Ã©tÃ© rejetÃ©e.
- La correction du bug de rÃ©analyse amÃ©liore le retour visuel pour l'utilisateur, confirmant que son action a bien Ã©tÃ© prise en compte.

---

### Session 20 : Expansion du Scope - Ã‰tape 1 (Amps & Ã‰tuis)

#### âœ… Objectif : Passer d'un systÃ¨me "Tout-Guitare"- [x] Bugfix: Taxonomy Count Collision (hierarchical paths).
  - [x] Round 1: Code Audit (Path normalization & aggregation).
  - [x] Round 2: Data Mapping Verification (Multi-parent nodes).
  - [x] Round 3: UI/Filter Interaction Sync.
- **Nouveaux Produits** : IntÃ©gration des `amplificateurs` (Lampes, Transistors, ModÃ©lisation) et des `accessoires_etuis` (Rigides, Housses souples).
- **Persona Luthier** : Mise Ã  jour des prompts pour Ã©valuer les amplis (Ã©tat des lampes, transformateurs) et valoriser l'apport financier des housses/Ã©tuis pour le flipping.
- **Synchronisation Full-Stack** : Mise Ã  jour de `config.py` et `useDealsManager.js` pour supporter dynamiquement la nouvelle structure.

#### ðŸ¤” Raisonnement

- L'expansion permet de capturer des opportunitÃ©s de "Fast Flip" (ex: Boss Katana) et de maximiser la valeur des packs guitare+Ã©tui.
- Le maintien du persona **MaÃ®tre Luthier** assure une analyse technique rigoureuse, mÃªme sur des objets non-luthier classiques comme les amplis numÃ©riques.

---

[2026-02-26] [FLASH] Action effectuÃ©e â†’ Migration complÃ¨te vers l'UI V2, suppression de l'obsolescence V1 et validation du build de production.

### Session 36 : Activation DÃ©finitive de la V2 & Nettoyage V1

#### âœ… Objectif : Remplacer l'ancienne UI par la nouvelle interface SaaS V2.

- **Standardisation des Composants** : Renommage massif des composants `Mockup*` en noms de production (`Dashboard`, `Navbar`, `DealCard`, `FilterDrawer`, `StatsView`).
- **Simplification de `App.jsx`** : Suppression de toute la logique de bascule V1/V2. L'application monte dÃ©sormais directement le `Dashboard` V2.
- **Suppression de la Dette Technique** : Ã‰limination des fichiers V1 obsolÃ¨tes (`FilterBar.jsx`, `SectionGroup.jsx`, `DealModal.jsx`, `BotControls.jsx`, `DebugStatus.jsx`).
- **Validation** : Build Vite (`npm run build`) validÃ© avec succÃ¨s (0 erreur d'import).

#### ðŸ¤” Raisonnement

- La V2 est jugÃ©e supÃ©rieure en termes d'ergonomie (Filtres en tiroir, Stats intÃ©grÃ©es, Map Split-screen) et d'esthÃ©tique (Dark Mode).
- Supprimer les fichiers obsolÃ¨tes Ã©vite toute confusion future et allÃ¨ge le bundle final.
- La transition "Production Ready" marque la fin de la phase de prototypage de la nouvelle interface.

---

[2026-02-26] [FLASH] Action effectuÃ©e â†’ Polissage UI : Verrouillage du scroll global et correction du clipping dans la Navbar.

### Session 39 : Polissage de l'ExpÃ©rience Utilisateur

#### âœ… Objectif : Supprimer les artefacts visuels rÃ©siduels pour une expÃ©rience "Produit" parfaite.

- **DÃ©sactivation du Scroll Corps** : Ajout de `overflow: hidden` sur `html, body, #root` dans `index.css` pour forcer l'utilisation des conteneurs internes et supprimer la barre de dÃ©filement du navigateur.
- **Correction du Menu Statut** : Retrait de `overflow-x-hidden` sur la `Navbar` pour permettre au menu de survol (status controls) de s'afficher sans Ãªtre tronquÃ©.
- **Z-Index & Layers** : VÃ©rification de la superposition des Ã©lÃ©ments interactifs pour un rendu "floating" optimal.

#### ðŸ¤” Raisonnement

- Le Dashboard V2 est conÃ§u pour Ãªtre une interface fixe (SPA). La prÃ©sence d'une scrollbar native sur le cÃ´tÃ© droit nuisait Ã  l'aspect premium et cassait l'alignement visuel.
- La Navbar doit Ãªtre capable de dÃ©border (overflow visible) pour ses menus contextuels, tout en restant `sticky`.

---

[2026-02-26] [FLASH] Action effectuÃ©e â†’ Bugfix ConfigPanel : Suppression d'un double `return` et de blocs syntaxiques redondants bloquant le build Vite.

### Session 40 : Correction Syntaxique Critique

- **Correction `ExclusionKeywordsSection`** : Suppression du code dupliquÃ© par erreur lors du prÃ©cÃ©dent push. Le composant `ConfigPanel.jsx` est dÃ©sormais syntaxiquement correct.
- **VÃ©rification** : Le build Vite ne doit plus lever l'erreur `The character "}" is not valid inside a JSX element`.

---

---

[2026-03-09] [FLASH] Action effectuÃ©e â†’ Migration vers Tailscale OAuth pour le dÃ©ploiement (CI/CD) et correction du pÃ©rimÃ¨tre des secrets.

### Session 48 : IntÃ©gration Tailscale OAuth (CI/CD)

#### âœ… Objectif : SÃ©curiser la connexion SSH du GitHub Runner via Tailscale OAuth.

- **DevOps (`deploy.yml`)** : Utilisation des secrets `TS_OAUTH_CLIENT_ID` et `TS_OAUTH_SECRET` pour rejoindre le Tailnet lors du dÃ©ploiement.
- **Documentation** : Mise Ã  jour de `ARCHITECTURE.md` pour clarifier que ces secrets concernent le pipeline de dÃ©ploiement et non l'application.
- **Correction** : Retrait des variables OAuth de `config.py` et de l'injection dans le `.env` du serveur (pÃ©rimÃ¨tre CI/CD uniquement).

#### ðŸ¤” Raisonnement

- Les identifiants OAuth Tailscale sont nÃ©cessaires au GitHub Runner pour accÃ©der au serveur privÃ©. L'application (bot) n'en a pas besoin pour son fonctionnement interne. SÃ©parer les deux types de secrets amÃ©liore la clartÃ© et la sÃ©curitÃ©.

---

---

[2026-07-19] [FLASH] Action effectuée -> Ajout des images dans l'index des annonces et refonte UX de la Google Map.

### Session : Optimisation MapView et Index Firestore

#### 1. Objectif : Afficher les images et les informations complètes sur les popups de la carte
- **Backend (
epository.py, 
ebuild_index.py)** : Modification de la signature de _update_deal_index pour inclure l'URL de l'image (stockée sous la clé i). Refactorisation du script de reconstruction de l'index avec une requête paginée (limit(500).offset(...)) pour éviter les timeouts gRPC et les fuites de mémoire.
- **Frontend (useDealsManager.js)** : Mapping de la nouvelle propriété dealData.i vers storageImageUrls lors de la récupération de l'index.
- **Frontend (MapView.jsx)** :
  - Restauration du design compact d'origine très apprécié (plus lisible, sans débordement).
  - Suppression du padding par défaut de Google Maps sur .gm-style-iw-d.
  - Suppression complète du bouton de fermeture (croix) via CSS (.gm-ui-hover-effect { display: none !important; }).
  - Ajout d'une fermeture automatique au survol sortant (onmouseleave="window.closeMapPopup()").
  - Suppression de la disparition de la carte lors du clic sur une annonce.

#### 2. Raisonnement
La carte interactive n'affichait plus les images des annonces car la structure de l'index Firebase (deals_index) n'incluait pas l'URL des images. En ajoutant cette information compressée, le chargement reste très rapide tout en offrant un rendu visuel.
La refonte de la popup MapView a été itérative pour finalement revenir à une ergonomie épurée (hover sur le marqueur, fermeture naturelle en quittant la zone, clic pour ouvrir les détails).

---

---

[2026-07-26] [PRO] Action effectuée -> Création du scraper Kijiji autonome (module non branché au pipeline) + corrections de code review.

### Session : Mise en place du scraping Kijiji

#### 1. Objectif : Poser l'architecture d'un scraper Kijiji, en préparation d'une future prise en charge multi-plateforme (Facebook + Kijiji)
- **Backend (`backend/scraping/kijiji/`, nouveau)** : `KijijiScraper`, `KijijiListingParser`, `KijijiScraperConfig` — calqués sur `FacebookScraper`, même forme de `listing_data` en sortie (+ `source: "kijiji"`) pour faciliter une intégration future dans `bot.py::run_scan()`. Recherche via le champ de recherche du site (pas d'équivalent `city_mapping`/ID de lieu numérique Kijiji à ce stade). Extraction de la fiche détail en 2 temps : JSON-LD en priorité (standard schema.org, plus stable qu'un sélecteur CSS), repli DOM sinon. `scan_specific_url()` (test isolé d'une annonce) et `check_listing_availability()` fournis en miroir de l'API Facebook.
- **Tests** : `test_kijiji_core.py`, 19 tests unitaires (extraction d'ID, validation de fiche détail, parsing JSON-LD, garde-fou constructeur).
- **Corrections post-review** (`/code-review`) : bug d'extraction d'ID (premier segment numérique au lieu du dernier), validation de fiche détail par sous-chaîne au lieu d'exact match, ambiguïté prix 0$/introuvable (flag `price_found`), gestion des variantes JSON-LD en tableau (`@type`/`image`/`offers`), garde manquante sur le champ de recherche, sélection de suggestion pour le filtre de lieu, `try/except` manquant après soumission de recherche, `.count()` au lieu de `.all()` dans la boucle de scroll, ajout de `check_listing_availability`, constructeur passé en keyword-only pour éviter un futur appel positionnel erroné copié depuis `FacebookScraper`.

#### 2. Raisonnement
Le protocole du projet a été suivi (plan validé avant code). L'utilisateur a choisi l'option "scraper autonome d'abord, testable seul" plutôt qu'une intégration complète immédiate dans `bot.py`.
**Point d'attention** : cet environnement de développement n'a pas d'accès réseau à `kijiji.ca` (bloqué par la politique d'egress de la session, confirmé via le proxy) — les sélecteurs CSS/`data-testid` et le parcours de recherche n'ont donc pas pu être vérifiés contre le DOM réel du site. Une validation manuelle sur kijiji.ca reste nécessaire avant toute intégration au pipeline de production.

---

---

[2026-07-27] [PRO] Action effectuée -> Validation live du scraper Kijiji (Longueuil, Toronto) + résolution de lieu pancanadienne + corrections de robustesse.

### Session : Tests live du scraper Kijiji et résolution de lieu

#### 1. Objectif : Valider le scraper Kijiji contre le vrai site (impossible depuis l'environnement de dev) et corriger ce qui casse en conditions réelles
- **Découverte clé (`__NEXT_DATA__`)** : kijiji.ca (Next.js/Apollo) intègre l'état SSR complet de chaque annonce dans `<script id="__NEXT_DATA__">` — title/description/price/location (nom + coordonnées GPS)/imageUrls exacts, aussi bien sur une fiche détail individuelle QUE sur une page de résultats de recherche (tous les `StandardListing` affichés y sont, avec une seule URL d'image en aperçu par annonce). `backend/scraping/kijiji/parser.py::parse_details_page()`/`extract_all_standard_listings()` l'utilisent désormais en priorité, avant JSON-LD et le repli DOM — bien plus fiable que n'importe quel sélecteur CSS.
- **`backend/scraping/kijiji/core.py::_scrape_results_page()`** : essaie `__NEXT_DATA__` en premier (`_scrape_from_next_data`, pas de scroll/sélecteur DOM nécessaire pour les métadonnées de carte), repli sur l'ancien défilement + sélecteurs `data-testid` (`_scrape_from_dom`) si absent.
- **Bugs corrigés en test live** : sélecteur d'annonces `a[href^='/v-']` (préfixe) qui ne matchait jamais car les liens Kijiji sont des URLs absolues → `a[href*='/v-']` (contient), comme pour Facebook. Localisation manquante (`Lieu: None`) malgré JSON-LD/DOM → résolue par `__NEXT_DATA__` (repli additionnel `extract_location_slug()` sur l'URL en dernier recours). Vrai sélecteur du champ de recherche (`input#global-header-search-bar-input`) trouvé par diagnostic live, remplaçant les sélecteurs devinés qui ne matchaient rien. Timeouts `networkidle` réduits de 60s à 15s (Kijiji charge des pubs/trackers en continu, l'attente échouait systématiquement en 60s pour rien). Un timeout de fiche détail sur une seule annonce ne fait plus échouer tout le scan (try/except manquant autour de `goto()`, découvert sur une annonce de Toronto — repli sur les infos de carte/recherche, `_fallback_details()` factorisé).
- **`scan_search_url(url, max_ads)`** (nouveau) : scrape directement une URL de résultats déjà construite, sans passer par le champ de recherche/la modale de lieu (dont le sélecteur n'a pas pu être identifié — aucun input de lieu visible sur la page d'accueil).
- **`backend/scraping/kijiji/locations.py`** (nouveau) : résolution ville → ID de lieu Kijiji. Kijiji publie un arbre statique et complet de tous ses lieux, pour tout le Canada, en un seul appel (`https://www.kijiji.ca/j-locations.json`) — l'hypothèse initiale que le paramètre `q=` filtrait par province s'est révélée fausse (vérifié par diagnostic comparatif puis confirmé décisivement : l'ID de Toronto est présent dans la réponse peu importe `q=`). `backend/scripts/fetch_kijiji_locations.py` télécharge et aplatit cet arbre en lookup `{nom_normalisé: {id, slug}}` sauvegardé dans `backend/resources/kijiji_locations.json` (165 villes, 192 clés générées). `KijijiScraper.scan_city(city_name, category_id, query, ...)` combine résolution + construction d'URL (`build_search_url`) + `scan_search_url()`.
- **Validé en live** : une annonce isolée (Longueuil, `scan_specific_url`), une recherche complète par URL directe (Longueuil, 5/5 annonces trouvées avec prix/images corrects), et `scan_city` sur une ville hors Québec (Toronto, catégorie Guitars, prix/images/description corrects) — confirmant que la résolution pancanadienne et la construction d'URL fonctionnent au-delà du Québec.
- **⚠️ Imprécision constatée sur `location` pour les annonces "hors ville exacte"** : sur le test de recherche Longueuil, une annonce physiquement à Sainte-Julie (visible comme telle sur la page HTML brute) est ressortie avec `location: "Longueuil / South Shore"` (le nom de la RÉGION Kijiji élargie couverte par la recherche, pas la ville précise de l'annonce) — `__NEXT_DATA__.location.name` reflète apparemment la région de recherche assignée à l'annonce, pas nécessairement la ville exacte affichée visuellement sur la page (qui semble dérivée séparément, ex: de `location.address` ou de la distance). Non corrigé ni creusé plus loin cette session — les tests unitaires "multi-villes" (Sainte-Julie/Québec, commit `4db9f21`) utilisent des échantillons construits à la main supposant `location.name` = ville précise, hypothèse **non vérifiée** contre un vrai payload d'annonce en périphérie d'une recherche. À vérifier avant de se fier à `location` pour un affichage utilisateur précis.
- **Tests** : 49 tests unitaires dans `backend/scraping/kijiji/` (extraction titre/prix/lieu, parsing `__NEXT_DATA__`, résolution de lieu, construction d'URL), tous basés sur des extraits de réponses réelles capturées en test live (à l'exception de l'hypothèse "multi-villes" ci-dessus).

#### 2. Raisonnement
Le réseau vers `kijiji.ca` restant bloqué dans cet environnement de développement, toute la validation s'est faite via l'utilisateur exécutant `backend/scripts/test_kijiji_scraper.py` (et ses flags `--diag-*`) en local et collant les résultats. Plusieurs hypothèses de conception se sont révélées fausses à l'usage (sélecteurs devinés, filtrage par province) — corrigées au fur et à mesure plutôt que supposées correctes après coup. Le scraper reste **non branché** à `bot.py::run_scan()` (scope volontairement limité à un module autonome et testable) — reste à décider : mapping de catégories au-delà de 613 (Guitars), config Firestore dédiée, fusion ou séparation des annonces Facebook/Kijiji.

---

---

[2026-07-27] [PRO] Action effectuée -> `nearest_configured_city` (tri GPS) + corrections de `/code-review` (locations.py, core.py) sur le module Kijiji.

### Session : Résolution de ville par GPS + correctifs de code review

#### 1. Objectif : Répondre à l'imprécision documentée de `location.name` et corriger les findings remontés par `/code-review`
- **`backend/scraping/kijiji/locations.py::nearest_configured_city(latitude, longitude, city_coordinates, max_radius_km=None)`** (nouveau) : calcule la distance Haversine (réutilise `scraping.utils.calculate_distance`, déjà utilisé côté Facebook) de l'annonce vers chaque ville configurée (même format que `city_coordinates.json`) et retourne la plus proche — les coordonnées GPS de l'annonce, contrairement à `location.name`, sont toujours présentes et fiables. `max_radius_km` optionnel pour ne pas rattacher une annonce trop lointaine à une ville non pertinente. **Pas encore branché au pipeline de scan** (en attendant que la forme du futur `scan_config` Kijiji soit tranchée) — utilitaire disponible, appel à faire depuis le futur code d'intégration `bot.py`.
- **Corrections post-`/code-review`** :
  - `nearest_configured_city` : une entrée `city_coordinates` avec des `lat`/`lng` non numériques faisait planter `math.radians()` dans `calculate_distance()`, qui capture l'exception et retourne 0 — cette entrée "gagnait" alors silencieusement comme ville la plus proche. Ajout de `_is_number()` (exclut aussi `bool`, sous-classe d'`int`) validant explicitement les coordonnées d'entrée ET celles de chaque ville avant de les utiliser. Type hint `max_radius_km` corrigé (`float = None` → `Optional[float] = None`).
  - `resolve_location()` : le repli par correspondance partielle pouvait matcher plusieurs lieux différents et retournait le premier trouvé selon l'ordre d'itération du dict — silencieux, non déterministe. Déduplication par `id` : un seul lieu distinct → résolu normalement ; plusieurs → ambigu, retourne `None` avec un `warning` loggé plutôt que de deviner. Accepte désormais un `log` optionnel (repli sur le logger de module) ; `core.py::scan_city()` y passe `self.logger`.
  - `core.py` : la visite de fiche détail (`goto` + repli sur erreur), dupliquée quasi à l'identique dans `_scrape_from_next_data` et `_scrape_from_dom`, extraite dans une méthode partagée `_visit_detail_page()`.
  - `.gitattributes` (nouveau) : `docs/management/JOURNAL.md` fixé en `eol=lf`. Un des findings signalait que `JOURNAL.md` avait été réécrit en CRLF via un script Bash lors d'une session précédente, en violation de la consigne d'éditer la doc uniquement via les outils directs. Investigation : Edit/Write ne peuvent produire que du LF dans cet environnement (confirmé empiriquement) — préserver le CRLF historique du fichier sans passer par un script terminal est donc impossible avec les outils autorisés. Plutôt que de perpétuer l'instabilité (reconversion partielle à chaque édition, ou script CRLF ponctuel à chaque session), LF est fixé comme convention officielle pour ce fichier allant de l'avant. Contenu textuel non affecté (vérifié octet à octet hors fins de ligne).
- **Tests** : 6 tests de régression ajoutés (`backend/scraping/kijiji/test_locations.py`) — coordonnées non numériques (chaîne, booléen) n'emportant plus faussement la résolution, résolution ambiguë (plusieurs lieux distincts) vs non ambiguë (plusieurs clés vers un même id). 65 tests au total dans le module Kijiji, tous verts.

#### 2. Raisonnement
`nearest_configured_city` est un utilitaire pur (pas d'accès réseau/DOM), donc pleinement testable dans cet environnement malgré l'absence d'accès à `kijiji.ca`. Les correctifs de code review touchent tous à des cas limites silencieux (donnée malformée "gagnant" par défaut, ambiguïté résolue au hasard) plutôt qu'à des bugs déjà observés en usage réel — traités avant intégration au pipeline plutôt qu'après.

---

---

[2026-07-27] [PRO] Action effectuée -> Merge de `dev` dans la branche Kijiji (résolution de conflit + bug de signature corrigé) + validation live du scan Kijiji intégré + clarification des logs + icône du bouton "voir l'annonce d'origine".

### Session : Merge `dev`, validation live, lisibilité des logs et icône Kijiji

#### 1. Objectif : Rattraper le retard pris par la branche Kijiji sur `dev` (LeBonCoin, corrections diverses) avant de valider le scan Kijiji en conditions réelles, puis lever les points de friction remontés par l'utilisateur pendant cette validation
- **Merge `origin/dev` → branche Kijiji** : un seul conflit réel, dans `bot.py::run_scan()` — la branche Kijiji avait remplacé la boucle séquentielle par ville par `_run_sources_in_parallel()` (threads Facebook/Kijiji), pendant que `dev` avait enrichi cette même boucle séquentielle d'une comptabilisation de cycle (`cycle_stats`) et d'un filtrage "autre ville autorisée" plus fin. Résolu en gardant l'architecture parallèle et en portant les apports de `dev` (stats de cycle, villes bloquées par anti-bot, logique à 3 voies du filtre STRICT) dans `_run_facebook_scan()`.
- **Bug de merge non conflictuel découvert et corrigé** : `dev` avait aussi changé la signature de retour de `FacebookScraper.scan_marketplace()` (dict `{deals, anti_bot_blocked, rejected_out_of_list, total_cards_seen}` au lieu d'une simple liste) dans un fichier qui a fusionné sans marqueur de conflit — `_run_facebook_scan()` (code propre à la branche Kijiji, absent de `dev`) continuait de traiter le retour comme une liste brute et aurait planté au premier scan. Détecté en retraçant manuellement tous les appelants de `scan_marketplace()` après le merge, pas par Git. Corrigé avant tout commit ; 76 tests (`backend/test_bot.py`, `scraping/test_core.py`, `scraping/kijiji/test_*.py`) verts après coup.
- **Validation live confirmée par l'utilisateur** : le scan Kijiji intégré au pipeline (`_run_kijiji_scan()`, déjà présent dans l'historique de la branche avant cette session — commits `edbe8a4`/`7e0797a`, jamais documentés) fonctionne de bout en bout en conditions réelles. Doc mise à jour en conséquence (`ARCHITECTURE.md`, `TODO.md` : la mention "non branché au pipeline" était obsolète).
- **Lisibilité des logs (`bot.py`)** : Facebook et Kijiji tournant désormais en parallèle et écrivant dans le même logger, leurs lignes s'entremêlaient dans le LogViewer sans indication d'origine — `handle_deal_found()` prend un paramètre `source` (`"Facebook"` par défaut, pour ne pas casser `scan_specific_url()`) et préfixe tous ses logs (`[Facebook]`/`[Kijiji]`). `_run_kijiji_scan()` reçoit un `cycle_stats` + un résumé de fin de cycle (`📊 Résumé du cycle Kijiji : ...`), symétrique à celui déjà présent côté Facebook.
- **Icône du bouton "voir l'annonce d'origine" (`DealCardActions.jsx`)** : affichait toujours l'icône/couleur Facebook, y compris pour une annonce Kijiji. Détection `isKijiji` via `deal.link.includes('kijiji.ca')` (même logique que le badge source de `DealCard/index.jsx`, `deal.source` n'existant que pour Kijiji) ; badge orange "K" + tooltip "Voir sur Kijiji" à la place de l'icône Facebook bleue quand pertinent.

#### 2. Raisonnement
Un merge avec conflit apparent (un seul marqueur dans `bot.py`) peut masquer des changements de signature dans des fichiers fusionnés sans friction — la seule façon fiable de les détecter est de retracer manuellement chaque appelant des fonctions modifiées par l'autre branche plutôt que de faire confiance à l'absence de marqueur `<<<<<<<`. Les logs de deux sources parallèles partageant un seul logger utilisateur (contrainte du `FirestoreHandler`, voir plus haut) doivent systématiquement s'auto-identifier plutôt que de compter sur l'ordre d'affichage (déjà documenté comme non fiable) pour distinguer leur origine.

---

---

[2026-07-27] [PRO] Action effectuée -> Diagnostic d'un signalement utilisateur (prix Kijiji périmé) → filtre de prix/rayon côté recherche pour Kijiji + comportement hors-budget uniforme Facebook/Kijiji + bug `_apply_filters()` corrigé.

### Session : Root cause d'un prix Kijiji "faux" + refonte du pré-filtre de prix

#### 1. Objectif : Investiguer un signalement utilisateur (une annonce Kijiji affichée à 280$ dans l'app, "Trop Cher" avec un plafond à 200$, alors que Kijiji.ca affichait 250$) puis répondre à la demande produit qui en a découlé
- **Diagnostic du signalement** : réseau vers `kijiji.ca` bloqué dans cet environnement (`WebFetch` → 403), diagnostic fait via l'utilisateur (HTML brut de la page Kijiji, puis `test_kijiji_scraper.py --search-url` en local). Le prix extrait (`__NEXT_DATA__` → `amount: 25000 / 100 = 250$`) était **correct** — pas de bug d'extraction. Le 280$ affiché dans l'app était une donnée périmée : le bot avait scrapé l'annonce avant une baisse de prix par le vendeur, jamais revisitée depuis. Même à 250$, l'annonce restait au-dessus du plafond de 200$ — le vrai désaccord n'était donc pas la valeur du prix, mais le fait qu'une annonce hors budget soit stockée/affichée comme `BAD_DEAL` du tout.
- **Décision produit (itérée sur plusieurs tours)** : une annonce hors budget "ne fait pas partie de la recherche" — elle ne doit être ni stockée, ni analysée, quelle que soit la source (refus explicite d'un traitement Kijiji-only ou d'une nouvelle vérification de prix dupliquée dans `_run_kijiji_scan()`, au profit de la réutilisation du calcul déjà présent dans `handle_deal_found()`).
- **`backend/bot.py::handle_deal_found()`** : la branche `price_too_high` ne stocke plus rien (ni `create_new_deal`, ni `update_deal_data_and_analysis`) — `return "out_of_budget"` directement, pour Facebook **et** Kijiji. `_create_price_rejection_analysis()` (verdict `BAD_DEAL` par pré-filtre) supprimée — `BAD_DEAL` reste un verdict IA légitime (`prompts.json`), simplement plus jamais produit par ce raccourci. Le mot-clé exclu (`found_keyword`) garde son comportement (`REJECTED`, stocké) — non concerné.
- **Filtre de prix/rayon côté recherche pour Kijiji (2026-07-27, validé en live)** : jusqu'ici, contrairement à Facebook (`minPrice`/`maxPrice` dans l'URL), Kijiji ne filtrait rien à la recherche — tout était fetché (fiche détail visitée) puis rejeté après coup. L'utilisateur a fourni une URL Kijiji réelle avec `price=100__250` — confirmant que Kijiji supporte un filtre de prix par URL, jusque-là non exploité. `locations.py::build_search_url()` accepte désormais `min_price`/`max_price` (`?price=min__max`, un bord vide si absent) et `lat`/`lng`/`radius_km` (`&ll=lat,lng&radius=...`, même mécanisme que la géolocalisation forcée Facebook), câblés depuis `bot.py::_run_kijiji_scan()`. Rayon plafonné à **1km minimum** (jamais 0) — sur demande explicite, le sélecteur de rayon du site Kijiji n'autorisant pas 0km (contrairement à `distance=0` côté Facebook, qui signifie "correspondance exacte de ville", concept inexistant côté Kijiji).
- **Validation live** : `test_kijiji_scraper.py --search-url` avec `price=100__250&ll=45.5385193,-73.3556313&radius=6` → 5/5 annonces retournées entre 100$ et 250$, toutes à proximité de la coordonnée donnée (Longueuil/Saint-Bruno/Sainte-Julie).
- **Bug trouvé et corrigé en vérifiant la source du problème côté Facebook** : `scraping/core.py::_apply_filters()` remplissait et **soumettait** le champ "Prix maximum" même à `max_price == 0` (pas de plafond configuré), sans le garde-fou `if max_price > 0:` déjà présent côté prix min — un scan sans plafond aurait pu appliquer un filtre Facebook `maxPrice=0` invalide. Restructuré : soumission (`Enter` + attente de rechargement) faite une seule fois à la fin, seulement si au moins un des deux champs a été rempli (sinon un plafond min seul, sans max, ne se soumettait plus du tout — régression introduite puis corrigée dans le même passage).
- **Tests** : 76 tests (`backend/test_bot.py`, `scraping/test_core.py`, `scraping/kijiji/test_*.py`) toujours verts après les changements.

#### 2. Raisonnement
Un signalement utilisateur "le prix est faux" n'impliquait pas forcément un bug de parsing — remonter jusqu'à la donnée source (page Kijiji réelle vs résultat du scraper sur la même URL) a permis de distinguer une extraction correcte d'une donnée simplement obsolète, plutôt que de corriger un chemin d'extraction qui n'était pas le coupable. La demande produit qui a suivi ("hors budget = pas traité, point") a explicitement guidé vers la réutilisation du calcul de prix déjà centralisé dans `handle_deal_found()` plutôt qu'une nouvelle vérification dupliquée dans le chemin Kijiji — la duplication de logique métier entre les deux sources scraper (déjà visible dans `_run_facebook_scan()`/`_run_kijiji_scan()`) est un point de friction récurrent de cette session, à garder en tête pour une éventuelle factorisation future.

---

---

[2026-07-27] [PRO] Action effectuée -> Détecte les doublons cross-plateforme (Facebook/Kijiji) avant l'analyse IA (commit `d890393`, jamais documenté) → Résultat : plus de double appel Gemini sur une même annonce postée sur les deux sites.

### Session : Détection de doublon cross-plateforme

#### 1. Objectif : Éviter de repayer le pipeline IA (3-Tiers Gemini) sur une même annonce postée à la fois sur Facebook et Kijiji, désormais scannés en parallèle
- **`backend/bot.py::_find_cross_platform_duplicate(listing_data, source)`** (nouveau) : compare prix normalisé (`_normalize_price`), ville normalisée (`ListingParser.normalize_city_name`) et similarité de titre (Jaccard sur tokens ASCII sans accents, `_title_tokens`, seuil `CROSS_PLATFORM_TITLE_SIMILARITY_THRESHOLD=0.6`) contre chaque entrée de `repo.get_deals_index_snapshot()`, en ignorant les entrées de la **même** source (préfixe `kijiji_` de l'ID) — un doublon même-source est déjà couvert par `should_skip_deal()` (comparaison par ID exact). Retourne l'ID du doublon trouvé, ou `None`.
- **`backend/repository.py::get_deals_index_snapshot()`** (nouveau) : fusionne les 20 chunks de l'index léger `deals_index` en un seul dict `{deal_id: {champs...}}`, sans lire les documents complets de `guitar_deals` — réutilise l'infrastructure de sharding déjà en place pour le Frontend (`DATA_FLOW.md` § 5) pour une recherche transverse côté backend.
- **`handle_deal_found()`** : appel en tout début de fonction (avant tout appel IA), après le garde-fou "scraping raté" mais avant l'upsert Firestore. Court-circuité pour un scan manuel (`is_manual_scan=True`) — l'utilisateur demande explicitement l'analyse de cette URL précise, pas question de la sauter au prétexte qu'elle ressemble à une annonce déjà connue. Retourne `"duplicate_cross_platform"` (nouveau code de statut, sans écriture Firestore) si un doublon est trouvé.

#### 2. Raisonnement
Cette entrée documente un changement déjà commité (`d890393`) par une autre session avant cette passe de documentation — même angle mort que celui déjà rencontré pour `_run_kijiji_scan()` (commits `edbe8a4`/`7e0797a`, voir plus haut) : du code fonctionnel peut atterrir sur la branche sans jamais transiter par l'étape 3 du protocole `CLAUDE.md`. Consigné ici pour que `ARCHITECTURE.md`/`TODO.md` reflètent l'état réel du code plutôt que l'état du dernier commit documenté.

---

---

[2026-07-27] [PRO] Action effectuée -> `scan_city()` Kijiji ancré Canada entier + `address`/`ll`/`radius` pour toute ville, plus dépendant de la résolution par nom → Résultat : validé en live, chaque ville du catalogue obtient désormais une recherche Kijiji précise.

### Session : Recherche Kijiji indépendante de la résolution de sous-zone par nom

#### 1. Objectif : Répondre à une limitation découverte en creusant "pourquoi ne pas toujours configurer le champ adresse par défaut" — beaucoup de petites municipalités du catalogue n'ont aucune sous-zone Kijiji qui leur soit propre
- **Constat** : `kijiji_locations.json` (~192 entrées) recense de larges sous-régions (ex: "Longueuil / South Shore" couvre aussi Saint-Bruno, Sainte-Julie, etc.), pas une ville par entrée — ni coordonnées GPS ni niveau intermédiaire province/région dans ce lookup (vérifié : "Québec"/"Greater Montréal" absents en tant que clés, seules les feuilles de l'arbre ont été aplaties par `fetch_kijiji_locations.py`). `resolve_location()` échouait donc silencieusement pour la plupart des petites villes configurées, et `scan_city()` retournait `[]` sans lancer de recherche.
- **`backend/scraping/kijiji/locations.py::build_search_url()`** : nouveau paramètre `address` (encodé via `urllib.parse.quote`), envoyé **uniquement avec** `ll=`/`radius=` — jamais seul, faute de preuve que `ll=`/`radius=` suffisent sans `address=` (les deux URLs testées en live avaient toujours les trois ensemble).
- **`backend/scraping/kijiji/core.py::scan_city()`** : n'appelle plus `resolve_location()`. Ancre désormais toujours l'URL sur `location_id=0` (Canada, toujours valide) + `address=<ville>`/`ll=`/`radius=` — chaque ville du catalogue obtient une vraie recherche Kijiji précise, qu'elle ait ou non sa propre sous-zone nommée.
- **`backend/scripts/test_kijiji_scraper.py`** : `--scan-city` gagne `--lat`/`--lng`/`--radius-km`/`--min-price`/`--max-price` pour rester utilisable en diagnostic (`scan_city()` ne fonctionne plus "gratuitement" sans coordonnées).
- **Test obsolète remplacé** : l'ancien test (`TestScanCity::test_returns_empty_list_when_city_not_found`) vérifiait qu'une ville inconnue retournait `[]` sans lancer de session Playwright — comportement qui n'existe plus par design. Remplacé par un test vérifiant la construction de l'URL (`k0c613l0` + `address=`/`ll=`/`radius=`) via `unittest.mock.patch.object(scraper, "scan_search_url")` plutôt qu'un vrai lancement de navigateur.
- **Validation live (Saint-Bruno-de-Montarville, aucune sous-zone Kijiji propre)** : `--scan-city "Saint-Bruno-de-Montarville" --lat 45.5298901 --lng -73.3453766 --radius-km 2` → 3/3 annonces trouvées, toutes correctement ciblées sur cette ville précise (l'étiquette "Longueuil / South Shore" affichée sur les annonces est juste la région assignée par Kijiji à l'annonce elle-même, pas un signe d'échec du filtre géographique).
- **Tests** : 76 tests (`backend/test_bot.py`, `scraping/test_core.py`, `scraping/kijiji/test_*.py`) verts après les changements.

#### 2. Raisonnement
La question de l'utilisateur ("pourquoi ne pas toujours configurer `address` par défaut") a fait ressortir que la distinction "résolution réussie vs repli" envisagée initialement n'apportait aucun bénéfice démontré (aucune preuve qu'une sous-zone déjà ciblée améliore la pertinence des résultats une fois `address`/`ll`/`radius` présents) pour un coût réel (deux chemins de code à maintenir) — simplifié vers un chemin unique, uniforme pour toutes les villes. Deuxième question de l'utilisateur ("je ne comprends pas pourquoi `address=` devient redondant") a corrigé une affirmation non vérifiée avancée dans le plan initial (que `ll=`/`radius=` suffiraient seuls) — les trois paramètres sont maintenus ensemble par prudence, faute de test live isolant leur nécessité individuelle.

⚠️ **Correctif du 2026-07-27 (entrée suivante) : le test "positif" ci-dessus sur Saint-Bruno n'a pas validé ce que je croyais.** `location_id=0` s'est révélé cassé en usage réel — voir plus bas.

---

---

[2026-07-27] [PRO] Action effectuée -> Correctif : `location_id=0` (Canada) confirmé cassé en production (annonce réelle, Brossard) → repli sur le point d'ancrage résolvable le plus proche.

### Session : `location_id=0` invalide un ciblage géographique — correctif par point d'ancrage GPS

#### 1. Objectif : Corriger un signalement utilisateur — une annonce Kijiji réelle scannée en production pour "Brossard" (`location_id=0` + `address=Brossard`) est retombée sur "No results for guitare in Canada" ("Brossard n'est pas dans les filtres"), alors que la même recherche faite manuellement sur le site (ancrée sur `l1700279`, Longueuil/South Shore) fonctionne
- **Diagnostic** : deux hypothèses possibles pour expliquer l'échec — (1) `location_id=0` ignore `address`/`ll`/`radius`, ou (2) `address=Brossard` seul (sans province) échoue à se géocoder à l'échelle du pays. Un test isolant la seconde hypothèse (même URL, `address=Brossard%2C%20QC`, toujours `l0`) a échoué de la même façon ("pas mieux") — confirme l'hypothèse (1) : **`location_id=0` ignore silencieusement `address`/`ll`/`radius`, indépendamment du format de `address`.** Le test "positif" de la session précédente sur Saint-Bruno-de-Montarville (entrée ci-dessus) n'a donc probablement pas validé le vrai mécanisme — coïncidence plausible (tri par défaut/géolocalisation IP de l'environnement de test, déjà proche de Montréal).
- **`backend/scraping/kijiji/locations.py`** : `load_city_coordinates()` (charge `city_coordinates.json`, même convention que `load_location_lookup()`) ; `build_resolvable_hubs(lookup, city_coordinates, log=None)` (précalcule, parmi les ~839 municipalités du catalogue, celles qui résolvent réellement vers un lieu Kijiji — ~24 sur 839, à calculer une seule fois, coûteux à refaire par ville) ; `nearest_resolvable_hub(latitude, longitude, resolvable_hubs, log=None)` (trouve le point d'ancrage résolvable le plus proche par distance Haversine). `_HUB_CANDIDATE_EXCLUSIONS = {"richmond"}` : collision confirmée en vérification directe — "richmond" (QC, Estrie) résout réellement vers l'ID Kijiji de Richmond, BC (même famille de piège que documentée dans `resolve_location()` pour Waterloo/Abbotsford/Stoke/Oka, mais celle-ci vérifiée réelle contre les données live plutôt qu'hypothétique).
- **`backend/scraping/kijiji/core.py::scan_city()`** : essaie `resolve_location(city_name)` d'abord (sous-zone propre) ; à défaut, `nearest_resolvable_hub(lat, lng, self.resolvable_hubs)` (repli, précalculé une fois dans `__init__`). `address`/`ll`/`radius` restent construits sur la ville réelle (Brossard), seul l'ID d'ancrage du chemin d'URL change (celui de Longueuil/South Shore, 1700279 — identique à la sélection manuelle de l'utilisateur via l'UI Kijiji pour la même ville). Si aucun ancrage n'est trouvé (pas de lat/lng, ou aucun candidat proche), la ville est ignorée (`[]`) plutôt que de lancer une recherche Canada entière non ciblée — plus sûr maintenant que `l0` seul est confirmé inefficace pour le ciblage géographique.
- **Tests** : ancien test `TestScanCity` (qui affirmait `k0c613l0` comme comportement voulu) réécrit en 3 cas — sous-zone propre résolue directement, repli sur le point d'ancrage le plus proche (Brossard → Longueuil), aucun ancrage trouvé → `[]`. Nouveaux tests dédiés pour `build_resolvable_hubs()`/`nearest_resolvable_hub()` (`test_locations.py`) : filtrage des candidats non résolvables, exclusion de "richmond", coordonnées malformées, ville la plus proche, cas limites (lat/lng absents, aucun hub). 84 tests au total, tous verts.

#### 2. Raisonnement
Un signalement de production sur une annonce réelle a invalidé une hypothèse que je pensais déjà validée en live (Saint-Bruno) — le test précédent avait la bonne conclusion apparente (résultats pertinents) pour la mauvaise raison probable (coïncidence de géolocalisation, pas le mécanisme `address`/`ll`/`radius` réellement testé). Là où un test isolé (une seule ville, un seul environnement) peut sembler concluant, il ne prouve le mécanisme que s'il exclut les explications alternatives plausibles — ici, le tri par défaut d'une recherche Kijiji Canada-entière depuis un environnement dont l'IP géolocalise probablement déjà près de Montréal aurait produit un résultat presque identique, indépendamment de tout ciblage explicite. Lesson : préférer un test qui isole spécifiquement la variable en cause (ex: une ville délibérément loin de la géolocalisation probable de l'environnement de test) avant de documenter un mécanisme comme "validé en live".

---

---

[2026-07-27] [PRO] Action effectuée -> Rayon de recherche Kijiji : défaut à deux paliers (proxy sans nouvelle donnée) + réglage par ville (Firestore/UI) → Résultat : plus de plancher fixe 1km inadapté aux petites/grandes villes.

### Session : Rayon Kijiji adaptatif — défaut à deux paliers + réglage par ville

#### 1. Objectif : Répondre à un point soulevé par l'utilisateur juste après le correctif précédent — le plancher fixe de 1km (hérité de `scanConfig.distance`) est insuffisant pour une petite ville (Sainte-Julie, ~4km nécessaires) et bien pire pour une grande (Montréal), et un seul rayon fixe ne peut satisfaire les deux extrêmes sans donnée de taille/population par ville (qu'on n'a pas)
- **Défaut à deux paliers (`backend/scraping/kijiji/core.py`)** : réutilise un signal déjà disponible gratuitement plutôt que d'acquérir une nouvelle donnée — `KijijiScraper.DEFAULT_RADIUS_KM_RESOLVED=15` (ville résolue directement via `resolve_location()`, sa propre sous-zone Kijiji nommée, en pratique toujours assez grande pour ça) vs `DEFAULT_RADIUS_KM_HUB_FALLBACK=5` (ville via `nearest_resolvable_hub()`, petite municipalité satellite par construction). Appliqué dans `scan_city()` uniquement quand `radius_km` n'est pas fourni (`None`/`<= 0`) — proxy imparfait (Longueuil résolu directement n'est pas Montréal) mais accepté comme tel.
- **Réglage par ville (complément, pas remplacement)** : nouveau champ Firestore optionnel `kijijiRadiusKm` sur les préférences user des villes (`users/{uid}/cities/{cityId}`, même document qu'`isScannable`) — `firestoreService.js::setCityKijijiRadius()` (écriture directe côté client, même pattern que `toggleCityScannable()`), `useCities.js::handleSetCityKijijiRadius`, `ConfigPanel.jsx::CityManagementSection` (nouveau sous-composant `CityKijijiRadiusInput` — petit champ "km" par ville active, placeholder "auto", commit au blur). `repository.py::get_cities()` le propage dans le dict retourné (`kijijiRadiusKm`, `None` si non réglé).
- **`backend/bot.py::_run_kijiji_scan()`** : le plancher fixe (`radius_km if radius_km > 0 else 1`) est retiré. Nouvelle priorité par ville, calculée dans la boucle (pas avant) : `city_data['kijijiRadiusKm']` > `scanConfig.distance` (si > 0) > `None` transmis à `scan_city()`, qui applique alors elle-même le défaut à deux paliers.
- **Tests** : `test_kijiji_core.py` (3 nouveaux — palier "résolu directement", palier "repli hub", override explicite prioritaire sur les deux), `test_bot.py` (3 nouveaux — `None` transmis par défaut, `scanConfig.distance` utilisé si > 0, `kijijiRadiusKm` par ville prioritaire sur `scanConfig.distance`). 90 tests au total (`backend/test_bot.py`, `scraping/test_core.py`, `scraping/kijiji/`), tous verts. Frontend : `npm run build` (Vite) réussi, pas de suite de tests JS existante dans le projet à ce jour.

#### 2. Raisonnement
Le rayon Kijiji n'a jamais eu de donnée fiable pour distinguer une petite d'une grande ville (contrairement à `location.name`, qui a sa propre imprécision documentée plus haut) — plutôt que d'acquérir une nouvelle source de données (population, superficie), le proxy choisi réutilise une information déjà calculée par le mécanisme de résolution de lieu lui-même (`resolve_location()` réussit ou échoue), gratuite et déjà disponible à cet endroit précis du code. Le réglage par ville comble le cas où ce proxy se trompe (ex: Longueuil, résolue directement mais pas réellement "grande" au sens Montréal) sans bloquer sur la précision du défaut automatique — les deux mécanismes demandés par l'utilisateur ("oui les deux") se complètent : l'un comme filet de sécurité raisonnable partout, l'autre comme correction ciblée là où c'est nécessaire.

---

---

[2026-07-27] [PRO] Action effectuée -> Fix : `Page.goto` Kijiji basculé sur `wait_until="domcontentloaded"` (3 sites d'appel) → Résultat : évite un échec total de scan sur un simple ralentissement des pubs/trackers Kijiji.

### Session : Timeout `Page.goto` 60s en production sur une recherche Kijiji valide

#### 1. Objectif : Corriger un signalement utilisateur — `❌ Erreur scan Kijiji (URL directe): Page.goto: Timeout 60000ms exceeded` sur une URL de recherche par ailleurs correcte (Mont-Saint-Hilaire, ancrée sur Saint-Hyacinthe), faisant échouer tout le scan de la ville sans résultat partiel
- **Cause** : `scan_search_url()`, `_visit_detail_page()` et `scan_specific_url()` appelaient `page.goto(url, timeout=self.config.timeout_navigation)` sans `wait_until` explicite — défaut Playwright `"load"`, qui attend la fin de **toutes** les ressources de la page. Kijiji charge en continu des pubs/trackers en arrière-plan (déjà documenté dans ce module via les `wait_for_load_state("networkidle", ...)` tolérants existants, jamais pour le `goto()` initial lui-même) : `"load"` peut donc dépasser les 60s de `timeout_navigation` même quand le contenu utile (résultats de recherche) est déjà disponible.
- **`backend/scraping/kijiji/core.py`** : les 3 `page.goto()` concernés passent désormais `wait_until="domcontentloaded"` — suffisant puisque `__NEXT_DATA__` (dont dépendent `_scrape_results_page()`/`parse_details_page()`) est rendu côté serveur (SSR), donc déjà présent dans le HTML initial avant même le "load" complet. Même précédent que `check_listing_availability()` (déjà en `domcontentloaded` dans ce même fichier) et que le fix Facebook analogue (`_apply_filters()`, 2026-07-21, voir plus haut).
- **Tests** : 90 tests toujours verts (aucun test unitaire ne couvrait directement `wait_until`, changement de configuration Playwright pure — pas de comportement testable sans navigateur réel).

#### 2. Raisonnement
Le même symptôme ("load"/"networkidle" qui n'aboutit jamais sur un site à trafic de fond permanent) avait déjà été diagnostiqué et corrigé côté Facebook (2026-07-21) et partiellement côté Kijiji (les `wait_for_load_state("networkidle", ...)` secondaires, déjà tolérants) — mais le `goto()` initial de `scan_search_url()`, point d'entrée de **tout** scan Kijiji (`scan_city()` en dépend), restait exposé à une attente bloquante de 60s sur l'événement le plus strict ("load"). Un signalement de production a révélé cet angle mort resté non couvert malgré le précédent déjà établi ailleurs dans le même fichier (`check_listing_availability()`) — la leçon du 2026-07-21 n'avait pas été appliquée de façon uniforme à tous les points d'entrée équivalents.

---

---

[2026-07-27] [PRO] Action effectuée -> Source Facebook désactivable indépendamment de Kijiji (`scanConfig.facebook_enabled`) → Résultat : possibilité d'isoler un scan Kijiji seul pour déboguer.

### Session : Facebook optionnel, symétrique à Kijiji

#### 1. Objectif : L'utilisateur a l'impression qu'aucun scraping Kijiji ne se produit malgré les correctifs récents (rayon, ancrage, timeout `Page.goto`) — plutôt que de continuer à deviner depuis les logs partagés Facebook+Kijiji, il demande de pouvoir isoler un scan Kijiji seul comme moyen de diagnostic direct
- **Vérification Git au passage** : `dev` local strictement à jour avec `origin/dev` (`32a6577`), rien en attente. `master` en retard de plusieurs commits (dernier push explicite sur `master` antérieur aux correctifs Kijiji récents) — normal, aucun push `master` demandé depuis.
- **`src/components/ConfigPanel.jsx`** : nouveau toggle "Source Facebook" (`scanConfig.facebook_enabled`), symétrique au toggle "Source Kijiji (bêta)" déjà existant — activé par défaut (case cochée tant que le champ n'est pas explicitement à `false`), pour qu'un compte existant (créé avant ce réglage, champ absent de Firestore) continue de scanner Facebook sans interruption.
- **`backend/bot.py::_run_sources_in_parallel()`** : le thread Facebook n'est plus systématique — construit seulement si `scan_config.get('facebook_enabled', True)`, symétrique au thread Kijiji (déjà conditionnel à `kijiji_enabled`). Si aucune des deux sources n'est activée, log un `warning` explicite et retourne sans rien faire, plutôt qu'un cycle silencieusement vide (pas de thread démarré, pas d'erreur, mais aussi aucune trace claire de pourquoi).
- **Tests** : 4 nouveaux dans `TestRunSourcesInParallel` — `facebook_enabled` absent = Facebook tourne quand même (pas de désactivation silencieuse rétroactive), Facebook désactivé seul = Kijiji continue, les deux désactivés = aucun thread + warning loggé. 93 tests au total (`backend/test_bot.py`, `scraping/test_core.py`, `scraping/kijiji/`), tous verts. Frontend : `npm run build` (Vite) réussi.

#### 2. Raisonnement
Face à un signalement flou ("j'ai l'impression que...") sans log d'erreur précis à investiguer, la demande de l'utilisateur elle-même est le bon outil de diagnostic : plutôt que de deviner depuis les logs entremêlés Facebook/Kijiji (déjà connus pour se chevaucher, voir le préfixage `[Facebook]`/`[Kijiji]` du 2026-07-27 plus haut, motivé par le même problème de lisibilité), isoler la source à observer élimine une variable entière d'un coup. Le défaut `True` pour `facebook_enabled` absent est le seul choix qui ne casse rien rétroactivement — un défaut `False` aurait désactivé Facebook pour tout compte existant à la prochaine lecture de config, une régression silencieuse bien plus grave que le problème qu'on essaie de diagnostiquer.

---

---

[2026-07-27] [PRO] Action effectuée -> Root cause du signalement "le scraping Kijiji ne fonctionne pas" : `scan_specific_url()` utilisait toujours `FacebookScraper` → `bot.py`/`notifications.py` corrigés (dispatch par domaine).

### Session : "Scan d'URL Direct" toujours Facebook, même pour une URL Kijiji

#### 1. Objectif : L'utilisateur, suite au toggle Facebook/Kijiji indépendant ajouté à la session précédente, a fourni une URL Kijiji précise et le message d'erreur reçu — diagnostiquer la vraie cause plutôt que deviner
- **Diagnostic** : l'URL fournie (`.../guitare-electrique/1740804650`) a d'abord été vérifiée directement (récupération HTTP brute) — page valide, `__NEXT_DATA__` complet (titre, prix 220$, 4 images, localisation), donc pas un problème côté Kijiji ou d'extraction. Tentative de reproduction avec Playwright/Chromium dans cet environnement : `net::ERR_CONNECTION_RESET`, expliqué par le proxy TLS obligatoire du sandbox (Chromium ne fait pas confiance à son certificat MITM, contrairement à `curl` qui honore `HTTPS_PROXY` nativement) — non représentatif de l'environnement réel de l'utilisateur, écarté comme piste.
- **Vraie cause, révélée par le message reçu par l'utilisateur** : la notification affichait `"URL Facebook : https://www.kijiji.ca/..."` — un signal direct que `bot.py::scan_specific_url()` traite **toute** URL manuelle comme du Facebook, sans jamais vérifier son domaine. Confirmé en lisant le code : `temp_scraper = FacebookScraper({}, {}, logger=self.logger)` sans condition, quel que soit `url`. Pour une URL Kijiji, `FacebookScraper` échoue silencieusement (mauvais site/sélecteurs) → `scan_result` reste vide → message générique de repli `"❓ Impossible de récupérer les informations de cette annonce (URL invalide ou bloquée)."`.
- **`backend/bot.py::scan_specific_url()`** : dispatch désormais sur `"kijiji.ca" in url.lower()` — `KijijiScraper` ou `FacebookScraper` selon le cas. Pour Kijiji : l'ID retourné par `KijijiScraper.scan_specific_url()` (bare, non préfixé — à la différence de `_run_kijiji_scan()` qui le fait déjà) est préfixé `kijiji_` avant `handle_deal_found()`, et `source="Kijiji"` propagé.
- **`backend/notifications.py::notify_scan_url_finished()`** : nouveau paramètre `source` (défaut `"Facebook"`, rétrocompatible), utilisé pour étiqueter correctement la ligne `"URL {source} : ..."` du message — corrige le même symptôme que celui qui a permis le diagnostic.
- **`src/components/ConfigPanel.jsx`** : placeholder du champ "Scan d'URL Direct" ("URL Facebook Marketplace..." → "...ou Kijiji...") — la mention Facebook-only dans l'UI elle-même invitait à l'erreur.
- **Tests** : 4 nouveaux (`TestScanSpecificUrl`, `test_bot.py`) — dispatch Facebook vs Kijiji selon le domaine, préfixage d'ID + `source` propagé pour Kijiji, `source` transmis à la notification. 97 tests au total, tous verts.

#### 2. Raisonnement
Le signalement initial ("le scraping ne fonctionne pas") était sous-spécifié — la première urgence était de faire préciser QUEL scan échoue (planifié vs manuel) et avec QUEL symptôme exact, plutôt que de deviner à partir du seul terme "scraping". Le message d'erreur fourni ensuite par l'utilisateur ("URL Facebook :" pour une URL Kijiji) contenait déjà la réponse — un mauvais étiquetage dans une notification est souvent un signe direct d'un mauvais dispatch dans le code qui l'a générée, pas seulement un problème d'affichage cosmétique à corriger isolément. Tentative de reproduction directe dans cet environnement utile malgré son échec : elle a confirmé que la donnée source n'était pas en cause avant de chercher ailleurs, et le diagnostic de la cause du `ERR_CONNECTION_RESET` (proxy MITM du sandbox) a évité de partir sur une fausse piste ("Kijiji bloque Playwright").

---

---

[2026-07-27] [PRO] Action effectuée -> Fix dédup cross-plateforme : faux négatif confirmé (même guitare FB/Kijiji jamais fusionnée) → comparaison de localisation par distance GPS plutôt que nom de ville exact.

### Session : Dédup cross-plateforme — du faux négatif signalé au risque de faux positif écarté par l'utilisateur

#### 1. Objectif : L'utilisateur a fourni deux liens de partage (`shareId=kijiji_1740804650` et `shareId=1058333816773727`) pour la même guitare réellement postée sur Kijiji ET Facebook — la détection de doublon cross-plateforme (ajoutée le même jour par une autre session, voir plus haut) ne les a pas fusionnées
- **Diagnostic** : l'annonce Kijiji en question est celle déjà utilisée pour diagnostiquer le bug `scan_specific_url()` de la session précédente — ajoutée via le **scan manuel** ("Scan d'URL Direct"), pas le scan automatique. Or `location` pour cette annonce vaut la valeur brute Kijiji imprécise ("Longueuil / South Shore", la grande sous-région de recherche — l'adresse réelle est à Sainte-Julie, vérifié via la page réelle) : le scan manuel Kijiji n'a **jamais** appliqué la correction GPS (`nearest_configured_city()`), contrairement au scan automatique (`_run_kijiji_scan()`) qui le fait déjà depuis le 2026-07-27 (plus tôt dans la journée). `_find_cross_platform_duplicate()` exigeant une correspondance exacte de ville normalisée, "longueuil / south shore" ≠ le nom précis affiché côté Facebook → jamais de match.
- **Plan initial rejeté par l'utilisateur** : retirer la ville comme critère (prix + titre seuls) — **risque de faux positif souligné avant implémentation** : un titre générique ("guitare électrique") et un prix identique par coïncidence entre deux guitares différentes de villes différentes serait alors fusionné à tort. Retenu à la place : comparer par **distance GPS** plutôt que par texte.
- **`backend/repository.py`** : `_update_deal_index()` gagne `latitude`/`longitude` (nouveaux champs `la`/`lo` dans `deals_index`), câblés depuis `create_new_deal()`/`update_deal_data_and_analysis()` (`deal_data.get('latitude'/'longitude')`, déjà présent sur `listing_data` quand extrait par le scraper).
- **`backend/bot.py::_find_cross_platform_duplicate()`** : après le filtre prix+titre (inchangés), compare `latitude`/`longitude` (nouveau) par distance Haversine (`CROSS_PLATFORM_MAX_DISTANCE_KM=5`, réutilise `calculate_distance`) quand disponibles des deux côtés — le `location.coordinates` Kijiji est précis même quand `location.name` ne l'est pas, contrairement à Facebook où les coordonnées sont parfois absentes. Repli sur l'ancienne comparaison par nom de ville normalisé si les coordonnées manquent d'un côté, pour ne jamais perdre tout filtre géographique. `_is_number()` (nouveau, même piège que `nearest_configured_city()` — `bool` sous-classe d'`int`, coordonnée non numérique faussement "gagnante" à distance 0) valide les coordonnées avant `calculate_distance()`.
- **`backend/bot.py::scan_specific_url()`** : applique désormais `nearest_configured_city()` sur la branche Kijiji (comme `_run_kijiji_scan()`), corrigeant `location` en général — pas seulement pour la dédup, améliore aussi l'affichage/le filtrage habituel de l'annonce.
- **Tests** : 12 nouveaux (`TestFindCrossPlatformDuplicate` — match GPS proche, non-match GPS lointain malgré titre générique identique [régression clé du risque signalé], repli par ville quand coordonnées absentes, non-match repli, filtrage même-source, coordonnées invalides ignorées + `TestScanSpecificUrl::test_kijiji_manual_scan_corrects_location_via_gps`). 106 tests au total, tous verts.

#### 2. Raisonnement
Le fix initialement proposé (simplement retirer la ville) aurait résolu le faux négatif signalé en introduisant un risque de faux positif symétrique — l'utilisateur l'a identifié avant l'implémentation plutôt qu'après coup en production, évitant un aller-retour. La bonne réponse n'était pas "garder ou retirer la ville" mais "remplacer un signal fragile (texte de région Kijiji) par un signal plus fiable déjà disponible mais non exploité (coordonnées GPS précises de l'annonce)" — la ville en tant que TEXTE est le problème, pas la géographie en tant que critère. Repli sur l'ancien comportement quand les coordonnées manquent : ne régresse jamais en dessous du comportement précédent, seulement au-dessus quand c'est possible.

---

---

[2026-07-31] [PRO] Action effectuée -> Durcissement du prompt d'identification (marque/numéro de série), enrichissement de la fiche descriptive (couleur) et filtres de type en multi-sélection.

### Session : De la précision d'identification IA à la sélection multiple de filtres

#### 1. Objectif
L'utilisateur a signalé que le Portier IA ignorait parfois totalement des photos de marque/logo ou de numéro de série pourtant présentes dans l'annonce, menant à de grosses erreurs de filtrage en amont. Deux demandes complémentaires dans la même session : enrichir la fiche descriptive de chaque guitare (couleur, etc.) et permettre de sélectionner plusieurs filtres de type à la fois (ex: Parlor et Baby simultanément — actuellement un seul chemin de taxonomie possible). Suite à validation du plan, l'utilisateur a demandé de s'assurer que les nouvelles données extraites soient aussi utilisables pour la recherche et pour les stats, pas seulement affichées.
- **`prompts.json`** : section IDENTIFICATION de `main_analysis_prompt` et `gatekeeper_verbosity_instruction` (Portier T1, qui reçoit aussi les images) renforcées — exigent désormais explicitement l'examen de toute photo de tête/logo, plaque au dos du manche ou étiquette via la rosace, et font primer cette preuve visuelle sur le titre en cas de contradiction (ex: titre "Gibson", logo "Epiphone" → corrige la marque, pèse sur le verdict). Nouveau champ `color` dans le schéma JSON attendu. Nouveau few-shot (identification via numéro de série malgré un titre vague, jamais répondre "Inconnue" si une preuve photo est lisible).
- **`src/components/DealCard/DealAnalysisModal.jsx`** : nouveau bloc "Fiche Technique" (marque, modèle, année, pays, couleur) — champs déjà produits par l'IA mais jamais affichés dans l'UI.
- **`backend/repository.py`** : `_update_deal_index()` indexe désormais `brand`/`model_name`/`color` (`b`/`mn`/`co`) dans `deals_index`.
- **`src/hooks/useDealsManager.js`** : la recherche texte libre matche aussi `brand`/`model_name`/`color` (plus seulement `title`), sur toutes les annonces via l'index (pas seulement le cache `loadedDeals`). Filtres de type refondus : `selectedTypePaths` (tableau de chemins de taxonomie) remplace le quadruplet `level1-4Filter` (un seul chemin en cascade) — un deal correspond si son chemin égale ou descend d'**au moins un** chemin sélectionné, permettant de cocher des catégories dans des branches différentes. Migration douce : si l'ancien format `level1Filter` est trouvé sans `selectedTypePaths`, le chemin équivalent est reconstruit au premier chargement plutôt que d'effacer le filtre déjà sauvegardé par l'utilisateur. `level1-4Options` (exports morts, plus aucun consommateur) supprimés.
- **`src/components/FilterDrawer.jsx`** : arbre de taxonomie passé en cases à cocher (`TaxonomyOption`) — sélection (checkbox) et navigation (déplier/replier, `ChevronRight`) rendues indépendantes ; une catégorie cochée se déplie automatiquement pour révéler ses sous-catégories.
- **`src/components/Dashboard.jsx`** : adapté à la nouvelle API de filtres (`selectedTypePaths`/`toggleTypePath`/`onClearTypes` au lieu de `level1-4Filter`/`setLevel1-4Filter`).
- **`src/components/StatsView.jsx`** : nouveau graphique "Distribution (Couleurs / Finitions)" ; le graphique marque existant devient représentatif de toutes les annonces (plus seulement celles déjà ouvertes) grâce à l'indexation de `brand`.
- **Tests** : 106 tests backend (`pytest`) toujours verts (aucun test dédié à l'ajout de 3 champs dans `_update_deal_index()`, changement mécanique de bas risque) ; `npm run build` frontend réussi.

#### 2. Raisonnement
La demande initiale ("le Portier ignore les photos de marque/série") pointait vers un problème de contenu de prompt, pas de code — `analyzer.py` transmettait déjà les images à chaque Tier, le texte d'instruction ne les exploitait simplement pas assez explicitement. Durcir uniquement l'Analyste (T2) aurait laissé le Portier (T1, premier filtre, le plus rapide/économique et donc le plus exposé aux erreurs signalées) sans le même garde-fou — les deux instructions ont été renforcées en miroir. Pour l'enrichissement de la fiche + recherche/stats, la question de suivi de l'utilisateur ("s'assurer que c'est utilisable pour la recherche et les stats") a révélé que `brand` existait déjà dans `aiAnalysis` mais n'était PAS dans l'index léger `deals_index` — la recherche et les stats ne portaient donc que sur les annonces déjà chargées en cache côté client, une limitation silencieuse pré-existante (le graphique "Distribution par Marque" avait déjà un commentaire l'évoquant). Plutôt que de reproduire cette même limitation pour `color`, les trois champs ont été indexés ensemble. Pour les filtres, l'exemple concret de l'utilisateur (Parlor + Baby, deux branches différentes de la taxonomie) excluait toute solution restant à l'intérieur du modèle "un seul chemin en cascade" — une refonte vers une sélection de chemins arbitraires (avec correspondance par préfixe) était nécessaire, pas un ajustement local.

---

---

[2026-07-31] [PRO] Action effectuée -> Branche `feature/discuter-gemini` : bouton "Discuter sur Gemini" (presse-papier + nouvel onglet), non fusionné, en attente de validation utilisateur.

### Session : Poursuivre une analyse par chat — chat IA intégré écarté au profit d'un simple hand-off vers Gemini

#### 1. Objectif
L'utilisateur voulait pouvoir poursuivre la conversation sur une annonce déjà analysée (au-delà de la réanalyse avec commentaire existante). Proposition initiale : un vrai chat intégré (nouvelle collection Firestore `guitar_deals/{id}/chat`, nouveau type de commande, historique de conversation) — écartée par l'utilisateur lui-même au profit d'une solution plus simple : construire le prompt (annonce + analyse) et laisser Gemini (site/app) prendre le relais.
- **`src/components/DealCard/utils.js`** : nouvelle fonction `buildGeminiChatPrompt(deal)` — construit un texte structuré (titre, prix, localisation, description, lien, identification IA, analyse financière, verdict, résumé/raisonnement) suivi d'une phrase invitant Gemini à poursuivre la discussion. Aucune dépendance React/Firebase, testée directement en Node (sortie vérifiée manuellement, cohérente).
- **`src/components/DealCard/DealCardActions.jsx`** : nouveau bouton "Discuter sur Gemini" (icône `MessageCircle`, à côté de Partager) — copie le prompt dans le presse-papier (`navigator.clipboard`, feedback visuel 2s comme le bouton Partager existant) puis ouvre `gemini.google.com/app?q={prompt encodé}` dans un nouvel onglet. Plafond `GEMINI_URL_PREFILL_LIMIT=6000` : au-delà, ouvre l'URL sans paramètre plutôt qu'une URL disproportionnée (le presse-papier reste de toute façon rempli).
- **Non testé en conditions réelles** : tentative de chargement de `gemini.google.com` via Playwright (Python) pour vérifier si `?q=` préremplit effectivement le champ de saisie — bloquée par le proxy MITM du sandbox (`net::ERR_CONNECTION_RESET`), y compris en forçant explicitement le proxy et `ignore_https_errors`. Même limite déjà rencontrée et documentée lors des tests live Kijiji de cette même session. Build frontend (`npm run build`) réussi, mais aucune validation visuelle du bouton dans un vrai navigateur avec des données Firestore réelles (pas de `.env` Firebase dans cet environnement).
- **Branche dédiée** (`feature/discuter-gemini`, demande explicite de l'utilisateur) plutôt qu'un push direct sur `dev`, précisément parce que le point non vérifiable (préremplissage Gemini) doit être testé par l'utilisateur en conditions réelles avant fusion.

#### 2. Raisonnement
Face à la proposition initiale (chat intégré), la question de l'utilisateur ("on ne peut pas faire plus simple ?") a été le bon réflexe : un chat complet aurait ajouté une collection Firestore, un nouveau type de commande, et surtout une latence par message calquée sur le cycle de polling du backend (pensé pour des opérations lentes en arrière-plan, pas pour un aller-retour conversationnel) — un mauvais fit architectural pour l'usage demandé. Déléguer la conversation à Gemini lui-même élimine tout ce chantier : zéro backend, zéro coût API supplémentaire, zéro latence anormale. Le point non garanti (préremplissage par URL) a été traité par un repli qui fonctionne à coup sûr (presse-papier) plutôt que de faire reposer toute la fonctionnalité sur un comportement non documenté d'un service tiers — si `?q=` ne marche pas, l'utilisateur colle simplement le texte déjà copié. Ne pas prétendre avoir validé ce qui ne pouvait pas l'être depuis cet environnement (limite du sandbox déjà rencontrée sur Kijiji) plutôt que de deviner un résultat.

---

---

[2026-07-31] [PRO] Action effectuée -> Retours utilisateur post-test du bouton "Discuter sur Gemini" : préremplissage `?q=` retiré (confirmé inefficace), photos ajoutées en liens publics dans le prompt.

### Session : Itération sur le hand-off Gemini après test en conditions réelles

#### 1. Objectif
L'utilisateur a testé le bouton fusionné sur `dev` et remonté 3 points : (1) le texte reste dans le presse-papier, il faut coller manuellement — confirmation que `?q=` ne préremplit rien sur gemini.google.com ; (2) il manque les images de l'annonce dans le prompt ; (3) la barre d'actions a maintenant trop de boutons — décision de placement différée par l'utilisateur lui-même, aucune action demandée sur ce point.
- **Point 1** : proposition initiale (garder `?q=` en best-effort) devenue obsolète une fois le fait confirmé en conditions réelles — `DealCardActions.jsx::handleDiscussGemini()` simplifié : ouvre systématiquement `https://gemini.google.com/app` sans paramètre, `GEMINI_URL_PREFILL_LIMIT`/construction d'URL encodée supprimés (code mort).
- **Point 2** : plutôt que la piste initialement envisagée (`navigator.share` avec fichiers images, mobile uniquement, complexité CORS/blob), l'utilisateur a suggéré une solution plus simple — les images sont déjà uploadées vers Firebase Storage avec des **URLs publiques pérennes** (`deal.storageImageUrls`, voir `handle_deal_found()`/`repository.py`). `buildGeminiChatPrompt()` (`utils.js`) les ajoute désormais comme liens cliquables numérotés dans le prompt copié, avec repli sur `deal.imageUrls` si `storageImageUrls` est absent. Fonctionne identiquement sur desktop et mobile, aucune nouvelle surface d'API.
- **Point 3** : consigné dans `TODO.md` (décision de placement UI non tranchée) — aucun changement de code, le sujet a été explicitement reporté par l'utilisateur.
- **Build** : `npm run build` réussi.

#### 2. Raisonnement
Le test réel de l'utilisateur a résolu en une phrase une incertitude que l'environnement de développement ne pouvait pas trancher (le sandbox bloquant toute navigation externe pour Playwright) — la bonne réaction a été de retirer immédiatement le code mort plutôt que de le garder "au cas où". Pour les images, la suggestion de l'utilisateur (lien public plutôt que transfert de fichier) illustre le même principe que la session précédente : préférer un mécanisme déjà existant et fiable (`storageImageUrls`, conçu à l'origine pour survivre à l'expiration des CDN Facebook/Kijiji) à une nouvelle API plus complexe et moins prévisible (`navigator.share` + fichiers, limité au mobile, dépendant du support de partage de l'app Gemini). Le point 3 (encombrement de la barre d'actions) n'a délibérément reçu aucune tentative de solution non demandée — l'utilisateur a explicitement indiqué vouloir y réfléchir lui-même, et CLAUDE.md interdit d'ajouter des changements non sollicités.

---

---

[2026-07-31] [PRO] Action effectuée -> Migration des modèles Gemini (dépréciation gemini-2.5-* en octobre 2026) + chat intégré via Firebase AI Logic, en remplacement du hand-off presse-papier.

### Session : De "le presse-papier ne suffit pas" à un chat maison — audit des modèles et architecture Firebase AI Logic

#### 1. Objectif
Le hand-off vers gemini.google.com (session précédente) s'est heurté à sa limite prévisible : impossible d'y joindre des photos. L'utilisateur a proposé de construire un chat maison via l'API, en s'appuyant sur une base de réflexion externe (choix du modèle Pro, lecture directe `gs://` via Vertex AI, Cloud Function pour cacher la clé API, question ouverte sur le caching). En parallèle, demande de vérifier si des modèles Gemini plus récents étaient disponibles.

**Audit des modèles (recherche web — pas d'accès API live, pas de `GEMINI_API_KEY` dans cet environnement)** :
- **Constat critique** : `gemini-2.5-*` (tous modèles) est retiré par Google en octobre 2026. Impacté : `gemini-2.5-flash-lite` (défaut Portier T1) et surtout le fallback codé en dur `analyzer.py::analyze_deal()` pour `expertModel` (`gemini-2.5-pro`) — exactement le piège déjà documenté dans `CLAUDE.md` (`GEMINI_MODELS["default_analyst"]` pas réellement câblé), désormais avec une échéance concrète.
- **Doute utilisateur légitime** : passer le Tier 2 (Analyste) sur un modèle "Flash" risquait-il de le rendre à peine meilleur que le Portier (Flash-Lite) ? Chiffres trouvés : Artificial Analysis Intelligence Index — Flash-Lite (3.5) = 36, Flash (3.5 et 3.6) = 50 ; en raisonnement visuel spécifiquement, Flash-Lite = 48,3% contre Flash (3.6) = 80,1%. Écart de capacité confirmé et net, en particulier sur l'analyse de photos (cas d'usage direct de ce projet).
- **Décision validée par l'utilisateur** : T1 `gemini-2.5-flash-lite` → `gemini-3.5-flash-lite` ; T2 `gemini-3.5-flash` → `gemini-3.6-flash` (capacité égale à 3.5 Flash, moins cher/plus rapide — pas une régression) ; T3 inchangé (`gemini-3.1-pro-preview`, toujours le plus fort en raisonnement pur). Pro explicitement écarté pour le T2 (tourne sur chaque annonce non rejetée, le T3 existe déjà pour l'escalade conditionnelle).
- **Fichiers modifiés** : `config.py::GEMINI_MODELS` (available + 3 défauts), `backend/analyzer.py::analyze_deal()` (3 fallbacks codés en dur), `src/hooks/useBotConfig.js` (2 occurrences, état initial + `handleResetDefaults`), `src/components/ConfigPanel.jsx` (liste de secours `availableModels`), `backend/scripts/analyze_funnel_by_user.py` (table de coûts T1/T2 mise à jour avec les tarifs actuels : Flash-Lite 0,30$/2,50$, Flash 1,50$/7,50$ par 1M tokens).

**Chat Gemini intégré (remplace le hand-off presse-papier)** :
- **Contre-proposition à la base de réflexion fournie** : pas de Cloud Function. Le backend Python existant est un *worker* qui poll Firestore (latence de plusieurs secondes, pensé pour des tâches d'arrière-plan) — mauvais fit pour un chat. **Firebase AI Logic** (SDK `firebase/ai`, appel direct du frontend à Gemini) est le produit officiel conçu pour "app + images Cloud Storage for Firebase + chat multi-tour" : sécurité via Firebase App Check plutôt qu'une clé à cacher côté serveur, latence normale d'API plutôt que le cycle de polling.
- **`gs://` confirmé fonctionnel** (recherche web) : Vertex AI / Firebase AI Logic lisent un objet Cloud Storage par son URI directement si public ou même projet — nos images sont déjà `blob.make_public()`, condition remplie sans changement.
- **Caching** : explicite (`CachedContent`) écarté — minimum ~32 768 tokens, très au-dessus du contexte d'une conversation sur une seule annonce (~1500-2500 tokens). Implicite : automatique sur les modèles récents dès qu'on garde le contexte stable en préfixe de l'historique (ce que `startChat()` fait déjà nativement) — aucun code de caching à écrire.
- **`backend/repository.py::upload_images_to_storage()`** : retourne désormais `(storageImageUrls, storageImageGsUris)` au lieu d'une simple liste — changement de signature répercuté sur ses 3 appelants (`bot.py`, `scripts/refresh_images.py`, `scripts/migrate_images.py`).
- **`src/services/firebase.js`** : ajout de `getAI()`/`GoogleAIBackend` (Firebase AI Logic) et `initializeAppCheck()`/`ReCaptchaEnterpriseProvider` (App Check, gardé par `VITE_RECAPTCHA_SITE_KEY` — désactivé proprement si absent plutôt que de planter).
- **Nouveaux fichiers** : `src/services/geminiChatService.js` (construction du modèle, contexte texte, pièces image `gs://`), `src/hooks/useDealChat.js` (session `startChat()`, persistance Firestore, capture de la référence chat avant écriture pour éviter une course avec le listener temps réel), `src/components/DealCard/DealChatPanel.jsx` (UI de conversation).
- **`DealCardActions.jsx`/`DealAnalysisModal.jsx`** : le bouton "Discuter avec Gemini" (ancien flux presse-papier) est retiré de la carte liste et ne subsiste que dans la modale (`isModal` + `onOpenChat`), qui bascule son corps entre l'analyse et le panneau de chat — un bouton en moins sur la vue liste, ce qui adresse en partie le point "trop de boutons" du TODO. `DealCard/utils.js::buildGeminiChatPrompt()` (devenu mort) supprimé.
- **Dépendance `firebase`** : `^10.8.0` → `^12.17.0` (le module `firebase/ai` n'existe qu'à partir de la v11). Surface utilisée par l'app (`app`/`auth`/`firestore`, APIs stables) inchangée, build vérifié.
- **Firestore** : nouvelle sous-collection `guitar_deals/{id}/chat`, déjà couverte par la règle générique existante (`users/{userId}/{document=**}`) — aucune règle à ajouter.
- **Tests** : 106 tests backend toujours verts, `npm run build` réussi. **Non testé en conditions réelles** : aucun compte Firebase dans cet environnement (déjà rencontré cette session) — login, chargement des annonces après l'upgrade `firebase`, et fonctionnement réel du chat (y compris `gs://`) restent à valider par l'utilisateur. Deux étapes manuelles bloquantes non faisables ici : activer Firebase AI Logic dans la console Firebase, et créer/enregistrer une clé reCAPTCHA Enterprise pour App Check.

#### 2. Raisonnement
La base de réflexion fournie par l'utilisateur contenait un bon diagnostic (Pro pour la profondeur de raisonnement, `gs://` pour éviter l'encodage) mais un choix d'architecture générique (Cloud Function) qui ne tenait pas compte de la spécificité de ce projet : un backend déjà existant, mais conçu pour du traitement asynchrone par lots, pas pour de la latence conversationnelle — exactement le problème identifié (et qui avait motivé le détour par le hand-off Gemini web) réapparaissait si on le routait par ce même backend. Repérer que Firebase AI Logic est un produit fait sur mesure pour ce cas précis a évité de réinventer un mécanisme de sécurité (Cloud Function + gestion de clé) alors qu'un standard existant (App Check) le couvre déjà. Sur le caching, la question de l'utilisateur méritait une vraie réponse chiffrée plutôt qu'un "oui c'est utile" par réflexe : le seuil minimum du caching explicite rend le mécanisme le plus visible inapplicable à l'échelle d'une seule annonce, et la bonne réponse (caching implicite, gratuit, déjà couvert par la structure naturelle de `startChat()`) ne nécessitait aucun code — l'ajouter quand même aurait été de la complexité non justifiée. Le doute de l'utilisateur sur le Tier 2 (Flash vs Pro) a été traité avec des chiffres de benchmark plutôt qu'une réassurance générique, en particulier le score de raisonnement visuel (le plus pertinent pour ce projet) — une réponse vérifiable vaut mieux qu'une intuition, la sienne ou la mienne.

---

---

[2026-07-31] [FLASH] Action effectuée -> Ajout du jeton de debug App Check pour le développement local (`npm run dev`) → Résultat : le chat Gemini reste testable en local sans domaine reCAPTCHA Enterprise dédié à `localhost`.
- **`src/services/firebase.js`** : `self.FIREBASE_APPCHECK_DEBUG_TOKEN = true` posé avant `initializeAppCheck()`, uniquement si `import.meta.env.DEV` (jamais actif en build de production). Au premier lancement local, un jeton s'affiche dans la console navigateur — à enregistrer une fois dans la console Firebase (App Check > Apps > ⋮ > Manage debug tokens).
- **Contexte** : suite aux étapes manuelles de configuration Firebase AI Logic/App Check données à l'utilisateur, question sur les "jetons" mentionnés par la console Google Cloud lors de la création de la clé reCAPTCHA Enterprise — clarifié que la clé de site (pas l'URL `enterprise.js?render=...` entière) va dans `.env`, et que le jeton de debug est un mécanisme séparé pour contourner la validation de domaine en local.

---

---

[2026-07-31] [FLASH] Action effectuée -> Fix scrollbar du panneau de chat (bug de layout flexbox) → Résultat : premier test utilisateur en conditions réelles du chat concluant (réponse Gemini cohérente sur une annonce Norman à 50$).
- **Test en conditions réelles réussi** : après résolution des blocages précédents (upgrade `firebase` non réinstallé, cache Vite obsolète après montée de version, jeton de debug App Check), le chat répond de façon pertinente. 4 points remontés par l'utilisateur : scrollbar manquante (corrigé ici), Gemini sans accès aux photos (cause identifiée : backend jamais déployé avec `storageImageGsUris`, `feature/gemini-chat` non fusionné dans `dev`/`master` — le workflow de déploiement ne se déclenche que sur ces branches), persistance de session (déjà conçue, à vérifier par l'utilisateur), envoi de photos supplémentaires (nouvelle feature, plan proposé — non implémenté à ce stade).
- **`src/components/DealCard/DealChatPanel.jsx`** : racine `flex flex-col h-full min-h-0` → `flex-1 flex flex-col min-h-0`. `h-full` (hauteur en %) dépendait d'un parent dont la hauteur n'était pas garantie explicitement (juste un item flex sans être lui-même conteneur flex) ; remplacé par le pattern flex imbriqué déjà utilisé ailleurs dans l'app (le parent devient aussi un conteneur flex, l'enfant se dimensionne par `flex-1`/`flex-grow` plutôt que par un pourcentage de hauteur).
- **`src/components/DealCard/DealAnalysisModal.jsx`** : le wrapper conditionnel `showChat` (`<div className="flex-1 min-h-0">`) devient lui-même `flex flex-col` pour porter correctement ce pattern.

---

---

[2026-07-31] [PRO] Action effectuée -> Fusion `feature/gemini-chat` → `dev` (déploiement backend) + filet de sécurité CSS + correctif d'alternance de rôles cassée par un échec App Check → Résultat : chat fonctionnel en conditions réelles après plusieurs itérations de déploiement.
- **Fusion vers `dev`** (fast-forward, `af3b2d5..5930bfb`) : déclenche le déploiement backend (`storageImageGsUris`) et frontend. Rappel donné à l'utilisateur : les annonces déjà en base n'auront pas ce champ rétroactivement (`backend/scripts/migrate_images.py` à lancer une fois pour les rétro-remplir).
- **`DealChatPanel.jsx`** : filet de sécurité `max-h-[55vh]` ajouté sur la zone de messages, en plus de `flex-1`/`min-h-0` — s'est avéré non nécessaire (la "vraie" cause du bug scrollbar précédent était un `git pull` local manquant, pas un défaut du CSS), gardé quand même comme garde-fou à faible risque.
- **Bug App Check en production (401, `AI/fetch-error`)** : `VITE_RECAPTCHA_SITE_KEY` était présente dans le `.env` local de l'utilisateur mais absente du secret GitHub Actions `DOT_ENV` qui alimente le build de déploiement — même classe d'incident que celui déjà documenté pour `VITE_FIREBASE_*` (écran blanc, 2026-07-07). Clarifié : le secret contient le fichier `.env` complet (toutes les variables), pas une clé isolée.
- **Bug découvert en cascade — alternance de rôles cassée (`AI/invalid-content`, "Content with role 'user' can't follow 'user'")** : l'échec App Check précédent avait laissé un tour `'user'` sauvegardé en Firestore sans réponse `'model'` associée (le message utilisateur est écrit avant l'appel Gemini, qui a échoué) — l'API exige une alternance stricte, donc toute nouvelle tentative sur cette même conversation cassait avec cette erreur, sans rapport apparent avec sa cause réelle.
  - **`src/hooks/useDealChat.js`** — deux correctifs complémentaires :
    1. **Prévention** : `sendMessage()` sépare désormais l'écriture du tour utilisateur (bloquante, erreur fatale si échec) de l'appel Gemini (son échec sauvegarde systématiquement un tour `'model'` placeholder d'erreur) — un tour utilisateur n'est plus jamais laissé sans réponse appariée, quelle que soit la cause de l'échec.
    2. **Auto-réparation** : la reconstruction de `startChat({history})` (à chaque mise à jour Firestore) retire désormais tout tour `'user'` final non apparié de l'historique **envoyé à l'IA** (toujours visible dans l'UI via `messages`, qui lit Firestore indépendamment) — répare silencieusement les conversations déjà cassées par l'incident ci-dessus, sans intervention manuelle sur Firestore.

#### Raisonnement
Le bug d'alternance illustre un principe de robustesse manqué à la conception initiale : persister un tour utilisateur avant de savoir si l'appel IA va réussir crée un état intermédiaire invalide si l'appel échoue — un système de conversation doit garantir l'invariant (alternance stricte) à chaque écriture, pas seulement dans le cas nominal. Le correctif traite les deux temporalités : les conversations déjà cassées (auto-réparation à la lecture) et celles à venir (les échecs sont désormais toujours résolus par un tour réponse, jamais silencieusement absents).

---

---

[2026-08-01] [FLASH] Action effectuée -> Correctif de l'auto-réparation d'historique : retirer toute la chaîne de tours 'user' non appariés, pas seulement le dernier → Résultat : erreur `role 'user' can't follow 'user'` toujours présente après le premier correctif, root cause identifiée et corrigée.
- **Cause** : l'utilisateur ayant retenté plusieurs fois d'envoyer un message pendant que le bug d'alternance était encore présent (avant déploiement du correctif précédent), chaque tentative avait ajouté un nouveau tour `'user'` sans réponse — Firestore contenait donc **plusieurs** tours `'user'` consécutifs en fin d'historique, pas un seul. L'auto-réparation initiale (`if` retirant un seul tour) laissait donc l'avant-dernier `'user'` exposé en fin d'historique, toujours invalide.
- **`src/hooks/useDealChat.js`** : le `if` de troncature devient un `while`, retirant toute la chaîne de tours `'user'` finaux non appariés plutôt qu'un seul.

---

---

[2026-08-01] [FLASH] Action effectuée -> Auto-réparation d'historique remplacée par un appariement strict (paires user/model consécutives uniquement) → Résultat : le `while` de troncature de fin de liste restait insuffisant, erreur d'alternance encore présente sur un nouveau message.
- **Cause probable** : la troncature ne traitait que les tours `'user'` en toute fin de liste ; si un tour cassé se trouve ailleurs (writes rapprochés dont les timestamps `new Date()` côté client ne reflètent pas fidèlement l'ordre réel d'écriture, `orderBy('createdAt')` peut alors ne pas trier dans l'ordre de conversation réel), il subsistait dans l'historique transmis à l'IA.
- **`src/hooks/useDealChat.js`** : nouvelle fonction `sanitizeHistory(msgs)` — parcourt la liste et ne conserve que les paires strictement consécutives (`user` immédiatement suivi de `model`), où qu'elles soient dans la liste ; tout tour `'user'` isolé est ignoré. Remplace la troncature de fin de liste, plus robuste par construction (garantit une alternance valide quelle que soit la position du problème) plutôt que de cibler un symptôme précis observé.

---

---

[2026-08-01] [PRO] Action effectuée -> App Check fonctionnel en local (nouvelle clé reCAPTCHA Enterprise de type Score) + `backend/scripts/backfill_gs_uris.py` créé, `migrate_images.py` était inutilisable pour rétro-remplir `storageImageGsUris` → Résultat : le chat répond correctement, reste le rétro-remplissage des photos sur les annonces existantes à exécuter.
- **App Check en local** : après recréation d'une clé reCAPTCHA Enterprise explicitement de type **Score** (pas Checkbox challenge — exigence documentée de Firebase App Check) et vérification qu'une clé créée via `console.cloud.google.com/security/recaptcha` est toujours une clé Enterprise (pas de choix "Classic" possible sur cette console, réservée à `google.com/recaptcha/admin`), l'erreur 401 `App Check token is invalid` a disparu en local. Un bandeau Google Cloud "clé configurée en partie, ne demande pas de scores" s'est avéré être un faux-positif pour un usage via Firebase App Check (qui appelle l'évaluation en interne) — pas une action à compléter via l'assistant proposé par la console.
- **Diagnostic du "pas d'accès aux photos" sur une annonce sans historique cassé** : confirmé que ce n'est pas un bug du mécanisme `gs://` lui-même mais l'absence de `storageImageGsUris` sur les annonces existantes, exactement comme anticipé — nécessite le script de rétro-remplissage.
- **`backend/scripts/migrate_images.py` inutilisable pour ce besoin** : sa condition de saut (`if data.get('storageImageUrls'): skip`) écarte toute annonce déjà uploadée vers Firebase Storage — soit quasiment toutes les annonces existantes, ce champ existant depuis longtemps avant l'ajout de `storageImageGsUris`. Ce script reste correct pour son usage d'origine (URLs Facebook expirées à re-scraper), mais ne peut pas servir de backfill pour le nouveau champ.
- **`backend/repository.py::list_deal_image_gs_uris(deal_id)`** (nouveau) : liste les blobs déjà présents dans Firebase Storage sous `deals/{deal_id}/` (réutilise le même motif que `delete_deal_images()`) pour en déduire les URIs `gs://` — aucun re-téléchargement nécessaire, contrairement à `migrate_images.py`.
- **`backend/scripts/backfill_gs_uris.py`** (nouveau) : parcourt `guitar_deals`, ignore les annonces déjà à jour (`storageImageGsUris` déjà présent) ou jamais uploadées (`storageImageUrls` absent — hors périmètre, voir `migrate_images.py`), écrit `storageImageGsUris` pour le reste via `list_deal_image_gs_uris()`. Support `--dry-run`. **Pas encore exécuté** — à lancer par l'utilisateur (accès à ses identifiants Firebase réels, non disponibles depuis cet environnement).

#### Raisonnement
Le script `migrate_images.py` existant semblait à première vue être le bon outil (mentionné dans le plan initial du chat) mais sa condition de saut, correcte pour son objectif d'origine (éviter de re-télécharger ce qui est déjà migré), le rendait inopérant pour le nouveau besoin — un rappel qu'un script "de migration" nommé génériquement peut avoir une portée plus étroite que son nom ne le suggère, à vérifier avant de le recommander plutôt que de supposer qu'il couvre tout besoin de rétro-remplissage. La solution retenue (lister les blobs déjà en Storage plutôt que re-télécharger depuis les URLs sources) est aussi strictement moins coûteuse en bande passante/quota Storage que n'importe quelle alternative basée sur un re-upload.

---

---

[2026-08-01] [PRO] Action effectuée -> Correctif majeur : `gs://` direct ne fonctionne pas avec le backend Gemini Developer API réellement configuré, bascule vers `inlineData` (base64) → Résultat : erreur de conception initiale identifiée en test réel, corrigée.
- **Erreur en conditions réelles** : après backfill de `storageImageGsUris` et sur une annonce jamais utilisée en chat (donc pas de conversation cassée), premier échange avec photo → `Error ... [400] Referencing Google Cloud Storage files directly is not supported. Register them using FileService.RegisterFile first. (AI/fetch-error)`.
- **Cause racine** : la vérification web faite au moment de choisir l'architecture du chat (session précédente) confirmait bien que `gs://` fonctionne pour lire une image directement — mais spécifiquement pour **Vertex AI** (`docs.cloud.google.com/vertex-ai/...`). Le code utilise `GoogleAIBackend()` (API Developer, choisi pour rester cohérent avec `GEMINI_API_KEY` côté backend Python, pas de migration Vertex AI). Le File API du Developer API existe bien côté Google, mais **n'est pas exposé par le SDK Firebase AI Logic** — confirmé par une recherche complémentaire après l'échec, qui aurait dû être faite au moment du choix initial plutôt qu'après un test en échec.
- **`src/services/geminiChatService.js`** : `buildDealImageParts(deal)` devient asynchrone — télécharge chaque image depuis son URL HTTPS publique (`storageImageUrls`, pas `storageImageGsUris`) via `fetch()`, l'encode en base64 (`FileReader.readAsDataURL`), et retourne des parts `inlineData` au lieu de `fileData`/`gs://`.
- **`src/hooks/useDealChat.js`** : `await` ajouté sur l'appel (devenu asynchrone) lors de la construction du premier message.
- **`storageImageGsUris`/`backfill_gs_uris.py` non retirés** : le champ reste écrit en base (travail déjà fait, inoffensif) au cas où une migration future vers `VertexAIBackend` serait décidée — mais n'est plus consommé par le chat dans sa forme actuelle.
- **Risque non vérifié signalé** : `fetch()` cross-origin vers `storage.googleapis.com` peut être bloqué par une politique CORS absente sur le bucket (contrairement à une balise `<img>`, qui n'a jamais eu ce problème dans le reste de l'app) — à surveiller si le prochain test échoue encore, cette fois côté réseau/CORS plutôt que côté API.

#### Raisonnement
La vérification initiale (recherche web confirmant "gs:// fonctionne") était correcte mais insuffisamment précise : elle validait la capacité générale de la plateforme Google (Vertex AI) sans vérifier qu'elle s'appliquait bien au backend *spécifique* retenu dans la décision d'architecture (`GoogleAIBackend`, choisi pour d'autres raisons — cohérence avec le backend existant). Une confirmation "la plateforme le permet" ne garantit pas "le produit/SDK/backend precis configuré le permet" — les deux doivent être vérifiés ensemble, particulièrement pour un écosystème (Firebase AI Logic) qui expose plusieurs backends avec des capacités différentes sous une API unifiée en apparence. Le correctif (inlineData) est une solution connue et documentée pour ce même SDK, donc un repli fiable plutôt qu'une nouvelle inconnue.

---

---

[2026-08-01] [FLASH] Action effectuée -> Redimensionnement/compression des photos avant envoi en base64 → Résultat : "Failed to fetch" générique sur l'appel Gemini, cause probable identifiée (taille de requête) sur la première annonce testée avec le correctif inlineData.
- **Symptôme** : sur une annonce jamais utilisée en chat (donc hors des bugs précédents), premier message → `Failed to fetch (AI/error)`, une erreur réseau générique sans code HTTP précis, cohérente avec une requête trop volumineuse (plusieurs photos Marketplace en haute résolution, base64 = ×1.33 la taille déjà conséquente des originaux).
- **`src/services/geminiChatService.js::fetchImageAsInlinePart()`** : chaque image est désormais redimensionnée via `createImageBitmap()` + `<canvas>` (plafond 1024px de long côté, réencodage JPEG qualité 80%) avant l'encodage base64 — même principe que `_download_and_optimize_image()` côté backend (PIL), côté navigateur cette fois. Le passage par un blob local (`fetch()` puis `createImageBitmap(blob)`) évite le "tainted canvas" qu'aurait causé un chargement direct via `<img src>` cross-origin sans CORS.
- **Non confirmé comme cause définitive** : "Failed to fetch" est trop générique pour l'affirmer avec certitude sans inspection de l'onglet réseau du navigateur — traité comme la piste la plus probable et une amélioration de toute façon justifiée (coût/latence réduits), pas comme un diagnostic certain.

---

---

[2026-08-01] [PRO] Action effectuée -> CORS manquant sur le bucket Firebase Storage identifié et corrigé (gsutil), chat Gemini validé de bout en bout en conditions réelles → Résultat : fonctionnalité complète, photos analysées correctement.
- **Dernier symptôme** : plus d'erreur affichée, mais Gemini répond ne voir aucune photo — `buildDealImageParts()` avale silencieusement chaque échec de `fetch()` par annonce (comportement voulu pour ne pas bloquer tout le chat sur une seule image ratée), masquant la cause réelle tant que l'utilisateur n'a pas regardé la console navigateur.
- **Confirmation** : `TypeError: Failed to fetch` sur `https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/...` — CORS non configuré sur le bucket. Contrairement à une balise `<img src>` (jamais soumise aux mêmes règles, d'où l'absence de ce problème ailleurs dans l'app), un appel `fetch()` JavaScript cross-origin nécessite un en-tête `Access-Control-Allow-Origin` explicite.
- **Correctif (config, pas de code)** : `gsutil cors set` avec une policy autorisant `GET` depuis `https://ludoviclebart.github.io` et `localhost` (dev), appliquée par l'utilisateur via Cloud Shell (pas de `gsutil` installé localement).
- **Validation finale utilisateur** : "ça marche!!" — chat fonctionnel de bout en bout (texte + photos) sur une annonce Epiphone DR-100.

#### Raisonnement
Cette session illustre une chaîne de diagnostic en couches successives, chacune masquant la suivante : déploiement manquant → secret GitHub incomplet → type de clé reCAPTCHA incorrect → mécanisme `gs://` incompatible avec le backend choisi → requête trop volumineuse → CORS. Chaque couche a nécessité un signal différent (message d'erreur explicite, comportement silencieux, ou absence totale de signal) et le réflexe systématique a été de vérifier plutôt que de supposer résolu — en particulier le cas CORS, où l'absence de toute erreur visible aurait pu faire croire à un problème côté prompt/IA plutôt qu'un échec de chargement réseau silencieusement avalé. La leçon générale pour les prochaines fonctionnalités touchant Firebase Storage + appels `fetch()` cross-origin côté client : vérifier CORS dès la conception plutôt qu'en réaction à un symptôme.
