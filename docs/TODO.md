# Liste des Tâches - Guitar Hunter AI

Ce document sert à suivre les tâches à accomplir, les bugs à corriger et les améliorations prévues.

**Consigne pour l'Assistant AI :**
- Consultez ce fichier au début de chaque session.
- Ajoutez-y les nouvelles tâches définies lors des discussions avec l'utilisateur.
- Marquez les tâches comme `[x]` une fois qu'elles sont terminées et validées.
- Déplacez les tâches terminées dans la section "Terminé" si la liste devient trop longue.

---

## 🚨 Priorité Haute (Bugs & Correctifs)

- [ ] **Bug : Liens d'images Facebook expirés ("URL signature expired")**
    - *Détails :* Les liens CDN de Facebook (`scontent.fbcdn.net`) sont temporaires et signés. Sur les annonces stockées depuis plusieurs jours, les images ne s'affichent plus dans l'UI alors qu'elles sont toujours sur FB.
    - *Pistes :* Nécessite un mécanisme de stockage pérenne. 4 Options :
        - **Option 1 (Recommandée) : Firebase Storage.** Le bot télécharge et héberge les bonnes images sur Firebase (gratuit jusqu'à 5Go, optimisé par compression/filtrage).
        - **Option 2 : Re-Scraping Dynamique.** Le bot revisite la page FB si l'image casse (Coûteux, et l'image est perdue si l'annonce FB est vendue entre-temps).
        - **Option 3 : Base64 dans Firestore.** Lourd et limite Firestore (1Mo max). Écarté.
        - **Option 4 : Auto-Hébergement sur Serveur Ubuntu.** Espace illimité, mais requiert que le serveur expose les images via un lien **HTTPS public** (nom de domaine + SSL) à cause du *Mixed Content* de GitHub Pages. En attente de vérification technique de l'infrastructure de l'utilisateur.

- [ ] **Problème de la double connexion API (Feature future) :**
    - *Détails :* À lister si le besoin s'en fait sentir.

---

## 🧹 Maintenabilité & Dette Technique

- [ ] **Problème à documenter...**
    - *Détails :* ...

---

## 🎨 Interface Utilisateur (UI/UX)

- [ ] **Revoir l'affichage du bloc de prix**
    - *Détails :* Continuer d'affiner le composant `PriceDisplay` dans `DealCard.jsx`. Objectif : affichage clair, compact et informatif sur mobile et desktop.

- [ ] **Ajouter un bouton de sauvegarde explicite pour les prompts**
    - *Détails :* Actuellement, chaque `onBlur` sur un champ du `PromptListEditor` déclenche une sauvegarde immédiate dans Firestore. Envisager un bouton "Sauvegarder" avec confirmation pour éviter les sauvegardes accidentelles.

---

## 🧠 Système de Prompts & IA

### 🔴 Fiabilité de l'Éditeur de Prompts

- [ ] **Ajouter une validation des prompts avant sauvegarde**
    - *Détails :* L'éditeur ne vérifie pas si l'utilisateur a cassé la structure JSON attendue dans `mainAnalysisPrompt`. Implémenter une détection de la présence du bloc `### FORMAT DE RÉPONSE JSON STRICT` et afficher un avertissement si absent. Ajouter un bouton "Réinitialiser cette section" par prompt.

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
