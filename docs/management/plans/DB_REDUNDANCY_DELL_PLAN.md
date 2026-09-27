# Plan — Redondance serveur sur le Dell T5810 (cluster MoneyBot)

> Statut (2026-09-27) : **préparation**. Socle HA codé et poussé (`claude/db-redundancy-dell-5810-mvzv2j`),
> rien encore déployé sur une machine réelle. Voir `TODO.md` § Infrastructure pour la checklist à jour.

## 0. Contexte et origine

Chantier ouvert le 2026-09-06 (`TODO.md`) suite à un échec du job `deploy.yml` — timeout SSH vers
le serveur de production, serveur injoignable sur le tailnet, redémarré manuellement. Le Lenovo
ThinkCentre M720q (serveur de production actuel) est un point de défaillance unique : s'il tombe,
`deploy.yml` échoue ET le bot est down jusqu'à intervention manuelle.

Explicitement reporté le 2026-09-19 (décision actée avec l'utilisateur) jusqu'à la fin de la
bascule Firestore→Postgres, pour ne pas mélanger deux chantiers d'infra à risque. Cette bascule
est close depuis Phase B.5 (voir `TODO.md`, `CUTOVER_RUNBOOK.md`) — ce chantier reprend le
2026-09-27.

## 1. Périmètre (décidé avec l'utilisateur, 2026-09-27)

- **Redondance Postgres + bot/API**, pas seulement la base : le Dell doit pouvoir reprendre le
  service complet, pas seulement garder une copie des données.
- **Bascule automatique** (pas un runbook manuel) : un mécanisme détecte la panne et bascule seul.
- **Accord MoneyBot déjà obtenu** pour ce niveau de partage du Dell (au-delà de l'usage GPU déjà
  validé pour l'inférence vision, `NECK_RESET_VISION_PLAN.md`).

## 2. Le problème du split-brain (2 machines, sans quorum tiers)

Un health-check mutuel entre seulement 2 machines résidentielles est structurellement ambigu :
en cas de coupure réseau *entre elles* (pas forcément une vraie panne), chacune peut croire
l'autre morte et se promouvoir en même temps → scraping en double, notifications en double,
écritures Postgres potentiellement divergentes.

**Décision (discussion avec l'utilisateur)** : un arbitre EXTERNE aux deux machines est
nécessaire pour trancher. Retenu : un **bail de leadership Firestore** (`system_ha/leader`,
`backend/ha/lease.py`) — indépendant de Tailscale/SSH entre les deux machines, déjà dans l'infra
du projet, et une transaction Firestore garantit qu'une seule des deux tentatives concurrentes
peut gagner.

En complément, l'utilisateur a demandé 2 checks mutuels explicites, utilisés comme **garde-fou
secondaire** (pas comme mécanisme principal — le bail Firestore reste la seule source de vérité
pour "qui est primaire") :
1. L'autre machine est-elle allumée/joignable sur le tailnet ?
2. Son service est-il rapporté actif (surtout après un redémarrage du PC ou du service) ?

Si les deux sont vrais malgré un bail Firestore expiré, c'est un signal de bug de renouvellement
côté nœud actif plutôt qu'une vraie panne — pas de bascule automatique dans ce cas, alerte à la
place.

## 3. Design retenu

### 3.1 Le bail (`backend/ha/lease.py`)
Document unique `system_ha/leader` = `{host, heartbeat_at, expires_at}`. Le nœud actif le
renouvelle en continu (`acquire_or_renew`, transactionnel). Un nœud standby ne tente de le
prendre que si `expires_at` est dépassé.

### 3.2 Séquence de bascule (`backend/ha/watchdog.py::_attempt_failover`)
1. Bail lu comme expiré pendant `failover_confirm_rounds` tours consécutifs (évite de basculer
   sur un simple pic de latence Firestore).
2. Check mutuel (`health.py`) : si le pair répond ET son service est actif → PAS de bascule,
   alerte ntfy à la place.
3. **Le bail est pris AVANT le fencing** (ordre corrigé en revue de code, voir §5) —
   `acquire_or_renew()`. Si un autre nœud l'a déjà pris entre-temps, abandon sans avoir touché
   au service du pair.
4. Fencing : arrêt actif du service du pair via SSH (`stop_peer_service`) — réduit, sans
   l'éliminer complètement, le risque de split-brain si le pair redevient joignable juste après.
5. `pg_promote()` sur la réplique Postgres locale.
6. Démarrage du service applicatif local (bot + API).
7. Notification ntfy.sh (urgente).

Un échec aux étapes 5-6 (après prise du bail à l'étape 3) libère le bail (`lease.release()`) et
alerte, plutôt que de laisser le nœud se croire indéfiniment primaire sans service réel.

### 3.3 Traçabilité (`scraped_by_node`)
Chaque annonce scrapée porte désormais le nœud qui l'a traitée (`guitar_deals.scraped_by_node`,
posé par `bot.py::handle_deal_found` si `config.HA_NODE_ID` est configuré) — sert au diagnostic
si les deux nœuds tournaient par erreur en même temps, pas un mécanisme de verrouillage en soi
(c'est le rôle du bail).

### 3.4 Retour à la normale
**Manuel, volontairement** — le Lenovo réparé ne reprend pas le bail automatiquement, pour éviter
un aller-retour incontrôlé entre les deux machines. Runbook à écrire (§6), sur le modèle de
`CUTOVER_RUNBOOK.md`.

## 4. Prérequis d'infrastructure (pas encore faits)

- Réplication Postgres physique WAL (`guitarhunter_pg_prod` → réplique standby sur le Dell,
  `guitarhunter_pg_dell`).
- Dépendances Python/Playwright installées en continu sur le Dell, distinctes de l'environnement
  MoneyBot (même logique que `run_script_dell.yml` : répertoire dédié, jamais `~/MoneyBot`).
- Unités systemd standby (`guitare-hunter-dell`/`guitarhunter-api-dell`), arrêtées par défaut.
- **Règles sudoers NOPASSWD dédiées sur les DEUX machines** pour `systemctl stop/start` des
  services concernés — précondition de `health.py::stop_peer_service` et
  `watchdog.py::start_local_service`. Même pattern que la règle déjà en place pour
  `guitarhunter-api-prod` (voir `ARCHITECTURE.md`).
- Le démon `watchdog.py` doit tourner en dehors du thread du bot lui-même (process/service
  systemd séparé) sur chaque machine — sinon il ne peut jamais aider l'autre nœud si SON PROPRE
  service local est arrêté.

## 5. Historique des correctifs de conception

- **2026-09-27, revue `/code-review` (2 passes, 5 findings)** : voir `JOURNAL.md` [2026-09-27]
  pour le détail — fencing réordonné après la prise du bail, échec de promotion/démarrage géré
  explicitement (libération du bail), `lease.release()` rendu transactionnel, backfill Postgres
  préexistant protégé contre un cast invalide au démarrage, fuite d'erreur frontend après
  démontage corrigée.

## 6. Reste à faire (dans l'ordre probable)

1. Provisioning réel du Dell (§4) — nécessite un accès SSH réel, pas faisable depuis
   l'environnement de dev.
2. Règles sudoers NOPASSWD sur les deux machines.
3. Validation manuelle du bail/watchdog en conditions réelles (déclencher une bascule
   volontairement, vérifier chaque étape) AVANT tout branchement automatique.
4. Gating de `bot.py::run_scan()` sur le bail (ne pas scraper si ce nœud n'est pas primaire) —
   délibérément pas fait dans la passe du 2026-09-27 : `run_scan()` est un point d'attention
   critique déjà signalé (`CLAUDE.md`), à toucher séparément avec sa propre conception/tests.
5. Indirection frontend (`apiService.js`) : `VITE_API_BASE_URL` est actuellement figé sur
   `serveur.tail16b52e.ts.net/prod` — design pressenti : un petit fichier statique republié par
   le watchdog au moment de la bascule, interrogé par le frontend avant connexion.
6. Avenant CI (`run_script_dell.yml` ou nouveau workflow) pour déployer/mettre à jour le
   watchdog et les services standby sur le Dell.
7. Runbook de retour à la normale (§3.4).
