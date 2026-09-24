"""
Tests unitaires — backend/auto_annotation/config.py
Vérifie que les constantes critiques sont correctement définies.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import backend.auto_annotation.config as cfg


class TestConfig:

    def test_project_root_is_absolute(self):
        """PROJECT_ROOT doit être un chemin absolu."""
        assert cfg.PROJECT_ROOT.is_absolute()

    def test_module_root_is_absolute(self):
        """MODULE_ROOT doit être un chemin absolu."""
        assert cfg.MODULE_ROOT.is_absolute()

    def test_labels_dir_is_absolute(self):
        """LABELS_DIR doit être absolu (indépendant du CWD)."""
        assert cfg.LABELS_DIR.is_absolute()

    def test_images_dir_is_absolute(self):
        """IMAGES_DIR doit être absolu."""
        assert cfg.IMAGES_DIR.is_absolute()

    def test_yolo_weights_is_absolute_string(self):
        """YOLO_V1_OBB_WEIGHTS doit être un chemin absolu (sous forme de str)."""
        assert Path(cfg.YOLO_V1_OBB_WEIGHTS).is_absolute()

    def test_class_names_not_empty(self):
        """CLASS_NAMES doit contenir des classes."""
        assert len(cfg.CLASS_NAMES) > 0

    def test_class_names_contains_expected_classes(self):
        """Les classes attendues du pipeline doivent toutes être présentes."""
        expected = {'headstock', 'neck', 'body', 'bridge', 'pickups', 'soundhole'}
        assert expected == set(cfg.CLASS_NAMES)

    def test_neck_ratio_min_positive(self):
        """NECK_RATIO_MIN doit être > 1 (un manche n'est jamais carré)."""
        assert cfg.NECK_RATIO_MIN > 1.0

    def test_inclusion_ratio_min_between_0_and_1(self):
        """INCLUSION_RATIO_MIN doit être dans (0, 1)."""
        assert 0.0 < cfg.INCLUSION_RATIO_MIN < 1.0

    def test_min_crop_dim_positive(self):
        """MIN_CROP_DIM doit être un entier positif."""
        assert cfg.MIN_CROP_DIM > 0

    def test_min_image_dim_positive(self):
        """MIN_IMAGE_DIM doit être un entier positif."""
        assert cfg.MIN_IMAGE_DIM > 0

    def test_pipeline_concurrency_positive(self):
        """PIPELINE_CONCURRENCY doit être >= 1."""
        assert cfg.PIPELINE_CONCURRENCY >= 1

    def test_ollama_timeout_positive(self):
        """OLLAMA_TIMEOUT_S doit être > 0."""
        assert cfg.OLLAMA_TIMEOUT_S > 0

    def test_vlm_prompt_has_placeholder(self):
        """VLM_PROMPT doit contenir {class_name} pour la substitution dynamique."""
        assert '{class_name}' in cfg.VLM_PROMPT

    def test_setup_directories_creates_dirs(self, tmp_path, monkeypatch):
        """setup_directories() doit créer IMAGES_DIR et LABELS_DIR."""
        # Rediriger vers tmp_path pour ne pas toucher au filesystem réel
        test_images = tmp_path / 'images'
        test_labels = tmp_path / 'labels'
        monkeypatch.setattr(cfg, 'IMAGES_DIR', test_images)
        monkeypatch.setattr(cfg, 'LABELS_DIR', test_labels)
        cfg.setup_directories()
        assert test_images.exists()
        assert test_labels.exists()
