"""Amorçage SOURCÉ de la base de connaissances « univers des guitares » (STRATEGIE_IA.md §3.4/§3.7).

Charge des fiches écrites à la main depuis des fichiers JSON versionnés dans `backend/knowledge/seed/` :
marques, séries et usines que Wikidata ne connaît pas (Vantage, Profile, les marques de la famille Godin...).
C'est la voie d'entrée des recherches sourcées (pages Wikipédia, sites de collectionneurs, fabricants).

RÈGLES (une fiche fausse dans le prompt d'un petit modèle est pire que pas de fiche) :
- Chaque fiche DOIT citer au moins une source (URL, éditeur, courte citation qui appuie la fiche).
- Le niveau de confiance est CALCULÉ, jamais déclaré : `sourced` si au moins 2 éditeurs (domaines) distincts,
  sinon `single_source` — conservée en base mais JAMAIS injectée dans le prompt du Portier.
- N'écrire que ce que les sources concordantes disent : une date ou un rattachement contesté est omis.
- Idempotent. N'écrase JAMAIS `hunt_notes`, ni les alias / sources ajoutés à la main ; `tier` et `made_by`
  déjà curés en base ne sont remplacés que si le fichier en fournit une valeur.

Format d'une entrée (liste JSON, ou {"entries": [...]}) :
    {"slug": "vantage", "kind": "brand", "name": "Vantage", "description": "…", "parent": "Godin",
     "made_by": ["Matsumoku"], "countries": ["Canada"], "active_from": 1979, "active_to": null,
     "relevance": "guitars", "tier": "entry", "aliases": ["Vantage Guitars"],
     "sources": [{"url": "https://…", "publisher": "…", "kind": "collector", "title": "…", "lang": "en",
                  "license": "copyright", "excerpt": "courte citation (300 caractères max)"}]}
Un `excerpt` qui n'est PAS une citation mot pour mot (résumé de la page, titre d'annonce) commence par « [résumé] ».
CORRIGER UNE FICHE EXISTANTE (import Wikidata) : entrée « patch » — la surcharge que l'import n'écrasera jamais :
    {"patch": "Vox", "relevance_override": "guitars", "hunt_notes": "…faits sourcés…", "tier": "mid",
     "made_by": ["Matsumoku"], "aliases": ["…"], "sources": [au moins 2 éditeurs distincts]}
`patch` = nom EXACT unique (ou id) de la fiche à corriger. Une correction exige AU MOINS 2 sources de domaines
distincts (changer la pertinence d'une marque est plus risqué que d'ajouter une fiche). `hunt_notes` n'est posé que
s'il est vide (jamais d'écrasement de tes notes) ; `relevance_override` et `tier` remplacent la valeur actuelle.
`name_as_alias: false` : ne PAS utiliser le nom seul comme alias (nom trop courant, ex. « Profile », aussi une marque
d'accordeurs) ; seuls les alias listés sont alors reconnus.
`parent` / `made_by` : nom EXACT d'une fiche existante (ou id `wd:Q…` / `manual:slug`) ; un nom ambigu est refusé.

Usage (serveur, mêmes variables que l'import) :
    export DATABASE_URL="$(grep -h '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | tr -d '\\r')"
    python backend/scripts/seed_guitar_knowledge.py --dry-run          # valide et affiche, n'écrit rien
    python backend/scripts/seed_guitar_knowledge.py                    # écrit
    python backend/scripts/seed_guitar_knowledge.py --file backend/knowledge/seed/batch1_godin_vantage_profile.json
"""
import argparse
import glob
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.guitar_knowledge import alias_usable, normalize  # noqa: E402

SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge", "seed")
KINDS = {"company", "brand", "line", "factory", "luthier"}
RELEVANCES = {"guitars", "accessories", "unknown"}
TIERS = {"entry", "mid", "high", "boutique"}
SOURCE_KINDS = {"wikidata", "wikipedia", "wikipedia_list", "collector", "manufacturer", "forum", "marketplace",
                "press", "other"}
MAX_EXCERPT = 300


class SeedError(ValueError):
    pass


def domain(url):
    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


# Hébergeurs où chaque sous-domaine est un éditeur DIFFÉRENT (un blog n'est pas l'autre).
SHARED_HOSTS = {"blogspot.com", "wordpress.com", "fandom.com", "github.io", "substack.com", "medium.com",
                "tumblr.com", "wixsite.com", "weebly.com"}


def publisher_key(url):
    """Éditeur indépendant d'une URL : le domaine « racine » (en.wikipedia.org et fr.wikipedia.org = UN éditeur,
    Wikipédia), sauf sur les hébergeurs de blogs où chaque sous-domaine est un auteur distinct."""
    labels = domain(url).split(".")
    root = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if root in SHARED_HOSTS and len(labels) >= 3 else root


def confidence_of(sources):
    """`sourced` si au moins 2 éditeurs indépendants (voir `publisher_key`), sinon `single_source`."""
    return "sourced" if len({publisher_key(s["url"]) for s in sources}) >= 2 else "single_source"


PATCH_KEYS = {"patch", "relevance_override", "hunt_notes", "tier", "made_by", "aliases", "sources", "_file"}


def _validate_sources(label, sources):
    problems = []
    for i, src in enumerate(sources, 1):
        where = f"{label} source #{i}"
        if not str(src.get("url", "")).startswith(("http://", "https://")):
            problems.append(f"{where} : url http(s) manquante")
        if not src.get("publisher"):
            problems.append(f"{where} : éditeur (publisher) manquant")
        if src.get("kind") and src["kind"] not in SOURCE_KINDS:
            problems.append(f"{where} : kind « {src['kind']} » inconnu")
        excerpt = src.get("excerpt") or ""
        if not excerpt:
            problems.append(f"{where} : citation (excerpt) manquante — dire ce que cette source appuie")
        elif len(excerpt) > MAX_EXCERPT:
            problems.append(f"{where} : citation trop longue ({len(excerpt)} > {MAX_EXCERPT}) — une citation courte, pas l'article")
    urls = [s.get("url") for s in sources]
    if len(urls) != len(set(urls)):
        problems.append(f"{label} : URL de source en double")
    return problems


def validate_patch(entry):
    """Correction d'une fiche existante : au moins 2 sources de domaines distincts, champs limités."""
    label = f"patch « {entry.get('patch')} »"
    problems = []
    unknown = set(entry) - PATCH_KEYS
    if unknown:
        problems.append(f"{label} : champs non autorisés dans un patch : {', '.join(sorted(unknown))}")
    if not any(entry.get(k) for k in ("relevance_override", "hunt_notes", "tier", "made_by", "aliases")):
        problems.append(f"{label} : rien à corriger (relevance_override, hunt_notes, tier, made_by ou aliases)")
    if entry.get("relevance_override") and entry["relevance_override"] not in RELEVANCES:
        problems.append(f"{label} : relevance_override invalide ({', '.join(sorted(RELEVANCES))})")
    if entry.get("tier") and entry["tier"] not in TIERS:
        problems.append(f"{label} : tier invalide")
    sources = entry.get("sources") or []
    problems += _validate_sources(label, sources)
    if len({publisher_key(s.get("url", "")) for s in sources}) < 2:
        problems.append(f"{label} : une correction exige AU MOINS 2 sources de sites distincts")
    for alias in entry.get("aliases") or []:
        if not alias_usable(normalize(alias)):
            problems.append(f"{label} : alias « {alias} » inexploitable (trop court, numérique ou générique)")
    return problems


def validate_entry(entry):
    """Renvoie la liste des problèmes de l'entrée (vide = valide)."""
    if entry.get("patch"):
        return validate_patch(entry)
    problems = []
    label = entry.get("name") or entry.get("slug") or "?"
    for key in ("slug", "kind", "name", "description"):
        if not entry.get(key):
            problems.append(f"{label} : champ « {key} » manquant")
    if entry.get("kind") and entry["kind"] not in KINDS:
        problems.append(f"{label} : kind « {entry['kind']} » inconnu ({', '.join(sorted(KINDS))})")
    if entry.get("relevance", "guitars") not in RELEVANCES:
        problems.append(f"{label} : relevance invalide")
    if entry.get("tier") and entry["tier"] not in TIERS:
        problems.append(f"{label} : tier invalide")
    slug = entry.get("slug") or ""
    if slug and (slug != slug.lower() or " " in slug):
        problems.append(f"{label} : slug « {slug} » doit être en minuscules sans espaces")
    for key in ("active_from", "active_to"):
        if entry.get(key) is not None and not isinstance(entry[key], int):
            problems.append(f"{label} : {key} doit être une année (entier)")
    sources = entry.get("sources") or []
    if not sources:
        problems.append(f"{label} : AUCUNE source — une fiche sans source est refusée")
    problems += _validate_sources(label, sources)
    for alias in entry.get("aliases") or []:
        if not alias_usable(normalize(alias)):
            problems.append(f"{label} : alias « {alias} » inexploitable (trop court, numérique ou générique)")
    return problems


def load_entries(paths):
    entries = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        items = data["entries"] if isinstance(data, dict) else data
        for item in items:
            item["_file"] = os.path.basename(path)
            entries.append(item)
    slugs = [e.get("slug") or (f"patch:{e['patch']}" if e.get("patch") else None) for e in entries]
    dups = {s for s in slugs if s and slugs.count(s) > 1}
    if dups:
        raise SeedError(f"slugs en double : {', '.join(sorted(dups))}")
    return entries


def resolve_ref(conn, ref, entry_ids, include_accessories=False):
    """Résout un `parent` / `made_by` en id de fiche : id direct, slug du même lot, ou nom exact UNIQUE.
    `include_accessories` : pour la CIBLE d'une correction (patch), qui est justement souvent classée
    « accessories » à tort (Vox, Supro)."""
    if ref.startswith(("wd:", "manual:")):
        return ref
    if f"manual:{ref}" in entry_ids:
        return f"manual:{ref}"
    rows = conn.execute(f"""SELECT id, kind, name FROM guitar_knowledge
                            WHERE lower(name) = lower(%s){'' if include_accessories else " AND relevance <> 'accessories'"}""",
                        (ref,)).fetchall()
    if len(rows) > 1:
        preferred = [r for r in rows if r["kind"] in ("company", "brand", "factory")]
        rows = preferred if len(preferred) == 1 else rows
    if not rows:
        raise SeedError(f"« {ref} » : aucune fiche de ce nom (donner un id wd:Q… / manual:slug, ou l'ajouter au lot)")
    if len(rows) > 1:
        raise SeedError(f"« {ref} » : ambigu, {len(rows)} fiches (" +
                        ", ".join(f"{r['id']} [{r['kind']}]" for r in rows) + ") — donner l'id exact")
    return rows[0]["id"]


def plan(conn, entries):
    """Valide tout le lot et résout les références. Lève SeedError avec TOUS les problèmes trouvés."""
    problems, planned = [], []
    for entry in entries:
        problems += validate_entry(entry)
    entry_ids = {f"manual:{e['slug']}" for e in entries if e.get("slug")}
    if problems:
        raise SeedError("\n".join(problems))
    for entry in entries:
        if entry.get("patch"):
            try:
                target = resolve_ref(conn, entry["patch"], entry_ids, include_accessories=True)
                made_by = [resolve_ref(conn, m, entry_ids) for m in entry.get("made_by") or []]
            except SeedError as e:
                problems.append(f"patch « {entry['patch']} » : {e}")
                continue
            planned.append({**entry, "_patch": True, "target_id": target, "made_by_ids": made_by,
                            "name": entry["patch"]})
            continue
        try:
            parent = resolve_ref(conn, entry["parent"], entry_ids) if entry.get("parent") else None
            made_by = [resolve_ref(conn, m, entry_ids) for m in entry.get("made_by") or []]
        except SeedError as e:
            problems.append(f"{entry['name']} : {e}")
            continue
        planned.append({**entry, "id": f"manual:{entry['slug']}", "parent_id": parent, "made_by_ids": made_by,
                        "confidence": confidence_of(entry["sources"])})
    if problems:
        raise SeedError("\n".join(problems))
    return planned


def write(conn, planned, notes=None):
    """Écrit le lot dans UNE NOUVELLE VERSION de la base (non validée) : les fiches créées ou corrigées prennent ce
    numéro et ne sont donc utilisées par le Portier qu'après `UPDATE guitar_knowledge_versions SET validated = true
    WHERE version = N` (STRATEGIE_IA.md §3.6) — un amorçage n'entre jamais en prod sans le rejeu de non-régression."""
    previous = conn.execute("SELECT MAX(version) AS v FROM guitar_knowledge_versions").fetchone()
    previous = previous["v"] if isinstance(previous, dict) else previous[0]
    if not previous:
        raise SeedError("aucune version de la base : lancer d'abord import_guitar_knowledge_wikidata.py")
    version = previous + 1
    with conn.transaction():
        conn.execute("INSERT INTO guitar_knowledge_versions (version, source, notes, counts) VALUES (%s,'seed',%s,%s)",
                     (version, notes or "amorçage sourcé : " + ", ".join(sorted({e.get("_file", "?") for e in planned})),
                      json.dumps({"fiches": sum(1 for e in planned if not e.get("_patch")),
                                  "corrections": sum(1 for e in planned if e.get("_patch"))})))
        for e in planned:
            if e.get("_patch"):
                _write_patch(conn, e, version)
                continue
            conn.execute("""
                INSERT INTO guitar_knowledge (id, kind, name, description, parent_id, countries, active_from, active_to,
                    relevance, tier, made_by, curated, source, confidence, kb_version, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,'manual',%s,%s,now())
                ON CONFLICT (id) DO UPDATE SET
                    kind = EXCLUDED.kind, name = EXCLUDED.name, description = EXCLUDED.description,
                    parent_id = EXCLUDED.parent_id, countries = EXCLUDED.countries,
                    active_from = EXCLUDED.active_from, active_to = EXCLUDED.active_to,
                    relevance = EXCLUDED.relevance, confidence = EXCLUDED.confidence,
                    tier = COALESCE(EXCLUDED.tier, guitar_knowledge.tier),
                    made_by = COALESCE(EXCLUDED.made_by, guitar_knowledge.made_by),
                    curated = true, kb_version = EXCLUDED.kb_version, updated_at = now()
                -- hunt_notes : JAMAIS touché""",
                         (e["id"], e["kind"], e["name"], e["description"], e["parent_id"], e.get("countries") or None,
                          e.get("active_from"), e.get("active_to"), e.get("relevance", "guitars"), e.get("tier"),
                          e["made_by_ids"] or None, e["confidence"], version))
            names = ([e["name"]] if e.get("name_as_alias", True) else []) + list(e.get("aliases") or [])
            for alias in dict.fromkeys(names):
                norm = normalize(alias)
                if alias_usable(norm):
                    conn.execute("""INSERT INTO guitar_knowledge_alias (alias_norm, knowledge_id, alias, source)
                                    VALUES (%s,%s,%s,'manual') ON CONFLICT DO NOTHING""", (norm, e["id"], alias))
            for src in e["sources"]:
                conn.execute("""
                    INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, title, publisher, lang, license, excerpt, origin)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'manual')
                    ON CONFLICT (knowledge_id, url) DO UPDATE SET kind = EXCLUDED.kind, title = EXCLUDED.title,
                        publisher = EXCLUDED.publisher, lang = EXCLUDED.lang, license = EXCLUDED.license,
                        excerpt = EXCLUDED.excerpt, origin = 'manual'""",
                             (e["id"], src["url"], src.get("kind") or "other", src.get("title"), src["publisher"],
                              src.get("lang"), src.get("license"), src["excerpt"]))
    return version


def _write_patch(conn, e, version):
    """Corrige une fiche existante sans jamais écraser tes notes : `hunt_notes` seulement s'il est vide."""
    conn.execute("""
        UPDATE guitar_knowledge SET
            relevance_override = COALESCE(%s, relevance_override),
            tier = COALESCE(%s, tier),
            made_by = COALESCE(%s, made_by),
            hunt_notes = COALESCE(hunt_notes, %s),
            curated = true, kb_version = %s, updated_at = now()
        WHERE id = %s""", (e.get("relevance_override"), e.get("tier"), e["made_by_ids"] or None,
                           e.get("hunt_notes"), version, e["target_id"]))
    for alias in e.get("aliases") or []:
        norm = normalize(alias)
        if alias_usable(norm):
            conn.execute("""INSERT INTO guitar_knowledge_alias (alias_norm, knowledge_id, alias, source)
                            VALUES (%s,%s,%s,'manual') ON CONFLICT DO NOTHING""", (norm, e["target_id"], alias))
    for src in e["sources"]:
        conn.execute("""
            INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, title, publisher, lang, license, excerpt, origin)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'manual')
            ON CONFLICT (knowledge_id, url) DO UPDATE SET kind = EXCLUDED.kind, title = EXCLUDED.title,
                publisher = EXCLUDED.publisher, lang = EXCLUDED.lang, license = EXCLUDED.license,
                excerpt = EXCLUDED.excerpt, origin = 'manual'""",
                     (e["target_id"], src["url"], src.get("kind") or "other", src.get("title"), src["publisher"],
                      src.get("lang"), src.get("license"), src["excerpt"]))


def print_plan(planned):
    print(f"{len(planned)} entrée(s) valide(s) :")
    for e in planned:
        if e.get("_patch"):
            changes = [k for k in ("relevance_override", "hunt_notes", "tier", "made_by", "aliases") if e.get(k)]
            print(f"  [correction   ] {e['name']} → {e['target_id']} | {', '.join(changes)}"
                  + (f" = {e['relevance_override']}" if e.get("relevance_override") else "")
                  + f" | {len(e['sources'])} source(s) : {', '.join(sorted({domain(s['url']) for s in e['sources']}))}")
        else:
            _print_fiche(e)
    single = [e["name"] for e in planned if not e.get("_patch") and e["confidence"] == "single_source"]
    if single:
        print(f"\n⚠️ {len(single)} fiche(s) à source unique — enregistrées mais JAMAIS injectées tant qu'une 2e source "
              f"indépendante n'est pas ajoutée : {', '.join(single)}")


def _print_fiche(e):
    made = f" | fabriquée par {', '.join(e['made_by_ids'])}" if e["made_by_ids"] else ""
    parent = f" | parent {e['parent_id']}" if e["parent_id"] else ""
    print(f"  [{e['confidence']:13s}] {e['name']} ({e['kind']}/{e.get('relevance', 'guitars')}){parent}{made}"
          f" | {len(e['sources'])} source(s) : {', '.join(sorted({domain(s['url']) for s in e['sources']}))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", action="append", help="fichier JSON à charger (défaut : tout backend/knowledge/seed/*.json)")
    ap.add_argument("--dry-run", action="store_true", help="valide et affiche, n'écrit rien")
    ap.add_argument("--notes", default=None, help="note attachée à la version créée")
    args = ap.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL non défini : ce script ne lit pas .env. Voir l'en-tête du fichier.")
    paths = args.file or sorted(glob.glob(os.path.join(SEED_DIR, "*.json")))
    if not paths:
        raise SystemExit(f"aucun fichier de fiches dans {SEED_DIR}")
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True)
    try:
        if args.dry_run:
            conn.read_only = True
        else:
            from backend import pg_db
            pg_db.init_pool()        # applique schema.sql (colonne `confidence`, table des sources)
        planned = plan(conn, load_entries(paths))
        print_plan(planned)
        if args.dry_run:
            print("\n(dry-run : rien écrit)")
            return
        version = write(conn, planned, args.notes)
        print(f"\n✅ {len(planned)} entrée(s) écrite(s) dans la version {version} de la base (NON validée : utilisée par le "
              f"Portier seulement après le rejeu, puis UPDATE guitar_knowledge_versions SET validated = true WHERE "
              f"version = {version};).")
    except SeedError as e:
        raise SystemExit(f"❌ {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
