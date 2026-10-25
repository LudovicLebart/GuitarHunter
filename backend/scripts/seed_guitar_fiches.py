"""Chargement des fiches techniques de restauration (`docs/fiches/*.md`) dans la base commune
`guitar_knowledge` (kind 'fiche', id 'fiche:<slug>') — mêmes règles que l'amorçage des marques
(`seed_guitar_knowledge.py`), dont il réutilise la validation des sources, la confiance et la résolution des références.

Les fichiers Markdown restent la SOURCE DE VÉRITÉ (on les modifie en session de chat, puis on recharge) :
- En-tête `clé: valeur` en tête de fichier (voir `docs/fiches/_GABARIT.md`) : slug (= nom du fichier), titre,
  categorie, difficulte, duree, statut, revision ; `alias:` (expressions qui retrouvent la fiche, séparées par des
  virgules) ; `concerne:` (marques ou séries auxquelles la fiche s'applique, noms EXACTS de fiches de marques ;
  absent = fiche générale).
- Sources : section « Sources et liens », une puce par source `- [Éditeur : titre](url) : ce que la source appuie`.
  Une fiche SANS source est refusée ; la confiance est CALCULÉE (`sourced` si ≥ 2 éditeurs distincts).
- Renvois entre fiches : liens relatifs `autre-fiche.md`, vérifiés (le fichier doit exister).

RÈGLES :
- Idempotent : une fiche dont le contenu (`content_hash`) n'a pas changé n'est pas réécrite (`--force` pour forcer).
- Une fiche NE CRÉE JAMAIS de version de la base (`guitar_knowledge_versions`) et prend `kb_version = 0` : sinon une
  version « validée » ferait entrer au Portier une amorce de marques non rejouée. Le Portier ne lit de toute façon
  que les types de marques (`guitar_knowledge.BRAND_KINDS`).
- Les alias, sources et liens d'origine « fiche » sont réécrits à chaque chargement de la fiche (ce qui a été retiré du
  fichier disparaît) ; ceux ajoutés à la main ne sont jamais touchés.
- Le mode normal ne supprime aucune fiche ; `--prune --yes` retire de la base celles dont le fichier n'existe plus
  (refusé si `docs/fiches/_GABARIT.md` est absent : dossier incomplet ou mauvais chemin).

Usage (serveur, mêmes variables que l'import ; ce script ne lit pas .env) :
    export DATABASE_URL="$(grep -h '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | tr -d '\\r')"
    python backend/scripts/seed_guitar_fiches.py --dry-run          # valide et affiche, n'écrit rien
    python backend/scripts/seed_guitar_fiches.py                    # écrit
    python backend/scripts/seed_guitar_fiches.py --file docs/fiches/reglage-truss-rod.md --force
"""
import argparse
import datetime
import glob
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.guitar_knowledge import (BRAND_KINDS, FICHE_KINDS, FICHE_STOP, MAX_EXCERPT, confidence_of,  # noqa: E402
                                      domain, fiche_alias_usable, fiche_id, normalize, valid_fiche_slug, validate_sources)
from backend.scripts.seed_guitar_knowledge import SeedError, resolve_ref  # noqa: E402

FICHES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "fiches")
# Mêmes valeurs que `RESTORATION_CATEGORIES` (src/constants/restorationPlan.js) : une fiche se range dans la
# catégorie de l'étape de restauration à laquelle elle sert.
CATEGORIES = {"structurel", "cosmetique", "electronique", "quincaillerie", "reglage", "autre"}
STATUTS = {"brouillon", "en_revision", "validee"}
LIST_KEYS = {"alias", "concerne"}
REQUIRED_KEYS = ("slug", "titre", "categorie", "difficulte", "duree", "statut", "revision")
# Type de source déduit du site quand la puce n'en dit pas plus (voir SOURCE_KINDS) ; « other » par défaut.
PUBLISHER_KINDS = {"martinguitar.com": "manufacturer", "gibson.com": "manufacturer", "fender.com": "manufacturer",
                   "premierguitar.com": "press", "wikipedia.org": "wikipedia", "youtube.com": "other"}
# URL : parenthèses tolérées si elles sont équilibrées sur un niveau (Wikipédia : `Les_Paul_(guitare)`).
SOURCE_RE = re.compile(r"^\s*[-*]\s+\[(?P<label>[^\]]+)\]\((?P<url>https?://(?:[^()\s]|\([^()\s]*\))+)\)\s*(?::\s*(?P<note>.+))?$")
BULLET_RE = re.compile(r"^\s*[-*]\s+\S")
SOURCES_TITLE = "Sources et liens"
# Marqueur d'une fiche complète dans docs/fiches/ : sans lui, `--prune` refuse de supprimer quoi que ce soit.
SENTINEL = "_GABARIT.md"
MD_LINK_RE = re.compile(r"\]\((?P<target>[^)\s#]+\.md)(?:#[^)]*)?\)")


def split_front_matter(text):
    """(en-tête, corps) : l'en-tête est un bloc `---` de lignes `clé: valeur` (commentaire `# …` toléré après une
    espace), sans YAML. Les clés de `LIST_KEYS` sont des listes séparées par des virgules."""
    # La fermeture est une ligne ENTIÈRE `---` (pas `----` ni `--- x`).
    m = re.match(r"\A---[ \t]*\r?\n(?:(.*?)\r?\n)?---[ \t]*(?:\r?\n|\Z)(.*)\Z", text, re.S)
    if not m:
        raise SeedError("en-tête `---` manquant en tête de fichier")
    meta = {}
    for line in (m.group(1) or "").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise SeedError(f"ligne d'en-tête illisible : « {line} »")
        key, value = line.split(":", 1)
        # Commentaire = `#` précédé d'une espace ET suivi d'une espace ou de la fin (« Réglage #1 » reste intact).
        value = re.split(r"\s+#(?:\s|$)", value, maxsplit=1)[0].strip()
        key = key.strip()
        meta[key] = [v.strip() for v in value.split(",") if v.strip()] if key in LIST_KEYS else value
    return meta, m.group(2)


def section(body, title):
    """Texte de la section dont le titre (`##` ou `###`) COMMENCE par `title` (« Sources et liens utiles » passe),
    jusqu'au prochain titre de niveau égal ou supérieur ; None si absente."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^(#{{2,3}})\s+{re.escape(title)}\b.*$", line, re.I)
        if not m:
            continue
        level, out = len(m.group(1)), []
        for nxt in lines[i + 1:]:
            h = re.match(r"^(#{1,6})\s", nxt)
            if h and len(h.group(1)) <= level:
                break
            out.append(nxt)
        return "\n".join(out)
    return None


def parse_sources(body):
    """(sources, puces illisibles) de la section « Sources et liens » : une puce `[Éditeur : titre](url) : note` par
    source. Éditeur = texte avant « : » du lien, sinon le domaine ; la note (ce que la source appuie) devient la
    citation, préfixée « [résumé] » (c'est un résumé, pas une citation mot pour mot). Une puce qui ne suit pas ce
    format est RAPPORTÉE (jamais ignorée en silence : elle ferait perdre une source, donc de la confiance)."""
    text = section(body, SOURCES_TITLE) or ""
    sources, unparsed = [], []
    for line in text.splitlines():
        m = SOURCE_RE.match(line)
        if not m:
            if BULLET_RE.match(line):
                unparsed.append(line.strip())
            continue
        label, url, note = m.group("label").strip(), m.group("url"), (m.group("note") or "").strip()
        publisher, _, title = label.partition(" : ")
        if not title:
            publisher, title = domain(url), label
        host = domain(url)
        kind = next((k for d, k in PUBLISHER_KINDS.items() if host == d or host.endswith("." + d)), "other")
        excerpt = f"[résumé] {note}" if note else ""
        sources.append({"url": url, "publisher": publisher.strip(), "kind": kind, "title": title.strip(),
                        "lang": None, "license": "copyright", "excerpt": excerpt[:MAX_EXCERPT] if excerpt else ""})
    return sources, unparsed


def summary_of(body):
    """Résumé : le premier bloc de citation (`> …`) après le titre, sur une ligne."""
    lines = []
    for line in body.splitlines():
        if line.startswith(">"):
            lines.append(line.lstrip("> ").strip())
        elif lines:
            break
    return " ".join(lines)


def load_fiche(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    meta, body = split_front_matter(text)
    sources, unparsed = parse_sources(body)
    return {"path": path, "file": os.path.basename(path), "meta": meta, "body": body.strip() + "\n",
            "sources": sources, "unparsed_sources": unparsed, "summary": summary_of(body),
            "file_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def validate_fiche(f, known_slugs):
    """Problèmes de la fiche (liste vide = valide)."""
    meta = f["meta"]
    label = f["file"]
    problems = [f"{label} : champ « {k} » manquant" for k in REQUIRED_KEYS if not meta.get(k)]
    slug = meta.get("slug") or ""
    if slug and slug != os.path.splitext(f["file"])[0]:
        problems.append(f"{label} : slug « {slug} » différent du nom du fichier")
    if slug and not valid_fiche_slug(slug):
        problems.append(f"{label} : slug « {slug} » invalide (a-z, 0-9 et tirets, 80 caractères au plus : l'API "
                        f"n'ouvrirait pas la fiche)")
    if meta.get("categorie") and meta["categorie"] not in CATEGORIES:
        problems.append(f"{label} : categorie « {meta['categorie']} » inconnue ({', '.join(sorted(CATEGORIES))})")
    if meta.get("statut") and meta["statut"] not in STATUTS:
        problems.append(f"{label} : statut « {meta['statut']} » inconnu ({', '.join(sorted(STATUTS))})")
    if meta.get("difficulte") and not (meta["difficulte"].isdigit() and 1 <= int(meta["difficulte"]) <= 5):
        problems.append(f"{label} : difficulte doit être un entier de 1 à 5")
    if meta.get("revision"):
        try:
            datetime.date.fromisoformat(meta["revision"])
        except ValueError:
            problems.append(f"{label} : revision « {meta['revision']} » n'est pas une date AAAA-MM-JJ")
    for bullet in f["unparsed_sources"]:
        problems.append(f"{label} : puce de source illisible « {bullet[:80]} » — format attendu "
                        f"`- [Éditeur : titre](url) : ce que la source appuie`")
    if not f["sources"] and not f["unparsed_sources"]:
        found = section(f["body"], SOURCES_TITLE) is not None
        problems.append(f"{label} : AUCUNE source — une fiche sans source est refusée "
                        + ("(la section existe mais ne contient aucune puce `- [Éditeur : titre](url) : ce que la source appuie`)"
                           if found else f"(section `## {SOURCES_TITLE}` introuvable)"))
    problems += validate_sources(label, f["sources"])
    for alias in meta.get("alias", []):
        if not fiche_alias_usable(normalize(alias)):
            problems.append(f"{label} : alias « {alias} » inexploitable (trop court, numérique, générique ou "
                            f"composé de mots trop courants : une fiche se retrouve par une expression précise)")
    if meta.get("titre") and not any(fiche_alias_usable(normalize(a)) for a in [meta["titre"], *meta.get("alias", [])]):
        problems.append(f"{label} : aucun alias exploitable (titre compris) : la fiche serait introuvable — "
                        f"ajouter `alias:` avec des expressions précises")
    for m in MD_LINK_RE.finditer(f["body"]):
        target = m.group("target")
        if target.startswith(("http://", "https://", "/")) or os.path.dirname(target):
            continue
        if os.path.splitext(target)[0] not in known_slugs:
            problems.append(f"{label} : renvoi vers « {target} » qui n'existe pas dans docs/fiches/")
    return problems


def list_paths(paths=None):
    paths = paths or sorted(glob.glob(os.path.join(FICHES_DIR, "*.md")))
    return [p for p in paths if not os.path.basename(p).startswith("_") and os.path.basename(p) != "README.md"]


def _has_fiche_tables(conn):
    """Les tables des fiches existent-elles ? Un `--dry-run` (lecture seule) peut tourner AVANT le premier chargement
    réel, qui est ce qui applique `schema.sql` : il valide alors sans comparer à la base."""
    row = conn.execute("SELECT to_regclass('guitar_knowledge_fiche') AS t, to_regclass('guitar_knowledge_link') AS l").fetchone()
    return bool(row["t"] and row["l"])


def resolve_brand(conn, ref):
    """Marque ou série désignée par `concerne:` : un nom EXACT unique, ou un id `wd:Q…` / `manual:slug` qui doit
    EXISTER et être une fiche de marque (`resolve_ref` laisse passer ces préfixes sans vérifier : l'insertion du lien
    échouerait alors sur la clé étrangère, au milieu de la transaction, sans nommer la fiche fautive)."""
    if ref.startswith(("wd:", "manual:")):
        row = conn.execute("SELECT id FROM guitar_knowledge WHERE id = %s AND kind = ANY(%s)",
                           (ref, list(BRAND_KINDS))).fetchone()
        if not row:
            raise SeedError(f"« {ref} » : aucune fiche de marque avec cet id")
        return ref
    return resolve_ref(conn, ref, set())


def fingerprint(f):
    """Empreinte de TOUT ce qui détermine ce qu'on écrit en base : le fichier, les règles d'alias (`FICHE_STOP`) et
    les marques visées. Un changement de règle ou de marque rejoue donc la fiche sans `--force`."""
    parts = [f["file_hash"], ",".join(sorted(FICHE_STOP)), ",".join(sorted(f["concerne_ids"]))]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def plan(conn, paths, known_slugs=None, force=False):
    """Valide tout le lot, résout `concerne:` et marque les fiches inchangées. Lève SeedError avec TOUS les problèmes."""
    fiches, problems = [], []
    for path in paths:
        try:
            fiches.append(load_fiche(path))
        except SeedError as e:
            problems.append(f"{os.path.basename(path)} : {e}")
    known = set(known_slugs) if known_slugs is not None else {os.path.splitext(os.path.basename(p))[0] for p in list_paths()}
    known |= {f["meta"].get("slug") for f in fiches}
    slugs = [f["meta"].get("slug") for f in fiches]
    for dup in {s for s in slugs if s and slugs.count(s) > 1}:
        problems.append(f"slug en double : {dup}")
    for f in fiches:
        problems += validate_fiche(f, known)
    if problems:
        raise SeedError("\n".join(problems))
    tables = _has_fiche_tables(conn)
    stored = {r["knowledge_id"]: r["content_hash"] for r in conn.execute(
        "SELECT knowledge_id, content_hash FROM guitar_knowledge_fiche").fetchall()} if tables else {}
    planned = []
    for f in fiches:
        slug = f["meta"]["slug"]
        f["id"] = fiche_id(slug)
        f["confidence"] = confidence_of(f["sources"])
        try:
            f["concerne_ids"] = [resolve_brand(conn, ref) for ref in f["meta"].get("concerne", [])]
        except SeedError as e:
            problems.append(f"{f['file']} : concerne : {e}")
            continue
        f["content_hash"] = fingerprint(f)
        # Inchangée = même empreinte ET ses liens vers les marques existent toujours (une marque supprimée puis
        # recréée sous le même id emporte le lien avec elle : il faut le rétablir).
        links_ok = not tables or all(conn.execute(
            "SELECT 1 FROM guitar_knowledge_link WHERE from_id = %s AND to_id = %s AND rel = 'fiche_pour'",
            (brand_id, f["id"])).fetchone() for brand_id in f["concerne_ids"])
        f["unchanged"] = not force and stored.get(f["id"]) == f["content_hash"] and links_ok
        planned.append(f)
    if problems:
        raise SeedError("\n".join(problems))
    return planned


def write(conn, planned):
    """Écrit les fiches modifiées. Aucune version créée, `kb_version = 0` (voir l'en-tête du module)."""
    written = 0
    with conn.transaction():
        for f in planned:
            if f["unchanged"]:
                continue
            meta, fid = f["meta"], f["id"]
            conn.execute("""
                INSERT INTO guitar_knowledge (id, kind, name, description, relevance, curated, source, confidence,
                                              kb_version, updated_at)
                VALUES (%s,%s,%s,%s,'guitars',true,'manual',%s,0,now())
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description,
                    kind = EXCLUDED.kind, relevance = 'guitars', relevance_override = NULL, curated = true,
                    source = 'manual', confidence = EXCLUDED.confidence, kb_version = 0, updated_at = now()""",
                         (fid, FICHE_KINDS[0], meta["titre"], f["summary"] or None, f["confidence"]))
            conn.execute("""
                INSERT INTO guitar_knowledge_fiche (knowledge_id, body_md, categorie, difficulte, duree, statut,
                                                    revision, content_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (knowledge_id) DO UPDATE SET body_md = EXCLUDED.body_md, categorie = EXCLUDED.categorie,
                    difficulte = EXCLUDED.difficulte, duree = EXCLUDED.duree, statut = EXCLUDED.statut,
                    revision = EXCLUDED.revision, content_hash = EXCLUDED.content_hash""",
                         (fid, f["body"], meta["categorie"], int(meta["difficulte"]) if meta.get("difficulte") else None,
                          meta.get("duree"), meta["statut"], meta["revision"], f["content_hash"]))
            # Alias, sources, liens d'origine « fiche » : réécrits (ce qui a quitté le fichier disparaît).
            conn.execute("DELETE FROM guitar_knowledge_alias WHERE knowledge_id = %s AND source = 'fiche'", (fid,))
            for alias in dict.fromkeys([meta["titre"], *meta.get("alias", [])]):
                norm = normalize(alias)
                if fiche_alias_usable(norm):
                    conn.execute("""INSERT INTO guitar_knowledge_alias (alias_norm, knowledge_id, alias, source)
                                    VALUES (%s,%s,%s,'fiche') ON CONFLICT DO NOTHING""", (norm, fid, alias))
            conn.execute("DELETE FROM guitar_knowledge_source WHERE knowledge_id = %s AND origin = 'fiche'", (fid,))
            for src in f["sources"]:
                conn.execute("""
                    INSERT INTO guitar_knowledge_source (knowledge_id, url, kind, title, publisher, lang, license, excerpt, origin)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'fiche')
                    ON CONFLICT (knowledge_id, url) DO NOTHING""",
                             (fid, src["url"], src["kind"], src["title"], src["publisher"], src["lang"], src["license"],
                              src["excerpt"]))
            conn.execute("DELETE FROM guitar_knowledge_link WHERE to_id = %s AND origin = 'fiche'", (fid,))
            for brand_id in f["concerne_ids"]:
                conn.execute("""INSERT INTO guitar_knowledge_link (from_id, to_id, rel, origin)
                                VALUES (%s,%s,'fiche_pour','fiche') ON CONFLICT DO NOTHING""", (brand_id, fid))
            written += 1
    return written


def orphans(conn, planned):
    """Fiches en base dont le fichier n'existe plus (ou n'est pas dans le lot chargé en entier)."""
    if not _has_fiche_tables(conn):
        return []
    present = {f["id"] for f in planned}
    return [r["knowledge_id"] for r in conn.execute("SELECT knowledge_id FROM guitar_knowledge_fiche").fetchall()
            if r["knowledge_id"] not in present]


def prune(conn, ids):
    with conn.transaction():
        for fid in ids:
            conn.execute("DELETE FROM guitar_knowledge WHERE id = %s AND kind = ANY(%s)", (fid, list(FICHE_KINDS)))


def prune_decision(prune_asked, dry_run, confirmed, fiches_dir=None):
    """(faut-il supprimer, message) pour `--prune` : jamais sans `--yes`, jamais en dry-run, jamais si le dossier des
    fiches est incomplet (marqueur `_GABARIT.md` absent : mauvais chemin, extraction partielle) — supprimer une fiche
    emporte ses alias, sources et liens."""
    fiches_dir = fiches_dir or FICHES_DIR
    if not prune_asked:
        return False, "(--prune --yes pour les retirer)"
    if dry_run:
        return False, "(dry-run : rien retiré)"
    if not confirmed:
        return False, "--prune demande --yes : rien retiré"
    if not os.path.exists(os.path.join(fiches_dir, SENTINEL)):
        return False, f"--prune refusé : {SENTINEL} introuvable dans {fiches_dir} (dossier incomplet ou mauvais chemin)"
    return True, ""


def print_plan(planned):
    print(f"{len(planned)} fiche(s) valide(s) :")
    for f in planned:
        meta = f["meta"]
        state = "inchangée" if f["unchanged"] else "à écrire"
        concerne = f" | concerne {', '.join(meta['concerne'])}" if meta.get("concerne") else ""
        print(f"  [{f['confidence']:13s}] {meta['slug']} ({meta['categorie']}, {meta['statut']}, {state})"
              f" | {len(f['sources'])} source(s) : {', '.join(sorted({domain(s['url']) for s in f['sources']}))}"
              f" | {len(meta.get('alias', []))} alias{concerne}")
    single = [f["meta"]["slug"] for f in planned if f["confidence"] == "single_source"]
    if single:
        print(f"\n⚠️ {len(single)} fiche(s) à source unique — chargées, affichées avec leur niveau de confiance : "
              f"{', '.join(single)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", action="append", help="fiche à charger (défaut : tout docs/fiches/*.md)")
    ap.add_argument("--dry-run", action="store_true", help="valide et affiche, n'écrit rien")
    ap.add_argument("--force", action="store_true", help="réécrit aussi les fiches inchangées")
    ap.add_argument("--prune", action="store_true", help="retire de la base les fiches dont le fichier n'existe plus "
                                                         "(exige --yes ; refusé si docs/fiches/ est incomplet)")
    ap.add_argument("--yes", action="store_true", help="confirme --prune")
    args = ap.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL non défini : ce script ne lit pas .env. Voir l'en-tête du fichier.")
    paths = list_paths(args.file)
    if not paths:
        raise SystemExit(f"aucune fiche dans {FICHES_DIR}")
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True)
    try:
        if args.dry_run:
            conn.read_only = True
        else:
            from backend import pg_db
            pg_db.init_pool()        # applique schema.sql (tables des fiches)
        planned = plan(conn, paths, force=args.force)
        print_plan(planned)
        if args.dry_run and not _has_fiche_tables(conn):
            print("\n(tables des fiches pas encore créées : le premier chargement réel applique schema.sql)")
        gone = orphans(conn, planned) if not args.file else []
        do_prune = False
        if gone:
            print(f"\nEn base mais sans fichier : {', '.join(gone)}")
            do_prune, message = prune_decision(args.prune, args.dry_run, args.yes)
            if message:
                print(f"  {message}")
        if args.dry_run:
            print("\n(dry-run : rien écrit)")
            return
        written = write(conn, planned)
        if do_prune:
            prune(conn, gone)
            print(f"  {len(gone)} fiche(s) retirée(s)")
        print(f"\n✅ {written} fiche(s) écrite(s), {len(planned) - written} inchangée(s). Aucune version de la base créée "
              f"(le cache d'alias de l'API se renouvelle de lui-même sous 10 minutes).")
    except SeedError as e:
        raise SystemExit(f"❌ {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
