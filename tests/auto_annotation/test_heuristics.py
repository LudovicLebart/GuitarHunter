"""
Tests unitaires — backend/auto_annotation/heuristics.py
Aucune dépendance réseau, aucun modèle YOLO requis.
"""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.auto_annotation.heuristics import (
    rotated_rect_intersection_area,
    check_inclusion_obb,
    check_connectivity_obb,
    apply_heuristics,
)
from backend.auto_annotation.config import CLASS_NAMES, NECK_RATIO_MIN, INCLUSION_RATIO_MIN


# ─── Helpers ──────────────────────────────────────────────────────────────────

def rect(cx, cy, w, h, angle=0.0):
    """Crée un RotatedRect OpenCV : ((cx, cy), (w, h), angle)."""
    return ((cx, cy), (w, h), angle)


def cls_list(names: list[str]) -> list[int]:
    """Crée une liste d'indices de classes à partir de noms de classes.
    Utilise des int Python purs — pas de dépendance torch dans les tests unitaires.
    """
    return [CLASS_NAMES.index(n) for n in names]


# Alias pour compatibilité avec les tests existants
cls_tensor = cls_list


# ─── Tests rotated_rect_intersection_area ─────────────────────────────────────

class TestRotatedRectIntersectionArea:

    def test_identical_rects_area_equals_rect_area(self):
        """Deux rects identiques → intersection = aire du rect."""
        r = rect(100, 100, 80, 40, 0)
        area = rotated_rect_intersection_area(r, r)
        expected = 80 * 40
        assert abs(area - expected) < 5.0  # tolérance float

    def test_non_overlapping_rects(self):
        """Deux rects séparés → intersection = 0."""
        r1 = rect(100, 100, 50, 30, 0)
        r2 = rect(400, 400, 50, 30, 0)
        area = rotated_rect_intersection_area(r1, r2)
        assert area == 0.0

    def test_partial_overlap(self):
        """Deux rects qui se chevauchent partiellement → 0 < area < aire totale."""
        r1 = rect(100, 100, 100, 100, 0)
        r2 = rect(150, 100, 100, 100, 0)  # chevauchement de 50px en x
        area = rotated_rect_intersection_area(r1, r2)
        assert 0 < area < 100 * 100


# ─── Tests check_inclusion_obb ────────────────────────────────────────────────

class TestCheckInclusionOBB:

    def test_small_rect_inside_large_rect(self):
        """Un petit rect entièrement dans un grand → inclusion vraie."""
        inner = rect(200, 200, 40, 20, 0)
        outer = rect(200, 200, 300, 200, 0)
        assert check_inclusion_obb(inner, outer) is True

    def test_large_rect_not_inside_small_rect(self):
        """Un grand rect ne peut pas être inclus dans un petit."""
        outer = rect(200, 200, 300, 200, 0)
        inner = rect(200, 200, 40, 20, 0)
        # inner est l'argument "inner", outer est l'argument "outer"
        # ici on inverse pour tester l'asymétrie
        assert check_inclusion_obb(outer, inner) is False

    def test_non_overlapping_rects_not_included(self):
        """Deux rects séparés → pas d'inclusion."""
        r1 = rect(100, 100, 50, 30, 0)
        r2 = rect(500, 500, 50, 30, 0)
        assert check_inclusion_obb(r1, r2) is False

    def test_zero_area_inner(self):
        """Un rect de taille nulle → False (évite division par zéro)."""
        inner = rect(200, 200, 0, 0, 0)
        outer = rect(200, 200, 300, 200, 0)
        assert check_inclusion_obb(inner, outer) is False

    def test_threshold_is_from_config(self):
        """Le seuil d'inclusion est bien lu depuis config (INCLUSION_RATIO_MIN)."""
        assert INCLUSION_RATIO_MIN == 0.8


# ─── Tests check_connectivity_obb ─────────────────────────────────────────────

class TestCheckConnectivityOBB:

    def test_overlapping_rects_are_connected(self):
        """Deux rects qui se chevauchent → connectés."""
        r1 = rect(100, 100, 100, 100, 0)
        r2 = rect(150, 100, 100, 100, 0)
        assert check_connectivity_obb(r1, r2) is True

    def test_non_overlapping_rects_not_connected(self):
        """Deux rects séparés → non connectés."""
        r1 = rect(100, 100, 50, 30, 0)
        r2 = rect(400, 400, 50, 30, 0)
        assert check_connectivity_obb(r1, r2) is False

    def test_touching_rects_connected(self):
        """Deux rects se touchant (bord à bord) → connectés."""
        r1 = rect(100, 100, 100, 100, 0)  # s'étend de 50 à 150
        r2 = rect(150, 100, 100, 100, 0)  # s'étend de 100 à 200
        assert check_connectivity_obb(r1, r2) is True


# ─── Tests apply_heuristics ───────────────────────────────────────────────────

class TestApplyHeuristics:

    def test_valid_body_always_passes(self):
        """Un 'body' est toujours conservé (pas de règle exclusive)."""
        rects = [rect(320, 320, 300, 200, 0)]
        classes = cls_tensor(['body'])
        valid = apply_heuristics(rects, classes)
        assert 0 in valid

    def test_valid_headstock_always_passes(self):
        """Un 'headstock' est toujours conservé."""
        rects = [rect(320, 50, 80, 60, 0)]
        classes = cls_tensor(['headstock'])
        valid = apply_heuristics(rects, classes)
        assert 0 in valid

    def test_valid_bridge_always_passes(self):
        """Un 'bridge' est toujours conservé."""
        rects = [rect(320, 400, 60, 30, 0)]
        classes = cls_tensor(['bridge'])
        valid = apply_heuristics(rects, classes)
        assert 0 in valid

    def test_pickup_inside_body_passes(self):
        """Un pickup bien inclus dans le body passe le filtre."""
        body = rect(320, 320, 400, 300, 0)   # grand body centré
        pickup = rect(320, 320, 60, 30, 0)    # pickup centré dans le body
        rects = [body, pickup]
        classes = cls_tensor(['body', 'pickups'])
        valid = apply_heuristics(rects, classes)
        assert 1 in valid  # pickup doit passer

    def test_pickup_outside_body_fails(self):
        """Un pickup totalement hors du body est rejeté."""
        body = rect(100, 100, 100, 100, 0)    # body en haut à gauche
        pickup = rect(500, 500, 40, 20, 0)    # pickup loin du body
        rects = [body, pickup]
        classes = cls_tensor(['body', 'pickups'])
        valid = apply_heuristics(rects, classes)
        assert 1 not in valid  # pickup doit être rejeté

    def test_neck_good_ratio_and_connected_passes(self):
        """
        Un manche avec ratio >> NECK_RATIO_MIN et connecté au body passe.
        """
        body = rect(320, 320, 400, 300, 0)
        # Manche très allongé (ratio 6:1) qui touche le body
        neck = rect(320, 300, 240, 40, 0)
        rects = [body, neck]
        classes = cls_tensor(['body', 'neck'])
        valid = apply_heuristics(rects, classes)
        assert 1 in valid

    def test_neck_square_ratio_fails(self):
        """Un manche avec ratio 1:1 (carré) doit être rejeté."""
        body = rect(320, 320, 400, 300, 0)
        neck_square = rect(320, 300, 60, 60, 0)  # ratio = 1.0 < NECK_RATIO_MIN
        rects = [body, neck_square]
        classes = cls_tensor(['body', 'neck'])
        valid = apply_heuristics(rects, classes)
        assert 1 not in valid

    def test_neck_disconnected_from_body_fails(self):
        """Un manche allongé mais totalement déconnecté du body est rejeté."""
        body = rect(100, 100, 100, 80, 0)      # body en haut à gauche
        neck = rect(600, 600, 200, 40, 0)       # manche allongé mais loin
        rects = [body, neck]
        classes = cls_tensor(['body', 'neck'])
        valid = apply_heuristics(rects, classes)
        assert 1 not in valid

    def test_empty_input(self):
        """Aucune boîte → aucune boîte valide."""
        valid = apply_heuristics([], [])
        assert valid == []

    def test_neck_ratio_constant_from_config(self):
        """NECK_RATIO_MIN doit être accessible et valoir 2.0."""
        assert NECK_RATIO_MIN == 2.0
