"""Chantier 0.a (validation) : les annonces à prix 0$ sont-elles ré-analysées en boucle ?

Bug trouvé par une consultation Opus indépendante (2026-09-13, branche
`claude/guitarhunter-benchmark-setup-h9q9gr`) : `bot.py::handle_deal_found()` déduplique via
`if old_p > 0 and old_p == new_p: return "duplicate_unchanged"` — une annonce déjà stockée à
`price = 0` (gratuite, ou prix gaté par Facebook pour une session non authentifiée, déjà
documenté dans CLAUDE.md) a `old_p = 0`, donc cette condition est TOUJOURS fausse : l'annonce
est repassée dans toute la cascade (T1 minimum, potentiellement plus) à chaque cycle de scan
où elle réapparaît, indéfiniment — jamais reconnue comme "déjà vue".

Candidat sérieux pour expliquer le facteur 2,4x du volume mystère du Chantier 0.a (95→229
annonces/jour, jamais confirmé) — et il frappe T1 à 100%, contrairement aux autres causes déjà
explorées cette session (ré-analyses par baisse de prix, ~4,8% seulement, voir run #34).

Méthode, lecture seule : `published_at_ts` (date de publication réelle de l'annonce, parsée au
scraping, jamais réécrite ensuite) donne l'âge RÉEL de l'annonce, indépendamment de `timestamp`
(réécrit à SERVER_TIMESTAMP à chaque ré-analyse, voir `repository.py`). Un grand écart entre
les deux pour les annonces à prix 0$ — largement supérieur à celui des annonces à prix normal —
est un signe direct de ré-analyses répétées bien après la publication initiale.

Usage : python -m backend.scripts.audit_price_zero_loop
"""
import os
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())


def _normalize_price(price):
    try:
        return float(str(price).replace(',', '.').replace('$', '').strip())
    except (ValueError, TypeError):
        return 0.0


def _gap_days(timestamp, published_at_ts):
    """Écart en jours entre `timestamp` (dernier passage, Firestore SERVER_TIMESTAMP) et
    `published_at_ts` (date de publication réelle, unix timestamp, jamais réécrite)."""
    if timestamp is None or published_at_ts is None:
        return None
    try:
        ts_dt = timestamp if hasattr(timestamp, "timestamp") else None
        if ts_dt is None:
            return None
        ts_unix = ts_dt.timestamp()
        published_unix = float(published_at_ts)
        return (ts_unix - published_unix) / 86400.0
    except (ValueError, TypeError, OSError):
        return None


def main():
    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s).")

    buckets = {"price_zero": [], "price_normal": []}
    total_docs = 0
    price_zero_examples = []

    for uid in user_ids:
        deals_ref = (
            db.collection('artifacts').document(APP_ID_TARGET)
            .collection('users').document(uid).collection('guitar_deals')
        )
        for doc in deals_ref.stream():
            deal = doc.to_dict()
            total_docs += 1
            price = _normalize_price(deal.get('price'))
            gap = _gap_days(deal.get('timestamp'), deal.get('published_at_ts'))
            bucket = "price_zero" if price <= 0 else "price_normal"
            buckets[bucket].append(gap)
            if bucket == "price_zero" and gap is not None and len(price_zero_examples) < 10:
                price_zero_examples.append({
                    "id": doc.id, "title": deal.get("title"),
                    "gap_days": round(gap, 1), "status": deal.get("status"),
                })

    n_zero = len(buckets["price_zero"])
    n_normal = len(buckets["price_normal"])
    pct_zero = round(100 * n_zero / total_docs, 2) if total_docs else None

    print(f"\n{'=' * 60}\nRésultat\n{'=' * 60}")
    print(f"{total_docs} annonce(s) au total. {n_zero} ({pct_zero}%) à prix 0$/invalide.")

    for label, key in (("Prix 0$", "price_zero"), ("Prix normal", "price_normal")):
        gaps = [g for g in buckets[key] if g is not None]
        n_missing_published = len(buckets[key]) - len(gaps)
        if gaps:
            print(f"\n{label} (n={len(buckets[key])}, {n_missing_published} sans published_at_ts) :")
            print(f"  Écart timestamp/publication — médiane : {statistics.median(gaps):.1f}j, "
                  f"moyenne : {statistics.mean(gaps):.1f}j, max : {max(gaps):.1f}j")
            n_over_7d = sum(1 for g in gaps if g > 7)
            print(f"  {n_over_7d}/{len(gaps)} ({100*n_over_7d/len(gaps):.1f}%) avec écart > 7 jours "
                  f"(re-touchées bien après leur publication réelle)")
        else:
            print(f"\n{label} : aucune donnée exploitable (published_at_ts absent sur tous les items).")

    if price_zero_examples:
        print("\nExemples (prix 0$, écart le plus grand en premier) :")
        for ex in sorted(price_zero_examples, key=lambda e: -e["gap_days"])[:5]:
            print(f"  - {ex['id']} : '{ex['title']}' — écart {ex['gap_days']}j, status={ex['status']}")

    print(f"\n{'=' * 60}\nInterprétation\n{'=' * 60}")
    zero_gaps = [g for g in buckets["price_zero"] if g is not None]
    normal_gaps = [g for g in buckets["price_normal"] if g is not None]
    if zero_gaps and normal_gaps:
        med_zero, med_normal = statistics.median(zero_gaps), statistics.median(normal_gaps)
        if med_zero > med_normal * 2:
            print(f"Écart médian des annonces à prix 0$ ({med_zero:.1f}j) nettement supérieur à celui "
                  f"des annonces à prix normal ({med_normal:.1f}j) — cohérent avec des ré-analyses "
                  f"répétées bien après la publication (bug de dédup old_p>0 suspecté confirmé).")
        else:
            print(f"Écart médian comparable entre prix 0$ ({med_zero:.1f}j) et prix normal ({med_normal:.1f}j) "
                  f"— ne confirme pas d'emblée une boucle de ré-analyse systématique sur cet échantillon.")


if __name__ == "__main__":
    main()
