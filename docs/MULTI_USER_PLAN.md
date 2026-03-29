# Plan d'Implémentation : Architecture Multi-Utilisateur (Superviseur/Worker)

**Objectif :** Transformer le bot monoprocessus actuel en un système capable de gérer plusieurs utilisateurs simultanément, tout en limitant strictement l'empreinte mémoire du serveur (nombre maximum de navigateurs Playwright ouverts en même temps).

**Stratégie :** Créer une architecture parallèle (non destructive pour l'existant) basée sur le modèle `Superviseur -> N x Workers (Processus isolés)`.

**Modèle IA Recommandé pour l'exécution :** `Gemini 2.5 Pro` (Nécessite une compréhension approfondie des threads, des sous-processus et de la gestion d'état Firestore).

---

## Étape 1 : Préparation de la Base de Données (Firestore)

Actuellement, le bot se base sur des variables d'environnement (`APP_ID_TARGET`, `USER_ID_TARGET`) pour savoir qui scanner. Dans un contexte multi-utilisateur, le Superviseur doit découvrir dynamiquement les utilisateurs actifs.

**Actions (Agent) :**
1.  Créer un script utilitaire (ex: `backend/scripts/register_user.py`) ou documenter la structure nécessaire dans Firestore.
2.  **Nouvelle Collection :** Définir une collection globale `registered_users` à la racine de Firestore (ou sous `artifacts/{APP_ID}/registered_users`).
3.  **Structure du Document Utilisateur :**
    ```json
    {
      "user_id": "UID_FIREBASE",
      "email": "user@example.com", // Optionnel, pour le debug
      "is_active": true, // Permet de désactiver un utilisateur sans supprimer ses données
      "last_scan_timestamp": null // Pour savoir quand le prochain scan est dû
    }
    ```

## Étape 2 : Création du Worker Indépendant (`backend/worker.py`)

Le Worker est un script court, conçu pour mourir dès qu'il a terminé sa tâche. Il prend en entrée les identifiants d'un utilisateur, exécute **uniquement** le scraping et l'analyse pour cet utilisateur, puis s'arrête, libérant ainsi la mémoire (Playwright).

**Actions (Agent) :**
1.  Créer le fichier `backend/worker.py`.
2.  Le script doit utiliser `argparse` pour accepter deux arguments : `--app-id` et `--user-id`.
3.  **Logique interne :**
    *   Initialiser la connexion Firebase (via `DatabaseService`).
    *   Instancier `GuitarHunterBot` en lui passant spécifiquement l'`app_id` et le `user_id` reçus en arguments (nécessite une petite adaptation de `bot.py` si ces valeurs sont hardcodées depuis `config.py`).
    *   Charger la configuration de cet utilisateur depuis Firestore (`sync_and_apply_config`).
    *   Exécuter `bot.run_scan()` (qui va scraper toutes les villes configurées par cet utilisateur).
    *   Terminer le processus avec un code de retour propre (0 pour succès, 1 pour erreur).
4.  **Logging :** S'assurer que les logs de ce script spécifique remontent bien dans la collection `logs` de *l'utilisateur concerné* dans Firestore.

## Étape 3 : Création du Superviseur (`supervisor.py`)

Le Superviseur est le chef d'orchestre persistant. Il tourne en boucle, observe Firestore, et décide quand lancer un `worker.py`. **Il n'importe jamais Playwright.**

**Actions (Agent) :**
1.  Créer le fichier `supervisor.py` à la racine du projet (au même niveau que `main.py`).
2.  **Configuration :** Définir une constante `MAX_CONCURRENT_WORKERS = 3` (Ajustable selon la RAM du serveur).
3.  **Boucle Principale (`while True`) :**
    *   Interroger la collection `registered_users` dans Firestore pour obtenir la liste des utilisateurs où `is_active == true`.
    *   Pour chaque utilisateur :
        *   Récupérer sa configuration (fréquence de scan) dans `artifacts/{APP_ID}/users/{USER_ID}/botConfig`.
        *   Calculer si un scan est dû en comparant `last_scan_timestamp` avec la fréquence.
    *   Générer une "file d'attente" interne (liste Python) des utilisateurs nécessitant un scan.
4.  **Gestion des Processus (Le cœur du système) :**
    *   Utiliser la bibliothèque standard `subprocess` (ex: `subprocess.Popen`) pour lancer `python backend/worker.py --app-id ... --user-id ...`.
    *   Maintenir une liste des processus actifs.
    *   **Contrôle strict :** Ne lancer un nouveau subprocess que si le nombre actuel de processus actifs est inférieur à `MAX_CONCURRENT_WORKERS`.
    *   Vérifier régulièrement (ex: `process.poll()`) si des workers ont terminé pour les retirer de la liste des actifs et libérer des "slots".
5.  **Mise à jour du statut :** Après le lancement réussi d'un worker pour un utilisateur, mettre à jour son `last_scan_timestamp` dans la collection `registered_users` pour éviter qu'il ne soit relancé immédiatement au prochain tour de boucle.

## Étape 4 : Gestion des Commandes Manuelles (Le Défi)

Dans `main.py`, le frontend envoie des commandes (`REFRESH`, `STOP_SCAN`) qui sont lues par la boucle principale. Avec le Superviseur, cette logique doit évoluer.

**Actions (Agent) :**
1.  Le Superviseur (`supervisor.py`) doit **aussi** écouter la sous-collection `commands` de *chaque* utilisateur actif.
2.  Si un utilisateur envoie un `REFRESH` :
    *   Le Superviseur place cet utilisateur en tête de file d'attente (priorité haute).
    *   Dès qu'un slot worker se libère, il lance un `worker.py` pour cet utilisateur (même si le `last_scan_timestamp` indique qu'il n'est pas encore l'heure).
3.  Si un utilisateur envoie un `STOP_BOT` ou `STOP_SCAN` :
    *   Le Superviseur doit identifier le `subprocess` (le PID) correspondant au worker de cet utilisateur (s'il est en cours d'exécution) et lui envoyer un signal d'arrêt (ex: `process.terminate()`).

## Phase de Test et Migration

1.  Conserver l'ancien `main.py` intact.
2.  Lancer manuellement `supervisor.py` pour tester le système avec quelques utilisateurs "cobayes" inscrits dans la nouvelle collection Firestore.
3.  Vérifier via la commande `top` ou `htop` sur le serveur que le nombre d'instances de Python reste plafonné à `MAX_CONCURRENT_WORKERS + 1` (les workers + le superviseur).
4.  Une fois validé, le script de démarrage du serveur (`run.bat` / service systemd) sera modifié pour pointer vers `supervisor.py` au lieu de `main.py`.
