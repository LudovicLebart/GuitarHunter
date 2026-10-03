# Plan — Héberger le site et les photos sur notre serveur

_Rédigé le 2026-10-02, **relu par Opus le même jour** (corrections intégrées : préfixe de chemin retiré par le Funnel, permissions de `/home`, prérequis du dépôt privé, point de résolution des URLs côté API, audit des consommateurs). **Priorité basse (décision utilisateur) : rien n'est implémenté.** Ce document fixe l'objectif, les faits vérifiés, les étapes, les risques et le retour arrière, pour qu'un futur chantier démarre sans réenquête._

## 1. Pourquoi

_Idée d'origine : `FIRESTORE_MIGRATION_PLAN.md` §4 (« fin de GitHub Pages »), jamais réalisée ; ce plan la remplace avec les faits vérifiés le 2026-10-02._

- **Dépôt GitHub privé.** Il est public aujourd'hui parce que GitHub Pages l'exige sur le plan gratuit (Pages sur dépôt privé : plan Pro, Team ou Enterprise ; et le site reste public même avec un dépôt privé). Des données personnelles ont déjà été poussées (voir `TODO.md`, « Données personnelles dans un dépôt public »).
- **Sortir du payant et des dépendances Google** : la base est déjà sur le serveur (Postgres) ; il reste le site (Pages) et les photos (Firebase Storage). **Seule l'authentification doit rester sur Firebase** (décision utilisateur).

## 2. Deux chantiers, indépendants

| Chantier | Objet | Dépend de |
|---|---|---|
| **S** | Servir le site depuis le serveur, abandonner GitHub Pages, passer le dépôt en privé | rien |
| **P** | Stocker et servir les photos sur le serveur, abandonner Firebase Storage | S1 (serveur web local partagé) |

On peut faire S sans P. P ne se fait pas sans les protections décrites en §5 (sauvegardes) : Google assurait la durabilité des photos, plus nous.

## 3. Faits vérifiés (2026-10-02)

**Réseau et serveur**
- Le serveur est exposé par **Tailscale Funnel** sur `https://serveur.tail16b52e.ts.net` : `/` → API de test (127.0.0.1:8000), `/prod` → API de production (127.0.0.1:8001). Le frontend utilise `VITE_API_BASE_URL=https://serveur.tail16b52e.ts.net` (et `/prod` à la bascule, voir `CUTOVER_RUNBOOK.md`).
- **Le Funnel retire le préfixe du chemin avant de transmettre** (vérifié le 2026-10-02 : `…/prod/openapi.json` → 200 via le Funnel, alors que l'API sur `:8001` répond 404 à `/prod/openapi.json` et 200 à `/openapi.json`). Conséquence : un service monté sur `/app` ou `/photos` reçoit des chemins **sans** ce préfixe, et deux montages ne peuvent pas partager le même port.
- nginx est installé et actif, mais seul le site par défaut existe (port 80, `/var/www/html`). Node n'est pas installé sur le serveur.
- `/home/ludovic` est en `drwxr-x---` (750) : nginx (`www-data`) n'y a aucun accès.
- Le serveur utilise un remote git SSH (`git@github.com:LudovicLebart/GuitarHunter.git`) ; le job `deploy` ne fait un `git clone https://…` qu'au premier déploiement ; le Dell se met à jour par `git fetch`/`reset` (`run_script_dell.yml`, remote non vérifié).
- Disque : 140 Go libres sur 212 Go. Aucune autre machine web : le Dell est le serveur de secours (chantier HA).

**Site**
- Build `npm run build` dans GitHub Actions (job `build`), publié sur la branche `gh-pages` par `peaceiris/actions-gh-pages`, sous `https://ludoviclebart.github.io/GuitarHunter/` (`vite.config.js` : `base: '/GuitarHunter/'`).
- L'API autorise en CORS `https://ludoviclebart.github.io` et `http://localhost:5173` (`backend/api/main.py`).
- Authentification : Firebase Auth (e-mail / mot de passe via le SDK) ; le frontend envoie le jeton en `Authorization: Bearer`, l'API le vérifie. Les clés `VITE_FIREBASE_*` sont dans le secret `DOT_ENV` et publiques par conception.

**Photos**
- **16 949 photos sur 4 198 annonces** en production (`guitar_deals.storage_image_urls`) ; 7 625 annonces au total (les autres n'ont pas de photo stockée). Taille moyenne d'un échantillon de 25 photos : 50 Ko (max 126 Ko) → **≈ 850 Mo au total** (estimation, à mesurer sur le bucket).
- Deux formes d'URL : 16 932 en `https://storage.googleapis.com/guitarehunter-d6e35.firebasestorage.app/deals/...` (posées par le bot, publiques via `make_public()`), **17** en `https://firebasestorage.googleapis.com/v0/b/...` avec jeton (posées par le navigateur : photos de chat et plan de restauration, via `getDownloadURL`).
- Tables qui référencent Firebase Storage : `guitar_deals` (6 588 lignes, colonnes `storage_image_urls`, `storage_image_gs_uris` et autres champs), `shared_deals` (30), `deal_chat` (8, pièces `gs://`), `restoration_plan_items` (1).
- Écriture par le bot : `PostgresRepository.upload_images_to_storage` (`pg_repository.py`) ; par le site : `src/services/storageService.js` (`uploadChatPhotoToDealStorage`, plan de restauration), encadré par `storage.rules` (création seule, préfixes `chat_` / `restoration_`, < 5 Mo, `image/*`, jamais d'écrasement).
- Le chat Gemini lit les photos par `fetch()` du navigateur puis les envoie en base64 (`inlineData`) : l'accès direct par `gs://` ne marche pas avec le backend configuré (`ARCHITECTURE.md`). Le bucket a dû recevoir une configuration CORS pour cela (2026-08-01) : **notre serveur devra envoyer les mêmes en-têtes CORS sur les photos**.
- Page de partage publique (`SharedDealPage`) : lit les photos sans authentification.
- Scripts existants dans le dépôt : `migrate_images.py` (re-scrape Facebook vers Firebase, ancien), `backfill_gs_uris.py` (liste les blobs du bucket).

## 4. Chantier S — le site sur le serveur

**Cible** : `https://serveur.tail16b52e.ts.net/app/`, servi par un nginx local, derrière le Funnel existant. Les chemins `/` et `/prod` (API) ne changent pas.

| # | Étape | Détail | Critère |
|---|---|---|---|
| S0 | Vérifications côté Google (utilisateur) | Console Firebase → Authentication → domaines autorisés : ajouter `serveur.tail16b52e.ts.net`. Console Google Cloud → restrictions éventuelles de la clé d'API web (référents HTTP limités à `github.io` bloqueraient la connexion). | une connexion de test réussit depuis la nouvelle origine |
| S1 | Serveur web local | Dossier **`/srv/guitarhunter/`** (pas `~` : voir ci-dessus), propriétaire `ludovic`, groupe partagé lisible par `www-data`. Nouveau `/etc/nginx/conf.d/guitarhunter-site.conf` : serveur sur `127.0.0.1:8090` qui sert le site **à la racine** (`root /srv/guitarhunter/site/current`, repli SPA `try_files … /index.html`, compression, `Cache-Control: immutable` pour `assets/*`, `no-cache` pour `index.html`) ; **le site par défaut n'est pas modifié**. Puis `tailscale serve --bg --set-path /app http://127.0.0.1:8090` (Funnel inchangé). Vite garde `base: '/app/'` : le navigateur demande `/app/assets/…`, le Funnel retire `/app`, nginx voit `/assets/…`. | `curl https://…/app/` renvoie l'`index.html` et `…/app/assets/<fichier>` le fichier |
| S2 | Base du site paramétrable | `vite.config.js` : `base: process.env.VITE_BASE \|\| '/GuitarHunter/'`. Pages et serveur coexistent pendant la transition. | deux builds possibles |
| S3 | Déploiement CI | Nouveau job : build avec `VITE_BASE=/app/`, copie de `dist/` dans `/srv/guitarhunter/site/releases/<sha>/` (rsync par SSH via Tailscale, comme le job `deploy` existant), puis bascule atomique du lien `/srv/guitarhunter/site/current`. **Retour arrière = repointer le lien.** Conserver les 5 dernières versions. | un push produit une version accessible |
| S4 | CORS | Ajouter `https://serveur.tail16b52e.ts.net` aux origines de `backend/api/main.py` (même origine : sans effet, mais utile en développement) ; retirer `github.io` seulement à S6. | pas d'erreur CORS |
| S5 | Recette | Site de test en parallèle de Pages : connexion, liste, carte, chat, partage public, WebSocket des logs, téléphone. | checklist signée par l'utilisateur |
| S5 bis | **Prérequis au passage en privé** | Vérifier le remote git et l'accès de **chaque machine** qui clone ou met à jour le dépôt : serveur (SSH : une clé enregistrée sur le dépôt, ou une clé de déploiement en lecture seule, à tester), Dell (remote de `run_script_dell.yml` et des scripts d'installation), job `deploy` (le `git clone https://…` du premier déploiement échouerait sur un dépôt privé : le remplacer par SSH ou un jeton en lecture). Tester une mise à jour réelle **avant** de changer la visibilité. | un `git fetch` réussit sur chaque machine avec le dépôt en privé (test à blanc possible sur un dépôt miroir privé) |
| S6 | Bascule | Communiquer la nouvelle adresse aux utilisateurs (7 lignes dans la table `users`, dont d'éventuels comptes de test : à vérifier) ; supprimer l'étape « Deploy to GitHub Pages » de `deploy.yml` ; supprimer la branche `gh-pages` ; **passer le dépôt en privé** ; retirer `github.io` du CORS. | Pages éteint, dépôt privé |

**Points d'attention S**
- Le job `deploy` se déclenche sur `master` **et** `dev` ; décider quelle branche publie le site (aujourd'hui, le job `build` de Pages suit le même déclencheur).
- **Dépôt privé** : minutes GitHub Actions gratuites limitées (2 000 / mois sur le plan gratuit) ; le workflow tourne deux fois par push. Vérifier la consommation avant S6.
- **Historique déjà public** : passer en privé n'efface pas ce qui a pu être copié. La purge de l'historique reste une décision séparée.
- **HA** : le site doit aussi être servi par le Dell en cas de bascule (même nginx, même rsync) ; à intégrer au runbook HA.
- **Chemins des services** : un montage `tailscale serve --set-path` par service, **chacun sur son port local** (site `:8090`, photos `:8091`) ; ne jamais monter deux chemins sur le même port.
- Les anciens favoris `github.io` cesseront de fonctionner à S6.

## 5. Chantier P — les photos sur le serveur

**Cible** : dossier `/srv/guitarhunter/photos/deals/{dealId}/{fichier}` (**mêmes chemins relatifs que le bucket**), servi en lecture publique par nginx (second serveur local, monté sur `/photos`) (comme aujourd'hui : `make_public`, noms aléatoires), écrit par le bot et par l'API.

| # | Étape | Détail | Critère |
|---|---|---|---|
| P0 | Inventaire exact | Lister le bucket (service account déjà sur le serveur) : nombre d'objets, taille totale, hors `deals/`. Lister tous les motifs d'URL en base (4 tables + `guitar_deals` hors `storage_image_urls`). | rapport chiffré, aucun écart avec la base |
| P1 | Stockage et service | Dossier `/srv/guitarhunter/photos/deals/{dealId}/{fichier}` ; droits : lecture pour `www-data`, écriture pour l'utilisateur du bot et de l'API de **production** seulement. Second serveur nginx sur `127.0.0.1:8091` qui sert ce dossier **à la racine** (`root /srv/guitarhunter/photos`), `Access-Control-Allow-Origin` pour l'origine du site, `Cache-Control: public, max-age=31536000, immutable`, pas de listing. Puis `tailscale serve --bg --set-path /photos http://127.0.0.1:8091`. Vérifier aussi les **limites de débit du Funnel** (en plus de la bande passante montante résidentielle). | une photo test se charge à `…/photos/deals/…`, et `fetch()` depuis le site fonctionne |
| P2 | Envoi par l'API | `POST /deals/{id}/photos` (multipart, authentifié) qui reprend **les règles de `storage.rules`** : création seule (jamais d'écrasement), préfixe `chat_` / `restoration_`, < 5 Mo, type vérifié sur les octets (pas seulement l'en-tête), nom `…_{uuid}.jpg`, quota par utilisateur. `storageService.js` appelle cet endpoint. | mêmes refus qu'avant sur les cas limites (tests) |
| P3 | Écriture locale par le bot, **double écriture** | `upload_images_to_storage` écrit sur disque ; interrupteur `PHOTOS_BACKEND = firebase \| both \| local`. En `both`, Firebase reste complet : c'est le filet de sécurité. | nouvelles annonces visibles avec les deux URL |
| P4 | Copie de l'existant | Script reprenable et idempotent : copie chaque objet `deals/**` du bucket vers le disque, compare le MD5 (`md5Hash` de GCS), débit limité, `--dry-run`, rapport. **Aucune modification de la base.** | 100 % des objets copiés, MD5 identiques |
| P5 | Vérification | Chaque URL de la base (toutes tables) doit avoir son fichier local ; **audit des consommateurs dans le code** (`grep` de `storage.googleapis`, `storage_image_urls`, `storageImageUrls`, `image_urls` dans `backend/`, `backend/scripts/`, `main.py`) : (a) chemins applicatifs : réanalyse `ANALYZE_DEAL` (`bot.py` ~l.1183 : `storageImageUrls` re-téléchargées par l'analyseur), `bot.py` ~l.1527 (notifications), `analyzer._download_and_optimize_image` ; (b) scripts de rejeu et d'export (`compare_qwen_local_vs_prod.py`, `export_dataset_a.py`, `export_neck_reset_sample.py`, `refresh_images.py`, `rebuild_index.py`, `reanalyze_sold_deals.py`, `study_visual_dependence.py`, `download_phase1_images.py`) ; (c) fichiers `dataset_a_*.jsonl` (URLs du bucket). Chacun est classé « bascule vers lecture locale » ou « casse acceptée » dans le rapport ; échantillon visuel ; cas des 17 URL à jeton ; traitement des pièces `gs://` historiques de `deal_chat` (8 lignes : réécriture ponctuelle ou acceptation de la perte d'affichage). | zéro URL orpheline |
| P6 | Bascule en lecture | **Résolution à la sortie de l'API** (pas dans `deal_mapping.py`, qui ne sert que le bot) : une fonction unique `resolve_photo_url()` appliquée à tout ce que l'API renvoie comme URL de photo — `deals_repo` (liste allégée `/deals/index` construite en SQL, détail), `shared_repo` (partage public), `chat_repo` (pièces de chat), restoration — **par simple remplacement du préfixe connu** (`https://storage.googleapis.com/<bucket>/` et `https://firebasestorage.googleapis.com/v0/b/<bucket>/o/…` → `PHOTOS_BASE_URL`), **sans** `stat` fichier par fichier (coûteux sur `/deals/index`) ; la vérification de présence est faite en P5. Pas de réécriture de masse de la base : l'interrupteur vide `PHOTOS_BASE_URL` et on revient. Changer de nom de domaine ou basculer vers le Dell devient un changement de configuration. | le site affiche les photos locales ; retour arrière testé |
| P7 | Observation et nettoyage | Après 2 à 4 semaines sans incident : `PHOTOS_BACKEND=local`, retirer l'étape « règles Storage » de `deploy.yml`, `storage.rules`, la dépendance `firebase/storage` du site. **Le bucket n'est vidé qu'après une copie vérifiée sur une seconde machine et ton accord explicite.** | Firebase = authentification seule |
| P8 | Durabilité (à faire **avant** P6) | Sauvegarde quotidienne du dossier vers le Dell (rsync) avec rétention, ajoutée au runbook HA et surveillée comme `backup_postgres.py` ; idéalement une copie hors site. | restauration d'une photo testée |

**Points d'attention P**
- **Perte de la durabilité Google** : disque unique. P8 n'est pas optionnel.
- **Bande passante montante résidentielle** (déjà un souci noté pour l'API, `main.py`) : galeries jusqu'à 10 photos × 50 Ko ; l'index de la liste n'envoie que la première photo. Le cache navigateur `immutable` est essentiel. Vignettes : hors périmètre, à reconsidérer si la latence gêne.
- **Exposition publique inchangée** : photos lisibles sans compte (page de partage), noms aléatoires. Un contrôle d'accès par jeton signé serait un chantier ultérieur.
- Le bot et l'API tournent sous deux services ; les deux doivent pouvoir écrire dans le dossier (droits Unix) ; l'API de test (`:8000`) ne doit pas écrire dans le dossier de production.
- Photos Facebook expirées : `migrate_images.py` (re-scrape) reste un outil à part, non réutilisé ici.

## 6. Ordre, effort, priorité

Ordre : **S0 → S1 → S2 → S3 → S4 → S5 → S6**, puis **P0 → P1 → P8 → P2 → P3 → P4 → P5 → P6 → P7**. Estimation grossière : S ≈ 1 jour de travail réparti sur quelques sessions ; P ≈ 3 jours plus 2 à 4 semaines d'observation. **Priorité basse** : à lancer quand les chantiers Portier/détecteur de parties laissent de la place, ou plus tôt si la question des données personnelles dans l'historique public devient pressante (S6 la règle en grande partie).

## 7. Risques et retour arrière

| Risque | Parade |
|---|---|
| Connexion impossible depuis la nouvelle origine (domaine autorisé, clé d'API) | S0 en premier ; Pages reste en ligne jusqu'à S6 |
| Panne du serveur = site indisponible | l'API l'est déjà ; intégrer le site au basculement vers le Dell |
| Photos perdues (disque) | P8 avant P6 ; bucket conservé jusqu'à une copie vérifiée |
| URL ou pièces `gs://` oubliées dans une table | P0/P5 : inventaire exhaustif et vérification avant bascule |
| Écrasement ou envoi abusif de fichiers via l'API | règles de `storage.rules` reprises + tests + quotas (P2) |
| Régression du chat Gemini (CORS, base64) | recette P1 : `fetch()` depuis le site vers `/photos/` |
| Quota de minutes GitHub Actions en dépôt privé | mesurer avant S6 |
| Mises à jour du serveur, du Dell ou du premier déploiement impossibles une fois le dépôt privé | S5 bis : tester l'accès git de chaque machine avant de changer la visibilité |
| nginx renvoie 403 (dossier sous `/home`) ou 404 (préfixe de chemin) | dossiers sous `/srv/guitarhunter/`, un port local par montage, test `curl` dès S1/P1 |

**Retour arrière** : S → repointer `~/site/current` ou réactiver Pages tant que `gh-pages` existe (avant S6) ; P → `PHOTOS_BASE_URL=''` (lecture) et `PHOTOS_BACKEND=firebase`, grâce à la double écriture et au bucket intact jusqu'à P7.

## 8. Questions ouvertes

- Quelle branche publie le site (`master` seule ?).
- Nom de domaine personnalisé (Cloudflare, etc.) ou rester en `.ts.net` ?
- Faut-il aussi mettre `/` (aujourd'hui l'API de test) sous un autre chemin, pour que le site soit à la racine ?
- Quota de minutes Actions réellement consommé par mois.
- Taille réelle du bucket (P0) et existence d'objets hors `deals/`.
