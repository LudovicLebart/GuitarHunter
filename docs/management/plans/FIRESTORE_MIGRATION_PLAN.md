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

- **Accessibilité publique du serveur** : IP fixe/port forwarding possible sur 80/443 avec un nom de domaine, ou serveur derrière un NAT sans IP publique (auquel cas un tunnel type Cloudflare Tunnel/Tailscale Funnel serait nécessaire en plus) ? Conditionne toute la partie déploiement frontend.
- **Sauvegardes** : Firestore est managé/répliqué automatiquement ; Postgres sur un seul serveur ne l'est pas — prévoir un `pg_dump` planifié + stockage externe des backups (le serveur devient un point de défaillance unique pour les données ET le site).
- **Tolérance à la coupure** pendant la fenêtre de bascule.

## 7. Hors périmètre de ce plan

- Optimisation des photos envoyées à Gemini (Tier 2/3, redimensionnement 2048px → ciblage de zones détaillées) — sujet séparé, déjà identifié dans l'analyse de coûts.
- Migration du SDK `google.generativeai` → `google-genai` (`TODO.md`, dette technique existante).

## 8. Non fait à ce stade

Aucun code écrit. Ce document est le seul livrable de ce chantier pour l'instant — prochaine étape à définir avec l'utilisateur (probablement : trancher le point 6 accessibilité réseau, puis détailler l'implémentation par tranche verticale).
