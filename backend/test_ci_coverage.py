"""Garde-fou de la CI (R-9-5, 2026-11-08) : la liste des tests lancés par `.github/workflows/deploy.yml` est écrite à la
main, et rien ne rappelait d'y ajouter un nouveau fichier de test. Ce test relève tous les `test_*.py` du dépôt (suivis par Git) et exige que chacun soit soit dans la liste du job `tests`, soit dans `NOT_IN_CI` avec sa raison.
Un nouveau fichier de test oublié, ou une entrée devenue inutile, fait donc échouer la CI au lieu de passer inaperçu.
Sans Postgres ni réseau : analyse statique du dépôt."""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "deploy.yml")

# Fichiers `test_*.py` volontairement hors de la CI : chemin (relatif, séparateurs `/`) -> raison.
NOT_IN_CI = {
    # Essais manuels aux effets réels (R-10-3) : ne jamais les ramasser par une découverte automatique.
    "backend/scripts/test_dell_vision_inference.py": "essai manuel : appelle le Dell et installe des modèles",
    "backend/scripts/test_kijiji_scraper.py": "essai manuel : ouvre un navigateur sur Kijiji",
    "backend/scripts/test_notification.py": "essai manuel : envoie de vraies notifications ntfy et e-mail",
    "test_ntfy.py": "essai manuel à la racine : envoie une vraie notification ntfy",
    # Tests qui ne s'importent pas (R-3-12) : `from scraping…` sans le préfixe `backend.`, à réparer avant de les rajouter.
    "backend/scraping/test_core.py": "ne s'importe pas (ModuleNotFoundError: scraping)",
    "backend/scraping/test_geo_clustering.py": "ne s'importe pas (ModuleNotFoundError: scraping)",
    "backend/scraping/test_scan_loop.py": "ne s'importe pas (ModuleNotFoundError: scraping)",
    "backend/scraping/kijiji/test_kijiji_core.py": "ne s'importe pas (ModuleNotFoundError: scraping)",
    "backend/scraping/kijiji/test_locations.py": "ne s'importe pas (ModuleNotFoundError: scraping)",
    # Détecteur de parties (non branché en production) : numpy, pytest et modèles de vision absents de requirements.txt.
    "tests/auto_annotation/test_config.py": "détecteur de parties : dépendances de vision hors CI",
    "tests/auto_annotation/test_extract_phase1.py": "détecteur de parties : dépendances de vision hors CI",
    "tests/auto_annotation/test_geometry.py": "détecteur de parties : dépendances de vision hors CI",
    "tests/auto_annotation/test_heuristics.py": "détecteur de parties : dépendances de vision hors CI",
    "tests/auto_annotation/test_labelstudio_export.py": "détecteur de parties : dépendances de vision hors CI",
    "tests/auto_annotation/test_post_processing.py": "détecteur de parties : dépendances de vision hors CI",
    "tests/auto_annotation/test_preannotate.py": "détecteur de parties : dépendances de vision hors CI",
    "tests/test_crop_manifest_and_description.py": "détecteur de parties : dépendances de vision hors CI",
    # Expériences de vision (modèles lourds, GPU) : jamais des tests au sens de la CI.
    "backend/scripts/experiments/test_owlv2_parts_detection.py": "expérience de vision (modèle lourd)",
    "backend/scripts/experiments/test_sam2_point_segmentation.py": "expérience de vision (modèle lourd)",
    "backend/scripts/experiments/yolo_annotation/test_dino_parts.py": "expérience de vision (modèle lourd)",
    "backend/scripts/experiments/yolo_annotation/test_gemini_genai.py": "expérience : appelle Gemini",
}


def ci_entries():
    """Modules `backend.x.test_y` et chemins `tests/test_z.py` cités par le workflow, sous forme de chemins de fichiers."""
    with open(WORKFLOW, encoding="utf-8") as fh:
        text = fh.read()
    paths = set()
    for module in re.findall(r"^\s+(backend\.[\w.]*test_\w+)\b", text, re.M):
        paths.add(module.replace(".", "/") + ".py")
    paths.update(re.findall(r"\btests/test_\w+\.py\b", text))
    return paths


def repo_test_files():
    """Fichiers `test_*.py` suivis par Git : ni `venv/`, ni brouillons locaux (un nouveau fichier est vu dès son `git add`)."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--", "*test_*.py"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        # Pas de Git (archive téléchargée, outil absent) : le garde-fou ne peut pas juger, il ne doit pas casser la suite.
        raise unittest.SkipTest(f"git indisponible ou dépôt absent : {exc}")
    return {line.strip() for line in out.splitlines() if os.path.basename(line.strip()).startswith("test_")}


class TestCiCoverage(unittest.TestCase):
    def test_every_test_file_runs_in_ci_or_is_excluded_with_a_reason(self):
        missing = sorted(repo_test_files() - ci_entries() - set(NOT_IN_CI))
        self.assertEqual(missing, [], "fichiers de test absents de la liste du job `tests` de deploy.yml ET de NOT_IN_CI "
                                      f"(backend/test_ci_coverage.py) : {missing}")

    def test_the_exclusion_list_has_no_dead_entry(self):
        files = repo_test_files()
        dead = sorted(p for p in NOT_IN_CI if p not in files)
        listed = sorted(p for p in NOT_IN_CI if p in ci_entries())
        self.assertEqual(dead, [], f"entrées de NOT_IN_CI qui n'existent plus : {dead}")
        self.assertEqual(listed, [], f"entrées de NOT_IN_CI déjà lancées par la CI : {listed}")

    def test_every_ci_entry_exists(self):
        files = repo_test_files()
        gone = sorted(p for p in ci_entries() if p not in files)
        self.assertEqual(gone, [], f"fichiers cités par deploy.yml mais absents du dépôt : {gone}")

    def test_the_workflow_list_is_parsed(self):
        entries = ci_entries()
        self.assertIn("backend/test_bot.py", entries)
        self.assertIn("backend/api/test_api.py", entries)
        self.assertIn("tests/test_replay_t3.py", entries)


if __name__ == "__main__":
    unittest.main()
