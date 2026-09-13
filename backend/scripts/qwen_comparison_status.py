"""Lecture seule (aucune écriture Firestore, aucun appel IA) : état actuel de la comparaison
Gemini vs Qwen au rôle de Portier (Chantier H), sur toutes les annonces de production qui ont
déjà les deux verdicts (`aiAnalysis.gatekeeperVerdict` + `qwenGatekeeperVerdict`).

Sert à suivre la progression de l'échantillon (cible 150-200) et à vérifier si le schéma JSON
strict (2026-09-13, T1_GATEKEEPER_OPENAI_JSON_SCHEMA) a bien éliminé les verdicts Qwen hors
taxonomie (ex: "ACCEPTED", trouvé au run #42) sur les nouvelles annonces scannées depuis.

Usage : python -m backend.scripts.qwen_comparison_status
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from backend.analyzer import T1_VALID_STATUSES
    from config import APP_ID_TARGET

    db = setup_firebase()
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s).")

    pairs = []
    for uid in user_ids:
        deals_ref = (
            db.collection('artifacts').document(APP_ID_TARGET)
            .collection('users').document(uid).collection('guitar_deals')
        )
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            ai = deal.get('aiAnalysis') or {}
            gemini_v = ai.get('gatekeeperVerdict')
            qwen_v = ai.get('qwenGatekeeperVerdict')
            if gemini_v and qwen_v:
                pairs.append((doc.id, gemini_v, qwen_v, deal.get('timestamp')))

    print(f"📋 {len(pairs)} annonce(s) avec les deux verdicts (Gemini + Qwen).")

    REJECT_PREFIXES = ("BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE", "REJECTED")

    def classify(v):
        """'accept'/'reject', ou None si exclu (erreur Gemini ou verdict hors taxonomie
        connue -- ne peut alors pas être comparé de façon fiable)."""
        v = (v or "").upper()
        if v == "ERROR_GATEKEEPER" or v not in T1_VALID_STATUSES:
            return None
        return "reject" if v in REJECT_PREFIXES or v.startswith("REJECTED") else "accept"

    n_agree, n_disagree, n_excluded, exact_match, n_qwen_out_of_taxonomy = 0, 0, 0, 0, 0
    disagreements = []
    for deal_id, gv, qv, ts in pairs:
        if gv == qv:
            exact_match += 1
        if qv.upper() not in T1_VALID_STATUSES:
            n_qwen_out_of_taxonomy += 1
        gc, qc = classify(gv), classify(qv)
        if gc is None or qc is None:
            n_excluded += 1
            continue
        if gc == qc:
            n_agree += 1
        else:
            n_disagree += 1
            disagreements.append((deal_id, gv, qv))

    total_comparable = n_agree + n_disagree
    print(f"\n{'=' * 60}\nRésultat\n{'=' * 60}")
    print(f"Échantillon total : {len(pairs)} (cible 150-200)")
    print(f"Exclus (erreur Gemini ou verdict hors taxonomie) : {n_excluded}")
    if pairs:
        print(f"Accord exact (même chaîne) : {exact_match}/{len(pairs)} ({100 * exact_match / len(pairs):.1f}%)")
    if total_comparable:
        print(f"Accord accept/reject : {n_agree}/{total_comparable} ({100 * n_agree / total_comparable:.1f}%)")
    if pairs:
        print(f"Verdicts Qwen hors taxonomie (ex: 'ACCEPTED') : {n_qwen_out_of_taxonomy}/{len(pairs)} "
              f"({100 * n_qwen_out_of_taxonomy / len(pairs):.1f}%)")
    if disagreements:
        print("\nDésaccords accept/reject :")
        for deal_id, gv, qv in disagreements:
            print(f"  ❌ {deal_id} : Gemini={gv!r} vs Qwen={qv!r}")


if __name__ == "__main__":
    main()
