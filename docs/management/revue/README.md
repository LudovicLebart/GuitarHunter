# Constats de revue (phase d'analyse après la passe « deepdocument »)

Ce dossier reçoit ce que la relecture du code fait remonter et qui **n'est pas de la documentation** : bugs probables, code mort, doublons, complexité inutile, incohérences doc↔code qu'il vaut mieux corriger dans le code. Un fichier par section : `AAAA-section.md` (ex. `2026-bot.md`).

La doc dit ce qui est ; ici on dit ce qui devrait changer. Rien n'est corrigé pendant la passe : les constats alimentent les code reviews ensuite.

## Format d'un constat

```
### R-<section>-<n> — titre court
- Où : `chemin/fichier.py:ligne`
- Catégorie : bug | code-mort | doublon | simplification | performance | robustesse | sécurité | test-manquant | doc-code
- Gravité : haute | moyenne | basse
- Constat : ce qui est observé, avec la preuve (extrait, appel, valeur).
- Piste : correction envisagée (facultatif).
```

## Règles

- Un constat porte une preuve lue dans le code, pas une impression.
- Un point sans importance pratique (style) n'est pas consigné.
- La synthèse finale (`SYNTHESE.md`) classe tout par gravité et par module avant les reviews.
