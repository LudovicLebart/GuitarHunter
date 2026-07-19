# Journal de Bord - Guitar Hunter AI

[2026-07-19] [PRO] Fix : Code review 48h — 4 correctifs appliqués → Résultat :
- **`backend/scraping/parser.py`** : Ajout du cas `"il y a X mois"` dans `parse_french_date()` (formule Facebook fréquente, sans ce cas les annonces de 1-3 mois n'avaient pas de `publishTimestamp` et tombaient en fond de tri). Remplacement du regex mois générique `[a-zûé]+` par la liste exhaustive des 12 mois français pour éviter les faux positifs sur des mots inattendus.
- **`backend/repository.py`** : Transformation de `purge_rejected_images()` — passage d'un `.limit(200)` unique à une boucle `while True / break si len(docs) < BATCH_SIZE` pour épuiser un arriéré potentiel si la purge n'a pas tourné pendant plusieurs jours.
- **`src/hooks/useDealsManager.js`** : Ajout d'un `useRef fetchingIdsRef` (Set) pour tracker les IDs en cours de fetch et éviter les double-appels réseau lors de scrolls rapides ou re-renders consécutifs. Libération des IDs dans `.finally()` pour couvrir succès et erreur.
- **`scripts/build_deals_index.py`** : Ajout d'un warning explicite (`print`) si `ListingParser` est `None` suite à un `ImportError`, avec la commande correcte pour lancer le script depuis la racine du projet.

[2026-07-18] [PRO 3.1] Fix : Tableau de bord vide suite Ã  la mise en place du Lazy Loading â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : L'utilisateur ne voyait plus aucune annonce sur son tableau de bord aprÃ¨s la migration vers l'index allÃ©gÃ©.
- **Diagnostic** : Le nouveau script de migration `build_deals_index.py` crÃ©ait un index lÃ©ger qui retirait intentionnellement le champ `reasoning` de l'IA (trop volumineux) pour Ã©conomiser l'espace. Or, `useDealsManager.js` vÃ©rifiait encore la prÃ©sence de `analysis.reasoning` pour certifier qu'une annonce n'Ã©tait pas une erreur IA.
- **`src/hooks/useDealsManager.js`** : Suppression stricte de la dÃ©pendance Ã  `analysis.reasoning` dans `matchesVerdictFilter` et `verdictCounts`. Les filtres s'appuient dÃ©sormais uniquement sur le verdict et les classifications prÃ©sentes dans l'index. Le tableau de bord affiche de nouveau toutes les annonces et profite de la fluiditÃ© et des Ã©conomies du Lazy Loading.

[2026-07-18] [PRO] Fix : Partage d'annonces (Analyse IA tronquÃ©e) â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : Lorsqu'un utilisateur partageait une annonce, le lien gÃ©nÃ©rÃ© affichait une version rÃ©duite sans le verdict ni l'analyse complÃ¨te de l'IA.
- **`src/services/firestoreService.js`** : Mise Ã  jour de `createSharedDeal` pour qu'il puise correctement le verdict, l'analyse (`reasoning`) et les scores depuis l'objet imbriquÃ© `deal.aiAnalysis` (au lieu de les chercher Ã  la racine de `deal`). Les liens partagÃ©s affichent dÃ©sormais l'intÃ©gralitÃ© du travail de l'Expert IA.

[2026-07-18] [PRO] Feature : Notification (ntfy + email) Ã  la fin d'un scan d'URL manuel â†’ RÃ©sultat :
- **Contexte** : Demande d'Ãªtre informÃ© de la fin d'une requÃªte de scan d'URL.
- **`backend/notifications.py`** : Ajout de la mÃ©thode statique `notify_scan_url_finished(url, user_email, logger)` qui envoie un ntfy et un email au demandeur.
- **`backend/bot.py`** : Appel de la notification dans le bloc `try/finally` de `scan_specific_url` une fois le scraper temporaire terminÃ©.

[2026-07-18] [PRO] Refactor : Optimisation massive des coÃ»ts de lecture Firestore via Sharded Index Document et Lazy Loading â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : CoÃ»ts de lecture Firestore astronomiques (~15$/mois pour 40 millions de lectures) causÃ©s par le chargement intÃ©gral des 2748 annonces au dÃ©marrage.
- **Architecture d'Index Document ShardÃ© (`deals_index/`)** : CrÃ©ation d'un index allÃ©gÃ© contenant uniquement les mÃ©tadonnÃ©es de filtrage/tri/compteurs (10 propriÃ©tÃ©s, ~100 octets/annonce) divisÃ© uniformÃ©ment en 20 chunks pour Ã©viter la limite Firestore d'indexation par document (INDEX_ENTRIES_COUNT_LIMIT_EXCEEDED).
- **Frontend (`src/services/firestoreService.js`, `src/hooks/useDealsManager.js`)** : Hydratation initiale sur l'Ã©couteur d'index (seulement 20 lectures Firestore). Les annonces complÃ¨tes (images, description, analyse IA longue) sont tÃ©lÃ©chargÃ©es par paquets de 30 uniquement lorsqu'elles entrent dans la zone visible de l'Ã©cran (Lazy Loading avec cache local rÃ©utilisable).
- **Backend (`backend/repository.py`)** : Maintien chirurgical de l'index en dot-notation Ã  chaque crÃ©ation, modification ou suppression d'annonce, sans aucune lecture Firestore supplÃ©mentaire.
- **Migration (`scripts/build_deals_index.py`)** : Script de migration exÃ©cutÃ© avec succÃ¨s pour peupler initialement l'index de toutes les annonces existantes et injecter les `chunkId` correspondants.
- **Optimisation Backend additionnelle (`backend/repository.py`)** : Ciblage strict de `status == 'analyzed'` dans `get_active_listings()`, et limitation de la tÃ¢che de purge `purge_rejected_images` via `limit(200)` pour rÃ©duire les lectures de maintenance.

[2026-07-15] [PRO] Fix : 4 bugs remontÃ©s (vendues non identifiÃ©es, bruit non catÃ©gorisÃ©, favoris polluÃ©s) + persistance des filtres par utilisateur â†’ RÃ©sultat :
- **Contexte** : 5 points remontÃ©s par l'utilisateur. Investigation (docs + code frontend/backend + agent Explore sur `bot.py`/`analyzer.py`/`core.py`) avant tout code, conformÃ©ment au protocole.
- **Annonce vendue non identifiÃ©e (frontend)** : `DealCard.jsx` n'affichait **aucun** indicateur pour `deal.status === 'sold'` (ni badge, ni opacitÃ©) â€” le badge de verdict d'origine restait affichÃ© tel quel. Ajout d'un badge "Vendu" (icÃ´ne `Ban`) + opacitÃ© rÃ©duite (`opacity-60 saturate-50`), dans la carte ET la modale, indÃ©pendamment du verdict.
- **Annonces "dans le bruit" sans label (frontend)** : cause identifiÃ©e en lisant `analyzer.py` â€” un double-Ã©chec IA (Tier 1 **et** Tier 2 en erreur) produit un verdict `ERROR_GATEKEEPER` avec un `reasoning` non vide. Ce verdict Ã©chappait Ã  la fois au filtre `isError` de `useDealsManager.js` (qui ne dÃ©tectait que `DEFAULT`/`ERROR` littÃ©raux ou reasoning vide) et Ã  `ARCHIVE_GROUP` (`constants.js`) â†’ il atterrissait dans la vue "Toutes" avec le badge par dÃ©faut trompeur ("Analyse..."). `isError` Ã©largi pour couvrir tout verdict absent de la taxonomie connue (`NEW_VERDICTS`/`LEGACY_VERDICTS`/`ARCHIVE_GROUP`), pas seulement les valeurs littÃ©rales `DEFAULT`/`ERROR`.
- **Favoris incluant du bruit (frontend)** : `matchesVerdictFilter` retournait `deal.isFavorite` sans filtrer le verdict pour le cas `FAVORITES`. Exclusion dÃ©sormais des verdicts archivÃ©s (`REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA`, `REJECTED`) et des erreurs, en gardant `BAD_DEAL` ("trop cher" confirmÃ© comme favori lÃ©gitime par l'utilisateur). Le compteur `verdictCounts.FAVORITES` (2 emplacements) corrigÃ© pour rester cohÃ©rent avec la liste affichÃ©e.
- **Annonces supprimÃ©es de Facebook encore visibles (backend, diagnostiquÃ©, non corrigÃ©)** : le bot dÃ©tecte dÃ©jÃ  les annonces supprimÃ©es par le vendeur (404, redirection vers l'accueil Marketplace dans `check_listing_availability`, `backend/scraping/core.py`) â€” fusionnÃ©es avec la dÃ©tection de vente (`status: 'sold'`, pas de statut "supprimÃ©" distinct). Le nettoyage (`cleanup_sold_listings`) tourne automatiquement toutes les 24h (`schedule.every(24).hours`, `backend/services.py`) â†’ latence normale jusqu'Ã  24h, pas un bug. Le "ralentissement du chargement" perÃ§u vient probablement plutÃ´t du fait qu'`onDealsUpdate` charge **toute** la collection `guitar_deals` (y compris vendues/rejetÃ©es, jamais purgÃ©es) Ã  chaque connexion. Ces deux constats ajoutÃ©s au `TODO.md`, non corrigÃ©s (dÃ©cision produit Ã  trancher : rÃ©duire l'intervalle ? filtrer/paginer cÃ´tÃ© serveur ?).
- **Persistance des filtres par utilisateur (Firestore)** : `useBotConfig.js` â€” nouvel Ã©tat `uiFilters` (lu depuis le doc utilisateur au mÃªme titre que `scanConfig`/`analysisConfig`) + `saveUiFilters` (Ã©criture debouncÃ©e 800ms). `DealsContext.jsx` relaie vers `useDealsManager`, qui hydrate une seule fois au premier chargement puis sauvegarde automatiquement Ã  chaque changement (`filterType`, niveaux 1-4, condition, prix, `sortMode`) â€” la recherche texte libre n'est pas persistÃ©e.
- **VÃ©rifiÃ©** : build/console propres (`npm run dev`), rendu de la page de login OK. Non testÃ© en conditions rÃ©elles avec des annonces (nÃ©cessite authentification) â€” confirmÃ© fonctionnel par l'utilisateur avant push.

[2026-07-14] [PRO] Fix : DÃ©filement fixe (3 scrolls) limitant le nombre d'annonces scrapÃ©es par ville â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : l'utilisateur constate que beaucoup d'annonces ne sont pas listÃ©es dans l'app, malgrÃ© 12 villes configurÃ©es et un `max_ads` rÃ©glÃ© Ã  50.
- **Cause confirmÃ©e par lecture du code (pas d'accÃ¨s aux logs de prod depuis cet environnement)** : `run_scan()` (`bot.py`) applique `max_ads` **par ville** (pas globalement) â€” avec 12 villes ce n'est donc pas le plafond limitant. Le vrai goulot : `ScraperConfig.scroll_iterations` Ã©tait fixÃ© en dur Ã  3 (`backend/scraping/config.py`), non exposÃ© dans Firestore/`ConfigPanel`. `scan_marketplace()` ne scrollait que 3 fois avant de lire les cartes d'annonces chargÃ©es dans le DOM (`backend/scraping/core.py`) â€” ce plafond Ã©tait atteint bien avant `max_ads`, quel que soit le volume rÃ©el de rÃ©sultats Facebook pour une ville donnÃ©e.
- **Piste Ã©cartÃ©e par l'utilisateur** : le matching strict de localisation (`is_city_allowed()`, mode `distance=0`) est un choix assumÃ©, pas un bug â€” non modifiÃ©.
- **`backend/scraping/config.py`** : `scroll_iterations` (fixe) â†’ `max_scroll_iterations` (garde-fou, dÃ©faut 20).
- **`backend/scraping/core.py::scan_marketplace()`** : scroll dynamique â€” la boucle s'arrÃªte dÃ¨s que le nombre de cartes chargÃ©es atteint `max_ads`, ou stagne sur 2 itÃ©rations consÃ©cutives (fin de liste rÃ©elle), sinon continue jusqu'au plafond de sÃ©curitÃ©.
- **Non testÃ© en conditions rÃ©elles depuis cet environnement** (pas d'accÃ¨s Ã  un compte Facebook/Playwright live) â€” seule la syntaxe Python a Ã©tÃ© vÃ©rifiÃ©e avant de committer ; validation en prod Ã  la charge de l'utilisateur.

[2026-07-14] [PRO] Feature : Note d'intÃ©rÃªt IA par annonce + choix de tri (Date / IntÃ©rÃªt) â†’ RÃ©sultat :
- **Contexte** : Demande utilisateur â€” pouvoir dÃ©partager les annonces qui ne sont pas des "PÃ©pites" selon leur intÃ©rÃªt, plutÃ´t que de les subir dans l'ordre chronologique imposÃ© par `onDealsUpdate` (`firestoreService.js`).
- **`src/constants.js`** : nouvelle fonction `computeInterestScore(aiAnalysis)` â€” moyenne des 5 scores IA dÃ©jÃ  existants (`deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, `restoration_interest_score`). Purement client-side, aucun nouveau champ Firestore/backend.
- **`src/hooks/useDealsManager.js`** : nouvel Ã©tat `sortMode` (`'date'` par dÃ©faut, `'interest'` en option), exposÃ© via `filterProps`. `filteredDeals` retriÃ© par note dÃ©croissante en mode `'interest'`, avec repli sur l'ordre par date pour les annonces sans scores (erreurs, `PENDING`).
- **`src/components/FilterDrawer.jsx`** : nouvelle section "Trier par" en tÃªte du tiroir de filtres (options "Plus rÃ©centes" / "Plus intÃ©ressantes (note IA)").
- **`src/components/Dashboard.jsx`** : relais `sortMode`/`setSortMode` entre `useDealsManager` et `FilterDrawer` (clÃ© `sort`, sans mapping `'all'`/`'ALL'` contrairement aux autres filtres).
- **`src/components/DealCard.jsx`** : badge "Note X.X/10" affichÃ© Ã  cÃ´tÃ© du badge de verdict, absent si aucun score disponible.
- **VÃ©rification** : `npm run build` (Vite) passe sans erreur aprÃ¨s les 5 modifications.

[2026-07-13] [PRO] Fix : Menu "RÃ©-analyser" (options de rescan) de la carte annonce inaccessible au survol sur desktop â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : sur l'interface ordinateur, les options du menu RÃ©-analyser (Scan Standard, Luthier Expert, Avec commentaire...) disparaissent souvent avant qu'on puisse cliquer dessus ; quand on y arrive, rien ne se passe (ni rescan lancÃ©, ni popup de commentaire). Meilleur fonctionnement sur mobile.
- **Cause confirmÃ©e** : mÃªme famille de bug que le fix Navbar du 2026-07-11 (ci-dessous), mais sur un gap **vertical** cette fois. Le conteneur `.relative` qui gÃ¨re `onMouseEnter`/`onMouseLeave` (`DealCard.jsx`) n'englobe que le bouton RefreshCw (40Ã—40px) ; le menu dÃ©roulant Ã©tait positionnÃ© avec `bottom-full mb-2` (carte) / `top-full mt-2` (modale) â€” un `margin`, donc hors de la boÃ®te du conteneur survolÃ©. En traversant ce vide (~8px), le curseur sortait de `:hover` avant d'atteindre le menu, qui se dÃ©montait en plein trajet. Si ce dÃ©montage survenait pendant le clic (mousedown/mouseup), le clic ne touchait plus rien â€” d'oÃ¹ le second symptÃ´me.
- **`src/components/DealCard.jsx`** : `margin` remplacÃ© par `padding` sur un wrapper englobant (`pb-2`/`pt-2` au lieu de `mb-2`/`mt-2`), avec le style visuel du menu dÃ©placÃ© dans un `<div>` interne â€” le gap fait dÃ©sormais partie de la zone survolÃ©e, comme pour la Navbar. AppliquÃ© aux deux emplacements dupliquÃ©s : footer de carte (rendu direct) et `renderActionButtons` (utilisÃ© par la modale d'analyse IA).
- **Fix vÃ©rifiÃ© avant/aprÃ¨s** : reproduction isolÃ©e (HTML/Tailwind servi en local, hors app, sans dÃ©pendance Firebase) â€” la version "margin" se ferme bien quand le curseur traverse le gap, empÃªchant tout clic ; la version "padding" reste ouverte dans la mÃªme zone et le clic dÃ©clenche bien l'action. Non testÃ© en conditions rÃ©elles dans l'app (nÃ©cessite authentification) â€” Ã  confirmer par l'utilisateur.

[2026-07-11] [PRO] Fix : Menu dÃ©roulant du statut bot (Navbar) inaccessible au survol sur desktop â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : sur l'interface ordinateur, les boutons du menu (Scanner maintenant, VÃ©rifier Stocks, Stop Scan/Start Bot) affichÃ© au survol du statut bot disparaissent dÃ¨s que la souris se dÃ©place vers eux.
- **Cause confirmÃ©e par reproduction isolÃ©e (HTML/CSS + Playwright, mouvement de souris simulÃ© hors application)** : le conteneur `.group` (`Navbar.jsx`) qui dÃ©clenche l'affichage au survol n'a que la largeur du texte de statut ("Scan en cours", "En attente"...), nettement plus Ã©troit que le menu affichÃ© en dessous (jusqu'Ã  4 boutons + sÃ©parateur). Un dÃ©placement en diagonale vers un bouton excentrÃ© (gauche/droite du centre) sort de la zone `:hover` avant d'atteindre le menu, qui redevient invisible/non cliquable en plein trajet â€” reproduit et confirmÃ© de faÃ§on dÃ©terministe, pas un problÃ¨me de souris/OS particulier.
- **`src/components/Navbar.jsx`** : ajout de `justify-center lg:min-w-[190px]` au conteneur `.group` (calibrÃ© sur la largeur max du menu Ã  4 boutons), pour que sa zone de survol couvre dÃ©jÃ  toute la largeur du menu Ã  toute hauteur. LimitÃ© Ã  `lg:` (desktop) pour ne pas Ã©largir inutilement la barre de navigation sur mobile.
- **Fix vÃ©rifiÃ© avant implÃ©mentation** : reproduction du bug puis du fix dans un fichier HTML/CSS isolÃ© (classes Ã©quivalentes, sans dÃ©pendance Firebase), via Playwright â€” Ã©chec de clic confirmÃ© sur les boutons excentrÃ©s avant le fix, succÃ¨s sur les 4 boutons aprÃ¨s.

[2026-07-11] [PRO] Fix : Cause racine de l'absence d'emails "PÃ©pite" trouvÃ©e + pipeline de dÃ©ploiement fragilisÃ© au passage â†’ RÃ©sultat :
- **Cause confirmÃ©e** : le secret GitHub `DOT_ENV` ne contenait jamais `SMTP_USER`/`SMTP_PASSWORD` depuis la mise en place de la feature â€” `.env.example` les documentait comme modÃ¨le, mais jamais reportÃ©s dans le vrai secret. Ni un bug de code (le fix logger du 2026-07-09 Ã©tait correct mais insuffisant pour ce diagnostic), ni des identifiants Gmail rÃ©voquÃ©s. ConfirmÃ© par investigation en direct avec l'utilisateur : `WorkingDirectory` du service `guitare-hunter` vÃ©rifiÃ© correct, `.env` dÃ©ployÃ© confirmÃ© prÃ©sent et Ã  jour (timestamp du dÃ©ploiement), mais `grep -o '^[A-Z_]*=' ~/GuitareHunter/.env` ne listait aucune clÃ© `SMTP_`.
- **Bug dÃ©couvert en corrigeant** : aprÃ¨s ajout des lignes SMTP au secret, 2 dÃ©ploiements consÃ©cutifs ont Ã©chouÃ© (`bash: erreur de syntaxe prÃ¨s du symbole inattendu Â« ) Â»`) sur les jobs `deploy-frontend` ET `deploy` (SSH). Cause : `.github/workflows/deploy.yml` interpolait `${{ secrets.DOT_ENV }}`/`${{ secrets.FIREBASE_SERVICE_ACCOUNT_KEY }}` littÃ©ralement dans les scripts bash (`echo "${{ secrets.X }}" > .env`) â€” un simple guillemet dans la valeur du secret casse la chaÃ®ne bash et fait Ã©chouer tout le dÃ©ploiement, quel que soit le contenu voulu.
- **`deploy.yml` durci** : `DOT_ENV` transmis via `env:` au step `Create .env file` (rÃ©fÃ©rencÃ© `"$DOT_ENV"`, plus jamais interpolÃ© littÃ©ralement). Pour le job `deploy` (SSH, `appleboy/ssh-action`), `DOT_ENV`/`FIREBASE_SERVICE_ACCOUNT_KEY` transmis via le paramÃ¨tre `envs:` de l'action plutÃ´t qu'interpolÃ©s dans le script distant. `echo >` remplacÃ© par `printf '%s' >` pour l'Ã©criture des fichiers. Rend le pipeline robuste Ã  n'importe quel caractÃ¨re dans les secrets, sans avoir Ã  les Ã©diter avec prÃ©caution.
- **Outils utilisÃ©s pour le diagnostic** : LogViewer (curseur "Limite Temporaire de Logs" du `ConfigPanel`, jusqu'Ã  500 lignes â€” pas 100, contrairement Ã  l'idÃ©e reÃ§ue de l'utilisateur), historique des runs GitHub Actions (`mcp__github__actions_list`/`get_job_logs`) pour confirmer succÃ¨s/Ã©chec et timestamps de dÃ©ploiement, vÃ©rifications directes sur le serveur (`systemctl show`, `grep` sur `.env`).

[2026-07-11] [PRO] Fix : `schedule.run_pending()` non protÃ©gÃ© dans la boucle watchdog globale (risque de crash process-wide) â†’ RÃ©sultat :
- **Contexte** : Revue du commit "Dashboard Administrateur â€” Phase 1" (voir entrÃ©e suivante) Ã  la demande de l'utilisateur ("vÃ©rifie que Ã§a ne pose pas de problÃ¨mes"). Ce commit ajoute `schedule.every().day.at("03:00").do(run_admin_stats_job, ...)` et un appel `schedule.run_pending()` dans la boucle watchdog globale de `main.py`.
- **Risque identifiÃ©** : `backend/services.py::TaskScheduler` utilise le scheduler **global partagÃ©** de la librairie `schedule` (pas d'instance dÃ©diÃ©e) â€” chaque thread utilisateur y enregistre ses jobs (`scan`/`cleanup`/`purge`) sur la mÃªme liste. Jusqu'ici, `schedule.run_pending()` n'Ã©tait appelÃ© que depuis la boucle interne de chaque thread utilisateur (`main.py:82`), protÃ©gÃ©e par un `except Exception` qui logue et continue. Le nouvel appel dans la boucle watchdog globale n'Ã©tait protÃ©gÃ© que par `except KeyboardInterrupt` â€” comme `run_pending()` exÃ©cute *tous* les jobs dus (pas seulement `admin_stats`), une exception non gÃ©rÃ©e dans le job planifiÃ© de n'importe quel utilisateur aurait fait planter tout le process, tous utilisateurs confondus, via le mÃ©canisme censÃ© les protÃ©ger d'une panne isolÃ©e.
- **`main.py`** : Ajout d'un `try/except Exception` dÃ©diÃ© autour de l'appel, mÃªme pattern que la boucle par-utilisateur (log + continue, pas d'interruption du watchdog).

[2026-07-11] [PRO] Feature : Dashboard Administrateur â€” Phase 1 (Monitoring, lecture seule) â†’ RÃ©sultat :
- **`backend/scripts/set_admin_claim.py`** : Script one-shot (Admin SDK) pour poser le custom claim `admin: true` sur un compte Firebase. Usage : `python backend/scripts/set_admin_claim.py --email admin@example.com` (option `--revoke` pour retrait).
- **`firebase/firestore.rules`** : Ajout de la fonction `isAdmin()` (`request.auth.token.admin == true`) + rÃ¨gles `collectionGroup('users')` et `collectionGroup('guitar_deals')` autorisant la lecture cross-utilisateurs uniquement pour l'admin. Nouvelle collection `admin_stats/{docId}` en lecture admin, Ã©criture interdite au client (Admin SDK only). Les rÃ¨gles d'isolation utilisateur existantes sont inchangÃ©es.
- **`backend/admin_stats.py`** : Job quotidien calculant, par utilisateur, le volume `guitar_deals` des derniÃ¨res 24h, le funnel Tier 1â†’2â†’3 et le coÃ»t Gemini estimÃ©. RÃ©utilise les constantes et formules de `analyze_funnel_by_user.py`. Ã‰crit dans `artifacts/{APP_ID}/admin_stats/latest`.
- **`main.py`** : IntÃ©gration du job `run_admin_stats_job` dans la boucle watchdog via `schedule.every().day.at("03:00")` (singleton global, une seule fois quel que soit le nombre de threads utilisateur).
- **`src/hooks/useAuth.js`** : Nouveau state `isAdmin` initialisÃ© via `firebaseUser.getIdTokenResult()` Ã  chaque changement d'Ã©tat d'auth. VÃ©rification dÃ©fensive cÃ´tÃ© client (la vraie protection reste les rÃ¨gles Firestore). ExposÃ© dans le return du hook.
- **`src/components/Navbar.jsx`** : Bouton `ShieldCheck` affichÃ© uniquement si `isAdmin === true`. Nouvelle prop `onOpenAdmin`.
- **`src/components/Dashboard.jsx`** : Import et montage conditionnel de `AdminDashboard` via `showAdmin` state.
- **`src/components/AdminDashboard.jsx`** : Nouveau composant â€” tableau des utilisateurs (email, UID, botStatus, villes, frÃ©quence de scan, dernier login), enrichi par les stats de coÃ»t/volume du snapshot `admin_stats/latest` (non-bloquant si absent). Bouton RafraÃ®chir.
- **Phase 2 non livrÃ©e** : Actions privilÃ©giÃ©es (`DISABLE_USER`, `SEND_EMAIL`, `STOP_BOT` admin, journal d'audit) restent planifiÃ©es dans `ADMIN_DASHBOARD_PLAN.md`.

[2026-07-11] [PRO] Fix : STOP_SCAN/STOP_BOT/START_BOT Ã©chouaient toujours ("Erreur lors de l'envoi de la commande") â†’ RÃ©sultat :
- **SymptÃ´me signalÃ©** : clic sur "Interrompre le scan" â†’ alerte `Erreur STOP_SCAN: Erreur lors de l'envoi de la commande.`
- **Cause** : `src/components/Navbar.jsx` appelle `triggerStopScan()`/`triggerStopBot()`/`triggerStartBot()` (`firestoreService.js`) directement, sans passer par `useBotConfig.js` (qui fournit correctement `user.uid` pour Refresh/Cleanup/Reanalyze). Ces 3 appels n'avaient aucun argument `userId` â†’ `getRefs(undefined)` lÃ¨ve une erreur (fail fast, voir CLAUDE.md), catchÃ©e par `addCommand()` et remplacÃ©e par le message gÃ©nÃ©rique `"Erreur lors de l'envoi de la commande."` â€” masquant la vraie cause Ã  l'utilisateur comme dans les logs.
- **`Navbar.jsx`** : `user` rÃ©cupÃ©rÃ© via `useAuth()` (dÃ©jÃ  importÃ© pour `signOut`, mais jamais destructurÃ©) et passÃ© en `user?.uid` aux 3 appels.
- **Non couvert par les tests/lint** : bug uniquement visible Ã  l'usage (clic bouton), invisible en compilation puisque `userId` est un paramÃ¨tre optionnel cÃ´tÃ© JS.

[2026-07-11] [PRO] Feature : Stat "Erreurs Portier corrigÃ©es" (StatsView) â†’ RÃ©sultat :
- **Contexte** : Suite Ã  un cas rÃ©el observÃ© par l'utilisateur (une annonce rejetÃ©e par le Portier, rÃ©analysÃ©e manuellement, rÃ©vÃ©lÃ©e comme une PÃ©pite), constat que `dev` disposait dÃ©jÃ  d'un outil de diagnostic ponctuel (`analyze_funnel_by_user.py --sample-size`, Â§8.2 de `GEMINI_PROMPT_CACHING_PLAN.md`) mais rien d'automatisÃ©/permanent dans l'app pour suivre ce taux d'erreur dans le temps.
- **`backend/repository.py::create_new_deal()`** : deux nouveaux champs figÃ©s Ã  la crÃ©ation, jamais rÃ©Ã©crits par les rÃ©analyses ultÃ©rieures (contrairement Ã  `aiAnalysis`) : `initialVerdict` (verdict du tout premier passage IA) et `initialModelUsed` (chaÃ®ne `model_used` du premier passage, ex: `"gemini-2.5-flash-lite"` si arrÃªtÃ© au Portier seul).
- **`src/components/StatsView.jsx`** : nouvelle stat sous le Funnel â€” parmi les annonces dont la chaÃ®ne `initialModelUsed` ne compte qu'un seul maillon (= arrÃªtÃ©es au Portier seul, jamais passÃ©es Ã  l'Analyste), compte celles dont la chaÃ®ne `aiAnalysis.model_used` **actuelle** compte 2 maillons ou plus (= rÃ©analysÃ©es avec succÃ¨s depuis). Affichage : `X/Y (Z%)`.
- **Pourquoi pas une simple comparaison de `verdict`** : `BAD_DEAL` peut provenir soit d'un vrai rejet Portier, soit d'un verdict lÃ©gitime de l'Analyste (Tier 2) aprÃ¨s analyse complÃ¨te ("trop cher") â€” les confondre aurait faussÃ© la stat. La longueur de chaÃ®ne `model_used` lÃ¨ve l'ambiguÃ¯tÃ© sans dÃ©pendre du texte du verdict (qui est configurable par l'utilisateur via `rejectionVerdicts`).
- **Limite assumÃ©e** : pas de backfill â€” seules les annonces crÃ©Ã©es aprÃ¨s ce dÃ©ploiement auront `initialVerdict`/`initialModelUsed` ; la stat dÃ©marre Ã  0/0.
- **Branche** : rebase (fast-forward) de `claude/claude-md-literate-ovyt5p` sur `dev` avant implÃ©mentation (18 commits de retard sur `master`, incluant le fix du faux positif Portier "acoustique 12 cordes" â€” voir `GEMINI_PROMPT_CACHING_PLAN.md Â§8.2`).

[2026-07-09] [FLASH] Ajout : Script de test manuel du pipeline de notifications â†’ RÃ©sultat :
- `backend/scripts/test_notification.py` : dÃ©clenche une notification factice (verdict `PEPITE`) sans attendre un vrai scan, avec le vrai logger par-utilisateur (raccordÃ© au LogViewer). Usage : `python3 backend/scripts/test_notification.py` (utilise `USER_ID_TARGET` du `.env` et l'email Firebase Auth associÃ© par dÃ©faut ; `--user-id`/`--email` pour surcharger).
- **Raison** : Suite au signalement "plus d'email reÃ§u, seulement des ntfy", permet de diagnostiquer directement la cause (SMTP mal configurÃ© vs identifiants Gmail rÃ©voquÃ©s) sans dÃ©pendre du hasard d'un scan qui trouve une vraie PÃ©pite.

[2026-07-09] [PRO] Fix : Logs de `notifications.py` et `analyzer.py` invisibles dans le LogViewer (mÃªme bug que le scraper) â†’ RÃ©sultat :
- **Contexte** : Signalement "plus d'email reÃ§u, seulement des ntfy". Investigation de l'historique Git de `notifications.py`/`bot.py`/`deploy.yml` â€” aucun changement de code rÃ©cent ne touche l'envoi d'email ou les identifiants SMTP, et la rÃ©solution de l'email utilisateur fonctionne (confirmÃ© par les logs). RÃ©gression probablement externe (identifiants Gmail rÃ©voquÃ©s/expirÃ©s, ou variable d'environnement serveur manquante) â€” non confirmable tant que l'erreur rÃ©elle restait invisible.
- **Cause** : `notifications.py` et `analyzer.py` loguaient via `logging.getLogger(__name__)` (loggers de module), jamais raccordÃ©s au logger par-utilisateur `bot.{user_id}` â€” mÃªme bug que celui dÃ©jÃ  corrigÃ© pour `backend/scraping/` (voir plus bas).
- **`analyzer.py`** : `DealAnalyzer.__init__` accepte un `logger` optionnel ; les 18 appels `logger.x()` de la classe basculÃ©s sur `self.logger.x()`. `bot.py` passe `logger=self.logger` aux 2 instanciations.
- **`notifications.py`** : `NtfyNotifier.send()`/`EmailNotifier.send()`/`NotificationService.notify_deal()`/`notify_model_error()` acceptent tous un paramÃ¨tre `logger` optionnel, propagÃ© depuis `bot.py` et `analyzer.py`.
- **Bonus** : `EmailNotifier.send()` logue dÃ©sormais explicitement quand l'envoi est bloquÃ© par une config SMTP manquante (avant : un seul warning au tout premier chargement du module, jamais revu ensuite â€” ratait donc silencieusement chaque tentative suivante).

[2026-07-09] [PRO] Fix : `gemini-2.5-flash` (Tier 2 â€” Analyste) n'est plus disponible chez Google (404) â†’ RÃ©sultat :
- RemplacÃ© par `gemini-3.5-flash` partout oÃ¹ codÃ© en dur : `backend/analyzer.py` (fallback runtime `config.get('mainModel', ...)` â€” probable cause directe du 404 en prod, puisque `mainModel` n'est jamais initialisÃ© dans la structure Firestore crÃ©Ã©e pour un nouvel utilisateur), `config.py::GEMINI_MODELS` (`default_analyst` + retrait de la liste `available`), `src/components/ConfigPanel.jsx` (liste de repli + valeur par dÃ©faut du `<select>`), `src/hooks/useBotConfig.js` (Ã©tat initial React ET bouton "RÃ©initialiser par dÃ©faut", qui rÃ©Ã©crivait encore le modÃ¨le mort dans Firestore).
- **Suivi requis** : comme pour l'Expert Pro en 2026-07-07, resÃ©lection manuelle du modÃ¨le Analyste dans ParamÃ¨tres â†’ IA si la config Firestore existante a dÃ©jÃ  `mainModel` enregistrÃ© Ã  l'ancienne valeur (non migrÃ©e rÃ©troactivement).

[2026-07-09] [PRO] Feature : Ne pas stocker un scraping ratÃ© + rejet automatique des annonces hors budget â†’ RÃ©sultat :
- **`bot.py::handle_deal_found()`** : garde-fou en tout dÃ©but de fonction â€” si `imageUrls` est vide ET prix Ã  0$ (scraping manifestement ratÃ©), aucune Ã©criture Firestore ni appel IA ; l'annonce reste absente de la base et sera retraitÃ©e comme nouvelle Ã  la prochaine session/scan, au lieu de figer une fiche vide comme "dÃ©jÃ  traitÃ©e".
- **Plafond de prix dÃ©fensif** : vÃ©rification de `scanConfig.max_price` cÃ´tÃ© code, indÃ©pendante du filtre de prix Facebook (observÃ© en prod : peut Ã©chouer avec `Timeout 10000ms exceeded` sur le champ de saisie, sans vÃ©rification a posteriori jusqu'ici). RÃ©utilise le verdict `BAD_DEAL` existant ("Trop Cher") plutÃ´t qu'un nouveau statut dÃ©diÃ© â€” `status` reste `analyzed`, pas `rejected`, pour ne pas confondre "hors budget" avec un vrai rejet (mot-clÃ©/IA).
- **`src/constants.js`** : `BAD_DEAL` dÃ©placÃ© de `MARKET_GROUP` vers `ARCHIVE_GROUP` â€” masquÃ© de la vue par dÃ©faut via le mÃ©canisme de filtrage existant (`matchesVerdictFilter`), toujours consultable via son propre filtre "Trop Cher" dÃ©jÃ  prÃ©sent dans le menu dÃ©roulant. Aucune nouvelle logique de statut/filtre Ã  construire.
- S'applique uniformÃ©ment Ã  `scan_marketplace()` et `scan_specific_url()` (demande explicite de l'utilisateur : pas d'exemption pour le scan manuel d'URL).
- **Raison** : Ã‰viter de figer des fiches vides comme "dÃ©jÃ  traitÃ©es" (bloquant tout nouveau scraping futur), et donner un moyen de filtrer les annonces valides mais hors budget sans les traiter comme du bruit/rejet de fond.

[2026-07-09] [PRO] Fix : Crash pipeline IA si Gemini rÃ©pond avec un tableau JSON au lieu d'un objet â†’ RÃ©sultat :
- **SymptÃ´me** : `TypeError: list indices must be integers or slices, not str` sur `result_t3["model_used"] = ...` (Tier 3 â€” Expert Pro), observÃ© en prod pendant la vÃ©rification du fix images ci-dessous â€” bloquait toute analyse tant qu'il n'Ã©tait pas corrigÃ©.
- **`backend/analyzer.py::_call_gemini_json()`** : normalise dÃ©sormais tout rÃ©sultat de type liste (`[{...}]`) en `dict` (premier Ã©lÃ©ment si c'est un dict, sinon `{}`) avant de le retourner â€” correction unique Ã  la source plutÃ´t qu'un patch sur le seul Tier touchÃ© ; protÃ¨ge aussi T1 (Portier) et T2 (Analyste), qui partagent cette mÃ©thode utilitaire et avaient la mÃªme fragilitÃ© latente.

[2026-07-09] [PRO] Fix : Logs du scraper invisibles dans le LogViewer (mauvais logger) â†’ RÃ©sultat :
- **Cause racine** : `backend/scraping/core.py`, `parser.py` et `city_finder.py` loguaient via `logging.getLogger(__name__)` (loggers de module `scraping.core`/`scraping.parser`/`scraping.city_finder`), jamais raccordÃ©s au logger par-utilisateur `bot.{user_id}` (seul logger avec un `FirestoreHandler` attachÃ©, alimentant la collection lue par `LogViewer.jsx`). Aucun log du scraper â€” y compris les diagnostics `[DIAG]` ajoutÃ©s pendant l'investigation du bug images ci-dessous â€” n'a jamais Ã©tÃ© visible dans l'app, faussant tout le diagnostic jusqu'ici.
- **`FacebookScraper.__init__`** : nouveau paramÃ¨tre optionnel `logger` (repli sur le logger de module pour scripts autonomes/tests). Les 49 appels `logger.x()` de la classe basculÃ©s sur `self.logger.x()`.
- **`ListingParser.parse_listing_card()`/`parse_details_page()`** : paramÃ¨tre `logger` optionnel ajoutÃ© et propagÃ© depuis `core.py`.
- **`city_finder.py`** : `find_city_id_and_coords()` utilise dÃ©sormais `scraper.logger` (dÃ©jÃ  reÃ§u en paramÃ¨tre) au lieu d'un logger de module â€” import `logging` devenu inutile, retirÃ©.
- **`bot.py`** : les 5 instanciations de `FacebookScraper` passent `logger=self.logger` â€” isolation multi-tenant prÃ©servÃ©e (un thread = un scraper = un logger, pas de logger global partagÃ© entre utilisateurs).
- **Raison** : Sans ce correctif, impossible de vÃ©rifier depuis l'app si les correctifs scraping (voir entrÃ©e suivante) fonctionnaient rÃ©ellement â€” la dÃ©couverte de ce bug a dÃ©bloquÃ© le reste de l'investigation.

[2026-07-09] [PRO] Fix : Fiche dÃ©tail Facebook dÃ©gradÃ©e â†’ titre/prix/images manquants sur certaines annonces (SCAN_URL) â†’ RÃ©sultat :
- **SymptÃ´me initial** : Sur l'annonce "Guitare Ã©lectrique Aria Pro 2" (Granby), seule la premiÃ¨re miniature Ã©tait rÃ©cupÃ©rÃ©e ; investigation Ã©tendue ensuite au prix (0$) et aux images (0), rapportÃ©es comme "intermittentes" (certaines annonces fonctionnent).
- **`backend/scraping/core.py`** : 1Ã¨re version (`_recover_degraded_page`) basÃ©e sur l'absence de carrousel photo interactif (`ListingParser.has_photo_carousel()`) pour dÃ©clencher un reload â€” remplacÃ©e aprÃ¨s une code review dÃ©diÃ©e par un dÃ©clencheur non ambigu : "0 image extraite aprÃ¨s parsing" (l'absence de carrousel donnait un faux positif systÃ©matique sur toute annonce Ã  une seule photo lÃ©gitime, qui n'a par nature aucun bouton "photo suivante"). Nouvelle mÃ©thode `_parse_details_with_reload_retry()`/logique dÃ©diÃ©e dans `scan_specific_url()` : rÃ©-extraction complÃ¨te (titre/prix/localisation incluses, pas seulement les images) avec comparaison avant/aprÃ¨s reload (on ne garde le reload que s'il apporte strictement plus d'images).
- **Code review dÃ©diÃ©e (`/code-review` niveau high)** : a rÃ©vÃ©lÃ© que le premier correctif (`_recover_degraded_page()`) ne revÃ©rifiait jamais si le reload avait rÃ©ellement rÃ©parÃ© la page â€” son retour n'Ã©tait que le contrÃ´le d'URL (`_is_valid_detail_page`), donc un reload sans effet Ã©tait quand mÃªme considÃ©rÃ© comme un succÃ¨s et la page toujours dÃ©gradÃ©e Ã©tait parsÃ©e comme valide. 8 autres pistes (reuse, simplification, efficacitÃ©, altitude, conventions) explorÃ©es en parallÃ¨le via sous-agents ; 2 confirmÃ©es comme critiques, corrigÃ©es dans la foulÃ©e.
- **Diagnostic enrichi** (`parser.py::parse_details_page`) : quand 0 image est retenue, logue dÃ©sormais le nombre total d'`<img>` trouvÃ©es dans `div[role='main']` (avant filtrage taille) et leurs dimensions â€” confirmÃ© en prod (une fois le bug de logging ci-dessous corrigÃ©) : `0 <img>` dans le DOM, ni avant ni aprÃ¨s reload. Ã‰carte dÃ©finitivement l'hypothÃ¨se d'un filtre `>300Ã—300px` trop strict.
- **Cause probable, non rÃ©solue** : le scraper ne s'authentifie jamais sur Facebook (aucune session/cookies persistants dans tout le backend, vÃ©rifiÃ©). Facebook semble parfois (comportement confirmÃ© intermittent par l'utilisateur) servir une version limitÃ©e de la fiche dÃ©tail aux sessions anonymes â€” titre/description (balises `og:*`) disponibles, prix et carrousel photo absents du DOM. DÃ©cision produit Ã  trancher : accepter la limitation (couverte par le garde-fou "scraping ratÃ©" ci-dessus) ou implÃ©menter une session Facebook authentifiÃ©e (risque de bannissement du compte selon les CGU FB, gestion sÃ©curisÃ©e des secrets) â€” voir `TODO.md`.
- **Raison** : Plusieurs itÃ©rations ont Ã©tÃ© nÃ©cessaires car chaque diagnostic partiel masquait la cause suivante â€” le vrai verrou a Ã©tÃ© le bug de logging (entrÃ©e suivante), qui empÃªchait toute observation rÃ©elle du comportement en prod jusqu'Ã  sa correction.

[2026-07-07] [PRO] Fix : Job `deploy-frontend` rejetÃ© par Git (`gh-pages` non fast-forward) â†’ RÃ©sultat :
- **SymptÃ´me** : `git push origin gh-pages` Ã©choue dans le job CI avec `! [rejected] gh-pages -> gh-pages (fetch first)`.
- **Cause** : Des dÃ©ploiements manuels (`npm run deploy`) faits en parallÃ¨le pendant la session ont fait diverger la branche `gh-pages` de l'Ã©tat attendu par le job CI, dont le `git push` normal n'est pas `--force`.
- **`.github/workflows/deploy.yml`** : Ajout de `force_orphan: true` sur l'Ã©tape `peaceiris/actions-gh-pages@v4` â€” republie systÃ©matiquement un commit unique et propre sur `gh-pages`, sans jamais dÃ©pendre ni tenir compte de son Ã©tat prÃ©cÃ©dent (adaptÃ© Ã  une branche de build, sans historique utile Ã  prÃ©server).
- **Raison** : `gh-pages` ne contient que des artefacts de build ; `force_orphan` est le pattern recommandÃ© pour ce cas prÃ©cis et rend le dÃ©ploiement CI totalement insensible Ã  d'Ã©ventuels dÃ©ploiements manuels intercalÃ©s.

[2026-07-07] [PRO] Feature : Mise Ã  jour des modÃ¨les Gemini + commentaire personnalisÃ© sur rÃ©analyse + alerte modÃ¨le indisponible â†’ RÃ©sultat :
- **`config.py`** : `GEMINI_MODELS["available"]` nettoyÃ© (retrait de `gemini-1.5-flash`/`gemini-1.5-pro`, gÃ©nÃ©ration obsolÃ¨te). Ajout de `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3.1-pro-preview`. `default_expert` (Tier 3 â€” contre-analyses) â†’ `gemini-3.1-pro-preview` (choix utilisateur : prÃ©fÃ©rÃ© Ã  `gemini-3.5-flash` malgrÃ© son statut Preview, jugement qualitÃ© > stabilitÃ©).
- **`src/components/ConfigPanel.jsx`** : Liste de repli alignÃ©e sur `config.py`.
- **Important** : La config Firestore d'un utilisateur existant n'est Ã©crite qu'une fois Ã  la crÃ©ation du compte (`ensure_initial_structure` prÃ©serve les docs existants) â€” le nouveau dÃ©faut ne s'applique pas rÃ©troactivement, resÃ©lection manuelle requise dans le panneau IA.
- **`backend/analyzer.py`** : `analyze_deal()` accepte `user_comment` (injectÃ© en prioritÃ© dans le prompt de base, ex: "Tu as identifiÃ© une PRS mais c'est une GWD") et `user_email` (pour l'alerte modÃ¨le indisponible ci-dessous).
- **`backend/bot.py`** : `analyze_single_deal(payload)` lit `payload['userComment']` ; `user_email` transmis aux 3 points d'appel de `analyze_deal`.
- **`src/services/firestoreService.js`**, **`useDealsManager.js`**, **`Dashboard.jsx`** : `userComment` relayÃ© de bout en bout jusqu'Ã  la commande Firestore `ANALYZE_DEAL`.
- **`src/components/DealCard.jsx`** : Nouvelle option "Avec commentaire..." dans les deux dropdowns "RÃ©-analyser" (carte + modale â€” code dupliquÃ© existant, non refactorisÃ©), ouvrant une modale dÃ©diÃ©e (textarea) qui lance une rÃ©analyse Expert avec le commentaire inclus.
- **`backend/notifications.py`** : Nouvelle fonction `notify_model_error(model_name, error, user_email)` (email + ntfy).
- **`backend/analyzer.py`** : `_call_gemini_json` dÃ©tecte les erreurs "modÃ¨le introuvable" (404/not found/not supported) et dÃ©clenche l'alerte, throttlÃ©e Ã  1Ã—/24h par modÃ¨le (`self._model_error_last_notified`).
- **DÃ©couverte technique** : Le SDK Python `google.generativeai` (utilisÃ© par `analyzer.py`) Ã©met dÃ©sormais un `FutureWarning` explicite â€” support totalement terminÃ©, remplacÃ© par `google-genai`. Migration non faite ici (hors pÃ©rimÃ¨tre, refactor plus large), Ã  planifier sÃ©parÃ©ment.
- **Raison** : Le Portier/Analyste (Tier 1/2) restent sur leurs modÃ¨les 2.5 actuels (stables, non concernÃ©s par la demande) ; seul l'Expert Pro (contre-analyses) a Ã©tÃ© mis Ã  jour vers le modÃ¨le jugÃ© le plus puissant.

[2026-07-07] [PRO] Incident : Site en panne suite Ã  l'automatisation du dÃ©ploiement frontend (`TypeError onAuthStateChanged`) â†’ RÃ©sultat :
- **SymptÃ´me** : AprÃ¨s le premier push dÃ©clenchant le nouveau job `deploy-frontend`, le site entier plantait sur tous les appareils avec `TypeError: Cannot read properties of undefined (reading 'onAuthStateChanged')`.
- **Cause** : `src/services/firebase.js` lit `import.meta.env.VITE_FIREBASE_*`, injectÃ©es au build depuis `.env` (fichier local, non versionnÃ©). Le job CI `deploy-frontend` buildait sans ce fichier â†’ `firebaseConfig` entiÃ¨rement `undefined` â†’ `initializeApp()` Ã©choue (catchÃ©, juste loggÃ©) â†’ `auth` reste `undefined` â†’ premier appel `auth.onAuthStateChanged(...)` plante.
- **RÃ©paration immÃ©diate** : `npm run deploy` relancÃ© manuellement en local (avec le vrai `.env`) pour restaurer le site.
- **Correctif permanent (`.github/workflows/deploy.yml`)** : Ajout d'une Ã©tape "Create .env file" dans `deploy-frontend`, Ã©crivant `secrets.DOT_ENV` avant `npm run build` â€” mÃªme mÃ©canisme dÃ©jÃ  utilisÃ© par le job backend. Ã‰chec explicite (`exit 1`) si le secret est absent, plutÃ´t qu'un build silencieusement cassÃ©.
- **Raison** : Le job frontend ajoutÃ© la veille n'avait pas repris l'injection de secrets dÃ©jÃ  en place cÃ´tÃ© backend â€” angle mort dÃ©couvert seulement une fois le dÃ©ploiement automatique rÃ©ellement dÃ©clenchÃ© en production.

[2026-07-07] [PRO] Fix : Viewport mobile fixe (475px) au lieu de device-width â†’ RÃ©sultat :
- **`index.html`** : `<meta name="viewport" content="width=device-width, initial-scale=1.0">` â†’ `<meta name="viewport" content="width=475">`. Sans effet sur desktop (balise ignorÃ©e hors navigateurs mobiles).
- **MÃ©canisme** : Au lieu de forcer un mappage 1:1 CSS/Ã©cran (`device-width`) et de devoir cacher des Ã©lÃ©ments du `Navbar` pour tenir dans ~375px, le viewport logique est fixÃ© Ã  475px â€” le navigateur mobile calcule alors automatiquement un zoom (`visualViewport.scale` â‰ˆ 0.79 sur un Ã©cran de 375px) pour l'adapter Ã  l'Ã©cran rÃ©el. Rien n'est plus cachÃ© ni coupÃ©, juste rendu proportionnellement plus petit.
- **VÃ©rifiÃ©** : `document.documentElement.clientWidth` = 475, `scrollWidth` = `clientWidth` partout (nav compris) â†’ zÃ©ro dÃ©bordement. Les 4 boutons du Navbar (Filtres, Aide, ParamÃ¨tres, DÃ©connexion) restent tous visibles et cliquables. TestÃ© via Ã©mulateur mobile (Chrome DevTools respecte la balise viewport comme un vrai appareil) â€” confirmation sur tÃ©lÃ©phone rÃ©el en attente.
- **Raison** : L'utilisateur a proposÃ© cette approche aprÃ¨s avoir constatÃ© que le fix prÃ©cÃ©dent (masquer des boutons sous 640px) rÃ©glait le dÃ©bordement mais rendait l'interface "trop petite"/cramped ; fixer un viewport logique plus large et laisser le navigateur zoomer automatiquement est plus simple et n'oblige Ã  cacher aucune fonctionnalitÃ©.

[2026-07-07] [PRO] Automatisation du dÃ©ploiement frontend (GitHub Pages) â†’ RÃ©sultat :
- **DÃ©couverte** : Le fix mobile de la veille testÃ© sur le site en ligne (`ludoviclebart.github.io`) ne montrait aucun changement. Cause : le dÃ©ploiement frontend Ã©tait **manuel** (`npm run deploy`) et n'avait pas Ã©tÃ© refait depuis le **2026-05-06** â€” 2 mois de retard, indÃ©pendant du CI backend (qui ne dÃ©ploie que le service Python via SSH).
- **Action immÃ©diate** : `npm run deploy` exÃ©cutÃ© manuellement pour publier la version Ã  jour (commit `6acd749` sur `gh-pages`).
- **`.github/workflows/deploy.yml`** : Nouveau job `deploy-frontend`, indÃ©pendant et parallÃ¨le au job backend existant, dÃ©clenchÃ© sur les mÃªmes branches (`master`, `dev`). `npm ci` â†’ `npm run build` â†’ publication de `dist/` sur `gh-pages` via `peaceiris/actions-gh-pages@v4` (`GITHUB_TOKEN` intÃ©grÃ©, pas de nouveau secret).
- **PrÃ©requis** : Repo GitHub â†’ Settings â†’ Actions â†’ General â†’ "Workflow permissions" sur "Read and write permissions", sinon le push vers `gh-pages` Ã©choue malgrÃ© le `permissions: contents: write` du job.
- **Raison** : Le dÃ©ploiement manuel avait permis un dÃ©calage de 2 mois entre le code et le site en ligne sans que Ã§a se remarque â€” source du "Ã§a n'a pas marchÃ©" alors que le correctif mobile Ã©tait dÃ©jÃ  en place dans le code.

[2026-07-06] [PRO] Fix : DÃ©bordement horizontal en mode mobile (Dashboard) â†’ RÃ©sultat :
- **`index.css`** : Ajout de `overflow-x: hidden` sur `html, body, #root` â€” filet de sÃ©curitÃ© empÃªchant tout Ã©lÃ©ment fautif de crÃ©er un scroll horizontal.
- **`src/components/Dashboard.jsx`** (`VerdictDropdown`) : Le conteneur du bouton avait `relative shrink-0` (largeur indÃ©finie) avec un enfant `w-full` â€” cas ambigu en CSS. RemplacÃ© par `flex-1 sm:flex-none min-w-0` sur le conteneur, avec troncature propre (`truncate`) du libellÃ© au lieu de dÃ©pendre du `w-full`.
- **`src/components/Dashboard.jsx`** (barre Recherche & Actions, lignes ~372-413) : Les deux groupes de boutons (Statut/Favoris, Vue/Compteur/Croix) tenaient sur une seule ligne en mobile (`flex-row justify-between`), ce qui Ã©crasait la croix "Effacer les filtres". Passage Ã  `flex-col sm:flex-row` pour empiler les deux groupes sous 640px.
- **`src/components/Dashboard.jsx`** et **`src/components/Navbar.jsx`** : Les deux menus dÃ©roulants en `position: absolute` (filtre Statut, menu hover du bot) n'avaient aucune limite de largeur liÃ©e au viewport â€” mÃªme invisibles, ils pouvaient dÃ©passer l'Ã©cran et gonfler la largeur scrollable de la page. Ajout de `max-w-[calc(100vw-2rem)]`.
- **VÃ©rifiÃ©** : build Vite propre, page de connexion testÃ©e en viewport mobile (375px) â€” `document.documentElement.scrollWidth === window.innerWidth`, aucune erreur console. Le rendu du Dashboard authentifiÃ© reste Ã  confirmer par l'utilisateur (mur d'authentification, pas de session de test disponible).
- **Raison** : Aucune contention `overflow-x` n'existait nulle part dans l'app â€” la page se dimensionnait sur l'Ã©lÃ©ment le plus large (carte, dropdown, menu cachÃ©) plutÃ´t que sur la largeur de l'Ã©cran, donnant l'impression d'une page "Ã  plat" sans conteneur englobant.

[2026-07-06] [PRO] Feature : Double appartenance "PÃ©pite" + fix critique notifications â†’ RÃ©sultat :
- **Bug critique corrigÃ© (`backend/notifications.py`)** : `notify_deal()` rÃ©fÃ©renÃ§ait `HIGH_PRIORITY_VERDICTS` (variable commentÃ©e) et `profit` (jamais dÃ©fini dans cette fonction) â†’ `NameError` systÃ©matique Ã  chaque PÃ©pite trouvÃ©e. Comme `bot.py::run_scan()` n'a pas de `except` sur sa boucle des villes (seulement un `finally`), ce crash interrompait le scan des villes restantes dÃ¨s qu'une PÃ©pite Ã©tait dÃ©tectÃ©e. `HIGH_PRIORITY_VERDICTS` rÃ©activÃ©, `profit` recalculÃ© localement.
- **`prompts.json`** (`main_analysis_prompt`) : Nouveau champ IA `also_qualifies_pepite` (boolÃ©en). L'IA le met Ã  `true` quand le verdict principal est `FAST_FLIP`/`LUTHIER_PROJ`/`CASE_WIN`/`COLLECTION` ET que les critÃ¨res PÃ©pite sont aussi remplis (Marge > 100% et > 150$ OU Marge > 30% et modÃ¨le iconique).
- **`backend/notifications.py`** : `notify_deal()` dÃ©clenche aussi la notification (prioritÃ© haute) quand `also_qualifies_pepite` est vrai, mÃªme si le verdict principal n'est pas `PEPITE`. Sujet/corps mentionnent "(Aussi PÃ©pite â­�)".
- **`src/hooks/useDealsManager.js`** : `matchesVerdictFilter` fait apparaÃ®tre ces annonces aussi dans le filtre "PÃ©pites" ; `verdictCounts` les compte aussi dans ce compteur (sans dupliquer le total `ALL`).
- **`src/components/DealCard.jsx`** : Badge secondaire "ðŸ’Ž Aussi PÃ©pite" affichÃ© Ã  cÃ´tÃ© du badge du verdict principal (carte + modale).
- **Bug annexe corrigÃ© (`backend/notifications.py`)** : `NtfyNotifier.send()` plantait silencieusement (`UnicodeEncodeError`, catchÃ©e) sur les titres contenant Ã©mojis/accents â€” headers HTTP en Latin-1 uniquement. CorrigÃ© via encodage RFC 2047 (`email.header.Header`, `maxlinelen=998` pour Ã©viter le repliement multi-ligne invalide en HTTP), conformÃ©ment Ã  la documentation officielle ntfy.sh.
- **Raison** : Un projet de lutherie ou un case win peut Ãªtre *aussi* exceptionnellement rentable ; le figer dans une seule catÃ©gorie le rendait invisible du filtre/notifications "PÃ©pites". Le bug de notification dÃ©couvert au passage minait directement l'objectif du bot (scan interrompu Ã  chaque vraie trouvaille).

[2026-07-06] [PRO] Doc : Migration de `docs/` vers la structure Diataxis â†’ RÃ©sultat :
- **RÃ©organisation** (`git mv`, historique prÃ©servÃ©) : `docs/management/` (`JOURNAL.md`, `TODO.md`, `plans/MULTI_USER_PLAN.md`), `docs/reference/` (`ARCHITECTURE.md`, `DATA_FLOW.md`, `STATE_MODELS.md`, `UI_UX_ANALYSIS.md`), `docs/explanation/` (`PROJECT_OVERVIEW.md`, `STATS_REFLEXION.md`).
- **`CLAUDE.md`** : Ã‰tape 3 et tableau "Fichiers ClÃ©s" mis Ã  jour vers les nouveaux chemins ; correction de la rÃ©fÃ©rence erronÃ©e `backend/main.py` â†’ `main.py` (racine, vrai point d'entrÃ©e).
- **`AI_BRIEFING.md`** : Chemins de l'Ã‰tape 3 alignÃ©s sur la nouvelle arborescence.
- **`docs/management/TODO.md`** : Lien relatif vers `STATS_REFLEXION.md` corrigÃ© (`../explanation/STATS_REFLEXION.md`).
- **Skill partagÃ© `~/.claude/skills/document/SKILL.md`** : GÃ©nÃ©ralisÃ© â€” ne rÃ©fÃ©rence plus une convention figÃ©e (ex-MoneyBot) ; lit dÃ©sormais le `CLAUDE.md`/`AGENTS.md` du projet courant pour suivre sa convention documentaire exacte, avec repli heuristique (Diataxis ou fichiers plats) si rien n'est prÃ©cisÃ©.
- **Raison** : Le skill `/document` appliquait par erreur la convention Diataxis propre Ã  MoneyBot lors d'une session Guitar Hunter (qui Ã©tait encore Ã  plat). Aligner Guitar Hunter sur Diataxis et rendre le skill gÃ©nÃ©rique Ã©vite ce dÃ©calage pour tous les projets.

[2026-07-06] [PRO] Fix : Images sans rapport (vÃ©hicules, bateaux...) dans les annonces â†’ RÃ©sultat :
- **`backend/scraping/parser.py`** : `ListingParser.parse_details_page()` accepte dÃ©sormais un paramÃ¨tre `fb_id` et exclut du rÃ©sultat toute image entourÃ©e d'un lien `<a href="/marketplace/item/{AUTRE_ID}/...">` â€” ces vignettes appartiennent au bloc "Suggestions" que Facebook affiche systÃ©matiquement sous la description de l'annonce, pas aux vraies photos du produit.
- **`backend/scraping/core.py`** : Ajout de `_is_valid_detail_page()` (garde-fou dÃ©tectant une redirection vers `/login`, un captcha, ou une URL ne correspondant plus Ã  l'annonce ciblÃ©e) utilisÃ© dans `scan_marketplace()` et `scan_specific_url()` avant l'extraction des dÃ©tails ; log `debug` temporaire de l'URL de la fiche dÃ©tail chargÃ©e (`[DIAG]`) conservÃ© pour un diagnostic futur.
- **`backend/scraping/test_core.py`** (nouveau) : 4 tests unitaires couvrant `_is_valid_detail_page` (page valide, redirection feed, redirection login, ID diffÃ©rent).
- **Diagnostic rÃ©el** : reproduit sur une annonce publique (`.../marketplace/item/1680540959879684/`) â€” 19 images extraites avant correctif (16 Ã©taient des suggestions d'autres annonces : voiture, bateau, meubles...) contre 3 aprÃ¨s correctif (toutes les vraies photos du produit).
- **Raison** : Le filtre initial se basait uniquement sur la taille de l'image (>300Ã—300px) et le domaine CDN (`scontent`), ce qui capturait aussi les vignettes du bloc "Suggestions" â€” visible surtout sur les annonces ayant peu de vraies photos (le plafond de collecte n'Ã©tant alors pas atteint par les vraies photos seules).

[2026-07-05] [PRO] Feature : Partage d'annonce sans authentification â†’ RÃ©sultat :
- **`firebase/firestore.rules`** : Ajout d'une rÃ¨gle de lecture publique sur la collection `shared_deals/{dealId}`. Ã‰criture rÃ©servÃ©e aux utilisateurs authentifiÃ©s.
- **`firebase.json`** : Correction d'un espace parasite dans le chemin des rÃ¨gles Firestore (empÃªchait `firebase deploy --only firestore:rules`).
- **`src/services/firestoreService.js`** : Ajout de `createSharedDeal(deal)` (snapshot public dans `shared_deals/`) et `getSharedDeal(dealId)` (lecture sans auth).
- **`src/components/DealCard.jsx`** : `handleShare` Ã©crit d'abord le snapshot dans Firestore, puis gÃ©nÃ¨re un lien `?shareId={deal.id}` au lieu de `?dealId=`.
- **`src/components/SharedDealPage.jsx`** : Nouveau composant public affichant titre, prix, localisation, images, scores IA, analyse et lien FB â€” sans login requis.
- **`src/App.jsx`** : DÃ©tection de `?shareId=` avant le mur d'auth â†’ rendu de `SharedDealPage` directement.
- **Raison** : Un destinataire qui reÃ§oit un lien partagÃ© ne doit pas Ãªtre forcÃ© Ã  crÃ©er un compte pour consulter l'annonce.

[2026-05-06] [PRO] Refonte Aide UX & Robustesse Internationale â†’ RÃ©sultat :
- **`src/components/HelpOverlay.jsx`** : Refonte totale du guide de prise en main. Transition vers un guide technique en 4 Ã©tapes (Cibles, Vigilance, Lancement, Analyse) avec explications prÃ©cises sur le "Rayon 0" (Recherche Stricte) et la frÃ©quence de scan. Isolation des rÃ©glages IA dans une section "Expertise AvancÃ©e".
- **`src/components/ConfigPanel.jsx`** : Ajout d'un bouton **"Lancer le Scan"** direct pour dÃ©clencher la recherche aprÃ¨s configuration. Simplification radicale de l'ajout de villes : suppression du formulaire secondaire, l'ajout se fait dÃ©sormais directement via le bouton "+" du champ de recherche principal.
- **`backend/bot.py`** : Correction d'une `NameError` critique (`city_coords`) lors de l'ajout automatique de ville.
- **`backend/scraping/city_finder.py`** : Hardening de la recherche de villes Facebook. Support des versions internationales (Lieu/Location/Lugar), dÃ©tection des alias d'URL (non-numÃ©riques), et nettoyage forcÃ© du champ de recherche (`Ctrl+A -> Backspace`).
- **Raison** : AmÃ©liorer l'onboarding utilisateur, clarifier les paramÃ¨tres vitaux de scan et assurer que le bot peut s'exporter sur n'importe quel marchÃ© (Bordeaux, Paris, etc.) sans friction technique.


[2026-05-06] [PRO] Robustesse Auth & Scraping: Fix duplication et sÃ©curisation sessions â†’ RÃ©sultat :
- **`src/hooks/useAuth.js`** : Centralisation de l'onboarding via `ensureUserDoc` (DRY). Propagation des erreurs Firestore vers l'UI dans `onAuthStateChanged` (Status Warning).
- **`backend/scraping/core.py`** : SÃ©curisation du `finally` (fix `page` non-dÃ©finie) et clarification du pÃ©rimÃ¨tre de `get_city_id_and_coords` (gÃ©ocodage dÃ©lÃ©guÃ© Ã  Nominatim).
- **Raison** : Ã‰liminer la dette technique de duplication et amÃ©liorer le feedback utilisateur en cas d'erreur de permissions Firestore.

[2026-05-06] [PRO] Correctifs VisibilitÃ© UI & GÃ©o-localisation Paris â†’ RÃ©sultat :
- **`src/components/Navbar.jsx`** : AmÃ©lioration de la visibilitÃ© du bouton d'aide (ajout du label "Aide" sur Desktop et augmentation du contraste).
- **`src/components/Dashboard.jsx`** : ImplÃ©mentation d'un bandeau d'erreur global et correction d'une `ReferenceError` (contexte mal dÃ©structurÃ©).
- **`backend/bot.py` & `core.py`** : Fiabilisation de l'ajout de ville. PrioritÃ© aux coordonnÃ©es extraites de Facebook et Ã©largissement de la recherche Nominatim pour supporter **n'importe quelle ville dans le monde** (suppression des restrictions rÃ©gionales). ImplÃ©mentation du scraping automatisÃ© de l'ID de ville Facebook via le sÃ©lecteur de lieu.
- **`src/components/MapView.jsx`** : Correction de l'interaction avec les InfoWindows (suppression du `mouseout` agressif) et restauration/styling du bouton de fermeture.
- **`src/components/ConfigPanel.jsx`** : Ajout de consignes textuelles pour guider l'utilisateur dans l'ajout de nouvelles villes.
- **Raison** : RÃ©soudre les points de friction utilisateur et assurer la stabilitÃ© de l'interface aprÃ¨s l'ajout des nouveaux mÃ©canismes de feedback.

[2026-05-05] [FLASH] IntÃ©gration de la Documentation Utilisateur â†’ RÃ©sultat :
- **`src/components/HelpOverlay.jsx`** : CrÃ©ation d'un guide interactif premium dÃ©taillant le Radar IA (scores Gemini), les Verdicts (badges), les Commandes (Refresh/Cleanup) et les Notifications (Email/Ntfy).
- **`src/components/Navbar.jsx`** : Ajout du bouton d'aide (`HelpCircle`) Ã  cÃ´tÃ© des paramÃ¨tres.
- **`src/components/Dashboard.jsx`** : Gestion de l'Ã©tat d'affichage de l'aide et rendu de l'overlay.
- **Raison** : AmÃ©liorer l'autonomie de l'utilisateur final et clarifier les fonctionnalitÃ©s de l'IA et du systÃ¨me d'alertes.

[2026-05-05] [PRO] Audit multi-tenant & correctifs onboarding â†’ RÃ©sultat :
- **`src/hooks/useAuth.js`** : Initialisation automatique du document utilisateur Firestore lors du `signUp` ET du `onAuthStateChanged` (session persistante), garantissant que le backend dÃ©couvre tout utilisateur actif mÃªme s'il existait dÃ©jÃ .
- **`backend/bot.py`** : Assouplissement du gÃ©ocodage Nominatim (suppression de la restriction stricte Canada) permettant l'ajout de villes internationales comme Paris.
- **`main.py`** : 
    - **Watchdog** : Correction d'un bug critique oÃ¹ le `firestore_handler` n'Ã©tait pas recrÃ©Ã© lors d'un redÃ©marrage de thread, coupant les logs.
    - **Performance** : Passage de la commande `ADD_CITY` en asynchrone pour ne plus geler le bot pendant le scraping/gÃ©ocodage.
    - **HygiÃ¨ne** : ImplÃ©mentation du nettoyage automatique des bots pour les utilisateurs supprimÃ©s de Firestore.
- **`src/components/Navbar.jsx`** : Ajout d'un tooltip sur le point de statut "Auth" pour afficher les messages d'erreur (ex: "Dossier Python introuvable").
- **`src/components/LogViewer.jsx`** : Correction de l'envoi de l'UID lors de la suppression des logs.

[2026-05-05] [PRO] Onboarding Dynamique & Isolation du Logging â†’ RÃ©sultat :
- **`main.py`** : ImplÃ©mentation de `discover_users` (scan cyclique toutes les 30s) et `start_user_bot`. Transition d'une liste statique vers un mode multi-tenant rÃ©actif.
- **`backend/logging_config.py`** : Isolation du logging par utilisateur. Les logs de chaque bot sont dÃ©sormais dirigÃ©s vers leur propre collection Firestore (`bot.XXXX`) sans interfÃ©rer avec le logger racine ou les autres utilisateurs.
- **Watchdog** : Surveillance active des threads par UID. RedÃ©marrage automatique en cas de crash.
- **Raison** : Permettre l'ajout de nouveaux utilisateurs Ã  chaud sans redÃ©marrage serveur et garantir l'Ã©tanchÃ©itÃ© des logs en production.

[2026-05-05] [PRO] Restauration des fonctionnalitÃ©s d'authentification Frontend â†’ RÃ©sultat :
- **`src/hooks/useAuth.js`** : RÃ©implÃ©mentation de `signUp` (createUserWithEmailAndPassword) et `resetPassword` (sendPasswordResetEmail).
- **`src/components/LoginPage.jsx`** : Refonte de l'interface pour inclure les modes Inscription et RÃ©initialisation de mot de passe, avec gestion des messages de succÃ¨s et d'erreur.
- **Raison** : Correction de la disparition des boutons suite Ã  une sÃ©curisation trop stricte (Task 1.2) et perte d'accÃ¨s utilisateur.

[2026-04-10] [PRO] Ajout des notifications email par utilisateur (SMTP Gmail) â†’ RÃ©sultat :
- Task 1.4 : `firestoreService.js:migrateOldDataToNewUser` â†’ Email admin â†’ `VITE_ADMIN_EMAIL` env var, flag `migrationDone`, try/catch granulaire par Ã©tape (config âœ… / villes âœ… / annonces âœ…).

**PHASE 2 â€” Robustesse Backend [6 Tasks]**
- Task 2.1 : `main.py` â†’ `try/except` autour de `GuitarHunterBot()` pour chaque user. Ã‰checs isolÃ©s par user sans crash global.
- Task 2.2 : `main.py` â†’ Boucle watchdog `while True` (30s interval) redÃ©marre threads morts. Capteur de crashes `t.is_alive()`.
- Task 2.3 : `bot.py` + `main.py` â†’ `threading.Semaphore(MAX_CONCURRENT_BROWSERS)` partagÃ©. Chaque `FacebookScraper` acquis/libÃ©rÃ©. Limite navigateurs simultanÃ©s.
- Task 2.4 : `main.py` â†’ `threading.Lock()` sur `in_flight_command_ids`, `.discard()` au lieu de `.remove()` pour Ã©viter `KeyError`.
- Task 2.5 : `bot.py` â†’ `session_processed_ids` â†’ `@property` sur `threading.local()`. IsolÃ© par thread, `.clear()` au lieu de `= set()`.
- Task 2.6 : `bot.py` â†’ Logger par user `logging.getLogger(f"bot.{user_id[:8]}")`, tous les `logger.` remplacÃ©s par `self.logger.`.

**Code Review â€” 3 Rondes validÃ©es**
- Ronde 1 (Exactitude) : 1 bug Firestore rules trouvÃ© et corrigÃ© (document parent).
- Ronde 2 (CohÃ©rence) : ChaÃ®ne useAuth â†’ AuthContext â†’ LoginPage OK. SÃ©maphore propagÃ© correctement.
- Ronde 3 (Edge Cases) : Acceptables. Watchdog sans backoff reste backlog.

**Variables d'Environnement Ã  ajouter**
```
VITE_ADMIN_EMAIL=ton@email.com
MAX_CONCURRENT_BROWSERS=3
```

[2026-03-21] [PRO] Action : Raffinement Login & Data Migration V2 â†’ RÃ©sultat : (1) **Frontend** : Ajout du mode Inscription (`signUp`) dans `LoginPage.jsx` avec autocomplÃ©tion pour gestionnaires de mots de passe. (2) **Migration** : ImplÃ©mentation de `migrateOldDataToNewUser` dans `firestoreService.js` pour copier automatiquement les donnÃ©es de l'ID historique vers le compte `ludovic.lebart@gmail.com` lors de sa premiÃ¨re connexion (si profil vide). (3) **SÃ©curitÃ©** : Isolation stricte garantie par `getRefs(userId)`.

[2026-03-21] [PRO] Action : ImplÃ©mentation du systÃ¨me Multi-Utilisateurs â†’ RÃ©sultat : (1) **Backend** : `config.py` supporte `USER_IDS_TARGET` (liste d'UIDs sÃ©parÃ©s par virgule, rÃ©trocompatible `USER_ID_TARGET`). `bot.py` reÃ§oit `app_id` et `user_id` comme paramÃ¨tres explicites. `main.py` lance un thread `main_loop` indÃ©pendant par utilisateur. (2) **Frontend** : `useAuth.js` migrÃ© vers Firebase Auth email/password. `AuthContext.jsx` et `LoginPage.jsx` crÃ©Ã©s. `firestoreService.js` dynamisÃ© via `getRefs(userId)`. Tous les hooks propagent `user.uid`. `App.jsx` affiche `LoginPage` si non connectÃ©. (3) Build Vite validÃ© (exit code 0).


[2026-03-05] [PRO] Action : Fiabilisation des comparaisons de prix et anti-spam Ntfy â†’ RÃ©sultat : (1) CrÃ©ation d'une fonction `_normalize_price` dans `bot.py` pour comparer sereinement les prix (ex: "150$" vs " 150.0") et Ã©viter les fausses "mises Ã  jour". (2) ImplÃ©mentation d'un filtre dans `notifications.py` (`notify_deal`) pour ne dÃ©clencher une alerte de "Baisse de Prix" que si la baisse est de plus de 5% ou de plus de 50$.

[2026-03-05] [PRO] Action : DÃ©tection et intÃ©gration visuelle des Baisses de Prix â†’ RÃ©sultat : (1) Backend (`bot.py`, `repository.py`) mis Ã  jour pour Ã©craser le prix Firestore et conserver l'ancien prix (`original_price`) lors d'une baisse. (2) Les annonces subissant une baisse repassent dÃ©sormais au travers du pipeline de l'IA avec le nouveau prix. (3) Frontend (`DealCard.jsx`) mis Ã  jour pour afficher un badge vert vif Â« Baisse -XX$ Â» si le prix a chutÃ©, visible sur la miniature et dans la modale IA.

[2026-03-05] [PRO] Action : ImplÃ©mentation complÃ¨te de la sÃ©lection 3-Tiers et correction Gemini 2.5 Pro â†’ RÃ©sultat : (1) Correction du bug oÃ¹ l'Expert Pro Ã©tait Ã©crasÃ© vers Flash Ã  cause d'une omission dans l'UI. (2) Ajout du modÃ¨le `gemini-2.5-pro` Ã  la liste des modÃ¨les disponibles dans l'interface. (3) Ajout d'un 3Ã¨me menu dÃ©roulant dans le `ConfigPanel` pour configurer le modÃ¨le de l'Analyste (Tier 2 - `mainModel`) de maniÃ¨re indÃ©pendante du Portier (Tier 1) et de l'Expert (Tier 3). (4) Mise Ã  jour du hook `useBotConfig.js` pour gÃ©rer les 3 modÃ¨les avec les bonnes valeurs par dÃ©faut du backend.

[2026-02-28] [PRO] Action : ImplÃ©mentation de la redirection par `dealId` et amÃ©lioration du partage â†’ RÃ©sultat : (1) Le composant `Dashboard.jsx` lit dÃ©sormais le paramÃ¨tre `dealId` de l'URL au chargement, sÃ©lectionne l'annonce correspondante et force l'affichage en mode "Carte" (`MapView`). (2) Le bouton de partage dans `DealCard.jsx` gÃ©nÃ¨re un lien vers l'application avec le `dealId` de l'annonce, permettant un partage direct et une ouverture de la modale de dÃ©tail. (3) La logique de sÃ©lection de l'annonce depuis l'URL a Ã©tÃ© dÃ©placÃ©e de `useDealsManager.js` vers `Dashboard.jsx` pour une meilleure gestion de l'Ã©tat de l'interface.


[2024-07-30] [PRO] Action : ImplÃ©mentation d'une stratÃ©gie de rotation d'IP (Proxies) â†’ RÃ©sultat : (1) Ajout d'une liste `PROXIES` dans `config.py` pour centraliser la configuration. (2) Modification de `FacebookScraper` (`backend/scraping/core.py`) pour sÃ©lectionner alÃ©atoirement un proxy de la liste Ã  chaque instanciation d'un navigateur Playwright. (3) La rotation est effective car le bot instancie un scraper temporaire pour chaque tÃ¢che, garantissant une nouvelle IP pour chaque scan de ville ou action manuelle.

[2024-07-30] [FLASH] Action : Analyse du diagnostic de dÃ©tection du scraper par Facebook â†’ RÃ©sultat : Le diagnostic est validÃ©. Le projet a dÃ©jÃ  implÃ©mentÃ© la plupart des contre-mesures (session persistante, randomisation User-Agent/Viewport, jitter, intÃ©gration du tÃ©lÃ©chargement d'images, flags Playwright furtifs) documentÃ©es dans les Sessions 35 et 29. Une stratÃ©gie de rotation d'IP reste une amÃ©lioration potentielle.

[2026-02-27] [FLASH] Action : Optimisation Mobile du LogViewer â†’ RÃ©sultat : ForÃ§age de l'affichage en plein Ã©cran (`inset-0`, `rounded-none`) sur les petits Ã©crans pour Ã©viter la perte de visibilitÃ© de la console. Le comportement flottant est conservÃ© pour les Ã©crans larges (`sm:`).

[2026-02-27] [FLASH] Action : Correction de la lisibilitÃ© de la console (LogViewer) et du ConfigPanel â†’ RÃ©sultat : Passage d'un fond semi-transparent (`bg-slate-900/95`) Ã  un fond totalement opaque (`bg-slate-950`). Suppression du `backdrop-blur` qui causait des interfÃ©rences visuelles lors de la superposition sur des images ou des cartes.

[2026-02-27] [FLASH] Action : Correction du blocage du scroll sur mobile â†’ RÃ©sultat : Suppression des contraintes `min-height: 100%` et `overflow-x: hidden` sur les Ã©lÃ©ments racines dans `index.css`, `App.jsx` et `Dashboard.jsx`. Le dÃ©filement vertical natif et le geste de rafraÃ®chissement ("pull-to-refresh") sont dÃ©sormais fonctionnels sur mobile.

[2026-02-26] [FLASH] Action : Restauration du Bouton de Partage â†’ RÃ©sultat : Ajout de l'icÃ´ne `Share2` et de la fonction `handleShare` dans `DealCard.jsx`. Le bouton supporte dÃ©sormais le partage natif (API `navigator.share`) et la copie automatique dans le presse-papier avec confirmation visuelle ("Lien copiÃ© !") en cas de fallback.

[2026-02-26] [FLASH] Action : Correction Critique du Scroll â†’ RÃ©sultat : Restauration du dÃ©filement vertical en supprimant `overflow: hidden` de `index.css`. Ajout de `overflow-x-hidden` sur le `body` et le `Dashboard` pour empÃªcher les dÃ©calages horizontaux tout en conservant une expÃ©rience fluide sur PC et Mobile.

[2026-02-26] [FLASH] Action : Extraction de la Date de Mise en Ligne â†’ RÃ©sultat : ImplÃ©mentation du sÃ©lecteur `abbr[aria-label]` dans `ListingParser` pour capturer l'Ã¢ge de l'annonce. Le champ `published_at_raw` est dÃ©sormais propagÃ© dans `listing_data` et stockÃ© dans Firestore.

[2026-02-26] [FLASH] Action : Raffinement des Prompts pour les Lots (Bundles) â†’ RÃ©sultat : Mise Ã  jour de `prompts.json` (directives Portier et Prompt Principal). L'IA autorise dÃ©sormais explicitement les instruments vendus avec des accessoires mineurs (micros, cÃ¢bles, supports). Le verdict `REJECTED_ITEM` est dÃ©sormais restreint aux annonces vendant *uniquement* des accessoires non autorisÃ©s.

[2026-02-26] [PRO] Action : Finalisation du Dashboard (Radar & Marques) & Ajout de Champs IA â†’ RÃ©sultat : (1) IntÃ©gration de la librairie `recharts` dans le frontend. (2) Remplacement des placeholders dans `MockupStatsView.jsx` par un **Radar Chart** affichant le profil moyen des 5 scores Gemini et un **Bar Chart** pour la distribution du Top 5 des marques. Les donnÃ©es sont calculÃ©es dynamiquement depuis l'inventaire filtrÃ©. (3) Backend : Ajout des clÃ©s `brand`, `model_name`, `production_year`, et `country_of_origin` au dictionnaire JSON attendu dans `main_analysis_prompt` (`prompts.json`), enrichissant considÃ©rablement la granularitÃ© future de l'analyse IA.

[2026-02-26] [PRO] Action : Audit approfondi des Statistiques et du Tunnel de Conversion â†’ RÃ©sultat : VÃ©rification du code de `MockupStatsView.jsx`. (1) Le **Tunnel de Conversion** Ã  3 niveaux est dÃ©jÃ  fonctionnel et alimentÃ© par les donnÃ©es rÃ©elles de Firestore. (2) Les **KPIs Financiers** (Marge latente, ROI, Score moyen) sont calculÃ©s dynamiquement. (3) Identification des manques : le Radar Chart (nÃ©cessite Recharts) et la distribution par Marque (nÃ©cessite extraction `brand` backend) restent Ã  implÃ©menter. Mise Ã  jour de la `TODO.md` pour reflÃ©ter cet Ã©tat d'avancement supÃ©rieur aux attentes.

[2026-02-26] [PRO] Action : ImplÃ©mentation d'une Protection Anti-Botting (Stealth) Globale â†’ RÃ©sultat : Correction du blocage par Facebook lors du rescraping massif. (1) **Randomisation** : Injection de User-Agents tournants et de Viewports alÃ©atoires dans `FacebookScraper` (`core.py`). (2) **FurtivitÃ© Playwright** : Ajout de flags spÃ©cifiques (`AutomationControlled`, `infobars`) pour masquer l'automatisation. (3) **DÃ©tection de Blocage** : Interruption propre en cas de redirection vers `/login` ou CAPTCHA. (4) **Rotation & Jitter** : Le script `migrate_images.py` redÃ©marre maintenant le navigateur toutes les 15 requÃªtes et utilise des dÃ©lais alÃ©atoires (jitter) pour simuler un comportement humain. Test `--dry-run` validÃ© avec succÃ¨s.

[2026-02-26] [PRO] Action : Raffinement des Interactions Cartographiques (Tooltip & Pins) â†’ RÃ©sultat : Ajout d'InfoWindows enrichies au survol (PC) et au clic (Mobile) sur les marqueurs Google Maps. Les bulles incluent dÃ©sormais une miniature, le titre, le score IA et la valeur estimÃ©e dans un design Dark Theme. Le marqueur sÃ©lectionnÃ© est dÃ©sormais visuellement identifiÃ© par une taille supÃ©rieure.

[2026-02-26] [PRO] Action : Optimisation de l'ExpÃ©rience Mobile (Overlay & Navigation) â†’ RÃ©sultat : (1) Correction de l'affichage de l'annonce sur mobile : elle s'affiche dÃ©sormais en "Full-Screen Overlay" par-dessus la carte au lieu de la compresser, garantissant une lisibilitÃ© maximale. (2) Inversion de la logique de clic sur mobile : le premier clic sur un pin ouvre l'InfoWindow, le clic sur la bulle ouvre l'annonce complÃ¨te.

[2026-02-26] [PRO] Action : AmÃ©lioration UX de la DealCard et de la Modale IA â†’ RÃ©sultat : (1) Le bouton de rÃ©-analyse est devenu un menu dÃ©roulant dynamique offrant les options "Scan Standard" et "Luthier Expert", gÃ©rÃ© par `useState` pour supporter le survol (PC) et le clic (Mobile). (2) Factorisation de la barre d'actions complÃ¨te (Favori, Scan, Rejeter, Suppression, Facebook) pour l'injecter directement dans l'en-tÃªte de la Modale d'Expertise IA, offrant une paritÃ© fonctionnelle totale entre les vues.

[2026-02-26] [PRO] Action : Correction UI Mobile du Menu des Verdicts (Mockup V2) â†’ RÃ©sultat : Le composant `VerdictDropdown` s'Ã©crasait et coupait le texte sÃ©lectionnÃ© sur les petits Ã©crans. Application de `whitespace-nowrap` sur le bouton principal et dÃ©finition d'une largeur fixe (`w-56`) avec `truncate` sur les options du menu dÃ©roulant dans `MockupDashboard.jsx` pour garantir un affichage propre sur une seule ligne.

[2026-02-26] [PRO] Action : Correction du Responsive Design et RÃ©solution de la "Double Navbar" Mobile (Mockup V2) â†’ RÃ©sultat : Le rendu mobile souffrait d'un overflow horizontal causÃ© par la Navbar V1 qui restait active en arriÃ¨re-plan avec une largeur minimale incompressible. (1) DÃ©sactivation conditionnelle de la Navbar V1 dans `App.jsx` lorsque le Mockup V2 est ouvert, Ã©liminant la "bande blanche" sur mobile. (2) Refonte du container de recherche/filtres dans `MockupDashboard` en utilisant un layout `grid-cols-1 md:flex` pour forcer un empilement vertical propre des Ã©lÃ©ments (Recherche, Favoris, Vues, Bouton X) sur petits Ã©crans. (3) Application de `whitespace-nowrap` sur l'indicateur de statut du bot dans `MockupNavbar` pour empÃªcher le texte de se casser sur deux lignes, et ajustement global des marges internes (padding) pour maximiser l'espace utile sur smartphone.

[2026-02-26] [PRO] Action : RÃ©solution de l'erreur Greenlet (Cannot switch to a different thread) sur le backend â†’ RÃ©sultat : L'implÃ©mentation de tÃ¢ches de scraping en arriÃ¨re-plan (ex: REFRESH, SCAN_URL) gÃ©nÃ©rait des crashs asynchrones car l'instance Playwright globale (`self.scraper`) du thread principal ne pouvait pas Ãªtre partagÃ©e avec les threads secondaires. La solution a Ã©tÃ© de retirer le contexte Playwright global dans le bot (`bot.py`) et la boucle principale (`main.py`). DÃ©sormais, chaque action appelant le Scraper (comme `run_scan`, `scan_specific_url` ou `cleanup_sold_listings`) instancie son propre scraper temporaire (`temp_scraper = FacebookScraper()`) localement et le libÃ¨re `finally: temp_scraper.close_session()`. Cette architecture garantit l'isolation absolue des navigateurs Chromium par thread.

[2026-02-25] [PRO] Action : Raffinement final de l'UI V2 (Modale IA, Barre de Filtres, Map Centering, Raccourci Favoris) â†’ RÃ©sultat : (1) Restauration de la section "Analyse DÃ©taillÃ©e" dans la Modale IA : Le Markdown complet (`aiAnalysis.analysis`) s'affiche maintenant correctement avec saut de ligne grÃ¢ce Ã  `whitespace-pre-wrap` au lieu de l'ancien `aiAnalysis.reasoning` tronquÃ©. (2) Rapatriement du statut "Favoris" dans la V2 avec un double accÃ¨s : option intÃ©grÃ©e au sommet de `VerdictDropdown` + crÃ©ation d'un bouton fixe "CÅ“ur" adjacent pour un accÃ¨s ultra-rapide en un clic. (3) Dynamisme de la Carte : IntÃ©gration de la logique `fitBounds` dans `MapView.jsx` pour que la Google Map se centre et zoome automatiquement sur les annonces visibles selon les filtres actifs, avec une sÃ©curitÃ© anti-zoom extrÃªme pour les annonces solitaires.

[2026-02-25] [PRO] Action : Finalisation de l'UI/UX du Mockup V2 (Responsive, Modale IA, Barre de Filtres) â†’ RÃ©sultat : (1) Modale IA Plein Ã‰cran : Le bloc d'expertise IA collapsible a Ã©tÃ© remplacÃ© par une modale "glassmorphism" (`z-[100]`) permettant une lecture trÃ¨s confortable sur Desktop sans dÃ©former la DealCard. (2) Nettoyage Dashboard : Le compteur de rÃ©sultats et le bouton "Effacer tous les filtres" (maintenant stylisÃ© en bouton carrÃ© dynamique rouge) ont Ã©tÃ© consolidÃ©s Ã  l'intÃ©rieur de la barre de filtres principale. (3) Hauteur des cartes : RÃ©duction de la hauteur des images de `400px` Ã  `280px` pour afficher la carte entiÃ¨re sur les Ã©crans de PC portables sans scroller. (4) Correction Navbar Mobile : RÃ©solution du dÃ©bordement horizontal (`overflow-x-hidden`) en contraignant la largeur de la toolbar.
[2026-02-25] [FLASH] Action : IntÃ©gration de la galerie ImageGallery et donnÃ©es rÃ©elles dans le Mockup V2 â†’ RÃ©sultat : Remplacement du dÃ©filement horizontal basique par le composant robuste ImageGallery. Support natif du plein Ã©cran, des flÃ¨ches de navigation et de l'affichage vertical intÃ©gral (object-contain). Extraction de vÃ©ritables URLs Facebook depuis Firestore pour un rendu rÃ©aliste.

[2026-02-25] [PRO] Action : Finalisation Responsive et Logique Taxonomique Mockup V2 â†’ RÃ©sultat : (1) Correction Mobile : Le status interactif du bot reste toujours visible sur `MockupNavbar` (points info annexes masquÃ©s), et ajout d'un bouton "Fermer" sur les DealCards en vue carte sur petit Ã©cran pour Ã©viter les blocages. (2) Comptage Taxonomie : Mise Ã  jour de `buildDealCounts` pour que chaque item `FAKE_DEALS` itÃ¨re sur son chemin entier de `classification` (`ex: electrique.ampli.combo`) pour remplir parfaitement l'arbre Ã  4 niveaux. (3) UX : Retrait des choix multiples "Toutes" redondants dans les sous-niveaux de filtres. (4) Alignement du Dropdown de filtres sur les "Nouveaux Verdicts" V2 via `ALL_FILTERS_CONFIG`.

[2026-02-25] [PRO] Action : Raffinement UX approfondi du Mockup V2 â†’ RÃ©sultat : (1) Tiroir de filtres : Transformation de `MockupFilterDrawer` en un accordÃ©on imbriquÃ© en cascade Ã  4 niveaux avec badges dynamiques de comptage d'annonces. (2) Barre d'actions (`MockupDashboard`) : Remplacement du dÃ©filement horizontal des verdicts par un composant `VerdictDropdown` compact. (3) Recherche : Ajout du filtrage interactif (text/location) avec bouton de rÃ©initialisation interne. (4) Carte : ImplÃ©mentation du mode "Split-Screen" (`MockupMapView`) et du bouton toggle Liste/Carte. (5) ContrÃ´les UI (`MockupNavbar`) : IntÃ©gration de la vÃ©ritable logique `BotControls` interactive au survol, et ajout des boutons d'actions manuelles (VÃ©rification et Rescan) Ã  la racine de la Toolbar. Le prototype Mockup V2 est achevÃ© et valide toutes les recommandations heuristiques UX de l'analyse prÃ©cÃ©dente.

[2026-02-25] [PRO] Action : ImplÃ©mentation du filtre Drawer en cascade Ã  4 niveaux â†’ RÃ©sultat : `MockupFilterDrawer.jsx` entiÃ¨rement rÃ©Ã©crit avec un arbre de taxonomie `TAXONOMY_TREE` Ã  4 niveaux de profondeur. Comportement : tous les groupes sont repliÃ©s par dÃ©faut (accordÃ©on). Chaque niveau s'affiche et s'ouvre automatiquement dÃ¨s qu'un choix est fait au niveau parent (Niveau 1 : Type d'instrument, Niveau 2 : Sous-catÃ©gorie contextuelle, Niveau 3 : ModÃ¨le/Type, Niveau 4 : Marque/DÃ©tail). La sÃ©lection d'un niveau parent rÃ©initialise automatiquement tous les niveaux enfants. Le titre du groupe indique le contexte (ex : "Sous-catÃ©gorie Â· Ã‰lectrique"). Les clÃ©s de filtres dans `MockupDashboard.jsx` ont Ã©tÃ© mises Ã  jour (`level1/level2/level3/level4`). "Verdict IA" retirÃ© du Drawer (couvert par les onglets rapides en haut de la grille).


[2026-02-25] [PRO] Action : CrÃ©ation du Mockup Complet UI V2 â†’ RÃ©sultat : Prototype interactif Dark Mode complet accessible via le bouton "Mockup V2" dans la Navbar.
 Composants crÃ©Ã©s : `MockupDealCard.jsx` (image full-width, marge affichÃ©e, bloc IA collapsible, titres normalisÃ©s, hit-zones 44px), `MockupNavbar.jsx` (statuts systÃ¨me compacts, boutons Filtres et ParamÃ¨tres, bouton quitter), `MockupFilterDrawer.jsx` (volet latÃ©ral coulissant avec 4 niveaux de filtres dynamiques et taxonomie en cascade â€” les sous-catÃ©gories s'adaptent automatiquement au type sÃ©lectionnÃ©, sans bouton Appliquer), `MockupDashboard.jsx` (assemblage complet : 8 fausses annonces, filtrage live via `useMemo`, onglets verdicts rapides, 3 sections Radar/MarchÃ©/Archives, bouton "Effacer les filtres"). IntÃ©gration du vrai `ConfigPanel` ouvert via le bouton âš™ï¸�. Le `App.jsx` bascule entre l'interface rÃ©elle et le Mockup V2 via un `useState` sans modifier les donnÃ©es ni les hooks Firestore.

[2026-02-25] [PRO] Action : Extension de l'analyse UI/UX (Deep Heuristic Evaluation) â†’ RÃ©sultat : Analyse des dÃ©tails qualitatifs au-delÃ  du simple layout.

[2026-02-25] [PRO] Action : RÃ©vision de l'analyse UI/UX suite aux retours utilisateurs â†’ RÃ©sultat : Mise Ã  jour de `docs/UI_UX_ANALYSIS.md` pour se concentrer sur les dÃ©fauts structurels critiques : 1) DÃ©mantÃ¨lement du panneau latÃ©ral (Aside) qui gaspille 20% de la largeur. 2) Refonte des filtres horizontaux qui dÃ©bordent en un "Drawer" latÃ©ral. 3) Correction de la DealCard Mobile pour forcer l'image en pleine largeur (`w-full`). 4) Nettoyage des boutons d'action (remplacement des textes par des icÃ´nes comme FB). Le `TODO.md` a Ã©tÃ© rÃ©Ã©crit avec ces nouvelles prioritÃ©s absolues.

[2026-02-25] [PRO] Action : Analyse approfondie de l'UI/UX et ajout de `docs/UI_UX_ANALYSIS.md` â†’ RÃ©sultat : Validation de la structure d'interface actuelle (Dashboard SaaS, code couleur sÃ©mantique). DÃ©finition de 4 axes prioritaires documentÃ©s dans le TODO pour un design Premium : Dark Mode, Micro-interactions visuelles, Refonte par "Tiroir" de la taxonomie des filtres, IntÃ©gration d'un panneau de statistiques.

[2026-02-25] [PRO] Action : ImplÃ©mentation du stockage pÃ©renne des images via Firebase Storage â†’ RÃ©sultat : Les URLs CDN de Facebook expirent aprÃ¨s 1-3 jours, rendant les images des annonces archivÃ©es inaccessibles. (Action 1) Init du bucket Storage dans `backend/database.py` : passage du `storageBucket` Ã  `firebase_admin.initialize_app()` et exposition de `self.bucket`. (Action 2) Ajout de `FIREBASE_STORAGE_BUCKET` et `IMAGE_RETENTION_REJECTED_DAYS` (30j) dans `config.py`. (Action 3) Le `FirestoreRepository` passe le bucket aux mÃ©thodes `upload_images_to_storage()` (upload + URL publique) et `purge_rejected_images()` (purge lifecycle). (Action 4) Le bot (`bot.py`) uploade systematiquement les images avant de sauvegarder chaque annonce et expose `purge_rejected_images()` pour le scheduler. (Action 5) Le frontend (`DealCard.jsx`) utilise `storageImageUrls || imageUrls` comme fallback. (Action 6) CrÃ©ation du script one-shot `backend/scripts/migrate_images.py` pour migrer les annonces existantes (test validitÃ© URL, re-scraping si expirÃ©e, upload Storage). (Action 7) Branchement de la purge lifecycle au `TaskScheduler` (`services.py`) via `purge_func=` â€” job hebdomadaire automatique. (Action 8) Correction du dry-run du script de migration : Playwright ne se lanÃ§ait pas inutilement, seulement un HTTP HEAD pour tester la validitÃ© des URLs. (Action 9) Ajout de `run.bat` et du workflow `.agent/workflows/run-venv.md` pour forcer l'usage du venv.

[2026-02-24] [FLASH] Action : Ajout de la taxonomie aux annonces rejetÃ©es par le Portier â†’ RÃ©sultat : Les annonces immÃ©diatement rejetÃ©es (BAD_DEAL, REJECTED_ITEM) ne possÃ©daient pas de champ `classification`, empÃªchant leur filtrage par type dans l'UI. (Action 1) Modification de `gatekeeper_verbosity_instruction` dans `prompts.json` pour exiger la classification dans le JSON de sortie du Portier (Tier 1). (Action 2) Mise Ã  jour de `backend/analyzer.py` pour extraire cette classification et l'inclure dans le payload de retour lors du coupe-circuit. Ce correctif affine l'expÃ©rience utilisateur lors de l'exploration des archives rejetÃ©es.

[2026-02-24] [PRO] Action : Simplification de la taxonomie des accessoires et durcissement des rejets â†’ RÃ©sultat : L'IA laissait passer les pÃ©dales et les supports de guitare en les amalgamant sous la clÃ© racine `accessoire_etui`. (Action 1) Renommage de la clÃ© racine de la taxonomie `accessoire_etui` en `etui_housse` et suppression du niveau imbriquÃ© `protection` pour aplatir la structure. (Action 2) Modification stricte du prompt du Portier (Tier 1) et du prompt principal pour ordonner le rejet immÃ©diat (`REJECTED_ITEM`) de tout accessoire n'Ã©tant pas un Ã©tui rigide ou une housse (ex: pÃ©dales, supports, ficelles, micros).

[2026-02-24] [PRO] Action : Correction de la profondeur de filtrage et de la justification des rejets (Frontend) â†’ RÃ©sultat : (Bug 1) Le filtre de taxonomie (FilterBar) n'affichait que 3 niveaux, empÃªchant la sÃ©lection des feuilles (ex: `Parlor`) suite Ã  l'ajout des catÃ©gories racines (`guitare`, `ampli`, etc.). Ajout d'un 4Ã¨me niveau `level4Filter` dans `useDealsManager.js` et `FilterBar.jsx` pour restaurer la granularitÃ© complÃ¨te. (Bug 2) Les annonces rejetÃ©es par l'Intelligence Artificielle restaient affichÃ©es avec le statut trompeur "Analyse en cours...". Modification de `DealCard.jsx` pour afficher la justification rÃ©elle (`deal.aiAnalysis.reasoning`) ou une phrase de rejet par dÃ©faut.



[2026-02-24] [PRO] Action : CrÃ©ation d'un point central de mise Ã  jour `set_status` (avec `threading.Lock()`) activÃ© â†’ RÃ©sultat : RÃ©solution du bug "En attente" pendant le scan. Le statut `botStatus` repassait Ã  `idle` prÃ©maturÃ©ment quand des threads parallÃ¨les (comme le nettoyage en arriÃ¨re-plan) se terminaient pendant qu'un scan principal tournait. CrÃ©ation d'un point central de mise Ã  jour `set_status` dans `GuitarHunterBot` avec `threading.Lock()` et un suivi des tÃ¢ches actives par nom (`_active_tasks`). Le statut `idle` n'est confirmÃ© sur Firestore que si l'ensemble des processus sont terminÃ©s, avec prÃ©servation de la prioritÃ© du statut `scanning` sur `cleaning` pour l'interface UI.

[2026-02-24] [PRO] Action : Ajout d'un sondage Firestore pendant les pauses et rÃ©Ã©criture de `delete_all_logs` â†’ RÃ©sultat : RÃ©paration de deux bugs. (Bug 1) RÃ©veil du bot en pause : La boucle d'attente dans `main.py` ne sondait pas Firestore, rendant le bot sourd Ã  toute commande (REFRESH, SCAN_URL, etc.) sauf START_BOT. Correction : ajout d'un sondage Firestore toutes les 5s avec `bot.sync_and_apply_config()`. Toute commande actionnable interrompt maintenant la pause et est traitÃ©e immÃ©diatement aprÃ¨s le rÃ©veil. (Bug 2) Suppression des logs : RÃ©Ã©criture de `delete_all_logs` dans `repository.py` pour utiliser `list()` afin de forcer la consommation du stream Firestore avant chaque batch, ajout d'un garde-fou `max_iterations` et de logs de diagnostic amÃ©liorÃ©s.

[2026-02-24] [FLASH] Action : Identification d'un bug de rÃ©veil du bot â†’ RÃ©sultat : Ajout au `TODO.md` : le bot en pause (`paused`) ignore la commande `REFRESH` (Rescan All) mais rÃ©agit au `SCAN_URL`.

[2026-02-24] [PRO] Session 27 : Robustesse de la dÃ©tection d'indisponibilitÃ© du scraper (`check_listing_availability`). Passage d'une vÃ©rification textuelle stricte Ã  une analyse Regex (insensible Ã  la casse, mots entiers `\b`) incluant le franÃ§ais et l'anglais ("vendu", "sold", "expired"). Ajout de l'inspection des attributs ARIA et vÃ©rification stricte de la visibilitÃ© CSS (`display: none`, `opacity: 0`) vis `window.getComputedStyle` pour Ã©liminer les faux positifs (Ã©lÃ©ments cachÃ©s ou mots partiels comme "revendu").

[2026-02-24] [FLASH] Session 26 (Bug Report) : Identification d'un problÃ¨me de pÃ©rennitÃ© des images. Les URLs Facebook CDN expirent (paramÃ¨tre `oe` dans l'URL). Les annonces valides perdent leur visibilitÃ© visuelle aprÃ¨s quelques jours. Ajout au `TODO.md`.

[2026-02-24] [PRO] Session 26 : AmÃ©lioration du Pilotage du Bot (Commandes AvancÃ©es & UI). (Action 1) Ajout de la commande `STOP_SCAN` avec `scan_stop_event` indÃ©pendant pour interrompre un scraping sans tuer le bot. (Action 2) Refonte sÃ©mantique de `STOP_BOT` : le bot entre dans une boucle de pause de 12h (interruptible) au lieu de s'Ã©teindre totalement. (Action 3) Ajout de `START_BOT` pour rÃ©veiller le bot instantanÃ©ment de sa pause. (Action 4) Extraction et refonte de l'interface des contrÃ´les : crÃ©ation du composant `<BotControls />` hybride avec indicateur de statut dynamique intÃ©grÃ© dans le panneau latÃ©ral "SystÃ¨me".

[2026-02-24] [FLASH] Session 25 : Correction "Mode Hors Ligne" du Bot. Automatisation du dÃ©ploiement des fichiers ignorÃ©s par Git via GitHub Secrets (`DOT_ENV` et `FIREBASE_SERVICE_ACCOUNT_KEY`). Mise Ã  jour de `deploy.yml` pour recrÃ©er dynamiquement `.env` Ã  la racine et `serviceAccountKey.json` dans `backend/config/` sur le serveur.

[2026-02-24] [FLASH] Session 24 : Correction du flux de dÃ©ploiement GitHub Actions (`deploy.yml`). (Action 1) Correction de la casse de la branche `dev` (Ã©tait `Dev`). (Action 2) Remplacement de la rÃ©initialisation forcÃ©e sur `master` par une logique dynamique utilisant `${{ github.ref_name }}`. (Action 3) Ajout de logs dÃ©taillÃ©s et d'une gestion d'erreur robuste pour le redÃ©marrage du service `guitare-hunter`. (Action 4) Audit complet de la documentation (`docs/`).

[2026-02-24] [FLASH] Session 23 : Correction du rejet systÃ©matique des Ã©tuis/housses par le Portier et le Coupe-Circuit. (Action 1) Mise Ã  jour de `prompts.json` : retrait de la condition d'exclusion sur les "accessoires bas de gamme (gigbag fin seul)" dans `main_analysis_prompt` â€” Les amplis, Ã©tuis et housses (mÃªme simples) sont maintenant tous acceptÃ©s. Mise Ã  jour de `gatekeeper_verbosity_instruction` : retrait du rejet des "accessoires nuls", ajout explicite des guitares, amplis, Ã©tuis et housses comme objets acceptÃ©s. (Action 2) Standardisation des 3 instructions de verbositÃ© (`gatekeeper`, `analyst`, `expert_pro`) de `string` â†’ `array of strings` pour la compatibilitÃ© avec l'Ã©diteur ligne-par-ligne du ConfigPanel. Mise Ã  jour de `backend/analyzer.py` : ajout de `join("\n")` si l'instruction reÃ§ue est une liste.

[2026-02-24] [PRO] Session 22 : RÃ©solution du conflit de casse Git (`Dev` vs `dev`) empÃªchant le dÃ©ploiement sur `gh-pages`. Suppression de la branche `Dev` distante, nettoyage des rÃ©fÃ©rences locales, et succÃ¨s de `npm run deploy`. ExÃ©cution du workflow `/git-push-dev-master` pour synchroniser et achever la session.

[2026-02-24] [FLASH] Session 21 (suite) : Correctif TypeError prix int â†’ cast `str()` dans `analyzer.py` avant `extract_price_from_text`. CrÃ©ation de `backend/scripts/migrate_firestore_prompts.py` (audit racine + injection clÃ©s Tier2/3 + nettoyage obsolÃ¨tes, mode `--dry-run`). Ajout commande `STOP_BOT` : handler `threading.Event` dans `main.py`, `triggerStopBot()` dans `firestoreService.js`, bouton Power dans `LogViewer.jsx`.

[2026-02-24] [FLASH] Session 21 : ImplÃ©mentation du Funnel 3-Tiers + Refacto DRY â†’ `analyzer.py` restructurÃ© avec `_call_gemini_json` (mutualisation des appels API), prompt de base construit une seule fois. Cascade T1 (Flash-Lite) â†’ T2 (Flash, format compact + 5 scores) â†’ Carrefour Logique â†’ T3 (Pro, conditionnel). Seuils ajoutÃ©s dans `config.py`. Nouvelles instructions `analyst_verbosity_instruction` et `expert_pro_context_instruction` ajoutÃ©es dans `prompts.json` et init Firestore (`bot.py`). 4 rondes de vÃ©rification, 4 bugs corrigÃ©s. Push `dev`.

[2026-02-23] [FLASH] RÃ©flexion Statistiques â†’ Conceptualisation des KPIs basÃ©s sur les scores du Tier 2/3 et archivage dans `docs/STATS_REFLEXION.md`.

[2026-02-23] [FLASH] Action : Conception de l'entonnoir d'analyse Ã  3 niveaux et crÃ©ation de `docs/FUNNEL_PLAN.md` â†’ RÃ©sultat : StratÃ©gie validÃ©e pour rÃ©duire les coÃ»ts (Tier 2 compact) tout en augmentant la profondeur (Tier 3 Expert Pro conditionnel). Introduction de 5 scores numÃ©riques et d'une logique de dÃ©clenchement "Jackpot" (Marge + DÃ©fi).
[2026-02-23] [FLASH] Action : CrÃ©ation de `backend/scripts/fetch_deal.py` â†’ RÃ©sultat : Outil fonctionnel pour inspecter les annonces rÃ©elles dans la structure Firestore imbriquÃ©e (`artifacts/{app}/users/{user}/...`).
[2026-02-23] [FLASH] Action : Mise Ã  jour de `docs/ARCHITECTURE.md` â†’ RÃ©sultat : Documentation de la structure multi-tenant de la base de donnÃ©es.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` â†’ RÃ©sultat : Assainissement du titre de la notification (suppression des sauts de ligne `\n`) pour Ã©viter des erreurs HTTP `Invalid header value` lors de l'envoi Ã  `ntfy.sh`.
[2026-02-22] [PRO] Action : Modification de `src/App.jsx` â†’ RÃ©sultat : Le lecteur rÃ©cupÃ¨re dÃ©sormais l'ID d'annonce via le lien `deals` complet (et plus `filteredDeals`), Ã©vitant que la carte ne s'ouvre pas si l'annonce est archivÃ©e/filtrÃ©e.
[2026-02-22] [PRO] Action : Modification de `backend/notifications.py` â†’ RÃ©sultat : Le lien cliquable des notifications `ntfy` renvoie dÃ©sormais vers la carte du deal sur le frontend (`?dealId=...`) au lieu de l'annonce Facebook FB.
[2026-02-23] [FLASH] Action : Audit final et synchronisation des branches â†’ RÃ©sultat : Documentation (Journal, Todo, Architecture, Data Flow) auditÃ©e et synchronisÃ©e. Fusion de la branche `dev` vers `master` et push remote.

Ce journal suit les changements majeurs, les dÃ©cisions d'architecture et les nouvelles fonctionnalitÃ©s.

---

---

### **Date: 23/02/2026** (Session 19)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Entonnoir v2)

#### ðŸ“� Description des Changements
- **Raffinage des dÃ©clencheurs Tier 3 (Expert Pro) :**
    - Couplage intelligent du prix et du score : le passage Ã  l'Expert Pro pour les objets > 1000$ ne se fait que si le `deal_score` est >= 4 (Ã©vite d'analyser en profondeur des objets chers mais inintÃ©ressants).
    - Durcissement des contrÃ´les d'authenticitÃ© : dÃ©clenchement systÃ©matique de l'Expert si `authenticity_score` <= 7.
    - Ajout d'un dÃ©clencheur spÃ©cifique pour les verdicts `COLLECTION`.
- **Mise Ã  jour de `docs/FUNNEL_PLAN.md` :** Documentation complÃ¨te de la logique de cascade.

#### ðŸ¤” Raisonnement
L'objectif est d'Ã©conomiser les appels au modÃ¨le Pro (plus coÃ»teux) en s'assurant qu'il n'intervient que sur des annonces ayant un rÃ©el potentiel ou prÃ©sentant un risque technique/historique nÃ©cessitant une haute prÃ©cision.

---

### **Date: 23/02/2026** (Session 18)

**Auteur:** Assistant AI

**Type:** Optimisation IA (Scores & PÃ©dagogie)

#### ðŸ“� Description des Changements
- **Enrichissement du Tier 2 (Analyste) :**
    - Introduction d'un systÃ¨me de notation sur 10 pour 5 indices : `deal_score`, `authenticity_score`, `condition_score`, `liquidity_score`, et `restoration_interest_score`.
    - Ajout du `restoration_interest_score` : Ce score Ã©value la valeur "pÃ©dagogique" ou le dÃ©fi technique d'un projet de lutherie, permettant d'identifier des "PÃ©pites de restauration" mÃªme si la marge financiÃ¨re pure est moindre.
- **Logique "Jackpot" :** CrÃ©ation d'un dÃ©clencheur Expert Pro si `deal_score` >= 6 ET `restoration_interest_score` >= 7.

#### ðŸ¤” Raisonnement
Le projet "Guitar Hunter" n'est pas qu'une question de profit immÃ©diat, c'est aussi un projet luthier-centric. Valoriser l'intÃ©rÃªt technique des rÃ©parations permet de ne pas rater des instruments rares ou complexes qui enrichissent l'expertise du MaÃ®tre Luthier.

---

### **Date: 23/02/2026** (Session 17)

**Auteur:** Assistant AI

**Type:** Refonte SystÃ¨me (Commandes & Base de donnÃ©es)

#### ðŸ“� Description des Changements
- **Migration des "Legacy Commands" vers la collection `commands` :**
    - Modification du Frontend (`src/services/firestoreService.js`) pour que les actions manuelles (Refresh, Cleanup, Reanalyze All, Scan URL) crÃ©ent des documents dans la collection `commands` au lieu de modifier des champs d'horodatage sur la racine du document utilisateur.
    - Simplification du Backend (`backend/services.py` & `backend/bot.py`) : Le `ConfigManager` a Ã©tÃ© Ã©purÃ© de toute la logique complexe de vÃ©rification d'horodatage. La boucle principale (`main.py`) gÃ¨re dÃ©sormais de maniÃ¨re unifiÃ©e toutes les commandes entrantes (avec statut `pending`, `completed`, `failed`).
    - Nettoyage du Backend (`backend/repository.py`) : L'ancienne mÃ©thode `consume_command` qui supprimait les champs du document utilisateur a Ã©tÃ© supprimÃ©e suite Ã  la nouvelle architecture.

#### ðŸ¤” Raisonnement
Cette unification de l'architecture autour de la collection `commands` facilite grandement la traÃ§abilitÃ©. Auparavant, le bot devait surveiller 4 champs (`forceRefresh`, `forceCleanup`, `forceReanalyzeAll`, `scanSpecificUrl`) greffÃ©s sur le document utilisateur. Maintenant, chaque commande, quelle que soit sa nature, suit un flux de vie identique (crÃ©ation â†’ attente â†’ traitement â†’ terminÃ©/erreur), ce qui rend le systÃ¨me beaucoup plus robuste et prÃ©visible.

---

### **Date: 23/02/2026** (Session 16)

**Auteur:** Assistant AI

**Type:** Refonte SystÃ¨me (Scraping & Frontend)

#### ðŸ“� Description des Changements
- **Robustesse du Scraper Playwright :**
    - Modification de `check_listing_availability` dans `backend/scraping/core.py` pour utiliser l'Ã©valuation JavaScript native du DOM (`page.evaluate`). La dÃ©tection des marqueurs "Vendu", "Sold" ou "plus disponible" ne repose plus sur des cibles CSS volatiles, mais scanne les textes rendus et visibles du `div[role="main"]`.
    - Timeout de navigation augmentÃ© Ã  30 secondes pour compenser la lenteur applicative de Facebook sans dÃ©clencher de "faux positifs" de suppressions.
- **Sauvegarde de l'Historique (Soft Delete) :**
    - La fonction de nettoyage `cleanup_sold_listings` bascule exclusivement sur le taggage Firestore avec `status: 'sold'`, abandonnant le comportement `Hard Delete` non-dÃ©sirÃ©.
- **Transparence de l'UI Frontend (`DealCard.jsx` & Filtrage) :**
    - L'Ã©tat `sold` rÃ©duit dÃ©sormais l'opacitÃ© visuelle de l'annonce et applique un badge contextuel bloquant.
    - Correction du "FantÃ´me d'Analyse" : Les annonces liquidÃ©es avant qu'une IA ne rende un verdict (`DEFAULT`) ne tentent plus d'afficher "Analyse en cours..." mais explicitement "Non AnalysÃ© (Vendu)".
    - Correction du badge Compteur (`SOLD`) dans la barre de filtre pour comptabiliser les annonces vendues sans qu'elles ne soient exclues prÃ©maturÃ©ment par l'absence d'une classe d'instruments.

#### ðŸ¤” Raisonnement
Le cycle complet de vie d'une annonce doit garantir zÃ©ro perte de donnÃ©es. Les annonces vendues constituent une mine d'or pour Ã©valuer le "Velocity Pricing" d'un luthier ou d'un revendeur. En prÃ©servant ces documents Firestore de faÃ§on Ã©lÃ©gante, l'application mÃ»rit vers une plateforme d'analyse de marchÃ© long terme, et non plus un simple scanner Ã©phÃ©mÃ¨re.

---

### **Date: 22/02/2026** (Session 15 - Soir)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'Architecture & RÃ©solution de Dette Technique

#### ðŸ“� Description des Changements
- **Externalisation des verdicts de rejet (Coupe-circuit) :**
    - La liste des verdicts provoquant l'arrÃªt immÃ©diat de l'analyse (`BAD_DEAL`, `REJECTED_ITEM`...) a Ã©tÃ© retirÃ©e du code Python (`backend/analyzer.py`).
    - Elle est dÃ©sormais stockÃ©e dans `prompts.json` par dÃ©faut et gÃ©rÃ©e dynamiquement via Firestore (`analysisConfig.rejectionVerdicts`).
    - Ajout d'une interface d'Ã©dition (liste de textes) dans `ConfigPanel.jsx` (section "Intelligence Artificielle").

#### ðŸ¤” Raisonnement
Cette modification rÃ©sout une dette technique identifiÃ©e. Auparavant, si la taxonomie des verdicts venait Ã  Ã©voluer, le backend devait Ãªtre recompilÃ©. Maintenant, l'utilisateur a un contrÃ´le total sur les conditions de "coupe-circuit" directement depuis l'interface web, rendant le systÃ¨me de filtrage (Portier) 100% pilotÃ© par les donnÃ©es.

---

### **Date: 22/02/2026** (Session 15 - AprÃ¨s-midi)

**Auteur:** Assistant AI

**Type:** Nettoyage & Organisation du Projet

#### ðŸ“� Description des Changements
- **DÃ©pollution de la racine :** Suppression des scripts de diagnostic et de setup obsolÃ¨tes (`diagnose_firestore.py`, `populate_cities.py`, `test_notification.py`, `verify_setup.py`) et de l'ancien journal (`implementation_journal.md`).
- **Restructuration des fichiers de configuration :**
    - CrÃ©ation de `backend/resources/` et dÃ©placement de `city_coordinates.json`.
    - CrÃ©ation de `firebase/` et dÃ©placement de `firestore.rules`.
    - CrÃ©ation de `backend/config/` et dÃ©placement de `serviceAccountKey.json`.
- **Mise Ã  jour des rÃ©fÃ©rences :** Correction des chemins d'accÃ¨s dans `config.py` (backend), `src/components/MapView.jsx` (frontend) et `tests/check_baseline.py`.

#### ðŸ¤” Raisonnement
Une racine propre facilite la navigation dans le projet et sÃ©pare clairement les fichiers de configuration, les ressources de donnÃ©es et le code source. La mise Ã  jour des imports garantit que les deux environnements (Python et React) continuent de fonctionner sans interruption.

---

### **Date: 22/02/2026** (Session 15 - Matin)

**Auteur:** Assistant AI

**Type:** Analyse Technique & Audit de DonnÃ©es

#### ðŸ“� Description des Changements
- **Audit de la base de donnÃ©es (Le mystÃ¨re des annonces invisibles) :**
    - **ProblÃ¨me :** L'utilisateur a remarquÃ© un Ã©cart de ~300 annonces entre le total Firestore (486) et les annonces visibles (84 + 91).
    - **Investigation :** CrÃ©ation de scripts d'audit (`inspect_db_stats.py`, `inspect_rejection_reasons.py`) pour analyser les documents `status: 'rejected'`.
    - **DÃ©couverte :** 287 annonces portent le verdict `REJECTED` (ancienne nomenclature v1). 20 proviennent du prÃ©-filtre Javascript, le reste (267) provient des modÃ¨les Gemini (anciennes analyses).
    - **Cause de l'invisibilitÃ© :** Le frontend (`matchesVerdictFilter`) masque totalement les documents ayant un statut global `rejected`. Dans la nomenclature v2, le "bruit" est classÃ© `REJECTED_ITEM` avec un statut global `analyzed`, ce qui les rend comptabilisable dans l'UI alors que la v1 les annihilait visuellement.
- **Analyse du systÃ¨me de nettoyage (Sold Listings) :**
    - Documentation du fonctionnement de `cleanup_sold_listings`. Identification de la fragilitÃ© de la dÃ©tection (basÃ©e sur du texte strict) et du risque de perte d'historique dÃ» au "Hard Delete".

#### ðŸ¤” Raisonnement
Il est crucial de conserver l'historique des ventes pour de futures statistiques (Price History / Velocity). Le passage au "Soft Delete" est validÃ© comme prochaine Ã©tape majeure.

---

### **Date: 20/02/2026** (Session 14 - Suite 2)

**Auteur:** Assistant AI

**Type:** Correction de Bug (Frontend / Firestore)

#### ðŸ“� Description des Changements
- **Fix Bug #3 â€” Le bouton "Reset" corrompait Firestore :**
    - **ProblÃ¨me :** Bien que la sauvegarde champ par champ ait Ã©tÃ© corrigÃ©e hier (utilisation de la notation par point `updateDoc` avec `analysisConfig.mainAnalysisPrompt`), la fonction `handleResetDefaults` envoyait encore l'objet imbriquÃ© entier `{ analysisConfig: { ... } }`. Cela entraÃ®nait un fallback de `firestoreService` sur l'ancienne mÃ©thode `setDoc` qui Ã©crasait silencieusement la racine du document.
    - **Solution :** Refonte de `handleResetDefaults` dans `useBotConfig.js` pour construire un objet plat utilisant la notation par point avant de l'envoyer Ã  `updateUserConfig`. La rÃ©initialisation utilise dÃ©sormais la mÃªme mÃ©thode d'Ã©criture chirurgicale que les sauvegardes manuelles.

#### ðŸ¤” Raisonnement
Cette asymÃ©trie entre la sauvegarde ligne-par-ligne et la rÃ©initialisation globale Ã©tait un reste de l'ancienne architecture. Maintenant, toutes les opÃ©rations de mise Ã  jour utilisent systÃ©matiquement la notation par point de Firestore pour garantir l'intÃ©gritÃ© des autres donnÃ©es du document.

---

### **Date: 20/02/2026** (Session 14 - Suite)

**Auteur:** Assistant AI

**Type:** Nettoyage de Dette Technique

#### ðŸ“� Description des Changements
- **Suppression du code mort :** Le fichier `backend/prompt_manager.py`, qui contenait l'ancienne architecture de prompts Ã  5 blocs inutilisÃ©e, a Ã©tÃ© retirÃ© du projet (via `git rm`).
- **Nettoyage des configurations obsolÃ¨tes :** Les anciennes clÃ©s (`persona`, `verdict_rules`, `system_structure`, etc.) ont Ã©tÃ© supprimÃ©es de `prompts.json` et de `config.py` pour allÃ©ger le code et Ã©viter toute confusion future.

#### ðŸ¤” Raisonnement
Le projet Ã©volue avec succÃ¨s vers un systÃ¨me d'analyse IA en cascade et paramÃ©trable. Supprimer le code inactif (le vieux `PromptManager` monolithique) et nettoyer les rÃ©sidus dans les configurations garantit que l'architecture reste claire et facile Ã  comprendre pour les futures itÃ©rations.

---

### **Date: 20/02/2026** (Session 14)

**Auteur:** Assistant AI

**Type:** Audit Complet du Projet (Full Stack)

#### ðŸ“� Description des Changements

1.  **Analyse globale des flux de donnÃ©es et de l'architecture :**
    - RÃ©alisation d'un audit de bas en haut (Scrapers -> Core Logic -> IA -> Base de donnÃ©es -> Frontend).
    - Mise Ã  jour de `docs/TODO.md` avec de nouvelles prioritÃ©s de pointe (dette technique cachÃ©e).
    - Mise Ã  jour de `docs/ARCHITECTURE.MD` pour reflÃ©ter la situation rÃ©elle des flux de commandes.

2.  **Identifications ClÃ©s (Dette Technique ajoutÃ©e au TODO) :**
    - **Architecture de Commandes Hybride :** Le backend Ã©coute Ã  la fois des champs horodatÃ©s sur `users/{id}` (legacy) et des documents dans la collection `commands` (nouveau). Cela crÃ©e une complexitÃ© inutile.
    - **Logique de Rejet HardcodÃ©e :** Le composant `DealAnalyzer` filtre les annonces en lisant en dur une liste de "verdicts de rejet" (`BAD_DEAL`, `REJECTED_ITEM`, etc.). Si la taxonomie en frontend/prompts Ã©volue, le backend devient aveugle sans mise Ã  jour du code source.
    - **FragilitÃ© du Scraper :** La dÃ©tection d'une annonce vendue sur Playwright se fie Ã  une expression exacte ("Cette annonce nâ€™est plus disponible"), ce qui est trÃ¨s cassable.

#### ðŸ¤” Raisonnement

- Il est vital de de temps Ã  autre "dÃ©zoomer" de la rÃ©solution de bugs isolÃ©s pour analyser les tendances de l'architecture. Ces dÃ©couvertes empÃªchent qu'un simple changement de configuration (ex: renommage d'un statut dans l'UI) ne fasse tomber tout le backend silencieusement.

---
### **Date: 20/02/2026** (Session 13)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de la Configuration / PrÃ©paration au DÃ©ploiement

#### ðŸ“� Description des Changements

1.  **Uniformisation de la gestion des IDs dans le Frontend :**
    - **ProblÃ¨me :** Les constantes `PYTHON_USER_ID` et `APP_ID` Ã©taient codÃ©es en dur dans `src/services/firestoreService.js`, crÃ©ant une redondance avec les variables d'environnement dÃ©jÃ  prÃ©sentes dans `.env` et configurÃ©es dans `vite.config.js`.
    - **Solution :** Remplacement des valeurs en dur par `process.env.USER_ID_TARGET` et `process.env.APP_ID_TARGET`.
    - **BÃ©nÃ©fice :** La configuration est dÃ©sormais centralisÃ©e dans le fichier `.env`, facilitant le dÃ©ploiement et la maintenance.

#### ðŸ¤” Raisonnement

- Le passage aux variables d'environnement est une bonne pratique indispensable avant un dÃ©ploiement, assurant que le code reste agnostique de l'environnement et que les identifiants clÃ©s peuvent Ãªtre gÃ©rÃ©s de maniÃ¨re sÃ©curisÃ©e et centralisÃ©e.

---

### **Date: 20/02/2026** (Session 12)

**Auteur:** Assistant AI

**Type:** Correction de Bugs (PrioritÃ© Haute)

#### ðŸ“� Description des Changements

1.  **Fix Bug #1 â€” Classifications "Autre" (Frontend + Backend) :**
    - **ProblÃ¨me :** L'IA inventait des libellÃ©s libres (ex: "Fender Stratocaster") qui ne correspondaient pas exactement aux clÃ©s de la taxonomie (ex: "Stratocaster"). La fonction `normalize` ne permettait pas de trouver ces classifications.
    - **Solution :**
        - Rendu l'instruction de classification plus stricte dans `prompts.json` (demande la valeur exacte d'une feuille de la taxonomie).
        - Ajout d'une fonction `findPathFuzzy` dans `useDealsManager.js` pour tolÃ©rer les variations (recherche par sous-chaÃ®ne normalisÃ©e).

2.  **Fix Bug #2 â€” Compteurs de filtres incorrects (Frontend) :**
    - **ProblÃ¨me :** La boucle de comptage dans `useDealsManager.js` n'incrÃ©mentait que les 3 premiers niveaux (`path[0]`, `path[1]`, `path[2]`). Sur une taxonomie Ã  4 niveaux, la feuille finale n'Ã©tait jamais comptÃ©e, affichant des badges erronÃ©s.
    - **Solution :** Remplacement des affectations dures par une boucle `path.forEach(segment => ...)` pour incrÃ©menter dynamiquement tous les niveaux du chemin de la taxonomie.

#### ðŸ¤” Raisonnement

- Ces deux bugs impactaient fortement l'expÃ©rience utilisateur (mauvais comptage, difficultÃ© Ã  filtrer les guitares). En durcissant le backend (prompt) tout en assouplissant le frontend (fuzzy match), on maximise les chances que la classification fonctionne mÃªme sur les anciennes annonces.

---

### **Date: 20/02/2026** (Session 11)

**Auteur:** Assistant AI

**Type:** Correction de Bug Critique (Frontend / Firestore)

#### ðŸ“� Description des Changements

1.  **Correction du bug de corruption silencieuse de `analysisConfig` dans Firestore :**
    - **ProblÃ¨me :** La fonction `updateUserConfig` dans `firestoreService.js` utilisait systÃ©matiquement `setDoc` avec `merge: true`. Ce comportement merge uniquement au niveau racine du document Firestore. Passer un objet `{ analysisConfig: { mainAnalysisPrompt: [...] } }` **remplaÃ§ait intÃ©gralement** le sous-objet `analysisConfig`, effaÃ§ant silencieusement `gatekeeperModel`, `expertModel`, `gatekeeperVerbosityInstruction` et `expertContextInstruction`.
    - **Impact :** Chaque `onBlur` sur un `PromptListEditor` corrompait Firestore. La corruption causait Ã©galement une race condition qui annulait le Reset.
    - **Solution :** `updateUserConfig` dÃ©tecte maintenant si les clÃ©s passÃ©es contiennent une notation par points (ex: `'analysisConfig.mainAnalysisPrompt'`) :
        - **Dot-notation** â†’ `updateDoc` : Ã©criture chirurgicale sur le champ exact, sans toucher les champs frÃ¨res.
        - **Objet complet** (ex: Reset) â†’ `setDoc` + `merge: true` : comportement inchangÃ© pour les resets complets.
    - **Fichiers modifiÃ©s :** `src/services/firestoreService.js`

#### ðŸ¤” Raisonnement

- `updateDoc` de Firestore accepte nativement la notation par points pour cibler des sous-champs prÃ©cis. C'est l'outil prÃ©vu pour ce cas d'usage. Le code utilisait dÃ©jÃ  `unflatten` pour "deviner" l'intention, mais ce n'est pas suffisant car `setDoc + merge` ne merge pas en profondeur.

---

### **Date: 20/02/2026** (Session 10)

**Auteur:** Assistant AI

**Type:** Audit de Documentation & Analyse Approfondie

#### ðŸ“� Description des Changements

1.  **Audit complet du systÃ¨me de prompts :**
    - Analyse exhaustive de tous les fichiers impliquÃ©s dans le pipeline de prompts, du backend (`config.py`, `analyzer.py`, `services.py`) au frontend (`useBotConfig.js`, `firestoreService.js`, `ConfigPanel.jsx`).
    - Identification et documentation du code mort : la classe `PromptManager` dans `backend/prompt_manager.py` est un orphelin non instanciÃ©, vestige d'une ancienne architecture "5 blocs". Les clÃ©s `persona`, `verdict_rules`, `reasoning_instruction`, `user_prompt`, `system_structure` dans `prompts.json` et leurs constantes associÃ©es dans `config.py` sont obsolÃ¨tes.
    - Validation du format de `prompts.json` : syntaxiquement valide.

2.  **Mise Ã  jour de `docs/ARCHITECTURE.md` (Section 4 â€” SystÃ¨me de Prompts) :**
    - Remplacement de la description gÃ©nÃ©rale par une analyse technique dÃ©taillÃ©e avec inventaire des fichiers, diagrammes de flux de donnÃ©es rÃ©els (Backend + Frontend), tableau des prompts modifiables par l'utilisateur, documentation du mÃ©canisme de fallback, et inventaire de la dette technique.

#### ðŸ¤” Raisonnement

- La documentation prÃ©cÃ©dente donnait une vue d'ensemble correcte mais imprÃ©cise. L'ajout du tableau de fichiers avec leur statut (actif/orphelin) et des diagrammes de flux en texte brut offre une rÃ©fÃ©rence fiable pour les futurs dÃ©veloppements, notamment pour le nettoyage du code mort.

---

### **Date: 23/02/2026** (Session 9)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Ajustement de la largeur de l'image sur mobile:**
    - **ProblÃ¨me:** La largeur de l'image sur mobile (`w-32`) Ã©tait trop Ã©troite.
    - **Solution:** La largeur du conteneur de l'image est passÃ©e Ã  `w-1/2` (50% de la largeur de la carte), offrant un meilleur Ã©quilibre visuel avec le bloc de prix qui occupe les 50% restants.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Cet ajustement rÃ©pond Ã  la demande de donner plus d'importance Ã  l'image sur mobile, tout en conservant une disposition en deux colonnes compacte.

---

### **Date: 23/02/2026** (Session 8)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Refonte de la structure de la `DealCard` (Mobile First):**
    - **ProblÃ¨me:** La disposition prÃ©cÃ©dente ne satisfaisait pas les besoins spÃ©cifiques de l'affichage mobile (image complÃ¨te, compacitÃ©) et desktop (hiÃ©rarchie claire).
    - **Solution:** Une approche "Mobile First" avec deux structures distinctes a Ã©tÃ© implÃ©mentÃ©e :
        - **Mobile (`md:hidden`):** Un en-tÃªte compact affiche l'image (largeur fixe `w-32`) et le bloc de prix cÃ´te Ã  cÃ´te. Le titre et les dÃ©tails suivent en dessous.
        - **Desktop (`hidden md:block`):** La disposition classique en deux colonnes est conservÃ©e, avec l'image "sticky" Ã  gauche. Dans la colonne de droite, le bloc de prix est positionnÃ© au-dessus du titre pour une meilleure hiÃ©rarchie.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

2.  **CrÃ©ation du composant `PriceDisplay`:**
    - **Action:** La logique d'affichage du prix et du menu dÃ©roulant financier a Ã©tÃ© extraite dans un sous-composant `PriceDisplay`. Cela permet de l'utiliser Ã  deux endroits diffÃ©rents dans le code (header mobile et colonne desktop) sans dupliquer la logique complexe.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

3.  **Retour Ã  l'affichage complet des images:**
    - **Action:** Annulation du changement `object-cover` dans `ImageGallery.jsx`. Les images sont de nouveau affichÃ©es en entier (`object-contain`) pour ne perdre aucun dÃ©tail de l'instrument.

#### ðŸ¤” Raisonnement

- Cette solution hybride offre le meilleur des deux mondes : une expÃ©rience mobile optimisÃ©e pour la densitÃ© d'information et une expÃ©rience desktop riche et structurÃ©e. L'extraction du composant `PriceDisplay` maintient le code propre et maintenable malgrÃ© la duplication structurelle.

---

### **Date: 23/02/2026** (Session 6)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Uniformisation de l'affichage du bloc prix:**
    - **ProblÃ¨me:** Le bloc de prix pouvait encore dÃ©passer de la carte sur certains Ã©crans d'ordinateur lorsque le titre Ã©tait long et que l'affichage Ã©tait en mode "ligne" (cÃ´te Ã  cÃ´te).
    - **Solution:** L'affichage a Ã©tÃ© uniformisÃ© pour Ãªtre identique sur mobile et desktop. Le bloc de prix est dÃ©sormais **toujours** positionnÃ© en dessous du titre et alignÃ© Ã  gauche. Cela garantit qu'il dispose toujours de toute la largeur nÃ©cessaire et Ã©limine tout risque de dÃ©passement.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- La cohÃ©rence de l'interface est primordiale. En adoptant une disposition verticale unique, on simplifie la maintenance et on s'assure que le contenu critique (le prix et les dÃ©tails financiers) est toujours lisible, quelle que soit la contrainte d'espace horizontal.

---

### **Date: 23/02/2026** (Session 5)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Ajustement de la taille du bouton de prix:**
    - **ProblÃ¨me:** Le bouton de prix, bien que fonctionnel, pouvait Ãªtre rendu plus compact pour un meilleur Ã©quilibre visuel.
    - **Solution:** Plusieurs micro-ajustements ont Ã©tÃ© effectuÃ©s : rÃ©duction du `padding`, de la taille de la police, de la taille de l'icÃ´ne, de l'espacement interne et du rayon de la bordure.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Ce changement est un raffinement stylistique visant Ã  perfectionner l'Ã©quilibre et l'harmonie des composants de l'interface.

---

### **Date: 23/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Fusion du Bouton de Prix et du Toggle d'Expansion:**
    - **ProblÃ¨me:** Le bouton affichant le prix et le bouton pour dÃ©plier les dÃ©tails financiers Ã©taient deux Ã©lÃ©ments sÃ©parÃ©s, ce qui Ã©tait moins intuitif et prenait plus de place.
    - **Solution:** Les deux Ã©lÃ©ments ont Ã©tÃ© fusionnÃ©s en un seul composant interactif. Le bouton de prix contient maintenant le montant et l'icÃ´ne "chevron". L'ensemble du bloc est cliquable pour afficher/masquer les dÃ©tails financiers.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Cette modification amÃ©liore l'expÃ©rience utilisateur en crÃ©ant un point d'interaction unique et clair, ce qui est un standard de design d'interface.
- Elle permet Ã©galement un gain d'espace marginal mais apprÃ©ciable sur les petits Ã©crans.

---

### **Date: 24/02/2026** (Session 4)

**Auteur:** Assistant AI

**Type:** Correction de bugs (PrioritÃ© Haute)

#### ðŸ“� Description des Changements

1.  **Correction de la commande `STOP_BOT` (Backend):**
    - **ProblÃ¨me:** La commande `STOP_BOT` via l'interface UI (ou Firestore) passait le statut du bot Ã  `stopped` mais le programme Python continuait son scan ou nettoyage en cours (boucles synchrones Playwright/Firebase longues).
    - **Solution:** J'ai passÃ© l'instance `threading.Event()` (`stop_event`) depuis `main.py` jusque dans `GuitarHunterBot` (`bot.py`) et `FacebookScraper` (`core.py`). Des vÃ©rifications `if self.stop_event.is_set(): return/break` ont Ã©tÃ© ajoutÃ©es dans les points stratÃ©giques des boucles de dÃ©filement (`page.mouse.wheel`), d'analyse d'annonces, de nettoyage des vendues (`cleanup_sold_listings`) et des rÃ©analyses en attente.
    - **Fichiers modifiÃ©s:** `main.py`, `backend/bot.py`, `backend/scraping/core.py`.

2.  **Correction de la suppression des logs cÃ´tÃ© client (Frontend):**
    - **ProblÃ¨me:** Le bouton "Vider la base de donnÃ©es" du `LogViewer.jsx` ne produisait aucun effet. Les logs Ã©coutÃ©s correspondaient Ã  un "userIdTarget" et un "appId" codÃ©s en dur (`00737242777130596039`, `c_5d118e71...`). 
    - **Solution:** Standardisation via des variables d'environnement. Ajout de `VITE_APP_ID_TARGET` et `VITE_USER_ID_TARGET` dans `.env` cÃ´tÃ© React, de faÃ§on Ã  ce que le `LogViewer` se base dynamiquement sur la mÃªme configuration ciblÃ©e que le Backend Python et Firebase.
    - **Fichiers modifiÃ©s:** `src/components/LogViewer.jsx`, `.env`.

#### ðŸ¤” Raisonnement

- **Stop Bot rÃ©actif :** Pour que "l'arrÃªt d'urgence" fonctionne, il fallait sortir le code d'une simple vÃ©rification entre deux cycles du scheduler (ancienne mÃ©thode) et propager un kill-switch asynchrone jusque dans les boucles de scraping internes. L'objet `threading.Event()` est parfait pour Ã§a, agissant comme un drapeau partagÃ© et thread-safe.
- **Dette Technique (Logs) :** Le code frontend pour les logs Ã©tait restÃ© sur un ancien jet de POC oÃ¹ je dÃ©veloppais avec mes propres IDs personnels (Session 1 Ã  5). La standardisation avec `.env` aligne le `LogViewer` sur le reste de l'application.

---

### **Date: 23/02/2026** (Session 3)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX)

#### ðŸ“� Description des Changements

1.  **Refonte du Menu de RÃ©analyse:**
    - **ProblÃ¨me:** Le menu de rÃ©analyse (Standard/Expert) Ã©tait "dÃ©tachÃ©" de la carte lors du dÃ©filement (scroll) car il utilisait un `Portal`. De plus, il Ã©tait trop volumineux avec du texte inutile.
    - **Solution:**
        - **Ancrage:** Le menu est maintenant rendu directement dans le DOM de la carte, positionnÃ© en absolu par rapport au bouton de rÃ©analyse. Il suit donc parfaitement le dÃ©filelement de la page.
        - **Design Compact:** Le texte a Ã©tÃ© supprimÃ© au profit d'icÃ´nes (`RefreshCw` et `BrainCircuit`) avec des info-bulles (`title`). Le menu est beaucoup plus discret et s'intÃ¨gre mieux Ã  l'interface.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- L'utilisation de `Portal` pour des menus contextuels liÃ©s Ã  des Ã©lÃ©ments scrollables est souvent problÃ©matique sans une gestion complexe de la position. L'ancrage direct via CSS (`position: absolute`) est une solution plus robuste et plus simple ici.
- La rÃ©duction de la taille du menu amÃ©liore l'expÃ©rience utilisateur, en particulier sur mobile oÃ¹ l'espace est limitÃ©.

---

### **Date: 23/02/2026** (Session 2)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration du Design Responsive (UI/UX)

#### ðŸ“� Description des Changements

1.  **AmÃ©lioration de l'affichage de la `DealCard` sur mobile:**
    - **ProblÃ¨me:** Sur les Ã©crans de petite taille, le bloc contenant les informations financiÃ¨res (`Prix`, `Valeur EstimÃ©e`, etc.) ne passait pas Ã  la ligne et dÃ©bordait de la carte, rendant l'interface inutilisable.
    - **Solution:** La structure de l'en-tÃªte de la carte a Ã©tÃ© rendue "responsive" :
        - Sur les Ã©crans `md` et plus, le titre et le bloc financier sont cÃ´te Ã  cÃ´te.
        - Sur les petits Ã©crans (mobile), le bloc financier passe automatiquement sous le titre, utilisant toute la largeur disponible et Ã©vitant tout dÃ©passement.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

2.  **Simplification de l'affichage du prix:**
    - **ProblÃ¨me:** Pour gagner de la place sur mobile, l'affichage du prix pouvait Ãªtre plus compact.
    - **Solution:**
        - La mention "Prix DemandÃ©" a Ã©tÃ© supprimÃ©e.
        - La taille de la police du prix a Ã©tÃ© rÃ©duite (`text-xl` au lieu de `text-2xl`).
        - Le padding du conteneur du prix a Ã©tÃ© ajustÃ©.
    - **Fichiers modifiÃ©s:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- Ces changements sont cruciaux pour l'utilisabilitÃ© de l'application sur des appareils mobiles. Ils suivent les principes du "responsive design" en adaptant la disposition du contenu Ã  la taille de l'Ã©cran.
- La simplification du prix contribue Ã  une interface plus Ã©purÃ©e et directe.

---

### **Date: 23/02/2026** (Session 1)

**Auteur:** Assistant AI

**Type:** AmÃ©lioration de l'interface utilisateur (UI/UX) & Correction de bug

#### ðŸ“� Description des Changements

1.  **Refonte du Module Financier sur la `DealCard`:**
    - **ProblÃ¨me:** Les indicateurs financiers clÃ©s (`estimated_value`, `net_guitar_cost`, etc.) Ã©taient cachÃ©s sous des conditions trop restrictives (ex: uniquement si la marge Ã©tait positive ou si l'annonce n'Ã©tait pas rejetÃ©e).
    - **Solution:** Un nouveau module financier a Ã©tÃ© implÃ©mentÃ© :
        - **Toujours visible:** Le prix demandÃ©, la valeur estimÃ©e et le potentiel de revente sont maintenant toujours visibles si les donnÃ©es existent, mÃªme pour les annonces rejetÃ©es.
        - **DÃ©tails sur demande:** Un menu dÃ©roulant (toggle) a Ã©tÃ© ajoutÃ© pour afficher les dÃ©tails techniques comme le **CoÃ»t Net** et la **Marge Brute**.
        - **Code couleur:** La marge brute est maintenant colorÃ©e (vert si positive, rouge si nÃ©gative) pour une identification rapide de la rentabilitÃ©.
    - **Fichier modifiÃ©:** `src/components/DealCard.jsx`

2.  **Correction du Bug de RÃ©analyse "Expert":**
    - **ProblÃ¨me:** Lors d'un clic sur le bouton de rÃ©analyse "Expert", l'indicateur de chargement (spinner) ne s'activait pas car le statut `analyzing_expert` n'Ã©tait pas correctement gÃ©rÃ© par le frontend.
    - **Solution:** Le statut `analyzing_expert` a Ã©tÃ© ajoutÃ© aux listes de vÃ©rification `isAnalyzing` et `getModelName` dans la `DealCard`.
    - **Fichier modifiÃ©:** `src/components/DealCard.jsx`

#### ðŸ¤” Raisonnement

- La refonte du module financier a pour but de fournir Ã  l'utilisateur un contexte complet sur **pourquoi** une annonce est jugÃ©e bonne ou mauvaise, mÃªme aprÃ¨s qu'elle ait Ã©tÃ© rejetÃ©e.
- La correction du bug de rÃ©analyse amÃ©liore le retour visuel pour l'utilisateur, confirmant que son action a bien Ã©tÃ© prise en compte.

---

### Session 20 : Expansion du Scope - Ã‰tape 1 (Amps & Ã‰tuis)

#### âœ… Objectif : Passer d'un systÃ¨me "Tout-Guitare"- [x] Bugfix: Taxonomy Count Collision (hierarchical paths).
  - [x] Round 1: Code Audit (Path normalization & aggregation).
  - [x] Round 2: Data Mapping Verification (Multi-parent nodes).
  - [x] Round 3: UI/Filter Interaction Sync.
- **Nouveaux Produits** : IntÃ©gration des `amplificateurs` (Lampes, Transistors, ModÃ©lisation) et des `accessoires_etuis` (Rigides, Housses souples).
- **Persona Luthier** : Mise Ã  jour des prompts pour Ã©valuer les amplis (Ã©tat des lampes, transformateurs) et valoriser l'apport financier des housses/Ã©tuis pour le flipping.
- **Synchronisation Full-Stack** : Mise Ã  jour de `config.py` et `useDealsManager.js` pour supporter dynamiquement la nouvelle structure.

#### ðŸ¤” Raisonnement

- L'expansion permet de capturer des opportunitÃ©s de "Fast Flip" (ex: Boss Katana) et de maximiser la valeur des packs guitare+Ã©tui.
- Le maintien du persona **MaÃ®tre Luthier** assure une analyse technique rigoureuse, mÃªme sur des objets non-luthier classiques comme les amplis numÃ©riques.

---

[2026-02-26] [FLASH] Action effectuÃ©e â†’ Migration complÃ¨te vers l'UI V2, suppression de l'obsolescence V1 et validation du build de production.

### Session 36 : Activation DÃ©finitive de la V2 & Nettoyage V1

#### âœ… Objectif : Remplacer l'ancienne UI par la nouvelle interface SaaS V2.

- **Standardisation des Composants** : Renommage massif des composants `Mockup*` en noms de production (`Dashboard`, `Navbar`, `DealCard`, `FilterDrawer`, `StatsView`).
- **Simplification de `App.jsx`** : Suppression de toute la logique de bascule V1/V2. L'application monte dÃ©sormais directement le `Dashboard` V2.
- **Suppression de la Dette Technique** : Ã‰limination des fichiers V1 obsolÃ¨tes (`FilterBar.jsx`, `SectionGroup.jsx`, `DealModal.jsx`, `BotControls.jsx`, `DebugStatus.jsx`).
- **Validation** : Build Vite (`npm run build`) validÃ© avec succÃ¨s (0 erreur d'import).

#### ðŸ¤” Raisonnement

- La V2 est jugÃ©e supÃ©rieure en termes d'ergonomie (Filtres en tiroir, Stats intÃ©grÃ©es, Map Split-screen) et d'esthÃ©tique (Dark Mode).
- Supprimer les fichiers obsolÃ¨tes Ã©vite toute confusion future et allÃ¨ge le bundle final.
- La transition "Production Ready" marque la fin de la phase de prototypage de la nouvelle interface.

---

[2026-02-26] [FLASH] Action effectuÃ©e â†’ Polissage UI : Verrouillage du scroll global et correction du clipping dans la Navbar.

### Session 39 : Polissage de l'ExpÃ©rience Utilisateur

#### âœ… Objectif : Supprimer les artefacts visuels rÃ©siduels pour une expÃ©rience "Produit" parfaite.

- **DÃ©sactivation du Scroll Corps** : Ajout de `overflow: hidden` sur `html, body, #root` dans `index.css` pour forcer l'utilisation des conteneurs internes et supprimer la barre de dÃ©filement du navigateur.
- **Correction du Menu Statut** : Retrait de `overflow-x-hidden` sur la `Navbar` pour permettre au menu de survol (status controls) de s'afficher sans Ãªtre tronquÃ©.
- **Z-Index & Layers** : VÃ©rification de la superposition des Ã©lÃ©ments interactifs pour un rendu "floating" optimal.

#### ðŸ¤” Raisonnement

- Le Dashboard V2 est conÃ§u pour Ãªtre une interface fixe (SPA). La prÃ©sence d'une scrollbar native sur le cÃ´tÃ© droit nuisait Ã  l'aspect premium et cassait l'alignement visuel.
- La Navbar doit Ãªtre capable de dÃ©border (overflow visible) pour ses menus contextuels, tout en restant `sticky`.

---

[2026-02-26] [FLASH] Action effectuÃ©e â†’ Bugfix ConfigPanel : Suppression d'un double `return` et de blocs syntaxiques redondants bloquant le build Vite.

### Session 40 : Correction Syntaxique Critique

- **Correction `ExclusionKeywordsSection`** : Suppression du code dupliquÃ© par erreur lors du prÃ©cÃ©dent push. Le composant `ConfigPanel.jsx` est dÃ©sormais syntaxiquement correct.
- **VÃ©rification** : Le build Vite ne doit plus lever l'erreur `The character "}" is not valid inside a JSX element`.

---

---

[2026-03-09] [FLASH] Action effectuÃ©e â†’ Migration vers Tailscale OAuth pour le dÃ©ploiement (CI/CD) et correction du pÃ©rimÃ¨tre des secrets.

### Session 48 : IntÃ©gration Tailscale OAuth (CI/CD)

#### âœ… Objectif : SÃ©curiser la connexion SSH du GitHub Runner via Tailscale OAuth.

- **DevOps (`deploy.yml`)** : Utilisation des secrets `TS_OAUTH_CLIENT_ID` et `TS_OAUTH_SECRET` pour rejoindre le Tailnet lors du dÃ©ploiement.
- **Documentation** : Mise Ã  jour de `ARCHITECTURE.md` pour clarifier que ces secrets concernent le pipeline de dÃ©ploiement et non l'application.
- **Correction** : Retrait des variables OAuth de `config.py` et de l'injection dans le `.env` du serveur (pÃ©rimÃ¨tre CI/CD uniquement).

#### ðŸ¤” Raisonnement

- Les identifiants OAuth Tailscale sont nÃ©cessaires au GitHub Runner pour accÃ©der au serveur privÃ©. L'application (bot) n'en a pas besoin pour son fonctionnement interne. SÃ©parer les deux types de secrets amÃ©liore la clartÃ© et la sÃ©curitÃ©.

---

---

[2026-07-19] [FLASH] Action effectuée -> Ajout des images dans l'index des annonces et refonte UX de la Google Map.

### Session : Optimisation MapView et Index Firestore

#### 1. Objectif : Afficher les images et les informations complètes sur les popups de la carte
- **Backend (epository.py, ebuild_index.py)** : Modification de la signature de _update_deal_index pour inclure l'URL de l'image (stockée sous la clé i). Refactorisation du script de reconstruction de l'index avec une requête paginée (limit(500).offset(...)) pour éviter les timeouts gRPC et les fuites de mémoire.
- **Frontend (useDealsManager.js)** : Mapping de la nouvelle propriété dealData.i vers storageImageUrls lors de la récupération de l'index.
- **Frontend (MapView.jsx)** :
  - Restauration du design compact d'origine très apprécié (plus lisible, sans débordement).
  - Suppression du padding par défaut de Google Maps sur .gm-style-iw-d.
  - Suppression complète du bouton de fermeture (croix) via CSS (.gm-ui-hover-effect { display: none !important; }).
  - Ajout d'une fermeture automatique au survol sortant (onmouseleave="window.closeMapPopup()").
  - Suppression de la disparition de la carte lors du clic sur une annonce.

#### 2. Raisonnement
La carte interactive n'affichait plus les images des annonces car la structure de l'index Firebase (deals_index) n'incluait pas l'URL des images. En ajoutant cette information compressée, le chargement reste très rapide tout en offrant un rendu visuel.
La refonte de la popup MapView a été itérative pour finalement revenir à une ergonomie épurée (hover sur le marqueur, fermeture naturelle en quittant la zone, clic pour ouvrir les détails).
