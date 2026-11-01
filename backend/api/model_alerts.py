"""Alerte quand un modèle d'IA est injoignable (2026-11-01) : une notification ntfy, quel que soit le fournisseur (Claude, Gemini,
Qwen cloud, Dell local) et l'appelant (robot, chat Claude, chat Gemini du navigateur).

Deux familles d'échecs :
- **À traiter par l'administrateur** (clé absente, crédit épuisé, clé refusée, modèle retiré) : alerte immédiate, au plus une
  fois par jour pour un même (fournisseur, modèle, cause), avec ce qu'il faut faire ;
- **Pannes passagères** (timeout, surcharge, 429, 5xx, connexion du serveur) : alerte seulement quand elles se répètent,
  `BURST_COUNT` échecs en `BURST_WINDOW_S` secondes pour un même modèle, au plus une fois par heure.

Module autonome (bibliothèque standard seulement), importé par le robot (`llm_usage.record`) ET par l'API : il vit dans
`backend/api/` parce que c'est tout ce dossier que le déploiement recopie vers l'API de production. L'état (dates d'envoi,
compteurs) est en mémoire : un redémarrage peut renvoyer une alerte encore valable, jamais en perdre une. Ne lève jamais et
ne bloque jamais l'appelant (l'envoi se fait dans un fil séparé).
"""
import logging
import os
import threading
import time
import urllib.request
from collections import defaultdict, deque

log = logging.getLogger("model_alerts")

BURST_COUNT = 5
BURST_WINDOW_S = 15 * 60
BURST_COOLDOWN_S = 60 * 60
ACTION_COOLDOWN_S = 24 * 60 * 60

# Cause → (libellé court du titre, consigne pour l'administrateur)
ACTIONS = {
    "no_key": ("clé absente", "Clé API absente : l'ajouter au secret GitHub DOT_ENV (ou au fichier d'environnement du service), puis redéployer."),
    "no_credit": ("crédit épuisé", "Crédit épuisé : recharger le compte du fournisseur."),
    "auth": ("clé refusée", "Clé refusée (invalide, révoquée ou sans droit d'accès) : vérifier la clé du fournisseur et la mettre à jour."),
    "model_unavailable": ("modèle introuvable", "Modèle retiré ou introuvable : choisir un autre modèle dans la configuration."),
}
# Échecs passagers qui comptent pour la détection de répétition
TRANSIENT = ("timeout", "http_429", "connection")

_lock = threading.Lock()
_last_sent = {}  # clé d'alerte -> instant (monotonic) du dernier envoi
_failures = defaultdict(deque)  # (fournisseur, modèle) -> instants des échecs passagers récents


def classify(error_type, source="backend"):
    """('action', cause) | ('transient', type) | None (échec sans intérêt pour l'alerte : JSON invalide, annulation...).
    `source="browser"` : une coupure de connexion est celle du navigateur de l'utilisateur, pas celle du modèle → ignorée."""
    et = str(error_type or "")
    if et in ACTIONS:
        return ("action", et)
    if et in ("http_401", "http_403"):
        return ("action", "auth")
    if et == "http_404":
        return ("action", "model_unavailable")
    if et == "connection" and source == "browser":
        return None
    if et in TRANSIENT or (et.startswith("http_5") and len(et) == 8):
        return ("transient", et)
    return None


def send_ntfy(topic, title, message):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "warning"}, method="POST")
    urllib.request.urlopen(req, timeout=5).close()


def _deliver(title, message):
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        log.warning("[model_alerts] %s — NTFY_TOPIC absent, aucune notification envoyée.", title)
        return
    try:
        send_ntfy(topic, title, message)
    except Exception as e:
        log.warning("[model_alerts] envoi impossible (ignoré) : %s", e)


def _spawn(target, args):
    """Envoi en arrière-plan (point d'injection des tests : ne pas patcher threading.Thread, partagé avec tout le process)."""
    threading.Thread(target=target, args=args, daemon=True).start()


def report_failure(provider, model, error_type, source="backend", now=None):
    """Signale un échec d'appel à un modèle ; envoie (en arrière-plan) une alerte si elle est due. Retourne le titre envoyé
    ou None. Ne lève jamais."""
    try:
        if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("MODEL_ALERTS_TEST"):
            return None  # les tests existants qui simulent des échecs ne doivent jamais envoyer de vraie notification
        kind = classify(error_type, source)
        if kind is None:
            return None
        now = time.monotonic() if now is None else now
        who = f"{provider}/{model}"
        with _lock:
            if kind[0] == "action":
                key, cooldown = (who, kind[1]), ACTION_COOLDOWN_S
            else:
                window = _failures[(provider, model)]
                window.append(now)
                while window and now - window[0] > BURST_WINDOW_S:
                    window.popleft()
                if len(window) < BURST_COUNT:
                    return None
                key, cooldown = (who, "burst"), BURST_COOLDOWN_S
            if key in _last_sent and now - _last_sent[key] < cooldown:
                return None
            _last_sent[key] = now
            count = len(_failures[(provider, model)])
        if kind[0] == "action":
            short, advice = ACTIONS[kind[1]]
            title, message = f"Modele injoignable : {model} ({short})", f"{who} — {advice}"
        else:
            title = f"Modele instable : {model}"
            message = (f"{who} — {count} échecs ({kind[1]}) en moins de {BURST_WINDOW_S // 60} minutes. "
                       "Vérifier l'état du fournisseur ou du réseau.")
        _spawn(_deliver, (title, message))
        return title
    except Exception as e:  # une alerte ne doit jamais faire échouer l'appelant
        log.warning("[model_alerts] signalement impossible (ignoré) : %s", e)
        return None


def reset():
    """Remet l'état à zéro (tests)."""
    with _lock:
        _last_sent.clear()
        _failures.clear()
