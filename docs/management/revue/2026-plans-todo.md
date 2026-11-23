# Constats de revue — section 11 : plans, TODO, journal, aperçu

Relevés le 2026-11-06 pendant la passe « deepdocument » : en-têtes et dates de commit des 21 plans, présence du code décrit, structure et cases de `TODO.md`, liens. Les plans n'ont pas été relus en entier. Rien n'a été corrigé, sauf deux retouches mineures de `TODO.md` et la création de `plans/README.md` (index d'état). Format : voir [README](README.md).

### R-11-1 — Presque aucun plan ne porte un statut fiable
- Où : `docs/management/plans/` (4 plans sur 21 ont une ligne « Statut », dont 2 périmées).
- Catégorie : doc · Gravité : moyenne
- Constat : `DB_REDUNDANCY_DELL_PLAN.md` dit « préparation, rien déployé » alors que le watchdog tourne (R-9-9) ; `PERF_API_INDEX_PLAN.md` dit « palier 1, non déployé » alors que `TODO.md` annonce les paliers 1 à 3 poussés ; `CUTOVER_RUNBOOK.md` garde un « statut d'origine : préparation seulement ». Un lecteur ne sait pas quels plans décrivent le système.
- Piste : une ligne `Statut : <état> (date)` en tête de chaque plan, d'après `plans/README.md`.

### R-11-2 — Trois plans décrivent une architecture abandonnée ou jamais réalisée
- Où : `MULTI_USER_PLAN.md` (superviseur + processus workers), `GEMINI_PROMPT_CACHING_PLAN.md` (cache de contexte explicite), `FIRESTORE_MIGRATION_PLAN.md` (schéma « une ligne par utilisateur »).
- Catégorie : doc-code · Gravité : basse
- Constat : le bot tourne en un thread par utilisateur ; aucune création de cache Gemini dans le code ; le catalogue d'annonces est partagé. Seul le dernier le signale.
- Piste : bandeau « remplacé / non réalisé » ou déplacement dans un sous-dossier `archive/`.

### R-11-3 — `TODO.md` pèse 190 Ko et mêle cases ouvertes, fermées et récits
- Où : `docs/management/TODO.md` (704 lignes, 30 sections ; 142 cases ouvertes, 183 fermées).
- Catégorie : doc · Gravité : moyenne
- Constat : des sections entières n'ont plus aucune case ouverte (Chat galerie, Plan de restauration, Ajout de ville, Migration Firestore) mais restent dans le fichier ; « Priorité Immédiate — 2026-09-24 » date de six semaines ; l'item « Dérive documentaire » parle de Firestore comme d'un état présent. Les plus gros blocs ouverts : audit de fiabilité du Portier (21 ouvertes), remplacement de Gemini par Sonnet (17), base de connaissances (7), redondance (7), maintenabilité (7).
- Piste : déplacer vers `TODO_ARCHIVE.md` les sections sans case ouverte ; classer le reste par priorité réelle.

### R-11-4 — Liens cassés dans `TODO.md` (un corrigé)
- Où : `TODO.md` section « Priorité Immédiate » : lien vers `../explanation/plan/…PLAN.pdf` (inexistant).
- Catégorie : doc · Gravité : basse
- Constat : corrigé le 2026-11-06 (pointe vers `plans/LOCAL_PERCEPTION_AND_MENTOR_RAG_PLAN.md`). Une vérification de tous les liens relatifs de `docs/` reste à faire en section 12.
- Piste : script de contrôle des liens dans la CI de documentation.

### R-11-5 — `REPRISE_SESSION_2026-09-21.md` devait être supprimé
- Où : `docs/management/REPRISE_SESSION_2026-09-21.md` (98 lignes).
- Catégorie : doc / hygiène · Gravité : basse
- Constat : le fichier dit lui-même « à supprimer une fois la reprise faite » ; le chantier I (Qwen local) est soldé depuis le 2026-09-29.
- Piste : supprimer (Git le garde) ou verser l'utile dans `TODO_ARCHIVE.md`.

### R-11-6 — La branche du banc d'essai et celle de la vision ne sont pas décrites côté documentation
- Où : branches `claude/guitarhunter-benchmark-setup-h9q9gr`, `claude/guitar-condition-vision-pipeline-uj6jj4`, `claude/guitar-hunter-leboncoin-1prbyl`, `claude/scraper-stealth-mutualization`, `ccr-e759704a-jpvqmr`, `ccr-a6708397-9dr6ta`.
- Catégorie : doc / risque de dérive · Gravité : basse
- Constat : aucune doc ne dit ce que contient chaque branche ni si elle sera fusionnée ; le contenu n'a pas été relu ici. Le RAG « mentor » n'a pas de branche (plan seul).
- Piste : un tableau branche → objet → état dans `plans/README.md` après relecture des branches (hors de cette passe).

### R-11-7 — Les documents d'explication ont été alignés, `STATS_REFLEXION.md` reste une réflexion non suivie
- Où : `docs/explanation/PROJECT_OVERVIEW.md` (à jour sur Postgres, Portier local, Expert Claude), `STATS_REFLEXION.md` (idées de statistiques jamais cochées nulle part).
- Catégorie : doc · Gravité : basse
- Constat : l'aperçu correspond au code relevé en sections 1 à 10. La réflexion statistique n'est reliée à aucun item du TODO (section « Statistiques & Dashboard » à part).
- Piste : lier les deux ou archiver la réflexion.
