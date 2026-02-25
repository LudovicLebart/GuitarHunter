# run.ps1 - Script de lancement du bot GuitarHunter avec le venv correct
# Usage :
#   .\run.ps1           → Démarre le bot (main.py)
#   .\run.ps1 migrate   → Exécute la migration des images (dry-run par défaut)
#   .\run.ps1 migrate --real → Migration réelle dans Firebase Storage

param(
    [string]$Command = "bot",
    [switch]$Real
)

$VenvPython = ".\venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "❌ Venv introuvable. Créer le venv d'abord : python -m venv venv && .\venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Write-Host "✅ Venv GuitarHunter activé : $VenvPython" -ForegroundColor Green

switch ($Command) {
    "bot" {
        Write-Host "🚀 Démarrage du bot..." -ForegroundColor Cyan
        & $VenvPython main.py
    }
    "migrate" {
        if ($Real) {
            Write-Host "☁️  Migration RÉELLE des images vers Firebase Storage..." -ForegroundColor Yellow
            & $VenvPython -m backend.scripts.migrate_images
        } else {
            Write-Host "🔍 Migration en mode DRY-RUN (aucune écriture)..." -ForegroundColor Cyan
            & $VenvPython -m backend.scripts.migrate_images --dry-run
        }
    }
    default {
        Write-Host "❓ Commande inconnue : '$Command'. Commandes disponibles : bot, migrate" -ForegroundColor Red
    }
}
