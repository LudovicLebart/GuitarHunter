"""Lecture seule (aucune écriture Firestore, aucun appel IA) : affiche le détail complet des
annonces passées en argument (par ID) — pensé pour inspecter à l'œil les "pépites potentiellement
ratées" identifiées par désaccord Gemini/Qwen (Chantier H) : Gemini a rejeté l'annonce (cascade
arrêtée net, jamais vue par T2/T3) alors que Qwen, en observation, penchait vers un verdict
pépite-tier (PEPITE/FAST_FLIP/LUTHIER_PROJ/CASE_WIN/COLLECTION).

Usage : python -m backend.scripts.inspect_candidate_missed_gems <deal_id> [<deal_id> ...]
"""
import os
import sys

sys.path.insert(0, os.getcwd())

# Les 2 candidats identifiés (run #42/#43, 16 annonces rejetées par Gemini au total, 2 avec un
# désaccord Qwen dans le sens "pépite") -- valeur par défaut si aucun ID n'est passé en argument.
DEFAULT_DEAL_IDS = ["2149184059355395", "1120308157236475"]


def main():
    deal_ids = sys.argv[1:] or DEFAULT_DEAL_IDS

    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s), recherche de {len(deal_ids)} annonce(s)...")

    remaining = set(deal_ids)
    for uid in user_ids:
        if not remaining:
            break
        deals_ref = (
            db.collection('artifacts').document(APP_ID_TARGET)
            .collection('users').document(uid).collection('guitar_deals')
        )
        for deal_id in list(remaining):
            doc = deals_ref.document(deal_id).get()
            if not doc.exists:
                continue
            deal = doc.to_dict()
            ai = deal.get('aiAnalysis') or {}
            print(f"\n{'=' * 70}\n{deal_id} (utilisateur {uid})\n{'=' * 70}")
            print(f"Titre        : {deal.get('title')}")
            print(f"Prix         : {deal.get('price')}$")
            print(f"Ville        : {deal.get('location')}")
            print(f"Lien         : {deal.get('link')}")
            print(f"Photos       : {len(deal.get('storageImageUrls') or deal.get('imageUrls') or [])}")
            print(f"Timestamp    : {deal.get('timestamp')}")
            print(f"--- Décision réelle (Gemini) ---")
            print(f"gatekeeperVerdict       : {ai.get('gatekeeperVerdict')}")
            print(f"gatekeeperClassification: {ai.get('gatekeeperClassification')}")
            print(f"gatekeeperBrand         : {ai.get('gatekeeperBrand')}")
            print(f"reasoning (Gemini)      : {ai.get('reasoning')}")
            print(f"--- Observation Qwen (jamais décisionnelle) ---")
            print(f"qwenGatekeeperVerdict       : {ai.get('qwenGatekeeperVerdict')}")
            print(f"qwenGatekeeperClassification: {ai.get('qwenGatekeeperClassification')}")
            print(f"qwenGatekeeperBrand         : {ai.get('qwenGatekeeperBrand')}")
            remaining.discard(deal_id)

    if remaining:
        print(f"\n⚠️ Annonce(s) introuvable(s) (peut-être purgée/déplacée) : {sorted(remaining)}")


if __name__ == "__main__":
    main()
