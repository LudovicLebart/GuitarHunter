"""Tests du manifeste de crops (banc de rejeu) et du contrat de description d'un crop."""
import json

import pytest
from PIL import Image

from backend import crop_description as cd
from backend.auto_annotation.config import CLASS_NAMES
from backend.scripts import crop_manifest as cm


def make_image(path, size=(40, 30), mode="RGB"):
    Image.new(mode, size, "white").save(path)


class TestManifest:
    def test_load_normalises_ids_and_drops_invalid_entries(self, tmp_path):
        f = tmp_path / "m.json"
        f.write_text(json.dumps({"123": ["a.jpg", "b.jpg"], "456": [], "789": "pas une liste", 42: ["c.jpg"],
                                 "9": ["ok.jpg", ""]}), encoding="utf-8")
        assert cm.load_manifest(f) == {"123": ["a.jpg", "b.jpg"], "42": ["c.jpg"]}

    def test_load_rejects_non_object(self, tmp_path):
        f = tmp_path / "m.json"
        f.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(ValueError):
            cm.load_manifest(f)

    def test_relative_paths_resolve_from_manifest_folder(self, tmp_path):
        assert cm.resolve_spec("crops/a.jpg", tmp_path) == str(tmp_path / "crops" / "a.jpg")
        assert cm.resolve_spec("https://x/y.jpg", tmp_path) == "https://x/y.jpg"

    def test_images_for_deal_uses_crops_when_present(self, tmp_path):
        make_image(tmp_path / "a.jpg")
        make_image(tmp_path / "b.jpg")
        mode, images = cm.images_for_deal("123", {"123": ["a.jpg", "b.jpg"]}, tmp_path, max_crops=8)
        assert mode == "crops" and len(images) == 2

    def test_max_crops_is_respected(self, tmp_path):
        for n in "abc":
            make_image(tmp_path / f"{n}.jpg")
        _, images = cm.images_for_deal("1", {"1": ["a.jpg", "b.jpg", "c.jpg"]}, tmp_path, max_crops=2)
        assert len(images) == 2

    def test_deal_not_in_manifest_keeps_full_photos(self, tmp_path):
        assert cm.images_for_deal("999", {"123": ["a.jpg"]}, tmp_path, 8) == ("full", None)

    def test_all_crops_unreadable_falls_back_to_full(self, tmp_path):
        assert cm.images_for_deal("1", {"1": ["absent.jpg"]}, tmp_path, 8) == ("full", None)

    def test_large_crop_is_capped_and_rgba_converted(self, tmp_path):
        make_image(tmp_path / "big.png", size=(3000, 1000), mode="RGBA")
        img = cm.load_crop_image("big.png", tmp_path, max_size=2048)
        assert max(img.size) == 2048 and img.mode == "RGB"

    def test_small_crop_is_never_enlarged(self, tmp_path):
        make_image(tmp_path / "s.jpg", size=(100, 50))
        assert cm.load_crop_image("s.jpg", tmp_path).size == (100, 50)

    def test_url_crop_uses_injected_downloader(self, tmp_path):
        sentinel = object()
        assert cm.load_crop_image("https://x/y.jpg", tmp_path, download=lambda u: sentinel) is sentinel
        assert cm.load_crop_image("https://x/y.jpg", tmp_path) is None


def valid_description():
    return {
        "vue": "headstock", "qualite": "nette",
        "texte_lu": {"transcription": "Gibson", "confiance": "haute"},
        "formes": ["tête ouverte"], "materiel_visible": ["mécaniques chromées"], "finition": "vernie_brillante",
        "etat": [{"observation": "petite éraflure", "gravite": "legere", "zone": "headstock"}],
        "non_visible": ["heel", "bridge"],
    }


class TestDescriptionContract:
    def test_valid_description_has_no_error(self):
        assert cd.validate_description(valid_description()) == []

    def test_empty_transcription_and_empty_lists_are_valid(self):
        d = valid_description()
        d.update(texte_lu={"transcription": "", "confiance": "basse"}, formes=[], materiel_visible=[], etat=[], non_visible=[])
        assert cd.validate_description(d) == []

    def test_vocabulary_follows_the_detector_classes(self):
        assert set(CLASS_NAMES) <= set(cd.VUES) and set(CLASS_NAMES) <= set(cd.ZONES)

    @pytest.mark.parametrize("field,value", [("vue", "brand_new"), ("qualite", "mauvaise"), ("finition", "dorée")])
    def test_closed_vocabularies_are_enforced(self, field, value):
        d = valid_description()
        d[field] = value
        assert any(field in e for e in cd.validate_description(d))

    def test_missing_and_unknown_fields_are_reported(self):
        d = valid_description()
        del d["finition"]
        d["marque"] = "Gibson"        # une déduction de marque n'a pas sa place dans le contrat
        errors = cd.validate_description(d)
        assert "champ manquant : finition" in errors and "champ inconnu : marque" in errors

    def test_bad_etat_item_and_gravity(self):
        d = valid_description()
        d["etat"] = [{"observation": "x", "gravite": "énorme", "zone": "dos"}]
        errors = cd.validate_description(d)
        assert any("gravite" in e for e in errors) and any("zone" in e for e in errors)

    def test_long_transcription_is_rejected(self):
        d = valid_description()
        d["texte_lu"]["transcription"] = "x" * 201
        assert any("200" in e for e in cd.validate_description(d))

    def test_not_an_object(self):
        assert cd.validate_description([]) == ["la description doit être un objet JSON"]

    def test_non_visible_must_use_known_zones(self):
        d = valid_description()
        d["non_visible"] = ["pedalboard"]
        assert any("non_visible" in e for e in cd.validate_description(d))

    def test_openai_schema_is_strict_and_shares_the_schema(self):
        wrapper = cd.DESCRIPTION_OPENAI_JSON_SCHEMA["json_schema"]
        assert wrapper["strict"] is True and wrapper["schema"] is cd.DESCRIPTION_SCHEMA
        assert cd.DESCRIPTION_SCHEMA["additionalProperties"] is False
        assert set(cd.DESCRIPTION_SCHEMA["required"]) == set(cd.DESCRIPTION_SCHEMA["properties"])

    def test_prompt_forbids_inference(self):
        assert "sans interpréter" in cd.DESCRIPTION_PROMPT and "ne déduis jamais" in cd.DESCRIPTION_PROMPT
