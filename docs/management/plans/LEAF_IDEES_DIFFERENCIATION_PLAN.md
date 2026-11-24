# Leaf Hunter — idées de différenciation (sauvées le 2026-11-24, NON planifiées)

> **Statut : idées seulement.** Décision de l'utilisateur (2026-11-24) : « on sauve juste le plan ». Rien n'est engagé ; chaque piste demande un plan formel (CLAUDE.md, Étape 1) avant tout code.
> **Prudence** : ce document vient d'un échange, pas d'une étude de marché. Les affirmations sur ce que fait la concurrence (sites d'annonces, évaluateurs de prix, rapports d'historique, alertes par mot-clé) viennent de connaissances générales et **n'ont pas été vérifiées**. Dépôt public : aucune annonce réelle, aucun identifiant.

## Ce que Leaf fait déjà et qui est rare
- Chaque affirmation vient avec sa **preuve** : citation exacte du texte, ou numéro de la photo pour un fait lu sur image (garde-fou des preuves).
- **Santé de la batterie** (SOH, barres, Ah) lue dans le texte et les captures LeafSpy : rarement publiée de façon structurée, alors que c'est elle qui fait le prix d'une Leaf.
- **Autonomie hivernale pour l'usage de l'utilisateur** (50 km par jour, hiver québécois, marge), pas une autonomie moyenne.
- Annonces regroupées entre plateformes, doublons marqués, historique de prix, verdict calculé en code, questions au vendeur, prompts éditables.

## Pistes à fort effet de différenciation
1. **Arnaques et photos recyclées** : empreinte perceptuelle des photos (déjà téléchargées en mémoire) pour repérer la même voiture annoncée deux fois ou des photos volées ; recoupement du kilométrage du tableau de bord avec celui de l'annonce (drapeau `photo_km_mismatch` déjà en place pour l'écart > 5 %). *Le plus faisable avec l'existant.*
2. **Prix corrigé par la santé de la batterie** : accumuler année, km, SOH et prix pour estimer ce que vaut une Leaf à 70 % de SOH face à une à 85 % (donnée que personne ne publie ; l'avantage grandit avec le temps). S'appuie sur `price_fit` (régression, minimum 15 comparables).
3. **Coût réel, pas seulement le prix** : prix + risque de remplacement de batterie selon le SOH + borne à domicile + pneus d'hiver, comparé à l'essence. Le prix plafond de l'Expert en est une version simple.
4. **Simulation du trajet de l'utilisateur** : autonomie hivernale sur son parcours avec la température prévue et l'accès à la recharge (aujourd'hui : estimation générale).
5. **Vitesse et préparation** : alerte dans les minutes qui suivent la publication, avec le premier message au vendeur déjà rédigé (questions LeafSpy incluses). **Brouillons seulement, envoyés par l'utilisateur** (envoi automatique : problème de conditions d'utilisation).

## Pistes utiles, de moindre différenciation
6. Aide à l'inspection sur place : guide LeafSpy pas à pas, photos prises sur place comparées à celles de l'annonce (dommages, usure).
7. Fiabilité du vendeur : relistages, baisses de prix successives, temps passé en ligne.
8. Suivi après achat : rappels, entretien, valeur de revente ; les résultats de l'utilisateur servent à corriger les estimations.
9. Autres véhicules électriques d'occasion avec le même socle (particularités de batterie par modèle) ; côté guitares, plans de restauration et fiches déjà en place.

## Ordre recommandé (si l'utilisateur relance le sujet)
1 (photos recyclées + recoupement du kilométrage) → 2 (prix corrigé par la santé) → 5 (rédaction du premier message au vendeur).

## Liens
- Plan d'origine : [`LEAF_HUNTER_PLAN.md`](LEAF_HUNTER_PLAN.md) ; suivi : `../TODO.md`, section Leaf Hunter.
- Reste du plan « s'appuyer sur Guitar Hunter » : fiches techniques Leaf, chat Leaf, temps réel (voir le TODO).
