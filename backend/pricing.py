"""Normalisation des prix d'annonces (partagée par le bot et les scripts)."""


def normalize_price(price):
    """Nettoie une chaîne de prix (ex: ' 150 $ ') pour retourner un float fiable."""
    try:
        num_str = ''.join(c for c in str(price).replace(',', '.') if c.isdigit() or c == '.')
        return float(num_str) if num_str else 0.0
    except Exception:
        return 0.0
