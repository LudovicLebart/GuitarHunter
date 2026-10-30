# Comment utiliser les fiches techniques de restauration

Les fiches sont des procédures pratiques (ajuster l'action, régler le truss rod…) écrites en Markdown dans `docs/fiches/`. Elles sont consultables sur le site, liables depuis les étapes d'un plan de restauration et citées par le chat de l'annonce.

**Principe à retenir : la source est Git.** La base Postgres n'en est qu'une copie, réécrite à chaque déploiement. Ne jamais corriger une fiche en base.

## 1. Lire une fiche sur le site

- Liste : `#fiches` (ex. `https://…/#fiches`). Filtrer par catégorie ou chercher par mot.
- Une fiche : `#fiche/<slug>` (ex. `#fiche/reglage-truss-rod`). Table des matières à côté du texte.
- Les badges **statut** (`brouillon`, `en_revision`, `validee`) et **confiance** indiquent la fiabilité : une fiche `brouillon` n'a pas été relue.
- Chaque fiche liste ses **sources** (sites et vidéos de luthiers), avec une note quand elles divergent.

## 2. Lier une fiche à une étape de restauration

1. Ouvrir l'annonce, puis son plan de restauration.
2. Sur une étape (en création ou en édition), choisir la fiche dans le sélecteur « fiche technique ».
3. L'étape affiche alors un lien cliquable vers la fiche. Pour retirer le lien, vider le sélecteur.

Un slug inconnu est refusé par l'API (422) ; si une fiche disparaît, le lien n'est simplement plus affiché.

## 3. Utiliser les fiches dans le chat

- Poser la question normalement (« ma truss rod est coincée, que faire ? »). Les fiches pertinentes sont retrouvées par la question, puis par l'étape du plan, le plan, l'annonce.
- Les fiches trouvées s'affichent en cartes ; le chat les cite avec des liens cliquables et peut les proposer comme `fiche_slug` d'une nouvelle étape.
- Le contexte d'une fiche n'est injecté qu'une fois par conversation.
- Si la recherche de fiches est lente ou en panne (délai 2,5 s), le chat répond quand même, sans fiches.

## 4. Créer une nouvelle fiche

1. Copier `docs/fiches/_GABARIT.md` vers `docs/fiches/<slug>.md` (le slug = nom du fichier sans `.md`, en minuscules et tirets).
2. Remplir l'en-tête, sans champ inconnu :

   | Champ | Valeur |
   |---|---|
   | `slug`, `titre` | identifiant et titre |
   | `categorie` | `structurel`, `cosmetique`, `electronique`, `quincaillerie`, `reglage`, `autre` |
   | `difficulte` | 1 (débutant) à 5 (luthier confirmé), **obligatoire** |
   | `duree` | texte libre, **obligatoire** |
   | `statut` | `brouillon` → `en_revision` → `validee` |
   | `revision` | date `AAAA-MM-JJ` |
   | `alias` | expressions précises qui retrouvent la fiche (éviter les mots seuls trop courants : « action », « manche ») |

3. Écrire le corps : résumé, risques et points de non-retour, outils, étapes, pièges, vérifications finales.
4. **Sources obligatoires** : dans la section « Sources et liens », une ligne par source :
   `- [Éditeur : titre](https://…) : note`. Une source n'est jamais tronquée (note de plus de 300 caractères refusée).
5. Images dans `docs/fiches/img/<slug>/NN-description.jpg`, référencées en chemin relatif : `![légende](img/<slug>/01-nom.jpg)`.
6. Renvoi vers une autre fiche : lien relatif `[titre](autre-fiche.md)` ; la fiche appelante garde un résumé minimal.
7. Dépôt public : aucune donnée personnelle, aucun titre ni URL d'annonce.

## 5. Modifier une fiche

Modifier le fichier par petits blocs, mettre à jour `revision`, ajouter une ligne à l'*Historique des révisions* de la fiche. Passer le statut à `validee` seulement après relecture à l'atelier.

## 6. Valider et publier

Vérifier avant de pousser (n'écrit rien) :

```bash
export DATABASE_URL=...   # base visée
python backend/scripts/seed_guitar_fiches.py --dry-run
```

Le script contrôle les sources, les renvois, les alias, `difficulte` et `duree`, et refuse les champs inconnus.

Publier : pousser sur `dev`. Le déploiement charge les fiches dans chaque base (bot, API prod, API staging) ; l'étape est non bloquante et idempotente. Chargement manuel : même commande sans `--dry-run` ; `--force` réécrit tout, `--prune --yes` supprime les fiches dont le fichier n'existe plus.

Les tests `npm test` et `test_seed_guitar_fiches.py` / `test_fiches_api.py` (job `tests` de `deploy.yml`) bloquent le déploiement s'ils échouent.

## 7. Dépannage

| Symptôme | Cause probable |
|---|---|
| La fiche n'apparaît pas sur le site | Chargement non fait ou refusé : relancer `--dry-run` et lire l'erreur ; vérifier les logs de l'étape de chargement du déploiement |
| Le chat ne cite pas la fiche | Alias trop vagues ou absents ; l'index d'alias se rafraîchit toutes les 30 s |
| Image manquante sur le site | Fichier absent de `docs/fiches/img/<slug>/` (le build affiche un avertissement) |
| Correction en base écrasée | Normal : corriger le fichier Markdown dans Git |
