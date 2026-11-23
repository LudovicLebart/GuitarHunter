# Plans : index et état réel (vérifié le 2026-11-06)

Les 21 documents de ce dossier ont été écrits à des moments différents ; la plupart ne portent pas de ligne de statut, ou une ligne périmée. Cet index donne l'état **constaté** (date du dernier commit du plan, présence du code décrit), sans modifier les plans eux-mêmes. En cas de désaccord entre un plan et le code, le code et les références (`docs/reference/`) font foi.

Légende : **Appliqué** (livré, vérifié dans le code) · **En cours** · **Non commencé** · **Remplacé** (l'architecture a changé) · **Historique** (garde la trace d'une décision, ne décrit plus le système) · **R&D** (réflexion, rien de branché).

| Plan | Dernier commit | État | Remarque |
|---|---|---|---|
| `ADMIN_DASHBOARD_PLAN.md` | 2026-07-08 | Appliqué | `backend/api/admin_repo.py`, `AdminDashboard.jsx` ; les règles Firestore citées sont périmées |
| `CHAT_GALLERY_REQUALIFICATION_PLAN.md` | 2026-08-27 | Appliqué | lots 1 et 2 livrés ; l'API du chat est passée sur Claude (voir `COUT_SONNET…`) |
| `RESTORATION_PLAN_PLAN.md` | 2026-08-23 | Appliqué | `restoration_repo.py` ; voir `reference/restauration_et_pieces.md` |
| `MULTI_USER_PLAN.md` | 2026-07-06 | Remplacé | superviseur + processus workers jamais réalisés : le bot tourne en un thread par utilisateur |
| `FIRESTORE_MIGRATION_PLAN.md` | 2026-10-03 | Historique | migration faite ; le plan porte déjà un avertissement de péremption |
| `CUTOVER_RUNBOOK.md` | 2026-10-03 | Historique | « bascule faite » ; ne pas rejouer |
| `DB_REDUNDANCY_DELL_PLAN.md` | 2026-09-28 | En cours, **statut périmé** | l'en-tête dit « préparation, rien déployé » ; le service `guitarhunter-ha-watchdog` tourne sur le serveur (R-9-9) ; branche `claude/db-redundancy-dell-5810-mvzv2j` mentionnée |
| `COUT_SONNET_CHAT_OPUS_PLAN.md` | 2026-11-01 | En cours | étapes 1 et 2 poussées, validation en conditions réelles restante |
| `FB_CITY_IDS_AND_SCRAPER_HEALTH_PLAN.md` | 2026-10-30 | En cours | phase B2 et phase C (question « compte connecté ou anonyme ») ouvertes |
| `PERF_API_INDEX_PLAN.md` | 2026-11-04 | En cours | paliers 1 à 3 poussés sur `dev` d'après `TODO.md` ; l'en-tête du plan dit encore « palier 1, non déployé » (périmé) |
| `COST_OPTIMIZATION_CHANTIERS.md` | 2026-09-21 | En cours (synthèse) | rassemble les chantiers de coût ; plusieurs sont soldés ailleurs (Portier local, Expert Claude) |
| `GEMINI_PROMPT_CACHING_PLAN.md` | 2026-09-08 | Non appliqué | aucune création de cache explicite dans le code (seul le compteur de jetons mis en cache est lu) ; visait Gemini 2.5 Pro, remplacé comme Expert |
| `TOKEN_OPTIMIZATION_PLAN.md` | 2026-08-23 | Non tranché | persona « luthier » et pages narratives : état non vérifié |
| `STRATEGIE_IA.md` | 2026-10-25 | Référence vivante, en partie datée | v6 du 2026-09-28 ; l'Expert est passé à Claude depuis (voir `reference/ia.md`) |
| `CHANTIER_B_PERCEPTION_RAISONNEMENT_PLAN.md` | 2026-09-07 | En révision | banc d'essai sur la branche `claude/guitarhunter-benchmark-setup-h9q9gr` ; `backend/benchmark/` est dans `dev` |
| `LOCAL_PERCEPTION_AND_MENTOR_RAG_PLAN.md` | 2026-09-24 | Brouillon | **aucune branche RAG n'existe** ; rien de codé |
| `NECK_RESET_VISION_PLAN.md` | 2026-10-03 | R&D | pipeline vision sur la branche `claude/guitar-condition-vision-pipeline-uj6jj4` |
| `NECK_RESET_FABLE.md` | 2026-10-02 | R&D | v5, même sujet, approche probabiliste |
| `PARTS_DETECTOR_AND_CROPS_PLAN.md` | 2026-10-03 | En cours, non branché | `backend/auto_annotation/` ; pas en production |
| `YOLO_OBB_AUTO_ANNOTATION_PLAN.md` | 2026-10-02 | Référence technique | phases 0 à 6 du plan précédent |
| `SELF_HOSTING_SITE_AND_PHOTOS_PLAN.md` | 2026-10-03 | Non commencé | priorité basse décidée |

## Branches actives en rapport avec les plans
- `claude/guitar-condition-vision-pipeline-uj6jj4` : vision (neck reset, état).
- `claude/guitarhunter-benchmark-setup-h9q9gr` : banc d'essai IA (porte `sample_benchmark_dataset.py`, absent de `dev`).
- `claude/guitar-hunter-leboncoin-1prbyl`, `claude/scraper-stealth-mutualization`, `ccr-e759704a-jpvqmr`, `ccr-a6708397-9dr6ta` : scraping et divers, sans plan dédié ici.
- RAG « mentor » : plan seul, pas de branche.
