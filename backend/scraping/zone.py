"""Appartenance géographique d'une annonce à la liste de villes d'un utilisateur : fonctions PURES.

Pourquoi : Facebook écrit la localisation d'une carte de façons très variables (« Réunion, Reunion » pour
une île entière, « West Island », « Laval / North Shore », deux « Paris » homonymes). Comparer ces textes
aux noms de villes de la liste est donc fragile. Le GPS de la fiche détail, lui, est fiable : même règle
que Kijiji (`GuitarHunterBot._kijiji_strict_label`), partagée ici par `nearest_listed_city()`.
"""
from backend.scraping.utils import calculate_distance

# Boîte englobante du Canada, volontairement large : on ne veut écarter que les villes manifestement
# ailleurs (La Réunion, France...). Limite connue : le nord des États-Unis proche de la frontière
# (Vermont, État de New York, Maine...) reste dans la boîte et n'est pas écarté.
CANADA_LAT = (41.0, 84.0)
CANADA_LNG = (-141.5, -52.0)
# Ouest du pays : au sud du 49e parallèle et à l'ouest de -95°, il n'y a que des États-Unis.
US_WEST_LAT_MAX = 49.0
US_WEST_LNG_MAX = -95.0


def is_outside_canada(lat, lng):
    """True si les coordonnées sont connues ET hors du Canada. Coordonnées absentes : False
    (ville sans coordonnées = traitée comme avant, jamais écartée sur une absence d'information)."""
    if not (isinstance(lat, (int, float)) and isinstance(lng, (int, float))):
        return False
    if not (CANADA_LAT[0] <= lat <= CANADA_LAT[1] and CANADA_LNG[0] <= lng <= CANADA_LNG[1]):
        return True
    return lat < US_WEST_LAT_MAX and lng < US_WEST_LNG_MAX


def nearest_listed_city(lat, lng, city_points, max_km):
    """Clé de la ville listée la plus proche à <= max_km, ou None.
    `city_points` : itérable de (clé, latitude, longitude) ou (clé, latitude, longitude, km_en_plus) ;
    `km_en_plus` (réglage par ville, ex. `kijijiRadiusKm`) élargit la borne pour cette ville seulement."""
    best, best_d = None, None
    for point in city_points:
        key, c_lat, c_lng = point[:3]
        extra_km = (point[3] if len(point) > 3 else 0) or 0
        d = calculate_distance(lat, lng, c_lat, c_lng)
        if d <= max(max_km, extra_km) and (best_d is None or d < best_d):
            best, best_d = key, d
    return best


def card_verdict(name_allowed, coords, city_points, gps_km, name_km):
    """Décision finale sur une carte Facebook une fois sa fiche détail lue (mode strict).

    `name_allowed` : le lieu affiché sur la carte est dans la liste de villes. `coords` : {"lat","lng"} de la
    fiche, ou None si illisible. Retourne `("keep", clé_de_ville_ou_None)` ou `("reject", mémorisable)` ;
    `mémorisable` est vrai quand le rejet vient d'un GPS lu (la fiche n'a pas besoin d'être rouverte).

    - Nom reconnu : tolérance large `name_km` (grande sous-région), mais un homonyme lointain
      (« Paris, ON » pour une liste « Paris ») est rejeté par le GPS.
    - Nom non reconnu : seul un GPS à <= `gps_km` d'une ville listée le rattache.
    - GPS illisible : le nom décide (comme Kijiji).
    """
    if not coords:
        return ("keep", None) if name_allowed else ("reject", False)
    label = nearest_listed_city(coords["lat"], coords["lng"], city_points, name_km if name_allowed else gps_km)
    return ("keep", label) if label is not None else ("reject", True)


def may_try_gps_fallback(pages_used, rescued, cap, probe_limit=3):
    """Faut-il ouvrir une fiche de plus pour une carte au lieu non reconnu ?
    Non au-delà de `cap` fiches par scan ; et non si les `probe_limit` premières n'en ont rattaché aucune
    (ID de ville probablement faux : toutes les cartes sont ailleurs, inutile de payer 8 fiches par scan)."""
    if pages_used >= cap:
        return False
    return not (pages_used >= probe_limit and rescued == 0)
