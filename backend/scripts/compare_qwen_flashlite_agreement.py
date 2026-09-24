"""
Diagnostic en lecture seule, SANS appel Gemini (Chantier H, suite à `audit_rejected_gems.py`
et sa discussion du 2026-09-19) : compare directement les métadonnées déjà stockées sur chaque
annonce — le verdict Gemini/Flash-Lite vs le verdict Qwen — sur TOUTES les annonces analysées
depuis le 2026-09-13, tous utilisateurs confondus.

Mise à jour 2026-09-20 (bascule `T1_GATEKEEPER_PROVIDER=qwen` en production) : `gatekeeperVerdict`
(le champ "décideur réel") ne désigne plus un fournisseur fixe — avant la bascule c'était
Flash-Lite, depuis c'est Qwen. Le fournisseur non-décideur écrit son verdict en miroir dans
`qwenGatekeeperVerdict` OU `flashliteGatekeeperVerdict` selon lequel des deux n'était PAS
décideur pour cette annonce (voir `analyzer.py::_run_t1_shadow_observation`). Ce script
reconstruit donc la paire (verdict Gemini, verdict Qwen) par déduction : si
`qwenGatekeeperVerdict` est présent, Gemini était décideur (`gatekeeperVerdict` = Gemini) ; si
c'est `flashliteGatekeeperVerdict` qui est présent, Qwen était décideur (`gatekeeperVerdict` =
Qwen) — plutôt que de supposer un sens fixe, ce qui romprait silencieusement la collecte de
données pour toute annonce analysée après la bascule.

**Objectif recadré avec l'utilisateur (2026-09-19)** : ce n'est PAS un test de précision de
Qwen. Un faux positif de Qwen (il signale une pépite qui n'en est pas) ne coûte qu'une
ré-analyse T2 à ~0,008$ (négligeable) — voir `audit_rejected_gems.py`, déjà mesuré (8 faux
positifs sur 8 désaccords, run #49). Le SEUL cas qui compterait vraiment si Qwen devenait un
jour LE Portier de production : le RAPPEL — une annonce que Flash-Lite accepte aujourd'hui et
que Qwen aurait rejetée serait une opportunité perdue DÉFINITIVEMENT (contrairement à un faux
positif, jamais revue par la suite). C'est ce cas ("Gemini accepte, Qwen aurait rejeté") que ce
script met en avant, pas l'inverse (déjà couvert par `audit_rejected_gems.py`).

Aucune écriture Firestore, aucun appel Gemini/Qwen — lecture pure des champs déjà en base.
Coût : zéro. Ne nécessite donc pas de repasser par le mécanisme `run_script.yml` en scratch (le
job SSH suffit pour la connectivité Firestore), et peut être relancé aussi souvent que voulu.

Usage : python -m backend.scripts.compare_qwen_flashlite_agreement
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark", "results")

# T1_VALID_STATUSES / sous-ensemble de rejet (backend/analyzer.py) — dupliqués ici (pas
# d'import direct) pour que ce script reste lisible seul et ne dépende pas d'un import lourd
# d'analyzer.py (google.generativeai) juste pour ces constantes.
T1_VALID_STATUSES = frozenset({
    "PEPITE", "FAST_FLIP", "LUTHIER_PROJ", "CASE_WIN", "COLLECTION",
    "FAIR", "BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE",
})
T1_REJECTION_VERDICTS = frozenset({"BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE"})


def _is_rejected(verdict):
    return verdict in T1_REJECTION_VERDICTS


def main():
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()
    users_ref = db.collection("artifacts").document(APP_ID_TARGET).collection("users")
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s).")

    both_present = []
    n_excluded_error = 0
    for uid in user_ids:
        deals_ref = (
            db.collection("artifacts").document(APP_ID_TARGET)
            .collection("users").document(uid).collection("guitar_deals")
        )
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            ai = deal.get("aiAnalysis") or {}
            real_verdict = ai.get("gatekeeperVerdict")
            # `gatekeeperVerdict` (le décideur réel) désigne Gemini avant la bascule du
            # 2026-09-20, Qwen depuis — déduit ici annonce par annonce via lequel des deux
            # champs miroir est renseigné, plutôt que supposé fixe (voir docstring du module).
            shadow_qwen = ai.get("qwenGatekeeperVerdict")
            shadow_flashlite = ai.get("flashliteGatekeeperVerdict")
            if shadow_qwen:
                gemini_verdict, qwen_verdict = real_verdict, shadow_qwen
            elif shadow_flashlite:
                gemini_verdict, qwen_verdict = shadow_flashlite, real_verdict
            else:
                continue
            if not gemini_verdict or not qwen_verdict:
                continue
            # Exclut les cas où l'un des deux appels a lui-même échoué (ex: `ERROR_GATEKEEPER`,
            # hors T1_VALID_STATUSES) — pas un vrai désaccord de jugement, juste un appel raté.
            # Bug trouvé le 2026-09-19 : la 1ère version comptait ERROR_GATEKEEPER comme un
            # "accept" par défaut, gonflant à tort le taux de désaccord coûteux (62 → 21 réels).
            if gemini_verdict not in T1_VALID_STATUSES or qwen_verdict not in T1_VALID_STATUSES:
                n_excluded_error += 1
                continue
            both_present.append((doc.id, deal, gemini_verdict, qwen_verdict))

    n = len(both_present)
    print(f"📦 {n} annonce(s) avec les deux verdicts VALIDES (Gemini + Qwen) disponibles depuis le 2026-09-13 "
          f"({n_excluded_error} exclue(s) pour cause de verdict hors taxonomie, ex: ERROR_GATEKEEPER — appel raté, pas un vrai désaccord).\n")

    if n == 0:
        print("Rien à comparer — l'observation Qwen n'a peut-être pas encore accumulé assez de données.")
        return

    agree_accept = agree_reject = 0
    gemini_accept_qwen_reject = []  # LE cas qui compte (coût = rappel, opportunité perdue)
    gemini_reject_qwen_accept = []  # déjà audité en réel avec de vrais appels T2 (run #49)

    for deal_id, deal, gv, qv in both_present:
        g_rej, q_rej = _is_rejected(gv), _is_rejected(qv)
        if not g_rej and not q_rej:
            agree_accept += 1
        elif g_rej and q_rej:
            agree_reject += 1
        elif not g_rej and q_rej:
            gemini_accept_qwen_reject.append((deal_id, deal, gv, qv))
        else:
            gemini_reject_qwen_accept.append((deal_id, deal, gv, qv))

    print(f"{'=' * 60}\nRÉSUMÉ\n{'=' * 60}")
    print(f"Total avec les deux verdicts : {n}")
    print(f"  Accord ACCEPT/ACCEPT : {agree_accept} ({100 * agree_accept / n:.1f}%)")
    print(f"  Accord REJECT/REJECT : {agree_reject} ({100 * agree_reject / n:.1f}%)")
    print(f"  Gemini ACCEPTE, Qwen aurait REJETÉ (coûteux si bascule, rappel) : "
          f"{len(gemini_accept_qwen_reject)} ({100 * len(gemini_accept_qwen_reject) / n:.1f}%)")
    print(f"  Gemini REJETTE, Qwen aurait ACCEPTÉ (déjà audité en réel, run #49 : 0/8 confirmées) : "
          f"{len(gemini_reject_qwen_accept)} ({100 * len(gemini_reject_qwen_accept) / n:.1f}%)")

    if gemini_accept_qwen_reject:
        print(f"\n{'=' * 60}\nDÉTAIL — Gemini accepte, Qwen aurait rejeté (n={len(gemini_accept_qwen_reject)})\n{'=' * 60}")
        for deal_id, deal, gv, qv in gemini_accept_qwen_reject:
            ai = deal.get("aiAnalysis") or {}
            print(f"- {deal_id} : '{deal.get('title', '')[:60]}' — Gemini={gv} Qwen={qv} "
                  f"deal_score={ai.get('deal_score')} resto={ai.get('restoration_interest_score')}")
            print(f"    lien original : {deal.get('link') or '(absent)'}")
            # Verdict/raisonnement réel du Tier 2/3 (demande utilisateur, 2026-09-20) : plutôt
            # que de rouvrir chaque fiche dans l'app, autant lire l'analyse déjà écrite en base
            # par la cascade réelle de production (verdict/reasoning, écrits par
            # _run_analysis_cascade — voir backend/analyzer.py) — absente pour les FAIR
            # (deal_score=None), jamais promues au Tier 2 sous la config de recherche active.
            if ai.get("verdict") or ai.get("reasoning"):
                print(f"    verdict T2/T3 réel : {ai.get('verdict')}")
                reasoning = (ai.get("reasoning") or "").strip()
                if reasoning:
                    print(f"    raisonnement : {reasoning[:400]}")
            else:
                print(f"    (pas d'analyse Tier 2 en base — probablement NOT_PROMOTED)")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "compare_qwen_flashlite_agreement.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "n_total": n,
            "agree_accept": agree_accept,
            "agree_reject": agree_reject,
            "gemini_accept_qwen_reject": [
                {
                    "id": deal_id,
                    "title": deal.get("title"),
                    "link": deal.get("link"),
                    "gemini_verdict": gv,
                    "qwen_verdict": qv,
                    "deal_score": (deal.get("aiAnalysis") or {}).get("deal_score"),
                    "restoration_interest_score": (deal.get("aiAnalysis") or {}).get("restoration_interest_score"),
                    "t2_verdict": (deal.get("aiAnalysis") or {}).get("verdict"),
                    "t2_reasoning": (deal.get("aiAnalysis") or {}).get("reasoning"),
                }
                for deal_id, deal, gv, qv in gemini_accept_qwen_reject
            ],
            "gemini_reject_qwen_accept_count": len(gemini_reject_qwen_accept),
        }, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
