@echo off
chcp 65001 >nul
set PYTHONUTF8=1
:: run.bat - Script de lancement du bot GuitarHunter avec le venv correct
:: Usage :
::   run                   -> Demarre le bot (main.py)
::   run migrate           -> Migration images dry-run
::   run migrate --real    -> Migration images reelle

set VENV_PYTHON=.\venv\Scripts\python.exe

if not exist %VENV_PYTHON% (
    echo [ERREUR] Venv introuvable. Creez-le : python -m venv venv
    exit /b 1
)

if "%1"=="" goto bot
if "%1"=="bot" goto bot
if "%1"=="migrate" goto migrate

echo [ERREUR] Commande inconnue : "%1". Disponibles : bot, migrate
exit /b 1

:bot
echo [GuitarHunter] Demarrage du bot...
%VENV_PYTHON% main.py
goto end

:migrate
if "%2"=="--real" (
    echo [GuitarHunter] Migration REELLE des images...
    %VENV_PYTHON% -m backend.scripts.migrate_images
) else (
    echo [GuitarHunter] Migration DRY-RUN - aucune ecriture...
    %VENV_PYTHON% -m backend.scripts.migrate_images --dry-run
)

:end
