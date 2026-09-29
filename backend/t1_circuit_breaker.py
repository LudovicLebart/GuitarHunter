"""Coupe-circuit en mémoire pour la chaîne de fournisseurs T1 (`T1_PROVIDER_CHAIN`, voir
`config.py` et `analyzer.py::_run_analysis_cascade`) — Chantier I, étape 2 (2026-09-29).

Process-wide (pas par thread/utilisateur) : une panne Ollama sur le Dell affecte tous les
utilisateurs pareil, inutile de la traquer séparément par thread.

Volontairement minimal (décision utilisateur, 2026-09-28, feuille de route actée avec Opus) :
pas de sondes dédiées, pas de promotion/démotion automatique par qualité, pas de dashboard.
Juste : après `threshold` échecs consécutifs, mettre le fournisseur en pause `cooldown_seconds` ;
le premier appel réel après la pause sert de test (passe -> réouverture, échoue -> nouvelle
pause, sans repasser par `threshold` échecs).
"""
import threading
import time

_lock = threading.Lock()
_state = {}  # provider -> {"consecutive_failures": int, "opened_until": float}


def is_open(provider, now=None):
    """True si ce fournisseur doit être SAUTÉ pour le moment (en pause)."""
    now = now if now is not None else time.time()
    with _lock:
        st = _state.get(provider)
        return bool(st and st["opened_until"] > now)


def record_success(provider):
    """Réinitialise l'historique d'échecs — un seul appel réussi suffit à réouvrir."""
    with _lock:
        _state.pop(provider, None)


def record_failure(provider, threshold, cooldown_seconds, now=None):
    now = now if now is not None else time.time()
    with _lock:
        st = _state.setdefault(provider, {"consecutive_failures": 0, "opened_until": 0.0})
        st["consecutive_failures"] += 1
        if st["consecutive_failures"] >= threshold:
            st["opened_until"] = now + cooldown_seconds


def reset():
    """Vide tout l'état — réservé aux tests (`backend/test_analyzer.py`) : `_state` est un
    global process-wide, sans ça l'historique d'échecs fuit d'un test à l'autre dans le même
    process pytest."""
    with _lock:
        _state.clear()
