"""
Tests unitaires — backend/auto_annotation/extract_phase1.py
Utilise des dossiers temporaires (tmp_path pytest) — aucune dépendance réseau.
"""
import sys
from pathlib import Path
import shutil
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.auto_annotation.extract_phase1 import extraire_echantillon_stratifie


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def create_category_folder(root: Path, name: str, n_images: int) -> Path:
    """Crée un sous-dossier de catégorie avec n_images fichiers .jpg factices."""
    cat_dir = root / name
    cat_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n_images):
        # Fichier JPEG factice (1 octet suffit pour tester le nom)
        (cat_dir / f"img_{i:04d}.jpg").write_bytes(b'\xff\xd8\xff')
    return cat_dir


@pytest.fixture
def dataset_root(tmp_path):
    """Dataset synthétique : 3 catégories avec 100/60/40 images = 200 total."""
    create_category_folder(tmp_path, "electrique", 100)
    create_category_folder(tmp_path, "acoustique", 60)
    create_category_folder(tmp_path, "basse", 40)
    return tmp_path


@pytest.fixture
def output_dir(tmp_path):
    """Dossier de sortie temporaire."""
    return tmp_path / "output"


# ─── Tests extraire_echantillon_stratifie ─────────────────────────────────────

class TestExtraction:

    def test_exact_target_count(self, dataset_root, output_dir):
        """Le nombre exact de fichiers copiés doit égaler total_cible."""
        extraire_echantillon_stratifie(str(dataset_root), str(output_dir), total_cible=150)
        copied = list(output_dir.glob("*.jpg"))
        assert len(copied) == 150

    def test_custom_target_count(self, dataset_root, output_dir):
        """Fonctionne aussi avec un total_cible différent de 150."""
        extraire_echantillon_stratifie(str(dataset_root), str(output_dir), total_cible=60)
        copied = list(output_dir.glob("*.jpg"))
        assert len(copied) == 60

    def test_proportional_distribution(self, dataset_root, output_dir):
        """
        La répartition doit être proportionnelle.
        electrique=100/200=50% → 75 images sur 150
        acoustique=60/200=30% → 45 images sur 150
        basse=40/200=20%      → 30 images sur 150
        Tolérance ±1 pour les arrondis.
        """
        extraire_echantillon_stratifie(str(dataset_root), str(output_dir), total_cible=150)
        copied = list(output_dir.glob("*.jpg"))

        counts = {"electrique": 0, "acoustique": 0, "basse": 0}
        for f in copied:
            prefix = f.name.split("_")[0]
            if prefix in counts:
                counts[prefix] += 1

        assert abs(counts["electrique"] - 75) <= 1
        assert abs(counts["acoustique"] - 45) <= 1
        assert abs(counts["basse"] - 30) <= 1

    def test_files_have_category_prefix(self, dataset_root, output_dir):
        """Tous les fichiers doivent avoir un préfixe de catégorie."""
        extraire_echantillon_stratifie(str(dataset_root), str(output_dir), total_cible=30)
        copied = list(output_dir.glob("*.jpg"))
        known_prefixes = {"electrique", "acoustique", "basse"}
        for f in copied:
            prefix = f.name.split("_")[0]
            assert prefix in known_prefixes, f"Préfixe inattendu: {f.name}"

    def test_reproducibility_with_same_seed(self, tmp_path_factory):
        """Deux runs avec la même seed doivent produire le même ensemble de fichiers."""
        # Dossiers isolés : dataset_root ne contient PAS les dossiers de sortie
        src = tmp_path_factory.mktemp("src")
        create_category_folder(src, "electrique", 100)
        create_category_folder(src, "acoustique", 60)
        create_category_folder(src, "basse", 40)
        out1 = tmp_path_factory.mktemp("out1")
        out2 = tmp_path_factory.mktemp("out2")
        extraire_echantillon_stratifie(str(src), str(out1), total_cible=50, seed=42)
        extraire_echantillon_stratifie(str(src), str(out2), total_cible=50, seed=42)
        files1 = sorted(f.name for f in out1.glob("*.jpg"))
        files2 = sorted(f.name for f in out2.glob("*.jpg"))
        assert files1 == files2

    def test_different_seeds_produce_different_results(self, tmp_path_factory):
        """Deux seeds différentes doivent (très probablement) produire des résultats différents."""
        src = tmp_path_factory.mktemp("src")
        create_category_folder(src, "electrique", 100)
        create_category_folder(src, "acoustique", 60)
        create_category_folder(src, "basse", 40)
        out1 = tmp_path_factory.mktemp("out1")
        out2 = tmp_path_factory.mktemp("out2")
        extraire_echantillon_stratifie(str(src), str(out1), total_cible=50, seed=42)
        extraire_echantillon_stratifie(str(src), str(out2), total_cible=50, seed=99)
        files1 = sorted(f.name for f in out1.glob("*.jpg"))
        files2 = sorted(f.name for f in out2.glob("*.jpg"))
        # Avec 200 images et un tirage de 50, la probabilité de collision est négligeable
        assert files1 != files2

    def test_creates_output_directory(self, dataset_root, tmp_path):
        """Le dossier de sortie doit être créé s'il n'existe pas."""
        nested_out = tmp_path / "deep" / "nested" / "output"
        assert not nested_out.exists()
        extraire_echantillon_stratifie(str(dataset_root), str(nested_out), total_cible=10)
        assert nested_out.exists()

    def test_missing_source_raises_error(self, tmp_path, output_dir):
        """Un dossier source inexistant doit lever FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            extraire_echantillon_stratifie(
                str(tmp_path / "inexistant"), str(output_dir), total_cible=10
            )

    def test_not_enough_images_raises_error(self, tmp_path, output_dir):
        """Moins d'images que total_cible doit lever ValueError."""
        small_root = tmp_path / "small"
        create_category_folder(small_root, "cat", 5)
        with pytest.raises(ValueError, match="Pas assez"):
            extraire_echantillon_stratifie(str(small_root), str(output_dir), total_cible=50)

    def test_no_valid_subfolder_raises_error(self, tmp_path, output_dir):
        """Un dossier source sans sous-dossiers valides doit lever ValueError."""
        empty_root = tmp_path / "empty_root"
        empty_root.mkdir()
        with pytest.raises(ValueError):
            extraire_echantillon_stratifie(str(empty_root), str(output_dir), total_cible=10)
