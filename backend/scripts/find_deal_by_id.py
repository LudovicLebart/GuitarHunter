"""
Diagnostic : recherche une annonce par son ID (le numéro dans l'URL Facebook/Kijiji) à travers
TOUS les utilisateurs, et rapporte si/où elle existe en base.

Contexte : chaque utilisateur possède sa propre sous-collection isolée `users/{uid}/guitar_deals`
(architecture multi-tenant, voir ARCHITECTURE.md §1) — l'ID d'une annonce ne suffit donc pas à
savoir dans quelle sous-collection chercher sans itérer les utilisateurs. `deal_id` = ID Facebook
brut (numérique), ou préfixé `kijiji_` côté Kijiji (voir bot.py).

Accepte en entrée : l'ID seul (`1234567890123`), l'ID déjà préfixé (`kijiji_1234567890123`), ou
l'URL complète de l'annonce (le premier long nombre y est extrait automatiquement).

Lookup en lecture directe par clé de document (`.get()`), pas un scan de collection — aussi peu
coûteux qu'un `fetch_deal.py` par utilisateur, jamais une requête `where()`.

Usage local (nécessite les credentials Firebase, voir README) :
    python3 backend/scripts/find_deal_by_id.py <id_ou_url>

Depuis cet environnement de dev (aucun accès Firestore) : armer via `backend/scripts/run_once.py`
(voir son docstring pour le protocole complet ACTIVE=True → déploiement → lecture des logs
GitHub Actions → ACTIVE=False dans un commit séparé).
"""
import sys
import os
import re
import logging

sys.path.insert(0, os.getcwd())

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("find_deal_by_id")


def candidate_ids(raw):
    """Normalise l'entrée (ID nu, déjà préfixé, ou URL) en liste d'IDs de document à essayer."""
    raw = raw.strip()
    if raw.startswith('kijiji_'):
        return [raw]
    digits_match = re.search(r'\d{6,}', raw)
    if not digits_match:
        return [raw]
    digits = digits_match.group(0)
    return [digits, f'kijiji_{digits}']


def run(raw_id):
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    ids_to_try = candidate_ids(raw_id)
    logger.info(f"Recherche de l'ID(s) {ids_to_try} à travers tous les utilisateurs.")

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())

    found = []
    for user_doc in users:
        user_id = user_doc.id
        deals_ref = db_client.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(user_id).collection('guitar_deals')
        for deal_id in ids_to_try:
            doc = deals_ref.document(deal_id).get()
            if doc.exists:
                found.append((user_id, deal_id, doc.to_dict()))

    if not found:
        logger.info(f"Introuvable : aucun utilisateur ne possède {ids_to_try} dans guitar_deals.")
        return

    for user_id, deal_id, data in found:
        logger.info(
            f"Trouvée : user={user_id} id={deal_id} statut={data.get('status')} "
            f"titre={data.get('title')} prix={data.get('price')} url={data.get('url')}"
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 backend/scripts/find_deal_by_id.py <id_ou_url>")
        sys.exit(1)
    run(sys.argv[1])
