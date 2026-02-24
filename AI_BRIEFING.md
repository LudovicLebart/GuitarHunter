# AI_BRIEFING

## Section 1 — Identité du Projet
- **Nom du projet :** Guitare Hunter
- **Objectif principal :** Scrapping et analyse IA d'annonce marketplace
- **Stack Technique complète :**
  - **Backend :** Python, Playwright (Scraping), Google GenAI/Gemini (Analyse IA), Schedule (Planification)
  - **Frontend :** React 18, Vite, TailwindCSS
  - **Base de données / Services Cloud :** Firebase (Firestore pour Base de Données, Admin SDK côté Backend Python, Client SDK côté Frontend React)
  - **Notifications :** ntfy.sh
- **Flux de données synthétisé :** Le bot Backend (Python) scrape les données d'annonces sur Facebook via Playwright. Les annonces brutes sont traitées et évaluées par Google Gemini pour l'extraction de métadonnées et la détection d'opportunités. Les résultats sont synchronisés sur Firebase Firestore. Le Frontend (React/Vite) récupère et affiche les annonces depuis Firestore et peut émettre des commandes (ex: REFRESH, CLEANUP, SCAN_URL) traitées de manière asynchrone par la boucle de monitoring du bot. Des notifications push sont envoyées via ntfy.

## Section 2 — Le Cycle de Développement (Protocole Strict en 3 Étapes)
La résolution d'une tâche doit IMPÉRATIVEMENT suivre cet ordre. Tu ne peux pas passer à l'étape suivante sans la validation explicite de l'utilisateur.

- **Étape 1 (Le Plan) :** Analyse la demande et propose un plan d'action technique étape par étape (quels fichiers, quelles fonctions, quelle logique). NE CODE RIEN. Attends l'accord de l'utilisateur.
- **Étape 2 (Le Code) :** Une fois le plan validé, génère les diffs de code. Attends que l'utilisateur teste. NE METS PAS À JOUR LA DOC.
- **Étape 3 (La Documentation) :** UNIQUEMENT APRÈS validation du fonctionnement par l'utilisateur ("C'est bon", "Validé"), mets à jour `docs/JOURNAL.md`, `docs/TODO.md`, `docs/ARCHITECTURE.md`, `docs/DATA_FLOW.md`, et tout autre document nécessaire.
Format du journal : `[DATE] [MODÈLE] Action effectuée → Résultat`.
⚠️ INTERDICTION ABSOLUE : N'utilise jamais de commandes Terminal/CLI (comme `echo`, `sed` ou `cat`) pour mettre à jour la documentation. Tu dois modifier le fichier directement avec tes outils d'édition.

## Section 3 — Protocole d'Aiguillage des Modèles
L'agent recommande [FLASH] ou [PRO] avant chaque tâche :
- **[FLASH] :** Lecture, analyse, recherche dans la doc, rédaction de documentation, réponses simples.
- **[PRO] :** Génération de code complexe, refactoring, debug multi-fichiers, audit.

## Section 4 — Frugalité Chirurgicale
- Interdit d'analyser l'intégralité du code source au démarrage.
- Source de vérité prioritaire : les fichiers du dossier `docs/`.
- Ne lire un fichier source que si la doc ne suffit pas.

## Section 5 — Réponses par Diffs
Interdit de réécrire des fichiers complets.
Fournir uniquement les blocs modifiés :
```javascript
// ... existing code ...
[CHANGEMENT ICI]
// ... existing code ...
```

## Section 6 — L'Aiguillage Systématique (RÈGLE D'ENGAGEMENT PERMANENTE)
Cette règle s'applique à CHAQUE NOUVELLE DEMANDE de l'utilisateur, tout au long de la session. 
Tu as l'interdiction formelle d'exécuter la tâche (qu'il s'agisse de coder, d'analyser, de résumer, d'expliquer ou de répondre à une simple question) sans avoir PRÉALABLEMENT obtenu un accord explicite.

Pour CHAQUE nouvelle requête, ta réponse doit IMPÉRATIVEMENT prendre cette forme exacte et s'arrêter là :

"🚦 **AIGUILLAGE ET PLAN D'ACTION**
- **Périmètre :** [Résumé court de la demande]
- **Modèle Requis :** [Recommande FLASH ou PRO]
- **Le Plan :** [Les étapes de ce que je vais faire ou vérifier pour te répondre]

👉 *Valides-tu ce modèle et ce plan pour que j'exécute la tâche ?*"

⚠️ AUCUNE EXCEPTION : Tu dois absolument attendre le "Oui" ou "Go" de l'utilisateur pour formuler ta réponse finale, faire ton résumé, ou générer ton code.
