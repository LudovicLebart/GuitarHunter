"""Tests de la conversion 4 coins → rectangle pivoté Label Studio (aller-retour avec labelstudio_export)
et des fonctions pures de train_phase0."""
import math

import pytest

from backend.auto_annotation import labelstudio_export as ls
from backend.auto_annotation import preannotate as pre
from backend.auto_annotation import train_phase0 as train


def corners_px(value, w_img, h_img):
    c = ls.ls_rect_to_corners(value, w_img, h_img)
    return [(c[i] * w_img, c[i + 1] * h_img) for i in range(0, 8, 2)]


def same_rectangle(a, b, tol=1e-6):
    """Mêmes 4 coins, quel que soit le point de départ et le sens de parcours."""
    return all(min(math.dist(p, q) for q in b) < tol for p in a)


class TestCornersToLsRect:
    @pytest.mark.parametrize("rotation", [0, 5, 30, 89, -45, -120, 150])
    @pytest.mark.parametrize("size", [(540, 960), (960, 720)])
    def test_round_trip_through_label_studio_convention(self, rotation, size):
        w_img, h_img = size
        original = {"x": 40, "y": 30, "width": 14, "height": 5, "rotation": rotation}
        pts = corners_px(original, w_img, h_img)
        x, y, w, h, theta = pre.corners_to_ls_rect(pts)
        rebuilt = {"x": 100 * x / w_img, "y": 100 * y / h_img, "width": 100 * w / w_img,
                   "height": 100 * h / h_img, "rotation": theta}
        assert same_rectangle(pts, corners_px(rebuilt, w_img, h_img))

    def test_axis_aligned_box_has_zero_rotation(self):
        x, y, w, h, theta = pre.corners_to_ls_rect([(10, 20), (50, 20), (50, 30), (10, 30)])
        assert (x, y, w, h) == (10, 20, 40, 10)
        assert theta == pytest.approx(0)

    def test_corner_order_and_direction_do_not_matter(self):
        pts = [(10, 20), (50, 20), (50, 30), (10, 30)]
        for variant in (pts, pts[::-1], pts[2:] + pts[:2], pts[1:] + pts[:1]):
            assert same_rectangle(pts, _rebuild(pre.corners_to_ls_rect(variant)))

    def test_smallest_rotation_is_preferred(self):
        # Rectangle presque droit : la rotation retournée doit rester proche de 0, pas de ±90° ou 180°.
        _, _, _, _, theta = pre.corners_to_ls_rect(corners_px(
            {"x": 20, "y": 20, "width": 30, "height": 10, "rotation": 7}, 1000, 1000))
        assert abs(theta) < 10

    def test_wrong_number_of_corners_raises(self):
        with pytest.raises(ValueError):
            pre.corners_to_ls_rect([(0, 0), (1, 0), (1, 1)])


def _rebuild(rect):
    x, y, w, h, theta = rect
    t = math.radians(theta)
    return [(x + dx * math.cos(t) - dy * math.sin(t), y + dx * math.sin(t) + dy * math.cos(t))
            for dx, dy in ((0, 0), (w, 0), (w, h), (0, h))]


class TestPredictionResult:
    def test_values_are_percentages_with_label_and_score(self):
        item = pre.prediction_result("neck", [(100, 200), (500, 200), (500, 300), (100, 300)], 1000, 1000, score=0.8)
        v = item["value"]
        assert item["type"] == "rectanglelabels" and v["rectanglelabels"] == ["neck"]
        assert (v["x"], v["y"], v["width"], v["height"]) == pytest.approx((10, 20, 40, 10))
        assert item["original_width"] == 1000 and item["score"] == 0.8

    def test_prediction_matches_what_the_export_would_draw(self):
        # Vrai rectangle incliné (comme toute prédiction YOLO-OBB) : côté 218 px, hauteur 55 px.
        p0, u, v = (310.0, 120.0), (210.0, 60.0), (-60.0, 210.0)
        k = 55.0 / math.hypot(*v)
        p1 = (p0[0] + u[0], p0[1] + u[1])
        p3 = (p0[0] + v[0] * k, p0[1] + v[1] * k)
        p2 = (p1[0] + v[0] * k, p1[1] + v[1] * k)
        pts = [p0, p1, p2, p3]
        item = pre.prediction_result("body", pts, 800, 600)
        back = ls.ls_rect_to_corners(item["value"], 800, 600)
        back_px = [(back[i] * 800, back[i + 1] * 600) for i in range(0, 8, 2)]
        assert same_rectangle(pts, back_px, tol=1e-4)


class TestTrainHelpers:
    def test_rewrite_dataset_path(self, tmp_path):
        yaml = tmp_path / "dataset.yaml"
        yaml.write_text("path: C:/ailleurs/dataset\ntrain: images/train\nnames:\n  0: headstock\n", encoding="utf-8")
        train.rewrite_dataset_path(yaml)
        lines = yaml.read_text(encoding="utf-8").splitlines()
        assert lines[0] == f"path: {tmp_path.resolve().as_posix()}"
        assert lines[1:] == ["train: images/train", "names:", "  0: headstock"]

    def test_verdict_against_target(self):
        assert "atteint" in train.verdict(0.62)
        assert "NON atteint" in train.verdict(0.31)
        assert "atteint" in train.verdict(0.50)
