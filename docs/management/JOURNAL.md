# Journal de Bord - Guitar Hunter AI

[2026-07-11] [PRO] Fix : Cause racine de l'absence d'emails "Pépite" trouvée + pipeline de déploiement fragilisé au passage → Résultat :
- **Cause confirmée** : le secret GitHub `DOT_ENV` ne contenait jamais `SMTP_USER`/`SMTP_PASSWORD` depuis la mise en place de la feature — `.env.example` les documentait comme modèle, mais jamais reportés dans le vrai secret. Ni un bug de code (le fix logger du 2026-07-09 était correct mais insuffisant pour ce diagnostic), ni des identifiants Gmail révoqués. Confirmé par investigation en direct avec l'utilisateur : `WorkingDirectory` du service `guitare-hunter` vérifié correct, `.env` déployé confirmé présent et à jour (timestamp du déploiement), mais `grep -o '^[A-Z_]*=' ~/GuitareHunter/.env` ne listait aucune clé `SMTP_`.
- **Bug découvert en corrigeant** : après ajout des lignes SMTP au secret, 2 déploiements consécutifs ont échoué (`bash: erreur de syntaxe près du symbole inattendu « ) »`) sur les jobs `deploy-frontend` ET `deploy` (SSH). Cause : `.github/workflows/deploy.yml` interpolait `${{ secrets.DOT_ENV }}`/`${{ secrets.FIREBASE_SERVICE_ACCOUNT_KEY }}` littéralement dans les scripts bash (`echo "${{ secrets.X }}" > .env`) — un simple guillemet dans la valeur du secret casse la chaîne bash et fait échouer tout le déploiement, quel que soit le contenu voulu.
- **`deploy.yml` durci** : `DOT_ENV` transmis via `env:` au step `Create .env file` (référencé `"$DOT_ENV"`, plus jamais interpolé littéralement). Pour le job `deploy` (SSH, `appleboy/ssh-action`), `DOT_ENV`/`FIREBASE_SERVICE_ACCOUNT_KEY` transmis via le paramètre `envs:` de l'action plutôt qu'interpolés dans le script distant. `echo >` remplacé par `printf '%s' >` pour l'écriture des fichiers. Rend le pipeline robuste à n'importe quel caractère dans les secrets, sans avoir à les éditer avec précaution.
- **Outils utilisés pour le diagnostic** : LogViewer (curseur "Limite Temporaire de Logs" du `ConfigPanel`, jusqu'à 500 lignes — pas 100, contrairement à l'idée reçue de l'utilisateur), historique des runs GitHub Actions (`mcp__github__actions_list`/`get_job_logs`) pour confirmer succès/échec et timestamps de déploiement, vérifications directes sur le serveur (`systemctl show`, `grep` sur `.env`).

[2026-07-11] [PRO] Fix : `schedule.run_pending()` non protégé dans la boucle watchdog globale (risque de crash process-wide) → Résultat :
- **Contexte** : Revue du commit "Dashboard Administrateur — Phase 1" (voir entrée suivante) à la demande de l'utilisateur ("vérifie que ça ne pose pas de problèmes"). Ce commit ajoute `schedule.every().day.at("03:00").do(run_admin_stats_job, ...)` et un appel `schedule.run_pending()` dans la boucle watchdog globale de `main.py`.
- **Risque identifié** : `backend/services.py::TaskScheduler` utilise le scheduler **global partagé** de la librairie `schedule` (pas d'instance dédiée) — chaque thread utilisateur y enregistre ses jobs (`scan`/`cleanup`/`purge`) sur la même liste. Jusqu'ici, `schedule.run_pending()` n'était appelé que depuis la boucle interne de chaque thread utilisateur (`main.py:82`), protégée par un `except Exception` qui logue et continue. Le nouvel appel dans la boucle watchdog globale n'était protégé que par `except KeyboardInterrupt` — comme `run_pending()` exécute *tous* les jobs dus (pas seulement `admin_stats`), une exception non gérée dans le job planifié de n'importe quel utilisateur aurait fait planter tout le process, tous utilisateurs confondus, via le mécanisme censé les protéger d'une panne isolée.
- **`main.py`** : Ajout d'un `try/except Exception` dédié autour de l'appel, même pattern que la boucle par-utilisateur (log + continue, pas d'interruption du watchdog).

[2026-07-11] [PRO] Feature : Dashboard Administrateur — Phase 1 (Monitoring, lecture seule) → Résultat :
- **`backend/scripts/set_admin_claim.py`** : Script one-shot (Admin SDK) pour poser le custom claim `admin: true` sur un compte Firebase. Usage : `python backend/scripts/set_admin_claim.py --email admin@example.com` (option `--revoke` pour retrait).
- **`firebase/firestore.rules`** : Ajout de la fonction `isAdmin()` (`request.auth.token.admin == true`) + règles `collectionGroup('users')` et `collectionGroup('guitar_deals')` autorisant la lecture cross-utilisateurs uniquement pour l'admin. Nouvelle collection `admin_stats/{docId}` en lecture admin, écriture interdite au client (Admin SDK only). Les règles d'isolation utilisateur existantes sont inchangées.
- **`backend/admin_stats.py`** : Job quotidien calculant, par utilisateur, le volume `guitar_deals` des dernières 24h, le funnel Tier 1→2→3 et le coût Gemini estimé. Réutilise les constantes et formules de `analyze_funnel_by_user.py`. Écrit dans `artifacts/{APP_ID}/admin_stats/latest`.
- **`main.py`** : Intégration du job `run_admin_stats_job` dans la boucle watchdog via `schedule.every().day.at("03:00")` (singleton global, une seule fois quel que soit le nombre de threads utilisateur).
- **`src/hooks/useAuth.js`** : Nouveau state `isAdmin` initialisé via `firebaseUser.getIdTokenResult()` à chaque changement d'état d'auth. Vérification défensive côté client (la vraie protection reste les règles Firestore). Exposé dans le return du hook.
- **`src/components/Navbar.jsx`** : Bouton `ShieldCheck` affiché uniquement si `isAdmin === true`. Nouvelle prop `onOpenAdmin`.
- **`src/components/Dashboard.jsx`** : Import et montage conditionnel de `AdminDashboard` via `showAdmin` state.
- **`src/components/AdminDashboard.jsx`** : Nouveau composant — tableau des utilisateurs (email, UID, botStatus, villes, fréquence de scan, dernier login), enrichi par les stats de coût/volume du snapshot `admin_stats/latest` (non-bloquant si absent). Bouton Rafraîchir.
- **Phase 2 non livrée** : Actions privilégiées (`DISABLE_USER`, `SEND_EMAIL`, `STOP_BOT` admin, journal d'audit) restent planifiées dans `ADMIN_DASHBOARD_PLAN.md`.

[2026-07-11] [PRO] Fix : STOP_SCAN/STOP_BOT/START_BOT échouaient toujours ("Erreur lors de l'envoi de la commande") → Résultat :
- **Symptôme signalé** : clic sur "Interrompre le scan" → alerte `Erreur STOP_SCAN: Erreur lors de l'envoi de la commande.`
- **Cause** : `src/components/Navbar.jsx` appelle `triggerStopScan()`/`triggerStopBot()`/`triggerStartBot()` (`firestoreService.js`) directement, sans passer par `useBotConfig.js` (qui fournit correctement `user.uid` pour Refresh/Cleanup/Reanalyze). Ces 3 appels n'avaient aucun argument `userId` → `getRefs(undefined)` lève une erreur (fail fast, voir CLAUDE.md), catchée par `addCommand()` et remplacée par le message générique `"Erreur lors de l'envoi de la commande."` — masquant la vraie cause à l'utilisateur comme dans les logs.
- **`Navbar.jsx`** : `user` récupéré via `useAuth()` (déjà importé pour `signOut`, mais jamais destructuré) et passé en `user?.uid` aux 3 appels.
- **Non couvert par les tests/lint** : bug uniquement visible à l'usage (clic bouton), invisible en compilation puisque `userId` est un paramètre optionnel côté JS.

[2026-07-11] [PRO] Feature : Stat "Erreurs Portier corrigées" (StatsView) → Résultat :
- **Contexte** : Suite à un cas réel observé par l'utilisateur (une annonce rejetée par le Portier, réanalysée manuellement, révélée comme une Pépite), constat que `dev` disposait déjà d'un outil de diagnostic ponctuel (`analyze_funnel_by_user.py --sample-size`, §8.2 de `GEMINI_PROMPT_CACHING_PLAN.md`) mais rien d'automatisé/permanent dans l'app pour suivre ce taux d'erreur dans le temps.
- **`backend/repository.py::create_new_deal()`** : deux nouveaux champs figés à la création, jamais réécrits par les réanalyses ultérieures (contrairement à `aiAnalysis`) : `initialVerdict` (verdict du tout premier passage IA) et `initialModelUsed` (chaîne `model_used` du premier passage, ex: `"gemini-2.5-flash-lite"` si arrêté au Portier seul).
- **`src/components/StatsView.jsx`** : nouvelle stat sous le Funnel — parmi les annonces dont la chaîne `initialModelUsed` ne compte qu'un seul maillon (= arrêtées au Portier seul, jamais passées à l'Analyste), compte celles dont la chaîne `aiAnalysis.model_used` **actuelle** compte 2 maillons ou plus (= réanalysées avec succès depuis). Affichage : `X/Y (Z%)`.
- **Pourquoi pas une simple comparaison de `verdict`** : `BAD_DEAL` peut provenir soit d'un vrai rejet Portier, soit d'un verdict légitime de l'Analyste (Tier 2) après analyse complète ("trop cher") — les confondre aurait faussé la stat. La longueur de chaîne `model_used` lève l'ambiguïté sans dépendre du texte du verdict (qui est configurable par l'utilisateur via `rejectionVerdicts`).
- **Limite assumée** : pas de backfill — seules les annonces créées après ce déploiement auront `initialVerdict`/`initialModelUsed` ; la stat démarre à 0/0.
- **Branche** : rebase (fast-forward) de `claude/claude-md-literate-ovyt5p` sur `dev` avant implémentation (18 commits de retard sur `master`, incluant le fix du faux positif Portier "acoustique 12 cordes" — voir `GEMINI_PROMPT_CACHING_PLAN.md §8.2`).

[2026-07-09] [FLASH] Ajout : Script de test manuel du pipeline de notifications → Résultat :
- `backend/scripts/test_notification.py` : déclenche une notification factice (verdict `PEPITE`) sans attendre un vrai scan, avec le vrai logger par-utilisateur (raccordé au LogViewer). Usage : `python3 backend/scripts/test_notification.py` (utilise `USER_ID_TARGET` du `.env` et l'email Firebase Auth associé par défaut ; `--user-id`/`--email` pour surcharger).
- **Raison** : Suite au signalement "plus d'email reçu, seulement des ntfy", permet de diagnostiquer directement la cause (SMTP mal configuré vs identifiants Gmail révoqués) sans dépendre du hasard d'un scan qui trouve une vraie Pépite.

[2026-07-09] [PRO] Fix : Logs de `notifications.py` et `analyzer.py` invisibles dans le LogViewer (même bug que le scraper) → Résultat :
- **Contexte** : Signalement "plus d'email reçu, seulement des ntfy". Investigation de l'historique Git de `notifications.py`/`bot.py`/`deploy.yml` — aucun changement de code récent ne touche l'envoi d'email ou les identifiants SMTP, et la résolution de l'email utilisateur fonctionne (confirmé par les logs). Régression probablement externe (identifiants Gmail révoqués/expirés, ou variable d'environnement serveur manquante) — non confirmable tant que l'erreur réelle restait invisible.
- **Cause** : `notifications.py` et `analyzer.py` loguaient via `logging.getLogger(__name__)` (loggers de module), jamais raccordés au logger par-utilisateur `bot.{user_id}` — même bug que celui déjà corrigé pour `backend/scraping/` (voir plus bas).
- **`analyzer.py`** : `DealAnalyzer.__init__` accepte un `logger` optionnel ; les 18 appels `logger.x()` de la classe basculés sur `self.logger.x()`. `bot.py` passe `logger=self.logger` aux 2 instanciations.
- **`notifications.py`** : `NtfyNotifier.send()`/`EmailNotifier.send()`/`NotificationService.notify_deal()`/`notify_model_error()` acceptent tous un paramètre `logger` optionnel, propagé depuis `bot.py` et `analyzer.py`.
- **Bonus** : `EmailNotifier.send()` logue désormais explicitement quand l'envoi est bloqué par une config SMTP manquante (avant : un seul warning au tout premier chargement du module, jamais revu ensuite — ratait donc silencieusement chaque tentative suivante).

[2026-07-09] [PRO] Fix : `gemini-2.5-flash` (Tier 2 — Analyste) n'est plus disponible chez Google (404) → Résultat :
- Remplacé par `gemini-3.5-flash` partout où codé en dur : `backend/analyzer.py` (fallback runtime `config.get('mainModel', ...)` — probable cause directe du 404 en prod, puisque `mainModel` n'est jamais initialisé dans la structure Firestore créée pour un nouvel utilisateur), `config.py::GEMINI_MODELS` (`default_analyst` + retrait de la liste `available`), `src/components/ConfigPanel.jsx` (liste de repli + valeur par défaut du `<select>`), `src/hooks/useBotConfig.js` (état initial React ET bouton "Réinitialiser par défaut", qui réécrivait encore le modèle mort dans Firestore).
- **Suivi requis** : comme pour l'Expert Pro en 2026-07-07, resélection manuelle du modèle Analyste dans Paramètres → IA si la config Firestore existante a déjà `mainModel` enregistré à l'ancienne valeur (non migrée rétroactivement).

[2026-07-09] [PRO] Feature : Ne pas stocker un scraping raté + rejet automatique des annonces hors budget → Résultat :
- **`bot.py::handle_deal_found()`** : garde-fou en tout début de fonction — si `imageUrls` est vide ET prix à 0$ (scraping manifestement raté), aucune écriture Firestore ni appel IA ; l'annonce reste absente de la base et sera retraitée comme nouvelle à la prochaine session/scan, au lieu de figer une fiche vide comme "déjà traitée".
- **Plafond de prix défensif** : vérification de `scanConfig.max_price` côté code, indépendante du filtre de prix Facebook (observé en prod : peut échouer avec `Timeout 10000ms exceeded` sur le champ de saisie, sans vérification a posteriori jusqu'ici). Réutilise le verdict `BAD_DEAL` existant ("Trop Cher") plutôt qu'un nouveau statut dédié — `status` reste `analyzed`, pas `rejected`, pour ne pas confondre "hors budget" avec un vrai rejet (mot-clé/IA).
- **`src/constants.js`** : `BAD_DEAL` déplacé de `MARKET_GROUP` vers `ARCHIVE_GROUP` — masqué de la vue par défaut via le mécanisme de filtrage existant (`matchesVerdictFilter`), toujours consultable via son propre filtre "Trop Cher" déjà présent dans le menu déroulant. Aucune nouvelle logique de statut/filtre à construire.
- S'applique uniformément à `scan_marketplace()` et `scan_specific_url()` (demande explicite de l'utilisateur : pas d'exemption pour le scan manuel d'URL).
- **Raison** : Éviter de figer des fiches vides comme "déjà traitées" (bloquant tout nouveau scraping futur), et donner un moyen de filtrer les annonces valides mais hors budget sans les traiter comme du bruit/rejet de fond.

[2026-07-09] [PRO] Fix : Crash pipeline IA si Gemini répond avec un tableau JSON au lieu d'un objet → Résultat :
- **Symptôme** : `TypeError: list indices must be integers or slices, not str` sur `result_t3["model_used"] = ...` (Tier 3 — Expert Pro), observé en prod pendant la vérification du fix images ci-dessous — bloquait toute analyse tant qu'il n'était pas corrigé.
- **`backend/analyzer.py::_call_gemini_json()`** : normalise désormais tout résultat de type liste (`[{...}]`) en `dict` (premier élément si c'est un dict, sinon `{}`) avant de le retourner — correction unique à la source plutôt qu'un patch sur le seul Tier touché ; protège aussi T1 (Portier) et T2 (Analyste), qui partagent cette méthode utilitaire et avaient la même fragilité latente.

[2026-07-09] [PRO] Fix : Logs du scraper invisibles dans le LogViewer (mauvais logger) → Résultat :
- **Cause racine** : `backend/scraping/core.py`, `parser.py` et `city_finder.py` loguaient via `logging.getLogger(__name__)` (loggers de module `scraping.core`/`scraping.parser`/`scraping.city_finder`), jamais raccordés au logger par-utilisateur `bot.{user_id}` (seul logger avec un `FirestoreHandler` attaché, alimentant la collection lue par `LogViewer.jsx`). Aucun log du scraper — y compris les diagnostics `[DIAG]` ajoutés pendant l'investigation du bug images ci-dessous — n'a jamais été visible dans l'app, faussant tout le diagnostic jusqu'ici.
- **`FacebookScraper.__init__`** : nouveau paramètre optionnel `logger` (repli sur le logger de module pour scripts autonomes/tests). Les 49 appels `logger.x()` de la classe basculés sur `self.logger.x()`.
- **`ListingParser.parse_listing_card()`/`parse_details_page()`** : paramètre `logger` optionnel ajouté et propagé depuis `core.py`.
- **`city_finder.py`** : `find_city_id_and_coords()` utilise désormais `scraper.logger` (déjà reçu en paramètre) au lieu d'un logger de module — import `logging` devenu inutile, retiré.
- **`bot.py`** : les 5 instanciations de `FacebookScraper` passent `logger=self.logger` — isolation multi-tenant préservée (un thread = un scraper = un logger, pas de logger global partagé entre utilisateurs).
- **Raison** : Sans ce correctif, impossible de vérifier depuis l'app si les correctifs scraping (voir entrée suivante) fonctionnaient réellement — la découverte de ce bug a débloqué le reste de l'investigation.

[2026-07-09] [PRO] Fix : Fiche détail Facebook dégradée → titre/prix/images manquants sur certaines annonces (SCAN_URL) → Résultat :
- **Symptôme initial** : Sur l'annonce "Guitare électrique Aria Pro 2" (Granby), seule la première miniature était récupérée ; investigation étendue ensuite au prix (0$) et aux images (0), rapportées comme "intermittentes" (certaines annonces fonctionnent).
- **`backend/scraping/core.py`** : 1ère version (`_recover_degraded_page`) basée sur l'absence de carrousel photo interactif (`ListingParser.has_photo_carousel()`) pour déclencher un reload — remplacée après une code review dédiée par un déclencheur non ambigu : "0 image extraite après parsing" (l'absence de carrousel donnait un faux positif systématique sur toute annonce à une seule photo légitime, qui n'a par nature aucun bouton "photo suivante"). Nouvelle méthode `_parse_details_with_reload_retry()`/logique dédiée dans `scan_specific_url()` : ré-extraction complète (titre/prix/localisation incluses, pas seulement les images) avec comparaison avant/après reload (on ne garde le reload que s'il apporte strictement plus d'images).
- **Code review dédiée (`/code-review` niveau high)** : a révélé que le premier correctif (`_recover_degraded_page()`) ne revérifiait jamais si le reload avait réellement réparé la page — son retour n'était que le contrôle d'URL (`_is_valid_detail_page`), donc un reload sans effet était quand même considéré comme un succès et la page toujours dégradée était parsée comme valide. 8 autres pistes (reuse, simplification, efficacité, altitude, conventions) explorées en parallèle via sous-agents ; 2 confirmées comme critiques, corrigées dans la foulée.
- **Diagnostic enrichi** (`parser.py::parse_details_page`) : quand 0 image est retenue, logue désormais le nombre total d'`<img>` trouvées dans `div[role='main']` (avant filtrage taille) et leurs dimensions — confirmé en prod (une fois le bug de logging ci-dessous corrigé) : `0 <img>` dans le DOM, ni avant ni après reload. Écarte définitivement l'hypothèse d'un filtre `>300×300px` trop strict.
- **Cause probable, non résolue** : le scraper ne s'authentifie jamais sur Facebook (aucune session/cookies persistants dans tout le backend, vérifié). Facebook semble parfois (comportement confirmé intermittent par l'utilisateur) servir une version limitée de la fiche détail aux sessions anonymes — titre/description (balises `og:*`) disponibles, prix et carrousel photo absents du DOM. Décision produit à trancher : accepter la limitation (couverte par le garde-fou "scraping raté" ci-dessus) ou implémenter une session Facebook authentifiée (risque de bannissement du compte selon les CGU FB, gestion sécurisée des secrets) — voir `TODO.md`.
- **Raison** : Plusieurs itérations ont été nécessaires car chaque diagnostic partiel masquait la cause suivante — le vrai verrou a été le bug de logging (entrée suivante), qui empêchait toute observation réelle du comportement en prod jusqu'à sa correction.

[2026-07-07] [PRO] Fix : Job `deploy-frontend` rejeté par Git (`gh-pages` non fast-forward) → Résultat :
- **Symptôme** : `git push origin gh-pages` échoue dans le job CI avec `! [rejected] gh-pages -> gh-pages (fetch first)`.
- **Cause** : Des déploiements manuels (`npm run deploy`) faits en parallèle pendant la session ont fait diverger la branche `gh-pages` de l'état attendu par le job CI, dont le `git push` normal n'est pas `--force`.
- **`.github/workflows/deploy.yml`** : Ajout de `force_orphan: true` sur l'étape `peaceiris/actions-gh-pages@v4` — republie systématiquement un commit unique et propre sur `gh-pages`, sans jamais dépendre ni tenir compte de son état précédent (adapté à une branche de build, sans historique utile à préserver).
- **Raison** : `gh-pages` ne contient que des artefacts de build ; `force_orphan` est le pattern recommandé pour ce cas précis et rend le déploiement CI totalement insensible à d'éventuels déploiements manuels intercalés.

[2026-07-07] [PRO] Feature : Mise à jour des modèles Gemini + commentaire personnalisé sur réanalyse + alerte modèle indisponible → Résultat :
- **`config.py`** : `GEMINI_MODELS["available"]` nettoyé (retrait de `gemini-1.5-flash`/`gemini-1.5-pro`, génération obsolète). Ajout de `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3.1-pro-preview`. `default_expert` (Tier 3 — contre-analyses) → `gemini-3.1-pro-preview` (choix utilisateur : préféré à `gemini-3.5-flash` malgré son statut Preview, jugement qualité > stabilité).
- **`src/components/ConfigPanel.jsx`** : Liste de repli alignée sur `config.py`.
- **Important** : La config Firestore d'un utilisateur existant n'est écrite qu'une fois à la création du compte (`ensure_initial_structure` préserve les docs existants) — le nouveau défaut ne s'applique pas rétroactivement, resélection manuelle requise dans le panneau IA.
- **`backend/analyzer.py`** : `analyze_deal()` accepte `user_comment` (injecté en priorité dans le prompt de base, ex: "Tu as identifié une PRS mais c'est une GWD") et `user_email` (pour l'alerte modèle indisponible ci-dessous).
- **`backend/bot.py`** : `analyze_single_deal(payload)` lit `payload['userComment']` ; `user_email` transmis aux 3 points d'appel de `analyze_deal`.
- **`src/services/firestoreService.js`**, **`useDealsManager.js`**, **`Dashboard.jsx`** : `userComment` relayé de bout en bout jusqu'à la commande Firestore `ANALYZE_DEAL`.
- **`src/components/DealCard.jsx`** : Nouvelle option "Avec commentaire..." dans les deux dropdowns "Ré-analyser" (carte + modale — code dupliqué existant, non refactorisé), ouvrant une modale dédiée (textarea) qui lance une réanalyse Expert avec le commentaire inclus.
- **`backend/notifications.py`** : Nouvelle fonction `notify_model_error(model_name, error, user_email)` (email + ntfy).
- **`backend/analyzer.py`** : `_call_gemini_json` détecte les erreurs "modèle introuvable" (404/not found/not supported) et déclenche l'alerte, throttlée à 1×/24h par modèle (`self._model_error_last_notified`).
- **Découverte technique** : Le SDK Python `google.generativeai` (utilisé par `analyzer.py`) émet désormais un `FutureWarning` explicite — support totalement terminé, remplacé par `google-genai`. Migration non faite ici (hors périmètre, refactor plus large), à planifier séparément.
- **Raison** : Le Portier/Analyste (Tier 1/2) restent sur leurs modèles 2.5 actuels (stables, non concernés par la demande) ; seul l'Expert Pro (contre-analyses) a été mis à jour vers le modèle jugé le plus puissant.

[2026-07-07] [PRO] Incident : Site en panne suite à l'automatisation du déploiement frontend (`TypeError onAuthStateChanged`) → Résultat :
- **Symptôme** : Après le premier push déclenchant le nouveau job `deploy-frontend`, le site entier plantait sur tous les appareils avec `TypeError: Cannot read properties of undefined (reading 'onAuthStateChanged')`.
- **Cause** : `src/services/firebase.js` lit `import.meta.env.VITE_FIREBASE_*`, injectées au build depuis `.env` (fichier local, non versionné). Le job CI `deploy-frontend` buildait sans ce fichier → `firebaseConfig` entièrement `undefined` → `initializeApp()` échoue (catché, juste loggé) → `auth` reste `undefined` → premier appel `auth.onAuthStateChanged(...)` plante.
- **Réparation immédiate** : `npm run deploy` relancé manuellement en local (avec le vrai `.env`) pour restaurer le site.
- **Correctif permanent (`.github/workflows/deploy.yml`)** : Ajout d'une étape "Create .env file" dans `deploy-frontend`, écrivant `secrets.DOT_ENV` avant `npm run build` — même mécanisme déjà utilisé par le job backend. Échec explicite (`exit 1`) si le secret est absent, plutôt qu'un build silencieusement cassé.
- **Raison** : Le job frontend ajouté la veille n'avait pas repris l'injection de secrets déjà en place côté backend — angle mort découvert seulement une fois le déploiement automatique réellement déclenché en production.

[2026-07-07] [PRO] Fix : Viewport mobile fixe (475px) au lieu de device-width → Résultat :
- **`index.html`** : `<meta name="viewport" content="width=device-width, initial-scale=1.0">` → `<meta name="viewport" content="width=475">`. Sans effet sur desktop (balise ignorée hors navigateurs mobiles).
- **Mécanisme** : Au lieu de forcer un mappage 1:1 CSS/écran (`device-width`) et de devoir cacher des éléments du `Navbar` pour tenir dans ~375px, le viewport logique est fixé à 475px — le navigateur mobile calcule alors automatiquement un zoom (`visualViewport.scale` ≈ 0.79 sur un écran de 375px) pour l'adapter à l'écran réel. Rien n'est plus caché ni coupé, juste rendu proportionnellement plus petit.
- **Vérifié** : `document.documentElement.clientWidth` = 475, `scrollWidth` = `clientWidth` partout (nav compris) → zéro débordement. Les 4 boutons du Navbar (Filtres, Aide, Paramètres, Déconnexion) restent tous visibles et cliquables. Testé via émulateur mobile (Chrome DevTools respecte la balise viewport comme un vrai appareil) — confirmation sur téléphone réel en attente.
- **Raison** : L'utilisateur a proposé cette approche après avoir constaté que le fix précédent (masquer des boutons sous 640px) réglait le débordement mais rendait l'interface "trop petite"/cramped ; fixer un viewport logique plus large et laisser le navigateur zoomer automatiquement est plus simple et n'oblige à cacher aucune fonctionnalité.

[2026-07-07] [PRO] Automatisation du déploiement frontend (GitHub Pages) → Résultat :
- **Découverte** : Le fix mobile de la veille testé sur le site en ligne (`ludoviclebart.github.io`) ne montrait aucun changement. Cause : le déploiement frontend était **manuel** (`npm run deploy`) et n'avait pas été refait depuis le **2026-05-06** — 2 mois de retard, indépendant du CI backend (qui ne déploie que le service Python via SSH).
- **Action immédiate** : `npm run deploy` exécuté manuellement pour publier la version à jour (commit `6acd749` sur `gh-pages`).
- **`.github/workflows/deploy.yml`** : Nouveau job `deploy-frontend`, indépendant et parallèle au job backend existant, déclenché sur les mêmes branches (`master`, `dev`). `npm ci` → `npm run build` → publication de `dist/` sur `gh-pages` via `peaceiris/actions-gh-pages@v4` (`GITHUB_TOKEN` intégré, pas de nouveau secret).
- **Prérequis** : Repo GitHub → Settings → Actions → General → "Workflow permissions" sur "Read and write permissions", sinon le push vers `gh-pages` échoue malgré le `permissions: contents: write` du job.
- **Raison** : Le déploiement manuel avait permis un décalage de 2 mois entre le code et le site en ligne sans que ça se remarque — source du "ça n'a pas marché" alors que le correctif mobile était déjà en place dans le code.

[2026-07-06] [PRO] Fix : Débordement horizontal en mode mobile (Dashboard) → Résultat :
- **`index.css`** : Ajout de `overflow-x: hidden` sur `html, body, #root` — filet de sécurité empêchant tout élément fautif de créer un scroll horizontal.
- **`src/components/Dashboard.jsx`** (`VerdictDropdown`) : Le conteneur du bouton avait `relative shrink-0` (largeur indéfinie) avec un enfant `w-full` — cas ambigu en CSS. Remplacé par `flex-1 sm:flex-none min-w-0` sur le conteneur, avec troncature propre (`truncate`) du libellé au lieu de dépendre du `w-full`.
- **`src/components/Dashboard.jsx`** (barre Recherche & Actions, lignes ~372-413) : Les deux groupes de boutons (Statut/Favoris, Vue/Compteur/Croix) tenaient sur une seule ligne en mobile (`flex-row justify-between`), ce qui écrasait la croix "Effacer les filtres". Passage à `flex-col sm:flex-row` pour empiler les deux groupes sous 640px.
- **`src/components/Dashboard.jsx`** et **`src/components/Navbar.jsx`** : Les deux menus déroulants en `position: absolute` (filtre Statut, menu hover du bot) n'avaient aucune limite de largeur liée au viewport — même invisibles, ils pouvaient dépasser l'écran et gonfler la largeur scrollable de la page. Ajout de `max-w-[calc(100vw-2rem)]`.
- **Vérifié** : build Vite propre, page de connexion testée en viewport mobile (375px) — `document.documentElement.scrollWidth === window.innerWidth`, aucune erreur console. Le rendu du Dashboard authentifié reste à confirmer par l'utilisateur (mur d'authentification, pas de session de test disponible).
- **Raison** : Aucune contention `overflow-x` n'existait nulle part dans l'app — la page se dimensionnait sur l'élément le plus large (carte, dropdown, menu caché) plutôt que sur la largeur de l'écran, donnant l'impression d'une page "à plat" sans conteneur englobant.

[2026-07-06] [PRO] Feature : Double appartenance "Pépite" + fix critique notifications → Résultat :
- **Bug critique corrigé (`backend/notifications.py`)** : `notify_deal()` référençait `HIGH_PRIORITY_VERDICTS` (variable commentée) et `profit` (jamais défini dans cette fonction) → `NameError` systématique à chaque Pépite trouvée. Comme `bot.py::run_scan()` n'a pas de `except` sur sa boucle des villes (seulement un `finally`), ce crash interrompait le scan des villes restantes dès qu'une Pépite était détectée. `HIGH_PRIORITY_VERDICTS` réactivé, `profit` recalculé localement.
- **`prompts.json`** (`main_analysis_prompt`) : Nouveau champ IA `also_qualifies_pepite` (booléen). L'IA le met à `true` quand le verdict principal est `FAST_FLIP`/`LUTHIER_PROJ`/`CASE_WIN`/`COLLECTION` ET que les critères Pépite sont aussi remplis (Marge > 100% et > 150$ OU Marge > 30% et modèle iconique).
- **`backend/notifications.py`** : `notify_deal()` déclenche aussi la notification (priorité haute) quand `also_qualifies_pepite` est vrai, même si le verdict principal n'est pas `PEPITE`. Sujet/corps mentionnent "(Aussi Pépite ⭐)".
- **`src/hooks/useDealsManager.js`** : `matchesVerdictFilter` fait apparaître ces annonces aussi dans le filtre "Pépites" ; `verdictCounts` les compte aussi dans ce compteur (sans dupliquer le total `ALL`).
- **`src/components/DealCard.jsx`** : Badge secondaire "💎 Aussi Pépite" affiché à côté du badge du verdict principal (carte + modale).
- **Bug annexe corrigé (`backend/notifications.py`)** : `NtfyNotifier.send()` plantait silencieusement (`UnicodeEncodeError`, catchée) sur les titres contenant émojis/accents — headers HTTP en Latin-1 uniquement. Corrigé via encodage RFC 2047 (`email.header.Header`, `maxlinelen=998` pour éviter le repliement multi-ligne invalide en HTTP), conformément à la documentation officielle ntfy.sh.
- **Raison** : Un projet de lutherie ou un case win peut être *aussi* exceptionnellement rentable ; le figer dans une seule catégorie le rendait invisible du filtre/notifications "Pépites". Le bug de notification découvert au passage minait directement l'objectif du bot (scan interrompu à chaque vraie trouvaille).

[2026-07-06] [PRO] Doc : Migration de `docs/` vers la structure Diataxis → Résultat :
- **Réorganisation** (`git mv`, historique préservé) : `docs/management/` (`JOURNAL.md`, `TODO.md`, `plans/MULTI_USER_PLAN.md`), `docs/reference/` (`ARCHITECTURE.md`, `DATA_FLOW.md`, `STATE_MODELS.md`, `UI_UX_ANALYSIS.md`), `docs/explanation/` (`PROJECT_OVERVIEW.md`, `STATS_REFLEXION.md`).
- **`CLAUDE.md`** : Étape 3 et tableau "Fichiers Clés" mis à jour vers les nouveaux chemins ; correction de la référence erronée `backend/main.py` → `main.py` (racine, vrai point d'entrée).
- **`AI_BRIEFING.md`** : Chemins de l'Étape 3 alignés sur la nouvelle arborescence.
- **`docs/management/TODO.md`** : Lien relatif vers `STATS_REFLEXION.md` corrigé (`../explanation/STATS_REFLEXION.md`).
- **Skill partagé `~/.claude/skills/document/SKILL.md`** : Généralisé — ne référence plus une convention figée (ex-MoneyBot) ; lit désormais le `CLAUDE.md`/`AGENTS.md` du projet courant pour suivre sa convention documentaire exacte, avec repli heuristique (Diataxis ou fichiers plats) si rien n'est précisé.
- **Raison** : Le skill `/document` appliquait par erreur la convention Diataxis propre à MoneyBot lors d'une session Guitar Hunter (qui était encore à plat). Aligner Guitar Hunter sur Diataxis et rendre le skill générique évite ce décalage pour tous les projets.

[2026-07-06] [PRO] Fix : Images sans rapport (véhicules, bateaux...) dans les annonces → Résultat :
- **`backend/scraping/parser.py`** : `ListingParser.parse_details_page()` accepte désormais un paramètre `fb_id` et exclut du résultat toute image entourée d'un lien `<a href="/marketplace/item/{AUTRE_ID}/...">` — ces vignettes appartiennent au bloc "Suggestions" que Facebook affiche systématiquement sous la description de l'annonce, pas aux vraies photos du produit.
- **`backend/scraping/core.py`** : Ajout de `_is_valid_detail_page()` (garde-fou détectant une redirection vers `/login`, un captcha, ou une URL ne correspondant plus à l'annonce ciblée) utilisé dans `scan_marketplace()` et `scan_specific_url()` avant l'extraction des détails ; log `debug` temporaire de l'URL de la fiche détail chargée (`[DIAG]`) conservé pour un diagnostic futur.
- **`backend/scraping/test_core.py`** (nouveau) : 4 tests unitaires couvrant `_is_valid_detail_page` (page valide, redirection feed, redirection login, ID différent).
- **Diagnostic réel** : reproduit sur une annonce publique (`.../marketplace/item/1680540959879684/`) — 19 images extraites avant correctif (16 étaient des suggestions d'autres annonces : voiture, bateau, meubles...) contre 3 après correctif (toutes les vraies photos du produit).
- **Raison** : Le filtre initial se basait uniquement sur la taille de l'image (>300×300px) et le domaine CDN (`scontent`), ce qui capturait aussi les vignettes du bloc "Suggestions" — visible surtout sur les annonces ayant peu de vraies photos (le plafond de collecte n'étant alors pas atteint par les vraies photos seules).

[2026-07-05] [PRO] Feature : Partage d'annonce sans authentification → Résultat :
- **`firebase/firestore.rules`** : Ajout d'une règle de lecture publique sur la collection `shared_deals/{dealId}`. Écriture réservée aux utilisateurs authentifiés.
- **`firebase.json`** : Correction d'un espace parasite dans le chemin des règles Firestore (empêchait `firebase deploy --only firestore:rules`).
- **`src/services/firestoreService.js`** : Ajout de `createSharedDeal(deal)` (snapshot public dans `shared_deals/`) et `getSharedDeal(dealId)` (lecture sans auth).
- **`src/components/DealCard.jsx`** : `handleShare` écrit d'abord le snapshot dans Firestore, puis génère un lien `?shareId={deal.id}` au lieu de `?dealId=`.
- **`src/components/SharedDealPage.jsx`** : Nouveau composant public affichant titre, prix, localisation, images, scores IA, analyse et lien FB — sans login requis.
- **`src/App.jsx`** : Détection de `?shareId=` avant le mur d'auth → rendu de `SharedDealPage` directement.
- **Raison** : Un destinataire qui reçoit un lien partagé ne doit pas être forcé à créer un compte pour consulter l'annonce.

[2026-05-06] [PRO] Refonte Aide UX & Robustesse Internationale → Résultat :
- **`src/components/HelpOverlay.jsx`** : Refonte totale du guide de prise en main. Transition vers un guide technique en 4 étapes (Cibles, Vigilance, Lancement, Analyse) avec explications précises sur le "Rayon 0" (Recherche Stricte) et la fréquence de scan. Isolation des réglages IA dans une section "Expertise Avancée".
- **`src/components/ConfigPanel.jsx`** : Ajout d'un bouton **"Lancer le Scan"** direct pour déclencher la recherche après configuration. Simplification radicale de l'ajout de villes : suppression du formulaire secondaire, l'ajout se fait désormais directement via le bouton "+" du champ de recherche principal.
- **`backend/bot.py`** : Correction d'une `NameError` critique (`city_coords`) lors de l'ajout automatique de ville.
- **`backend/scraping/city_finder.py`** : Hardening de la recherche de villes Facebook. Support des versions internationales (Lieu/Location/Lugar), détection des alias d'URL (non-numériques), et nettoyage forcé du champ de recherche (`Ctrl+A -> Backspace`).
- **Raison** : Améliorer l'onboarding utilisateur, clarifier les paramètres vitaux de scan et assurer que le bot peut s'exporter sur n'importe quel marché (Bordeaux, Paris, etc.) sans friction technique.


[2026-05-06] [PRO] Robustesse Auth & Scraping: Fix duplication et sécurisation sessions → Résultat :
- **`src/hooks/useAuth.js`** : Centralisation de l'onboarding via `ensureUserDoc` (DRY). Propagation des erreurs Firestore vers l'UI dans `onAuthStateChanged` (Status Warning).
- **`backend/scraping/core.py`** : Sécurisation du `finally` (fix `page` non-définie) et clarification du périmètre de `get_city_id_and_coords` (géocodage délégué à Nominatim).
- **Raison** : Éliminer la dette technique de duplication et améliorer le feedback utilisateur en cas d'erreur de permissions Firestore.

[2026-05-06] [PRO] Correctifs Visibilité UI & Géo-localisation Paris → Résultat :
- **`src/components/Navbar.jsx`** : Amélioration de la visibilité du bouton d'aide (ajout du label "Aide" sur Desktop et augmentation du contraste).
- **`src/components/Dashboard.jsx`** : Implémentation d'un bandeau d'erreur global et correction d'une `ReferenceError` (contexte mal déstructuré).
- **`backend/bot.py` & `core.py`** : Fiabilisation de l'ajout de ville. Priorité aux coordonnées extraites de Facebook et élargissement de la recherche Nominatim pour supporter **n'importe quelle ville dans le monde** (suppression des restrictions régionales). Implémentation du scraping automatisé de l'ID de ville Facebook via le sélecteur de lieu.
- **`src/components/MapView.jsx`** : Correction de l'interaction avec les InfoWindows (suppression du `mouseout` agressif) et restauration/styling du bouton de fermeture.
- **`src/components/ConfigPanel.jsx`** : Ajout de consignes textuelles pour guider l'utilisateur dans l'ajout de nouvelles villes.
- **Raison** : Résoudre les points de friction utilisateur et assurer la stabilité de l'interface après l'ajout des nouveaux mécanismes de feedback.

[2026-05-05] [FLASH] Intégration de la Documentation Utilisateur → Résultat :
- **`src/components/HelpOverlay.jsx`** : Création d'un guide interactif premium détaillant le Radar IA (scores Gemini), les Verdicts (badges), les Commandes (Refresh/Cleanup) et les Notifications (Email/Ntfy).
- **`src/components/Navbar.jsx`** : Ajout du bouton d'aide (`HelpCircle`) à côté des paramètres.
- **`src/components/Dashboard.jsx`** : Gestion de l'état d'affichage de l'aide et rendu de l'overlay.
- **Raison** : Améliorer l'autonomie de l'utilisateur final et clarifier les fonctionnalités de l'IA et du système d'alertes.

[2026-05-05] [PRO] Audit multi-tenant & correctifs onboarding → Résultat :
- **`src/hooks/useAuth.js`** : Initialisation automatique du document utilisateur Firestore lors du `signUp` ET du `onAuthStateChanged` (session persistante), garantissant que le backend découvre tout utilisateur actif même s'il existait déjà.
- **`backend/bot.py`** : Assouplissement du géocodage Nominatim (suppression de la restriction stricte Canada) permettant l'ajout de villes internationales comme Paris.
- **`main.py`** : 
    - **Watchdog** : Correction d'un bug critique où le `firestore_handler` n'était pas recréé lors d'un redémarrage de thread, coupant les logs.
    - **Performance** : Passage de la commande `ADD_CITY` en asynchrone pour ne plus geler le bot pendant le scraping/géocodage.
    - **Hygiène** : Implémentation du nettoyage automatique des bots pour les utilisateurs supprimés de Firestore.
- **`src/components/Navbar.jsx`** : Ajout d'un tooltip sur le point de statut "Auth" pour afficher les messages d'erreur (ex: "Dossier Python introuvable").
- **`src/components/LogViewer.jsx`** : Correction de l'envoi de l'UID lors de la suppression des logs.

[2026-05-05] [PRO] Onboarding Dynamique & Isolation du Logging → Résultat :
- **`main.py`** : Implémentation de `discover_users` (scan cyclique toutes les 30s) et `start_user_bot`. Transition d'une liste statique vers un mode multi-tenant réactif.
- **`backend/logging_config.py`** : Isolation du logging par utilisateur. Les logs de chaque bot sont désormais dirigés vers leur propre collection Firestore (`bot.XXXX`) sans interférer avec le logger racine ou les autres utilisateurs.
- **Watchdog** : Surveillance active des threads par UID. Redémarrage automatique en cas de crash.
- **Raison** : Permettre l'ajout de nouveaux utilisateurs à chaud sans redémarrage serveur et garantir l'étanchéité des logs en production.

[2026-05-05] [PRO] Restauration des fonctionnalités d'authentification Frontend → Résultat :
- **`src/hooks/useAuth.js`** : Réimplémentation de `signUp` (createUserWithEmailAndPassword) et `resetPassword` (sendPasswordResetEmail).
- **`src/components/LoginPage.jsx`** : Refonte de l'interface pour inclure les modes Inscription et Réinitialisation de mot de passe, avec gestion des messages de succès et d'erreur.
- **Raison** : Correction de la disparition des boutons suite à une sécurisation trop stricte (Task 1.2) et perte d'accès utilisateur.

[2026-04-10] [PRO] Ajout des notifications email par utilisateur (SMTP Gmail) → Résultat :
- Task 1.4 : `firestoreService.js:migrateOldDataToNewUser` → Email admin → `VITE_ADMIN_EMAIL` env var, flag `migrationDone`, try/catch granulaire par étape (config ✅ / villes ✅ / annonces ✅).

**PHASE 2 — Robustesse Backend [6 Tasks]**
- Task 2.1 : `main.py` → `try/except` autour de `GuitarHunterBot()` pour chaque user. Échecs isolés par user sans crash global.
- Task 2.2 : `main.py` → Boucle watchdog `while True` (30s interval) redémarre threads morts. Capteur de crashes `t.is_alive()`.
- Task 2.3 : `bot.py` + `main.py` → `threading.Semaphore(MAX_CONCURRENT_BROWSERS)` partagé. Chaque `FacebookScraper` acquis/libéré. Limite navigateurs simultanés.
- Task 2.4 : `main.py` → `threading.Lock()` sur `in_flight_command_ids`, `.discard()` au lieu de `.remove()` pour éviter `KeyError`.
- Task 2.5 : `bot.py` → `session_processed_ids` → `@property` sur `threading.local()`. Isolé par thread, `.clear()` au lieu de `= set()`.
- Task 2.6 : `bot.py` → Logger par user `logging.getLogger(f"bot.{user_id[:8]}")`, tous les `logger.` remplacés par `self.logger.`.

**Code Review — 3 Rondes validées**
- Ronde 1 (Exactitude) : 1 bug Firestore rules trouvé et corrigé (document parent).
- Ronde 2 (Cohérence) : Chaîne useAuth → AuthContext → LoginPage OK. Sémaphore propagé correctement.
- Ronde 3 (Edge Cases) : Acceptables. Watchdog sans backoff reste backlog.

**Variables d'Environnement à ajouter**
```
VITE_ADMIN_EMAIL=ton@email.com
MAX_CONCURRENT_BROWSERS=3
```

[2026-03-21] [PRO] Action : Raffinement Login & Data Migration V2 → Résultat : (1) **Frontend** : Ajout du mode Inscription (`signUp`) dans `LoginPage.jsx` avec autocomplétion pour gestionnaires de mots de passe. (2) **Migration** : Implémentation de `migrateOldDataToNewUser` dans `firestoreService.js` pour copier automatiquement les données de l'ID historique vers le compte `ludovic.lebart@gmail.com` lors de sa première connexion (si profil vide). (3) **Sécurité** : Isolation stricte garantie par `getRefs(userId)`.

[2026-03-21] [PRO] Action : Implémentation du système Multi-Utilisateurs → Résultat : (1) **Backend** : `config.py` supporte `USER_IDS_TARGET` (liste d'UIDs séparés par virgule, rétrocompatible `USER_ID_TARGET`). `bot.py` reçoit `app_id` et `user_id` comme paramètres explicites. `main.py` lance un thread `main_loop` indépendant par utilisateur. (2) **Frontend** : `useAuth.js` migré vers Firebase Auth email/password. `AuthContext.jsx` et `LoginPage.jsx` créés. `firestoreService.js` dynamisé via `getRefs(userId)`. Tous les hooks propagent `user.uid`. `App.jsx` affiche `LoginPage` si non connecté. (3) Build Vite validé (exit code 0).


[2026-03-05] [PRO] Action : Fiabilisation des comparaisons de prix et anti-spam Ntfy → Résultat : (1) Création d'une fonction `_normalize_price` dans `bot.py` pour comparer sereinement les prix (ex: "150$" vs " 150.0") et éviter les fausses "mises à jour". (2) Implémentation d'un filtre dans `notifications.py` (`notify_deal`) pour ne déclencher une alerte de "Baisse de Prix" que si la baisse est de plus de 5% ou de plus de 50$.

[2026-03-05] [PRO] Action : Détection et intégration visuelle des Baisses de Prix → Résultat : (1) Backend (`bot.py`, `repository.py`) mis à jour pour écraser le prix Firestore et conserver l'ancien prix (`original_price`) lors d'une baisse. (2) Les annonces subissant une baisse repassent désormais au travers du pipeline de l'IA avec le nouveau prix. (3) Frontend (`DealCard.jsx`) mis à jour pour afficher un badge vert vif « Baisse -XX$ » si le prix a chuté, visible sur la miniature et dans la modale IA.

[2026-03-05] [PRO] Action : Implémentation complète de la sélection 3-Tiers et correction Gemini 2.5 Pro → Résultat : (1) Correction du bug où l'Expert Pro était écrasé vers Flash à cause d'une omission dans l'UI. (2) Ajout du modèle `gemini-2.5-pro` à la liste des modèles disponibles dans l'interface. (3) Ajout d'un 3ème menu déroulant dans le `ConfigPanel` pour configurer le modèle de l'Analyste (Tier 2 - `mainModel`) de manière indépendante du Portier (Tier 1) et de l'Expert (Tier 3). (4) Mise à jour du hook `useBotConfig.js` pour gérer les 3 modèles avec les bonnes valeurs par défaut du backend.

[2026-02-28] [PRO] Action : Implémentation de la redirection par `dealId` et amélioration du partage → Résultat : (1) Le composant `Dashboard.jsx` lit désormais le paramètre `dealId` de l'URL au chargement, sélectionne l'annonce correspondante et force l'affichage en mode "Carte" (`MapView`). (2) Le bouton de partage dans `DealCard.jsx` génère un lien vers l'application avec le `dealId` de l'annonce, permettant un partage direct et une ouverture de la modale de détail. (3) La logique de sélection de l'annonce depuis l'URL a été déplacée de `useDealsManager.js` vers `Dashboard.jsx` pour une meilleure gestion de l'état de l'interface.


[2024-07-30] [PRO] Action : Implémentation d'une stratégie de rotation d'IP (Proxies) → Résultat : (1) Ajout d'une liste `PROXIES` dans `config.py` pour centraliser la configuration. (2) Modification de `FacebookScraper` (`backend/scraping/core.py`) pour sélectionner aléatoirement un proxy de la liste à chaque instanciation d'un navigateur Playwright. (3) La rotation est effective car le bot instancie un scraper temporaire pour chaque tâche, garantissant une nouvelle IP pour chaque scan de ville ou action manuelle.

[2024-07-30] [FLASH] Action : Analyse du diagnostic de détection du scraper par Facebook → Résultat : Le diagnostic est validé. Le projet a déjà implémenté la plupart des contre-mesures (session persistante, randomisation User-Agent/Viewport, jitter, intégration du téléchargement d'images, flags Playwright furtifs) documentées dans les Sessions 35 et 29. Une stratégie de rotation d'IP reste une amélioration potentielle.

[2026-02-27] [FLASH] Action : Optimisation Mobile du LogViewer → Résultat : Forçage de l'affichage en plein écran (`inset-0`, `rounded-none`) sur les petits écrans pour éviter la perte de visibilité de la console. Le comportement flottant est conservé pour les écrans larges (`sm:`).

[2026-02-27] [FLASH] Action : Correction de la lisibilité de la console (LogViewer) et du ConfigPanel → Résultat : Passage d'un fond semi-transparent (`bg-slate-900/95`) à un fond totalement opaque (`bg-slate-950`). Suppression du `backdrop-blur` qui causait des interférences visuelles lors de la superposition sur des images ou des cartes.

[2026-02-27] [FLASH] Action : Correction du blocage du scroll sur mobile → Résultat : Suppression des contraintes `min-height: 100%` et `overflow-x: hidden` sur les éléments racines dans `index.css`, `App.jsx` et `Dashboard.jsx`. Le défilement vertical natif et le geste de rafraîchissement ("pull-to-refresh") sont désormais fonctionnels sur mobile.

[2026-02-26] [FLASH] Action : Restauration du Bouton de Partage → Résultat : Ajout de l'icône `Share2` et de la fonction `handleShare` dans `DealCard.jsx`. Le bouton supporte désormais le partage natif (API `navigator.share`) et la copie automatique dans le presse-papier avec confirmation visuelle ("Lien copié !") en cas de fallback.

[2026-02-26] [FLASH] Action : Correction Critique du Scroll → Résultat : Restauration du défilement vertical en supprimant `overflow: hidden` de `index.css`. Ajout de `overflow-x-hidden` sur le `body` et le `Dashboard` pour empêcher les décalages horizontaux tout en conservant une expérience fluide sur PC et Mobile.

[2026-02-26] [FLASH] Action : Extraction de la Date de Mise en Ligne → Résultat : Implémentation du sélecteur `abbr[aria-label]` dans `ListingParser` pour capturer l'âge de l'annonce. Le champ `published_at_raw` est désormais propagé dans `listing_data` et stocké dans Firestore.

[2026-02-26] [FLASH] Action : Raffinement des Prompts pour les Lots (Bundles) → Résultat : Mise à jour de `prompts.json` (directives Portier et Prompt Principal). L'IA autorise désormais explicitement les instruments vendus avec des accessoires mineurs (micros, câbles, supports). Le verdict `REJECTED_ITEM` est désormais restreint aux annonces vendant *uniquement* des accessoires non autorisés.

[2026-02-26] [PRO] Action : Finalisation du Dashboard (Radar & Marques) & Ajout de Champs IA → Résultat : (1) Intégration de la librairie `recharts` dans le frontend. (2) Remplacement des placeholders dans `MockupStatsView.jsx` par un **Radar Chart** affichant le profil moyen des 5 scores Gemini et un **Bar Chart** pour la distribution du Top 5 des marques. Les données sont calculées dynamiquement depuis l'inventaire filtré. (3) Backend : Ajout des clés `brand`, `model_name`, `production_year`, et `country_of_origin` au dictionnaire JSON attendu dans `main_analysis_prompt` (`prompts.json`), enrichissant considérablement la granularité future de l'analyse IA.

[2026-02-26] [PRO] Action : Audit approfondi des Statistiques et du Tunnel de Conversion → Résultat : Vérification du code de `MockupStatsView.jsx`. (1) Le **Tunnel de Conversion** à 3 niveaux est déjà fonctionnel et alimenté par les données réelles de Firestore. (2) Les **KPIs Financiers** (Marge latente, ROI, Score moyen) sont calculés dynamiquement. (3) Identification des manques : le Radar Chart (nécessite Recharts) et la distribution par Marque (nécessite extraction `brand` backend) restent à implémenter. Mise à jour de la `TODO.md` pour refléter cet état d'avancement supérieur aux attentes.

[2026-02-26] [PRO] Action : Implémentation d'une Protection Anti-Botting (Stealth) Globale → Résultat : Correction du blocage par Facebook lors du rescraping massif. (1) **Randomisation** : Injection de User-Agents tournants et de Viewports aléatoires dans `FacebookScraper` (`core.py`). (2) **Furtivité Playwright** : Ajout de flags spécifiques (`AutomationControlled`, `infobars`) pour masquer l'automatisation. (3) **Détection de Blocage** : Interruption propre en cas de redirection vers `/login` ou CAPTCHA. (4) **Rotation & Jitter** : Le script `migrate_images.py` redémarre maintenant le navigateur toutes les 15 requêtes et utilise des délais aléatoires (jitter) pour simuler un comportement humain. Test `--dry-run` validé avec succès.

[2026-02-26] [PRO] Action : Raffinement des Interactions Cartographiques (Tooltip & Pins) → Résultat : Ajout d'InfoWindows enrichies au survol (PC) et au clic (Mobile) sur les marqueurs Google Maps. Les bulles incluent désormais une miniature, le titre, le score IA et la valeur estimée dans un design Dark Theme. Le marqueur sélectionné est désormais visuellement identifié par une taille supérieure.

[2026-02-26] [PRO] Action : Optimisation de l'Expérience Mobile (Overlay & Navigation) → Résultat : (1) Correction de l'affichage de l'annonce sur mobile : elle s'affiche désormais en "Full-Screen Overlay" par-dessus la carte au lieu de la compresser, garantissant une lisibilité maximale. (2) Inversion de la logique de clic sur mobile : le premier clic sur un pin ouvre l'InfoWindow, le clic sur la bulle ouvre l'annonce complète.

[2026-02-26] [PRO] Action : Amélioration UX de la DealCard et de la Modale IA → Résultat : (1) Le bouton de ré-analyse est devenu un menu déroulant dynamique offrant les options "Scan Standard" et "Luthier Expert", géré par `useState` pour supporter le survol (PC) et le clic (Mobile). (2) Factorisation de la barre d'actions complète (Favori, Scan, Rejeter, Suppression, Facebook) pour l'injecter directement dans l'en-tête de la Modale d'Expertise IA, offrant une parité fonctionnelle totale entre les vues.

[2026-02-26] [PRO] Action : Correction UI Mobile du Menu des Verdicts (Mockup V2) → Résultat : Le composant `VerdictDropdown` s'écrasait et coupait le texte sélectionné sur les petits écrans. Application de `whitespace-nowrap` sur le bouton principal et définition d'une largeur fixe (`w-56`) avec `truncate` sur les options du menu déroulant dans `MockupDashboard.jsx` pour garantir un affichage propre sur une seule ligne.

[2026-02-26] [PRO] Action : Correction du Responsive Design et Résolution de la "Double Navbar" Mobile (Mockup V2) → Résultat : Le rendu mobile souffrait d'un overflow horizontal causé par la Navbar V1 qui restait active en arrière-plan avec une largeur minimale incompressible. (1) Désactivation conditionnelle de la Navbar V1 dans `App.jsx` lorsque le Mockup V2 est ouvert, éliminant la "bande blanche" sur mobile. (2) Refonte du container de recherche/filtres dans `MockupDashboard` en utilisant un layout `grid-cols-1 md:flex` pour forcer un empilement vertical propre des éléments (Recherche, Favoris, Vues, Bouton X) sur petits écrans. (3) Application de `whitespace-nowrap` sur l'indicateur de statut du bot dans `MockupNavbar` pour empêcher le texte de se casser sur deux lignes, et ajustement global des marges internes (padding) pour maximiser l'espace utile sur smartphone.

[2026-02-26] [PRO] Action : Résolution de l'erreur Greenlet (Cannot switch to a different thread) sur le backend → Résultat : L'implémentation de tâches de scraping en arrière-plan (ex: REFRESH, SCAN_URL) générait des crashs asynchrones car l'instance Playwright globale (`self.scraper`) du thread principal ne pouvait pas être partagée avec les threads secondaires. La solution a été de retirer le contexte Playwright global dans le bot (`bot.py`) et la boucle principale (`main.py`). Désormais, chaque action appelant le Scraper (comme `run_scan`, `scan_specific_url` ou `cleanup_sold_listings`) instancie son propre scraper temporaire (`temp_scraper = FacebookScraper()`) localement et le libère `finally: temp_scraper.close_session()`. Cette architecture garantit l'isolation absolue des navigateurs Chromium par thread.

[2026-02-25] [PRO] Action : Raffinement final de l'UI V2 (Modale IA, Barre de Filtres, Map Centering, Raccourci Favoris) → Résultat : (1) Restauration de la section "Analyse Détaillée" dans la Modale IA : Le Markdown complet (`aiAnalysis.analysis`) s'affiche maintenant correctement avec saut de ligne grâce à `whitespace-pre-wrap` au lieu de l'ancien `aiAnalysis.reasoning` tronqué. (2) Rapatriement du statut "Favoris" dans la V2 avec un double accès : option intégrée au sommet de `VerdictDropdown` + création d'un bouton fixe "Cœur" adjacent pour un accès ultra-rapide en un clic. (3) Dynamisme de la Carte : Intégration de la logique `fitBounds` dans `MapView.jsx` pour que la Google Map se centre et zoome automatiquement sur les annonces visibles selon les filtres actifs, avec une sécurité anti-zoom extrême pour les annonces solitaires.

[2026-02-25] [PRO] Action : Finalisation de l'UI/UX du Mockup V2 (Responsive, Modale IA, Barre de Filtres) → Résultat : (1) Modale IA Plein Écran : Le bloc d'expertise IA collapsible a été remplacé par une modale "glassmorphism" (`z-[100]`) permettant une lecture très confortable sur Desktop sans déformer la DealCard. (2) Nettoyage Dashboard : Le compteur de résultats et le bouton "Effacer tous les filtres" (maintenant stylisé en bouton carré dynamique rouge) ont été consolidés à l'intérieur de la barre de filtres principale. (3) Hauteur des cartes : Réduction de la hauteur des images de `400px` à `280px` pour afficher la carte entière sur les écrans de PC portables sans scroller. (4) Correction Navbar Mobile : Résolution du débordement horizontal (`overflow-x-hidden`) en contraignant la largeur de la toolbar.
[2026-02-25] [FLASH] Action : Intégration de la galerie ImageGallery et données réelles dans le Mockup V2 → Résultat : Remplacement du défilement horizontal basique par le composant robuste ImageGallery. Support natif du plein écran, des flèches de navigation et de l'affichage vertical intégral (object-contain). Extraction de véritables URLs Facebook depuis Firestore pour un rendu réaliste.

[2026-02-25] [PRO] Action : Finalisation Responsive et Logique Taxonomique Mockup V2 → Résultat : (1) Correction Mobile : Le status interactif du bot reste toujours visible sur `MockupNavbar` (points info annexes masqués), et ajout d'un bouton "Fermer" sur les DealCards en vue carte sur petit écran pour éviter les blocages. (2) Comptage Taxonomie : Mise à jour de `buildDealCounts` pour que chaque item `FAKE_DEALS` itère sur son chemin entier de `classification` (`ex: electrique.ampli.combo`) pour remplir parfaitement l'arbre à 4 niveaux. (3) UX : Retrait des choix multiples "Toutes" redondants dans les sous-niveaux de filtres. (4) Alignement du Dropdown de filtres sur les "Nouveaux Verdicts" V2 via `ALL_FILTERS_CONFIG`.

[2026-02-25] [PRO] Action : Raffinement UX approfondi du Mockup V2 → Résultat : (1) Tiroir de filtres : Transformation de `MockupFilterDrawer` en un accordéon imbriqué en cascade à 4 niveaux avec badges dynamiques de comptage d'annonces. (2) Barre d'actions (`MockupDashboard`) : Remplacement du défilement horizontal des verdicts par un composant `VerdictDropdown` compact. (3) Recherche : Ajout du filtrage interactif (text/location) avec bouton de réinitialisation interne. (4) Carte : Implémentation du mode "Split-Screen" (`MockupMapView`) et du bouton toggle Liste/Carte. (5) Contrôles UI (`MockupNavbar`) : Intégration de la véritable logique `BotControls` interactive au survol, et ajout des boutons d'actions manuelles (Vérification et Rescan) à la racine de la Toolbar. Le prototype Mockup V2 est achevé et valide toutes les recommandations heuristiques UX de l'analyse précédente.

[2026-02-25] [PRO] Action : Implémentation du filtre Drawer en cascade à 4 niveaux → Résultat : `MockupFilterDrawer.jsx` entièrement réécrit avec un arbre de taxonomie `TAXONOMY_TREE` à 4 niveaux de profondeur. Comportement : tous les groupes sont repliés par défaut (accordéon). Chaque niveau s'affiche et s'ouvre automatiquement dès qu'un choix est fait au niveau parent (Niveau 1 : Type d'instrument, Niveau 2 : Sous-catégorie contextuelle, Niveau 3 : Modèle/Type, Niveau 4 : Marque/Détail). La sélection d'un niveau parent réinitialise automatiquement tous les niveaux enfants. Le titre du groupe indique le contexte (ex : "Sous-catégorie · Électrique"). Les clés de filtres dans `MockupDashboard.jsx` ont été mises à jour (`level1/level2/level3/level4`). "Verdict IA" retiré du Drawer (couvert par les onglets rapides en haut de la grille).


[2026-02-25] [PRO] Action : Création du Mockup Complet UI V2 → Résultat : Prototype interactif Dark Mode complet accessible via le bouton "Mockup V2" dans la Navbar.
 Composants créés : `MockupDealCard.jsx` (image full-width, marge affichée, bloc IA collapsible, titres normalisés, hit-zones 44px), `MockupNavbar.jsx` (statuts système compacts, boutons Filtres et Paramètres, bouton quitter), `MockupFilterDrawer.jsx` (volet latéral coulissant avec 4 niveaux de filtres dynamiques et taxonomie en cascade — les sous-catégories s'adaptent automatiquement au type sélectionné, sans bouton Appliquer), `MockupDashboard.jsx` (assemblage complet : 8 fausses annonces, filtrage live via `useMemo`, onglets verdicts rapides, 3 sections Radar/Marché/Archives, bouton "Effacer les filtres"). Intégration du vrai `ConfigPanel` ouvert via le bouton ⚙️. Le `App.jsx` bascule entre l'interface réelle et le Mockup V2 via un `useState` sans modifier les données ni les hooks Firestore.

[2026-02-25] [PRO] Action : Extension de l'analyse UI/UX (Deep Heuristic Evaluation) → Résultat : Analyse des détails qualitatifs au-delà du simple layout.

[2026-02-25] [PRO] Action : Révision de l'analyse UI/UX suite aux retours utilisateurs → Résultat : Mise à jour de `docs/UI_UX_ANALYSIS.md` pour se concentrer sur les défauts structurels critiques : 1) Démantèlement du panneau latéral (Aside) qui gaspille 20% de la largeur. 2) Refonte des filtres horizontaux qui débordent en un "Drawer" latéral. 3) Correction de la DealCard Mobile pour forcer l'image en pleine largeur (`w-full`). 4) Nettoyage des boutons d'action (remplacement des textes par des icônes comme FB). Le `TODO.md` a été réécrit avec ces nouvelles priorités absolues.

[2026-02-25] [PRO] Action : Analyse approfondie de l'UI/UX et ajout de `docs/UI_UX_ANALYSIS.md` → Résultat : Validation de la structure d'interface actuelle (Dashboard SaaS, code couleur sémantique). Définition de 4 axes prioritaires documentés dans le TODO pour un design Premium : Dark Mode, Micro-interactions visuelles, Refonte par "Tiroir" de la taxonomie des filtres, Intégration d'un panneau de statistiques.

[2026-02-25] [PRO] Action : Implémentation du stockage pérenne des images via Firebase Storage → Résultat : Les URLs CDN de Facebook expirent après 1-3 jours, rendant les images des annonces archivées inaccessibles. (Action 1) Init du bucket Storage dans `backend/database.py` : passage du `storageBucket` à `firebase_admin.initialize_app()` et exposition de `self.bucket`. (Action 2) Ajout de `FIREBASE_STORAGE_BUCKET` et `IMAGE_RETENTION_REJECTED_DAYS` (30j) dans `config.py`. (Action 3) Le `FirestoreRepository` passe le bucket aux méthodes `upload_images_to_storage()` (upload + URL publique) et `purge_rejected_images()` (purge lifecycle). (Action 4) Le bot (`bot.py`) uploade systematiquement les images avant de sauvegarder chaque annonce et expose `purge_rejected_images()` pour le scheduler. (Action 5) Le frontend (`DealCard.jsx`) utilise `storageImageUrls || imageUrls` comme fallback. (Action 6) Création du script one-shot `backend/scripts/migrate_images.py` pour migrer les annonces existantes (test validité URL, re-scraping si expirée, upload Storage). (Action 7) Branchement de la purge lifecycle au `TaskScheduler` (`services.py`) via `purge_func=` — job hebdomadaire automatique. (Action 8) Correction du dry-run du script de migration : Playwright ne se lançait pas inutilement, seulement un HTTP HEAD pour tester la validité des URLs. (Action 9) Ajout de `run.bat` et du workflow `.agent/workflows/run-venv.md` pour forcer l'usage du venv.

[2026-02-24] [FLASH] Action : Ajout de la taxonomie aux annonces rejetées par le Portier → Résultat : Les annonces immédiatement rejetées (BAD_DEAL, REJECTED_ITEM) ne possédaient pas de champ `classification`, empêchant leur filtrage par type dans l'UI. (Action 1) Modification de `gatekeeper_verbosity_instruction` dans `prompts.json` pour exiger la classification dans le JSON de sortie du Portier (Tier 1). (Action 2) Mise à jour de `backend/analyzer.py` pour extraire cette classification et l'inclure dans le payload de retour lors du coupe-circuit. Ce correctif affine l'expérience utilisateur lors de l'exploration des archives rejetées.

[2026-02-24] [PRO] Action : Simplification de la taxonomie des accessoires et durcissement des rejets → Résultat : L'IA laissait passer les pédales et les supports de guitare en les amalgamant sous la clé racine `accessoire_etui`. (Action 1) Renommage de la clé racine de la taxonomie `accessoire_etui` en `etui_housse` et suppression du niveau imbriqué `protection` pour aplatir la structure. (Action 2) Modification stricte du prompt du Portier (Tier 1) et du prompt principal pour ordonner le rejet immédiat (`REJECTED_ITEM`) de tout accessoire n'étant pas un étui rigide ou une housse (ex: pédales, supports, ficelles, micros).

[2026-02-24] [PRO] Action : Correction de la profondeur de filtrage et de la justification des rejets (Frontend) → Résultat : (Bug 1) Le filtre de taxonomie (FilterBar) n'affichait que 3 niveaux, empêchant la sélection des feuilles (ex: `Parlor`) suite à l'ajout des catégories racines (`guitare`, `ampli`, etc.). Ajout d'un 4ème niveau `level4Filter` dans `useDealsManager.js` et `FilterBar.jsx` pour restaurer la granularité complète. (Bug 2) Les annonces rejetées par l'Intelligence Artificielle restaient affichées avec le statut trompeur "Analyse en cours...". Modification de `DealCard.jsx` pour afficher la justification réelle (`deal.aiAnalysis.reasoning`) ou une phrase de rejet par défaut.



[2026-02-24] [PRO] Action : Création d'un point central de mise à jour `set_status` (avec `threading.Lock()`) activé → Résultat : Résolution du bug "En attente" pendant le scan. Le statut `botStatus` repassait à `idle` prématurément quand des threads parallèles (comme le nettoyage en arrière-plan) se terminaient pendant qu'un scan principal tournait. Création d'un point central de mise à jour `set_status` dans `GuitarHunterBot` avec `threading.Lock()` et un suivi des tâches actives par nom (`_active_tasks`). Le statut `idle` n'est confirmé sur Firestore que si l'ensemble des processus sont terminés, avec préservation de la priorité du statut `scanning` sur `cleaning` pour l'interface UI.

[2026-02-24] [PRO] Action : Ajout d'un sondage Firestore pendant les pauses et réécriture de `delete_all_logs` → Résultat : Réparation de deux bugs. (Bug 1) Réveil du bot en pause : La boucle d'attente dans `main.py` ne sondait pas Firestore, rendant le bot sourd à toute commande (REFRESH, SCAN_URL, etc.) sauf START_BOT. Correction : ajout d'un sondage Firestore toutes les 5s avec `bot.sync_and_apply_config()`. Toute commande actionnable interrompt maintenant la pause et est traitée immédiatement après le réveil. (Bug 2) Suppression des logs : Réécriture de `delete_all_logs` dans `repository.py` pour utiliser `list()` afin de forcer la consommation du stream Firestore avant chaque batch, ajout d'un garde-fou `max_iterations` et de logs de diagnostic améliorés.

[2026-02-24] [FLASH] Action : Identification d'un bug de réveil du bot → Résultat : Ajout au `TODO.md` : le bot en pause (`paused`) ignore la commande `REFRESH` (Rescan All) mais réagit au `SCAN_URL`.

[2026-02-24] [PRO] Session 27 : Robustesse de la détection d'indisponibilité du scraper (`check_listing_availability`). Passage d'une vérification textuelle stricte à une analyse Regex (insensible à la casse, mots entiers `\b`) incluant le français et l'anglais ("vendu", "sold", "expired"). Ajout de l'inspection des attributs ARIA et vérification stricte de la visibilité CSS (`display: none`, `opacity: 0`) vis `window.getComputedStyle` pour éliminer les faux positifs (éléments cachés ou mots partiels comme "revendu").

[2026-02-24] [FLASH] Session 26 (Bug Report) : Identification d'un problème de pérennité des images. Les URLs Facebook CDN expirent (paramètre `oe` dans l'URL). Les annonces valides perdent leur visibilité visuelle après quelques jours. Ajout au `TODO.md`.

[2026-02-24] [PRO] Session 26 : Amélioration du Pilotage du Bot (Commandes Avancées & UI). (Action 1) Ajout de la commande `STOP_SCAN` avec `scan_stop_event` indépendant pour interrompre un scraping sans tuer le bot. (Action 2) Refonte sémantique de `STOP_BOT` : le bot entre dans une boucle de pause de 12h (interruptible) au lieu de s'éteindre totalement. (Action 3) Ajout de `START_BOT` pour réveiller le bot instantanément de sa pause. (Action 4) Extraction et refonte de l'interface des contrôles : création du composant `<BotControls />` hybride avec indicateur de statut dynamique intégré dans le panneau latéral "Système".

[2026-02-24] [FLASH] Session 25 : Correction "Mode Hors Ligne" du Bot. Automatisation du déploiement des fichiers ignorés par Git via GitHub Secrets (`DOT_ENV` et `FIREBASE_SERVICE_ACCOUNT_KEY`). Mise à jour de `deploy.yml` pour recréer dynamiquement `.env` à la racine et `serviceAccountKey.json` dans `backend/config/` sur le serveur.

[2026-02-24] [FLASH] Session 24 : Correction du flux de déploiement GitHub Actions (`deploy.yml`). (Action 1) Correction de la casse de la branche `dev` (était `Dev`). (Action 2) Remplacement de la réinitialisation forcée sur `master` par une logique dynamique utilisant `${{ github.ref_name }}`. (Action 3) Ajout de logs détaillés et d'une gestion d'erreur robuste pour le redémarrage du service `guitare-hunter`. (Action 4) Audit complet de la documentation (`docs/`).

[2026-02-24] [FLASH] Session 23 : Correction du rejet systématique des étuis/housses par le Portier et le Coupe-Circuit. (Action 1) Mise à jour de `prompts.json` : retrait de la condition d'exclusion sur les "accessoires bas de gamme (gigbag fin seul)" dans `main_analysis_prompt` — Les amplis, étuis et housses (même simples) sont maintenant tous acceptés. Mise à jour de `gatekeeper_verbosity_instruction` : retrait du rejet des "accessoires nuls", ajout explicite des guitares, amplis, étuis et housses comme objets acceptés. (Action 2) Standardisation des 3 instructions de verbosité (`gatekeeper`, `analyst`, `expert_pro`) de `string` → `array of strings` pour la compatibilité avec l'éditeur ligne-par-ligne du ConfigPanel. Mise à jour de `backend/analyzer.py` : ajout de `join("\n")` si l'instruction reçue est une liste.

[2026-02-24] [PRO] Session 22 : Résolution du conflit de casse Git (`Dev` vs `dev`) empêchant le déploiement sur `gh-pages`. Suppression de la branche `Dev` distante, nettoyage des références locales, et succès de `npm run deploy`. Exécution du workflow `/git-push-dev-master` pour synchroniser et achever la session.

[2026-02-24] [FLASH] Session 21 (suite) : Correctif TypeError prix int → cast `str()` dans `analyzer.py` avant `extract_price_from_text`. Création de `backend/scripts/migrate_firestore_prompts.py` (audit racine + injection clés Tier2/3 + nettoyage obsolètes, mode `--dry-run`). Ajout commande `STOP_BOT` : handler `threading.Event` dans `main.py`, `triggerStopBot()` dans `firestoreService.js`, bouton Power dans `LogViewer.jsx`.

[2026-02-24] [FLASH] Session 21 : Implémentation du Funnel 3-Tiers + Refacto DRY → `analyzer.py` restructuré avec `_call_gemini_json` (mutualisation des appels API), prompt de base construit une seule fois. Cascade T1 (Flash-Lite) → T2 (Flash, format compact + 5 scores) → Carrefour Logique → T3 (Pro, conditionnel). Seuils ajoutés dans `config.py`. Nouvelles instructions `analyst_verbosity_instruction` et `expert_pro_context_instruction` ajoutées dans `prompts.json` et init Firestore (`bot.py`). 4 rondes de vérification, 4 bugs corrigés. Push `dev`.

[2026-02-23] [FLASH] Réflexion Statistiques → Conceptualisation des KPIs basés sur les scores du Tier 2/3 et archivage dans `docs/STATS_REFLEXION.md`.

[2026-02-23] [FLASH] Action : Conception de l'entonnoir d'analyse à 3 niveaux et création de `docs/FUNNEL_PLAN.md` → Résultat : Stratégie validée pour réduire les coûts (Tier 2 compact) tout en augmentant la profondeur (Tier 3 Expert Pro conditionnel). Introduction de 5 scores numériques et d'une logique de déclenchement "Jackpot" (Marge + Défi).
[2026-02-23] [FLASH] Action : Création de `backend/scripts/fetch_deal.py` → Résultat : Outil fonctionnel pour inspecter les annonces réelles dans la structure Firestore imbriquée (`artifacts/{app}/users/{user}/...`).
[2026-02-23] [FLASH] Action : Mise à jour de `docs/ARCHITECTURE.md` → Résultat : Documentation de la structure multi-tenant de la base de données.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` → Résultat : Assainissement du titre de la notification (suppression des sauts de ligne `\n`) pour éviter des erreurs HTTP `Invalid header value` lors de l'envoi à `ntfy.sh`.
[2026-02-22] [PRO] Action : Modification de `src/App.jsx` → Résultat : Le lecteur récupère désormais l'ID d'annonce via le lien `deals` complet (et plus `filteredDeals`), évitant que la carte ne s'ouvre pas si l'annonce est archivée/filtrée.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` → Résultat : Le lien cliquable des notifications `ntfy` renvoie désormais vers la carte du deal sur le frontend (`?dealId=...`) au lieu de l'annonce Facebook FB.
[2026-02-23] [FLASH] Action : Audit final et synchronisation des branches → Résultat : Documentation (Journal, Todo, Architecture, Data Flow) auditée et synchronisée. Fusion de la branche `dev` vers `master` et push remote.

Ce journal suit les changements majeurs, les décisions d'architecture et les nouvelles fonctionnalités.

---

---

### **Date: 23/02/2026** (Session 19)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Entonnoir v2)

#### 📝 Description des Changements
- **Raffinage des déclencheurs Tier 3 (Expert Pro) :**
    - Couplage intelligent du prix et du score : le passage à l'Expert Pro pour les objets > 1000$ ne se fait que si le `deal_score` est >= 4 (évite d'analyser en profondeur des objets chers mais inintéressants).
    - Durcissement des contrôles d'authenticité : déclenchement systématique de l'Expert si `authenticity_score` <= 7.
    - Ajout d'un déclencheur spécifique pour les verdicts `COLLECTION`.
- **Mise à jour de `docs/FUNNEL_PLAN.md` :** Documentation complète de la logique de cascade.

#### 🤔 Raisonnement
L'objectif est d'économiser les appels au modèle Pro (plus coûteux) en s'assurant qu'il n'intervient que sur des annonces ayant un réel potentiel ou présentant un risque technique/historique nécessitant une haute précision.

---

### **Date: 23/02/2026** (Session 18)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Scores & Pédagogie)

#### 📝 Description des Changements
- **Enrichissement du Tier 2 (Analyste) :**
    - Introduction d'un système de notation sur 10 pour 5 indices : `deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, et `restoration_interest_score`.
    - Ajout du `restoration_interest_score` : Ce score évalue la valeur "pédagogique" ou le défi technique d'un projet de lutherie, permettant d'identifier des "Pépites de restauration" même si la marge financière pure est moindre.
- **Logique "Jackpot" :** Création d'un déclencheur Expert Pro si `deal_score` >= 6 ET `restoration_interest_score` >= 7.

#### 🤔 Raisonnement
Le projet "Guitar Hunter" n'est pas qu'une question de profit immédiat, c'est aussi un projet luthier-centric. Valoriser l'intérêt technique des réparations permet de ne pas rater des instruments rares ou complexes qui enrichissent l'expertise du Maître Luthier.

---

### **Date: 23/02/2026** (Session 17)

**Auteur:** Assistant AI

**Type:** Refonte Système (Commandes & Base de données)

#### 📝 Description des Changements
- **Migration des "Legacy Commands" vers la collection `commands` :**
    - Modification du Frontend (`src/services/firestoreService.js`) pour que les actions manuelles (Refresh, Cleanup, Reanalyze All, Scan URL) créent des documents dans la collection `commands` au lieu de modifier des champs d'horodatage sur la racine du document utilisateur.
    - Simplification du Backend (`backend/services.py` & `backend/bot.py`) : Le `ConfigManager` a été épuré de toute la logique complexe de vérification d'horodatage. La boucle principale (`main.py`) gère désormais de manière unifiée toutes les commandes entrantes (avec statut `pending`, `completed`, `failed`).
    - Nettoyage du Backend (`backend/repository.py`) : L'ancienne méthode `consume_command` qui supprimait les champs du document utilisateur a été supprimée suite à la nouvelle architecture.

#### 🤔 Raisonnement
Cette unification de l'architecture autour de la collection `commands` facilite grandement la traçabilité. Auparavant, le bot devait surveiller 4 champs (`forceRefresh`, `forceCleanup`, `forceReanalyzeAll`, `scanSpecificUrl`) greffés sur le document utilisateur. Maintenant, chaque commande, quelle que soit sa nature, suit un flux de vie identique (création → attente → traitement → terminé/erreur), ce qui rend le système beaucoup plus robuste et prévisible.

---

### **Date: 23/02/2026** (Session 16)

**Auteur:** Assistant AI

**Type:** Refonte Système (Scraping & Frontend)

#### 📝 Description des Changements
- **Robustesse du Scraper Playwright :**
    - Modification de `check_listing_availability` dans `backend/scraping/core.py` pour utiliser l'évaluation JavaScript native du DOM (`page.evaluate`). La détection des marqueurs "Vendu", "Sold" ou "plus disponible" ne repose plus sur des cibles CSS volatiles, mais scanne les textes rendus et visibles du `div[role="main"]`.
    - Timeout de navigation augmenté à 30 secondes pour compenser la lenteur applicative de Facebook sans déclencher de "faux positifs" de suppressions.
- **Sauvegarde de l'Historique (Soft Delete) :**
    - La fonction de nettoyage `cleanup_sold_listings` bascule exclusivement sur le taggage Firestore avec `status: 'sold'`, abandonnant le comportement `Hard Delete` non-désiré.
- **Transparence de l'UI Frontend (`DealCard.jsx` & Filtrage) :**
    - L'état `sold` réduit désormais l'opacité visuelle de l'annonce et applique un badge contextuel bloquant.
    - Correction du "Fantôme d'Analyse" : Les annonces liquidées avant qu'une IA ne rende un verdict (`DEFAULT`) ne tentent plus d'afficher "Analyse en cours..." mais explicitement "Non Analysé (Vendu)".
    - Correction du badge Compteur (`SOLD`) dans la barre de filtre pour comptabiliser les annonces vendues sans qu'elles ne soient exclues prématurément par l'absence d'une classe d'instruments.

#### 🤔 Raisonnement
Le cycle complet de vie d'une annonce doit garantir zéro perte de données. Les annonces vendues constituent une mine d'or pour évaluer le "Velocity Pricing" d'un luthier ou d'un revendeur. En préservant ces documents Firestore de façon élégante, l'application mûrit vers une plateforme d'analyse de marché long terme, et non plus un simple scanner éphémère.

---

### **Date: 22/02/2026** (Session 15 - Soir)

**Auteur:** Assistant AI

**Type:** Amélioration de l'Architecture & Résolution de Dette Technique

#### 📝 Description des Changements
- **Externalisation des verdicts de rejet (Coupe-circuit) :**
    - La liste des verdicts provoquant l'arrêt immédiat de l'analyse (`BAD_DEAL`, `REJECTED_ITEM`...) a été retirée du code Python (`backend/analyzer.py`).
    - Elle est désormais stockée dans `prompts.json` par défaut et gérée dynamiquement via Firestore (`analysisConfig.rejectionVerdicts`).
    - Ajout d'une interface d'édition (liste de textes) dans `ConfigPanel.jsx` (section "Intelligence Artificielle").

#### 🤔 Raisonnement
Cette modification résout une dette technique identifiée. Auparavant, si la taxonomie des verdicts venait à évoluer, le backend devait être recompilé. Maintenant, l'utilisateur a un contrôle total sur les conditions de "coupe-circuit" directement depuis l'interface web, rendant le système de filtrage (Portier) 100% piloté par les données.

---

### **Date: 22/02/2026** (Session 15 - Après-midi)

**Auteur:** Assistant AI

**Type:** Nettoyage & Organisation du Projet

#### 📝 Description des Changements
- **Dépollution de la racine :** Suppression des scripts de diagnostic et de setup obsolètes (`diagnose_firestore.py`, `populate_cities.py`, `test_notification.py`, `verify_setup.py`) et de l'ancien journal (`implementation_journal.md`).
- **Restructuration des fichiers de configuration :**
    - Création de `backend/resources/` et déplacement de `city_coordinates.json`.
    - Création de `firebase/` et déplacement de `firestore.rules`.
    - Création de `backend/config/` et déplacement de `serviceAccountKey.json`.
- **Mise à jour des références :** Correction des chemins d'accès dans `config.py` (backend), `src/components/MapView.jsx` (frontend) et `tests/check_baseline.py`.

#### 🤔 Raisonnement
Une racine propre facilite la navigation dans le projet et sépare clairement les fichiers de configuration, les ressources de données et le code source. La mise à jour des imports garantit que les deux environnements (Python et React) continuent de fonctionner sans interruption.

---

### **Date: 22/02/2026** (Session 15 - Matin)

**Auteur:** Assistant AI

**Type:** Analyse Technique & Audit de Données

#### 📝 Description des Changements
- **Audit de la base de données (Le mystère des annonces invisibles) :**
    - **Problème :** L'utilisateur a remarqué un écart de ~300 annonces entre le total Firestore (486) et les annonces visibles (84 + 91).
    - **Investigation :** Création de scripts d'audit (`inspect_db_stats.py`, `inspect_rejection_reasons.py`) pour analyser les documents `status: 'rejected'`.
    - **Découverte :** 287 annonces portent le verdict `REJECTED` (ancienne nomenclature v1). 20 proviennent du pré-filtre Javascript, le reste (267) provient des modèles Gemini (anciennes analyses).
    - **Cause de l'invisibilité :** Le frontend (`matchesVerdictFilter`) masque totalement les documents ayant un statut global `rejected`. Dans la nomenclature v2, le "bruit" est classé `REJECTED_ITEM` avec un statut global `analyzed`, ce qui les rend comptabilisable dans l'UI alors que la v1 les annihilait visuellement.
- **Analyse du système de nettoyage (Sold Listings) :**
    - Documentation du fonctionnement de `cleanup_sold_listings`. Identification de la fragilité de la détection (basée sur du texte strict) et du risque de perte d'historique dû au "Hard Delete".

#### 🤔 Raisonnement
Il est crucial de conserver l'historique des ventes pour de futures statistiques (Price History / Velocity). Le passage au "Soft Delete" est validé comme prochaine étape majeure.

---

### **Date: 20/02/2026** (Session 14 - Suite 2)

**Auteur:** Assistant AI

**Type:** Correction de Bug (Frontend / Firestore)

#### 📝 Description des Changements
- **Fix Bug #3 — Le bouton "Reset" corrompait Firestore :**
    - **Problème :** Bien que la sauvegarde champ par champ ait été corrigée hier (utilisation de la notation par point `updateDoc` avec `analysisConfig.mainAnalysisPrompt`), la fonction `handleResetDefaults` envoyait encore l'objet imbriqué entier `{ analysisConfig: { ... } }`. Cela entraînait un fallback de `firestoreService` sur l'ancienne méthode `setDoc` qui écrasait silencieusement la racine du document.
    - **Solution :** Refonte de `handleResetDefaults` dans `useBotConfig.js` pour construire un objet plat utilisant la notation par point avant de l'envoyer à `updateUserConfig`. La réinitialisation utilise désormais la même méthode d'écriture chirurgicale que les sauvegardes manuelles.

#### 🤔 Raisonnement
Cette asymétrie entre la sauvegarde ligne-par-ligne et la réinitialisation globale était un reste de l'ancienne architecture. Maintenant, toutes les opérations de mise à jour utilisent systématiquement la notation par point de Firestore pour garantir l'intégrité des autres données du document.

---

### **Date: 20/02/2026** (Session 14 - Suite)

**Auteur:** Assistant AI

**Type:** Nettoyage de Dette Technique

#### 📝 Description des Changements
- **Suppression du code mort :** Le fichier `backend/prompt_manager.py`, qui contenait l'ancienne architecture de prompts à 5 blocs inutilisée, a été retiré du projet (via `git rm`).
- **Nettoyage des configurations obsolètes :** Les anciennes clés (`persona`, `verdict_rules`, `system_structure`, etc.) ont été supprimées de `prompts.json` et de `config.py` pour alléger le code et éviter toute confusion future.

#### 🤔 Raisonnement
Le projet évolue avec succès vers un système d'analyse IA en cascade et paramétrable. Supprimer le code inactif (le vieux `PromptManager` monolithique) et nettoyer les résidus dans les configurations garantit que l'architecture reste claire et facile à comprendre pour les futures itérations.

---

### **Date: 20/02/2026** (Session 14)

**Auteur:** Assistant AI

**Type:** Audit Complet du Projet (Full Stack)

#### 📝 Description des Changements

1.  **Analyse globale des flux de données et de l'architecture :**
    - Réalisation d'un audit de bas en haut (Scrapers -> Core Logic -> IA -> Base de données -> Frontend).
    - Mise à jour de `docs/TODO.md` avec de nouvelles priorités de pointe (dette technique cachée).
    - Mise à jour de `docs/ARCHITECTURE.MD` pour refléter la situation réelle des flux de commandes.

2.  **Identifications Clés (Dette Technique ajoutée au TODO) :**
    - **Architecture de Commandes Hybride :** Le backend écoute à la fois des champs horodatés sur `users/{id}` (legacy) et des documents dans la collection `commands` (nouveau). Cela crée une complexité inutile.
    - **Logique de Rejet Hardcodée :** Le composant `DealAnalyzer` filtre les annonces en lisant en dur une liste de "verdicts de rejet" (`BAD_DEAL`, `REJECTED_ITEM`, etc.). Si la taxonomie en frontend/prompts évolue, le backend devient aveugle sans mise à jour du code source.
    - **Fragilité du Scraper :** La détection d'une annonce vendue sur Playwright se fie à une expression exacte ("Cette annonce n’est plus disponible"), ce qui est très cassable.

#### 🤔 Raisonnement

- Il est vital de de temps à autre "dézoomer" de la résolution de bugs isolés pour analyser les tendances de l'architecture. Ces découvertes empêchent qu'un simple changement de configuration (ex: renommage d'un statut dans l'UI) ne fasse tomber tout le backend silencieusement.

---
### **Date: 20/02/2026** (Session 13)

**Auteur:** Assistant AI

**Type:** Amélioration de la Configuration / Préparation au Déploiement

#### 📝 Description des Changements

1.  **Uniformisation de la gestion des IDs dans le Frontend :**
    - **Problème :** Les constantes `PYTHON_USER_ID` et `APP_ID` étaient codées en dur dans `src/services/firestoreService.js`, créant une redondance avec les variables d'environnement déjà présentes dans `.env` et configurées dans `vite.config.js`.
    - **Solution :** Remplacement des valeurs en dur par `process.env.USER_ID_TARGET` et `process.env.APP_ID_TARGET`.
    - **Bénéfice :** La configuration est désormais centralisée dans le fichier `.env`, facilitant le déploiement et la maintenance.

#### 🤔 Raisonnement

- Le passage aux variables d'environnement est une bonne pratique indispensable avant un déploiement, assurant que le code reste agnostique de l'environnement et que les identifiants clés peuvent être gérés de manière sécurisée et centralisée.

---

### **Date: 20/02/2026** (Session 12)

**Auteur:** Assistant AI

**Type:** Correction de Bugs (Priorité Haute)

#### 📝 Description des Changements

1.  **Fix Bug #1 — Classifications "Autre" (Frontend + Backend) :**
    - **Problème :** L'IA inventait des libellés libres (ex: "Fender Stratocaster") qui ne correspondaient pas exactement aux clés de la taxonomie (ex: "Stratocaster"). La fonction `normalize` ne permettait pas de trouver ces classifications.
    - **Solution :**
        - Rendu l'instruction de classification plus stricte dans `prompts.json` (demande la valeur exacte d'une feuille de la taxonomie).
        - Ajout d'une fonction `findPathFuzzy` dans `useDealsManager.js` pour tolérer les variations (recherche par sous-chaîne normalisée).

2.  **Fix Bug #2 — Compteurs de filtres incorrects (Frontend) :**
    - **Problème :** La boucle de comptage dans `useDealsManager.js` n'incrémentait que les 3 premiers niveaux (`path[0]`, `path[1]`, `path[2]`). Sur une taxonomie à 4 niveaux, la feuille finale n'était jamais comptée, affichant des badges erronés.
    - **Solution :** Remplacement des affectations dures par une boucle `path.forEach(segment => ...)` pour incrémenter dynamiquement tous les niveaux du chemin de la taxonomie.

#### 🤔 Raisonnement

- Ces deux bugs impactaient fortement l'expérience utilisateur (mauvais comptage, difficulté à filtrer les guitares). En durcissant le backend (prompt) tout en assouplissant le frontend (fuzzy match), on maximise les chances que la classification fonctionne même sur les anciennes annonces.

---

### **Date: 20/02/2026** (Session 11)

**Auteur:** Assistant AI

**Type:** Correction de Bug Critique (Frontend / Firestore)

#### 📝 Description des Changements

1.  **Correction du bug de corruption silencieuse de `analysisConfig` dans Firestore :**
    - **Problème :** La fonction `updateUserConfig` dans `firestoreService.js` utilisait systématiquement `setDoc` avec `merge: true`. Ce comportement merge uniquement au niveau racine du document Firestore. Passer un objet `{ analysisConfig: { mainAnalysisPrompt: [...] } }` **remplaçait intégralement** le sous-objet `analysisConfig`, effaçant silencieusement `gatekeeperModel`, `expertModel`, `gatekeeperVerbosityInstruction` et `expertContextInstruction`.
    - **Impact :** Chaque `onBlur` sur un `PromptListEditor` corrompait Firestore. La corruption causait également une race condition qui annulait le Reset.
    - **Solution :** `updateUserConfig` détecte maintenant si les clés passées contiennent une notation par points (ex: `'analysisConfig.mainAnalysisPrompt'`) :
        - **Dot-notation** → `updateDoc` : écriture chirurgicale sur le champ exact, sans toucher les champs frères.
        - **Objet complet** (ex: Reset) → `setDoc` + `merge: true` : comportement inchangé pour les resets complets.
    - **Fichiers modifiés :** `src/services/firestoreService.js`

#### 🤔 Raisonnement

- `updateDoc` de Firestore accepte nativement la notation par points pour cibler des sous-champs précis. C'est l'outil prévu pour ce cas d'usage. Le code utilisait déjà `unflatten` pour "deviner" l'intention, mais ce n'est pas suffisant car `setDoc + merge` ne merge pas en profondeur.

---

### **Date: 20/02/2026** (Session 10)

**Auteur:** Assistant AI

**Type:** Audit de Documentation & Analyse Approfondie

#### 📝 Description des Changements

1.  **Audit complet du système de prompts :**
    - Analyse exhaustive de tous les fichiers impliqués dans le pipeline de prompts, du backend (`config.py`, `analyzer.py`, `services.py`) au frontend (`useBotConfig.js`, `firestoreService.js`, `ConfigPanel.jsx`).
    - Identification et documentation du code mort : la classe `PromptManager` dans `backend/prompt_manager.py` est un orphelin non instancié, vestige d'une ancienne architecture "5 blocs". Les clés `persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`, `system_structure` dans `prompts.json` et leurs constantes associées dans `config.py` sont obsolètes.
    - Validation du format de `prompts.json` : syntaxiquement valide.

2.  **Mise à jour de `docs/ARCHITECTURE.md` (Section 4 — Système de Prompts) :**
    - Remplacement de la description générale par une analyse technique détaillée avec inventaire des fichiers, diagrammes de flux de données réels (Backend + Frontend), tableau des prompts modifiables par l'utilisateur, documentation du mécanisme de fallback, et inventaire de la dette technique.

#### 🤔 Raisonnement

- La documentation précédente donnait une vue d'ensemble correcte mais imprécise. L'ajout du tableau de fichiers avec leur statut (actif/orphelin) et des diagrammes de flux en texte brut offre une référence fiable pour les futurs développements, notamment pour le nettoyage du code mort.

---

### **Date: 23/02/2026** (Session 9)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Ajustement de la largeur de l'image sur mobile:**
    - **Problème:** La largeur de l'image sur mobile (`w-32`) était trop étroite.
    - **Solution:** La largeur du conteneur de l'image est passée à `w-1/2` (50% de la largeur de la carte), offrant un meilleur équilibre visuel avec le bloc de prix qui occupe les 50% restants.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Cet ajustement répond à la demande de donner plus d'importance à l'image sur mobile, tout en conservant une disposition en deux colonnes compacte.

---

### **Date: 23/02/2026** (Session 8)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Refonte de la structure de la `DealCard` (Mobile First):**
    - **Problème:** La disposition précédente ne satisfaisait pas les besoins spécifiques de l'affichage mobile (image complète, compacité) et desktop (hiérarchie claire).
    - **Solution:** Une approche "Mobile First" avec deux structures distinctes a été implémentée :
        - **Mobile (`md:hidden`):** Un en-tête compact affiche l'image (largeur fixe `w-32`) et le bloc de prix côte à côte. Le titre et les détails suivent en dessous.
        - **Desktop (`hidden md:block`):** La disposition classique en deux colonnes est conservée, avec l'image "sticky" à gauche. Dans la colonne de droite, le bloc de prix est positionné au-dessus du titre pour une meilleure hiérarchie.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

2.  **Création du composant `PriceDisplay`:**
    - **Action:** La logique d'affichage du prix et du menu déroulant financier a été extraite dans un sous-composant `PriceDisplay`. Cela permet de l'utiliser à deux endroits différents dans le code (header mobile et colonne desktop) sans dupliquer la logique complexe.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

3.  **Retour à l'affichage complet des images:**
    - **Action:** Annulation du changement `object-cover` dans `ImageGallery.jsx`. Les images sont de nouveau affichées en entier (`object-contain`) pour ne perdre aucun détail de l'instrument.

#### 🤔 Raisonnement

- Cette solution hybride offre le meilleur des deux mondes : une expérience mobile optimisée pour la densité d'information et une expérience desktop riche et structurée. L'extraction du composant `PriceDisplay` maintient le code propre et maintenable malgré la duplication structurelle.

---

### **Date: 23/02/2026** (Session 6)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Uniformisation de l'affichage du bloc prix:**
    - **Problème:** Le bloc de prix pouvait encore dépasser de la carte sur certains écrans d'ordinateur lorsque le titre était long et que l'affichage était en mode "ligne" (côte à côte).
    - **Solution:** L'affichage a été uniformisé pour être identique sur mobile et desktop. Le bloc de prix est désormais **toujours** positionné en dessous du titre et aligné à gauche. Cela garantit qu'il dispose toujours de toute la largeur nécessaire et élimine tout risque de dépassement.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- La cohérence de l'interface est primordiale. En adoptant une disposition verticale unique, on simplifie la maintenance et on s'assure que le contenu critique (le prix et les détails financiers) est toujours lisible, quelle que soit la contrainte d'espace horizontal.

---

### **Date: 23/02/2026** (Session 5)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Ajustement de la taille du bouton de prix:**
    - **Problème:** Le bouton de prix, bien que fonctionnel, pouvait être rendu plus compact pour un meilleur équilibre visuel.
    - **Solution:** Plusieurs micro-ajustements ont été effectués : réduction du `padding`, de la taille de la police, de la taille de l'icône, de l'espacement interne et du rayon de la bordure.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Ce changement est un raffinement stylistique visant à perfectionner l'équilibre et l'harmonie des composants de l'interface.

---

### **Date: 23/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Fusion du Bouton de Prix et du Toggle d'Expansion:**
    - **Problème:** Le bouton affichant le prix et le bouton pour déplier les détails financiers étaient deux éléments séparés, ce qui était moins intuitif et prenait plus de place.
    - **Solution:** Les deux éléments ont été fusionnés en un seul composant interactif. Le bouton de prix contient maintenant le montant et l'icône "chevron". L'ensemble du bloc est cliquable pour afficher/masquer les détails financiers.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Cette modification améliore l'expérience utilisateur en créant un point d'interaction unique et clair, ce qui est un standard de design d'interface.
- Elle permet également un gain d'espace marginal mais appréciable sur les petits écrans.

---

### **Date: 24/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** Correction de bugs (Priorité Haute)

#### 📝 Description des Changements

1.  **Correction de la commande `STOP_BOT` (Backend):**
    - **Problème:** La commande `STOP_BOT` via l'interface UI (ou Firestore) passait le statut du bot à `stopped` mais le programme Python continuait son scan ou nettoyage en cours (boucles synchrones Playwright/Firebase longues).
    - **Solution:** J'ai passé l'instance `threading.Event()` (`stop_event`) depuis `main.py` jusque dans `GuitarHunterBot` (`bot.py`) et `FacebookScraper` (`core.py`). Des vérifications `if self.stop_event.is_set(): return/break` ont été ajoutées dans les points stratégiques des boucles de défilement (`page.mouse.wheel`), d'analyse d'annonces, de nettoyage des vendues (`cleanup_sold_listings`) et des réanalyses en attente.
    - **Fichiers modifiés:** `main.py`, `backend/bot.py`, `backend/scraping/core.py`.

2.  **Correction de la suppression des logs côté client (Frontend):**
    - **Problème:** Le bouton "Vider la base de données" du `LogViewer.jsx` ne produisait aucun effet. Les logs écoutés correspondaient à un "userIdTarget" et un "appId" codés en dur (`00737242777130596039`, `c_5d118e71...`). 
    - **Solution:** Standardisation via des variables d'environnement. Ajout de `VITE_APP_ID_TARGET` et `VITE_USER_ID_TARGET` dans `.env` côté React, de façon à ce que le `LogViewer` se base dynamiquement sur la même configuration ciblée que le Backend Python et Firebase.
    - **Fichiers modifiés:** `src/components/LogViewer.jsx`, `.env`.

#### 🤔 Raisonnement

- **Stop Bot réactif :** Pour que "l'arrêt d'urgence" fonctionne, il fallait sortir le code d'une simple vérification entre deux cycles du scheduler (ancienne méthode) et propager un kill-switch asynchrone jusque dans les boucles de scraping internes. L'objet `threading.Event()` est parfait pour ça, agissant comme un drapeau partagé et thread-safe.
- **Dette Technique (Logs) :** Le code frontend pour les logs était resté sur un ancien jet de POC où je développais avec mes propres IDs personnels (Session 1 à 5). La standardisation avec `.env` aligne le `LogViewer` sur le reste de l'application.

---

### **Date: 23/02/2026** (Session 3)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX)

#### 📝 Description des Changements

1.  **Refonte du Menu de Réanalyse:**
    - **Problème:** Le menu de réanalyse (Standard/Expert) était "détaché" de la carte lors du défilement (scroll) car il utilisait un `Portal`. De plus, il était trop volumineux avec du texte inutile.
    - **Solution:**
        - **Ancrage:** Le menu est maintenant rendu directement dans le DOM de la carte, positionné en absolu par rapport au bouton de réanalyse. Il suit donc parfaitement le défilelement de la page.
        - **Design Compact:** Le texte a été supprimé au profit d'icônes (`RefreshCw` et `BrainCircuit`) avec des info-bulles (`title`). Le menu est beaucoup plus discret et s'intègre mieux à l'interface.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- L'utilisation de `Portal` pour des menus contextuels liés à des éléments scrollables est souvent problématique sans une gestion complexe de la position. L'ancrage direct via CSS (`position: absolute`) est une solution plus robuste et plus simple ici.
- La réduction de la taille du menu améliore l'expérience utilisateur, en particulier sur mobile où l'espace est limité.

---

### **Date: 23/02/2026** (Session 2)

**Auteur:** Assistant AI

**Type:** Amélioration du Design Responsive (UI/UX)

#### 📝 Description des Changements

1.  **Amélioration de l'affichage de la `DealCard` sur mobile:**
    - **Problème:** Sur les écrans de petite taille, le bloc contenant les informations financières (`Prix`, `Valeur Estimée`, etc.) ne passait pas à la ligne et débordait de la carte, rendant l'interface inutilisable.
    - **Solution:** La structure de l'en-tête de la carte a été rendue "responsive" :
        - Sur les écrans `md` et plus, le titre et le bloc financier sont côte à côte.
        - Sur les petits écrans (mobile), le bloc financier passe automatiquement sous le titre, utilisant toute la largeur disponible et évitant tout dépassement.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

2.  **Simplification de l'affichage du prix:**
    - **Problème:** Pour gagner de la place sur mobile, l'affichage du prix pouvait être plus compact.
    - **Solution:**
        - La mention "Prix Demandé" a été supprimée.
        - La taille de la police du prix a été réduite (`text-xl` au lieu de `text-2xl`).
        - Le padding du conteneur du prix a été ajusté.
    - **Fichiers modifiés:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- Ces changements sont cruciaux pour l'utilisabilité de l'application sur des appareils mobiles. Ils suivent les principes du "responsive design" en adaptant la disposition du contenu à la taille de l'écran.
- La simplification du prix contribue à une interface plus épurée et directe.

---

### **Date: 23/02/2026** (Session 1)

**Auteur:** Assistant AI

**Type:** Amélioration de l'interface utilisateur (UI/UX) & Correction de bug

#### 📝 Description des Changements

1.  **Refonte du Module Financier sur la `DealCard`:**
    - **Problème:** Les indicateurs financiers clés (`estimated_value`, `net_guitar_cost`, etc.) étaient cachés sous des conditions trop restrictives (ex: uniquement si la marge était positive ou si l'annonce n'était pas rejetée).
    - **Solution:** Un nouveau module financier a été implémenté :
        - **Toujours visible:** Le prix demandé, la valeur estimée et le potentiel de revente sont maintenant toujours visibles si les données existent, même pour les annonces rejetées.
        - **Détails sur demande:** Un menu déroulant (toggle) a été ajouté pour afficher les détails techniques comme le **Coût Net** et la **Marge Brute**.
        - **Code couleur:** La marge brute est maintenant colorée (vert si positive, rouge si négative) pour une identification rapide de la rentabilité.
    - **Fichier modifié:** `src/components/DealCard.jsx`

2.  **Correction du Bug de Réanalyse "Expert":**
    - **Problème:** Lors d'un clic sur le bouton de réanalyse "Expert", l'indicateur de chargement (spinner) ne s'activait pas car le statut `analyzing_expert` n'était pas correctement géré par le frontend.
    - **Solution:** Le statut `analyzing_expert` a été ajouté aux listes de vérification `isAnalyzing` et `getModelName` dans la `DealCard`.
    - **Fichier modifié:** `src/components/DealCard.jsx`

#### 🤔 Raisonnement

- La refonte du module financier a pour but de fournir à l'utilisateur un contexte complet sur **pourquoi** une annonce est jugée bonne ou mauvaise, même après qu'elle ait été rejetée.
- La correction du bug de réanalyse améliore le retour visuel pour l'utilisateur, confirmant que son action a bien été prise en compte.

---

### Session 20 : Expansion du Scope - Étape 1 (Amps & Étuis)

#### ✅ Objectif : Passer d'un système "Tout-Guitare"- [x] Bugfix: Taxonomy Count Collision (hierarchical paths).
  - [x] Round 1: Code Audit (Path normalization & aggregation).
  - [x] Round 2: Data Mapping Verification (Multi-parent nodes).
  - [x] Round 3: UI/Filter Interaction Sync.
- **Nouveaux Produits** : Intégration des `amplificateurs` (Lampes, Transistors, Modélisation) et des `accessoires_etuis` (Rigides, Housses souples).
- **Persona Luthier** : Mise à jour des prompts pour évaluer les amplis (état des lampes, transformateurs) et valoriser l'apport financier des housses/étuis pour le flipping.
- **Synchronisation Full-Stack** : Mise à jour de `config.py` et `useDealsManager.js` pour supporter dynamiquement la nouvelle structure.

#### 🤔 Raisonnement

- L'expansion permet de capturer des opportunités de "Fast Flip" (ex: Boss Katana) et de maximiser la valeur des packs guitare+étui.
- Le maintien du persona **Maître Luthier** assure une analyse technique rigoureuse, même sur des objets non-luthier classiques comme les amplis numériques.

---

[2026-02-26] [FLASH] Action effectuée → Migration complète vers l'UI V2, suppression de l'obsolescence V1 et validation du build de production.

### Session 36 : Activation Définitive de la V2 & Nettoyage V1

#### ✅ Objectif : Remplacer l'ancienne UI par la nouvelle interface SaaS V2.

- **Standardisation des Composants** : Renommage massif des composants `Mockup*` en noms de production (`Dashboard`, `Navbar`, `DealCard`, `FilterDrawer`, `StatsView`).
- **Simplification de `App.jsx`** : Suppression de toute la logique de bascule V1/V2. L'application monte désormais directement le `Dashboard` V2.
- **Suppression de la Dette Technique** : Élimination des fichiers V1 obsolètes (`FilterBar.jsx`, `SectionGroup.jsx`, `DealModal.jsx`, `BotControls.jsx`, `DebugStatus.jsx`).
- **Validation** : Build Vite (`npm run build`) validé avec succès (0 erreur d'import).

#### 🤔 Raisonnement

- La V2 est jugée supérieure en termes d'ergonomie (Filtres en tiroir, Stats intégrées, Map Split-screen) et d'esthétique (Dark Mode).
- Supprimer les fichiers obsolètes évite toute confusion future et allège le bundle final.
- La transition "Production Ready" marque la fin de la phase de prototypage de la nouvelle interface.

---

[2026-02-26] [FLASH] Action effectuée → Polissage UI : Verrouillage du scroll global et correction du clipping dans la Navbar.

### Session 39 : Polissage de l'Expérience Utilisateur

#### ✅ Objectif : Supprimer les artefacts visuels résiduels pour une expérience "Produit" parfaite.

- **Désactivation du Scroll Corps** : Ajout de `overflow: hidden` sur `html, body, #root` dans `index.css` pour forcer l'utilisation des conteneurs internes et supprimer la barre de défilement du navigateur.
- **Correction du Menu Statut** : Retrait de `overflow-x-hidden` sur la `Navbar` pour permettre au menu de survol (status controls) de s'afficher sans être tronqué.
- **Z-Index & Layers** : Vérification de la superposition des éléments interactifs pour un rendu "floating" optimal.

#### 🤔 Raisonnement

- Le Dashboard V2 est conçu pour être une interface fixe (SPA). La présence d'une scrollbar native sur le côté droit nuisait à l'aspect premium et cassait l'alignement visuel.
- La Navbar doit être capable de déborder (overflow visible) pour ses menus contextuels, tout en restant `sticky`.

---

[2026-02-26] [FLASH] Action effectuée → Bugfix ConfigPanel : Suppression d'un double `return` et de blocs syntaxiques redondants bloquant le build Vite.

### Session 40 : Correction Syntaxique Critique

- **Correction `ExclusionKeywordsSection`** : Suppression du code dupliqué par erreur lors du précédent push. Le composant `ConfigPanel.jsx` est désormais syntaxiquement correct.
- **Vérification** : Le build Vite ne doit plus lever l'erreur `The character "}" is not valid inside a JSX element`.

---

---

[2026-03-09] [FLASH] Action effectuée → Migration vers Tailscale OAuth pour le déploiement (CI/CD) et correction du périmètre des secrets.

### Session 48 : Intégration Tailscale OAuth (CI/CD)

#### ✅ Objectif : Sécuriser la connexion SSH du GitHub Runner via Tailscale OAuth.

- **DevOps (`deploy.yml`)** : Utilisation des secrets `TS_OAUTH_CLIENT_ID` et `TS_OAUTH_SECRET` pour rejoindre le Tailnet lors du déploiement.
- **Documentation** : Mise à jour de `ARCHITECTURE.md` pour clarifier que ces secrets concernent le pipeline de déploiement et non l'application.
- **Correction** : Retrait des variables OAuth de `config.py` et de l'injection dans le `.env` du serveur (périmètre CI/CD uniquement).

#### 🤔 Raisonnement

- Les identifiants OAuth Tailscale sont nécessaires au GitHub Runner pour accéder au serveur privé. L'application (bot) n'en a pas besoin pour son fonctionnement interne. Séparer les deux types de secrets améliore la clarté et la sécurité.

---
