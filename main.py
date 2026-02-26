import sys
import time
import logging
import threading

# On retire la classe Unbuffered qui peut causer des conflits.
# On utilisera flush=True dans les prints critiques.
print("--- DÉMARRAGE DU SCRIPT MAIN.PY ---", flush=True)

from config import APP_ID_TARGET, USER_ID_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.bot import GuitarHunterBot
from backend.logging_config import setup_logging
from backend.services import TaskScheduler

def monitor_retries(bot):
    """Thread qui surveille et traite la file d'attente de réanalyse."""
    logger = logging.getLogger(__name__)
    logger.info("Thread de surveillance des réanalyses démarré.")
    while True:
        try:
            bot.process_retry_queue()
            time.sleep(5)
        except Exception as e:
            logger.error(f"Erreur dans le thread de réanalyse : {e}", exc_info=True)
            time.sleep(10)

def _trigger_stop_scan(scan_stop_event):
    """Active le scan_stop_event et le remet à zéro après 3 secondes dans un thread daemon."""
    logger = logging.getLogger(__name__)
    logger.info("⏹️ Commande STOP_SCAN reçue. Interruption du scan en cours...")
    scan_stop_event.set()
    def _reset():
        time.sleep(3)
        scan_stop_event.clear()
        logger.info("⏹️ scan_stop_event remis à zéro. Le bot peut relancer un scan.")
    threading.Thread(target=_reset, daemon=True).start()

PAUSE_DURATION_SECONDS = 12 * 3600  # 12 heures

def main_loop(bot, firestore_handler, stop_event, start_event, scan_stop_event):
    logger = logging.getLogger(__name__)
    logger.info("--- Démarrage de la boucle principale ---")
    
    # Démarrage du thread de surveillance des réanalyses
    threading.Thread(target=monitor_retries, args=(bot,), daemon=True).start()
    
    command_handlers = {
        'REFRESH': lambda _: bot.run_scan(),
        'CLEANUP': lambda _: bot.cleanup_sold_listings(),
        'REANALYZE_ALL': lambda _: bot.reanalyze_all_listings(),
        'SCAN_URL': lambda url: bot.scan_specific_url(url),
        'ADD_CITY': lambda city_name: bot.add_city_auto(city_name),
        'ANALYZE_DEAL': lambda payload: bot.analyze_single_deal(payload),
        'CLEAR_LOGS': lambda _: bot.clear_logs(),
        'STOP_BOT': lambda _: stop_event.set(),
        'STOP_SCAN': lambda _: _trigger_stop_scan(scan_stop_event),
        'START_BOT': lambda _: start_event.set(),
    }
    
    try:
        scheduler = TaskScheduler(
            scan_func=bot.run_scan,
            cleanup_func=bot.cleanup_sold_listings,
            initial_frequency=bot.config_manager.get_valid_scan_frequency(),
            purge_func=bot.purge_rejected_images
        )
        while True:
            try:
                scheduler.run_pending()
                sync_result = bot.sync_and_apply_config()
                
                if sync_result:
                    for command in sync_result.commands:
                        logger.info(f"Commande reçue : {command.type} (ID: {command.command_id})")
                        handler = command_handlers.get(command.type)
                        if handler:
                            # Définition d'une fonction wrapper pour exécuter la commande asynchronement
                            def execute_command_async(h, p, cid, ctype):
                                try:
                                    h(p)
                                    if cid: bot.repo.mark_command_completed(cid)
                                except Exception as e:
                                    logger.error(f"Erreur exécution asynchrone commande {ctype}: {e}", exc_info=True)
                                    if cid: bot.repo.mark_command_failed(cid, str(e))

                            if command.type in ['REFRESH', 'REANALYZE_ALL', 'SCAN_URL']:
                                logger.info(f"Lancement de la commande {command.type} dans un thread séparé...")
                                threading.Thread(target=execute_command_async, args=(handler, command.payload, command.command_id, command.type), daemon=True).start()
                            else:
                                # Exécution synchrone pour les commandes rapides/vitales (STOP_BOT, CLEAR_LOGS...)
                                try:
                                    handler(command.payload)
                                    if command.command_id: bot.repo.mark_command_completed(command.command_id)
                                except Exception as e:
                                    logger.error(f"Erreur exécution synchrone commande {command.type}: {e}", exc_info=True)
                                    if command.command_id: bot.repo.mark_command_failed(command.command_id, str(e))
                        else:
                            logger.warning(f"Type de commande inconnu : {command.type}")
                            if command.command_id: bot.repo.mark_command_failed(command.command_id, f"Type de commande inconnu : {command.type}")
                    
                    if sync_result.new_scan_frequency is not None:
                        scheduler.update_scan_frequency(sync_result.new_scan_frequency)
                
                time.sleep(5)

                # Vérification de l'arrêt demandé
                if stop_event.is_set():
                    logger.info("⏸️ Commande STOP_BOT reçue. Mise en pause pour 12h max...")
                    bot.set_status('paused', task_name='paused')
                    
                    waited = 0
                    wake_commands = []  # Commandes reçues pendant la pause à exécuter après réveil
                    POLL_INTERVAL = 5  # Interroge Firestore toutes les 5 secondes

                    while waited < PAUSE_DURATION_SECONDS:
                        # Vérifie d'abord le START_BOT (événement rapide)
                        if start_event.wait(timeout=POLL_INTERVAL):
                            logger.info("▶️ Commande START_BOT reçue. Reprise immédiate.")
                            break
                        waited += POLL_INTERVAL

                        # Interrogation de Firestore pour des commandes actionnables pendant la pause
                        try:
                            sync_result = bot.sync_and_apply_config()
                            if sync_result and sync_result.commands:
                                # Filtre les commandes qui ne sont pas STOP_BOT (déjà actif) ni START_BOT (géré via start_event)
                                actionable = [c for c in sync_result.commands if c.type not in ('STOP_BOT', 'START_BOT')]
                                if actionable:
                                    logger.info(f"▶️ Commande reçue pendant la pause ({actionable[0].type}). Réveil du bot.")
                                    wake_commands = actionable  # On les exécutera après le réveil
                                    break
                        except Exception as e:
                            logger.warning(f"Erreur sondage Firestore pendant la pause : {e}")
                    else:
                        logger.info("⏰ Pause de 12h écoulée. Reprise automatique.")

                    stop_event.clear()
                    start_event.clear()
                    bot.set_status('idle', task_name='paused')
                    logger.info("✅ Bot de retour en état idle.")
                    
                    # Traitement des commandes reçues pendant la pause
                    for command in wake_commands:
                        logger.info(f"Traitement de la commande reçue pendant la pause : {command.type} (ID: {command.command_id})")
                        handler = command_handlers.get(command.type)
                        if handler:
                            try:
                                handler(command.payload)
                                if command.command_id: bot.repo.mark_command_completed(command.command_id)
                            except Exception as e:
                                logger.error(f"Erreur exécution commande post-pause {command.type}: {e}", exc_info=True)
                                if command.command_id: bot.repo.mark_command_failed(command.command_id, str(e))

            except Exception as e:
                logger.error(f"Erreur dans la boucle principale : {e}", exc_info=True)
                time.sleep(15)
    finally:
        logger.info("Arrêt de la boucle principale. Nettoyage...")
        if firestore_handler:
            firestore_handler.close()

def main():
    """Point d'entrée principal de l'application."""
    print("DEBUG: Initialisation de la DB...", flush=True)
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    db = db_service.db
    offline_mode = db_service.offline_mode

    print("DEBUG: Configuration du logging...", flush=True)
    firestore_handler = setup_logging(db, APP_ID_TARGET, USER_ID_TARGET, offline_mode)
    
    logger = logging.getLogger(__name__)
    logger.info("Logging initialisé avec succès.")

    if offline_mode:
        logger.warning("Le bot est en mode hors ligne. Sortie.")
        sys.exit(1)

    exit_code = 0
    try:
        print("DEBUG: Lancement du bot...", flush=True)
        # Events pour pilotage asynchrone du bot
        stop_event = threading.Event()
        start_event = threading.Event()
        scan_stop_event = threading.Event()
        bot = GuitarHunterBot(db, db_service.bucket, is_offline=offline_mode, stop_event=stop_event, scan_stop_event=scan_stop_event)
        main_loop(bot, firestore_handler, stop_event, start_event, scan_stop_event)
    except KeyboardInterrupt:
        logger.info("Interruption clavier reçue. Arrêt du bot.")
    except Exception as e:
        logger.critical(f"Erreur critique non gérée au démarrage : {e}", exc_info=True)
        exit_code = 1
    finally:
        logger.info("Fermeture propre de l'application.")
        if firestore_handler:
            firestore_handler.close()
        sys.exit(exit_code)

if __name__ == "__main__":
    main()
