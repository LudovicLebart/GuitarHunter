"""
Clustering géométrique par couverture d'ensembles gloutonne — regroupe une liste de
villes (avec coordonnées) en un nombre minimal de points d'ancrage tels que chaque
ville de la liste soit à moins de `radius_km` d'au moins un ancrage retenu.

Fonction pure et site-agnostique : ne connaît rien de Facebook, Kijiji ou LeBonCoin.
Chaque scraper décide lui-même du rayon à lui passer (empirique et non garanti côté
Facebook, explicite et réellement respecté côté Kijiji) et de comment consommer les
clusters retournés — voir docs/management/JOURNAL.md (2026-08-24/25) pour le contexte
complet de cette décision.

Algorithme : à chaque itération, sélectionne parmi les villes pas encore couvertes
celle qui couvre le plus d'autres villes pas encore couvertes (elle-même incluse) dans
le rayon donné, la retient comme ancre, marque toutes les villes qu'elle couvre comme
couvertes, et recommence jusqu'à couverture totale. Le nombre d'ancrages émerge de la
géométrie réelle de la liste passée en entrée — jamais une valeur figée : une liste de
villes formant plusieurs zones distantes (ex: Montérégie + grand Québec) produit
naturellement un ancrage séparé par zone, sans configuration supplémentaire.
"""
from backend.scraping.utils import calculate_distance


class AnchorCluster:
    """Un point d'ancrage (la ville retenue comme centre de recherche) et l'ensemble
    des villes d'origine qu'il couvre (lui-même inclus)."""

    __slots__ = ("anchor", "members")

    def __init__(self, anchor, members):
        self.anchor = anchor    # dict ville (mêmes clés que l'entrée : id/name/latitude/longitude/...)
        self.members = members  # liste de dicts ville, sous-ensemble de l'entrée, ancre incluse

    def max_member_distance_km(self):
        """Distance entre l'ancre et le membre le plus éloigné qu'elle couvre — le rayon
        minimal à donner à un moteur de recherche qui respecte réellement ce paramètre
        (ex: Kijiji) pour garantir la couverture de tous les membres du cluster."""
        a_lat, a_lon = self.anchor.get('latitude'), self.anchor.get('longitude')
        if a_lat is None or a_lon is None:
            return 0.0
        return max(
            (
                calculate_distance(a_lat, a_lon, m['latitude'], m['longitude'])
                for m in self.members
                if m is not self.anchor and m.get('latitude') is not None and m.get('longitude') is not None
            ),
            default=0.0,
        )


def compute_anchor_clusters(cities, radius_km):
    """Retourne une liste d'`AnchorCluster` couvrant `cities` avec le moins d'ancrages
    possible, tel que chaque ville soit à <= radius_km d'au moins un ancrage retenu.

    `cities` : liste de dicts exposant au minimum 'latitude'/'longitude' (les autres
    clés, ex: 'id'/'name'/'kijijiRadiusKm', sont conservées telles quelles — un scraper
    y retrouve tout ce dont il a besoin pour construire sa recherche). Une ville sans
    coordonnées est traitée comme son propre cluster isolé (ne peut ni couvrir ni être
    couverte) plutôt que de faire échouer tout le calcul.
    """
    remaining = list(cities)
    clusters = []

    while remaining:
        best_candidate, best_covered = None, []
        for candidate in remaining:
            c_lat, c_lon = candidate.get('latitude'), candidate.get('longitude')
            if c_lat is None or c_lon is None:
                covered = [candidate]
            else:
                covered = [
                    other for other in remaining
                    if other is candidate or (
                        other.get('latitude') is not None and other.get('longitude') is not None
                        and calculate_distance(c_lat, c_lon, other['latitude'], other['longitude']) <= radius_km
                    )
                ]
            if len(covered) > len(best_covered):
                best_candidate, best_covered = candidate, covered

        clusters.append(AnchorCluster(anchor=best_candidate, members=best_covered))
        covered_ids = {id(c) for c in best_covered}
        remaining = [c for c in remaining if id(c) not in covered_ids]

    return clusters
