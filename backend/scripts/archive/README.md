# Scripts archivés

Outils de la **migration Firestore → Postgres (terminée en septembre 2026)** et essais qui leur étaient liés. Ils sont gardés pour
l'historique, **ne pas les relancer** : relancé contre la base de production avec un `DATABASE_URL` exporté,
`export_firestore_to_postgres.py` réécrirait les annonces d'après le dernier contenu de Firestore (septembre), donc avec des
analyses plus anciennes que celles de Postgres (revue R-10-2, 2026-11-08).

| Fichier | Rôle d'origine |
|---|---|
| `export_firestore_to_postgres.py` | Export complet Firestore → Postgres (`ON CONFLICT DO UPDATE`) |
| `compare_firestore_postgres.py` | Comparaison des deux bases pendant la bascule |
| `migrate_cities_to_shared_catalog.py` | Villes par utilisateur → catalogue partagé |
| `migrate_firestore_prompts.py` | Prompts Firestore → `prompts.json` |
| `enrich_cities_coords.py` | Coordonnées des villes du catalogue (une fois) |
| `essai_export_firestore_to_postgres*.py` | Tests du mappage et de l'intégration de l'export (renommés pour ne pas être ramassés par `pytest`) |
