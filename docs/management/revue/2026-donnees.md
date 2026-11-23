# Constats de revue — section 1 : données et schéma Postgres

Relevés le 2026-11-05 pendant la passe « deepdocument » (commit `22e5a1b`). Rien n'a été corrigé dans le code. Format : voir [README](README.md).

### R-1-1 — La suppression d'un utilisateur n'efface pas ce que le message annonce
- Où : `src/components/AdminDashboard.jsx:66` (message de confirmation) ; `backend/api/admin_repo.py:111-120` ; `backend/api/schema.sql:375` (`restoration_plan_items.user_id TEXT` sans clé étrangère).
- Catégorie : doc-code (message affiché à l'utilisateur) · Gravité : moyenne
- Constat : le message (reformulé le 2026-11-05) dit que le « plan de restauration » est supprimé. Seule la ligne `users` est supprimée ; les étapes de plan restent en base avec un `user_id` orphelin. Les achats de l'utilisateur restent aussi (`purchased_by_user_id` passe à `NULL` par `ON DELETE SET NULL`, mais `is_purchased` reste vrai).
- Piste : corriger le texte du message (rapide) ; décider ensuite si `delete_user_data` doit aussi supprimer ces étapes et défaire les achats. Vérifié le 2026-11-06 (section 6) : `toggle_purchased` refuse alors tout le monde (409 « déjà achetée par un autre utilisateur ») ; voir R-6-9.

### R-1-2 — Le chat d'une annonce est partagé entre tous les utilisateurs qui la voient
- Où : `backend/api/chat_repo.py:36` (`SELECT * FROM deal_chat WHERE deal_id = $1`), `schema.sql:297` (`deal_chat` sans `user_id`).
- Catégorie : sécurité / robustesse · Gravité : haute si plusieurs utilisateurs réels, basse aujourd'hui
- Constat : depuis le catalogue partagé, deux utilisateurs dont les scans trouvent la même annonce voient le même fil de chat (messages, propositions de restauration, photos jointes). L'accès exige seulement la visibilité de l'annonce (`user_deal_matches`).
- Piste : ajouter `user_id` à `deal_chat` et filtrer dessus, ou documenter explicitement le partage comme voulu.

### R-1-3 — Le schéma est rejoué en entier à chaque démarrage et reconstruit des index
- Où : `schema.sql:165-172` (4 × `DROP INDEX IF EXISTS` puis `CREATE INDEX` sur `guitar_deals`), triggers `DROP TRIGGER` + `CREATE TRIGGER` partout, `UPDATE` de rattrapage lignes 276-284 et 376-383, bloc `DO $$` ligne 181.
- Catégorie : performance / robustesse · Gravité : moyenne
- Constat : à chaque démarrage de l'API de production, de l'API de test **et** du bot (trois processus, redémarrés ensemble à chaque push sur `dev`), les index de `guitar_deals` sont détruits puis recréés (verrou en écriture le temps de la construction), et les triggers redéfinis (verrous exclusifs brefs). Deux démarrages simultanés peuvent se bloquer l'un l'autre. Les `UPDATE` de rattrapage parcourent aussi la table.
- Piste : migrations numérotées (table `schema_migrations`) ou garde `IF NOT EXISTS` pour ces index ; réserver les `UPDATE` de rattrapage à un script ponctuel.

### R-1-4 — Aucun index sur `user_deal_matches(deal_id)` ni `user_deal_state(deal_id)`
- Où : `schema.sql:90-114` (clés primaires `(user_id, deal_id)`).
- Catégorie : performance · Gravité : basse (à mesurer)
- Constat : les accès par `deal_id` seul (cascade à la suppression d'une annonce, sous-requête « premier utilisateur qui a vu l'annonce » du rattrapage) ne peuvent pas utiliser la clé primaire. À 8 500 annonces c'est négligeable ; cela le sera moins avec plus d'utilisateurs.
- Piste : `EXPLAIN` sur ces requêtes avant d'ajouter l'index.

### R-1-5 — Commentaires périmés dans le code de la base
- Où : `backend/pg_db.py:13-16` (« n'est importé par aucun code de production » : faux, `main.py` et `analyzer.py` l'importent) ; `schema.sql:499-501` (« le bot restant sur Firestore ») ; `backend/deal_mapping.py:1-10` (renvoie à `export_firestore_to_postgres.py` et à `repository.py`, qui n'existe plus dans `master`).
- Catégorie : doc-code · Gravité : basse
- Piste : réécrire ces en-têtes ; vérifier en section 10 si les scripts `export_firestore_to_postgres.py`, `compare_firestore_postgres.py`, `migrate_*` sont encore utiles.

### R-1-6 — Modules sans importeur en production
- Où : `backend/scraper.py` (4 lignes, lève `ImportError` volontairement), `backend/crop_description.py` (aucun import hors tests). `backend/database.py` n'est plus utilisé que par `main.py` et des scripts.
- Catégorie : code-mort · Gravité : basse
- Piste : supprimer `scraper.py` ; `crop_description.py` appartient à la chaîne du détecteur de parties (il importe `auto_annotation`), non branchée : voir `restauration_et_pieces.md` §3 ; réduire `database.py` au bail HA et au Storage.

### R-1-7 — La purge des photos s'appuie sur le verdict et la date de dernière modification
- Où : `backend/pg_repository.py:693-740`.
- Catégorie : robustesse · Gravité : basse
- Constat : sont purgées les photos de toute annonce au verdict de rejet (dont `BAD_DEAL`) dont `timestamp` (dernière modification, pas date de scan) a plus de 30 jours, pour **tous** les utilisateurs de l'annonce partagée ; une annonce mise en favori par un utilisateur perd ses photos si un autre l'a jugée mauvaise. Une ré-analyse repousse la purge. Seul `storage_image_urls` est vidé : `image_urls` (URL Facebook périmées) reste.
- Piste : exclure les annonces en favori ou achetées de la purge.

### R-1-8 — Le schéma n'a ni contrainte de valeurs ni clé étrangère sur plusieurs liens
- Où : `schema.sql` : `guitar_deals.status`, `verdict`, `commands.type`/`status`, `bot_status` sont des `TEXT` libres ; `restoration_plan_items.user_id`, `llm_usage.deal_id`, `fiche_slug` n'ont pas de clé étrangère (les deux derniers volontairement, voir commentaires).
- Catégorie : robustesse · Gravité : basse
- Constat : l'ensemble des valeurs d'état n'est défini qu'en Python et en JavaScript (relevé dans `donnees.md`) ; une faute de frappe est acceptée par la base.
