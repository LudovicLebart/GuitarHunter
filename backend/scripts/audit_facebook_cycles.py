"""
Diagnostic (2026-08-24) : liste les résumés de cycle Facebook ("📊 Résumé du cycle Facebook : ...")
de tous les utilisateurs depuis un horodatage donné, avec le nombre de villes bloquées par
anti-bot extrait de chaque ligne — pour comparer AVANT/APRÈS un déploiement donné et distinguer
une régression introduite par ce déploiement d'un problème préexistant (IP/proxy flaggé,
changement de comportement côté Facebook, etc.).

Lit `users/{uid}/logs` (TTL Firestore 3 jours — rien de plus ancien n'existe de toute façon),
filtré côté client sur `createdAt >= since_epoch` puis sur les messages contenant "Résumé du
cycle Facebook" (Firestore ne supporte pas de recherche par sous-chaîne côté serveur).

Usage local :
    python3 backend/scripts/audit_facebook_cycles.py <since_epoch_unix>
"""
import sys
import os
import re
import logging

sys.path.insert(0, os.getcwd())

from config import APP_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("audit_facebook_cycles")

BLOCKED_RE = re.compile(r'(\d+) ville\(s\) bloqu[ée]e\(s\) par anti-bot')


def run(since_epoch):
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db_client = db_service.db
    if not db_client:
        logger.error("Erreur de connexion à Firebase.")
        return

    users_ref = db_client.collection('artifacts').document(APP_ID_TARGET).collection('users')
    users = list(users_ref.stream())
    logger.info(f"{len(users)} utilisateur(s), logs depuis epoch={since_epoch}.")

    for user_doc in users:
        user_id = user_doc.id
        logs_ref = db_client.collection('artifacts').document(APP_ID_TARGET) \
            .collection('users').document(user_id).collection('logs')
        docs = list(logs_ref.where('createdAt', '>=', since_epoch).order_by('createdAt').stream())
        cycles = [d.to_dict() for d in docs if 'Résumé du cycle Facebook' in (d.to_dict().get('message') or '')]
        if not cycles:
            continue
        logger.info(f"--- user={user_id} : {len(cycles)} cycle(s) Facebook, {len(docs)} logs lus ---")
        for c in cycles:
            msg = c.get('message', '')
            m = BLOCKED_RE.search(msg)
            blocked = m.group(1) if m else '?'
            logger.info(f"  createdAt={c.get('createdAt')} villes_bloquées={blocked} | {msg}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 backend/scripts/audit_facebook_cycles.py <since_epoch_unix>")
        sys.exit(1)
    run(float(sys.argv[1]))
