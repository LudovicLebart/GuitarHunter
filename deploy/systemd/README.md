# Unités systemd du serveur (R-9-3)

Copies des fichiers de `/etc/systemd/system/` relevés sur le serveur le 2026-11-10, **sans secrets** : les clés restent dans les `EnvironmentFile` (`~/GuitareHunter/.env`, `~/.guitarhunter_prod_db.env`, `~/.guitarhunter_ha.env`), qui ne sont pas dans le dépôt.

| Fichier | Rôle |
|---|---|
| `guitare-hunter.service` | le bot (`main.py` sous `xvfb-run`) |
| `guitarhunter-api-prod.service` | l'API de production (port 8001, base de production) |
| `guitarhunter-ha-watchdog.service` | le démon de haute disponibilité |

L'unité de l'API de test (`guitarhunter-api`, port 8000) est générée par `deploy.yml`.

**Ces fichiers ne sont pas installés par le déploiement** : ils servent de référence pour reconstruire le serveur (`sudo cp deploy/systemd/*.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now <unité>`). Si le serveur change, mettre à jour ces copies. Les fichiers `EnvironmentFile` sont à recréer à la main (noms de variables : voir `docs/reference/exploitation.md`).
