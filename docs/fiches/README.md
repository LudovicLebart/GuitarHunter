# Fiches techniques de restauration

Bibliothèque de fiches pratiques, construites au fil des sessions de chat et révisées au besoin.
Destinées à être affichées sur le site et liées depuis les étapes du plan de restauration
(voir `docs/management/plans/RESTORATION_PLAN_PLAN.md`).

## Conventions

- **Une fiche = un fichier Markdown** `docs/fiches/<slug>.md`, en partant de [`_GABARIT.md`](_GABARIT.md).
- **En-tête YAML obligatoire** (slug, titre, catégorie, difficulté, durée, statut, révision) : c'est ce
  que le site lira pour lister et lier les fiches.
- **Images** dans `docs/fiches/img/<slug>/`, nommées `NN-description.jpg`, référencées en chemin relatif.
- **Évolution** : on modifie par petits blocs, on met à jour `revision` et on ajoute une ligne à
  l'*Historique des révisions* de la fiche.
- **Statuts** : `brouillon` (rédigé, pas relu) → `en_revision` (en cours de correction) → `validee`
  (relue et confirmée par l'atelier).
- **Dépôt public** : aucune donnée personnelle, aucun titre ni URL d'annonce, aucun identifiant.

## Index

| Fiche | Catégorie | Difficulté | Statut |
|-------|-----------|:----------:|--------|
| [Ajuster l'action](reglage-action.md) | Réglage | 2/5 | brouillon |

## Fiches envisagées

- Décoller une touche
- Neck reset
