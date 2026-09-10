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

**Tranche 3 — `deal_chat` + canal WebSocket temps réel : codée et validée en conditions réelles.**
- `backend/api/chat_repo.py` : CRUD messages, marquage galerie, statut proposition de restauration/requalification. `deal_chat` n'a pas de `user_id` propre (seulement une FK vers `guitar_deals`) — `get_deal_owner()` vérifie la propriété du deal parent avant d'exposer/modifier son chat, réutilisé par le REST et le WebSocket.
- `schema.sql` : trigger `notify_chat_change` sur `deal_chat`, canal `chat_changes` séparé de `deal_changes`, filtré côté serveur par `deal_id` (pas par `user_id`, cohérent avec l'absence de cette colonne sur la table).
- `main.py` : endpoints REST `/deals/{id}/chat...` (mêmes contrats que `firestoreService.js::addDealChatMessage`/`replaceDealChatMessage`/`markChatMessage*`) + WebSocket `/ws/deals/{id}/chat`, remplace `onDealChatUpdate`. Même pattern anti-course que la tranche 2 (`{"type": "ready"}` après `add_listener()`), avec la vérification de propriété faite **avant** `accept()` cette fois (dépend uniquement du `deal_id` de l'URL, pas d'un filtrage a posteriori sur canal partagé).
- **Piège de migration réel trouvé** (pas propre à cette tranche, mais découvert en l'écrivant) : `CREATE TABLE IF NOT EXISTS` ne modifie jamais une table déjà créée par une tranche précédente — les nouvelles colonnes de `deal_chat` n'étaient silencieusement jamais appliquées sur une base déjà initialisée. Corrigé en restructurant `schema.sql` avec des `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` séparés pour toute colonne ajoutée après la création initiale d'une table (règle documentée en commentaire dans le fichier pour la suite).
- **Bug latent plus ancien découvert par cette tranche** (présent depuis la tranche 1, jamais détecté avant faute de test sur une structure JSONB imbriquée) : asyncpg ne décodait jamais nativement les colonnes JSON/JSONB (chaînes brutes au lieu de dict/list Python). Corrigé une fois pour toutes via `db.py::_register_json_codecs()` (`set_type_codec` sur `jsonb`/`json`, appliqué à chaque connexion du pool), avec retrait des `json.dumps()` manuels devenus redondants/nuisibles dans `commands_repo.py` et `chat_repo.py`.
- 17 tests d'intégration au total (Postgres local réel, pas de mocks) — 6 nouveaux pour cette tranche.

**Tranche 4 — `restoration_plan_items` + canal WebSocket temps réel : codée et validée en conditions réelles.**
- `backend/api/restoration_repo.py` : CRUD étapes, réordonnancement batché en un seul aller-retour SQL (`unnest()`) réutilisé pour le glisser-déposer manuel, une proposition IA appliquée, et le rattrapage silencieux (3 usages Firestore distincts, une seule fonction ici), photos par étape (équivalents `arrayUnion`/`arrayRemove` en JSONB).
- `schema.sql` : trigger `notify_restoration_plan_change`, canal `restoration_plan_changes` filtré par `deal_id` — couvre aussi `DELETE` (contrairement à `deal_changes`/`chat_changes`), la suppression d'étape étant une action réelle exposée par cette tranche.
- `main.py` : endpoints REST `/deals/{id}/restoration-plan...` + WebSocket `/ws/deals/{id}/restoration-plan`, remplace `onRestorationPlanUpdate`. Même vérification de propriété que la tranche 3 (`chat_repo.get_deal_owner`, réutilisée telle quelle).
- **Défaut de conception initiale corrigé** : les colonnes `cost_low`/`cost_high` du tout premier jet de `schema.sql` (§2, écrit avant la lecture complète du contrat réel dans `firestoreService.js`) ne correspondaient à aucun champ réellement utilisé — retirées, remplacées par les vrais champs (`estimated_cost`/`actual_cost`/`notes`/`source`/`proposed_by_message_id`).
- **Variante du piège de migration de la tranche 3** : `status` existait déjà (sans défaut) dans la table créée par une exécution précédente de `schema.sql` — un `ADD COLUMN IF NOT EXISTS` est un no-op sur une colonne déjà présente, contrairement à une colonne réellement absente. Corrigé par un `ALTER COLUMN SET DEFAULT` + backfill + `SET NOT NULL` explicites.
- **Bug de routage FastAPI trouvé et corrigé par les tests** : `PATCH /restoration-plan/order` était intercepté par la route `PATCH /restoration-plan/{item_id}` déclarée avant elle (Starlette matche dans l'ordre de déclaration, `"order"` échouait la validation `int` → 422). Corrigé en déclarant la route littérale avant la route paramétrée.
- 25 tests d'intégration au total (Postgres local réel, pas de mocks) — 8 nouveaux pour cette tranche.

**Tranche 5 — `cities`/`user_city_prefs` + canal WebSocket temps réel : codée et validée en conditions réelles.**
- `backend/api/cities_repo.py` : liste fusionnée catalogue partagé + préférences utilisateur (LEFT JOIN, remplace les deux `onSnapshot` d'`onCitiesUpdate`), toggle scannable, réglage/effacement du rayon Kijiji, suppression de préférence.
- **Périmètre volontairement limité** à ce que le frontend consomme aujourd'hui : l'écriture du catalogue partagé (`cities`) reste faite par `bot.py::add_city_auto()` côté Firestore jusqu'à la bascule (conforme à §5.1 — ne pas toucher au chemin Firestore existant), et l'ajout de ville passe déjà par la commande `ADD_CITY` (tranche 1) — rien de plus à construire ici pour ce chemin.
- **Bug de sémantique trouvé et corrigé avant même d'écrire les tests** (relecture attentive du contrat Firestore) : le tout premier jet de `schema.sql` posait `active DEFAULT true` sur `user_city_prefs` — aurait implicitement activé le scan d'une ville dès qu'un utilisateur y règle seulement un rayon Kijiji (`setCityKijijiRadius`, `merge: true` côté Firestore, qui ne touche jamais `isScannable`). Corrigé en `DEFAULT false` (absence de ligne de préférence == non scannable, comme `isScannable ?? false` côté `onCitiesUpdate`), vérifié par un test dédié plutôt que laissé au seul raisonnement.
- `main.py` : endpoints REST `/cities...` + WebSocket `/ws/cities`. **Simplification assumée** vs les tranches précédentes : pousse un signal léger (`cityId` concerné) plutôt que la ligne fusionnée complète — le calcul catalogue+prefs reste dans la requête SQL, pas dupliqué dans le trigger Postgres.
- 32 tests d'intégration au total (Postgres local réel, pas de mocks) — 7 nouveaux pour cette tranche.

**Tranche 6 (dernière) — `shared_deals` : codée et validée en conditions réelles.**
- `backend/api/shared_repo.py` : upsert (remplacement complet du snapshot, jamais un merge — même sémantique que le `setDoc` de `createSharedDeal`) + lecture.
- **Pas de canal WebSocket** : `SharedDealPage` fait un `getDoc` ponctuel côté Firestore, jamais un `onSnapshot` — rien à répliquer ici, contrairement à toutes les tranches précédentes.
- **Correction de schéma trouvée par relecture du contrat réel** : les colonnes `deal_id`/`user_id` du premier jet de `schema.sql` (§2) ne correspondaient à rien de réel — `createSharedDeal` utilise l'id du deal LUI-MÊME comme id de document (pas un id de partage séparé) et n'écrit aucun `user_id` (écriture ouverte à tout utilisateur authentifié, pas réservée au propriétaire du deal — vérifié dans `firestore.rules`). Colonnes retirées, table réduite à `(id, snapshot, created_at)`.
- `main.py` : `GET /shared-deals/{id}` public (équivalent `allow read: if true`), `PUT /shared-deals/{id}` réservé à un utilisateur authentifié quelconque (équivalent `allow write: if request.auth != null`).
- 36 tests d'intégration au total (Postgres local réel, pas de mocks) — 4 nouveaux pour cette tranche.

**Bilan de la construction (2026-09-09)** : les 6 tranches prévues (`commands`, `guitar_deals`, `deal_chat`, `restoration_plan_items`, `cities`/`user_city_prefs`, `shared_deals`) sont désormais codées et testées en conditions réelles — 36 tests au total, aucun mock, contre un vrai Postgres local. Toujours rien de branché à la production (Firestore reste l'unique source de vérité, conforme à la stratégie actée avec l'utilisateur).

**Point 2 avancé (2026-09-10)** : plutôt qu'un vrai système de double-écriture en parallèle (bot → Firestore + Postgres en continu, jugé disproportionné vu la stratégie "bascule en une seule fois" déjà actée et l'échelle du projet), décision prise avec l'utilisateur de construire un script d'export ponctuel + un script de comparaison, pour un dry-run de migration sans toucher au bot/frontend :
- `backend/scripts/export_firestore_to_postgres.py` : lecture seule Firestore → écriture idempotente Postgres, couvre tout sauf `commands`/`logs` (transitoires). Détails complets, limitations connues (id `itemId` non retraduit dans les propositions de chat déjà traitées, cosmétique) et bug réel trouvé (`is_favorite`/`is_purchased` NOT NULL) dans `JOURNAL.md` [2026-09-10].
- `backend/scripts/compare_firestore_postgres.py` : comptages + échantillon comparé champ par champ, pour vérifier une copie après coup.
- 24 tests (19 purs + 5 d'intégration contre un vrai Postgres local, Firestore simulé faute d'accès réel depuis cette session) — tous verts, aucune régression sur les 39 tests existants.
- **Jamais exécuté pour de vrai** : cette session n'a aucun credential Firebase — le dry-run réel doit être lancé depuis le serveur contre un Postgres de staging, reste à faire.

**Reste à faire avant toute mise en production** — hors de ce chantier de construction, jamais entamé sans décision explicite de l'utilisateur (§5.3) :
1. Décider et documenter le protocole de bascule réelle (ordre des étapes, fenêtre de maintenance ou non, plan de rollback).
2. Lancer le dry-run réel (`export_firestore_to_postgres.py` puis `compare_firestore_postgres.py`, depuis le serveur, contre un Postgres de staging) — scripts prêts (voir ci-dessus), jamais exécutés contre de vraies données.
3. Basculer le bot (`backend/bot.py` et modules associés) vers un accès SQL direct — actuellement hors périmètre : le bot continue d'écrire sur Firestore, y compris pour les tables déjà migrées côté API (ex: `cities` reste écrit par `add_city_auto()` côté Firestore, voir tranche 5).
4. Basculer le frontend (`src/services/firestoreService.js` → nouvelle API HTTP/WebSocket).
5. Déployer le service réseau (Tailscale Funnel, décidé le 2026-09-09, non encore mis en place).
