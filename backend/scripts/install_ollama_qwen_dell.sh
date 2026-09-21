#!/usr/bin/env bash
#
# Chantier I (docs/management/plans/COST_OPTIMIZATION_CHANTIERS.md) — installation d'Ollama +
# Qwen3-VL-8B-Instruct sur le Dell T5810 (RTX 2060 Super, 8 Go VRAM), pour le candidat
# `qwen_local` de backend/benchmark/candidates.py.
#
# À TRANSFÉRER ET EXÉCUTER MANUELLEMENT (pas via run_script_dell.yml/GitHub Actions) :
#   scp backend/scripts/install_ollama_qwen_dell.sh ludovic@100.94.33.54:~/
#   ssh ludovic@100.94.33.54 'bash ~/install_ollama_qwen_dell.sh'
#
# Idempotent : sûr à relancer (installation/pull sautés si déjà en place, override systemd
# réécrit à l'identique). N'installe/ne modifie rien en dehors d'Ollama lui-même — aucun
# contact avec ~/MoneyBot ni son cluster Ray (voir run_script_dell.yml pour cette séparation).
#
# Point d'attention réseau : Ollama n'écoute par défaut que sur 127.0.0.1. Ce script le
# reconfigure pour écouter sur 0.0.0.0:11434 (override systemd), afin d'être joignable depuis
# le reste du tailnet (100.94.33.54:11434, utilisé par backend/benchmark/candidates.py). Ça
# expose l'API Ollama à tout appareil de VOTRE tailnet privé (authentifié, pas Internet public)
# — pas un simple usage local, en connaissance de cause.
#
# Contention GPU : le Dell est aussi utilisé par le cluster MoneyBot (Ray). Ollama décharge un
# modèle inactif de la VRAM après OLLAMA_KEEP_ALIVE (fixé à 5 minutes ci-dessous) — limite
# l'empreinte VRAM aux seules fenêtres d'utilisation réelle, mais une contention reste possible
# si un job MoneyBot tourne au même moment qu'un appel qwen_local.

set -euo pipefail

readonly MODEL_TAG="qwen3-vl:8b"
readonly OLLAMA_PORT=11434
readonly MIN_FREE_DISK_GB=8

log() { echo "--- $1"; }

log "1/7 — Vérification GPU"
if ! command -v nvidia-smi &>/dev/null; then
  echo "ERREUR : nvidia-smi introuvable — pilote NVIDIA absent ou non fonctionnel. Abandon." >&2
  exit 1
fi
gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)
echo "GPU détecté : ${gpu_name}"
if [[ "${gpu_name}" != *"2060"* ]]; then
  echo "AVERTISSEMENT : GPU attendu 'RTX 2060 Super' non confirmé par le nom ci-dessus — la" >&2
  echo "                capacité VRAM (8 Go) suffisante pour Qwen3-VL-8B n'est donc pas garantie." >&2
fi
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

log "2/7 — Espace disque"
free_gb=$(df --output=avail -BG "${HOME}" | tail -n1 | tr -dc '0-9')
if [[ "${free_gb}" -lt "${MIN_FREE_DISK_GB}" ]]; then
  echo "ERREUR : seulement ${free_gb} Go libres dans ${HOME} (${MIN_FREE_DISK_GB} Go requis pour" >&2
  echo "         le modèle quantifié ~4,7 Go + marge). Abandon." >&2
  exit 1
fi
echo "${free_gb} Go libres — suffisant."

log "3/7 — Droits d'administration (nécessaires pour le service systemd Ollama)"
if ! sudo -v; then
  echo "ERREUR : sudo requis pour installer/configurer le service Ollama. Abandon." >&2
  exit 1
fi

log "4/7 — Installation d'Ollama"
if command -v ollama &>/dev/null; then
  echo "Ollama déjà installé ($(ollama --version 2>&1 | head -n1)) — étape sautée."
else
  curl -fsSL https://ollama.com/install.sh | sh
fi

log "5/7 — Configuration réseau (écoute sur 0.0.0.0:${OLLAMA_PORT}, joignable via Tailscale)"
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:${OLLAMA_PORT}"
Environment="OLLAMA_KEEP_ALIVE=5m"
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sudo systemctl restart ollama

log "6/7 — Attente de disponibilité du service (max 30s)"
ready=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${OLLAMA_PORT}/api/tags" &>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "${ready}" -ne 1 ]]; then
  echo "ERREUR : le service Ollama ne répond pas sur 127.0.0.1:${OLLAMA_PORT} après 30s." >&2
  echo "         Diagnostic : sudo systemctl status ollama ; sudo journalctl -u ollama -n 50" >&2
  exit 1
fi
echo "Service Ollama disponible."

log "7/7 — Téléchargement du modèle (${MODEL_TAG}, ~4,7 Go — peut prendre plusieurs minutes)"
ollama pull "${MODEL_TAG}"

echo
log "Test de fumée (requête texte minimale, sans image)"
smoke_response=$(curl -fsS "http://127.0.0.1:${OLLAMA_PORT}/api/generate" \
  -d "{\"model\": \"${MODEL_TAG}\", \"prompt\": \"Réponds uniquement par le mot OK.\", \"stream\": false}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('response', '').strip())")
echo "Réponse du modèle : ${smoke_response}"
if [[ -z "${smoke_response}" ]]; then
  echo "AVERTISSEMENT : réponse vide — le modèle a chargé mais n'a rien renvoyé, à examiner." >&2
fi

echo
log "VRAM après chargement du modèle"
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

echo
echo "========================================================================"
echo "Installation terminée."
echo "Ollama écoute sur 0.0.0.0:${OLLAMA_PORT} (vérifiez l'IP Tailscale de cette machine avec"
echo "'tailscale ip -4' si différente de 100.94.33.54 déjà utilisée ailleurs dans le projet)."
echo
echo "Depuis la machine qui lancera le benchmark (avec TOKENROUTER_API_KEY/ANTHROPIC_API_KEY) :"
echo "  python -m backend.benchmark.run_benchmark --models qwen,qwen_local --limit 10"
echo "========================================================================"
