# Liste des Tâches - Guitar Hunter AI

Ce document sert à suivre les tâches à accomplir, les bugs à corriger et les améliorations prévues.

**Consigne pour l'Assistant AI :**
- Consultez ce fichier au début de chaque session.
- Ajoutez-y les nouvelles tâches définies lors des discussions avec l'utilisateur.
- Marquez les tâches comme `[x]` une fois qu'elles sont terminées et validées.
- Déplacez les tâches terminées dans la section "Terminé" si la liste devient trop longue.

---

## 🚨 Priorité Haute (Bugs & Correctifs)

- [x] **Bug : Liens d'images Facebook expirés ("URL signature expired")** *(Corrigé Session 29)*
    - Stockage pérenne via Firebase Storage. Upload systématique lors de chaque `handle_deal_found`.
    - Politique de cycle de vie : purge des images des deals rejetés après 30 jours (`IMAGE_RETENTION_REJECTED_DAYS`).
    - Script de migration one-shot : `backend/scripts/migrate_images.py`.
    - Frontend : fallback `storageImageUrls || imageUrls` dans `DealCard.jsx`.

- [ ] **Bug : Interruption du Scraper par Facebook (Anti-botting)**
    - *Détails :* Playwright est détecté par Facebook lors des tâches asynchrones, qui redirige sur la page d'accueil ou requiert une vérification, empêchant l'extraction des données. Nécessite une solution de contournement (Proxies, Fingerprinting, Stealth plugins...).

- [x] **Bug : Le bot en pause ne se réveille pas via "Rescan All"** *(Corrigé Session 28)*
    - Boucle de pause dans `main.py` sonde désormais Firestore toutes les 5s.
    - Toute commande d'action, et notamment les commandes manuelles asynchrones (REFRESH, SCAN_URL), interrompt la pause.

- [x] **Bug : "Delete All Logs" ne fonctionne pas** *(Corrigé Session 28)*
    - `delete_all_logs` dans `repository.py` réécrite avec `list()` pour forcer la consommation du stream Firestore.

- [x] **Bug : Statut "En attente" pendant le Scraping** *(Corrigé Session 28)*
    - Implémentation de `set_status()` avec `threading.Lock()` et `_active_tasks` dans `GuitarHunterBot` pour gérer les conflits de threads (ex: `run_scan` vs `cleanup_sold_listings`).

- [x] **Bug : Commandes manuelles (Rescan, URL) qui démarrent "tardivement"** *(Corrigé Session 28)*
    - Les commandes `REFRESH`, `REANALYZE_ALL` et `SCAN_URL` s'exécutent désormais dans des threads `daemon` séparés dans `main_loop` pour ne pas bloquer le séquenceur `scheduler.run_pending()`.

- [x] **Brancher la purge lifecycle au scheduler** *(Corrigé Session 29)*
    - `bot.purge_rejected_images()` ajouté comme `purge_func=` dans `TaskScheduler` (`services.py`). Job hebdomadaire déclenché automatiquement au démarrage du bot.

- [x] **Vérifier les règles Firebase Storage** *(Fait)*
    - *Détails :* Confirmer que les blobs uploadés via `blob.make_public()` sont bien accessibles publiquement. Vérifier dans la console Firebase → Storage → Rules que les lectures publiques sont autorisées.

- [/] **Lancer la migration réelle des images** *(En cours)*
    - *Détails :* Migration lancée via `run.bat migrate --real`. Dry-run corrigé.

- [ ] **Problème de la double connexion API (Feature future) :**
    - *Détails :* À lister si le besoin s'en fait sentir.

---

## 🧹 Maintenabilité & Dette Technique

- [ ] **Problème à documenter...**
    - *Détails :* ...

---

## 🎨 Interface Utilisateur (UI/UX) - Priorités Structurelles et Ergonomiques

- [x] **Prototype Mockup V2 (Phase d'Exploration Completée)**
    - *Détails :* Mockup complet avec Dark Mode, Map Split-Screen, et Filtres en cascade. Validé en Session 29-31.
    - [x] **Libérer l'Affichage Desktop (Démantèlement de l'Aside)** *(Ok en Mockup)*
    - [x] **Lisibilité Financière : Badge Marge sur vue liste** *(Ok en Mockup)*
    - [x] **Filtre Drawer : Cascade 4 niveaux** *(Ok en Mockup)*
    - [x] **Refonte du Mobile : Images Full-Width** *(Ok en Mockup)*
- [x] **Réalisme des Images et Galerie (Mockup)** *(Ok en Mockup)*
- [x] **Dark Scrollbar pour les Filtres (Mockup)**
    - *Détails :* Terminé et appliqué aux blocs d'analyses IA et volets latéraux.

- [x] **🚀 Activation V2 — Mockup → Production Ready** *(Complété Session 32)*
    - *Détails :* `MockupDashboard` branché sur `useDealsContext` (données réelles Firestore). `MockupDealCard` câblé sur le vrai modèle `aiAnalysis` (verdict, reasoning, model_used, deal_score, estimated_value) et sur les vraies actions (favori, rejet, suppression, ré-analyse, lien Facebook). Vue MAP remplacée par le vrai `MapView.jsx`. Filtres (`filterType`, `level1-4Filter`, `searchQuery`) synchronisés avec `useDealsManager`. V1 intacte.
- [ ] **Système de Thème (Dark Mode) global**
    - *Détails :* Porter le thème sombre du mockup via un `ThemeContext`.
- [ ] **Dashboard Analytics & Statistiques**
    - *Détails :* Implémenter le moteur de stats (`docs/STATS_REFLEXION.md`).
- [ ] **Créer un Panneau de Statistiques (Dashboard Analytics)**
    - *Détails :* Afficher les KPIs comme le Tunnel de Conversion et un Radar Chart des 5 scores Gemini.
- [ ] **Revoir l'affichage du bloc de prix**
    - *Détails :* Continuer d'affiner le composant `PriceDisplay` dans `DealCard.jsx`. Objectif : affichage clair, compact et informatif sur mobile et desktop.
- [ ] **Ajouter un bouton de sauvegarde explicite pour les prompts**
    - *Détails :* Actuellement, chaque `onBlur` sur un champ du `PromptListEditor` déclenche une sauvegarde immédiate dans Firestore. Envisager un bouton "Sauvegarder" avec confirmation pour éviter les sauvegardes accidentelles.

---

## 🧠 Système de Prompts & IA

### 🔴 Fiabilité de l'Éditeur de Prompts

- [ ] **Ajouter une validation des prompts avant sauvegarde**
    - *Détails :* L'éditeur ne vérifie pas si l'utilisateur a cassé la structure JSON attendue dans `mainAnalysisPrompt`. Implémenter une détection de la présence du bloc `### FORMAT DE RÉPONSE JSON STRICT` et afficher un avertissement si absent.
- [ ] **Ajouter un bouton "Réinitialiser cette section" par prompt**
    - *Détails :* Permettre de revenir aux valeurs par défaut de `prompts.json` individuellement.

### 🟡 Architecture des Prompts

- [ ] **Découper `mainAnalysisPrompt` en sections éditables indépendantes**
    - *Détails :* Le prompt principal est actuellement un bloc monolithique. Le structurer en sous-sections indépendantes dans Firestore et dans l'UI : `Persona & Objectifs`, `Règles de Verdicts`, `Format JSON`. Permet une édition chirurgicale sans risque de tout casser.

- [ ] **Rendre la Taxonomie modifiable via l'interface**
    - *Détails :* Stocker `taxonomy_master` dans Firestore et l'injecter dynamiquement dans `analyzer.py`. Exposed dans le `ConfigPanel` avec un éditeur JSON dédié.

---

## 📊 Statistiques & Dashboard

- [ ] **Mettre en place le moteur de statistiques (Impact Tier 3)**
    - *Plan de travail :* [`docs/STATS_REFLEXION.md`](./STATS_REFLEXION.md)
    - *Objectif :* Exploiter les 5 scores et le funnel pour générer des KPIs financiers (ROI, Marges) et qualitatifs (Profil de marché, Vitesse de rotation).

---

## ✅ Terminé

- [x] Raffinement UI V2 : Modale IA plein écran, MapView auto-centrée, Raccourci Favoris.
- [x] Implémentation du Mockup V2 avec refonte UX totale (Filtres, Stats Dropdown, Navbar, Maps).
- [x] Session 29 : Stockage pérenne des images via Firebase Storage (Backend & UI implémenté).
- [x] Session 29 : Purge automatique hebdomadaire des images rejetées (TaskScheduler).
- [x] Correction: Simplification de la taxonomie (etui_housse) et rejet strict des autres accessoires (ex: pédales, stands).
- [x] Correction: Ajout du 4ème niveau de tri dans FilterBar et affichage des rejets (Session 28).
- [x] Expansion du Scope (Étape 1) : Taxonomie Master (Guitares, Amplis, Étuis).
- [x] Création de la structure de documentation (`docs/`).
- [x] Mise en place du `AI_BRIEFING.md`.
- [x] Refonte responsive de la `DealCard` (Mobile First).
- [x] Analyse approfondie du système de prompts dynamiques (Session 10).
- [x] Nettoyage et restructuration de la racine du projet (Session 15).
- [x] Externalisation des verdicts de rejet (Session 15).
- [x] Refonte du système de nettoyage des annonces vendues (Soft Delete) (Session 16).
- [x] Implémentation du Funnel 3-Tiers (Optimisation Expert Pro) (Session 21).
- [x] "Delete All Logs" : Correction IDs codés en dur (Session 21).
- [x] "Stop Bot" : Injection de `threading.Event` pour arrêt immédiat (Session 21/26).
- [x] Création d'un outil de migration et audit Firestore (Session 21).
- [x] Résolution du conflit de casse Git (`Dev` vs `dev`) (Session 22).
- [x] Correction du rejet systématique des étuis/housses (Session 23).
- [x] Standardisation des instructions de verbosité en format `array of strings` (Session 23).
- [x] Déploiement : Correction du redémarrage automatique et gestion des branches (Session 24).
- [x] Correction "Mode Hors Ligne" : Automatisation via GitHub Secrets (.env & Firebase Key) (Session 25).
- [x] Amélioration du Pilotage : Commandes `STOP_SCAN`, `START_BOT` et Pause 12h (Session 26).
- [x] Refonte UI : Composant `<BotControls />` et indicateur de statut dynamique (Session 26).
- [x] Fiabilisation (Regex PRO) de la détection de disponibilité du Scraper (Session 27).
