# Plan — Remplacement de Firestore par une solution auto-hébergée

## Contexte

Déclenché par l'analyse des factures GeminiDev (août puis septembre 2026, voir `JOURNAL.md`) : Firestore représente ~16-20% de la facture mensuelle (16,16$ en août sur 102,57$ total, 2,36$ sur 12,12$ en septembre partiel) — pas le poste dominant (Gemini API ~80-85%), mais pas négligeable, avec une tendance à la hausse sur les lectures/écritures (+41%/+74% Reads/Writes en septembre vs période équivalente d'août).

L'utilisateur a un serveur déjà en marche 24/24 pour le bot Python (`guitare-hunter`, systemd) et est prêt à abandonner GitHub Pages pour le frontend — les deux objections initiales (besoin d'un serveur en plus, frontend statique nécessitant un backend temps réel externe) ne tiennent donc plus. **Firebase Auth et Firebase Storage restent inchangés** (coût négligeable, pas de raison de les migrer).

Plan sommaire validé par l'utilisateur avant tout code (protocole du projet) — ce document sert de mémoire du chantier, pas encore d'implémentation.

---

## 1. Stack retenue

- **Base de données : PostgreSQL** (pas SQLite) — le nouveau serveur API/WS et le bot Python écriront concurremment (scans, commandes, chat, plan de restauration) ; SQLite gère mal l'écriture concurrente multi-process, Postgres non. S'installe directement sur le serveur existant.
- **Temps réel : Postgres `LISTEN/NOTIFY` + WebSocket (FastAPI)** — le bot notifie Postgres après chaque écriture (`NOTIFY deal_changed, '<user_id>:<deal_id>'`), le serveur API (qui tient les connexions WebSocket) écoute ces canaux et repousse la mise à jour au(x) client(s) concerné(s). Reproduit le découplage actuel bot↔Firestore↔frontend sans dépendance supplémentaire (pas de Redis).
- **Auth inchangée** : le frontend garde Firebase Auth. Chaque requête HTTP/WS porte le ID token Firebase, vérifié côté serveur via `firebase-admin` (déjà une dépendance backend) pour en tirer le `uid`. L'autorisation par ligne (`WHERE user_id = uid`) remplace les Firestore Security Rules.

## 2. Schéma Postgres (mapping des collections actuelles)

| Table | Remplace | Note |
|---|---|---|
| `users` | doc `users/{uid}` | `uid` PK, `bot_status`, `config` JSONB (scanConfig, prompts persos, uiFilters) |
| `guitar_deals` | `guitar_deals/{id}` **+ `deals_index`** | colonnes indexées natives pour tout ce que `deals_index` bricolait (status, verdict, price, timestamp, classification, is_favorite, is_purchased, les 5 scores, brand/model/color, lat/lng) + JSONB `ai_analysis_raw` pour le reste (reasoning, etc.). **`deals_index` et son sharding en 20 chunks disparaissent** — un index SQL fait ce travail nativement. |
| `deal_chat` | sous-collection `chat` | FK → `guitar_deals`, colonnes `role`, `parts` JSONB, `display_text`, `restoration_proposals` JSONB, etc. |
| `restoration_plan_items` | sous-collection `restorationPlan` | FK → `guitar_deals`, mêmes champs (label, category, status, coûts, order, photoUrls) |
| `commands` | collection `commands` | peut disparaître complètement : frontend et backend parlant au même serveur API, une commande devient un appel HTTP synchrone au lieu d'un document écrit-puis-écouté |
| `logs` | sous-collection `logs` | + job cron `DELETE ... WHERE created_at < now() - interval` en remplacement de la TTL policy Firestore |
| `cities` / `user_city_prefs` | collections `cities` | directes |
| `shared_deals` | collection publique | table à part, exposée via une route HTTP publique sans auth (équivalent `allow read: if true`) |

## 3. API/WS à construire

Service Python (FastAPI + `websockets`) sur le même serveur :
- Endpoints REST pour l'ensemble des fonctions actuellement dans `firestoreService.js` (~35 fonctions : CRUD deals/chat/restorationPlan/cities, favoris, achat, classification manuelle, overrides d'analyse...).
- Canaux WebSocket par utilisateur (remplace `onBotConfigUpdate`, `onDealsIndexUpdate`, `onCitiesUpdate`) et par annonce (remplace `onDealChatUpdate`, `onRestorationPlanUpdate`).
- `backend/database.py`/`repository.py` : Admin SDK Firestore → requêtes SQL (`asyncpg`/SQLAlchemy). Le bot Python parle à Postgres directement.

## 4. Déploiement (fin de GitHub Pages)

- nginx (ou Caddy) devant le serveur : sert `dist/` (build frontend) en statique + reverse-proxy vers le service API/WS.
- TLS via Let's Encrypt/Caddy automatique.
- `deploy.yml` : le job `deploy-frontend` (actuellement build + push `gh-pages`) devient un `scp`/`rsync` de `dist/` vers le serveur, dans le même job SSH que `deploy` (backend).
- Nouveau service systemd pour l'API/WS, à côté de `guitare-hunter`.

## 5. Migration & bascule

1. Construire sur une branche séparée, sans toucher au chemin Firestore existant.
2. Script d'export ponctuel Firestore → Postgres (même famille que `rebuild_index.py`/`run_once.py`).
3. Fenêtre de bascule : arrêt bref du bot + gel des écritures frontend, export final incrémental, bascule des URLs (frontend → nouveau serveur, bot → Postgres), vérification.
4. Filet de sécurité : garder Firestore intact (lecture seule) quelques jours avant suppression définitive, pour un rollback rapide si besoin.

## 6. Points ouverts à trancher avant tout code

- ✅ **Accessibilité publique du serveur — tranché (2026-09-09) : Tailscale Funnel.** Cohérent avec l'infra déjà utilisée pour le déploiement CI (`deploy.yml` s'y connecte déjà pour le SSH), pas de nouvel outil à intégrer.
- **Sauvegardes** : Firestore est managé/répliqué automatiquement ; Postgres sur un seul serveur ne l'est pas — prévoir un `pg_dump` planifié + stockage externe des backups (le serveur devient un point de défaillance unique pour les données ET le site). Toujours ouvert.
- **Tolérance à la coupure** pendant la fenêtre de bascule. Toujours ouvert.

## 7. Hors périmètre de ce plan

- Optimisation des photos envoyées à Gemini (Tier 2/3, redimensionnement 2048px → ciblage de zones détaillées) — sujet séparé, déjà identifié dans l'analyse de coûts.
- Migration du SDK `google.generativeai` → `google-genai` (`TODO.md`, dette technique existante).

## 8. Avancement (mis à jour 2026-09-09)

**Stratégie de bascule précisée avec l'utilisateur** : construction tranche par tranche (comme prévu ci-dessus), mais la bascule en production de toutes les tranches se fait **en une seule fois**, une fois la parité fonctionnelle complète validée — pas de mise en production progressive tranche par tranche. Firestore reste l'unique source de vérité en production jusqu'à ce moment.

**Branche dédiée** : `claude/firestore-postgres-migration` (base `dev`) — construite en isolation complète, aucun code de production (Firestore, frontend, bot) modifié à ce stade.

**Tranche 1 — bus de commandes : codée et validée en conditions réelles.**
- `backend/api/schema.sql` : schéma Postgres complet (les 9 tables de §2), idempotent.
- `backend/api/db.py`, `backend/api/auth.py` : pool `asyncpg` + vérification du ID token Firebase (dépendance FastAPI).
- `backend/api/commands_repo.py` + `backend/api/main.py` : `POST /commands`/`GET /commands/{id}`, même contrat que `firestoreService.js::addCommand()`. Le bot lira directement Postgres en SQL (pas via cette API) une fois la bascule décidée, conforme à §3.
- **Testé pour de vrai** (`backend/api/test_api.py`, 4 tests contre un Postgres local réel, pas des mocks) : round-trip création/lecture, payload objet, isolation multi-tenant, lecture "côté bot" de ce que l'API a écrit.

**Tranche 2 — `guitar_deals` + canal WebSocket temps réel : codée et validée en conditions réelles.**
- `backend/api/deals_repo.py` : list/get/by-ids/favori/achat/classification manuelle/reject/delete. Simplification vs `firestoreService.js` actuel : une seule écriture par mutation (colonnes indexées nativement) contre deux aujourd'hui (document + `deals_index`).
- `schema.sql` : trigger `notify_deal_change` sur `guitar_deals`, remplace `onDealsIndexUpdate` — notifie sur toute écriture, bot en SQL direct comme cette API, sans dupliquer de `NOTIFY` manuel par site d'écriture.
- `main.py` : endpoints REST `/deals/...` + WebSocket `/ws/deals` (canal `LISTEN` partagé, filtré côté serveur par `user_id`, token Firebase en paramètre de requête).
- **Bug réel trouvé et corrigé par les tests** : condition de course entre `websocket.accept()` et l'enregistrement effectif du `LISTEN` juste après — une notification émise dans cette fenêtre se serait perdue silencieusement (Postgres ne rejoue jamais les `NOTIFY` manqués). Corrigé par un accusé de réception explicite (`{"type": "ready"}`) que le client attend avant de compter sur le canal.
- Outillage : le `TestClient` Starlette ne délivre pas fiablement un message envoyé depuis une tâche créée hors du flot requête/réponse direct — un vrai serveur `uvicorn` + client `websockets` réel ont été nécessaires pour tester le canal correctement (`backend/api/test_deals_api.py::TestDealsWebSocket`).
- 11 tests d'intégration au total (Postgres local réel, pas de mocks).

**Reste à faire** : tranches `deal_chat`, `restoration_plan_items`, `cities`/`user_city_prefs`, `shared_deals`, avant toute décision de bascule réelle (§5.3).
