# Plan — IDs de villes Facebook et suivi de santé des scrapers

*Créé le 2026-10-23. Plan validé par l'utilisateur le 2026-10-23 (relu par Opus). Branche de travail : `ccr-92f47355-0yvnvx`.*

## 1. Contexte : ce qu'on a découvert

La question de départ était « les résultats Facebook sont-ils meilleurs avec un vrai compte qu'en anonyme ? » (hypothèse de l'utilisateur : « je suis sûr que c'est beaucoup moins bon en anonyme »). **Cette question reste OUVERTE** (voir Phase C, §6) : la comparaison n'a jamais pu être faite, car la connexion automatique du compte a été bloquée par Facebook (checkpoint `two_step_verification`, détection de bot) ; l'enquête a ensuite dévié vers un problème d'ID de ville, apparu prioritaire. Ce que la mesure a établi, sans répondre à la question de départ :

- **Le scan Facebook du bot cherchait en France.** L'ID de Bromont en base (`110035235685771`) est Bromont-Lamothe (Puy-de-Dôme), pas Bromont (Québec). Mesure anonyme sur le serveur : **82 cartes vues, 100 % hors liste de villes, 0 annonce gardée** (Riom, Clermont-Ferrand, Issoire…). Avec le bon ID (`103111009728836`) : 24 cartes, 12 % hors liste, 21 gardées (Montréal, Longueuil…).
- **Un seul ancrage** : `compute_anchor_clusters` (rayon 80 km) regroupe les 27 villes de l'utilisateur sous Bromont. Seul l'ID de l'ancrage compte pour le scan Facebook.
- **Le mode anonyme charge bien la page** (82 cartes avec l'ID français, 24 avec le bon : pas de blocage). Cela **ne dit rien** sur la qualité relative d'une session connectée : on n'a aucune mesure « connecté » (le compte a un 2FA que le script ne peut pas passer seul). La comparaison honnête n'est possible **qu'avec le bon ID de ville**, d'où la Phase 0 en préalable.
- **8 IDs faux sur 27** (audit `audit_fb_city_ids.py`) : Beloeil (→ Belgique), Saint-lambert (→ Woluwe-Saint-Lambert, Bruxelles), Sutton (→ Macclesfield, R.-U.), La saline (→ Réunion), Sherbrooke (ID texte `edmonton`), Chambly / Longueuil / McMasterville (ID texte aléatoire), Carignan (→ Chambly) ; doublons « Mc Masterville » / « McMasterville ». Sans effet sur le scan tant que Bromont est le seul ancrage, mais à corriger (un autre ancrage ou un ajout de ville les rendrait actifs).
- **Rien ne détectait le problème** : `bot.py` calculait des statistiques par cycle (`cycle_stats`) mais seulement sous forme de ligne de log, sans alerte.
- **Ce que Facebook affiche** : pour « Bromont », 3 suggestions (`Bromont | Ville`, `Bromont | Ville`, `Bromont-Lamothe, Auvergne, France | Ville`). Facebook **omet la région des lieux proches de l'IP** du client : l'indice « Québec » de `CityFinder` n'y correspond donc jamais et le code retombe sur la première suggestion. Le clic des suggestions 1 et 3 a donné le même ID : l'ordre / le clic ne sont pas fiables, l'ID obtenu doit être **vérifié**.
- **Piège de mesure** : les tests faits depuis un téléphone en France ne valent rien (le téléphone se géolocalise). Seules les mesures du serveur (IP québécoise, géolocalisation forcée Montréal) comptent.

## 2. Décisions de l'utilisateur (2026-10-23)

1. Ordre : **Phase A (suivi de santé) d'abord**, puis Phase B (réparation des villes).
2. Seuils d'alerte : **3 échecs de suite ou ≥ 50 % sur 10 scans**, 6 h entre deux alertes d'une même (source, ville).
3. Canal : **ntfy + email**, comme `notify_gatekeeper_failure`.
4. Deux villes qui partagent un ID Facebook (Saint-Hubert / Longueuil, Carignan / Chambly) : **colonne `fb_location_id` distincte de la clé primaire** (voir §4.3).
5. Coordonnées fausses (Sherbrooke porte celles de Montréal) : **signalées seulement**, corrigées à part (`--fix-coords`).
6. **Pas de nombre minimal d'annonces** pour valider une ville (Bromont est minuscule, il n'y a pas forcément 8 guitares) : la vérification d'un ID sonde le **fil général** de la ville (toutes catégories) et compare des **proportions** ; un plancher de 3 cartes évite seulement de conclure sur du vide (résultat INDÉTERMINÉ, jamais une correction automatique).
7. Un échec = « le scraper est cassé », **jamais** « aucune annonce » : un scan qui voit des cartes mais n'en garde aucune est `ok`.

## 3. Phase 0 — corriger Bromont (urgent, SQL manuel)

Tant que l'ID de Bromont est faux, le scan Facebook ne ramène rien d'utilisable. Commande donnée à l'utilisateur (transaction : insérer la ville sous `103111009728836`, recopier `user_city_prefs`, supprimer l'ancienne ligne ; `cities.id` est référencé sans `ON UPDATE CASCADE`). **Statut : à confirmer exécutée.** Avec la colonne `fb_location_id` (§4.3), cette correction se réduira à un `UPDATE` sans toucher à la clé primaire.

## 4. Phase A — suivi de santé des scrapers (faite, codée, non déployée)

Commit `bec5a48`. Résumé :

| Élément | Fichier |
|---|---|
| Classification d'un scan (`ok`, `no_cards`, `geo_mismatch`, `blocked`, `detail_degraded`, `error`), règle d'alerte, pistes de réparation | `backend/scrape_health.py` (fonctions pures) |
| Table `scrape_runs` (une ligne par scan de ville, sans titre ni URL, purge 90 j) | `backend/api/schema.sql` |
| `record_scrape_run`, `recent_scrape_outcomes`, `was_scrape_alerted_recently`, `last_ok_scrape_run`, `mark_scrape_run_alerted`, `purge_scrape_runs` | `backend/pg_repository.py` |
| Alerte ntfy + email | `NotificationService.notify_scrape_health` |
| `FacebookScraper._scan_result` expose `error` ; `KijijiScraper.last_scan` | `backend/scraping/core.py`, `backend/scraping/kijiji/core.py` |
| Un enregistrement par scan, alerte avec délai 6 h, jamais d'exception vers le scan | `backend/bot.py::_record_scrape_health` |
| Rapport chiffré par source / ville / code | `backend/scripts/scrape_health_report.py` |

Seuils : `geo_mismatch` = ≥ 5 cartes et ≥ 90 % hors liste ; `detail_degraded` = ≥ 3 fiches dont ≥ 50 % sans photo. Tests : 19 purs, 9 dans `test_bot.py`, 5 contre un vrai Postgres (`test_pg_repository.py`).

**Limite connue** : un utilisateur qui n'a que 1 ou 2 villes en liste verrait presque toutes les cartes de sa zone « hors liste » → fausse alerte `geo_mismatch`. Piste : distinguer « hors région » de « hors liste » (la région est dans le libellé de la carte, ex. « Montréal, QC »). Non traité.

## 5. Phase B — vérification et réparation des villes Facebook

### B1. Module pur `backend/scraping/city_verification.py` (sans Facebook, sans base)
- `parse_label(label)` → (nom, région ou `None`) : « Bromont | Ville » → (`Bromont`, `None`) ; « Bromont-Lamothe, Auvergne, France | Ville » → (`Bromont-Lamothe`, `Auvergne, France`).
- `filter_candidates(labels, city_name, region_hint)` : garde les suggestions dont le **nom normalisé est égal** (`normalize_city_key`, donc « Woluwe-Saint-Lambert » ≠ « Saint-Lambert ») et dont la région est **absente** (lieu proche, prioritaire) ou **compatible** avec l'indice ; une région explicite incompatible est exclue.
- `score_probe(card_locations, province, expected_coords, gazetteer)` → part de cartes de la province (« , QC »), et part de cartes proches des coordonnées attendues (départage les homonymes québécois). Cartes en `City, QC`.
- `decide(scores)` → `VERIFIED(id)` / `AMBIGUOUS` / `INDETERMINATE` (moins de 3 cartes) / `NOT_FOUND`. Valide = ≥ 70 % de cartes de la province **et** (si des coordonnées sont connues) ≥ 50 % de cartes proches. Deux ID distincts valides → `AMBIGUOUS`.

### B2. Correction de `CityFinder`
- Lister les suggestions, filtrer (B1), **cliquer par libellé** (l'ordre n'est pas stable d'un chargement à l'autre).
- **Attendre que l'URL change** par rapport à celle d'avant le clic et **exiger un ID numérique** (hypothèse d'Opus, à confirmer en journalisant l'URL avant/après : `wait_for_url(r"/marketplace/.*?/")` rend la main tout de suite si l'URL courante correspond déjà, ce qui expliquerait les IDs texte et le clic « incohérent »).
- Sonder chaque ID candidat (fil `/marketplace/<id>/`, cartes seulement, sans ouvrir les fiches), puis `decide`.
- `find_city_id_and_coords` garde son tuple de 4 éléments (`matched_confidently = status == VERIFIED`). Sur `AMBIGUOUS` / `INDETERMINATE` / `NOT_FOUND` : `city_id = None` → `add_city_auto` **refuse l'ajout** (décision 1 du TODO du 2026-10-05) ; hors Canada, ancien comportement marqué `needsReview`.
- `add_city_auto` : si le nom existe déjà au catalogue, l'ID trouvé par `CityFinder` est aujourd'hui ignoré (`target_id = existing_id_by_name`) → un ID faux n'est jamais réparé par ce chemin ; à corriger.

### B3. Colonne `fb_location_id` et script `backend/scripts/repair_fb_city_ids.py`
- **Schéma** : `cities.fb_location_id TEXT NULL` (ID Facebook réel ; `NULL` = repli sur `id`, comportement actuel). Plusieurs villes peuvent partager le même `fb_location_id` (Saint-Hubert → Longueuil). `cities.id` reste la clé primaire, donc aucun `INSERT` / `DELETE` de ville, aucune migration de `user_city_prefs`.
- **À inventorier avant de coder** : tous les lieux qui lisent `cities.id` comme ID Facebook (`bot.py` autour des l. 713 et 734 — `city_mapping` —, `add_city_auto`, `pg_repository.get_cities`, `backend/api/cities_repo.py`, frontend `ConfigPanel`).
- **Phase A du script, base seule, sans réseau** : doublons (clé canonique, espaces compris), IDs non numériques, deux noms sur un ID, coordonnées hors Québec ou à > 15 km d'un re-géocodage, ancrages par utilisateur (avant / après).
- **Phase B du script, Facebook** : ancrages d'abord, puis le reste dans un ordre aléatoire. Pour chaque ville : sonder l'ID actuel ; s'il échoue, `CityFinder` v2. États : `OK`, `À CORRIGER`, `AMBIGU`, `INDÉTERMINÉ`, `ÉCHEC`. Un seul contexte navigateur ; pause aléatoire de 20 à 60 s entre villes, 3 à 5 min toutes les 5 villes ; **arrêt complet sur login / captcha** ; fichier d'état JSON local pour reprendre.
- **Sortie** : rapport JSON (noms de lieux seulement, jamais de titres d'annonces), **dry-run par défaut**.
- **`--apply --from rapport.json`** : applique le rapport relu, sans re-scraper ; par ville, une transaction qui vérifie que la base est toujours dans l'état du rapport. Sauvegarde locale des lignes touchées avant écriture (elles contiennent des uid : jamais versionnée). Idempotent.
- Coordonnées : signalées seulement ; `--fix-coords` à part.

### B4. Tests (sans Facebook)
`test_city_verification.py` : `parse_label`, `filter_candidates` (exclut France / Alberta / Bruxelles, garde les libellés sans région), `score_probe`, `decide` (Québec ≈ 100 % contre France 0 % → VERIFIED ; deux valides → AMBIGUOUS ; moins de 3 cartes → INDETERMINATE ; aucune valide → NOT_FOUND) ; planification de l'application (nom partagé, déjà appliqué = no-op). Dans `test_bot.py` : l'ajout d'une ville non vérifiée est refusé ; un nom existant reçoit le nouvel ID.

### B5. Déploiement, risques, retour arrière
1. Sauvegarde de la base (`backup_postgres.py`).
2. B1 + tests. 3. Colonne `fb_location_id` + lecture par le bot (`fb_location_id or id`). 4. Script en dry-run sur Bromont seul, puis `--apply` **après confirmation**, puis vérifier au cycle suivant la baisse du taux hors liste (rapport de santé). 5. Dry-run complet, relecture, `--apply`. 6. `CityFinder` v2 + `add_city_auto`. 7. Coordonnées en dernier.
- **Risques** : blocage anti-bot (arrêt automatique) ; seuils mal calibrés (le dry-run sert à les juger, calibrer sur les deux IDs de Bromont) ; bot actif pendant `--apply` (transactions courtes).
- **Retour arrière** : remettre `fb_location_id` à `NULL` pour les villes touchées, ou restaurer depuis la sauvegarde JSON / la base.

## 6. Phase C — comparaison anonyme / connecté (à reprendre, question toujours ouverte)

*Objectif : répondre à l'hypothèse de l'utilisateur (« beaucoup moins bon en anonyme ») avec des chiffres, maintenant qu'on sait que le test était faussé par l'ID de Bromont.*

- **Préalable** : Phase 0 faite (bon ID de Bromont), sinon on compare deux scans de la France.
- **Base de référence anonyme (mesurée le 2026-10-23, bon ID, requête `Guitar.,,.,` 0-300 $)** : 24 cartes, 3 hors liste (12 %), 21 gardées, 100 % avec photos, 71 % avec description, 100 % avec GPS et date de publication.
- **Ce qui a bloqué** : la connexion automatique (`FB_EMAIL` / `FB_PASSWORD`) est arrêtée par Facebook (checkpoint 2FA, URL `two_step_verification`). C'est un blocage anti-bot de connexion, pas un échec de la comparaison elle-même.
- **Outil déjà prêt** : `backend/scripts/compare_fb_anon_vs_auth.py` (anonyme + connecté alternés, `--runs`, tableau, lieux hors liste ; réutilise `~/facebook_storage_state.json`). Avec `--anon-only`, il ne fait que la partie anonyme.
- **Chemin retenu pour se connecter sans ordinateur** (l'utilisateur n'a qu'un téléphone) : se connecter **depuis le serveur lui-même** (même IP que le bot, donc pas d'invalidation de session) par un écran virtuel visible depuis le téléphone : `Xvfb :99` + `x11vnc` lié à l'IP Tailscale + app VNC sur le téléphone, puis `DISPLAY=:99 python -m backend.scripts.compare_fb_anon_vs_auth --login-only --manual-login --relogin` (code 2FA saisi à la main). La session est ensuite mise en cache.
- **Comparer** (≥ 3 passages alternés) : cartes vues, part hors liste, annonces gardées, annonces présentes seulement en connecté (et leur âge), fiches avec prix / photos / description, blocages.
- **Décision à prendre ensuite** : si l'écart est net, évaluer le coût d'une session connectée en production (renouvellement manuel du 2FA, risque de restriction du compte, repli automatique vers l'anonyme + alerte ntfy à l'expiration).

## 7. Mode d'emploi (serveur) — correction des IDs de villes

*Codé et testé le 2026-10-25 (250 tests, dont l'application réelle contre un Postgres 16 local). Jamais exécuté contre le vrai Facebook ni la vraie base : les sélecteurs de la page de sélection de lieu et de lecture des cartes du fil sont ceux du bot, mais la sonde `/marketplace/<id>/` est nouvelle — à valider sur Bromont d'abord.*

**Ordre obligatoire** : le bot doit lire `fb_location_id` AVANT qu'on l'écrive, sinon la correction ne change rien au scan.
1. **Déployer le code** (`dev` / `master`, au choix de l'utilisateur) puis redémarrer le bot (`sudo systemctl restart guitare-hunter`). La colonne `cities.fb_location_id` est créée au démarrage (le schéma est rejoué) ; pour lancer le script avant le redémarrage : `psql "$DATABASE_URL" -c "ALTER TABLE cities ADD COLUMN IF NOT EXISTS fb_location_id TEXT"` (idempotent).
2. **Bromont d'abord** (3 minutes, c'est le seul ancrage) :
   ```bash
   cd ~/GuitareHunter && source venv/bin/activate
   set -a; source <(tr -d '\r' < ~/.guitarhunter_prod_db.env); set +a
   xvfb-run -a python -m backend.scripts.repair_fb_city_ids --user-id <UID> --only Bromont --report ~/fb_city_report.json
   python -m backend.scripts.repair_fb_city_ids --from ~/fb_city_report.json            # aperçu, n'écrit rien
   python -m backend.scripts.repair_fb_city_ids --from ~/fb_city_report.json --apply    # écrit fb_location_id
   ```
   Si la Phase 0 (SQL) a déjà été exécutée, le rapport dira `OK` pour Bromont : rien à faire.
3. **Toutes les villes actives** (compter ~1 h à 1 h 30 : sonde + recherche + pauses anti-bot ; reprenable, on peut interrompre et relancer la même commande) :
   `xvfb-run -a python -m backend.scripts.repair_fb_city_ids --user-id <UID> --report ~/fb_city_report_all.json`, puis relire le rapport, aperçu, `--apply`.
4. **Vérifier** : au cycle suivant, `python -m backend.scripts.scrape_health_report` (Bromont : 0 % `geo_mismatch`, cartes gardées > 0).
- **Retour arrière** : `UPDATE cities SET fb_location_id = NULL WHERE id = '<id>'` (retour à `cities.id`) ; la sauvegarde JSON locale (`cities_backup_*.json`, mode 600, ignorée par git) garde l'état d'avant.
- **Hors périmètre de ce script** : les doublons de graphie (`merge_city_catalog_duplicates.py`) et les coordonnées douteuses (signalées dans le rapport, jamais modifiées).

## 8. État d'avancement

- [x] Phase A codée, testée, poussée (non déployée, non validée par l'utilisateur).
- [x] Phase 0 : Bromont corrigé en base le 2026-10-28 (étape 2 du §7, rapport `A_CORRIGER` puis `--apply`) ; effet réel après déploiement du code qui lit `fb_location_id`.
- [x] B1 module pur (`city_verification.py`, 37 tests).
- [x] B2 `CityFinder` v2 (`city_finder.py`, orchestration testée avec un faux pilote, 20 tests) ; `add_city_auto` refuse un ID non vérifié et attache l'ID vérifié à un nom existant.
- [x] B3 colonne `cities.fb_location_id` (lue par le scan Facebook : `fb_location_id` sinon `id`) + `backend/scripts/repair_fb_city_ids.py` (rapport puis application, 25 tests dont l'application réelle en base).
- [ ] B5 déploiement par étapes (§7) : à faire par l'utilisateur, Bromont d'abord.
- [ ] Phase C : comparaison anonyme / connecté (question ouverte, voir §6).
