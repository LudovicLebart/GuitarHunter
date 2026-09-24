"""
Tests unitaires — backend/production_pipeline/post_processing.py
Aucune dépendance réseau, aucun modèle requis.
"""
import sys
from pathlib import Path
import numpy as np
import pytest
import cv2

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.production_pipeline.post_processing import (
    apply_route_ocr_surya,
    apply_route_vision_llm,
)


def make_bgr_image(h=100, w=100):
    """Image BGR synthétique avec du bruit pour tester les filtres."""
    rng = np.random.default_rng(42)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


# ─── Tests apply_route_ocr_surya ─────────────────────────────────────────────

class TestRouteOCR:

    def test_returns_numpy_array(self):
        img = make_bgr_image()
        result = apply_route_ocr_surya(img)
        assert isinstance(result, np.ndarray)

    def test_output_is_grayscale(self):
        """La route OCR doit retourner une image en niveaux de gris (2D)."""
        img = make_bgr_image()
        result = apply_route_ocr_surya(img)
        assert result.ndim == 2, f"Attendu 2D, obtenu shape={result.shape}"

    def test_output_same_spatial_dimensions(self):
        """Les dimensions spatiales (h, w) doivent être conservées."""
        img = make_bgr_image(120, 80)
        result = apply_route_ocr_surya(img)
        assert result.shape == (120, 80)

    def test_output_dtype_uint8(self):
        """La sortie doit être uint8 (0–255)."""
        img = make_bgr_image()
        result = apply_route_ocr_surya(img)
        assert result.dtype == np.uint8

    def test_values_in_valid_range(self):
        """Toutes les valeurs doivent être dans [0, 255]."""
        img = make_bgr_image()
        result = apply_route_ocr_surya(img)
        assert result.min() >= 0
        assert result.max() <= 255

    def test_not_identical_to_input(self):
        """Le résultat doit être différent de l'entrée (traitement effectué)."""
        img = make_bgr_image()
        # Convertir en gris pour comparer équitablement
        gray_input = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        result = apply_route_ocr_surya(img)
        # Le CLAHE + unsharp masking doit modifier les valeurs
        assert not np.array_equal(result, gray_input)

    def test_uniform_image_no_crash(self):
        """Une image uniforme (pas de contraste) ne doit pas planter."""
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        result = apply_route_ocr_surya(img)
        assert result is not None

    def test_black_image_no_crash(self):
        """Une image noire ne doit pas planter."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result = apply_route_ocr_surya(img)
        assert result is not None

    def test_white_image_no_crash(self):
        """Une image blanche ne doit pas planter."""
        img = np.full((100, 100, 3), 255, dtype=np.uint8)
        result = apply_route_ocr_surya(img)
        assert result is not None


# ─── Tests apply_route_vision_llm ─────────────────────────────────────────────

class TestRouteVision:

    def test_returns_numpy_array(self):
        img = make_bgr_image()
        result = apply_route_vision_llm(img)
        assert isinstance(result, np.ndarray)

    def test_output_is_color(self):
        """La route Vision doit retourner une image couleur BGR (3 canaux)."""
        img = make_bgr_image()
        result = apply_route_vision_llm(img)
        assert result.ndim == 3
        assert result.shape[2] == 3

    def test_output_same_spatial_dimensions(self):
        """Les dimensions spatiales doivent être conservées."""
        img = make_bgr_image(120, 80)
        result = apply_route_vision_llm(img)
        assert result.shape == (120, 80, 3)

    def test_output_dtype_uint8(self):
        """La sortie doit être uint8."""
        img = make_bgr_image()
        result = apply_route_vision_llm(img)
        assert result.dtype == np.uint8

    def test_values_in_valid_range(self):
        """Toutes les valeurs doivent être dans [0, 255]."""
        img = make_bgr_image()
        result = apply_route_vision_llm(img)
        assert result.min() >= 0
        assert result.max() <= 255

    def test_not_identical_to_input(self):
        """Le filtre bilatéral + CLAHE doit modifier l'image."""
        img = make_bgr_image()
        result = apply_route_vision_llm(img)
        assert not np.array_equal(result, img)

    def test_uniform_image_no_crash(self):
        """Une image uniforme ne doit pas planter."""
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        result = apply_route_vision_llm(img)
        assert result is not None

    def test_black_image_no_crash(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result = apply_route_vision_llm(img)
        assert result is not None
