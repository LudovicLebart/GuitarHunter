from dataclasses import dataclass, field
import logging
import schedule
import time
from typing import Optional, Callable, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Modulation de la fréquence de scan (2026-08-24, diagnostic blocages anti-bot) — un cycle
# déclenché à un intervalle parfaitement constant (ex: exactement toutes les 60 minutes, sans
# jamais dévier) est en soi un signal robotique, indépendamment du contenu des requêtes. `schedule`
# supporte nativement un intervalle aléatoire par occurrence (`every(a).to(b).minutes` — re-tiré au
# hasard après chaque exécution), pas besoin de gérer le jitter nous-mêmes.
SCAN_FREQUENCY_JITTER_RATIO = 0.2

_MISSING = object()  # clé absente de scan_config (distincte de None / 0 / "")


def _jittered_bounds(frequency_minutes: int) -> Tuple[int, int]:
    """Bornes (min, max) en minutes autour de `frequency_minutes`, ±SCAN_FREQUENCY_JITTER_RATIO."""
    low = max(1, round(frequency_minutes * (1 - SCAN_FREQUENCY_JITTER_RATIO)))
    high = max(low + 1, round(frequency_minutes * (1 + SCAN_FREQUENCY_JITTER_RATIO)))
    return low, high

@dataclass
class Command:
    """Représente une commande à exécuter par le bot."""
    type: str
    payload: Optional[Any] = None
    command_id: Optional[str] = None      # Pour les commandes de la collection 'commands'

@dataclass
class SyncResult:
    """Résultat structuré de la synchronisation de la configuration."""
    commands: List[Command] = field(default_factory=list)
    config_changed: bool = False
    new_scan_frequency: Optional[int] = None
    full_config: Dict[str, Any] = field(default_factory=dict)

class ConfigManager:
    """Gère la configuration du bot et la synchronisation avec la base de données."""
    def __init__(self, repo, initial_scan_config):
        self.repo = repo
        self.scan_config = initial_scan_config.copy()
        self.current_config_snapshot = {}

    def sync_with_db(self, initial=False):
        """Synchronise la configuration et détecte les commandes."""
        config_data = self.repo.get_user_config()
        if not config_data:
            return SyncResult()

        result = SyncResult()
        result.full_config = config_data
        self.current_config_snapshot = config_data

        # Synchronisation de la config de scan
        # Comparer APRÈS fusion : self.scan_config contient des valeurs par défaut absentes de la
        # config stockée, donc `stockée != self.scan_config` serait vrai en permanence (R-9-10).
        new_scan_config = config_data.get('scanConfig', {})
        if any(self.scan_config.get(k, _MISSING) != v for k, v in new_scan_config.items()):
            old_freq = self.scan_config.get('frequency')
            self.scan_config.update(new_scan_config)
            new_freq = self.scan_config.get('frequency')
            if old_freq != new_freq:
                result.new_scan_frequency = self.get_valid_scan_frequency()
            result.config_changed = True
            logger.info("Scan config updated.")

        # --- Commandes Collection (Nouvelle Architecture) ---
        # On ne vérifie pas les commandes lors de l'initialisation pour éviter de rejouer de vieilles commandes
        if not initial:
            pending_docs = self.repo.get_pending_commands()
            for doc in pending_docs:
                data = doc.to_dict()
                cmd_type = data.get('type')
                payload = data.get('payload')
                
                if cmd_type:
                    result.commands.append(Command(
                        type=cmd_type,
                        payload=payload,
                        command_id=doc.id
                    ))

        return result
    
    def get_valid_scan_frequency(self):
        """Valide et retourne la fréquence de scan."""
        try:
            freq = int(self.scan_config.get('frequency', 60))
            return freq if freq > 0 else 60
        except (ValueError, TypeError):
            return 60

class TaskScheduler:
    """Gère la planification et l'exécution des tâches du bot."""
    def __init__(self, scan_func: Callable, cleanup_func: Callable, initial_frequency: int,
                 purge_func: Optional[Callable] = None, bot_logger: Optional[logging.Logger] = None):
        # Chaque tâche est enveloppée : une exception ne doit pas laisser le job « en retard »
        # (`schedule` ne le replanifie pas) et donc le relancer à chaque tour de boucle.
        # `bot_logger` : logger du bot, seul visible dans le LogViewer (voir CLAUDE.md).
        self._log = bot_logger or logger
        self.scan_func = self._guarded(scan_func, "scan")
        self.cleanup_func = self._guarded(cleanup_func, "nettoyage")
        self.purge_func = self._guarded(purge_func, "purge") if purge_func else None
        self.scan_frequency = initial_frequency
        # Instance dédiée : le planificateur global de `schedule` est partagé par tout le
        # processus (R-2-1) — un clear('scan') ou un run_pending() y toucherait tous les bots.
        self._scheduler = schedule.Scheduler()
        self._setup_schedules()

    def _setup_schedules(self):
        """Configure les tâches planifiées initiales."""
        low, high = _jittered_bounds(self.scan_frequency)
        self._log.info(f"Scheduling scan every {low}-{high} minutes (base {self.scan_frequency}, jitter ±{int(SCAN_FREQUENCY_JITTER_RATIO * 100)}%).")
        self._scheduler.every(low).to(high).minutes.do(self.scan_func).tag('scan')
        self._scheduler.every(6).hours.do(self.cleanup_func)
        if self.purge_func:
            self._scheduler.every().week.do(self.purge_func)
            self._log.info("Purge lifecycle des images planifiée hebdomadairement.")

    def _guarded(self, func: Callable, name: str) -> Callable:
        def run():
            try:
                return func()
            except Exception as e:
                self._log.error(f"Tâche planifiée « {name} » en échec : {e}", exc_info=True)
        return run

    def jobs(self, tag: Optional[str] = None) -> list:
        """Jobs de ce bot (optionnellement filtrés par tag)."""
        return self._scheduler.get_jobs(tag) if tag else self._scheduler.get_jobs()

    def run_pending(self):
        """Exécute les tâches en attente.

        Après une pause du bot (jusqu'à 12 h), `run_pending` n'est pas appelé : à la reprise, les
        tâches échues (scan, nettoyage, purge) partent une seule fois chacune, l'une après l'autre.
        """
        self._scheduler.run_pending()

    def close(self):
        """Retire tous les jobs de ce bot (arrêt du thread utilisateur)."""
        self._scheduler.clear()

    def update_scan_frequency(self, new_frequency: int):
        """Met à jour la fréquence de la tâche de scan."""
        if new_frequency != self.scan_frequency:
            self.scan_frequency = new_frequency
            self._scheduler.clear('scan')
            low, high = _jittered_bounds(self.scan_frequency)
            self._scheduler.every(low).to(high).minutes.do(self.scan_func).tag('scan')
            self._log.info(f"Rescheduled scan to every {low}-{high} minutes (base {self.scan_frequency}, jitter ±{int(SCAN_FREQUENCY_JITTER_RATIO * 100)}%).")
