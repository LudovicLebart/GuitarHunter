# Constats de revue — section 5 : base de connaissances et fiches

Relevés le 2026-11-05 pendant la passe « deepdocument » (commit `c5a5f05`), à la lecture de `guitar_knowledge.py`, `fiches_repo.py`, des chargeurs, et à partir de l'état réel de la base du serveur (lecture seule). Rien n'a été corrigé. Format : voir [README](README.md).

### R-5-1 — Neuf tests Postgres échouent au lieu de se sauter sans `KB_TEST_DATABASE_URL`
- Où : `backend/test_guitar_knowledge.py:694` (`class TestWriteRecordsPostgres`, sans le `@unittest.skipUnless(os.getenv("KB_TEST_DATABASE_URL"), …)` que portent les classes des lignes 242 et 594) ; `CLAUDE.md` (« les tests qui exigent Postgres se sautent sans `KB_TEST_DATABASE_URL` »).
- Catégorie : test · Gravité : moyenne
- Constat (mesuré : 152 tests exécutés, 38 sautés, 11 erreurs) : neuf erreurs `KeyError: 'KB_TEST_DATABASE_URL'` viennent de cette classe. Deux autres sont des `UnicodeEncodeError` (impression d'une flèche `→` sur la console Windows cp1252) dans `TestBuildRecordsOnRealPreviewCases.test_wiring` et `TestReviewCases.test_skipped_entities_do_not_reach_the_records`. En CI la variable est posée, donc rien ne casse ; en local, la suite est rouge sans raison, ce qui masque les vraies régressions.
- Piste : ajouter le décorateur ; remplacer la flèche dans les `print` ou forcer l'encodage de sortie.

### R-5-2 — Chaque exécution de l'amorçage crée une version de plus : 12 versions, aucune validée
- Où : `backend/scripts/seed_guitar_knowledge.py:189-197` (INSERT d'une version à chaque exécution) ; base du serveur : versions 1 à 12 (une import Wikidata, onze amorçages).
- Catégorie : hygiène des données · Gravité : basse à moyenne
- Constat (mesuré) : le script se dit idempotent, mais chaque lancement insère une version et pose `kb_version` de toutes les fiches du lot sur ce nouveau numéro. Le 2026-10-15, les lots 7 et 8 ont été chargés quatre et trois fois (versions 5, 6, 9, 11 et 8, 10, 12) pour le même contenu. Aucune version n'est validée : la base de marques est donc inerte pour le Portier, quoi qu'on fasse du réglage.
- Piste : ne créer de version que si au moins une fiche change réellement.

### R-5-3 — « Approuvée » ne veut pas dire « relue par une personne », et rien n'est validé
- Où : base du serveur ; `guitar_knowledge.py:220-229` (`review_state`), `:251` (`is_trusted`), `knowledge_triage.py:36-38` et `knowledge_ai_review.py:238` (approbation automatique).
- Catégorie : qualité des données · Gravité : moyenne
- Constat (mesuré) : 731 fiches de marque approuvées : **447 par règles automatiques sans IA, 235 par Claude, 49 par une note individuelle** ; 112 rejetées (toutes avec une note individuelle). La porte de qualité (`is_trusted`) traite une approbation automatique comme une relecture humaine : une fiche importée de Wikidata devient « fiable » sans qu'une personne l'ait vue. Par ailleurs 0 version n'est validée et aucun rejeu de non-régression n'est consigné, donc aucune de ces approbations n'a d'effet au Portier aujourd'hui.
- Piste : distinguer dans `review_status` ou une colonne d'origine (`auto_rules`, `ai`, `human`), et exiger une origine humaine pour les fiches injectées au Portier, ou au moins la mesurer dans le rejeu.

### R-5-4 — Toutes les fiches sont servies au chat, brouillons compris
- Où : `backend/api/fiches_repo.py:9-11` (décision produit assumée), 13 fiches sur 14 au statut `brouillon`, 1 en révision, aucune validée.
- Catégorie : risque produit · Gravité : basse à moyenne
- Constat : le chat et le site citent des procédures non relues (neck reset, truss rod) avec leur statut visible. C'est voulu, mais le bandeau « brouillon » est la seule protection contre un conseil qui peut abîmer l'instrument. À reconsidérer quand l'application aura plus d'utilisateurs.
- Piste : réserver les procédures de difficulté 4 et plus aux fiches `validee`, ou les marquer plus fortement.

### R-5-5 — Docstrings périmées
- Où : `fiches_repo.py:13` (« chargées par … (commande manuelle) » : elles le sont à chaque déploiement) ; `guitar_knowledge.py:1-2` (renvoie à `STRATEGIE_IA.md` §3 sans préciser que les fiches y sont absentes).
- Catégorie : doc-code · Gravité : basse

### R-5-6 — Deux fonctions aux noms presque identiques, avec un garde-fou de levée d'exception
- Où : `guitar_knowledge.py:371` (`match_alias_index`) et `:651` (`match_aliases`, avec un `TypeError` explicite si on lui passe l'ancienne signature).
- Catégorie : simplification · Gravité : basse
- Piste : renommer `match_aliases` en `match_free_query` ; supprimer le garde-fou après renommage.

### R-5-7 — État global partagé par tous les threads du processus
- Où : `guitar_knowledge.py:145` (`_VERSION_MODE`), `:206` (`_REQUIRE_REVIEW`), `_caches`, `_cache_all`.
- Catégorie : robustesse · Gravité : basse
- Constat : `configure_version` et `configure_review_gate` sont appelés à chaque analyse (idempotents). Un script d'audit qui les règle sur `latest` ou `False` dans le même processus que le bot modifierait le comportement du Portier ; les scripts actuels tournent à part, donc sans effet aujourd'hui.
- Piste : passer le mode en paramètre de `lookup`.
