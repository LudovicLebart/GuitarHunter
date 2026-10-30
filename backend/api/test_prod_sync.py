"""Garde-fou du déploiement de l'API de PRODUCTION : `guitarhunter-api-prod` tourne dans ~/guitarhunter-api-prod, un répertoire
séparé où `.github/workflows/deploy.yml` ne recopie qu'une LISTE de fichiers de backend/ (voir l'étape « Service API PROD »).
Tout module de `backend/` importé (directement ou par ricochet) par `backend/api/*.py` hors de `backend/api/` doit figurer dans
cette liste, sinon l'API de production ne démarre plus après le déploiement (ImportError) alors que tous les tests passent
ici. Cas réel évité : `fiches_repo.py` importe `backend.guitar_knowledge`, absent de la liste (2026-10-30, trouvé en revue).
Sans Postgres ni réseau : analyse statique du code et du workflow."""
import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "deploy.yml")


def synced_backend_files():
    """Fichiers `backend/<x>.py` recopiés par la ligne `cp ... ~/guitarhunter-api-prod/backend/` du workflow."""
    with open(WORKFLOW, encoding="utf-8") as fh:
        text = fh.read()
    copied = set()
    for line in text.splitlines():
        if line.strip().startswith("cp ") and "guitarhunter-api-prod/backend/" in line and "-r" not in line.split()[:2]:
            copied.update(os.path.basename(p) for p in line.split() if p.startswith("backend/") and p.endswith(".py"))
    return copied


def backend_modules_imported(path):
    """Modules `backend.<x>` (hors `backend.api`) importés par un fichier Python."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[0] == "backend" and len(parts) == 1:
                found.update(alias.name for alias in node.names if alias.name != "api")          # from backend import x
            elif parts[0] == "backend" and parts[1] != "api":
                found.add(parts[1])                                                               # from backend.x import y
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "backend" and len(parts) > 1 and parts[1] != "api":
                    found.add(parts[1])
    return found


def required_backend_files():
    """Modules de backend/ nécessaires à l'API (fermeture transitive), sous forme de noms de fichiers."""
    api_dir = os.path.join(ROOT, "backend", "api")
    pending = set()
    for name in os.listdir(api_dir):
        if name.endswith(".py") and not name.startswith("test_"):
            pending |= backend_modules_imported(os.path.join(api_dir, name))
    required = set()
    while pending:
        module = pending.pop()
        required.add(module)
        path = os.path.join(ROOT, "backend", f"{module}.py")
        if os.path.exists(path):
            pending |= backend_modules_imported(path) - required
    return {f"{m}.py" for m in required}


class TestProdApiSync(unittest.TestCase):
    def test_the_prod_api_directory_receives_every_backend_module_it_imports(self):
        copied = synced_backend_files() | {"__init__.py"}
        missing = sorted(required_backend_files() - copied)
        self.assertEqual(missing, [], f"modules de backend/ importés par backend/api mais NON recopiés vers ~/guitarhunter-api-prod "
                                      f"par {os.path.relpath(WORKFLOW, ROOT)} (étape « Service API PROD ») : {missing}")

    def test_the_known_dependencies_are_detected(self):
        """Le détecteur voit bien les deux formes d'import (sinon le test ci-dessus ne garantirait rien)."""
        required = required_backend_files()
        self.assertIn("deal_mapping.py", required)         # from backend.deal_mapping import …  (deals_repo.py)
        self.assertIn("guitar_knowledge.py", required)     # from backend import guitar_knowledge  (fiches_repo.py)
        self.assertNotIn("api.py", required)

    def test_the_workflow_copy_line_is_parsed(self):
        copied = synced_backend_files()
        self.assertIn("deal_mapping.py", copied)


if __name__ == "__main__":
    unittest.main()
