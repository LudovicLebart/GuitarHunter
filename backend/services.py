from dataclasses import dataclass, field
import logging
import random
import schedule
import time
import uuid
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
    def __init__(self, scan_func: Callable, cleanup_func: Callable, initial_frequency: int, purge_func: Optional[Callable] = None,
                 leboncoin_scan_func: Optional[Callable] = None, leboncoin_base_frequency_func: Optional[Callable] = None):
        self.scan_func = scan_func
        self.cleanup_func = cleanup_func
        self.purge_func = purge_func
        self.scan_frequency = initial_frequency
        # Scan LeBonCoin : cadence indépendante du scan Facebook, jamais un
        # intervalle fixe (voir _schedule_next_leboncoin_run).
        self.leboncoin_scan_func = leboncoin_scan_func
        self.leboncoin_base_frequency_func = leboncoin_base_frequency_func
        # `schedule` est un scheduler process-wide unique, partagé par TOUTES les
        # instances de TaskScheduler (une par utilisateur, voir main.py) et par le
        # watchdog global. Un tag littéral partagé ('leboncoin_scan') ferait que
        # schedule.clear() d'une instance efface aussi le job d'une autre (ex: un
        # redémarrage watchdog qui recrée un TaskScheduler, ou un futur 2e
        # utilisateur avec LeBonCoin activé) — tag unique par instance.
        self._leboncoin_tag = f"leboncoin_scan_{uuid.uuid4().hex}"
        self._setup_schedules()

    def _setup_schedules(self):
        """Configure les tâches planifiées initiales."""
        logger.info(f"Scheduling scan every {self.scan_frequency} minutes.")
        schedule.every(self.scan_frequency).minutes.do(self.scan_func).tag('scan')
        schedule.every(24).hours.do(self.cleanup_func)
        if self.purge_func:
            schedule.every().week.do(self.purge_func)
            logger.info("Purge lifecycle des images planifiée hebdomadairement.")
        if self.leboncoin_scan_func:
            self._schedule_next_leboncoin_run()

    def _schedule_next_leboncoin_run(self):
        """Planifie le prochain scan LeBonCoin avec un intervalle jitterisé
        (+/-30% de la fréquence de scan Facebook courante) — jamais un
        intervalle fixe, pour ne pas introduire un nouveau pattern régulier
        détectable dans la durée."""
        base_minutes = self.leboncoin_base_frequency_func() if self.leboncoin_base_frequency_func else self.scan_frequency
        jittered_seconds = max(60, base_minutes * 60 * random.uniform(0.7, 1.3))
        logger.info(f"Prochain scan LeBonCoin dans ~{jittered_seconds / 60:.1f} min (base Facebook : {base_minutes} min).")
        schedule.every(jittered_seconds).seconds.do(self._run_leboncoin_once).tag(self._leboncoin_tag)

    def _run_leboncoin_once(self):
        """Exécute le scan LeBonCoin puis reprogramme le suivant avec un nouvel
        intervalle jitterisé — chaque exécution est un "one-shot" qui se
        replanifie lui-même, plutôt qu'une récurrence à intervalle fixe."""
        try:
            self.leboncoin_scan_func()
        except Exception as e:
            logger.error(f"Erreur pendant le scan LeBonCoin planifié : {e}", exc_info=True)
        finally:
            schedule.clear(self._leboncoin_tag)
            self._schedule_next_leboncoin_run()
        return schedule.CancelJob

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
