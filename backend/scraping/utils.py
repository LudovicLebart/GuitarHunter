import math
import logging
import unicodedata
import re

logger = logging.getLogger(__name__)


def city_name_variants(city_name: str) -> list[str]:
    """
    Génère une liste ordonnée de variantes du nom d'une ville
    pour maximiser les chances de geocodage (Nominatim, etc.).

    Exemples :
      "Mc Masterville"     → ["Mc Masterville", "McMasterville", ...]
      "Saint-Jean-sur-Richelieu" → [..., "St-Jean-sur-Richelieu", ...]
      "Sainte-Julie"       → [..., "Ste-Julie", ...]
    """
    variants = []

    def _add(name):
        stripped = name.strip()
        if stripped and stripped not in variants:
            variants.append(stripped)

    _add(city_name)

    # Mc X → McX (fusion espace après Mc/Mac)
    mc_fused = re.sub(r'\bMc\s+', 'Mc', city_name)
    _add(mc_fused)
    mac_fused = re.sub(r'\bMac\s+', 'Mac', city_name)
    _add(mac_fused)

    # Saint / Sainte → St / Ste (avec tiret ou espace)
    for sep in ['-', ' ']:
        st = re.sub(rf'\bSaint{sep}', f'St{sep}', city_name, flags=re.IGNORECASE)
        _add(st)
        ste = re.sub(rf'\bSainte{sep}', f'Ste{sep}', city_name, flags=re.IGNORECASE)
        _add(ste)

    # Tirets → espaces et vice-versa
    _add(city_name.replace('-', ' '))
    _add(city_name.replace(' ', '-'))

    # Sans accents (NFD → ASCII)
    def strip_accents(s):
        return ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )
    _add(strip_accents(city_name))
    _add(strip_accents(mc_fused))

    return variants

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calcule la distance en km entre deux points géographiques (Haversine)."""
    try:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except Exception as e:
        logger.error(f"Erreur calcul distance: {e}")
        return 0
