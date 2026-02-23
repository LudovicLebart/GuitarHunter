from dataclasses import dataclass, field
import logging
import schedule
import time
from typing import Optional, Callable, List, Dict, Any

logger = logging.getLogger(__name__)

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
    """Gère la configuration du bot et la synchronisation avec Firestore."""
    def __init__(self, repo, initial_scan_config):
        self.repo = repo
        self.scan_config = initial_scan_config.copy()
        self.current_config_snapshot = {} 

    def sync_with_firestore(self, initial=False):
        """Synchronise la configuration et détecte les commandes."""
        config_data = self.repo.get_user_config()
        if not config_data:
            return SyncResult()

        result = SyncResult()
        result.full_config = config_data
        self.current_config_snapshot = config_data

        # Synchronisation de la config de scan
        new_scan_config = config_data.get('scanConfig', {})
        if new_scan_config != self.scan_config:
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
    def __init__(self, scan_func: Callable, cleanup_func: Callable, initial_frequency: int):
        self.scan_func = scan_func
        self.cleanup_func = cleanup_func
        self.scan_frequency = initial_frequency
        self._setup_schedules()

    def _setup_schedules(self):
        """Configure les tâches planifiées initiales."""
        logger.info(f"Scheduling scan every {self.scan_frequency} minutes.")
        schedule.every(self.scan_frequency).minutes.do(self.scan_func).tag('scan')
        schedule.every(24).hours.do(self.cleanup_func)

    def run_pending(self):
        """Exécute les tâches en attente."""
        schedule.run_pending()

    def update_scan_frequency(self, new_frequency: int):
        """Met à jour la fréquence de la tâche de scan."""
        if new_frequency != self.scan_frequency:
            self.scan_frequency = new_frequency
            schedule.clear('scan')
            schedule.every(self.scan_frequency).minutes.do(self.scan_func).tag('scan')
            logger.info(f"Rescheduled scan to every {self.scan_frequency} minutes.")
