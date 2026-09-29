"""
Import de la base de connaissances « univers des guitares » depuis Wikidata et Wikipédia.
Voir docs/management/plans/STRATEGIE_IA.md §3 et les tables `guitar_knowledge*` (schema.sql).

Aucun appel IA, aucun coût. Sources en licence libre : Wikidata (CC0), Wikipédia (CC BY-SA).

Comment on trouve les fabricants
--------------------------------
Wikidata type les fabricants de guitares de façon incohérente (Music Man = « marque déposée »,
ESP = « entreprise »…) : une requête par type en raterait beaucoup. On combine donc quatre routes :
1. **Catégorie Wikipédia « Guitar manufacturing companies »** (Q9962269), parcourue dans
   toutes les langues retenues (en, fr, ja, de, es, it par défaut), sous-catégories comprises
   (par pays, etc.). Route principale : c'est là que les rédacteurs rangent réellement les marques.
2. **Wikidata P1056** (« produit ») = guitare ou basse et leurs sous-classes.
3. **Un saut** vers les marques et filiales des fabricants trouvés (P1716 marque, P355 filiale) :
   c'est ce qui ramène Squier depuis Fender, Epiphone depuis Gibson, etc.
4. **Séries de modèles** (P176 « fabricant ») sous-classes de guitare/basse, pour chaque
   fabricant : Stratocaster, SG, FG… Désactivable (`--no-lines`).

Ce que l'import écrit, et ce qu'il ne touche JAMAIS
---------------------------------------------------
- Réécrit à chaque import : nom, description, maison mère, pays, années, pertinence, alias de
  source wikidata/wikipedia, données brutes.
- Ne touche jamais : `tier`, `hunt_notes`, `made_by`, `curated`, alias de source 'manual'.
  C'est la partie relue et enrichie à la main.
- Crée une nouvelle **version** de la base (`guitar_knowledge_versions`), non validée par
  défaut : le Portier ne doit l'utiliser qu'après le rejeu de non-régression.

Usage (serveur, même DATABASE_URL que le bot ; réseau vers *.wikipedia.org et wikidata.org)
    python backend/scripts/import_guitar_knowledge_wikidata.py --dry-run --json-out kb_preview.json
    python backend/scripts/import_guitar_knowledge_wikidata.py
    python backend/scripts/import_guitar_knowledge_wikidata.py --langs en,fr,ja --depth 2 --notes "premier import"
    python backend/scripts/import_guitar_knowledge_wikidata.py --lookup "Vintage Yamaha Eterna EF-15"

Politesse envers Wikimedia : User-Agent descriptif obligatoire (renseigner KB_CONTACT, un e-mail),
requêtes groupées (50 entités par appel), pause entre appels, respect du Retry-After.
"""
import argparse
import email.utils
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests  # noqa: E402

from backend.guitar_knowledge import _STOP, normalize  # noqa: E402

CATEGORY_QID = "Q9962269"  # Category:Guitar manufacturing companies (et ses équivalents par langue)
GUITAR_ROOTS = ("Q6607", "Q46185")  # guitare, basse
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SPARQL_URL = "https://query.wikidata.org/sparql"
LABEL_LANGS = ("en", "fr", "mul", "de", "es", "it", "ja")

# Types Wikidata (P31) → nature de la fiche.
HUMAN = "Q5"
BRAND_TYPES = {"Q431289", "Q167270"}          # marque, marque déposée
COMPANY_TYPES = {"Q4830453", "Q783794", "Q6881511", "Q891723", "Q1589009"}  # entreprise, société, entreprise, cotée, privée

LIST_PAGE = "Q13406463"  # « article de liste » Wikimedia
LIST_TITLE = re.compile(r"^(list of|liste\b|lista\b|lijst van|liste des)|\b(list|liste|一覧)$", re.IGNORECASE)
# Un MODÈLE (guitare, ampli...) se reconnaît à son type Wikidata (ni organisation ni personne) ET à une
# description qui le dit — les deux, car un fabricant au type Wikidata inhabituel ne doit pas devenir un modèle.
MODEL_WORDS = re.compile(r"\bmodels?\b|\bmodèles?\b|\bmodell\b|\bseries\b|\bproduced by\b|\bintroduced in\b")

GUITAR_WORDS = re.compile(
    r"guitar|guitare|gitarre|guitarra|chitarr|\bbass(es)?\b|\bbasse|luthier|luthie|ギター|ベース")
ACCESSORY_WORDS = re.compile(
    r"tuner|tuning machine|machine head|\bstrings?\b|pickups?|effects?|pedals?|amplifier|amps?\b|"
    r"\bcordes?\b|mecaniques|mécaniques|micros?\b|capo|straps?|cases?\b|picks?\b")
GUITAR_MAKER = re.compile(
    r"guitars?( and (bass|bass guitars?|amplifiers?))? (manufacturer|maker|company|brand)|"
    r"(manufacturer|maker|builder) of [a-z ,-]*guitars|fabricant de guitares|marque de guitares|luthier")
# Le suffixe doit être un MOT entier, précédé d'un espace (ou début de chaîne) : sans cette
# frontière, `co`/`inc`/`ltd`... étaient arrachés au milieu des noms (« Marco » → « Mar »,
# « Nico » → « Ni ») et créaient des alias parasites.
SUFFIXES = re.compile(
    r"(?:^|\s+)(\((guitar|musical instrument|bass guitar)?\s*(manufacturer|company|brand|guitars?)\)|"
    r"guitars?( company| co\.?| corporation| inc\.?| ltd\.?)?|musical instruments?( corporation| co\.?| inc\.?)?|"
    r"manufacturing( company| co\.?)?|(& )?co(mpany)?\.?|inc\.?|ltd\.?|llc|gmbh|s\.a\.|corporation|corp\.?)\s*$",
    re.IGNORECASE)


class WikiClient:
    def __init__(self, pause=0.3, contact=None):
        self.session = requests.Session()
        contact = contact or os.getenv("KB_CONTACT", "contact-not-set")
        self.session.headers["User-Agent"] = f"GuitarHunterKB/1.0 (personal hobby project; {contact})"
        self.pause = pause

    @staticmethod
    def _retry_after(resp, default):
        """`Retry-After` = nombre de secondes OU date HTTP (RFC 9110) ; défaut si absent/illisible."""
        raw = resp.headers.get("Retry-After")
        if not raw:
            return default
        try:
            return max(0, min(int(raw), 300))
        except ValueError:
            pass
        try:
            when = email.utils.parsedate_to_datetime(raw)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0, min(int((when - datetime.now(timezone.utc)).total_seconds()), 300))
        except (TypeError, ValueError):
            return default

    def _get(self, url, params, tries=4):
        """GET JSON avec reprise : 429/5xx (souvent transitoires sur WDQS), timeouts et coupures
        réseau sont retentés avec pause croissante ; toute autre erreur HTTP remonte tout de suite."""
        last = None
        for attempt in range(tries):
            wait = 5 * (attempt + 1)
            try:
                resp = self.session.get(url, params=params, timeout=60)
            except (requests.Timeout, requests.ConnectionError) as e:
                last = e
                print(f"  … {type(e).__name__} sur {url.split('/')[2]}, pause {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(f"HTTP {resp.status_code}")
                wait = self._retry_after(resp, wait)
                print(f"  … HTTP {resp.status_code} de {url.split('/')[2]}, pause {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(self.pause)
            return resp.json()
        raise RuntimeError(f"Échec répété : {url} ({last})")

    # --- Wikipédia -------------------------------------------------------------------------
    def category_members(self, lang, title):
        api = f"https://{lang}.wikipedia.org/w/api.php"
        params = {"action": "query", "list": "categorymembers", "cmtitle": title, "cmlimit": "500",
                  "cmtype": "page|subcat", "format": "json", "formatversion": "2"}
        pages, subcats = [], []
        while True:
            data = self._get(api, params)
            for m in data.get("query", {}).get("categorymembers", []):
                (subcats if m.get("ns") == 14 else pages).append(m["title"])
            if "continue" not in data:
                return pages, subcats
            params.update(data["continue"])

    def pages_to_qids(self, lang, titles):
        api = f"https://{lang}.wikipedia.org/w/api.php"
        out = {}
        for i in range(0, len(titles), 50):
            data = self._get(api, {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                                   "titles": "|".join(titles[i:i + 50]), "format": "json",
                                   "formatversion": "2", "redirects": "1"})
            for p in data.get("query", {}).get("pages", []):
                qid = p.get("pageprops", {}).get("wikibase_item")
                if qid:
                    out[qid] = p["title"]
        return out

    # --- Wikidata --------------------------------------------------------------------------
    def entities(self, qids, props="labels|descriptions|aliases|claims|sitelinks"):
        out = {}
        qids = list(dict.fromkeys(qids))
        for i in range(0, len(qids), 50):
            data = self._get(WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                                            "props": props, "format": "json",
                                            "languages": "|".join(LABEL_LANGS)})
            for qid, ent in data.get("entities", {}).items():
                if "missing" not in ent:
                    out[qid] = ent
        return out

    def sparql(self, query):
        data = self._get(SPARQL_URL, {"query": query, "format": "json"})
        return data.get("results", {}).get("bindings", [])


# ------------------------------------------------------------------------------------------
# Lecture des entités Wikidata
# ------------------------------------------------------------------------------------------
def claim_ids(ent, prop):
    out = []
    for c in ent.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


def claim_year(ent, prop):
    for c in ent.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and v.get("time"):
            m = re.match(r"[+-]?(\d{1,4})-", v["time"])
            if m:
                return int(m.group(1))
    return None


def best_label(ent):
    labels = ent.get("labels", {})
    for lang in ("en", "mul", "fr", "de", "es", "it", "ja"):
        if lang in labels:
            return labels[lang]["value"]
    return None


def best_description(ent):
    d = ent.get("descriptions", {})
    for lang in ("fr", "en"):
        if lang in d:
            return d[lang]["value"]
    return None


def strip_suffix(name):
    prev = None
    while prev != name:
        prev, name = name, SUFFIXES.sub("", name).strip(" ,-")
    return name


def all_names(ent):
    names = []
    for lang_labels in ent.get("labels", {}).values():
        names.append(lang_labels["value"])
    for lang_aliases in ent.get("aliases", {}).values():
        names.extend(a["value"] for a in lang_aliases)
    for key, link in ent.get("sitelinks", {}).items():
        if key.endswith("wiki") and not key.startswith(("commons", "species")):
            names.append(re.sub(r"\s*\(.*\)\s*$", "", link["title"]))
    names += [strip_suffix(n) for n in list(names)]
    return [n for n in dict.fromkeys(n.strip() for n in names) if n]


# « guitar string manufacturer », « guitar pedal maker » : le mot « guitar » QUALIFIE un accessoire, il ne
# dit pas que le fabricant fait des guitares — on le retire avant de décider s'il reste un mot de guitare.
GUITAR_QUALIFIER = re.compile(rf"(?:{GUITAR_WORDS.pattern})\w*[\s-]+(?={ACCESSORY_WORDS.pattern})")


def _description_text(ent):
    return " ".join(filter(None, [best_description(ent)] +
                           [d["value"] for d in ent.get("descriptions", {}).values()])).lower()


def is_list_page(ent, name):
    """Article Wikipédia « liste de… » (« list of guitar manufacturers ») : pas une marque."""
    return LIST_PAGE in claim_ids(ent, "P31") or bool(LIST_TITLE.search(name or ""))


def is_model(ent):
    """Modèle de guitare/ampli (Epiphone G-400, Gibson ES-335, Fender Princeton) et non organisation."""
    types = set(claim_ids(ent, "P31"))
    if not types or types & (BRAND_TYPES | COMPANY_TYPES | {HUMAN}):
        return False
    text = _description_text(ent)
    return bool(MODEL_WORDS.search(text)) and not GUITAR_MAKER.search(text)


def relevance_of(ent, is_line, from_category=False, model=False):
    """`is_line` = série trouvée par la route « séries de modèles » (toujours des guitares). `model` =
    modèle rangé dans la catégorie Wikipédia : jugé sur sa description (un ampli reste `accessories`).
    `from_category` : un FABRICANT rangé dans la catégorie « Guitar manufacturing companies » n'est jamais
    classé `accessories` sur la seule foi de sa description (Framus « firme allemande », Supro « effects
    units », Robin « guitar pickups » l'étaient à tort) — au pire `unknown`, qui reste reconnaissable."""
    if is_line:
        return "guitars"
    text = _description_text(ent)
    if GUITAR_MAKER.search(text):
        return "guitars"
    if ACCESSORY_WORDS.search(text) and not GUITAR_WORDS.search(
            ACCESSORY_WORDS.sub("", GUITAR_QUALIFIER.sub("", text))):
        return "unknown" if (from_category and not model) else "accessories"
    return "guitars" if GUITAR_WORDS.search(text) else "unknown"


def kind_of(ent, is_line):
    if is_line:
        return "line"
    types = set(claim_ids(ent, "P31"))
    if HUMAN in types:
        return "luthier"
    if types & BRAND_TYPES and not types & COMPANY_TYPES:
        return "brand"
    return "company"


def enwiki_url(ent):
    link = ent.get("sitelinks", {}).get("enwiki") or ent.get("sitelinks", {}).get("frwiki")
    if not link:
        return None
    lang = "en" if "enwiki" in ent.get("sitelinks", {}) else "fr"
    return f"https://{lang}.wikipedia.org/wiki/" + link["title"].replace(" ", "_")


# ------------------------------------------------------------------------------------------
# Collecte
# ------------------------------------------------------------------------------------------
def collect_from_categories(client, langs, depth):
    sitelinks = client.entities([CATEGORY_QID], props="sitelinks").get(CATEGORY_QID, {}).get("sitelinks", {})
    qids = {}
    for lang in langs:
        link = sitelinks.get(f"{lang}wiki")
        if not link:
            print(f"  (pas de catégorie en {lang})", file=sys.stderr)
            continue
        seen, frontier, titles = set(), [link["title"]], []
        for level in range(depth + 1):
            nxt = []
            for cat in frontier:
                if cat in seen:
                    continue
                seen.add(cat)
                pages, subcats = client.category_members(lang, cat)
                titles += pages
                nxt += subcats
            frontier = nxt
        found = client.pages_to_qids(lang, list(dict.fromkeys(titles)))
        print(f"  catégorie {lang} : {len(seen)} catégories, {len(found)} pages liées à Wikidata")
        for qid in found:
            qids.setdefault(qid, set()).add(f"category:{lang}")
    return qids


def collect_from_products(client):
    roots = " ".join(f"wd:{q}" for q in GUITAR_ROOTS)
    try:
        rows = client.sparql(f"""
            SELECT DISTINCT ?item WHERE {{
              VALUES ?root {{ {roots} }}
              ?product wdt:P279* ?root .
              ?item wdt:P1056 ?product .
              FILTER NOT EXISTS {{ ?item wdt:P31 wd:{HUMAN} }}
            }} LIMIT 20000""")
    except (RuntimeError, requests.RequestException) as e:
        # Route secondaire (la catégorie Wikipédia est la route principale) : sa requête est la plus
        # lourde de WDQS et échoue parfois — on continue avec les autres routes plutôt qu'avorter.
        print(f"  ⚠️ route « produit = guitare/basse » ignorée ({e})", file=sys.stderr)
        return set()
    qids = {r["item"]["value"].rsplit("/", 1)[-1] for r in rows}
    print(f"  Wikidata « produit = guitare/basse » : {len(qids)} entités")
    return qids


def collect_lines(client, maker_qids):
    lines = {}
    makers = sorted(maker_qids)
    roots = " ".join(f"wd:{q}" for q in GUITAR_ROOTS)
    for i in range(0, len(makers), 150):
        values = " ".join(f"wd:{q}" for q in makers[i:i + 150])
        try:
            rows = client.sparql(f"""
                SELECT DISTINCT ?model ?maker WHERE {{
                  VALUES ?maker {{ {values} }}
                  VALUES ?root {{ {roots} }}
                  ?model wdt:P176 ?maker .
                  ?model (wdt:P31|wdt:P279)/wdt:P279* ?root .
                }}""")
        except (RuntimeError, requests.RequestException) as e:
            print(f"  ⚠️ lot de séries {i}–{i + 150} ignoré ({e})", file=sys.stderr)
            continue
        for r in rows:
            lines[r["model"]["value"].rsplit("/", 1)[-1]] = r["maker"]["value"].rsplit("/", 1)[-1]
    print(f"  séries de modèles : {len(lines)}")
    return lines


def build_records(client, langs, depth, with_lines):
    print("→ Collecte des fabricants")
    origin = collect_from_categories(client, langs, depth)
    for qid in collect_from_products(client):
        origin.setdefault(qid, set()).add("p1056")

    ents = client.entities(list(origin))
    # Un saut : marques et filiales des fabricants trouvés.
    hop = {q for e in ents.values() for q in claim_ids(e, "P1716") + claim_ids(e, "P355")} - set(ents)
    if hop:
        hop_ents = client.entities(list(hop))
        for qid, e in hop_ents.items():
            text = " ".join(d["value"] for d in e.get("descriptions", {}).values()).lower()
            if GUITAR_WORDS.search(text):
                ents[qid] = e
                origin.setdefault(qid, set()).add("hop")
        print(f"  marques/filiales ajoutées par un saut : {sum(1 for q in hop_ents if q in ents)}")
    ents = {q: e for q, e in ents.items() if HUMAN not in claim_ids(e, "P31") or "category" in " ".join(origin.get(q, ()))}

    lines = collect_lines(client, set(ents)) if with_lines else {}
    line_ents = client.entities([q for q in lines if q not in ents]) if lines else {}

    country_qids = {c for e in list(ents.values()) + list(line_ents.values())
                    for c in claim_ids(e, "P17") + claim_ids(e, "P495")}
    country_names = {q: best_label(e) for q, e in client.entities(list(country_qids), props="labels").items()}

    records = []
    for qid, e, is_line in [(q, e, False) for q, e in ents.items()] + [(q, e, True) for q, e in line_ents.items()]:
        name = best_label(e)
        if not name or is_list_page(e, name):
            continue
        model = not is_line and is_model(e)
        as_line = is_line or model  # kind « line » : série de modèles OU modèle isolé
        from_category = any(o.startswith("category") for o in origin.get(qid, ()))
        parents = (claim_ids(e, "P176") if as_line else []) or claim_ids(e, "P749") or claim_ids(e, "P127")
        if is_line and lines.get(qid):
            parents = [lines[qid]]
        countries = [country_names[c] for c in claim_ids(e, "P17") + claim_ids(e, "P495") if country_names.get(c)]
        aliases = all_names(e)
        derived = []  # alias courts dérivés (sans le nom du fabricant), filtrés plus bas
        if as_line and parents:
            # « Yamaha Eterna » → aussi « Eterna » : c'est souvent ce qu'on lit seul sur la tête.
            parent_ent = ents.get(parents[0]) or line_ents.get(parents[0])
            parent_names = sorted({strip_suffix(n) for n in all_names(parent_ent)} if parent_ent else set(),
                                  key=len, reverse=True)
            for alias in list(aliases):
                for pn in parent_names:
                    if pn and alias.lower().startswith(pn.lower() + " "):
                        derived.append(alias[len(pn):].strip())
                        break
        records.append({
            "id": f"wd:{qid}",
            "kind": kind_of(e, as_line),
            "name": name,
            "description": best_description(e),
            "parent_id": f"wd:{parents[0]}" if parents else None,
            "countries": list(dict.fromkeys(countries)) or None,
            "active_from": claim_year(e, "P571"),
            "active_to": claim_year(e, "P576") or claim_year(e, "P2669"),
            "relevance": relevance_of(e, is_line, from_category, model),
            "wikidata_qid": qid,
            "wikipedia_url": enwiki_url(e),
            "aliases": aliases,
            "_derived": derived,
            "raw": {"origin": sorted(origin.get(qid, {"line"})), "p31": claim_ids(e, "P31")},
        })
    _merge_derived_aliases(records)
    return records


def _merge_derived_aliases(records):
    """« Yamaha Eterna » → « Eterna » est utile, « Fender Deluxe » → « Deluxe » est dangereux (homonymes :
    ampli Peavey Deluxe, « Special edition »...). Un alias dérivé n'est gardé que s'il est UNIQUE : pas
    un mot générique (`_STOP`), pas produit par plusieurs séries, pas déjà un nom/alias d'une autre fiche."""
    owned = Counter(normalize(a) for r in records for a in set(r["aliases"]))
    produced = Counter(normalize(a) for r in records for a in set(r["_derived"]))
    dropped = 0
    for r in records:
        keep = []
        for alias in dict.fromkeys(r.pop("_derived")):
            n = normalize(alias)
            if len(n) >= 4 and n not in _STOP and produced[n] == 1 and owned[n] == 0:
                keep.append(alias)
            else:
                dropped += 1
        r["aliases"] = list(dict.fromkeys(r["aliases"] + keep))
    if dropped:
        print(f"  alias dérivés écartés (génériques ou ambigus) : {dropped}")


# ------------------------------------------------------------------------------------------
# Écriture Postgres
# ------------------------------------------------------------------------------------------
def write_records(records, notes):
    from backend import pg_db
    from backend.guitar_knowledge import normalize
    pool = pg_db.init_pool()  # applique schema.sql (tables guitar_knowledge* comprises)
    counts = Counter(r["kind"] for r in records)
    counts.update(f"relevance_{r['relevance']}" for r in records)
    with pool.connection() as conn:
        with conn.transaction():
            version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 AS v FROM guitar_knowledge_versions").fetchone()
            version = version["v"] if isinstance(version, dict) else version[0]
            for r in records:
                conn.execute("""
                    INSERT INTO guitar_knowledge (id, kind, name, description, parent_id, countries,
                        active_from, active_to, relevance, source, wikidata_qid, wikipedia_url, raw,
                        kb_version, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'wikidata',%s,%s,%s,%s,now())
                    ON CONFLICT (id) DO UPDATE SET
                        kind = EXCLUDED.kind, name = EXCLUDED.name, description = EXCLUDED.description,
                        parent_id = EXCLUDED.parent_id, countries = EXCLUDED.countries,
                        active_from = EXCLUDED.active_from, active_to = EXCLUDED.active_to,
                        relevance = EXCLUDED.relevance, wikidata_qid = EXCLUDED.wikidata_qid,
                        wikipedia_url = EXCLUDED.wikipedia_url, raw = EXCLUDED.raw,
                        kb_version = EXCLUDED.kb_version, updated_at = now()
                    -- tier / hunt_notes / made_by / curated : JAMAIS touchés par l'import
                """, (r["id"], r["kind"], r["name"], r["description"], r["parent_id"], r["countries"],
                      r["active_from"], r["active_to"], r["relevance"], r["wikidata_qid"],
                      r["wikipedia_url"], json.dumps(r["raw"]), version))
                conn.execute("DELETE FROM guitar_knowledge_alias WHERE knowledge_id = %s AND source <> 'manual'",
                             (r["id"],))
                for alias in r["aliases"]:
                    norm = normalize(alias)
                    if len(norm) >= 2:
                        conn.execute("""INSERT INTO guitar_knowledge_alias (alias_norm, knowledge_id, alias, source)
                                        VALUES (%s,%s,%s,'wikidata') ON CONFLICT DO NOTHING""",
                                     (norm, r["id"], alias))
            conn.execute("INSERT INTO guitar_knowledge_versions (version, source, notes, counts) VALUES (%s,%s,%s,%s)",
                         (version, "wikidata", notes, json.dumps(dict(counts))))
    return version, counts


def run_lookup(text):
    from backend import pg_db
    from backend.guitar_knowledge import lookup, format_for_prompt
    pool = pg_db.init_pool()
    from psycopg.rows import dict_row
    with pool.connection() as conn:
        conn.row_factory = dict_row
        fiches = lookup(conn, text)
    for f in fiches:
        print(f"  {f['match_type']:5s} « {f['matched_on']} » → {f['name']} ({f['kind']}, {f['relevance']})"
              + (f", rattaché à {f['parent_name']}" if f.get("parent_name") else ""))
    print("\n" + (format_for_prompt(fiches) or "(aucune fiche)"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", default="en,fr,ja,de,es,it")
    ap.add_argument("--depth", type=int, default=2, help="profondeur des sous-catégories")
    ap.add_argument("--no-lines", action="store_true", help="ne pas importer les séries de modèles")
    ap.add_argument("--dry-run", action="store_true", help="n'écrit rien en base")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--notes", default=None, help="note attachée à la version créée")
    ap.add_argument("--lookup", default=None, help="teste la recherche sur un texte (base déjà importée)")
    args = ap.parse_args()

    if args.lookup:
        run_lookup(args.lookup)
        return

    client = WikiClient()
    records = build_records(client, [l.strip() for l in args.langs.split(",") if l.strip()],
                            args.depth, not args.no_lines)
    counts = Counter(r["kind"] for r in records)
    rel = Counter(r["relevance"] for r in records)
    print(f"\n→ {len(records)} fiches : " + ", ".join(f"{k} {v}" for k, v in counts.most_common())
          + " | pertinence : " + ", ".join(f"{k} {v}" for k, v in rel.most_common()))
    print(f"  alias : {sum(len(r['aliases']) for r in records)}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        print(f"  aperçu écrit : {args.json_out}")
    if args.dry_run:
        print("  (dry-run : rien écrit en base)")
        return
    version, _ = write_records(records, args.notes)
    print(f"\n✅ Version {version} de la base écrite (NON validée). Rejouer le Portier avant de la "
          f"marquer validée : UPDATE guitar_knowledge_versions SET validated = true WHERE version = {version};")


if __name__ == "__main__":
    main()
