"""Santé des scrapers (Facebook / Kijiji) : classification de chaque scan et décision d'alerte.

Fonctions PURES (aucune base, aucun réseau) — l'enregistrement en base vit dans
`PostgresRepository.record_scrape_run()` et l'envoi de l'alerte dans
`NotificationService.notify_scrape_health()`, câblés par `bot.py`.

Principe : un ÉCHEC signifie « le scraper est cassé », jamais « il n'y a pas d'annonce ». Un scan qui
voit des cartes mais n'en garde aucune est `ok` (une petite ville peut n'avoir aucune nouvelle
guitare). Cas d'école qui a motivé ce module : l'ID Facebook de Bromont pointait sur Bromont-Lamothe
(France) — 82 cartes vues, 100 % hors liste, 0 gardée, sans la moindre alerte (journal 2026-10).
"""
from collections import Counter

OK = "ok"
NO_CARDS = "no_cards"                # 0 carte vue : page non chargée / sélecteur cassé
GEO_MISMATCH = "geo_mismatch"        # presque toutes les cartes hors liste : mauvaise ville recherchée
BLOCKED = "blocked"                  # redirection login / captcha
DETAIL_DEGRADED = "detail_degraded"  # fiches détail sans photo (gating, page dégradée)
ERROR = "error"                      # exception pendant le scan

FAILURE_OUTCOMES = (NO_CARDS, GEO_MISMATCH, BLOCKED, DETAIL_DEGRADED, ERROR)

# Seuils de classification (un petit nombre de cartes suffit : on mesure une PROPORTION).
GEO_MIN_CARDS = 5
GEO_OUT_OF_LIST_RATIO = 0.9
DETAIL_MIN_DEALS = 3
DETAIL_NO_PHOTO_RATIO = 0.5

# Seuils d'alerte.
ALERT_CONSECUTIVE = 3        # N échecs de suite pour une même (source, ville)
ALERT_WINDOW = 10            # ou, sur les N derniers scans...
ALERT_WINDOW_MIN_RUNS = 6    # ...(au moins 6 scans connus)...
ALERT_FAILURE_RATIO = 0.5    # ...au moins 50 % d'échecs
ALERT_COOLDOWN_HOURS = 6     # délai minimal entre deux alertes d'une même (source, ville)

REPAIR_HINTS = {
    GEO_MISMATCH: (
        "L'ID Facebook de cette ville pointe probablement sur une autre ville (homonyme à l'étranger). "
        "Vérifier : python -m backend.scripts.list_fb_city_candidates --names \"{city}\" --try-all"
    ),
    BLOCKED: "Le site redirige vers un login/captcha : attendre, puis vérifier l'IP du serveur (proxy) et le rythme des scans.",
    NO_CARDS: "Aucune carte lue : la page ne charge pas ou les sélecteurs ont changé. Consulter les logs du scan.",
    DETAIL_DEGRADED: "Les fiches détail n'ont pas de photos : page dégradée (gating Facebook non authentifié ?). Consulter les logs.",
    ERROR: "Exception pendant le scan. Consulter les logs (journalctl / LogViewer) pour la trace.",
}


def classify_facebook(scan_result, exception=None):
    """(outcome, detail) d'un scan Facebook à partir du dict de `FacebookScraper.scan_marketplace()`."""
    if exception is not None:
        return ERROR, str(exception)[:300]
    if scan_result.get("error"):
        return ERROR, str(scan_result["error"])[:300]
    if scan_result.get("anti_bot_blocked"):
        return BLOCKED, "redirection login/captcha"
    cards = scan_result.get("total_cards_seen", 0) or 0
    if cards == 0:
        return NO_CARDS, "0 carte vue"
    out_of_list = scan_result.get("rejected_out_of_list", 0) or 0
    no_location = scan_result.get("dropped_no_location", 0) or 0
    # Une carte de la ville cherchée prouve que l'ID est le bon : un compte à une seule ville (Paris)
    # a naturellement ~90 % de cartes de banlieue « hors liste » sans que le scraper soit cassé.
    in_list = cards - out_of_list - no_location
    if cards >= GEO_MIN_CARDS and in_list <= 0 and out_of_list / cards >= GEO_OUT_OF_LIST_RATIO:
        return GEO_MISMATCH, f"{out_of_list}/{cards} cartes hors liste de villes"
    deals = scan_result.get("deals") or []
    if len(deals) >= DETAIL_MIN_DEALS:
        no_photo = sum(1 for d in deals if not d.get("imageUrls"))
        if no_photo / len(deals) >= DETAIL_NO_PHOTO_RATIO:
            return DETAIL_DEGRADED, f"{no_photo}/{len(deals)} fiches sans photo"
    return OK, ""


def classify_kijiji(last_scan, exception=None):
    """(outcome, detail) d'un scan Kijiji à partir de `KijijiScraper.last_scan`
    ({"blocked": bool, "error": str|None, "cards_seen": int})."""
    if exception is not None:
        return ERROR, str(exception)[:300]
    last_scan = last_scan or {}
    if last_scan.get("blocked"):
        return BLOCKED, "redirection login/captcha"
    if last_scan.get("error"):
        return ERROR, str(last_scan["error"])[:300]
    if (last_scan.get("cards_seen") or 0) == 0:
        return NO_CARDS, "0 annonce lue"
    return OK, ""


def should_alert(outcomes):
    """Décide s'il faut alerter pour une (source, ville).

    `outcomes` : codes des scans connus, du PLUS RÉCENT au plus ancien.
    Retourne (alerter: bool, code dominant: str|None, nombre d'échecs récents: int).
    """
    if not outcomes:
        return False, None, 0

    consecutive = 0
    for o in outcomes:
        if o in FAILURE_OUTCOMES:
            consecutive += 1
        else:
            break
    if consecutive >= ALERT_CONSECUTIVE:
        dominant = Counter(outcomes[:consecutive]).most_common(1)[0][0]
        return True, dominant, consecutive

    window = outcomes[:ALERT_WINDOW]
    failures = [o for o in window if o in FAILURE_OUTCOMES]
    if len(window) >= ALERT_WINDOW_MIN_RUNS and len(failures) / len(window) >= ALERT_FAILURE_RATIO:
        return True, Counter(failures).most_common(1)[0][0], len(failures)
    return False, None, len(failures)


def repair_hint(code, city):
    return REPAIR_HINTS.get(code, "Consulter les logs.").format(city=city)
