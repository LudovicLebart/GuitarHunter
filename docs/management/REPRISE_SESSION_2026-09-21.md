# Fichier de reprise — Chantier I (Qwen local vs prod)

> Écrit le 2026-09-21 pour permettre à une nouvelle session (sur le PC Windows de l'utilisateur)
> de reprendre exactement où celle-ci s'est arrêtée, sans redécouvrir le contexte depuis zéro.
> À lire en premier, avant `CLAUDE.md` (déjà source de vérité générale) et
> `docs/management/plans/COST_OPTIMIZATION_CHANTIERS.md` (détail complet des Chantiers H et I).
> **À supprimer une fois la reprise faite** — ce n'est pas un document permanent du projet.

---

## 1. Où on en est (résumé en une phrase par sujet)

- **Chantier H (bascule T1 Gemini → Qwen)** : actée et codée sur `dev` (commit `62dd938` et
  suivants, 2026-09-20). Reste à faire : le script de comparaison en conditions réelles
  (`qwenGatekeeperVerdict`/`gatekeeperVerdict`) n'a jamais été écrit — TODO.md le liste toujours
  comme ouvert.
- **Chantier I (spécialisation locale — Qwen3-VL-8B sur le Dell)** : Ollama + le modèle sont
  **installés et fonctionnels** sur le Dell (confirmé par l'utilisateur, test de fumée OK, VRAM
  6982/8192 Mio). Un script de comparaison réelle (`compare_qwen_local_vs_prod.py`) est écrit et
  poussé, **mais jamais exécuté** — c'est la prochaine étape concrète (§3).
- Tout le travail de cette session est sur la branche **`claude/gatekeeper-specialized-architecture-s866gq`**,
  poussée sur `origin`. Rien n'a été mergé vers `dev`.

---

## 2. Trois machines distinctes — ne pas les confondre (piège déjà rencontré deux fois)

| Nom | Rôle | Accès |
|---|---|---|
| **Dell T5810** | RTX 2060 Super (8 Go VRAM), héberge `qwen_local` via Ollama. Partagé avec le cluster MoneyBot (Ray). | Tailscale, IP `100.94.33.54`, user `ludovic`. Aussi ciblé par `run_script_dell.yml` (jobs CI ponctuels, `~/GuitareHunter-scripts`). |
| **Lenovo ThinkCentre M720q** ("le serveur de prod", parfois appelé "le Dell" à tort dans d'anciennes sessions — **c'est une confusion historique, ce n'est PAS le Dell T5810**) | Fait tourner le bot de prod (`guitare-hunter`, service systemd) ET, sur la branche `claude/firestore-postgres-migration` (isolée, jamais mergée), un service `guitarhunter-api` (FastAPI) pointé sur une base **Postgres locale `guitarhunter_pg_staging`** (clone complet de Firestore, 6533 annonces au 2026-09-14). | Cible de `deploy.yml`/`run_script.yml` (secrets `SERVER_IP`/`SERVER_USER`, IP Tailscale non confirmée en clair dans les logs — redaction GitHub). |
| **PC Windows de l'utilisateur** | Là où la nouvelle session va tourner. A un accès `git`/`ssh` déjà fonctionnel vers le Dell (testé cette session) — à vérifier vers le ThinkCentre. | — |

**Le script `compare_qwen_local_vs_prod.py` doit tourner SUR le ThinkCentre**, pas sur le Dell
ni sur le PC Windows : la base Postgres n'est joignable qu'en `localhost` (`DATABASE_URL` par
défaut, auth locale sans mot de passe réseau — voir `backend/pg_db.py` sur
`claude/firestore-postgres-migration`).

---

## 3. Prochaine action concrète

Depuis le PC Windows, une fois la nouvelle session ouverte sur le repo (branche
`claude/gatekeeper-specialized-architecture-s866gq`, ou mergée si entretemps validée) :

1. Confirmer l'IP/le nom Tailscale du ThinkCentre (pas encore documenté en clair dans ce repo —
   à demander à l'utilisateur ou à retrouver via `tailscale status` sur une machine du tailnet).
2. Se connecter en SSH avec `-t` (nécessaire pour tout `sudo` interactif — piège déjà rencontré,
   voir §4) et vérifier le chemin du repo cloné là-bas (probablement pas encore sur
   `claude/gatekeeper-specialized-architecture-s866gq` — `git fetch`/`checkout` à faire).
3. Vérifier/installer les dépendances manquantes : `pip install psycopg[binary] openai` (le
   reste — `requests`, `pillow` — est très probablement déjà présent).
4. Vérifier que `.env` existe à la racine du repo sur cette machine (`config.py` exige
   `APP_ID_TARGET` au chargement, sinon `sys.exit(1)`).
5. Lancer :
   ```bash
   python3 -m backend.scripts.compare_qwen_local_vs_prod --limit 15
   ```
6. Lire le résumé affiché + `backend/benchmark/results/compare_qwen_local_vs_prod.json` — le
   chiffre qui compte vraiment : **"Cloud accepte, Local aurait rejeté"** (rappel perdu si
   `qwen_local` devenait un jour LE Portier réel). Un désaccord dans l'autre sens (Cloud rejette,
   Local accepte) est un faux positif à coût négligeable, pas un vrai problème.
7. Documenter le résultat (JOURNAL.md + `COST_OPTIMIZATION_CHANTIERS.md` § Chantier I) une fois
   obtenu — pas avant, conformément au protocole `CLAUDE.md` (doc seulement après confirmation
   de fonctionnement).

---

## 4. Pièges déjà rencontrés cette session (pour ne pas les refaire)

- **CRLF sur un script transféré depuis Windows** : `scp` d'un fichier `.sh` checké out sur
  Windows (`core.autocrlf=true`) y ajoute des `\r`, bash plante dessus (`$'\r': commande
  introuvable`). Corrigé dans `.gitattributes` (`*.sh text eol=lf`) — un futur `git pull`/`scp`
  de script est protégé, mais un fichier déjà présent quelque part avec de mauvaises fins de
  ligne doit être re-téléchargé ou nettoyé (`sed -i 's/\r$//' fichier`).
- **`sudo` via `ssh user@host "commande"` sans TTY** : échoue silencieusement
  ("a terminal is required to read the password"). Toujours utiliser `ssh -t` pour toute
  commande distante qui peut invoquer `sudo` de façon interactive.
- **Ne pas confondre Dell et ThinkCentre** (voir §2) — l'ancienne convention "le Dell" pour
  désigner le serveur de prod est fausse et vient d'une confusion historique déjà documentée sur
  la branche `claude/firestore-postgres-migration`.
- **Ne pas fusionner `claude/firestore-postgres-migration` dans quoi que ce soit** sans demande
  explicite — c'est un chantier volumineux (92 fichiers, 6580 lignes), délibérément isolé,
  explicitement "pas encore prêt" (dernier commit de cette branche). Seule la base Postgres
  qu'elle a produite sur le ThinkCentre est utile ici, pas le code de la branche elle-même.

---

## 5. Fichiers à connaître

- `docs/management/plans/COST_OPTIMIZATION_CHANTIERS.md` — Chantiers H (bascule) et I
  (spécialisation locale) en détail, tenu à jour à chaque étape.
- `backend/scripts/install_ollama_qwen_dell.sh` — déjà exécuté avec succès sur le Dell, pas à
  relancer sauf réinstallation complète (idempotent si besoin).
- `backend/benchmark/candidates.py` — candidat `qwen_local` (harnais générique, moins pertinent
  que le script ci-dessous pour cette comparaison précise, mais reste utile pour d'autres tests).
- `backend/scripts/compare_qwen_local_vs_prod.py` — **le script à exécuter**, voir §3.
- `docs/management/TODO.md` § Audit de fiabilité du Portier T1 — état des tâches ouvertes.
