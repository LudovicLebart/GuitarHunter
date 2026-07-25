"""
Comportement de navigation "humain" partagé entre les modules de scraping
(LeboncoinScraper, et les futurs modules — Kijiji, Reverb...). Aucune
dépendance à un site précis : pauses, trajectoires de souris, scroll, plage
horaire d'activité.

FacebookScraper (backend/scraping/core.py) n'utilise PAS ce module pour
l'instant — c'est un scraper en production, une migration éventuelle est un
chantier distinct et délibéré (voir docs/management/TODO.md), pas un effet
de bord de ce refactor.
"""
import math
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Plage nocturne (heure de Paris, pas l'heure système de la machine qui exécute
# le script) — un humain ne consulte pas les petites annonces en pleine nuit.
PARIS_TZ = ZoneInfo("Europe/Paris")
NIGHT_START_HOUR = 0
NIGHT_END_HOUR = 7


def is_night_time(now=None):
    """True si l'heure actuelle (Europe/Paris) tombe dans la plage nocturne
    [NIGHT_START_HOUR, NIGHT_END_HOUR)."""
    now = now or datetime.now(PARIS_TZ)
    return NIGHT_START_HOUR <= now.hour < NIGHT_END_HOUR


def seconds_until_active(now=None):
    """Secondes à attendre avant la prochaine heure d'activité plausible — 0 si
    on n'est pas actuellement en plage nocturne. Le réveil est variable (pas un
    couperet fixe à NIGHT_END_HOUR pile) pour rester plausible."""
    now = now or datetime.now(PARIS_TZ)
    if not is_night_time(now):
        return 0
    wake_hour = NIGHT_END_HOUR + random.uniform(0, 1.5)  # ex: entre 7h00 et ~8h30
    target = now.replace(hour=int(wake_hour), minute=int((wake_hour % 1) * 60), second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


class HumanBehaviorMixin:
    """À utiliser en mixin par une classe de scraper qui expose déjà
    `self.logger`. Ne touche ni `__init__`, ni la gestion de session —
    uniquement des méthodes de comportement décoratif (pauses, souris,
    scroll). `_human_mouse_move` suppose que l'hôte maintient un attribut
    `self._mouse_pos = (x, y)`, mis à jour à chaque déplacement."""

    def _human_pause(self, low, high):
        """Pause à distribution non-uniforme (asymétrique vers le bas, avec de
        rares hésitations plus longues) plutôt qu'un `random.uniform` plat — une
        signature statistique trop régulière est elle-même détectable dans la
        durée sur de nombreux cycles."""
        if random.random() < 0.12:
            time.sleep(random.uniform(high, high * 2.0))
        else:
            time.sleep(random.triangular(low, high, low))

    def _human_mouse_move(self, page, target_x, target_y):
        """Déplace la souris vers (target_x, target_y) en plusieurs étapes
        intermédiaires (courbe lissée + micro-jitter), au lieu de la
        téléportation instantanée d'un simple `page.mouse.move()`."""
        start_x, start_y = self._mouse_pos
        steps = random.randint(8, 20)
        for i in range(1, steps + 1):
            t = i / steps
            eased = t * t * (3 - 2 * t)  # smoothstep : accélération puis décélération
            jitter_x = random.uniform(-3, 3) if 0 < i < steps else 0
            jitter_y = random.uniform(-3, 3) if 0 < i < steps else 0
            x = start_x + (target_x - start_x) * eased + jitter_x
            y = start_y + (target_y - start_y) * eased + jitter_y
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.008, 0.03))
        self._mouse_pos = (target_x, target_y)

    def _move_mouse_to_element(self, page, element):
        """Scrolle l'élément dans le viewport puis y déplace la souris (trajectoire
        humaine) — factorise le survol/positionnement avant un clic ou une pause
        décorative, répété par toutes les actions qui interagissent avec une
        annonce (survol, ouverture, favoris). Retourne le bounding_box (ou None
        si l'élément n'est pas visible)."""
        element.scroll_into_view_if_needed()
        box = element.bounding_box()
        if box:
            self._human_mouse_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        return box

    def _human_scroll(self, page, total_delta):
        """Défile de `total_delta` px (signe = direction) en de nombreux petits
        paliers suivant une courbe en cloche (accélération puis décélération),
        pour un mouvement visuellement continu plutôt qu'une poignée de sauts."""
        steps = random.randint(18, 32)
        weights = [math.sin(math.pi * (i + 0.5) / steps) for i in range(steps)]
        weight_sum = sum(weights)
        remaining = total_delta
        for i, w in enumerate(weights):
            chunk = remaining if i == steps - 1 else round(total_delta * w / weight_sum)
            page.mouse.wheel(0, chunk)
            remaining -= chunk
            time.sleep(random.uniform(0.012, 0.045))
