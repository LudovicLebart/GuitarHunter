"""
Audit + uniformisation des villes (`deal.location`) — 2026-08-16. GRATUIT, AUCUN APPEL GEMINI.

La même ville était stockée sous plusieurs graphies parce que deux producteurs écrivaient deux
formats : Facebook la chaîne scrapée telle quelle (`Montréal, QC`), Kijiji la clé normalisée de
la ville configurée (`montreal`). Les regroupements par ville comptaient donc la même ville
plusieurs fois. La cause a été corrigée à la source (`bot.py` écrit désormais le nom
d'affichage) ; ce script traite l'historique déjà en base.

Deux passes, nécessairement :
  1. LECTURE — regroupe toutes les valeurs `location` par clé canonique et choisit, pour chaque
     ville, la graphie la plus riche observée (région + accents). Impossible de choisir en une
     seule passe : le meilleur libellé d'une ville peut n'apparaître qu'à la toute dernière
     annonce lue.
  2. ÉCRITURE (sauf `--dry-run`) — réécrit `location` (document + index) pour les annonces qui
     ne portent pas déjà ce libellé.

Ne renomme jamais une ville en une autre : deux graphies ne sont fusionnées que si elles ont la
MÊME clé canonique (insensible aux accents/casse/tirets/abréviations Saint-St/région). `Paris,
IDF` et `Montréal, QC` restent deux villes distinctes.

Idempotent : relancé, il ne réécrit plus rien (sûr pour la double exécution `dev` puis `master`
de `run_once.py`). Support `--dry-run`.
"""
import sys
import os
import argparse
import logging
from collections import defaultdict

sys.path.insert(0, os.getcwd())

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.repository import FirestoreRepository
from backend.cities import normalize_city_key, pick_best_label, regions_conflict

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("audit_cities")

PAGE_SIZE = 500


def _collect(repo):
    """Retourne `{deal_id: location}` pour toutes les annonces d'un utilisateur."""
    locations = {}
    query = repo.collection_ref.select(['location']).order_by('__name__').limit(PAGE_SIZE)
    last_doc = None
    while True:
        current = query.start_after(last_doc) if last_doc else query
        docs = list(current.stream())
        if not docs:
            break
        for doc in docs:
            locations[doc.id] = (doc.to_dict() or {}).get('location')
        last_doc = docs[-1]
    return locations


def run(dry_run=False):
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}Audit des villes sur {len(users)} utilisateurs.")

    grand_total_deals = 0
    grand_total_fixed = 0
    grand_total_variants = 0

    for user_doc in users:
        user_id = user_doc.id
        repo = FirestoreRepository(db_client, APP_ID_TARGET, user_id)

        locations = _collect(repo)
        if not locations:
            continue

        # Passe 1 : regroupement par clé canonique
        variants_by_key = defaultdict(list)
        for raw in locations.values():
            if raw:
                variants_by_key[normalize_city_key(raw)].append(raw)

        # Deux villes homonymes de régions différentes partagent la même clé (la clé ignore la
        # région, c'est ce qui permet de réunir "montreal" et "Montréal, QC"). Les réécrire
        # ensemble fusionnerait deux villes réelles, de façon irréversible : on s'abstient.
        conflicting = {k for k, v in variants_by_key.items() if regions_conflict(v)}
        for key in sorted(conflicting):
            logger.warning(
                f"      ⚠️ '{key}' porte des régions différentes {sorted(set(variants_by_key[key]))} — "
                f"probablement deux villes homonymes distinctes, laissées telles quelles."
            )

        labels = {
            key: pick_best_label(variants)
            for key, variants in variants_by_key.items() if key not in conflicting
        }
        multi = {
            k: sorted(set(v)) for k, v in variants_by_key.items()
            if len(set(v)) > 1 and k not in conflicting
        }

        # Passe 2 : uniformisation
        fixed = 0
        for deal_id, raw in locations.items():
            if not raw:
                continue
            target = labels.get(normalize_city_key(raw))
            if target and target != raw:
                if not dry_run:
                    repo.collection_ref.document(deal_id).update({'location': target})
                    repo._update_deal_index(deal_id, location=target)
                fixed += 1

        logger.info(
            f"  {user_id[:12]}… : {len(locations)} annonces | {len(variants_by_key)} villes | "
            f"{len(multi)} ville(s) à graphies multiples | "
            f"{'à uniformiser' if dry_run else 'uniformisées'}: {fixed}"
        )
        for key, values in sorted(multi.items()):
            logger.info(f"      {labels[key]!r}  <-  {values}")

        grand_total_deals += len(locations)
        grand_total_fixed += fixed
        grand_total_variants += len(multi)

    logger.info("=" * 78)
    logger.info(
        f"TOTAL : {grand_total_deals} annonces | {grand_total_variants} ville(s) à graphies "
        f"multiples | {'à uniformiser' if dry_run else 'uniformisées'} : {grand_total_fixed}"
    )
    logger.info("=" * 78)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Audit et uniformisation des villes stockées.")
    parser.add_argument('--dry-run', action='store_true', help="Compte et affiche sans rien écrire.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
