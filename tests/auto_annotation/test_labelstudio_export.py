"""Tests de l'export Label Studio → YOLO-OBB (conversion des rectangles pivotés, découpage, suivi)."""
import json
import sqlite3

import pytest

from backend.auto_annotation import labelstudio_export as ls
from backend.auto_annotation.config import CLASS_NAMES


def value(x=10, y=20, width=30, height=10, rotation=0.0, label="neck"):
    return {"x": x, "y": y, "width": width, "height": height, "rotation": rotation, "rectanglelabels": [label]}


def box(label, w=100, h=100):
    return {"type": "rectanglelabels", "original_width": w, "original_height": h, "value": value(label=label)}


class TestCorners:
    def test_no_rotation_gives_axis_aligned_rectangle(self):
        c = ls.ls_rect_to_corners(value(), 1000, 500)
        assert c == pytest.approx([0.10, 0.20, 0.40, 0.20, 0.40, 0.30, 0.10, 0.30])

    def test_rotation_90_swings_box_clockwise_around_top_left(self):
        # Image carrée 100x100 : rectangle 20x10 en (50,10) tourné de 90° autour de son coin haut-gauche.
        # (w,0) -> sous l'origine ; (0,h) -> à gauche de l'origine.
        c = ls.ls_rect_to_corners(value(x=50, y=10, width=20, height=10, rotation=90), 100, 100)
        assert c == pytest.approx([0.50, 0.10, 0.50, 0.30, 0.40, 0.30, 0.40, 0.10])

    def test_rotation_uses_pixels_not_percent(self):
        # Image 2:1 : après rotation, les côtés doivent garder leur longueur réelle en pixels (20 px et 20 px).
        c = ls.ls_rect_to_corners(value(x=50, y=10, width=10, height=20, rotation=90), 200, 100)
        px = [(c[i] * 200, c[i + 1] * 100) for i in range(0, 8, 2)]
        side_a = ((px[1][0] - px[0][0]) ** 2 + (px[1][1] - px[0][1]) ** 2) ** 0.5
        side_b = ((px[2][0] - px[1][0]) ** 2 + (px[2][1] - px[1][1]) ** 2) ** 0.5
        assert side_a == pytest.approx(20) and side_b == pytest.approx(20)

    def test_coordinates_are_clamped_to_unit_square(self):
        c = ls.ls_rect_to_corners(value(x=95, y=95, width=20, height=20), 100, 100)
        assert all(0.0 <= v <= 1.0 for v in c)

    def test_missing_rotation_is_zero(self):
        v = value()
        del v["rotation"]
        assert ls.ls_rect_to_corners(v, 100, 100) == pytest.approx([0.10, 0.20, 0.40, 0.20, 0.40, 0.30, 0.10, 0.30])


def official_rotated_rectangle(x, y, w, h, r):
    """Formule du convertisseur officiel (HumanSignal/label-studio-converter, `rotated_rectangle`), recopiée :
    x, y = coin haut-gauche AVANT rotation ; rotation en degrés ; tout en pixels. Sert d'étalon."""
    import math
    alpha = math.atan(h / w)
    beta = math.pi * (r / 180)
    radius = math.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    x0 = x - radius * (math.cos(math.pi - alpha - beta) - math.cos(math.pi - alpha)) + w / 2
    y0 = y + radius * (math.sin(math.pi - alpha - beta) - math.sin(math.pi - alpha)) + h / 2
    angles = [alpha + beta, math.pi - alpha + beta, math.pi + alpha + beta, 2 * math.pi - alpha + beta]
    return [(x0 + radius * math.cos(t), y0 + radius * math.sin(t)) for t in angles]


class TestRotationConventionMatchesLabelStudio:
    @pytest.mark.parametrize("rotation", [-120, -45, -5, 0, 7, 30, 90, 135])
    @pytest.mark.parametrize("size", [(540, 960), (960, 720), (800, 800)])
    def test_same_corners_as_official_converter(self, rotation, size):
        w_img, h_img = size
        v = value(x=40, y=30, width=12, height=6, rotation=rotation)
        mine = ls.ls_rect_to_corners(v, w_img, h_img)
        mine_px = [(mine[i] * w_img, mine[i + 1] * h_img) for i in range(0, 8, 2)]
        official = official_rotated_rectangle(0.40 * w_img, 0.30 * h_img, 0.12 * w_img, 0.06 * h_img, rotation)
        assert all(min(((a - c) ** 2 + (b - d) ** 2) ** 0.5 for c, d in official) < 1e-6 for a, b in mine_px)


class TestNamesAndClasses:
    def test_upload_hash_prefix_is_removed(self):
        assert ls.image_name_from_task({"image": "/data/upload/1/28858522-acoustique_768_0.jpg"}) == "acoustique_768_0.jpg"

    def test_name_without_prefix_is_kept(self):
        assert ls.image_name_from_task({"image": "/data/upload/1/acoustique_768_0.jpg"}) == "acoustique_768_0.jpg"

    def test_class_ids_follow_class_names_order(self):
        assert [ls.class_id(n) for n in CLASS_NAMES] == list(range(len(CLASS_NAMES)))

    def test_unknown_class_raises(self):
        with pytest.raises(ValueError):
            ls.class_id("body_kit")


class TestSplit:
    NAMES = [f"acoustique_{i}_0.jpg" for i in range(20)] + [f"electrique_{i}_0.jpg" for i in range(10)] + \
            [f"basse_{i}_0.jpg" for i in range(3)]

    def test_reproducible_and_disjoint(self):
        a = ls.split_train_val(self.NAMES, 0.2, 42)
        assert a == ls.split_train_val(self.NAMES, 0.2, 42)
        assert not set(a[0]) & set(a[1])
        assert sorted(a[0] + a[1]) == sorted(self.NAMES)

    def test_validation_share_is_close_to_ratio(self):
        names = [f"acoustique_{i}_0.jpg" for i in range(1000)]
        _, val = ls.split_train_val(names, 0.2, 42)
        assert 0.15 < len(val) / len(names) < 0.25

    def test_assignment_is_stable_when_more_images_are_annotated(self):
        """Le camp d'une image ne dépend pas des autres : indispensable quand on ré-exporte en cours d'annotation."""
        small = self.NAMES[:15]
        _, val_small = ls.split_train_val(small, 0.2, 42)
        train_all, val_all = ls.split_train_val(self.NAMES, 0.2, 42)
        assert set(val_small) <= set(val_all)
        assert set(small) & set(train_all) == set(small) - set(val_small)

    def test_seed_changes_the_split(self):
        names = [f"acoustique_{i}_0.jpg" for i in range(200)]
        assert ls.split_train_val(names, 0.2, 1)[1] != ls.split_train_val(names, 0.2, 2)[1]


def make_db(path, project="GuitarHunter OBB Phase 1"):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE project (id integer primary key, title text);
        CREATE TABLE task (id integer primary key, project_id integer, data text);
        CREATE TABLE task_completion (id integer primary key, task_id integer, project_id integer,
                                      result text, was_cancelled integer, updated_at text);
    """)
    conn.execute("INSERT INTO project VALUES (1, ?)", (project,))
    names = ["aaaaaaaa-acoustique_1_0.jpg", "bbbbbbbb-acoustique_2_0.jpg",
             "cccccccc-electrique_3_0.jpg", "dddddddd-electrique_4_0.jpg"]
    for i, name in enumerate(names, start=1):
        conn.execute("INSERT INTO task VALUES (?, 1, ?)", (i, json.dumps({"image": f"/data/upload/1/{name}"})))
    # tâche 1 : 2 boîtes ; tâche 2 : annotée sans boîte (négatif) ; tâche 3 : ignorée ; tâche 4 : non traitée.
    conn.execute("INSERT INTO task_completion VALUES (1,1,1,?,0,'2026-10-02 10:00')",
                 (json.dumps([box("neck"), box("headstock")]),))
    conn.execute("INSERT INTO task_completion VALUES (2,2,1,'[]',0,'2026-10-02 10:01')")
    conn.execute("INSERT INTO task_completion VALUES (3,3,1,?,1,'2026-10-02 10:02')", (json.dumps([box("neck")]),))
    conn.commit()
    conn.close()


class TestLoadAndReport:
    def test_sqlite_loading_rules(self, tmp_path):
        db = tmp_path / "ls.sqlite3"
        make_db(db)
        annotated, names = ls.load_annotations_sqlite(db)
        assert sorted(annotated) == ["acoustique_1_0.jpg", "acoustique_2_0.jpg"]   # ignorée et non traitée exclues
        assert [b[0] for b in annotated["acoustique_1_0.jpg"]] == ["neck", "headstock"]
        assert annotated["acoustique_2_0.jpg"] == []                                  # négatif conservé
        assert len(names) == 4

    def test_latest_annotation_wins(self, tmp_path):
        db = tmp_path / "ls.sqlite3"
        make_db(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO task_completion VALUES (9,1,1,?,0,'2026-10-02 12:00')", (json.dumps([box("body")]),))
        conn.commit()
        conn.close()
        annotated, _ = ls.load_annotations_sqlite(db)
        assert [b[0] for b in annotated["acoustique_1_0.jpg"]] == ["body"]

    def test_unknown_project_exits(self, tmp_path):
        db = tmp_path / "ls.sqlite3"
        make_db(db, project="Autre")
        with pytest.raises(SystemExit):
            ls.load_annotations_sqlite(db)

    def test_json_export_loading(self, tmp_path):
        export = [{"data": {"image": "/data/upload/1/aaaaaaaa-acoustique_1_0.jpg"},
                   "annotations": [{"was_cancelled": False, "result": [box("neck")]}]},
                  {"data": {"image": "/data/upload/1/bbbbbbbb-acoustique_2_0.jpg"}, "annotations": []}]
        p = tmp_path / "export.json"
        p.write_text(json.dumps(export), encoding="utf-8")
        annotated, names = ls.load_annotations_json(p)
        assert list(annotated) == ["acoustique_1_0.jpg"]
        assert len(names) == 2

    def test_progress_report_flags_rare_classes(self, tmp_path):
        db = tmp_path / "ls.sqlite3"
        make_db(db)
        annotated, names = ls.load_annotations_sqlite(db)
        report = ls.progress_report(annotated, names)
        assert "2 / 4" in report
        assert "Boîtes au total : 2" in report
        assert "plate" in report and "<- rare" in report


class TestExport:
    def test_export_writes_labels_images_and_yaml(self, tmp_path):
        db = tmp_path / "ls.sqlite3"
        make_db(db)
        annotated, _ = ls.load_annotations_sqlite(db)
        images = tmp_path / "images"
        images.mkdir()
        for n in annotated:
            (images / n).write_bytes(b"jpg")
        out = tmp_path / "out"
        summary = ls.export_dataset(annotated, images, out, val_ratio=0.5, seed=1)
        assert summary["boxes"] == 2
        assert summary["missing"] == []
        labels = {p.name: p.read_text() for p in (out / "labels").rglob("*.txt")}
        assert set(labels) == {"acoustique_1_0.txt", "acoustique_2_0.txt"}
        lines = labels["acoustique_1_0.txt"].strip().splitlines()
        assert [int(l.split()[0]) for l in lines] == [CLASS_NAMES.index("neck"), CLASS_NAMES.index("headstock")]
        assert all(len(l.split()) == 9 for l in lines)                      # classe + 8 coordonnées
        assert labels["acoustique_2_0.txt"] == ""                           # négatif : fichier vide
        yaml_text = (out / "dataset.yaml").read_text(encoding="utf-8")
        assert "0: headstock" in yaml_text
        assert f"{len(CLASS_NAMES) - 1}: plate" in yaml_text

    def test_reexport_after_more_annotations_leaves_no_image_in_both_splits(self, tmp_path):
        images = tmp_path / "images"
        images.mkdir()
        names = [f"acoustique_{i}_0.jpg" for i in range(40)]
        for n in names:
            (images / n).write_bytes(b"jpg")
        out = tmp_path / "out"
        ls.export_dataset({n: [] for n in names[:15]}, images, out)
        first_val = {p.name for p in (out / "images" / "val").iterdir()}
        ls.export_dataset({n: [] for n in names}, images, out)
        train = {p.name for p in (out / "images" / "train").iterdir()}
        val = {p.name for p in (out / "images" / "val").iterdir()}
        assert not train & val
        assert first_val <= val                                  # une image de validation le reste
        assert len(train) + len(val) == 40                       # aucune copie résiduelle

    def test_unknown_class_aborts_before_writing_anything(self, tmp_path):
        images = tmp_path / "images"
        images.mkdir()
        (images / "acoustique_1_0.jpg").write_bytes(b"jpg")
        bad = [("body_kit", value(), 100, 100)]
        out = tmp_path / "out"
        with pytest.raises(ValueError):
            ls.export_dataset({"acoustique_1_0.jpg": bad}, images, out)
        assert not out.exists()

    def test_missing_image_is_reported_not_fatal(self, tmp_path):
        db = tmp_path / "ls.sqlite3"
        make_db(db)
        annotated, _ = ls.load_annotations_sqlite(db)
        summary = ls.export_dataset(annotated, tmp_path / "vide", tmp_path / "out")
        assert len(summary["missing"]) == 2
