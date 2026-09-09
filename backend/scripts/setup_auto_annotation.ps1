param (
    [switch]$SkipOllama = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  Installation du Pipeline Auto-Annotation (YOLO-OBB) " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

# 1. Vérification de l'environnement virtuel Python
Write-Host "`n[1/4] Vérification de Python..." -ForegroundColor Yellow
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "ERREUR: Python n'est pas installé ou n'est pas dans le PATH." -ForegroundColor Red
    exit 1
}

$pythonVersion = python --version
Write-Host "Version détectée : $pythonVersion" -ForegroundColor Green

# 2. Installation des dépendances
Write-Host "`n[2/4] Installation des packages requis..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install ultralytics opencv-python aiohttp requests numpy
Write-Host "Dépendances Python installées." -ForegroundColor Green

# 3. Téléchargement des poids YOLO-OBB
Write-Host "`n[3/4] Téléchargement du modèle YOLOv8n-OBB..." -ForegroundColor Yellow
$modelUrl = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n-obb.pt"
# Chemin à la racine du projet (un dossier au-dessus de backend/scripts/)
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$modelPath = Join-Path $projectRoot "yolov8n-obb.pt"

if (-Not (Test-Path $modelPath)) {
    Write-Host "Téléchargement de $modelUrl vers $modelPath..."
    Invoke-WebRequest -Uri $modelUrl -OutFile $modelPath
    Write-Host "Modèle téléchargé avec succès." -ForegroundColor Green
} else {
    Write-Host "Le modèle yolov8n-obb.pt est déjà présent." -ForegroundColor Green
}

# 4. Configuration d'Ollama et du VLM
Write-Host "`n[4/4] Configuration du VLM local (Ollama)..." -ForegroundColor Yellow
if ($SkipOllama) {
    Write-Host "Ignoré via le flag -SkipOllama." -ForegroundColor DarkGray
} else {
    if (Get-Command "ollama" -ErrorAction SilentlyContinue) {
        Write-Host "Ollama détecté. Téléchargement de qwen2.5-vl (peut être long la première fois)..."
        ollama pull qwen2.5-vl
        Write-Host "Modèle Qwen2.5-VL prêt." -ForegroundColor Green
    } else {
        Write-Host "ATTENTION: Ollama n'est pas détecté sur cette machine." -ForegroundColor Red
        Write-Host "Veuillez l'installer manuellement depuis https://ollama.com/" -ForegroundColor Yellow
        Write-Host "Une fois installé, exécutez: ollama pull qwen2.5-vl" -ForegroundColor Yellow
    }
}

Write-Host "`n=======================================================" -ForegroundColor Cyan
Write-Host "  Installation terminée avec succès ! " -ForegroundColor Green
Write-Host "  Pour lancer l'extraction : " -ForegroundColor White
Write-Host "  python -m backend.auto_annotation.main " -ForegroundColor White
Write-Host "=======================================================" -ForegroundColor Cyan
