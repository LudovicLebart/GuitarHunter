"""Bornes de la configuration d'un compte (`PATCH /users/me/config`, revue R-6-3, 2026-11-06).

Le corps reste libre (le frontend décide des clés), mais les réglages qui pilotent le coût ou la charge
sur les sites sources doivent rester dans des bornes sensées : une fréquence d'une minute ferait bloquer
l'IP unique du serveur pour tous les comptes. Une valeur hors bornes est REFUSÉE (422), jamais corrigée en
silence. Sans dépendance : testé sans base."""
import json

MAX_CONFIG_BYTES = 200_000
MAX_STRING_CHARS = 30_000

# (clé de scanConfig) -> (minimum, maximum)
SCAN_BOUNDS = {
    "frequency": (5, 1440),
    "max_ads": (1, 500),
    "distance": (0, 500),
    "min_price": (0, 1_000_000),
    "max_price": (0, 1_000_000),
}


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_config_patch(patch):
    """Lève `ValueError` (message lisible) si `patch` sort des bornes ; sinon ne fait rien."""
    if not isinstance(patch, dict):
        raise ValueError("La configuration doit être un objet.")
    if len(json.dumps(patch, default=str)) > MAX_CONFIG_BYTES:
        raise ValueError("Configuration trop volumineuse.")

    scan = patch.get("scanConfig")
    if scan is not None:
        if not isinstance(scan, dict):
            raise ValueError("scanConfig doit être un objet.")
        for key, (lo, hi) in SCAN_BOUNDS.items():
            if key in scan and scan[key] is not None and scan[key] != "":
                v = scan[key]
                if not _is_number(v) or not lo <= v <= hi:
                    raise ValueError(f"scanConfig.{key} doit être un nombre entre {lo} et {hi}.")

    analysis = patch.get("analysisConfig")
    if analysis is not None:
        if not isinstance(analysis, dict):
            raise ValueError("analysisConfig doit être un objet.")
        for key, v in analysis.items():
            if key.startswith("proTrigger") and v is not None and v != "":
                hi = 1_000_000 if key.endswith("PriceThreshold") else 10
                if not _is_number(v) or not 0 <= v <= hi:
                    raise ValueError(f"analysisConfig.{key} doit être un nombre entre 0 et {hi}.")
            if isinstance(v, str) and len(v) > MAX_STRING_CHARS:
                raise ValueError(f"analysisConfig.{key} est trop long.")
