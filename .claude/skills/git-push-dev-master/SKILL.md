---
name: git-push-dev-master
description: Documenter, pousser sur dev, merger dans master, retourner sur dev
---

Exécute les étapes suivantes dans l'ordre :

## Étape 1 — Documentation

Exécute le skill /document pour mettre à jour le journal et la documentation.

## Étape 2 — Commit et push sur dev

```bash
git add -A
git status
```

Présente le diff à l'utilisateur et demande confirmation du message de commit.

```bash
git commit -m "<message>"
git push origin dev
```

## Étape 3 — Push dev:master (fast-forward direct)

```bash
git push origin dev:master
```

Ne jamais faire `git checkout master` ni `git merge dev --no-ff` — cela crée un commit de merge sur master absent de dev, causant une divergence qui casse les auto-push.

## Étape 4 — Confirmation

Reste sur dev. Confirme à l'utilisateur : branche active, dernier commit master, dernier commit dev.

## Règles

- Ne jamais pousser sans avoir exécuté /document d'abord.
- Toujours montrer le `git status` avant le commit.
- Ne jamais faire `git checkout master` ni `merge --no-ff` : utiliser `git push origin dev:master`.
- Ne jamais utiliser `--force` sauf demande explicite.
- Ne jamais skipper les hooks (`--no-verify`).
