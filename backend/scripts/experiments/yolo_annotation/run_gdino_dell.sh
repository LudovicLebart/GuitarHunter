#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# Setup & Run : Auto-annotation Grounding DINO pour GuitarHunter
# À exécuter sur le Dell Linux avec GPU
# ─────────────────────────────────────────────────────────────────────

set -e

echo "═══════════════════════════════════════════════════"
echo "  GuitarHunter — Grounding DINO Auto-Annotation"
echo "═══════════════════════════════════════════════════"

# 1. Créer un venv dédié
if [ ! -d "gdino_env" ]; then
    echo ""
    echo "📦 Création de l'environnement virtuel..."
    python3 -m venv gdino_env
fi

source gdino_env/bin/activate
echo "✅ Environnement activé : $(python3 --version)"

# 2. Installer les dépendances
echo ""
echo "📦 Installation des dépendances..."
pip install --upgrade pip -q
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118 -q 2>/dev/null || \
    pip install torch torchvision -q  # Fallback si CUDA 11.8 n'est pas dispo
pip install transformers accelerate pillow requests -q

# 3. Vérifier CUDA
echo ""
python3 -c "import torch; print(f'🔧 PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()} | GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# 4. Vérifier que le manifest existe
if [ ! -f "dataset_a_phase0.jsonl" ]; then
    echo ""
    echo "❌ ERREUR : dataset_a_phase0.jsonl introuvable !"
    echo "   Copie-le depuis ta machine Windows :"
    echo "   scp dataset_a_phase0.jsonl user@dell:/chemin/vers/ce/dossier/"
    exit 1
fi

# 5. Test rapide sur 5 images
echo ""
echo "═══════════════════════════════════════════════════"
echo "  Phase 1 : Test sur 5 images (avec vérification)"
echo "═══════════════════════════════════════════════════"
python3 auto_annotate_gdino.py --limit 5 --verify --output yolo_dataset_test

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Test terminé !"
echo ""
echo "  Vérifie les images dans yolo_dataset_test/verify/"
echo "  Si c'est OK, lance le dataset complet :"
echo ""
echo "  python3 auto_annotate_gdino.py --limit 300 --output yolo_dataset"
echo "═══════════════════════════════════════════════════"
