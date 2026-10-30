# Fiches techniques de restauration

Bibliothèque de fiches pratiques, construites au fil des sessions de chat et révisées au besoin.
Destinées à être affichées sur le site et liées depuis les étapes du plan de restauration
(voir `docs/management/plans/RESTORATION_PLAN_PLAN.md`).

## Conventions

- **Une fiche = un fichier Markdown** `docs/fiches/<slug>.md`, en partant de [`_GABARIT.md`](_GABARIT.md).
- **En-tête YAML obligatoire** (slug, titre, catégorie, difficulté, durée, statut, révision) : c'est ce
  que le site lira pour lister et lier les fiches.
- **Chargement en base** : automatique à chaque déploiement (`deploy.yml`) — la source est ce dossier, la base n'en est qu'une copie
  dérivée (ne jamais corriger une fiche en base). À la main : `python backend/scripts/seed_guitar_fiches.py --dry-run` valide (sources,
  renvois, alias, `difficulte` et `duree` obligatoires, marques de `concerne:`), puis sans `--dry-run` écrit ; `DATABASE_URL` à exporter.
- **Images** dans `docs/fiches/img/<slug>/`, nommées `NN-description.jpg`, référencées en chemin relatif.
- **Sources obligatoires** : chaque fiche cite un ou plusieurs liens (sites ou vidéos de luthiers)
  expliquant le problème et la marche à suivre ; signaler quand les sources divergent.
- **Renvois entre fiches** : un sujet qui mérite sa propre procédure devient une fiche à part, citée par
  lien relatif (`[titre](autre-fiche.md)`) ; la fiche appelante ne garde qu'un résumé minimal.
- **Évolution** : on modifie par petits blocs, on met à jour `revision` et on ajoute une ligne à
  l'*Historique des révisions* de la fiche.
- **Statuts** : `brouillon` (rédigé, pas relu) → `en_revision` (en cours de correction) → `validee`
  (relue et confirmée par l'atelier).
- **Dépôt public** : aucune donnée personnelle, aucun titre ni URL d'annonce, aucun identifiant.

## Index

| Fiche | Catégorie | Difficulté | Statut |
|-------|-----------|:----------:|--------|
| [Ajuster l'action](reglage-action.md) | Réglage | 2/5 | brouillon |
| [Ajuster le truss rod](reglage-truss-rod.md) | Réglage | 2/5 | brouillon |

## Fiches envisagées

- Décoller une touche
- Neck reset
