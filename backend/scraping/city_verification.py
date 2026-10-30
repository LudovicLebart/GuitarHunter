"""Vérification d'un ID de ville Facebook Marketplace : fonctions PURES (aucun réseau, aucune base).

Contexte (voir docs/management/plans/FB_CITY_IDS_AND_SCRAPER_HEALTH_PLAN.md) : `CityFinder` cliquait la
première suggestion du sélecteur de lieu de Facebook. Or Facebook OMET la région des lieux proches de
l'IP du client — « Bromont | Ville » (Québec) et « Bromont-Lamothe, Auvergne, France | Ville » — donc
l'indice « Québec » ne correspondait jamais et le bot a gardé l'ID d'un Bromont français.

Principe ici : (1) ne retenir que les suggestions DONT LE NOM correspond et dont la région n'est pas
explicitement étrangère ; (2) ne jamais croire un ID sans l'avoir SONDÉ — la part de cartes du fil
`/marketplace/<id>/` dont le lieu est « <ville>, QC » est le signal objectif (Québec ≈ 100 %, France 0 %).

Pas de nombre minimal d'annonces : on compare des PROPORTIONS, pas des volumes (Bromont est minuscule).
Un plancher de 3 cartes évite seulement de conclure sur du vide -> INDETERMINATE (jamais une correction).
"""
import re
from collections import namedtuple

from backend.cities import normalize_city_key
from backend.scraping.utils import calculate_distance

VERIFIED = "VERIFIED"
AMBIGUOUS = "AMBIGUOUS"
INDETERMINATE = "INDETERMINATE"
NOT_FOUND = "NOT_FOUND"

Decision = namedtuple("Decision", ["status", "city_id", "detail"])

# Variantes d'écriture d'une région (clé en minuscules) — Facebook affiche l'abréviation
# (« Sherbrooke, QC »), le frontend (Photon) le nom complet (« Québec »).
REGION_ALIASES = {
    "québec": ("quebec", "qc"), "quebec": ("québec", "qc"),
    "ontario": ("on",), "british columbia": ("bc", "colombie-britannique"),
    "colombie-britannique": ("bc", "british columbia"), "alberta": ("ab",),
    "nouveau-brunswick": ("nb", "new brunswick"), "new brunswick": ("nb", "nouveau-brunswick"),
    "nouvelle-écosse": ("ns", "nova scotia"), "nova scotia": ("ns", "nouvelle-écosse"),
    "manitoba": ("mb",), "saskatchewan": ("sk",),
}

PROVINCE_CODES = {
    "québec": "QC", "quebec": "QC", "ontario": "ON",
    "british columbia": "BC", "colombie-britannique": "BC", "alberta": "AB",
    "nouveau-brunswick": "NB", "new brunswick": "NB",
    "nouvelle-écosse": "NS", "nova scotia": "NS", "manitoba": "MB", "saskatchewan": "SK",
}

# Régions administratives du Québec, telles que Facebook les affiche entre parenthèses.
QC_REGIONS = (
    "montérégie", "estrie", "laurentides", "lanaudière", "outaouais", "capitale-nationale",
    "chaudière-appalaches", "centre-du-québec", "mauricie", "saguenay", "bas-saint-laurent",
    "gaspésie", "abitibi-témiscamingue", "côte-nord", "nord-du-québec", "laval", "montréal",
)

# Segments d'URL `/marketplace/<x>/` qui ne sont pas une ville.
_RESERVED_SEGMENTS = {"search", "category", "item", "you", "notifications", "selling", "inbox",
                      "create", "buying", "saved", "groups", "explore"}

# Seuils de décision (proportions, pas de volumes).
MIN_CARDS = 3
MIN_PROVINCE_SHARE = 0.7
MIN_NEAR_SHARE = 0.5
NEAR_RADIUS_KM = 80.0


def _hint_head(hint):
    """« Québec, Canada » -> « québec »."""
    return (hint or "").split(",")[0].strip().lower()


def province_code(hint):
    """Code de province d'un indice de région (« Québec » -> « QC »), ou None si inconnu."""
    head = _hint_head(hint)
    if head in PROVINCE_CODES:
        return PROVINCE_CODES[head]
    return head.upper() if len(head) == 2 else None


def parse_label(label):
    """(nom, région ou None) d'un libellé de suggestion.

    « Bromont | Ville » -> (« Bromont », None) ; « Bromont\\nVille » idem ;
    « Bromont-Lamothe, Auvergne, France | Ville » -> (« Bromont-Lamothe », « Auvergne, France »).
    Le type de lieu (« Ville ») est ignoré.
    """
    parts = [p.strip() for p in re.split(r"\n|\s\|\s", label or "") if p.strip()]
    place = parts[0] if parts else ""
    in_parens = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", place)  # « Saint-Lambert (Montérégie) », « Saline (Michigan) »
    if in_parens:
        return in_parens.group(1).strip(), (in_parens.group(2).strip() or None)
    name, _, region = place.partition(",")
    return name.strip(), (region.strip() or None)


def region_compatible(region, hint):
    """Une région absente (lieu proche) est compatible ; une région explicite l'est seulement si elle
    contient l'indice (ou une de ses variantes) comme mot entier."""
    if not region:
        return True
    head = _hint_head(hint)
    if not head:
        return True
    variants = {head, *REGION_ALIASES.get(head, ())}
    code = province_code(hint)
    if code:
        variants.add(code.lower())
    text = region.lower()
    if code == "QC" and any(re.search(rf"(?<![a-zà-ÿ]){re.escape(r)}(?![a-zà-ÿ])", text) for r in QC_REGIONS):
        return True  # Facebook écrit la région administrative : « Saint-Lambert (Montérégie) »
    return any(re.search(rf"(?<![a-zà-ÿ]){re.escape(v)}(?![a-zà-ÿ])", text) for v in variants)


def filter_candidates(labels, city_name, region_hint):
    """Suggestions retenues pour `city_name`, par ordre de priorité.

    Garde celles dont le NOM normalisé est égal (« Woluwe-Saint-Lambert » ≠ « Saint-Lambert »,
    « Bromont-Lamothe » ≠ « Bromont ») ET dont la région est absente ou compatible avec l'indice.
    Les lieux sans région (proches de l'IP) passent avant ceux dont la région est explicite.
    Retourne une liste de dicts {index, label, name, region, local}.
    """
    wanted = normalize_city_key(city_name)
    kept = []
    for index, label in enumerate(labels):
        name, region = parse_label(label)
        if normalize_city_key(name) != wanted:
            continue
        if not region_compatible(region, region_hint):
            continue
        kept.append({"index": index, "label": label, "name": name, "region": region, "local": region is None})
    return sorted(kept, key=lambda c: (not c["local"], c["index"]))


def parse_card_location(text):
    """« Montréal, QC » -> (« Montréal », « QC ») ; « Riom, ARA » -> (« Riom », « ARA »)."""
    name, _, region = (text or "").partition(",")
    return name.strip(), (region.strip().upper() or None)


def score_probe(card_locations, province, expected_coords=None, gazetteer=None, radius_km=NEAR_RADIUS_KM):
    """Résume le fil d'un ID candidat à partir des lieux de ses cartes.

    `province` : code attendu (« QC »). `expected_coords` : (lat, lon) de la ville, et `gazetteer` :
    {clé de ville normalisée: (lat, lon)} — ensemble, ils départagent des homonymes de la même province
    (Saint-Lambert / Saint-Lambert-de-Lauzon) : `part_near` = part des cartes, parmi celles dont la ville
    est connue du gazetteer, situées à moins de `radius_km` de la ville attendue (None si indéterminable).
    """
    locations = [l for l in (card_locations or []) if l and l.strip()]
    n = len(locations)
    if n == 0:
        return {"n": 0, "part_province": 0.0, "part_near": None}

    in_province = sum(1 for l in locations if province and parse_card_location(l)[1] == province.upper())
    part_near = None
    if expected_coords and gazetteer:
        known = [gazetteer[k] for k in (normalize_city_key(parse_card_location(l)[0]) for l in locations) if k in gazetteer]
        if known:
            near = sum(1 for lat, lon in known if calculate_distance(expected_coords[0], expected_coords[1], lat, lon) <= radius_km)
            part_near = near / len(known)
    return {"n": n, "part_province": in_province / n, "part_near": part_near}


def decide(scored, floor=MIN_CARDS, min_province=MIN_PROVINCE_SHARE, min_near=MIN_NEAR_SHARE):
    """Décision sur un ensemble d'ID candidats sondés.

    `scored` : liste de {id, n, part_province, part_near} (un même ID peut apparaître plusieurs fois).
      - aucun candidat avec au moins `floor` cartes  -> INDETERMINATE (on ne conclut pas) ;
      - exactement un ID valide                       -> VERIFIED ;
      - plusieurs ID distincts valides                -> AMBIGUOUS (jamais un choix arbitraire) ;
      - des candidats sondés mais aucun valide        -> NOT_FOUND.
    Valide : au moins `min_province` de cartes de la province ET, si les coordonnées permettent de le
    mesurer, au moins `min_near` de cartes proches de la ville attendue.
    """
    probed = [s for s in scored if s["n"] >= floor]
    if not probed:
        return Decision(INDETERMINATE, None, f"moins de {floor} cartes lues pour chaque candidat")

    valid_ids = []
    for s in probed:
        if s["part_province"] >= min_province and (s.get("part_near") is None or s["part_near"] >= min_near):
            if s["id"] not in valid_ids:
                valid_ids.append(s["id"])

    if len(valid_ids) == 1:
        return Decision(VERIFIED, valid_ids[0], "")
    if len(valid_ids) > 1:
        return Decision(AMBIGUOUS, None, f"plusieurs ID valides : {', '.join(map(str, valid_ids))}")
    best = max(probed, key=lambda s: s["part_province"])
    return Decision(NOT_FOUND, None, f"aucun ID ne passe (meilleur : {best['id']}, {best['part_province']:.0%} de la province)")


# ---------------------------------------------------------------------------------------------
# Lecture d'une page /marketplace/<id>/ : ID dans l'URL et ville affichée par le bouton de lieu.
# ---------------------------------------------------------------------------------------------

def marketplace_segment(url):
    """Segment qui suit `/marketplace/` dans une URL (ID numérique OU alias texte), ou None."""
    m = re.search(r"/marketplace/([^/?#]+)", url or "")
    if not m:
        return None
    seg = m.group(1)
    return None if seg in ("search", "category", "item", "you", "notifications", "inbox", "selling", "buying") else seg


def numeric_city_id(url):
    """ID Facebook numérique d'une URL `/marketplace/<id>/...`, ou None (alias texte, pas d'ID)."""
    seg = marketplace_segment(url)
    return seg if seg and seg.isdigit() else None


def slug_from_segment(segment):
    """Alias texte d'un segment `/marketplace/<alias>/` (« montreal »), ou None. Facebook n'a pas de
    numéro pour certaines grandes villes ; l'alias n'est accepté qu'après sondage de son fil."""
    seg = (segment or "").lower()
    if re.fullmatch(r"[a-z][a-z0-9_-]{2,40}", seg) and seg not in _RESERVED_SEGMENTS:
        return seg
    return None


def landed_place_name(button_text):
    """Nom du lieu affiché par le bouton de lieu : « Bromont · Dans un rayon de 65 km » -> « Bromont » ;
    « Beloeil, Hainaut, Belgium · Dans un rayon de 65 km » -> « Beloeil » (la région est ignorée ici)."""
    head = re.split(r"[·•]", button_text or "")[0]
    return parse_label(head)[0]


def landed_name_matches(button_text, city_name):
    """La page chargée affiche-t-elle bien `city_name` ? Garde-fou contre un clic qui n'a pas pris
    (URL de la ville précédente) : un ID « québécois » mais d'une AUTRE ville ne doit pas passer."""
    return bool(button_text) and normalize_city_key(landed_place_name(button_text)) == normalize_city_key(city_name)


def landed_region(button_text):
    """Région explicite du lieu affiché (« Hainaut, Belgium »), ou None."""
    head = re.split(r"[·•]", button_text or "")[0]
    return parse_label(head)[1]


def trusted_gazetteer(cities):
    """{clé de ville normalisée: (lat, lon)} à partir de dicts {name, latitude, longitude}, en écartant les
    coordonnées DOUTEUSES : manquantes, ou strictement identiques à celles d'une AUTRE ville (cas réel :
    « Sherbrooke » porte les coordonnées de Montréal). Mieux vaut ignorer une ville que se fier à une
    coordonnée fausse pour valider la proximité."""
    by_coords = {}
    for c in cities or []:
        lat, lon = c.get("latitude"), c.get("longitude")
        key = normalize_city_key(c.get("name", ""))
        if not key or lat is None or lon is None:
            continue
        by_coords.setdefault((round(float(lat), 4), round(float(lon), 4)), set()).add(key)
    gazetteer = {}
    for (lat, lon), keys in by_coords.items():
        if len(keys) == 1:
            gazetteer[next(iter(keys))] = (lat, lon)
    return gazetteer
