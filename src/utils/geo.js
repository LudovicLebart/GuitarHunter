/** Distance Haversine (km) — miroir de `backend/scraping/utils.py::calculate_distance`. */
export const calculateDistanceKm = (lat1, lon1, lat2, lon2) => {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const R = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

/**
 * Distance minimale d'un point à la ville la plus proche d'une liste — pas une seule boîte/un
 * seul barycentre global (voir discussion 2026-08-26) : un catalogue avec des villes dans
 * plusieurs zones distinctes (ex: Québec ET France) doit rattacher chaque nouvelle ville à la
 * zone dont elle est réellement proche, pas à une moyenne qui n'existe nulle part. `Infinity`
 * si `cities` est vide (aucun repère disponible — 1ère ville d'un catalogue neuf).
 */
export const minDistanceToCities = (lat, lon, cities) => {
  const valid = (cities || []).filter(c => c.latitude != null && c.longitude != null);
  if (valid.length === 0) return Infinity;
  return Math.min(...valid.map(c => calculateDistanceKm(lat, lon, c.latitude, c.longitude)));
};
