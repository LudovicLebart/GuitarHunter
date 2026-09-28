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

## 7. Runbook de provisioning + étapes de déploiement suivantes

> À exécuter par l'utilisateur (accès SSH réel requis, pas disponible depuis l'environnement de
> dev). Chaque bloc a sa propre vérification avant de passer au suivant — ne pas enchaîner à
> l'aveugle. Rédigé le 2026-09-28, avant toute exécution réelle : à ajuster si le terrain diverge
> (même discipline que `CUTOVER_RUNBOOK.md` — vérifier l'état réel du serveur avant d'agir, ne
> jamais supposer).

### 7.1 Réplication Postgres (Lenovo → Dell)

`guitarhunter_pg_prod` tourne en conteneur Docker (`postgres:16-alpine`) sur le Lenovo, exposé en
`127.0.0.1:5434` **seulement** (pas sur le tailnet) — cohérent avec la posture du projet
(Tailscale Funnel pour l'API HTTP, jamais Postgres directement exposé). Plutôt que de rebinder le
port sur l'interface Tailscale (surface d'exposition supplémentaire, à éviter), la réplication
passe par un **tunnel SSH persistant** (`autossh`) initié depuis le Dell — cohérent avec le fait
que tout l'accès inter-machines du projet passe déjà par SSH.

1. **Sur le Lenovo** — utilisateur de réplication dédié (jamais le compte applicatif) :
   ```sql
   -- Dans le conteneur guitarhunter_pg_prod
   CREATE ROLE guitarhunter_replicator WITH REPLICATION LOGIN PASSWORD '<à générer>';
   ```
   `pg_hba.conf` du conteneur : ajouter une ligne `host replication guitarhunter_replicator 127.0.0.1/32 scram-sha-256` (le tunnel SSH fait apparaître la connexion comme locale — pas besoin d'ouvrir plus large) puis `SELECT pg_reload_conf();`.
   Vérifier `wal_level = replica` et `max_wal_senders >= 3` (marge pour `guitarhunter_pg_staging` existant + cette réplique) dans `postgresql.conf` du conteneur — redémarrage du conteneur requis si `wal_level` doit changer (pas un simple reload).

2. **Sur le Dell** — tunnel SSH persistant vers le port de réplication du Lenovo :
   ```bash
   # Service systemd dédié (voir 7.3) plutôt qu'un tunnel lancé à la main, qui ne survivrait pas à un redémarrage
   autossh -M 0 -N -L 6543:127.0.0.1:5434 ludovic@serveur.tail16b52e.ts.net
   ```
   Vérification : `psql "host=127.0.0.1 port=6543 dbname=guitarhunter user=guitarhunter_replicator" -c "SELECT 1;"` depuis le Dell doit répondre.

3. **Sur le Dell** — base de la réplique via `pg_basebackup` (à travers le tunnel) :
   ```bash
   docker run -d --name guitarhunter_pg_dell -p 127.0.0.1:5435:5432 \
     -v guitarhunter_pg_dell_data:/var/lib/postgresql/data postgres:16-alpine
   docker stop guitarhunter_pg_dell   # on a juste besoin du volume vide, pas du process
   docker run --rm -v guitarhunter_pg_dell_data:/var/lib/postgresql/data postgres:16-alpine \
     pg_basebackup -h 127.0.0.1 -p 6543 -U guitarhunter_replicator -D /var/lib/postgresql/data -Fp -Xs -R -P
   ```
   `-R` écrit automatiquement `postgresql.auto.conf`/le signal de standby avec `primary_conninfo` pointant sur `127.0.0.1:6543` (le tunnel) — cohérent avec `backend/ha/watchdog.py::promote_local_postgres_replica()`, qui suppose une base déjà en mode standby.
   Démarrer ensuite `guitarhunter_pg_dell` et vérifier `SELECT pg_is_in_recovery();` → doit renvoyer `t`.

4. **Validation de bout en bout** : écrire une ligne de test sur `guitarhunter_pg_prod` (Lenovo),
   confirmer son apparition sur `guitarhunter_pg_dell` (Dell) en quelques secondes. Mesurer le lag
   de réplication réel (`pg_stat_replication` côté primaire) avant de considérer §7.1 clos.

### 7.2 Dépendances applicatives sur le Dell

Répertoire dédié `~/guitarhunter-standby` (jamais `~/MoneyBot`, même logique que
`run_script_dell.yml`) :
```bash
mkdir -p ~/guitarhunter-standby && cd ~/guitarhunter-standby
git clone https://github.com/LudovicLebart/GuitarHunter.git .
git checkout dev
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium
```
Fichiers `.env`/`backend/config/serviceAccountKey.json` à copier manuellement depuis le Lenovo
(mêmes secrets Firebase/`DOT_ENV` — jamais commités), plus `HA_NODE_ID=dell` et
`DATABASE_URL=postgresql://guitarhunter@127.0.0.1:5435/guitarhunter` (le port de la réplique
locale, §7.1) ajoutés à l'`.env` du Dell spécifiquement.

### 7.3 Unités systemd (contenu à créer via SSH, jamais versionné dans ce repo — même
convention que `guitarhunter-api-prod`, voir `ARCHITECTURE.md`)

Trois unités sur le Dell, toutes `Enabled: no` / arrêtées après création (démarrage manuel une
fois validées, jamais automatique au provisioning) :
- `guitarhunter-pg-dell-tunnel.service` — le tunnel `autossh` de 7.1.2 (`Restart=always`, pour
  survivre à une coupure réseau transitoire).
- `guitare-hunter-dell.service` — le bot (`WorkingDirectory=~/guitarhunter-standby`,
  `ExecStart=<venv>/bin/python main.py`).
- `guitarhunter-api-dell.service` — l'API FastAPI, sur un port distinct de `guitarhunter-api-prod`
  (ex: 8002) pour ne jamais collisionner si les deux tournaient par erreur en même temps.
- `guitarhunter-ha-watchdog.service` (Lenovo ET Dell cette fois, symétrique) —
  `backend/ha/watchdog.py::run_forever()`, ne dépend d'aucune des unités ci-dessus (doit survivre
  à leur arrêt, voir §4 du plan).

### 7.4 Règles sudoers NOPASSWD (Lenovo ET Dell)

Scopées aux seules commandes nécessaires — jamais un NOPASSWD large :
```
# /etc/sudoers.d/guitarhunter-ha (visudo -f)
ludovic ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop guitare-hunter-dell.service, /usr/bin/systemctl start guitare-hunter-dell.service, /usr/bin/systemctl stop guitarhunter-api-dell.service, /usr/bin/systemctl start guitarhunter-api-dell.service
```
(adapter les noms d'unité sur le Lenovo, symétriquement, pour que chaque watchdog puisse arrêter/démarrer les unités de SON PROPRE nœud et arrêter celles du pair via SSH).

### 7.5 Étapes de déploiement suivantes (après 7.1-7.4 validés manuellement)

1. **Valider `backend/ha/` en conditions réelles, SANS automatisme** : lancer `watchdog.py` à la
   main sur les deux machines, observer le bail se renouveler dans Firestore, couper
   volontairement le service du Lenovo et vérifier que le Dell détecte, fence, promeut et démarre
   correctement — avant de brancher quoi que ce soit en continu (unités `Enabled`).
2. **Gating de `bot.py::run_scan()`** (§6.4 du plan) : coder et tester séparément, une fois 1.
   validé — ne jamais l'activer sur un nœud dont le bail/watchdog n'a pas encore été validé en
   conditions réelles.
3. **Indirection frontend** (§6.5) : une fois 1-2 validés, pour que le frontend suive réellement
   une bascule.
4. **Avenant CI** (§6.6) : automatiser le déploiement du code (pas le provisioning, qui reste
   manuel et ponctuel) vers `~/guitarhunter-standby` sur le Dell à chaque push `dev`/`master`,
   sur le modèle de `run_script_dell.yml` mais sans jamais redémarrer les services (le watchdog
   s'en charge).
5. **Activation finale** : unités `Enabled` sur les deux machines, watchdog en continu — dernière
   étape, seulement après validation manuelle complète de 1-4.
