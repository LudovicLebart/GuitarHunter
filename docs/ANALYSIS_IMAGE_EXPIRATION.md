# Analyse : Expiration des Signatures d'Images Facebook

## Problème Identifié
Les URLs d'images extraites directement du CDN de Facebook (`scontent.fbcdn.net`) contiennent un paramètre de signature cryptographique (`oe` pour *expiration* et `oh` pour *hash*). Ces URLs sont temporaires par design et expirent (généralement après 1 à 3 jours). 
Conséquence : le frontend (`DealCard.jsx`) affiche des images brisées lorsque la signature expire, même si l'annonce est toujours active sur le réseau social.

## Options Considérées

### 1. Firebase Storage (Recommandée)
L'approche la plus robuste consiste à télécharger l'image au moment du scraping pour la stocker de manière pérenne et indépendante du cycle de vie de l'URL Facebook.

- **Avantages :** 
  - Intégration native dans notre écosystème existant (nous utilisons déjà Firestore/Firebase SDK).
  - URLs pérennes basées sur le bucket Firebase.
  - Résout nativement le problème critique du *Mixed Content* (HTTPS requis strict sur GitHub Pages), car Firebase fournit un CDN HTTPS par défaut.
  - Possibilité de compresser les images avant l'upload pour économiser le quota gratuit (5Go).
- **Inconvénients :** Nécessite d'implémenter la logique de téléchargement/upload dans le workflow de `handle_deal_found`.

### 2. Auto-Hébergement sur Serveur Ubuntu (Écartée)
L'utilisateur dispose d'un serveur Ubuntu. Nous pourrions sauvegarder les fichiers localement sur le serveur.

- **Avantages :** Espace quasi-illimité et gratuit. Contrôle total.
- **Inconvénients (Bloquants) :** Le frontend étant hébergé sur GitHub Pages (HTTPS imposé), le serveur de stockage doit **impérativement** servir les images via une URL publique HTTPS avec un certificat SSL valide (`https://mon-domaine.com/images/...`). Servir via une adresse IP brute (`http://192.168...`) provoquera un blocage du navigateur (*Mixed Content Block*). L'effort d'infrastructure requis (Reverse Proxy Nginx, nom de domaine, Certbot) est disproportionné par rapport à l'offre Firebase existante.

### 3. Base64 dans Firestore (Écartée)
Encoder directement le binaire de l'image en chaîne de texte Base64 dans le document Firestore `guitar_deals`.

- **Avantages :** Pas de service de stockage externe, requête unique.
- **Inconvénients :** Limite stricte de Firestore à 1Mo/document. Coût en bande passante explosif lors des requêtes Frontend (chaque Deal pèserait lourd). Anti-pattern de conception avec une base NoSQL axée sur l'agilité.

### 4. Re-scraping à l'affichage (Écartée)
Aller chercher la nouvelle URL fraîche à chaque fois qu'une image est affichée.
- *Solution écartée par l'utilisateur.* C'est lent, lourd en bande passante, et inutilement complexe. L'image disparaîtra sitôt l'annonce vendue (perte de l'historique visuel).

## Plan d'Implémentation Validé (Firebase Storage)

1.  **Configuration SDK :** S'assurer que `firebase-admin` dans `database.py` initialise correctement le bucket de stockage de l'application (probablement `gs://guitar-hunter-...appspot.com`).
2.  **Couche Accès Données :** Créer une fonction `upload_image_to_storage(image_url, deal_id)` dans `repository.py` pour orchestrer le flux `requests.get()` -> `bucket.blob().upload_from_string()`.
3.  **Intégration Flux Principal :** Dans `bot.py` (`handle_deal_found`), après l'extraction et *avant* la sauvegarde dans Firestore, déclencher le téléchargement et injecter la nouvelle clé `storageImageUrl` dans les données.
4.  **Frontend Fallback :** Dans `DealCard.jsx`, utiliser `deal.storageImageUrl || deal.imageUrl` pour assurer la tolérance aux pannes le temps de peupler les anciennes annonces (ou accepter que les anciennes expirent).
