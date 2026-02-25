---
description: Lancer le bot ou des scripts avec le venv GuitarHunter
---

## Règle absolue

Ne jamais utiliser `python` ou `pip` directement dans ce projet.
Toujours passer par le venv ou le script `run.ps1`.

---

## Lancer le bot

```powershell
.\run.ps1
```

Équivalent à `.\venv\Scripts\python.exe main.py`.

---

## Lancer la migration d'images (dry-run)

```powershell
.\run.ps1 migrate
```

---

## Lancer la migration d'images (réelle)

```powershell
.\run.ps1 migrate --real
```

---

## Exécuter un script Python quelconque

```powershell
.\venv\Scripts\python.exe -m backend.scripts.nom_du_script
```

---

## Installer une dépendance

```powershell
.\venv\Scripts\pip install <package>
# Puis l'ajouter dans requirements.txt
```

---

## Vérifier que le venv est bien utilisé

```powershell
.\venv\Scripts\python.exe -c "import sys; print(sys.executable)"
# Doit afficher un chemin contenant \venv\
```
