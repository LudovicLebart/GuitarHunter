# Guitar Hunter AI - Vue d'ensemble du Projet

## 🎯 Objectif
Guitar Hunter AI est une application automatisée conçue pour surveiller, analyser et évaluer les annonces d'équipements de musique (Guitares, Amplis, Étuis) sur Facebook Marketplace en temps réel. Son but est d'identifier les "bonnes affaires" (sous-évaluées, potentiel de revente, projets de lutherie) grâce à une analyse par Intelligence Artificielle (tri par un modèle local Qwen3-VL, analyse par Google Gemini) pilotée par une expertise de Maître Luthier.

## 🛠 Stack Technique

### Backend (Python)
- **Core:** Python 3.x
- **Scraping:** Playwright (via `FacebookScraper`) pour l'extraction de données.
- **AI Analysis:** modèle local **Qwen3-VL (Ollama, sur le Dell)** pour le Portier, avec Qwen cloud en secours ; Google Gemini API (Modèles Flash/Pro) pour l'Analyste et l'Expert.
- **Database:** **Postgres** sur le serveur du projet (annonces, configurations, commandes, journaux d'usage IA), depuis la bascule de septembre 2026. Firestore n'est plus la base.
- **API:** FastAPI (`backend/api/`), exposée par Tailscale Funnel ; authentifie le Frontend par jeton Firebase Auth.
- **Services Firebase restants:** Auth (connexion) et Storage (photos des annonces, pour l'instant ; sortie prévue dans `docs/management/plans/SELF_HOSTING_SITE_AND_PHOTOS_PLAN.md`).
- **Architecture:** le backend est un worker (un thread par utilisateur) qui lit et écrit Postgres et exécute les commandes déposées par le Frontend.

### Frontend (React)
- **Framework:** React (Vite)
- **Styling:** Tailwind CSS
- **State Management:** Context API (`DealsContext`, `BotConfigContext`)
- **Icons:** Lucide React
- **Maps:** Leaflet (via `react-leaflet`)

## 🔄 Flux de Données Global
1. **Scraping:** Le Bot Python scanne Marketplace selon des critères définis (Ville, Prix, Mots-clés).
2. **Filtrage:** Un premier filtrage local élimine les doublons et les exclusions.
3. **Analyse IA:**
   - **Portier (Gatekeeper) :** Modèle rapide (Qwen3-VL en local sur le Dell, Qwen cloud en secours ; Gemini Flash-Lite jusqu'au 2026-09-29) pour filtrer le "bruit" (accessoires seuls, services, arnaques) et, avec la Recherche Active, ne promouvoir à l'Analyste que les familles recherchées.
   - **Analyste :** Modèle rapide (Gemini Flash) pour structurer les données et attribuer 5 scores critiques (Deal, Authenticité, État, Liquidité, Intérêt Restauration).
   - **Expert Pro :** Modèle haute-précision (Gemini Pro) déclenché conditionnellement (prix élevé, anomalie de score, verdict 'COLLECTION') pour une expertise chirurgicale.
4. **Stockage:** Les résultats sont écrits dans Postgres (table `guitar_deals`) ; les photos sont envoyées à Firebase Storage.
5. **Affichage:** Le Frontend interroge l'API (REST) et reçoit un signal WebSocket quand quelque chose a changé ; il affiche les résultats sous forme de cartes interactives.
6. **Actions:** L'utilisateur interagit (Favori, Rejet, Réanalyse, Stop Bot) via le Frontend, qui dépose des commandes par l'API (table `commands`), exécutées par le Backend.

## 📂 Structure des Dossiers Clés
- `/src`: Code source Frontend (React).
- `/backend`: Code source du Bot Python, Scraper et Analyzer.
- `/docs`: Documentation du projet (Diátaxis : `reference/`, `explanation/`, `management/` ; journal hebdomadaire dans `management/journal/`).
- `main.py`: Point d'entrée du Backend.
- `firebase/firestore.rules`, `storage.rules`: règles Firebase historiques (Firestore n'est plus la base ; `storage.rules` protège encore les photos).
