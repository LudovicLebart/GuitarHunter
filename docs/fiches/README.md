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
  renvois, alias, `difficulte` et `duree` obligatoires, champs d'en-tête inconnus refusés), puis sans `--dry-run` écrit ; `DATABASE_URL` à exporter.
- **Images, visuels, diagrammes (obligatoires)** : une fiche illustre ses étapes, elle n'est pas que du texte. Fichiers dans `docs/fiches/img/<slug>/`, nommés `NN-description.svg` (ou `.jpg`, `.png`, `.webp`), référencés en chemin relatif, placés dans l'étape qu'ils servent. Par défaut : schémas SVG originaux, fabriqués avec la **banque d'éléments** `_banque/` (guitare, sac, hygromètre, repères numérotés… même style partout, voir `_banque/README.md`) ; sinon photos de l'atelier ou images sous licence libre avec crédit. **Jamais d'image copiée d'un site, d'un forum ou de Reddit sans accord** (le dépôt est public). Les liens externes restent un complément. Détail : `docs/how-to/FICHES_TECHNIQUES.md` §4.
- **Sources obligatoires** : chaque fiche cite un ou plusieurs liens (sites ou vidéos de luthiers)
  expliquant le problème et la marche à suivre ; signaler quand les sources divergent.
- **Renvois entre fiches** : un sujet qui mérite sa propre procédure devient une fiche à part, citée par
  lien relatif (`[titre](autre-fiche.md)`) ; la fiche appelante ne garde qu'un résumé minimal.
- **Évolution** : on modifie par petits blocs, on met à jour `revision` et on ajoute une ligne à
  l'*Historique des révisions* de la fiche. Cette section reste **la dernière** de la fiche, avec ce titre exact
  (`## Historique des révisions`) : le site l'affiche dans un panneau repliable, **fermé par défaut**.
- **Statuts** : `brouillon` (rédigé, pas relu) → `en_revision` (en cours de correction) → `validee`
  (relue et confirmée par l'atelier).
- **Dépôt public** : aucune donnée personnelle, aucun titre ni URL d'annonce, aucun identifiant.

## Index

| Fiche | Catégorie | Difficulté | Statut |
|-------|-----------|:----------:|--------|
| [Ajuster l'action](reglage-action.md) | Réglage | 2/5 | brouillon |
| [Ajuster le truss rod](reglage-truss-rod.md) | Réglage | 2/5 | brouillon |
| [Débloquer un truss rod coincé](debloquer-truss-rod.md) | Réglage | 3/5 | brouillon |
| [Mesurer le relief du manche](mesurer-relief-manche.md) | Réglage | 1/5 | brouillon |
| [Régler la hauteur des cordes au sillet de tête](regler-sillet-de-tete.md) | Réglage | 3/5 | brouillon |
| [Régler la hauteur des cordes au chevalet](regler-hauteur-chevalet.md) | Réglage | 3/5 | brouillon |
| [Réparer une fissure dans la table](reparation-fissure-table.md) | Structurel | 3/5 (2 à 5 selon l'état) | en_revision |
| [Nettoyer et dégraisser une fissure avant collage](nettoyer-avant-collage.md) | Structurel | 1/5 | brouillon |
| [Laisser une guitare retrouver une humidité normale](retrouver-humidite-normale.md) | Structurel | 1/5 | brouillon |

## Fiches envisagées

- Décoller une touche
- Neck reset
