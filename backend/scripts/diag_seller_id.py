"""Diagnostic (lecture seule, aucune écriture, 0 $) : les pages d'annonce exposent-elles un identifiant de VENDEUR ?

Ouvre UNE annonce Kijiji et/ou UNE annonce Facebook avec un navigateur anonyme (comme le scraper) et affiche
UNIQUEMENT la structure : noms de clés et formes de valeurs, jamais le contenu complet d'un identifiant (3 premiers
caractères + longueur), jamais de nom ni de texte de vendeur. Sert à décider si `seller_id` peut servir à détecter
les reposts (voir la discussion du 2026-10-07 sur les doublons).

À lancer sur le serveur (Playwright installé), sans DATABASE_URL :

    python -m backend.scripts.diag_seller_id \
        --kijiji "https://www.kijiji.ca/v-.../1744378028" \
        --facebook "https://www.facebook.com/marketplace/item/1683917960399986/"

Au moins une des deux options est requise. Ne rien coller d'autre que la sortie du script.
"""
import argparse
import json
import re
import sys


KEY_HINT = re.compile(r"seller|poster|user|owner|account|profile|member|author|advertiser|dealer", re.I)


def mask(value):
    """Forme d'une valeur sans l'exposer : type, et pour une chaîne/un nombre 3 premiers caractères + longueur."""
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, (int, float)):
        s = str(value)
        return f"nombre {s[:3]}… ({len(s)} chiffres)"
    if isinstance(value, str):
        return f"texte {value[:3]}… ({len(value)} car.)"
    if isinstance(value, list):
        return f"liste[{len(value)}]"
    if isinstance(value, dict):
        return f"objet({len(value)} clés)"
    return type(value).__name__


def walk(node, path, out, depth=0, max_depth=6):
    """Parcourt un JSON et collecte (chemin, forme) des clés dont le NOM évoque un vendeur/utilisateur."""
    if depth > max_depth:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if KEY_HINT.search(str(k)):
                out.append((p, mask(v)))
            walk(v, p, out, depth + 1, max_depth)
    elif isinstance(node, list):
        for i, v in enumerate(node[:3]):
            walk(v, f"{path}[{i}]", out, depth + 1, max_depth)


def diag_kijiji(page, url):
    print(f"\n=== KIJIJI ===")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)
    script = page.locator("script#__NEXT_DATA__").first
    if script.count() == 0:
        print("Pas de #__NEXT_DATA__ (page bloquée ou structure changée).")
        return
    data = json.loads(script.inner_text())
    props = data.get("props", {}).get("pageProps", {})
    apollo = props.get("__APOLLO_STATE__") or {}
    listing_id = props.get("listingId")
    print(f"listingId présent : {bool(listing_id)} ; entrées Apollo : {len(apollo)}")

    # Types d'entités présents dans l'état Apollo (ex: StandardListing, User, PosterInfo...).
    prefixes = {}
    for key in apollo:
        prefixes[str(key).split(":")[0]] = prefixes.get(str(key).split(":")[0], 0) + 1
    print("Types d'entités Apollo :", dict(sorted(prefixes.items(), key=lambda kv: -kv[1])[:20]))

    entry = apollo.get(f"StandardListing:{listing_id}") if listing_id else None
    if not isinstance(entry, dict):
        entry = next((v for k, v in apollo.items() if str(k).startswith("StandardListing:")), None)
    if isinstance(entry, dict):
        print("Clés de l'annonce :", sorted(entry.keys()))
        found = []
        walk(entry, "StandardListing", found)
        print("Clés évoquant un vendeur DANS l'annonce :")
        for p, shape in found or [("(aucune)", "")]:
            print(f"  {p} -> {shape}")
    else:
        print("Objet StandardListing introuvable.")

    found_all = []
    walk(props, "pageProps", found_all, max_depth=5)
    extra = [(p, s) for p, s in found_all if "StandardListing" not in p][:40]
    print("Autres clés évoquant un vendeur dans pageProps (40 max) :")
    for p, shape in extra or [("(aucune)", "")]:
        print(f"  {p} -> {shape}")


def diag_facebook(page, url):
    print(f"\n=== FACEBOOK ===")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)
    print("URL finale (masquée) :", re.sub(r"\d{6,}", lambda m: m.group(0)[:3] + "…", page.url))

    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    patterns = [h for h in hrefs if h and re.search(r"/marketplace/profile/|/profile\.php|/people/|/user/", h)]
    print(f"Liens de profil vendeur trouvés : {len(patterns)}")
    for h in patterns[:5]:
        print("  ", re.sub(r"\d{6,}", lambda m: m.group(0)[:3] + "…(%d)" % len(m.group(0)), h)[:120])

    html = page.content()
    hits = []
    for m in re.finditer(r'"(marketplace_listing_seller|seller|story_owner|actor_id|owner|marketplace_user_profile)"\s*:\s*(\{[^{}]{0,200})', html):
        snippet = re.sub(r'"(name|short_name|username)"\s*:\s*"[^"]*"', r'"\1":"<masqué>"', m.group(0))
        snippet = re.sub(r"\d{6,}", lambda mm: mm.group(0)[:3] + "…(%d)" % len(mm.group(0)), snippet)
        hits.append(snippet[:200])
    print(f"Blocs JSON évoquant un vendeur dans le HTML : {len(hits)}")
    for s in hits[:6]:
        print("  ", s)
    if "login" in page.url or page.locator("input[name='email']").count() > 0:
        print("⚠️ Page de connexion détectée : Facebook gate cette session anonyme.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kijiji", help="URL d'une annonce Kijiji")
    ap.add_argument("--facebook", help="URL d'une annonce Facebook Marketplace")
    args = ap.parse_args()
    if not args.kijiji and not args.facebook:
        ap.error("donner --kijiji et/ou --facebook")

    from playwright.sync_api import sync_playwright  # import tardif : les helpers restent testables sans Playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(locale="fr-CA")
        page = context.new_page()
        try:
            if args.kijiji:
                diag_kijiji(page, args.kijiji)
            if args.facebook:
                diag_facebook(page, args.facebook)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
