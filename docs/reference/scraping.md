# Scraping — Facebook Marketplace, Kijiji, villes, santé (référence)

> Vérifié le 2026-11-05 contre le commit `f1075b3` (code identique à `22e5a1b`) : `backend/scraping/` (`core.py`, `parser.py`, `zone.py`, `geo_clustering.py`, `utils.py`, `config.py`, `catchup.py`, `scroll.py`, `city_finder.py`, `city_verification.py`), `backend/scraping/kijiji/` (`core.py`, `parser.py`, `locations.py`, `config.py`), `backend/scraping_leboncoin/core.py`, `backend/scrape_health.py`, et la façon dont `bot.py` les appelle (voir [`bot.md`](bot.md)). Ce fichier remplace, pour le scraping, les sous-sections `backend/scraping/`, `kijiji/`, `CityFinder v2` et « Suivi de santé » d'`ARCHITECTURE.md`, qui restent comme historique des décisions.

## Rôle

Lire les annonces des sites sources avec Playwright et les rendre sous une forme commune (`listing_data`) que `bot.py::handle_deal_found` traite. Le scraping ne décide ni du budget, ni des mots-clés, ni de l'analyse : il filtre seulement par zone géographique.

## Fichiers

| Fichier | Rôle |
|---|---|
| `scraping/core.py` | `FacebookScraper` : session Playwright, scan de recherche, scan d'URL, vérification de disponibilité |
| `scraping/parser.py` | `ListingParser` : carte de résultat, fiche détail, prix, date de publication |
| `scraping/zone.py` | Fonctions pures de zone : GPS, hors Canada, décision sur une carte |
| `scraping/geo_clustering.py` | Points d'ancrage (couverture gloutonne), commun à Facebook et Kijiji |
| `scraping/catchup.py`, `scroll.py` | Règle d'arrêt « scan rattrapé » (désactivée) ; critères d'arrêt du défilement |
| `scraping/config.py` | `ScraperConfig` (Facebook) |
| `scraping/utils.py` | `calculate_distance` (Haversine), `city_name_variants` |
| `scraping/city_finder.py`, `city_verification.py` | Recherche et **vérification** de l'ID Facebook d'une ville (v2) |
| `scraping/kijiji/core.py`, `parser.py`, `locations.py`, `config.py` | `KijijiScraper` et sa résolution de lieux |
| `scraping_leboncoin/core.py` | `LeboncoinScraper` : **non branché** dans le bot (voir plus bas) |
| `backend/scrape_health.py` | Classe chaque scan (`ok`, `no_cards`, `geo_mismatch`, `blocked`, `detail_degraded`, `error`) et décide des alertes |
| `backend/resources/kijiji_locations.json`, `city_coordinates.json` | Lieux Kijiji ; 839 municipalités québécoises avec coordonnées |

## Facebook (`FacebookScraper`)

### Session
`start_session` lance Chromium avec `headless=False` (réglage `ScraperConfig.headless`, voulu : le serveur a Xvfb), un User-Agent et une taille de fenêtre tirés au hasard, `locale fr-CA`, fuseau `America/Montreal`, **géolocalisation par défaut Montréal** (45,5017 ; −73,5673) avec permission accordée, et un proxy tiré au hasard dans `PROXIES` s'il y en a. La session est **anonyme** (`storage_state_path = None`). Une instance par scan, jamais partagée entre threads.

### Scan de recherche (`scan_marketplace`)
1. URL `…/marketplace/<id>/search/?query=…&exact=false&sortBy=creation_time_descend` (tri par date). Le prix n'est **pas** dans l'URL : `_apply_filters` saisit min et max dans les champs de la page, en dernier. Si `sortBy` disparaît de l'URL après cela, un avertissement est journalisé.
2. Blocage détecté si l'URL contient `/login` ou `captcha` → résultat `anti_bot_blocked`.
3. Défilement par la molette (1 000 px, 2 s) jusqu'à `max_ads × 3 + 30` cartes, ou stagnation (2 étapes sans nouvelle carte), au plus `max_scroll_iterations = 20`.
4. Pour chaque carte : identifiant, titre, prix, lieu (`parse_listing_card`). Une carte sans lieu est abandonnée (`dropped_no_location`). Lieu hors liste de villes : rejet (`rejected_out_of_list`), sauf si le contrôle GPS peut tenter de la rattacher (voir ci-dessous). `should_skip_callback` (c'est `bot.should_skip_deal`) écarte les annonces connues au prix inchangé. Prix 0 sans « Gratuit »/« Free » : abandonnée (`dropped_no_price`).
5. Les cartes retenues ouvrent leur **fiche détail** une par une (page neuve, jusqu'à 10 photos, description, GPS, date). Fiche non chargée : repli sur la photo de la carte. Aucune photo extraite : un rechargement puis une seconde extraction, gardée seulement si elle apporte plus de photos.
6. Retour : dict `{deals, error, anti_bot_blocked, rejected_out_of_list, total_cards_seen, dropped_no_location, dropped_no_price, skipped_known, stopped_caught_up}`. Une exception est interceptée et renvoyée dans `error` (elle n'est pas propagée).

### Contrôle GPS (mode strict, `set_gps_zone`)
Actif seulement si le bot a appelé `set_gps_zone` (mode `distance = 0`). Règles de `zone.card_verdict` : lieu reconnu → GPS contrôlé avec la tolérance `FACEBOOK_STRICT_NAME_GPS_KM` (15 km) ; lieu non reconnu → rattaché seulement si le GPS est à ≤ `FACEBOOK_STRICT_GPS_KM` (5 km) d'une ville listée ; GPS illisible → le nom décide. Au plus 8 fiches supplémentaires par scan (`gps_fallback_max_pages`), arrêt si les 3 premières ne rattachent rien (`may_try_gps_fallback`). Les rejets au GPS sont mémorisés par processus (5 000 entrées au plus, clé = signature de la liste de villes + identifiant).

### Fiche détail (`ListingParser.parse_details_page`)
- **Photos** : images visibles de plus de 300 × 300 pixels dont l'URL contient `scontent`, en excluant celles entourées d'un lien vers une autre annonce (suggestions) ; flèche droite entre chaque lecture, 10 tours et 10 photos au plus.
- **GPS** : lu dans l'URL de la carte statique (`center=lat%2Clng`).
- **Description** : `og:description` si plus de 10 caractères, sinon le plus long texte de plus de 50 caractères ; tronquée à 3 000.
- **Date** : `abbr[aria-label]` interprété par `parse_french_date` (formules françaises « il y a N … » et « 12 mars »). **En cas d'échec, la date de scraping est utilisée** pour `published_at_ts`.

### Scan d'URL (`scan_specific_url`) et disponibilité (`check_listing_availability`)
`scan_specific_url` lit une fiche, tente un rechargement s'il n'y a pas de photo, puis appelle le callback. `check_listing_availability` renvoie « indisponible » sur : HTTP 404/410, URL sans `/marketplace/item/`, marqueur de vente dans `og:title` (`sold_markers`), ou un texte visible correspondant à un motif (« n'est plus disponible », « vendu », « sold », « plus disponible », « out of stock », « expired »…) dans les `span`, `div[role=button]`, `h1`, `h2`. Erreur ou délai dépassé : l'annonce est considérée disponible.

## Kijiji (`KijijiScraper`)

### Résolution du lieu
`locations.py` charge `kijiji_locations.json` (192 noms normalisés, EN et FR, pour 165 lieux distincts du Canada). `resolve_location` n'accepte qu'une égalité exacte du nom normalisé, ou de la partie avant `/` (« Longueuil / South Shore ») : volontairement **stricte**, pour éviter des homonymes d'autres provinces. Sans correspondance, `nearest_resolvable_hub` choisit, parmi les 23 municipalités de `city_coordinates.json` (839 au total, toutes québécoises) dont le nom se résout chez Kijiji, la plus proche par GPS — attention, cette liste contient des homonymes d'autres provinces (constat R-3-5). Sans coordonnées ni sous-zone, la ville est ignorée avec une erreur journalisée.

### Recherche (`scan_city` → `scan_search_url`)
URL `…/b-recherche/<lieu>/<requête>/k0c613l<lieu>` + `price=min__max` + `address`, `ll`, `radius` (le lieu `l0` serait ignoré par le site). Rayon : celui de l'appelant, sinon 15 km pour une sous-zone propre et 5 km pour un repli. Page chargée en `domcontentloaded`. Les annonces sont lues dans `__NEXT_DATA__` (état Apollo) ; repli par défilement et sélecteurs `data-testid` si absent. Chaque annonce retenue ouvre sa **fiche détail** (galerie complète, GPS, prix, lieu) ; en cas d'échec, repli sur les infos de la carte. `max_ads` plafonne le total ; la pagination n'est pas gérée.

### Détail (`KijijiListingParser.parse_details_page`)
Cascade : `__NEXT_DATA__` (prix en cents ÷ 100, coordonnées, 10 photos au plus) → JSON-LD → DOM → lieu déduit du slug d'URL. `price_found` distingue un prix à 0 réel d'un prix introuvable.

### Autres méthodes
`scan_specific_url` (une annonce) et `check_listing_availability` (HTTP 404/410, URL sans `/v-`, marqueur de vente dans `og:title`, motifs de texte sur tous les `span`, `div`, `h1`, `h2`). `scan_marketplace` (recherche par le champ de la page d'accueil) n'est **pas utilisée** par le bot : le filtre de lieu y est resté non fonctionnel.

Kijiji tourne en `headless=True`, sans proxy ni géolocalisation forcée.

## Points d'ancrage (`geo_clustering`)
`compute_anchor_clusters(villes, rayon)` : couverture gloutonne — à chaque tour, la ville qui couvre le plus de villes non couvertes dans le rayon devient ancrage. Une ville sans coordonnées forme son propre cluster. Rayon 80 km des deux côtés (`FACEBOOK_ANCHOR_RADIUS_KM`, `KIJIJI_ANCHOR_CLUSTERING_RADIUS_KM`) ; pour Kijiji le rayon réellement envoyé est le plus grand de `scanConfig.distance` et de `max_member_distance_km()`.

## ID Facebook d'une ville (`CityFinder` v2)
`CityFinder.lookup` : ouvre le sélecteur de lieu et liste les suggestions ; filtre celles dont le nom correspond et dont la région est absente ou compatible avec l'indice de province ; pour chaque candidat (4 au plus) clique **par libellé**, attend le **changement d'URL**, exige un ID numérique, puis **sonde** `/marketplace/<id>/` (ville affichée par le bouton de lieu, part des cartes dans la province attendue, proximité). `city_verification.decide` tranche (au moins 3 cartes, 70 % dans la province, 50 % à moins de 80 km quand des coordonnées sont connues). Statuts : `VERIFIED`, `AMBIGUOUS`, `INDETERMINATE`, `NOT_FOUND`, plus `LEGACY` (province inconnue : ID non vérifié, la ville est marquée `needsReview`). Seul un ID `VERIFIED` ou `LEGACY` est rendu ; la redirection vers login, captcha ou checkpoint lève `FacebookBlocked` et arrête la série. L'orchestration est séparée de Playwright (`PlaywrightCityDriver`) pour être testée avec un faux pilote.

## Santé des scrapers (`scrape_health.py`)
Fonctions pures. Après chaque scan d'ancrage, `bot._record_scrape_health` classe le résultat puis consulte `should_alert` : 3 échecs de suite, ou au moins 50 % d'échecs sur les 10 derniers scans (6 scans connus au minimum), avec un délai de 6 h entre deux alertes pour une même (source, ville). `geo_mismatch` : au moins 5 cartes dont 90 % ou plus hors liste ; `detail_degraded` : au moins 3 annonces dont la moitié n'a pas de photo. Table `scrape_runs` : voir `donnees.md`.

## LeBonCoin
`LeboncoinScraper` (Playwright « doux », lecture de `__NEXT_DATA__`, pause aléatoire, session réutilisable) n'est importé que par `backend/scripts/leboncoin_probe.py` et `leboncoin_login_once.py` : **pas de scan LeBonCoin dans le bot**. La branche `claude/guitar-hunter-leboncoin-1prbyl` contient une base commune `scraping_common` non fusionnée.

## Pièges et invariants
- Le site change son DOM sans prévenir : les sélecteurs (`a[href*='/marketplace/item/']`, `div[role='main']`, `abbr[aria-label]`, `data-testid`) sont la partie fragile. `scrape_health` sert à le détecter.
- Un identifiant Kijiji reçoit le préfixe `kijiji_` dans `bot.py`, pas dans le scraper.
- Facebook peut dégrader sa page (sans prix ni photos) pour une session anonyme ; `handle_deal_found` n'enregistre pas une annonce vide.
- Les modules qui doivent apparaître dans le LogViewer reçoivent le logger du bot (`logger=`).
- La session Playwright doit toujours être fermée (`close_session`), sinon le permis du sémaphore reste pris côté bot.

## Tests
`backend/scraping/test_*.py` (zone, clustering, catch-up, défilement, boucle de scan, vérification de ville, CityFinder avec faux pilote), `kijiji/test_kijiji_core.py`, `kijiji/test_locations.py`. Aucun test n'exerce Facebook ou Kijiji en réel.
