import os
import sys
import time
import logging
import threading

print("--- DÉMARRAGE DU SCRIPT MAIN.PY ---", flush=True)

from config import APP_ID_TARGET, USER_IDS_TARGET, FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET
from backend.database import DatabaseService
from backend.bot import GuitarHunterBot
from backend.logging_config import setup_logging
from backend.services import TaskScheduler
import firebase_admin.auth as fb_auth

# --- Sémaphore global : limite le nombre de navigateurs Playwright simultanés ---
MAX_CONCURRENT_BROWSERS = int(os.getenv("MAX_CONCURRENT_BROWSERS", 3))
playwright_semaphore = threading.Semaphore(MAX_CONCURRENT_BROWSERS)

PAUSE_DURATION_SECONDS = 12 * 3600  # 12 heures
WATCHDOG_INTERVAL = 30              # Vérifie les threads toutes les 30s


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


def main_loop(bot, firestore_handler, stop_event, start_event, scan_stop_event):
    logger = logging.getLogger(__name__)
    logger.info("--- Démarrage de la boucle principale ---")

    # Verrou + set protégé pour les commandes en cours d'exécution
    in_flight_lock = threading.Lock()
    in_flight_command_ids = set()

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

                        with in_flight_lock:
                            already_running = command.command_id in in_flight_command_ids
                        if already_running:
                            logger.warning(f"Commande {command.type} (ID: {command.command_id}) déjà en cours. Ignorée.")
                            continue

                        handler = command_handlers.get(command.type)
                        if handler:
                            def execute_command_async(h, p, cid, ctype):
                                with in_flight_lock:
                                    in_flight_command_ids.add(cid)
                                try:
                                    h(p)
                                    if cid: bot.repo.mark_command_completed(cid)
                                except Exception as e:
                                    logger.error(f"Erreur exécution asynchrone commande {ctype}: {e}", exc_info=True)
                                    if cid: bot.repo.mark_command_failed(cid, str(e))
                                finally:
                                    with in_flight_lock:
                                        in_flight_command_ids.discard(cid)

                            if command.type in ['REFRESH', 'REANALYZE_ALL', 'SCAN_URL']:
                                logger.info(f"Lancement de la commande {command.type} dans un thread séparé...")
                                threading.Thread(
                                    target=execute_command_async,
                                    args=(handler, command.payload, command.command_id, command.type),
                                    daemon=True
                                ).start()
                            else:
                                # Exécution synchrone pour les commandes rapides/vitales
                                try:
                                    handler(command.payload)
                                    if command.command_id: bot.repo.mark_command_completed(command.command_id)
                                except Exception as e:
                                    logger.error(f"Erreur exécution synchrone commande {command.type}: {e}", exc_info=True)
                                    if command.command_id: bot.repo.mark_command_failed(command.command_id, str(e))
                        else:
                            logger.warning(f"Type de commande inconnu : {command.type}")
                            if command.command_id:
                                bot.repo.mark_command_failed(command.command_id, f"Type de commande inconnu : {command.type}")

                    if sync_result.new_scan_frequency is not None:
                        scheduler.update_scan_frequency(sync_result.new_scan_frequency)

                time.sleep(5)

                # Vérification de l'arrêt demandé
                if stop_event.is_set():
                    logger.info("⏸️ Commande STOP_BOT reçue. Mise en pause pour 12h max...")
                    bot.set_status('paused', task_name='paused')

                    waited = 0
                    wake_commands = []
                    POLL_INTERVAL = 5

                    while waited < PAUSE_DURATION_SECONDS:
                        if start_event.wait(timeout=POLL_INTERVAL):
                            logger.info("▶️ Commande START_BOT reçue. Reprise immédiate.")
                            break
                        waited += POLL_INTERVAL

                        try:
                            sync_result = bot.sync_and_apply_config()
                            if sync_result and sync_result.commands:
                                actionable = [c for c in sync_result.commands if c.type not in ('STOP_BOT', 'START_BOT')]
                                if actionable:
                                    logger.info(f"▶️ Commande reçue pendant la pause ({actionable[0].type}). Réveil du bot.")
                                    wake_commands = actionable
                                    break
                        except Exception as e:
                            logger.warning(f"Erreur sondage Firestore pendant la pause : {e}")
                    else:
                        logger.info("⏰ Pause de 12h écoulée. Reprise automatique.")

                    stop_event.clear()
                    start_event.clear()
                    bot.set_status('idle', task_name='paused')
                    logger.info("✅ Bot de retour en état idle.")

                    for command in wake_commands:
                        logger.info(f"Traitement de la commande post-pause : {command.type} (ID: {command.command_id})")
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


def _create_user_bot(db_service, user_id):
    """Instancie un GuitarHunterBot + ses events pour un utilisateur donné.
    Retourne (bot, stop_event, start_event, scan_stop_event) ou lève une exception."""
    stop_event = threading.Event()
    start_event = threading.Event()
    scan_stop_event = threading.Event()

    bot = GuitarHunterBot(
        db_service.db,
        db_service.bucket,
        is_offline=False,
        stop_event=stop_event,
        scan_stop_event=scan_stop_event,
        app_id=APP_ID_TARGET,
        user_id=user_id,
        browser_semaphore=playwright_semaphore,
    )
    return bot, stop_event, start_event, scan_stop_event


def _get_user_label(uid):
    """Retourne 'email (uid[:8])' pour les logs. Fallback sur uid[:8] si Firebase Auth échoue."""
    try:
        fb_user = fb_auth.get_user(uid)
        email = fb_user.email or uid[:8]
        return f"{email} ({uid[:8]})"
    except Exception:
        return uid[:8]


def discover_users(db, app_id):
    """Scanne Firestore pour trouver tous les UIDs enregistrés sous l'App ID."""
    try:
        users_ref = db.collection('artifacts').document(app_id).collection('users')
        docs = users_ref.stream()
        return [doc.id for doc in docs]
    except Exception as e:
        logging.getLogger(__name__).error(f"Erreur lors de la découverte des utilisateurs : {e}")
        return []


def start_user_bot(user_id, db_service, user_contexts, offline_mode=False):
    """Initialise et démarre un bot pour un utilisateur s'il n'existe pas déjà."""
    if user_id in user_contexts:
        return False

    label = _get_user_label(user_id)
    logging.getLogger(__name__).info(f"🆕 Nouveau bot détecté pour {label}. Initialisation...")
    
    try:
        firestore_handler = setup_logging(db_service.db, APP_ID_TARGET, user_id, offline_mode)
        bot, stop_event, start_event, scan_stop_event = _create_user_bot(db_service, user_id)

        t = threading.Thread(
            target=main_loop,
            args=(bot, firestore_handler, stop_event, start_event, scan_stop_event),
            daemon=True,
            name=f"bot-{label}"
        )
        user_contexts[user_id] = {
            "thread": t,
            "bot": bot,
            "stop_event": stop_event,
            "start_event": start_event,
            "scan_stop_event": scan_stop_event,
            "firestore_handler": firestore_handler,
        }
        t.start()
        print(f"✅ Bot démarré pour {label}", flush=True)
        return True
    except Exception as e:
        print(f"❌ Impossible de démarrer le bot pour {label}: {e}", flush=True)
        return False


def main():
    """Point d'entrée principal de l'application."""
    print("DEBUG: Initialisation de la DB...", flush=True)
    db_service = DatabaseService(FIREBASE_KEY_PATH, FIREBASE_STORAGE_BUCKET)
    offline_mode = db_service.offline_mode

    if offline_mode:
        print("Le bot est en mode hors ligne. Sortie.", flush=True)
        sys.exit(1)

    print(f"🎸 MAX_CONCURRENT_BROWSERS = {MAX_CONCURRENT_BROWSERS}", flush=True)

    # Dictionnaire : user_id -> { thread, bot, stop_event, start_event, scan_stop_event, firestore_handler }
    user_contexts = {}

    # Premier scan au démarrage
    discovered_uids = discover_users(db_service.db, APP_ID_TARGET)
    all_target_uids = list(set(USER_IDS_TARGET + discovered_uids))
    
    for user_id in all_target_uids:
        start_user_bot(user_id, db_service, user_contexts, offline_mode)

    print(f"✅ {len(user_contexts)} bot(s) actif(s). Watchdog et Découverte dynamique activés.", flush=True)

    try:
        # Boucle de surveillance (watchdog) + Découverte dynamique
        while True:
            time.sleep(WATCHDOG_INTERVAL)
            
            # 1. Découverte de nouveaux utilisateurs
            current_uids = discover_users(db_service.db, APP_ID_TARGET)
            for uid in current_uids:
                if uid not in user_contexts:
                    start_user_bot(uid, db_service, user_contexts, offline_mode)

            # 2. Watchdog : redémarre les threads morts
            for user_id, ctx in list(user_contexts.items()):
                t = ctx["thread"]
                if not t.is_alive():
                    label = _get_user_label(user_id)
                    logging.getLogger(__name__).critical(
                        f"⚠️ Thread bot-{label} est mort ! Tentative de redémarrage..."
                    )
                    try:
                        new_bot, new_stop, new_start, new_scan_stop = _create_user_bot(db_service, user_id)
                        new_t = threading.Thread(
                            target=main_loop,
                            args=(new_bot, ctx["firestore_handler"], new_stop, new_start, new_scan_stop),
                            daemon=True,
                            name=f"bot-{label}"
                        )
                        ctx.update({
                            "thread": new_t,
                            "bot": new_bot,
                            "stop_event": new_stop,
                            "start_event": new_start,
                            "scan_stop_event": new_scan_stop,
                        })
                        new_t.start()
                        logging.getLogger(__name__).info(f"✅ Bot pour {label} redémarré.")
                    except Exception as e:
                        logging.getLogger(__name__).error(
                            f"❌ Redémarrage échoué pour {label}: {e}", exc_info=True
                        )

    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Interruption clavier reçue. Arrêt du bot.")
    finally:
        for ctx in user_contexts.values():
            if ctx.get("firestore_handler"):
                ctx["firestore_handler"].close()
        sys.exit(0)


if __name__ == "__main__":
    main()
