# API FastAPI — routes, authentification, temps réel, chat (référence)

> Vérifié le 2026-11-06 contre le commit `d9f919e` : `backend/api/main.py` (1 199 lignes, 54 routes), `auth.py`, `db.py`, `deals_repo.py`, `chat_repo.py`, `chat_claude.py`, `restoration_repo.py`, `fiches_repo.py`, `admin_repo.py`, `users_repo.py`, `cities_repo.py`, `commands_repo.py`, `usage_repo.py`, `shared_repo.py`, `logs_repo.py`, `index_version.py`, `model_alerts.py`, `cost_alert.py`, `llm_pricing.py`. Le relevé des routes, des classes Pydantic et des variables d'environnement a été fait par un agent Haiku puis recoupé avec ma lecture du code. Le schéma est dans `donnees.md`, le déploiement en section 9, le client côté navigateur en section 7.

## Rôle

Un service **FastAPI** asynchrone (un seul processus uvicorn, pool asyncpg de 1 à 10 connexions) entre l'application web et Postgres. Il authentifie par jeton Firebase, filtre toutes les données par utilisateur, pousse les changements par WebSocket et fait passer le chat par la clé Anthropic gardée côté serveur. Deux instances tournent sur le serveur : test (racine) et production (`/prod`), derrière Tailscale Funnel.

## Authentification et autorisation
- **HTTP** : en-tête `Authorization: Bearer <jeton Firebase>`. `get_current_uid` vérifie le jeton (`firebase_auth.verify_id_token`, dans un thread car l'appel est bloquant) et renvoie l'uid ; 401 sinon. `get_admin_uid` exige en plus le claim `admin == true` (403 sinon). Les jetons **ne sont pas vérifiés contre la révocation** (`check_revoked` absent).
- **WebSocket** : le navigateur ne peut pas poser d'en-tête, donc le jeton est dans l'URL (`?token=`), vérifié avant l'`accept()` ; invalide = fermeture 1008. La vérification n'a lieu qu'**à la connexion**.
- **Routes publiques** : `GET /health` et `GET /shared-deals/{id}` (page de partage).
- **Isolation** : aucune règle en base. Chaque requête filtre sur `user_id`, ou sur la **visibilité** de l'annonce (`user_deal_matches`) pour le catalogue partagé.
- **CORS** : origines `https://ludoviclebart.github.io` et `http://localhost:5173`, sans cookies, en-tête `Server-Timing` exposé. Un appel hors navigateur n'est pas concerné par CORS.
- Les erreurs non gérées renvoient `500 {"detail": "Erreur interne du serveur."}` en passant par le middleware CORS (sans cela le navigateur ne distingue plus une panne d'un 500). Compression gzip au-delà de 1 000 octets.

## Routes REST

### Utilisateur, commandes, usage, journaux
| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/users/me` | Crée la ligne `users` au premier contact (idempotent) ; sans elle le bot ne démarre pas pour ce compte |
| GET / PATCH | `/users/me/config` | Lit / fusionne (récursivement) la configuration ; corps libre (`extra="allow"`) ; depuis le 2026-11-06 `config_guard.py` refuse (422) une fréquence hors 5 à 1440 min, `max_ads` hors 1 à 500, `distance` hors 0 à 500, des prix hors 0 à 1 000 000, des seuils `proTrigger*` hors bornes, une chaîne de plus de 30 000 caractères ou un corps de plus de 200 Ko ; les autres clés restent libres |
| POST | `/commands` (201) | Ajoute une commande `pending` ; `type` et `payload` libres, le bot rejette les types inconnus ; pour `SCAN_URL`, l'adresse doit être en https sur facebook.com ou kijiji.ca (sinon 422, `backend/url_guard.py`, revérifié par le bot) |
| GET | `/commands/{id}` | État d'une commande de l'appelant (`status`, `error`) |
| POST | `/usage` (204) | Enregistre l'usage d'un tour de chat **Gemini** posté par le navigateur ; bornes 0 à 5 000 000 par compteur, refus des modèles `claude*` (enregistrés par le serveur), déclenche l'alerte de coût |
| GET | `/logs?limit=` (1 à 1 000) | Derniers journaux du bot de l'appelant |

### Annonces
| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/deals` | Liste complète (colonnes lourdes comprises) |
| GET | `/deals/index` | Index léger ; options `status`, `favorite`, `ids=a,b` (200 au plus), `format=columnar\|objects`, `perf=1` (réservé aux administrateurs, ignoré sinon) ; **ETag/304** pour la lecture complète sans filtre |
| POST | `/deals/by-ids` | Documents complets d'une liste d'ids visibles |
| GET | `/deals/{id}` | Une annonce complète |
| PATCH | `/deals/{id}/favorite` | Bascule le favori (personnel) |
| PATCH | `/deals/{id}/reject` | Rejet manuel (personnel) |
| DELETE | `/deals/{id}` (204) | Retire l'annonce **du fil de l'appelant** (l'annonce partagée reste) |
| PATCH | `/deals/{id}/purchased` | Achat **global** ; 428 sans `confirmUnpurchase` pour désacheter ; 409 si un autre utilisateur l'a achetée |
| PATCH | `/deals/{id}/user-sale` | Revente par l'acheteur (409 sinon, prix négatif refusé) |
| PATCH | `/deals/{id}/classification` | Correction manuelle de la classification, **globale** |
| PATCH | `/deals/{id}/analysis-overrides` | Corrige des colonnes d'analyse (liste blanche `AI_ANALYSIS_COLUMNS`), **globale** ; valeurs non validées |
| POST | `/deals/{id}/gallery` | Ajoute une URL de photo à `storage_image_urls`, **globale** ; seule une URL https du stockage Google/Firebase du projet est acceptée (422 sinon, aussi pour `…/chat/{msg}/gallery`) |

### Chat, fiches, plan de restauration
| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/deals/{id}/chat/claude` | Tour de chat sur Claude, flux SSE ; 429 au-delà de 2 $ de dépense du jour par utilisateur (`cost_alert.USER_DAILY_CAP_USD`, administrateur exempté) |
| POST | `/deals/{id}/chat/consult-opus` | Consultation d'Opus sur un dossier rédigé par le modèle, flux SSE |
| GET / POST | `/deals/{id}/chat` | Lit / ajoute un message ; **le fil est commun à tous les utilisateurs qui voient l'annonce** ; `role` limité à `user`/`model`, contenu borné à 2 Mo |
| PATCH | `/deals/{id}/chat/{msg}` | Remplace un message (« Réessayer ») |
| PATCH | `…/chat/{msg}/gallery`, `/restoration-proposal`, `/requalification-proposal` | Marque l'état d'une photo ajoutée, d'une proposition d'étape, d'une requalification |
| GET | `/fiches`, `/fiches/{slug}` | Catalogue et fiche complète |
| POST | `/deals/{id}/fiches/search` | Fiches utiles pour une annonce et la question en cours (`q` ≤ 2 000 caractères, `limit` 1 à 20) |
| GET / POST | `/deals/{id}/restoration-plan` | Étapes de l'appelant / création (fiche liée validée, 422 sinon) |
| PATCH | `…/restoration-plan/order` | Réordonne (déclarée avant `/{item_id}`) |
| PATCH / DELETE | `…/restoration-plan/{item}` | Modifie (sept champs autorisés) / supprime |
| POST / DELETE | `…/restoration-plan/{item}/photos` | Ajoute / retire une URL de photo d'étape |

Accès au **plan** : acheteur de l'annonce, ou utilisateur qui la voit et l'a mise en favori. Accès au **chat** : toute personne qui voit l'annonce.

### Villes, partage, administration
| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/cities` | Catalogue fusionné avec les préférences de l'appelant |
| PATCH | `/cities/{id}/scannable` | Bascule le scan de la ville (crée la préférence) |
| PATCH | `/cities/{id}/kijiji-radius` | Rayon Kijiji par ville ; valeur non bornée |
| DELETE | `/cities/{id}/pref` (204) | Retire la ville de la liste de l'appelant |
| PUT | `/shared-deals/{id}` (204) | Écrit le snapshot public d'une annonce ; **tout utilisateur connecté peut écraser n'importe quel partage** |
| GET | `/shared-deals/{id}` | Lit le snapshot, sans authentification |
| GET | `/admin/users` | Utilisateurs, état du bot, villes, volume et coût estimé sur 24 h glissantes (e-mail et dernière connexion lus dans Firebase) |
| GET | `/admin/chat-cost?days=` | Coût du chat par jour, modèle et utilisateur (1 à 365 jours) |
| POST | `/admin/users/{uid}/pause` (202) | Envoie `STOP_BOT` |
| PATCH | `/admin/users/{uid}/scan-frequency` | Fréquence en minutes (au moins 1) |
| DELETE | `/admin/users/{uid}` (204) | Supprime la ligne `users` (voir `donnees.md`) ; 409 si le bot scanne ou si c'est l'administrateur lui-même |

## Temps réel (WebSocket)
Cinq sockets, chacune avec **sa propre connexion Postgres** (`asyncpg.connect`, hors pool) en `LISTEN` : `/ws/users/me/config`, `/ws/deals`, `/ws/deals/{id}/chat`, `/ws/deals/{id}/restoration-plan`, `/ws/cities`. Canaux et triggers : `donnees.md`. Chaque socket envoie `{"type":"ready"}` une fois le `LISTEN` en place (le client attend ce message). `/ws/deals` regroupe les notifications pendant 250 ms, ne pousse que les annonces visibles pour l'utilisateur, et envoie un seul `{"type":"bulk"}` au-delà de 50 ; la perte de la connexion `LISTEN` ferme le socket (code 1011) pour forcer une reconnexion et une relecture complète.

## Index des annonces et ETag
`index_version.py` tient un compteur incrémenté à chaque notification `deal_changes` ou `restoration_plan_changes` sur une connexion `LISTEN` dédiée de l'API. Il sert d'ETag faible, propre à l'utilisateur (empreinte de l'uid), à la variante de format et à la tranche d'une heure. Aucun ETag n'est émis tant que l'écoute n'est pas établie. La sérialisation (orjson, repli `jsonable_encoder` ; gzip niveau 4) se fait **hors de la boucle d'événements**.

## Chat sur Claude (`chat_claude.py`)
Le navigateur envoie la conversation déjà au format Anthropic (système, outils, messages). Le serveur la **valide** (modèle autorisé : `claude-sonnet-5-5` seul ; système ≤ 40 000 caractères ; ≤ 8 outils ; ≤ 400 messages ; ≤ 40 images de 6 M caractères base64 au plus, 30 M au total ; ≤ 400 000 caractères de texte ; types de blocs et d'images limités), appelle l'API avec l'effort de raisonnement `CHAT_CLAUDE_EFFORT` (défaut `medium`), `CHAT_CLAUDE_MAX_TOKENS` (8 000) et 240 s, avec **cache de prompt** sur le système et le dernier bloc, et renvoie des événements SSE (`text`, `final`, `error`, commentaires de maintien de connexion toutes les 15 s). L'usage est enregistré par le serveur dans `llm_usage` (succès comme échec, usage partiel en cas d'annulation) puis l'alerte de coût est vérifiée. Le navigateur qui part annule la génération. Erreurs : clé absente (424, jamais réessayé), crédit épuisé (402), autres avec le code HTTP.
**Consultation d'Opus** : dossier de 14 000 caractères au plus rédigé par Sonnet, 2 images, aucun outil, consigne système fixée, 4 000 tokens (`CHAT_OPUS_MAX_TOKENS`).

## Alertes et coûts
- `model_alerts.py` : ntfy quand un modèle est injoignable. Causes à traiter (clé absente, crédit épuisé, clé refusée, modèle introuvable) : une fois par jour et par (fournisseur, modèle, cause). Pannes passagères (timeout, 429, 5xx, connexion) : 5 échecs en 15 minutes, une fois par heure. État en mémoire ; appelée par le bot, le chat Claude et `POST /usage`.
- `cost_alert.py` : ntfy quand le coût **du chat** du jour dépasse 2 $ (`DAILY_ALERT_USD`), une fois par jour et par processus ; jamais bloquant. Les coûts du bot (Portier, Analyste, Expert) n'entrent pas dans cette alerte.
- `llm_pricing.py` : tarifs par million de tokens pour `gemini-3.1-pro-preview`, `claude-sonnet-5-5`, `claude-opus-5-5` ; un modèle sans tarif est compté au tarif le plus haut.

## Variables d'environnement
`DATABASE_URL` (défaut `postgresql://guitarhunter@localhost/guitarhunter`), `FIREBASE_KEY_PATH`, `ANTHROPIC_API_KEY`, `NTFY_TOPIC`, `CHAT_CLAUDE_MAX_TOKENS` / `_EFFORT` / `_TIMEOUT_SECONDS`, `CHAT_OPUS_MAX_TOKENS` / `_EFFORT`. `model_alerts` lit aussi `PYTEST_CURRENT_TEST` et `MODEL_ALERTS_TEST` pour ne rien envoyer pendant les tests.

## Cycle de vie
Au démarrage : pool Postgres (qui joue `schema.sql`) puis tâche d'écoute `index_version`. À l'arrêt : annulation, fermeture du pool.

## Pièges et invariants
- **L'API de production n'est pas le dépôt entier** : tout module importé par `backend/api/*.py` doit figurer dans la liste copiée par `deploy.yml` (`__init__.py`, `deal_mapping.py`, `funnel_cost.py`, `guitar_knowledge.py`). Garde-fou : `backend/api/test_prod_sync.py` (passe au 2026-11-06).
- Routes statiques déclarées **avant** les routes dynamiques (`/deals/index`, `/restoration-plan/order`).
- Un seul processus : tout calcul lourd (sérialisation, gzip, vérification de jeton) passe par `asyncio.to_thread`.
- `PATCH /deals/{id}/…` sur une annonce partagée (classification, analyse, galerie, achat) agit sur la ligne **commune** : voir `donnees.md` et les constats de section 6.
- Une connexion Postgres par socket : `max_connections` doit couvrir (sockets × 2 instances) + pools du bot et de l'API.

## Tests
`backend/api/test_*.py` : `test_api`, `test_users_api`, `test_deals_api`, `test_chat_api`, `test_chat_claude`, `test_cities_api`, `test_fiches_api`, `test_restoration_api`, `test_shared_deals_api`, `test_admin_api`, `test_logs_api`, `test_index_serialization`, `test_perf_diagnostic`, `test_model_alerts`, `test_prod_sync`. Ceux qui exigent Postgres se sautent sans base jetable.
