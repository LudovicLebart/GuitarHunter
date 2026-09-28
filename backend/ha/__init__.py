"""Chantier "redondance Dell" (préparation) — bascule automatique Postgres + bot/API vers le
Dell T5810 (cluster MoneyBot) en cas de panne du serveur de production (Lenovo ThinkCentre
M720q). Voir docs/management/plans/DB_REDUNDANCY_DELL_PLAN.md pour l'état d'avancement.

Aucun module de ce paquet n'est encore importé par un chemin de production (`bot.py`/`main.py`/
`backend/api/main.py`) — préparation isolée, sur le modèle déjà suivi pour la bascule
Firestore→Postgres (FIRESTORE_MIGRATION_PLAN.md §5.1 : "construire sur une branche séparée, sans
toucher au chemin existant").
"""
