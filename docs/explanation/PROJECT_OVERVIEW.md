# Guitar Hunter AI - Vue d'ensemble du Projet

## 🎯 Objectif
Guitar Hunter AI est une application automatisée conçue pour surveiller, analyser et évaluer les annonces d'équipements de musique (Guitares, Amplis, Étuis) sur Facebook Marketplace en temps réel. Son but est d'identifier les "bonnes affaires" (sous-évaluées, potentiel de revente, projets de lutherie) grâce à une analyse par Intelligence Artificielle (Google Gemini) pilotée par une expertise de Maître Luthier.

## 🛠 Stack Technique

### Backend (Python)
- **Core:** Python 3.x
- **Scraping:** Playwright (via `FacebookScraper`) pour l'extraction de données.
- **AI Analysis:** Google Gemini API (Modèles Flash/Pro) pour l'évaluation des annonces.
- **Database:** Firebase Firestore (NoSQL) pour le stockage des annonces, des configurations et des commandes.
- **Architecture:** "Backend as a Service" (BaaS). Le backend agit comme un worker qui écoute Firestore.

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
   - **Portier (Gatekeeper) :** Modèle ultra-rapide (Gemini Flash-Lite) pour filtrer le "bruit" (versions, services, arnaques).
   - **Analyste :** Modèle rapide (Gemini Flash) pour structurer les données et attribuer 5 scores critiques (Deal, Authenticité, État, Liquidité, Intérêt Restauration).
   - **Expert Pro :** Modèle haute-précision (Gemini Pro) déclenché conditionnellement (prix élevé, anomalie de score, verdict 'COLLECTION') pour une expertise chirurgicale.
4. **Stockage:** Les résultats sont poussés dans Firestore (`guitar_deals`).
5. **Affichage:** Le Frontend écoute Firestore en temps réel et affiche les résultats sous forme de cartes interactives.
6. **Actions:** L'utilisateur interagit (Favori, Rejet, Réanalyse, Stop Bot) via le Frontend, qui écrit des commandes dans Firestore (`commands`), écoutées par le Backend.

## 📂 Structure des Dossiers Clés
- `/src`: Code source Frontend (React).
- `/backend`: Code source du Bot Python, Scraper et Analyzer.
- `/docs`: Documentation du projet (Architecture, Journal).
- `main.py`: Point d'entrée du Backend.
- `firestore.rules`: Règles de sécurité de la base de données.
