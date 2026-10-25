"""
Vérifie TOUS les IDs Facebook des villes du catalogue (`cities`) et corrige ceux qui sont faux.

Contexte (docs/management/plans/FB_CITY_IDS_AND_SCRAPER_HEALTH_PLAN.md) : l'ID de Bromont pointait sur
Bromont-Lamothe (France) ; 8 villes sur 27 avaient un ID faux (Belgique, Royaume-Uni, ID texte...).

DEUX TEMPS, volontairement séparés — l'écriture en base ne se fait JAMAIS pendant le scan Facebook :

  1. RAPPORT (lecture seule, dry-run par défaut). Pour chaque ville : sonde de l'ID actuel
     (`/marketplace/<id>/` : ville affichée + part de cartes de la province + proximité), puis, s'il ne
     passe pas, `CityFinder.lookup` (clic par libellé, ID vérifié). Écrit/complète le rapport JSON après
     CHAQUE ville (reprise possible, ville déjà faite = ignorée).
        xvfb-run -a python -m backend.scripts.repair_fb_city_ids --user-id <UID> --report rapport.json

  2. APPLICATION, après relecture du rapport : met `cities.fb_location_id` à l'ID vérifié (la clé
     primaire, les préférences et l'historique ne bougent pas ; plusieurs villes peuvent partager un ID).
     Sans `--apply`, n'affiche que ce qui serait fait.
        python -m backend.scripts.repair_fb_city_ids --from rapport.json            # aperçu
        python -m backend.scripts.repair_fb_city_ids --from rapport.json --apply    # écrit

Statuts : OK | ALIAS_OK (ID de la ville voisine qui sert la ville, ex. Saint-Hubert -> Longueuil) |
A_CORRIGER (nouvel ID vérifié) | AMBIGU (plusieurs ID valides, ou alias non confirmable) |
INDETERMINE (fil trop maigre pour conclure) | INTROUVABLE | ECHEC (erreur technique).
Seul A_CORRIGER est appliqué. Les coordonnées douteuses sont SIGNALÉES, jamais modifiées.

Anti-bot : un seul navigateur, pauses aléatoires (20-60 s entre villes, 3-5 min toutes les 5 villes),
ordre aléatoire (ancrages d'abord), ARRÊT COMPLET sur login/captcha/checkpoint (rapport sauvegardé).
Le rapport ne contient que des noms de lieux et d'IDs — jamais de titres ni d'URLs d'annonces — et il est
ignoré par git (dépôt public). Les scripts ne lisent pas .env : `export DATABASE_URL=...`.
"""
import sys
import os
import json
import time
import random
import argparse
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, '.')

import psycopg
from psycopg.rows import dict_row

from backend.pg_db import DATABASE_URL
from backend.cities import normalize_city_key
from backend.scraping import city_verification as cv

OK = "OK"
ALIAS_OK = "ALIAS_OK"
A_CORRIGER = "A_CORRIGER"
AMBIGU = "AMBIGU"
INDETERMINE = "INDETERMINE"
INTROUVABLE = "INTROUVABLE"
ECHEC = "ECHEC"
NEEDS_LOOKUP = "NEEDS_LOOKUP"  # interne : l'ID actuel ne passe pas, on cherche le bon

DEFAULT_PROVINCE = "QC"
DEFAULT_REGION_HINT = "Québec"


# ------------------------------------------------------------------------------------------------
# Logique pure (testée sans Facebook ni base)
# ------------------------------------------------------------------------------------------------

def current_fb_id(row):
    """ID Facebook actuellement utilisé par le scraper pour cette ville (voir schema.sql)."""
    return str(row.get("fb_location_id") or row["id"])


def static_findings(rows):
    """Constats sans réseau : {clé primaire: [messages]} — ID non numérique, deux villes sur un même ID,
    doublon de graphie, coordonnées douteuses."""
    gazetteer = cv.trusted_gazetteer(rows)
    by_fb_id, by_key = defaultdict(list), defaultdict(list)
    for r in rows:
        by_fb_id[current_fb_id(r)].append(r)
        by_key[normalize_city_key(r["name"])].append(r)
    out = {}
    for r in rows:
        msgs = []
        fb_id = current_fb_id(r)
        if not fb_id.isdigit():
            msgs.append(f"ID Facebook non numérique (« {fb_id} »)")
        sharing = [o["name"] for o in by_fb_id[fb_id] if o["id"] != r["id"]]
        if sharing:
            msgs.append(f"partage son ID avec : {', '.join(sharing)}")
        dups = [o for o in by_key[normalize_city_key(r["name"])] if o["id"] != r["id"]]
        if dups:
            msgs.append("doublon de graphie dans le catalogue (voir merge_city_catalog_duplicates.py)")
        if r.get("latitude") is None or r.get("longitude") is None:
            msgs.append("coordonnées manquantes")
        elif normalize_city_key(r["name"]) not in gazetteer:
            msgs.append("coordonnées douteuses (identiques à celles d'une autre ville)")
        if msgs:
            out[r["id"]] = msgs
    return out


def expected_coords_for(row, gazetteer):
    key = normalize_city_key(row["name"])
    return gazetteer.get(key)  # None si coordonnées douteuses ou absentes -> pas de contrôle de proximité


def classify_current(row, landed_label, cards, province, gazetteer):
    """Statut de l'ID ACTUEL d'après sa sonde. Retourne (statut, détail, score)."""
    fb_id = current_fb_id(row)
    if not fb_id.isdigit():
        return NEEDS_LOOKUP, f"ID non numérique (« {fb_id} »)", None
    expected = expected_coords_for(row, gazetteer)
    score = cv.score_probe(cards, province, expected, gazetteer if expected else None)
    name_ok = cv.landed_name_matches(landed_label, row["name"])
    decision = cv.decide([{"id": fb_id, **score}])

    if decision.status == cv.VERIFIED:
        if name_ok:
            return OK, "", score
        near = score["part_near"]
        if near is not None and near >= cv.MIN_NEAR_SHARE:
            return ALIAS_OK, f"la page affiche « {cv.landed_place_name(landed_label)} » (ville voisine, proximité {near:.0%})", score
        return AMBIGU, f"ID de la province mais la page affiche « {cv.landed_place_name(landed_label)} » et la proximité n'est pas vérifiable", score
    if decision.status == cv.INDETERMINATE:
        return INDETERMINE, decision.detail, score
    return NEEDS_LOOKUP, decision.detail or f"{score['part_province']:.0%} de cartes de la province", score


def classify_lookup(row, result):
    """Statut après `CityFinder.lookup` pour une ville dont l'ID actuel ne passe pas."""
    if result.status == cv.VERIFIED:
        if str(result.city_id) == current_fb_id(row):
            return OK, "ID confirmé par la recherche", None
        return A_CORRIGER, result.detail, str(result.city_id)
    return {cv.AMBIGUOUS: AMBIGU, cv.INDETERMINATE: INDETERMINE}.get(result.status, INTROUVABLE), result.detail, None


def top_places(cards, n=4):
    """Lieux de cartes les plus fréquents (noms de lieux seulement)."""
    return Counter(c.strip() for c in cards if c and c.strip()).most_common(n)


def plan_updates(results, db_rows):
    """Plan d'application : liste de (clé primaire, 'update'|'noop'|'skip', détail). `db_rows` : {pk: ligne}.
    N'applique que A_CORRIGER, et seulement si la base est toujours dans l'état du rapport."""
    plan = []
    for pk, r in results.items():
        if r.get("status") != A_CORRIGER:
            continue
        row = db_rows.get(pk)
        if row is None:
            plan.append((pk, "skip", "ville absente de la base"))
            continue
        cur = current_fb_id(row)
        if cur == str(r["new_id"]):
            plan.append((pk, "noop", "déjà appliqué"))
        elif cur != str(r["current_id"]):
            plan.append((pk, "skip", f"la base a changé depuis le rapport (ID actuel {cur} ≠ {r['current_id']})"))
        else:
            plan.append((pk, "update", str(r["new_id"])))
    return plan


# ------------------------------------------------------------------------------------------------
# Base de données
# ------------------------------------------------------------------------------------------------

def load_rows(conn, user_id, all_catalog):
    if all_catalog or not user_id:
        sql = "SELECT id, name, latitude, longitude, fb_location_id, needs_review FROM cities ORDER BY name"
        return conn.execute(sql).fetchall()
    return conn.execute(
        """
        SELECT c.id, c.name, c.latitude, c.longitude, c.fb_location_id, c.needs_review
        FROM cities c JOIN user_city_prefs p ON p.city_id = c.id AND p.user_id = %s AND p.active
        ORDER BY c.name
        """,
        (user_id,),
    ).fetchall()


def apply_plan(conn, plan, results, db_rows, backup_dir):
    to_update = [p for p in plan if p[1] == "update"]
    if not to_update:
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(backup_dir, f"cities_backup_{stamp}.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in db_rows[pk].items()} for pk, _, _ in to_update], f, ensure_ascii=False, indent=2, default=str)
    os.chmod(backup, 0o600)
    print(f"Sauvegarde des lignes touchées : {backup}")
    done = 0
    for pk, _, new_id in to_update:
        with conn.transaction():
            row = conn.execute("SELECT id, fb_location_id FROM cities WHERE id = %s FOR UPDATE", (pk,)).fetchone()
            if row is None or current_fb_id(row) != str(results[pk]["current_id"]):
                print(f"  ⏭️  {results[pk]['name']} : changée entre-temps, ignorée.")
                continue
            conn.execute("UPDATE cities SET fb_location_id = %s, needs_review = false WHERE id = %s", (new_id, pk))
            done += 1
            print(f"  ✅ {results[pk]['name']} : {results[pk]['current_id']} -> {new_id}")
    return done


# ------------------------------------------------------------------------------------------------
# Rapport (Facebook)
# ------------------------------------------------------------------------------------------------

def save_report(path, meta, results):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "results": results}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def order_rows(rows, anchors_first_ids):
    rest = [r for r in rows if r["id"] not in anchors_first_ids]
    random.shuffle(rest)
    return [r for r in rows if r["id"] in anchors_first_ids] + rest


def run_report(args):
    from backend.scraping.core import FacebookScraper
    from backend.scraping.config import ScraperConfig
    from backend.scraping.city_finder import CityFinder, PlaywrightCityDriver, FacebookBlocked
    from backend.scraping.geo_clustering import compute_anchor_clusters

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger = logging.getLogger("repair_fb_city_ids")

    with psycopg.connect(DATABASE_URL, connect_timeout=10, row_factory=dict_row) as conn:
        rows = load_rows(conn, args.user_id, args.all_catalog)
    if args.only:
        wanted = {normalize_city_key(n) for n in args.only.split(",") if n.strip()}
        rows = [r for r in rows if normalize_city_key(r["name"]) in wanted]
    if not rows:
        print("Aucune ville à vérifier.")
        return 1

    gazetteer = cv.trusted_gazetteer(rows)
    findings = static_findings(rows)
    print(f"{len(rows)} ville(s) à vérifier.\n\n--- Constats sans réseau ---")
    for r in rows:
        for m in findings.get(r["id"], []):
            print(f"  • {r['name']:<28} {m}")
    if not findings:
        print("  (aucun)")

    usable = [r for r in rows if r.get("latitude") is not None and r.get("longitude") is not None]
    anchors = {cl.anchor["id"] for cl in compute_anchor_clusters(usable, 80)}
    print(f"\nAncrages (scannés par le bot, vérifiés en premier) : {', '.join(sorted(r['name'] for r in rows if r['id'] in anchors))}")
    if args.anchors_only:
        rows = [r for r in rows if r["id"] in anchors]

    meta = {"created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "province": args.province,
            "region_hint": args.region, "user_id": args.user_id, "all_catalog": args.all_catalog}
    results = {}
    if os.path.exists(args.report):
        with open(args.report, encoding="utf-8") as f:
            results = (json.load(f).get("results") or {})
        print(f"\nReprise : {len(results)} ville(s) déjà dans {args.report}.")

    todo = [r for r in order_rows(rows, anchors) if r["id"] not in results or args.redo]
    if args.max_cities:
        todo = todo[: args.max_cities]
    print(f"\n--- Vérification Facebook de {len(todo)} ville(s) ---")

    scraper = FacebookScraper({}, {}, config=ScraperConfig(), logger=logger)
    driver = PlaywrightCityDriver(scraper)
    blocked = False
    try:
        for i, row in enumerate(todo, 1):
            name = row["name"]
            entry = {"name": name, "current_id": current_fb_id(row), "static": findings.get(row["id"], []),
                     "coords_trusted": normalize_city_key(name) in gazetteer}
            try:
                landed, cards, score = "", [], None
                if current_fb_id(row).isdigit():
                    probe = driver.probe(current_fb_id(row))
                    landed, cards = probe.landed_label, probe.cards
                status, detail, score = classify_current(row, landed, cards, args.province, gazetteer)
                entry.update({"landed": landed, "places": top_places(cards), "score": score})
                if status == NEEDS_LOOKUP:
                    result = CityFinder.lookup(driver, name, region_hint=args.region,
                                               expected_coords=expected_coords_for(row, gazetteer),
                                               gazetteer=gazetteer if expected_coords_for(row, gazetteer) else None, logger=logger)
                    status, detail, new_id = classify_lookup(row, result)
                    entry["evidence"] = result.evidence  # une entrée par suggestion testée (libellé, ID, ville affichée, scores)
                    if new_id:
                        entry["new_id"] = new_id
                entry.update({"status": status, "detail": detail})
            except FacebookBlocked as e:
                print(f"\n🚨 Facebook a bloqué la session ({e}). Arrêt complet ; rapport sauvegardé, relance plus tard.")
                blocked = True
                break
            except Exception as e:
                entry.update({"status": ECHEC, "detail": f"{type(e).__name__}: {str(e)[:150]}"})
            results[row["id"]] = entry
            save_report(args.report, meta, results)
            flag = {OK: "✅", ALIAS_OK: "✅", A_CORRIGER: "🔧"}.get(entry["status"], "⚠️")
            print(f"  {flag} [{i}/{len(todo)}] {name:<28} {entry['status']:<12} {entry.get('current_id')}"
                  + (f" -> {entry['new_id']}" if entry.get("new_id") else "") + (f"  ({entry['detail']})" if entry["detail"] else ""))
            if i < len(todo):
                pause = random.uniform(180, 300) if i % 5 == 0 else random.uniform(args.pause_min, args.pause_max)
                time.sleep(pause)
    finally:
        scraper.close_session()

    save_report(args.report, meta, results)  # toujours un rapport en sortie, même si Facebook a bloqué dès la 1re ville
    print_summary(results)
    print(f"\nRapport : {args.report}  (relire, puis : --from {args.report} --apply)")
    return 2 if blocked else 0


def print_summary(results):
    counts = Counter(r["status"] for r in results.values())
    print("\n--- Résumé ---  " + ", ".join(f"{s}={n}" for s, n in sorted(counts.items())))
    for r in results.values():
        if r["status"] not in (OK, ALIAS_OK):
            print(f"  {r['status']:<12}{r['name']:<28}{r.get('current_id', '')!s:<20}{('-> ' + str(r['new_id'])) if r.get('new_id') else ''}  {r.get('detail', '')}")


# ------------------------------------------------------------------------------------------------
# Application
# ------------------------------------------------------------------------------------------------

def run_apply(args):
    with open(args.from_report, encoding="utf-8") as f:
        results = (json.load(f).get("results") or {})
    print_summary(results)
    with psycopg.connect(DATABASE_URL, connect_timeout=10, row_factory=dict_row) as conn:
        db_rows = {r["id"]: r for r in conn.execute(
            "SELECT id, name, latitude, longitude, fb_location_id, needs_review, created_by FROM cities WHERE id = ANY(%s)",
            (list(results),)).fetchall()}
        plan = plan_updates(results, db_rows)
        print("\n--- Plan d'application ---")
        if not plan:
            print("  Rien à corriger.")
        for pk, action, detail in plan:
            label = {"update": "🔧 CORRIGER", "noop": "✔️  déjà fait", "skip": "⏭️  ignorée"}[action]
            suffix = f"{results[pk]['current_id']} -> {detail}" if action == "update" else detail
            print(f"  {label:<14}{results[pk]['name']:<28}{suffix}")
        if not args.apply:
            print("\nAperçu seulement (aucune écriture). Ajouter --apply pour écrire.")
            return 0
        done = apply_plan(conn, plan, results, db_rows, args.backup_dir)
    print(f"\n{done} ville(s) corrigée(s). Le bot lit `fb_location_id` au prochain cycle.")
    return 0


def main():
    p = argparse.ArgumentParser(description="Vérifie et corrige les IDs Facebook des villes (rapport puis application)")
    p.add_argument("--user-id", help="Villes ACTIVES de cet utilisateur (sinon tout le catalogue)")
    p.add_argument("--all-catalog", action="store_true", help="Tout le catalogue, pas seulement les villes actives")
    p.add_argument("--only", help="Noms de villes séparés par des virgules")
    p.add_argument("--anchors-only", action="store_true", help="Seulement les villes d'ancrage")
    p.add_argument("--max-cities", type=int, help="Plafond de villes pour cette exécution")
    p.add_argument("--report", default="fb_city_repair_report.json", help="Rapport JSON (reprise automatique)")
    p.add_argument("--redo", action="store_true", help="Revérifier aussi les villes déjà dans le rapport")
    p.add_argument("--province", default=DEFAULT_PROVINCE)
    p.add_argument("--region", default=DEFAULT_REGION_HINT)
    p.add_argument("--pause-min", type=float, default=20.0)
    p.add_argument("--pause-max", type=float, default=60.0)
    p.add_argument("--from", dest="from_report", help="Appliquer un rapport relu (aperçu sans --apply)")
    p.add_argument("--apply", action="store_true", help="Écrire en base (avec --from)")
    p.add_argument("--backup-dir", default=".", help="Dossier de la sauvegarde locale des lignes modifiées")
    args = p.parse_args()
    if args.apply and not args.from_report:
        p.error("--apply exige --from <rapport.json>")
    sys.exit(run_apply(args) if args.from_report else run_report(args))


if __name__ == "__main__":
    main()
