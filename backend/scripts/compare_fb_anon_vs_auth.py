"""
Compare le scraper Facebook Marketplace en mode anonyme (production) et connecté. Script unique :
connexion (si besoin) -> ID de ville (si besoin) -> scans anonyme/connecté -> tableau + rapport.

Lecture seule : réutilise FacebookScraper.scan_marketplace() tel quel, sans écriture en base ni
analyse IA. Les deux modes tournent avec la même requête, ville, budget et ordre de tri.

Réglages : lus dans la config Postgres de ton utilisateur (`--user-id`, ou l'unique utilisateur de
la base) : `scanConfig` (search_query, min_price, max_price, max_ads) et villes actives
(liste blanche + ancrage, comme le bot : rayon `FACEBOOK_ANCHOR_RADIUS_KM`). Tout argument CLI
l'emporte sur la config. Exporter `DATABASE_URL` avant (les scripts ne lisent pas `.env`).

Identifiants : FB_EMAIL / FB_PASSWORD, lus dans l'environnement ou dans --env-file
(défaut ~/.facebook_test.env, hors dépôt). La session est mise en cache dans --storage-state
(ignoré par git) et réutilisée tant qu'elle est valide.

Usage serveur (Xvfb, connexion automatique) :
    export DATABASE_URL=...
    xvfb-run -a python -m backend.scripts.compare_fb_anon_vs_auth --user-id <UID> --runs 3
    (ajouter --city-name "Saint-Bruno" pour choisir la ville parmi les tiennes ; sinon l'ancrage
     du plus gros cluster)

Usage poste avec écran, connexion manuelle (checkpoint, code de sécurité) : ajouter --manual-login.
--city-id/--city-name/--query/--min-price/--max-price/--max-ads/--allowed surchargent la config. --relogin force une nouvelle connexion.

Le rapport détaillé (IDs d'annonces seulement, aucun titre ni URL) est écrit dans
fb_compare_<horodatage>.json, ignoré par git (dépôt public).
"""
import os
import sys
import json
import time
import argparse
import logging

sys.path.insert(0, '.')

from playwright.sync_api import sync_playwright

from backend.scraping.core import FacebookScraper
from backend.scraping.config import ScraperConfig
from backend.scraping.parser import ListingParser
from backend.scraping.geo_clustering import compute_anchor_clusters

ANCHOR_RADIUS_KM = 80  # = GuitarHunterBot.FACEBOOK_ANCHOR_RADIUS_KM

DEFAULT_STATE = os.path.expanduser("~/facebook_storage_state.json")
DEFAULT_ENV_FILE = os.path.expanduser("~/.facebook_test.env")


def load_env_file(path):
    """Charge KEY=VALUE dans os.environ sans écraser l'existant. Ignore un fichier absent."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _new_context(p, cfg, state_path=None):
    browser = p.chromium.launch(
        headless=cfg.headless,
        args=["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-sandbox"],
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 900}, user_agent=cfg.user_agent,
        locale=cfg.locale, timezone_id=cfg.timezone,
        storage_state=state_path if state_path and os.path.exists(state_path) else None,
    )
    return browser, context


def _is_logged_in(page):
    page.goto("https://www.facebook.com/marketplace/", timeout=60000)
    time.sleep(3)
    url = page.url
    if any(x in url for x in ("/login", "checkpoint", "two_step")):
        return False
    return any(c["name"] == "c_user" for c in page.context.cookies())


def ensure_session(state_path, relogin, manual):
    """Garantit un storage_state connecté valide dans state_path. Retourne True si OK."""
    cfg = ScraperConfig()
    with sync_playwright() as p:
        browser, context = _new_context(p, cfg, None if relogin else state_path)
        try:
            page = context.new_page()
            if not relogin and os.path.exists(state_path) and _is_logged_in(page):
                print(f"✅ Session existante valide ({state_path}).")
                return True

            if manual:
                page.goto("https://www.facebook.com/login", timeout=60000)
                print("\n👉 Connecte-toi dans la fenêtre (codes de sécurité inclus), ouvre Marketplace.")
                input("   Appuie sur Entrée ici une fois connecté...\n")
            else:
                email, pwd = os.environ.get("FB_EMAIL"), os.environ.get("FB_PASSWORD")
                if not email or not pwd:
                    print("❌ FB_EMAIL / FB_PASSWORD introuvables (environnement ou --env-file).")
                    return False
                page.goto("https://www.facebook.com/login", timeout=60000)
                for label in ("Allow all cookies", "Decline optional cookies", "Autoriser tous les cookies"):
                    try:
                        page.get_by_role("button", name=label).click(timeout=2000)
                        break
                    except Exception:
                        pass
                page.fill("input[name='email']", email)
                page.fill("input[name='pass']", pwd)
                page.keyboard.press("Enter")
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                time.sleep(5)
                if any(x in page.url for x in ("checkpoint", "two_step", "/login")):
                    shot = "fb_login_failed.png"
                    try:
                        page.screenshot(path=shot)
                    except Exception:
                        shot = "(capture impossible)"
                    print(f"❌ Connexion automatique bloquée (checkpoint ou identifiants refusés). "
                          f"URL: {page.url} — capture: {shot}\n"
                          f"   Relance avec --manual-login sur un poste avec écran.")
                    return False

            if not _is_logged_in(page):
                print("❌ Session non connectée après la tentative de login.")
                return False
            context.storage_state(path=state_path)
            os.chmod(state_path, 0o600)
            print(f"✅ Session sauvegardée dans {state_path}")
            return True
        finally:
            browser.close()


def load_user_setup(user_id):
    """Config Postgres de l'utilisateur : (uid, scanConfig, villes actives). Lecture seule."""
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
    from backend.pg_db import DATABASE_URL
    from backend.pg_repository import PostgresRepository

    pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=2, kwargs={"row_factory": dict_row}, open=True)
    try:
        if not user_id:
            with pool.connection() as conn:
                uids = [r["uid"] for r in conn.execute("SELECT uid FROM users").fetchall()]
            if len(uids) != 1:
                print(f"❌ {len(uids)} utilisateurs en base — précise --user-id parmi : {', '.join(uids)}")
                return None
            user_id = uids[0]
        repo = PostgresRepository(pool, user_id, logger=logging.getLogger("fb_compare"))
        config = repo.get_user_config()
        if not config:
            print(f"❌ Utilisateur {user_id} introuvable.")
            return None
        return user_id, (config.get("scanConfig") or {}), repo.get_cities()
    finally:
        pool.close()


def pick_city(cities, wanted_name):
    """Ville à scanner : celle demandée (parmi les villes actives), sinon l'ancrage du plus gros
    cluster — exactement ce que le bot scanne pour cette zone."""
    if wanted_name:
        norm = ListingParser.normalize_city_name(wanted_name)
        for c in cities:
            if ListingParser.normalize_city_name(c.get("name", "")) == norm:
                return c
        print(f"⚠️ '{wanted_name}' n'est pas dans tes villes actives — ancrage du plus gros cluster utilisé.")
    clusters = compute_anchor_clusters(cities, ANCHOR_RADIUS_KM)
    return max(clusters, key=lambda cl: len(cl.members)).anchor


def resolve_city_id(city_name, logger):
    scraper = FacebookScraper({}, {}, config=ScraperConfig(), logger=logger)
    try:
        city_id, _ = scraper.get_city_id_and_coords(city_name)
    finally:
        scraper.close_session()
    return city_id


def run_mode(label, storage_state, args, allowed, logger):
    cfg = ScraperConfig(storage_state_path=storage_state)
    scraper = FacebookScraper({}, {args.location_key: args.city_id}, allowed_cities=allowed, config=cfg, logger=logger)
    scan_config = {
        "search_query": args.query, "location": args.location_key,
        "min_price": args.min_price, "max_price": args.max_price, "max_ads": args.max_ads,
    }
    t0 = time.time()
    try:
        res = scraper.scan_marketplace(scan_config)
    finally:
        scraper.close_session()
    deals = res["deals"]
    n = len(deals)
    return {
        "mode": label,
        "duration_s": round(time.time() - t0, 1),
        "anti_bot_blocked": res["anti_bot_blocked"],
        "total_cards_seen": res["total_cards_seen"],
        "rejected_out_of_list": res["rejected_out_of_list"],
        "dropped_no_location": res["dropped_no_location"],
        "dropped_no_price": res["dropped_no_price"],
        "kept": n,
        "kept_with_photos": sum(1 for d in deals if d.get("imageUrls")),
        "kept_with_description": sum(1 for d in deals if len(d.get("description") or "") > 80),
        "kept_with_gps": sum(1 for d in deals if d.get("latitude")),
        "kept_with_publish_date": sum(1 for d in deals if d.get("published_at_raw")),
        "avg_photos": round(sum(len(d.get("imageUrls") or []) for d in deals) / n, 2) if n else 0,
        "ids": [d["id"] for d in deals],
    }


def pct(part, whole):
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def print_table(rows):
    print(f"\n{'mode':<12}{'cartes':>8}{'hors zone':>11}{'sans prix':>11}{'gardées':>9}{'photos':>8}{'desc.':>8}{'GPS':>7}{'date':>7}{'bloqué':>8}{'durée':>8}")
    for r in rows:
        k = r["kept"]
        print(f"{r['mode']:<12}{r['total_cards_seen']:>8}"
              f"{r['rejected_out_of_list']:>5} ({pct(r['rejected_out_of_list'], r['total_cards_seen']):>4})"
              f"{r['dropped_no_price']:>11}{k:>9}"
              f"{pct(r['kept_with_photos'], k):>8}{pct(r['kept_with_description'], k):>8}"
              f"{pct(r['kept_with_gps'], k):>7}{pct(r['kept_with_publish_date'], k):>7}"
              f"{str(r['anti_bot_blocked']):>8}{r['duration_s']:>7}s")


def main():
    parser = argparse.ArgumentParser(description="Compare Facebook Marketplace anonyme vs connecté (lecture seule)")
    parser.add_argument("--user-id", help="UID de l'utilisateur dont on reprend la config (défaut : l'unique utilisateur)")
    parser.add_argument("--query")
    parser.add_argument("--city-id", help="ID numérique Facebook de la ville (sinon recherché via --city-name)")
    parser.add_argument("--city-name", help="Nom de la ville, pour retrouver l'ID automatiquement")
    parser.add_argument("--allowed", default="", help="Villes autorisées, séparées par des virgules")
    parser.add_argument("--min-price", type=int)
    parser.add_argument("--max-price", type=int)
    parser.add_argument("--max-ads", type=int)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--storage-state", default=DEFAULT_STATE)
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--manual-login", action="store_true", help="Connexion manuelle (poste avec écran)")
    parser.add_argument("--relogin", action="store_true", help="Ignorer la session en cache")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger = logging.getLogger("fb_compare")
    load_env_file(args.env_file)

    scan_cfg, cities, city = {}, [], None
    if not (args.city_id and args.query):
        setup = load_user_setup(args.user_id)
        if setup is None:
            sys.exit(1)
        uid, scan_cfg, cities = setup
        print(f"Config de l'utilisateur {uid[:8]}… : {len(cities)} villes actives")
        if cities and not args.city_id:
            city = pick_city(cities, args.city_name)
            args.city_id, args.city_name = str(city["id"]), city["name"]

    args.query = args.query or scan_cfg.get("search_query")
    if args.min_price is None: args.min_price = scan_cfg.get("min_price", 0)
    if args.max_price is None: args.max_price = scan_cfg.get("max_price", 1500)
    if args.max_ads is None: args.max_ads = scan_cfg.get("max_ads", 40)
    if not args.query:
        parser.error("--query requis (aucune search_query dans la config)")
    if not args.city_id and not args.city_name:
        parser.error("--city-id ou --city-name est requis (aucune ville active dans la config)")

    allowed_names = [c.strip() for c in args.allowed.split(",") if c.strip()] or [c["name"] for c in cities if c.get("name")]
    allowed = {ListingParser.normalize_city_name(c) for c in allowed_names}
    args.location_key = ListingParser.normalize_city_name(args.city_name) if args.city_name else str(args.city_id)
    print(f"Requête='{args.query}'  budget={args.min_price}-{args.max_price}$  max_ads={args.max_ads}  "
          f"ville={args.city_name or '?'} ({args.city_id or 'ID à rechercher'})  liste blanche={len(allowed)} villes")

    print("=== 1/3 Session connectée ===")
    if not ensure_session(args.storage_state, args.relogin, args.manual_login):
        sys.exit(1)

    if not args.city_id:
        print(f"\n=== 2/3 Recherche de l'ID de '{args.city_name}' ===")
        args.city_id = resolve_city_id(args.city_name, logger)
        if not args.city_id:
            print("❌ ID de ville introuvable via l'interface. Relance avec --city-id.")
            sys.exit(1)
        print(f"✅ ID: {args.city_id}")
    else:
        print(f"\n=== 2/3 ID de ville fourni: {args.city_id} ===")

    print("\n=== 3/3 Comparaison ===")
    rows = []
    for i in range(args.runs):
        print(f"\n--- Passage {i + 1}/{args.runs} ---")
        rows.append(run_mode("anonyme", None, args, allowed, logger))
        rows.append(run_mode("connecté", args.storage_state, args, allowed, logger))
        print_table(rows[-2:])

    if args.runs > 1:
        print("\n=== Tous les passages ===")
        print_table(rows)

    anon = {x for r in rows if r["mode"] == "anonyme" for x in r["ids"]}
    auth = {x for r in rows if r["mode"] == "connecté" for x in r["ids"]}
    print(f"\nAnnonces gardées : anonyme={len(anon)}  connecté={len(auth)}  "
          f"communes={len(anon & auth)}  seulement connecté={len(auth - anon)}  seulement anonyme={len(anon - auth)}")

    out = f"fb_compare_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"args": vars(args), "runs": rows}, f, ensure_ascii=False, indent=2)
    print(f"Rapport détaillé (IDs uniquement) : {out}")


if __name__ == "__main__":
    main()
