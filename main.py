import sys
import time
import logging
import threading

# On retire la classe Unbuffered qui peut causer des conflits.
# On utilisera flush=True dans les prints critiques.
print("--- DÉMARRAGE DU SCRIPT MAIN.PY ---", flush=True)

from config import APP_ID_TARGET, USER_ID_TARGET, FIREBASE_KEY_PATH
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

def main_loop(bot, firestore_handler):
    logger = logging.getLogger(__name__)
    logger.info("--- Démarrage de la boucle principale ---")
    bot.scraper.start_session()
    
    # Démarrage du thread de surveillance des réanalyses
    threading.Thread(target=monitor_retries, args=(bot,), daemon=True).start()
    
    command_handlers = {
        'REFRESH': lambda _: bot.run_scan(),
        'CLEANUP': lambda _: bot.cleanup_sold_listings(),
        'REANALYZE_ALL': lambda _: bot.reanalyze_all_listings(),
        'SCAN_URL': lambda url: bot.scan_specific_url(url),
        'ADD_CITY': lambda city_name: bot.add_city_auto(city_name),
        'ANALYZE_DEAL': lambda payload: bot.analyze_single_deal(payload),
        'CLEAR_LOGS': lambda _: bot.clear_logs()
    }
    
    try:
        scheduler = TaskScheduler(
            scan_func=bot.run_scan,
            cleanup_func=bot.cleanup_sold_listings,
            initial_frequency=bot.config_manager.get_valid_scan_frequency()
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
                            try:
                                handler(command.payload)
                                if command.command_id: bot.repo.mark_command_completed(command.command_id)
                                elif command.firestore_field: bot.repo.consume_command(command.firestore_field)
                            except Exception as e:
                                logger.error(f"Erreur exécution commande {command.type}: {e}", exc_info=True)
                                if command.command_id: bot.repo.mark_command_failed(command.command_id, str(e))
                        else:
                            logger.warning(f"Type de commande inconnu : {command.type}")
                            if command.command_id: bot.repo.mark_command_failed(command.command_id, f"Type de commande inconnu : {command.type}")
                    
                    if sync_result.new_scan_frequency is not None:
                        scheduler.update_scan_frequency(sync_result.new_scan_frequency)
                
                time.sleep(5)
            except Exception as e:
                logger.error(f"Erreur dans la boucle principale : {e}", exc_info=True)
                time.sleep(15)
    finally:
        logger.info("Arrêt de la boucle principale. Nettoyage...")
        bot.scraper.close_session()
        if firestore_handler:
            firestore_handler.close()

def main():
    """Point d'entrée principal de l'application."""
    print("DEBUG: Initialisation de la DB...", flush=True)
    db_service = DatabaseService(FIREBASE_KEY_PATH)
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
        bot = GuitarHunterBot(db, is_offline=offline_mode)
        main_loop(bot, firestore_handler)
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
