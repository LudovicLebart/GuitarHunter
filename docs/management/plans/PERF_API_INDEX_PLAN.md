# Plan — lenteur de chargement et erreurs « GET /deals/index a expiré après 20000ms »

Créé le 2026-11-03. Diagnostic mesuré sur le serveur + relecture Opus. **Palier 1 codé le 2026-11-03, NON déployé et NON validé par l'utilisateur** : journal, TODO et ARCHITECTURE ne sont à mettre à jour qu'après sa validation (protocole `CLAUDE.md`, étape 3).

## Mesures (serveur ThinkCentre M720q, API prod = 1 seul processus uvicorn)

- `/deals/index` : 8 444 annonces, 16,5 Mo brut, 2,4 Mo gzippé.
- Coût par requête : SQL 0,41 s (tri externe sur disque) + décodage asyncpg ; `jsonable_encoder` 0,95 s ; `json.dumps` 0,13 s ; gzip niveau 9 0,40 s. ≈ 1,5 s de CPU Python **sur la boucle d'événements**.
- 1 requête : première réponse à 2,0 s. 3 requêtes simultanées : 3,1 / 4,4 / 4,7 s, et `/health` (1 ms au repos) figé ≈ 1,1 s à chaque passage.
- `verify_token` (Firebase, synchrone, récupération réseau des certificats Google) appelé sur la boucle à chaque requête et connexion WS.
- Le serveur envoie déjà l'id modifié par WS, mais le client relit tout l'index à chaque notification.
- Un push sur `dev` redéploie et redémarre aussi l'API de production.
- 1,5 s/requête n'explique pas 20 s sans réponse : pistes restantes = socket mort après veille du téléphone, redémarrage + afflux, chemin Funnel. À mesurer (sonde `/health` 1 h, `?perf=1` sur téléphone, curl Funnel en 4G).

## Palier 1 (fait, à déployer)

- `auth.py` / `main.py` : `verify_token` et `verify_token_claims` via `asyncio.to_thread` (HTTP et 5 WebSocket).
- `main.py::encode_rows_json` / `rows_json_response` : `orjson` (repli `jsonable_encoder` si absent OU si orjson refuse une valeur) + gzip niveau 4, exécutés en thread ; `Content-Encoding` posé par le handler. Appliqué à `/deals/index`, `/deals/by-ids` et `/deals` ; `?perf=1` mesure le même chemin.
- `deals_repo.list_deals_index` : plus d'`ORDER BY` (le client retrie tout).
- WebSocket : `ready` dans le `try`, `OSError` (`ClientDisconnected` d'uvicorn) traité comme une déconnexion.
- Client : relance de la lecture de l'index avec attente croissante (`src/utils/retryBackoff.js`) ; 1er échec silencieux, pas d'erreur si la page est cachée ; pas de relance sur un 4xx (hors 408/429) ni au-delà de 10 échecs consécutifs ; toute nouvelle lecture annule la relance en attente.
- Tests : `backend/api/test_index_serialization.py` (parité orjson/jsonable_encoder, repli, gzip, routes via TestClient, ClientDisconnected, boucle non bloquée), `src/utils/retryBackoff.test.js`.
- Ordre : `ORDER BY` retiré de l'index ; vérifié que `useDealsManager.js` retrie dans tous les modes (date, intérêt, publication, vente).
- **Critères** : `/health` < 100 ms pendant 3 index simultanés ; première réponse < 0,8 s (1 requête) ; aucun écran vide qui ne se répare pas seul en < 30 s ; lignes d'erreur WS /10 sur 24 h.
- `orjson` ajouté à `requirements.txt` ; le venv de prod est celui de `~/GuitareHunter` (installé par le déploiement).

## Palier 2 (volume) — synchronisation incrémentale codée 2026-11-03, NON déployée ni validée

- **Fait** : `GET /deals/index?ids=a,b,c` (≤ 200 ids, jointure de visibilité conservée) ; client (`utils/indexDelta.js`, `onDealsIndexUpdate`) : notification `{id}` → lecture incrémentale ; relecture complète sur `bulk`, reconnexion, retour > 30 s, échec, > 50 ids, et toutes les 10 min (page visible). Tests : `test_index_serialization.py`, `indexDelta.test.js`.
- **Reste** : triggers NOTIFY (DELETE, `restoration_plan_items`) ; IndexedDB ; déploiement de l'API de production sur `master` seulement (`deploy.yml`, à confirmer).

- Le client demande seulement les annonces modifiées (`GET /deals/index?ids=`), fusionne, retire les ids absents ; relecture complète seulement sur `bulk`, après reconnexion, ou retour > 30 s.
- Trou existant : pas de NOTIFY sur DELETE ni sur `restoration_plan_items` → triggers ou relecture complète périodique (10 min).
- Dernier index conservé dans IndexedDB (affichage immédiat, revalidation en arrière-plan).
- Ne déployer l'API de production que sur `master` (modification de `deploy.yml`, à confirmer).
- **Critère** : relectures complètes ≈ 200/jour → < 30.

## Palier 3 (si nécessaire)

- Index plus léger (≈ 55 clés répétées par ligne), format colonne, ETag/304, cache serveur par utilisateur invalidé par NOTIFY.
- `--workers 2` seulement si le palier 1 ne suffit pas : alertes ntfy dédoublonnées par processus (`model_alerts._last_sent`, `cost_alert._alerted_on`), fichier systemd de prod installé à la main, `max_connections` Postgres (1 LISTEN hors pool par socket + 10 par pool et par worker).
