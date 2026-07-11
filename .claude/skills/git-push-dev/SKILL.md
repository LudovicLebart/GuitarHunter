---
name: git-push-dev
description: Documenter les changements puis pousser sur la branche remote dev
---

Exécute les étapes suivantes dans l'ordre :

## Étape 1 — Documentation

Exécute le skill /document pour mettre à jour le journal et la documentation.

## Étape 2 — Git push vers dev

```bash
git add -A
git status
```

Présente le diff à l'utilisateur et demande confirmation du message de commit.

```bash
git commit -m "<message>"
git push origin dev
```

## Règles

- Ne jamais pousser sans avoir exécuté /document d'abord.
- Toujours montrer le `git status` avant le commit.
- Ne jamais utiliser `--force` sauf demande explicite.
- Ne jamais skipper les hooks (`--no-verify`).
