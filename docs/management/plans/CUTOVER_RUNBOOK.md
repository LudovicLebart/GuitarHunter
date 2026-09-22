# Runbook de bascule — Phase B.5 (Firestore → Postgres)

> Statut : **préparation seulement**. Aucune fenêtre de coupure réelle planifiée. Ce document
> transforme la fenêtre de bascule en une exécution mécanique plutôt qu'une improvisation — il ne
> remplace pas la décision de déclencher B.5, qui reste entièrement à l'utilisateur (voir
> `TODO.md`, `JOURNAL.md` [2026-09-21] "On bascule ?" → "Préparer d'abord").

## 0. Pourquoi ce document

Au 2026-09-21, l'infrastructure Postgres est prête et validée (B.2-B.4 clos), mais trois choses
n'ont **jamais été faites**, et sont trop risquées pour être improvisées le jour J :
1. Le merge de `claude/firestore-postgres-migration` vers `dev`/`master` — plusieurs semaines de
   travail sur une branche isolée, jamais passées en revue comme un tout.
2. Le gel des écritures Firestore pendant la fenêtre de coupure.
3. Une stratégie de sauvegarde Postgres (comblée par ce chantier, voir §3).

## 1. Ce qui doit être mergé (ordre et raisons)

### 1.0 Fait établi en lisant `deploy.yml` (2026-09-21) — pourquoi ce n'est PAS un simple merge

`deploy.yml` est **identique** entre cette branche et `origin/dev` (`git diff origin/dev...HEAD --
.github/workflows/deploy.yml` : vide) — il n'a **aucune notion** de Postgres/`backend/api/*`
aujourd'hui. Et surtout : **toute** push sur `dev`/`master` déclenche automatiquement, sur le
serveur, `git reset --hard origin/<branche>` sur `~/GuitareHunter` **puis** `sudo systemctl
restart guitare-hunter` (le vrai bot, immédiatement, sans étape de validation manuelle). Donc
merger `bot.py`/`main.py` sur `dev` sans avoir préparé le terrain redémarre le vrai bot en mode
Postgres **dans la minute qui suit le push**, avec quoi que `pg_db.py` trouve dans l'environnement
à ce moment (repli par défaut : `postgresql://guitarhunter@localhost/guitarhunter` — **n'existe
pas** tel quel sur le serveur, le vrai Postgres tourne en conteneur sur le port `5434`). C'est
exactly le mécanisme qui a causé l'incident du 2026-09-19 (`apiService.js`), reproduit ici côté
bot si on merge sans préparer les secrets d'abord.

`requirements.txt` a en revanche déjà `fastapi`/`uvicorn`/`asyncpg`/`psycopg` sur `origin/dev`
(mergés lors d'un chantier antérieur) — pas un blocage de dépendances.

### 1.1 Préalable — secrets/sudoers à préparer AVANT tout merge qui en dépend (fait par l'utilisateur, pas par Claude)

- **Secret GitHub `DOT_ENV`** (déjà utilisé pour `.env` backend ET build Vite frontend, même
  secret pour les deux jobs) : y ajouter deux lignes AVANT l'étape 1.3 ci-dessous —
  `DATABASE_URL=postgresql://guitarhunter:...@127.0.0.1:5434/guitarhunter` (le DSN réel de
  `guitarhunter_pg_prod`, **sans** le `\r` qui a cassé `guitarhunter-api-prod` le 2026-09-21 — le
  copier depuis `~/.guitarhunter_prod_db.env` sur le serveur, pas retaper à la main) et
  `VITE_API_BASE_URL=https://serveur.tail16b52e.ts.net/prod`. Ajouter le secret AVANT ne casse
  rien (rien ne le lit tant que le code correspondant n'est pas mergé) — c'est l'inverse
  (merger avant d'avoir mis à jour le secret) qui est dangereux.
- **Règle sudoers** pour `guitarhunter-api-prod` (mêmes commandes que la règle existante pour
  `guitarhunter-api`, voir `TODO.md`) — seulement si on veut que `deploy.yml` gère ce service
  automatiquement (étape 1.5bis ci-dessous). Sinon il reste géré à la main comme aujourd'hui,
  aucune urgence à changer ça.

### 1.2-1.5 Ordre de merge — chaque étape doit rester déployable seule sans casser la précédente

1. **`backend/api/schema.sql`** — idempotent (`CREATE TABLE IF NOT EXISTS`/`ALTER ... ADD COLUMN
   IF NOT EXISTS`), aucun risque à le fusionner tôt, rien ne le déploie/l'exécute automatiquement.
2. **`backend/api/*` (code seul, ~4900 lignes, entièrement absent de `dev` aujourd'hui)** — sans
   toucher `deploy.yml` à ce stade : mergeable sans risque, puisque rien ne le déploie/redémarre
   automatiquement (reste géré à la main, `scp` + `systemctl`, comme actuellement).
   - *1.2bis (optionnel)* : ajouter à `deploy.yml` un bloc qui `scp` `backend/api/*` vers
     `~/guitarhunter-api-prod` et fait `sudo systemctl restart guitarhunter-api-prod` — seulement
     si la règle sudoers (§1.1) a été ajoutée.
3. **`backend/deal_mapping.py`, `backend/pg_repository.py`, `backend/pg_db.py`,
   `backend/logging_config.py`, `backend/bot.py`, `main.py`** — bascule le VRAI bot sur
   `PostgresRepository`. **Le morceau sensible** : à merger le MÊME JOUR que le secret `DOT_ENV`
   (§1.1) est en place, et de préférence en observant le déploiement en direct
   (`ssh ... journalctl -u guitare-hunter -f` pendant que le push tourne dans GitHub Actions) —
   pas improvisé un vendredi soir. Une fois ce commit sur `dev`, le bot réel écrit dans
   `guitarhunter_pg_prod` à la place de Firestore — **c'est en pratique le vrai moment de la
   bascule pour les écritures**, avant même la fenêtre B.5 formelle (§4 plus bas) ; y réfléchir
   comme tel plutôt que comme "juste un merge de code".
4. **Frontend (`src/services/apiService.js` + câblage des 9 hooks/composants)** — seulement une
   fois 1-3 validés en prod. `VITE_API_BASE_URL` déjà dans `DOT_ENV` depuis §1.1, rien à ajouter.
   Publication immédiate sur GitHub Pages au push (pas de fenêtre de validation intermédiaire
   dans le pipeline actuel) — même prudence que pour l'étape 3.
5. **`deploy.yml`** lui-même (si le 1.2bis n'a pas été fait plus tôt) — pour que les futurs
   déploiements gèrent `guitarhunter-api-prod` automatiquement, plutôt que de rester une procédure
   manuelle indéfiniment.

**Leçon du 2026-09-19 à ne pas reproduire** : ne jamais pousser un morceau isolé (ex: seulement le
frontend) sur `dev` en affirmant qu'il est "sans risque" sans avoir vérifié son comportement par
défaut réel (`VITE_API_BASE_URL` absent = `localhost:8000`, pas un no-op). Chaque étape ci-dessus
doit être vérifiée en conditions réelles avant la suivante, pas juste "ça compile".

## 2. Gel des écritures (fenêtre de coupure elle-même)

Le SDK Admin (utilisé par tout `backend/*`) **bypass toujours** les règles de sécurité Firestore
— gel en deux parties indépendantes, les DEUX nécessaires :

1. **Arrêter le bot** (bloque toutes les écritures via Admin SDK) :
   ```bash
   sudo systemctl stop guitare-hunter
   ```
2. **Geler les écritures client directes** (chat Gemini, plan de restauration, favori/rejet
   manuel, config — tout ce qui ne transite jamais par le bot) :
   ```bash
   cp firebase/firestore.rules firebase/firestore.rules.bak   # filet de sécurité local
   cp firebase/firestore.rules.freeze firebase/firestore.rules
   firebase deploy --only firestore:rules
   ```
   Voir `firebase/firestore.rules.freeze` (créé le 2026-09-21) — lecture laissée ouverte
   (l'app reste consultable), toute écriture bloquée. **Validé le 2026-09-21** via
   `firebase emulators:start --only firestore` + `@firebase/rules-unit-testing` (7/7 : lectures
   permises, toutes les écritures bloquées — config, chat, `shared_deals`, villes — isolation
   cross-utilisateur toujours respectée). Voir `JOURNAL.md`. Reste recommandé : un
   déploiement/rollback à blanc sur le VRAI projet Firebase (pas seulement l'émulateur) avant la
   vraie fenêtre, pour vérifier `firebase deploy --only firestore:rules` lui-même.

**Dégel** (une fois la bascule vérifiée, §4) :
```bash
git checkout firebase/firestore.rules   # restaure l'original depuis git
firebase deploy --only firestore:rules
```

## 3. Sauvegarde Postgres

Point resté ouvert depuis le début du plan (`FIRESTORE_MIGRATION_PLAN.md` §6) — comblé le
2026-09-21 par `backend/scripts/backup_postgres.py` : `pg_dump -Fc` + upload vers le bucket
Firebase Storage déjà utilisé par le projet (mêmes credentials, aucun nouvel outil/compte),
rétention des 14 sauvegardes les plus récentes. **Validé en conditions réelles contre
`guitarhunter_pg_staging`** (dump 16.1 Mo, upload + purge de rétention confirmés).

**Tranché et installé (2026-09-21)** : quotidien, 4h du matin. Testé manuellement en conditions
réelles contre `guitarhunter_pg_prod` (16.9 Mo, upload + purge de rétention confirmés) — pas
seulement staging.

```bash
# /home/ludovic/backup_prod_cron.sh (sur le serveur) — script dédié plutôt qu'une commande
# inline dans crontab : une première tentative de ligne crontab directe a cassé "$DATABASE_URL"
# à travers les couches d'échappement (bash local -> SSH -> bash distant -> crontab).
#!/bin/bash
cd /home/ludovic/GuitareHunter
set -a
. /home/ludovic/.guitarhunter_prod_db.env
set +a
venv/bin/python backend/scripts/backup_postgres.py --database-url "$DATABASE_URL"

# Entrée crontab (installée) :
0 4 * * * /home/ludovic/backup_prod_cron.sh >> /home/ludovic/guitarhunter-backup.log 2>&1
```

## 4. Séquence complète le jour J (une fois 1-3 ci-dessus préparés et mergés)

1. **Sauvegarde manuelle immédiate** (`backup_postgres.py`, en plus du cron) — filet avant toute
   action irréversible.
2. **Geler** (§2) : arrêt du bot + règles Firestore.
3. **Export final** : rejouer `export_firestore_to_postgres.py` (idempotent, déjà utilisé deux
   fois en conditions réelles — voir `JOURNAL.md` [2026-09-20]/[2026-09-21]) contre
   `guitarhunter_pg_prod` — capture tout ce qui a été écrit jusqu'à l'instant du gel.
4. **Bascule** : redémarrer `guitare-hunter` (désormais en mode Postgres, pointé prod) ; déployer
   le nouveau frontend (`VITE_API_BASE_URL` → `/prod`).
5. **Vérifier** : `compare_firestore_postgres.py` sur l'ensemble des données + test manuel du
   parcours principal (scan, chat, plan de restauration, achat, favori) en conditions réelles.
6. **Dégeler** (§2) — restaurer `firestore.rules` original.
7. **Filet de sécurité** : Firestore gardé intact en lecture seule quelques jours (déjà acté),
   suppression définitive seulement après une période d'observation sans incident.

## 5. Rollback si ça tourne mal en cours de route

- Avant l'étape 4 (bascule) : trivial — redémarrer `guitare-hunter` normalement (toujours en mode
  Firestore tant que le déploiement du bot Postgres n'a pas eu lieu), restaurer les règles.
- Après l'étape 4 : plus délicat — Firestore reste la source de vérité intacte (aucune écriture
  ne l'a jamais quitté pendant le gel), donc revenir en arrière veut dire redéployer l'ancienne
  version du bot/frontend (Firestore) et arrêter le service Postgres — mécaniquement possible
  mais **jamais répété**, à tester avant la vraie fenêtre plutôt que découvert en urgence.
