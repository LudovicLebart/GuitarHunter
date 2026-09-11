"""
Tests unitaires — backend/auto_annotation/geometry.py
Aucune dépendance réseau, aucun modèle YOLO requis.
"""
import sys
from pathlib import Path
import numpy as np
import pytest

# Ajouter la racine du projet au path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.auto_annotation.geometry import parse_obb, rotate_and_crop


# ─── Helpers ──────────────────────────────────────────────────────────────────

class _NumpyRow:
    """Simule un tenseur 1D Ultralytics avec les méthodes .cpu().numpy()."""

    def __init__(self, row: np.ndarray):
        self._row = row

    def cpu(self):
        return self

    def numpy(self):
        return self._row


class MockOBBBoxes:
    """Simule l'objet obb d'Ultralytics — pur numpy, sans torch."""

    def __init__(self, boxes_xywhr: list[tuple]):
        """
        boxes_xywhr: liste de (x_c, y_c, w, h, angle_rad)
        """
        rows = [np.array(b, dtype=np.float32) for b in boxes_xywhr]
        self.xywhr = [_NumpyRow(r) for r in rows]

    def __len__(self):
        return len(self.xywhr)


def make_image(h=640, w=640, color=(128, 128, 128)):
    """Crée une image BGR synthétique uniforme."""
    img = np.full((h, w, 3), color, dtype=np.uint8)
    return img


# ─── Tests parse_obb ──────────────────────────────────────────────────────────

class TestParseObb:

    def test_returns_tuple_of_3(self):
        """parse_obb doit retourner ((cx, cy), (w, h), angle_deg)."""
        import math
        boxes = MockOBBBoxes([(320.0, 240.0, 100.0, 50.0, math.pi / 4)])
        result = parse_obb(boxes, 0)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_center_coordinates(self):
        """Les coordonnées du centre doivent correspondre aux valeurs d'entrée."""
        import math
        boxes = MockOBBBoxes([(123.0, 456.0, 80.0, 40.0, 0.0)])
        center, size, angle = parse_obb(boxes, 0)
        assert abs(center[0] - 123.0) < 1e-3
        assert abs(center[1] - 456.0) < 1e-3

    def test_size(self):
        """La taille (w, h) doit être correctement extraite."""
        import math
        boxes = MockOBBBoxes([(200.0, 200.0, 150.0, 60.0, 0.0)])
        center, size, angle = parse_obb(boxes, 0)
        assert abs(size[0] - 150.0) < 1e-3
        assert abs(size[1] - 60.0) < 1e-3

    def test_angle_conversion_radians_to_degrees(self):
        """L'angle doit être converti de radians en degrés."""
        import math
        angle_rad = math.pi / 2  # 90°
        boxes = MockOBBBoxes([(320.0, 240.0, 100.0, 50.0, angle_rad)])
        _, _, angle_deg = parse_obb(boxes, 0)
        assert abs(angle_deg - 90.0) < 1e-3

    def test_zero_angle(self):
        """Un angle de 0 radian doit donner 0 degrés."""
        boxes = MockOBBBoxes([(100.0, 100.0, 50.0, 30.0, 0.0)])
        _, _, angle_deg = parse_obb(boxes, 0)
        assert abs(angle_deg) < 1e-3

    def test_multiple_boxes_index(self):
        """Doit extraire la bonne boîte selon l'index."""
        import math
        boxes = MockOBBBoxes([
            (100.0, 100.0, 50.0, 20.0, 0.0),
            (400.0, 300.0, 80.0, 40.0, math.pi / 6),
        ])
        center_0, _, _ = parse_obb(boxes, 0)
        center_1, _, _ = parse_obb(boxes, 1)
        assert abs(center_0[0] - 100.0) < 1e-3
        assert abs(center_1[0] - 400.0) < 1e-3


# ─── Tests rotate_and_crop ────────────────────────────────────────────────────

class TestRotateAndCrop:

    def test_returns_numpy_array(self):
        """rotate_and_crop doit retourner un ndarray numpy."""
        image = make_image(640, 640)
        rect = ((320.0, 320.0), (100.0, 50.0), 0.0)
        crop = rotate_and_crop(image, rect)
        assert isinstance(crop, np.ndarray)

    def test_non_empty_output_centered_rect(self):
        """Un rect centré dans l'image doit produire un crop non vide."""
        image = make_image(640, 640)
        rect = ((320.0, 320.0), (100.0, 50.0), 0.0)
        crop = rotate_and_crop(image, rect)
        assert crop.size > 0

    def test_non_empty_output_rotated_45deg(self):
        """Un rect incliné à 45° doit aussi produire un crop non vide."""
        image = make_image(640, 640)
        rect = ((320.0, 320.0), (120.0, 60.0), 45.0)
        crop = rotate_and_crop(image, rect)
        assert crop.size > 0

    def test_crop_shape_3_channels(self):
        """Le crop doit être une image BGR (3 canaux)."""
        image = make_image(640, 640)
        rect = ((320.0, 320.0), (100.0, 50.0), 0.0)
        crop = rotate_and_crop(image, rect)
        assert crop.ndim == 3
        assert crop.shape[2] == 3

    def test_crop_dimensions_approximately_correct(self):
        """
        Les dimensions du crop doivent être proches de (w, h) de la boîte.
        Tolérance de 2px pour les arrondis entiers.
        """
        image = make_image(640, 640)
        expected_w, expected_h = 100, 50
        rect = ((320.0, 320.0), (float(expected_w), float(expected_h)), 0.0)
        crop = rotate_and_crop(image, rect)
        # shape = (h, w, channels) en OpenCV
        assert abs(crop.shape[0] - expected_h) <= 2
        assert abs(crop.shape[1] - expected_w) <= 2

    def test_rect_near_edge_no_crash(self):
        """Un rect proche du bord ne doit pas planter (clipping géré)."""
        image = make_image(640, 640)
        rect = ((10.0, 10.0), (80.0, 40.0), 30.0)  # proche du coin supérieur gauche
        crop = rotate_and_crop(image, rect)
        assert crop is not None  # ne doit pas lever d'exception

    def test_large_angle_no_crash(self):
        """Un angle proche de 90° ne doit pas planter."""
        image = make_image(640, 640)
        rect = ((320.0, 320.0), (200.0, 80.0), 89.0)
        crop = rotate_and_crop(image, rect)
        assert crop.size > 0
