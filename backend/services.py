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
    firestore_field: Optional[str] = None

@dataclass
class SyncResult:
    """Résultat structuré de la synchronisation de la configuration."""
    commands: List[Command] = field(default_factory=list)
    config_changed: bool = False
    new_scan_frequency: Optional[int] = None

class ConfigManager:
    """Gère la configuration du bot et la synchronisation avec Firestore."""
    def __init__(self, repo, initial_scan_config):
        self.repo = repo
        self.scan_config = initial_scan_config.copy()
        self.user_prompt_template = ""
        self.last_refresh_ts = 0
        self.last_cleanup_ts = 0
        self.last_reanalyze_ts = 0

    def sync_with_firestore(self, initial=False):
        """Synchronise la configuration et détecte les commandes."""
        config_data = self.repo.get_user_config()
        if not config_data:
            return SyncResult()

        result = SyncResult()

        # Synchronisation du user prompt
        new_template = self._join_if_list(config_data.get('userPrompt', ''))
        if new_template and new_template != self.user_prompt_template:
            self.user_prompt_template = new_template
            result.config_changed = True
            logger.info("User prompt template updated.")

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

        # Détection des commandes
        if self._check_command(config_data, 'forceRefresh', 'last_refresh_ts', initial):
            result.commands.append(Command(type='REFRESH', firestore_field='forceRefresh'))
            
        if self._check_command(config_data, 'forceCleanup', 'last_cleanup_ts', initial):
            result.commands.append(Command(type='CLEANUP', firestore_field='forceCleanup'))
            
        if self._check_command(config_data, 'forceReanalyzeAll', 'last_reanalyze_ts', initial):
            result.commands.append(Command(type='REANALYZE_ALL', firestore_field='forceReanalyzeAll'))
        
        specific_url = config_data.get('scanSpecificUrl')
        if specific_url:
            # Note: scanSpecificUrl n'est pas basé sur un timestamp mais sur la présence du champ
            result.commands.append(Command(type='SCAN_URL', payload=specific_url, firestore_field='scanSpecificUrl'))

        return result

    def _check_command(self, config_data, key, ts_attr, initial):
        """Vérifie si une commande a été déclenchée via son timestamp."""
        timestamp = config_data.get(key, 0)
        last_ts = getattr(self, ts_attr)
        if not initial and timestamp != last_ts:
            setattr(self, ts_attr, timestamp)
            return True
        elif initial:
            setattr(self, ts_attr, timestamp)
        return False
    
    def get_valid_scan_frequency(self):
        """Valide et retourne la fréquence de scan."""
        try:
            freq = int(self.scan_config.get('frequency', 60))
            return freq if freq > 0 else 60
        except (ValueError, TypeError):
            return 60

    @staticmethod
    def _join_if_list(value):
        return "\n".join(value) if isinstance(value, list) else value

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
