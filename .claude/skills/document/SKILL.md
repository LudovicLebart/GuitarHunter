---
name: document
description: Mettre à jour la documentation du projet après une modification validée
argument-hint: [description optionnelle des changements]
---

Mets à jour la documentation du **projet courant** en reflétant les modifications qui viennent d'être validées.

Chaque projet a sa propre convention documentaire — ne la présume jamais, découvre-la.

## 1. Trouver la convention du projet (obligatoire, avant toute édition)

1. Cherche un `CLAUDE.md` (ou `AGENTS.md`) à la racine du projet.
   - S'il liste des fichiers/dossiers de documentation précis (ex: une étape "Documentation" avec des chemins explicites) → **suis-les exactement**, y compris le format de journal indiqué (le format varie d'un projet à l'autre : entrée unique en tête de fichier, sous-dossier par mois, par semaine, etc. — regarde un exemple existant dans le fichier avant d'écrire).
2. Si rien n'est précisé dans `CLAUDE.md`/`AGENTS.md`, inspecte le dossier `docs/` du projet :
   - Structure Diataxis présente (`docs/reference/`, `docs/explanation/`, `docs/how-to/` ou `docs/tutorials/`, `docs/management/`) → respecte ces catégories (journal/TODO dans `management/`, architecture/specs dans `reference/`, vision/stratégie dans `explanation/`, guides pratiques dans `how-to/`).
   - Sinon, fichiers plats habituels (`docs/JOURNAL.md` ou `CHANGELOG.md`, `docs/TODO.md`, `docs/ARCHITECTURE.md`, etc.) → édite ces fichiers directement, sans inventer de sous-dossiers.
3. Si le projet n'a ni `CLAUDE.md`/`AGENTS.md` ni `docs/`, demande à l'utilisateur où consigner le changement plutôt que de créer une structure arbitraire.

## 2. Journal (obligatoire s'il existe un fichier de journal/changelog dans le projet)

Ajoute une entrée décrivant l'action effectuée et son résultat, dans le **format déjà utilisé** par ce fichier (ne pas imposer un format d'un autre projet). À défaut de convention existante, utilise :

```
[DATE] [MODÈLE] Action effectuée → Résultat.
```

## 3. Autres fichiers à mettre à jour si concernés

- TODO / backlog du projet — cocher les tâches résolues, ajouter les nouvelles
- Documents d'architecture / pipeline de données / modèles d'état — si un composant ou un schéma change
- Documents de vision / stratégie — si la roadmap évolue
- `README.md` — si l'usage, l'installation ou l'architecture globale change
- Tout autre fichier de `docs/` directement impacté par les changements

## Règles

- Ne modifier que ce qui est réellement impacté. Ne pas tout réécrire.
- Ne jamais imposer la convention documentaire d'un autre projet ; toujours suivre celle déjà en place ici.
- Utiliser l'outil Edit (jamais echo/sed/cat en Terminal).
- Si $ARGUMENTS est fourni, l'utiliser comme contexte pour les entrées de journal.
