"""Nettoyage du texte lu sur les photos par le Portier (2026-10-15)."""
import unittest

from backend import t1_photo_text as pt


class TestParsePhotoText(unittest.TestCase):
    def test_joins_clean_items(self):
        self.assertEqual(pt.parse_photo_text({"visible_text": ["Epiphone", "Casino", "S/N 1234"]}),
                         "Epiphone ; Casino ; S/N 1234")

    def test_drops_duplicates_ignoring_case_and_spaces(self):
        self.assertEqual(pt.parse_photo_text({"visible_text": ["Fender", "  fender ", "FENDER"]}), "Fender")

    def test_drops_empty_markers_and_items_without_letters_or_digits(self):
        self.assertEqual(pt.parse_photo_text({"visible_text": ["N/A", "none", "Aucun", "illisible", "--", "???", "", "Ibanez"]}),
                         "Ibanez")

    def test_nothing_readable_is_an_empty_string(self):
        for result in ({"visible_text": []}, {"visible_text": ["N/A"]}, {}, None, "texte", [], {"visible_text": None},
                       {"visible_text": [1, None, {"a": 1}]}):
            self.assertEqual(pt.parse_photo_text(result), "")

    def test_a_single_string_is_accepted(self):
        self.assertEqual(pt.parse_photo_text({"visible_text": "Yamaha"}), "Yamaha")

    def test_control_characters_and_newlines_are_flattened(self):
        self.assertEqual(pt.parse_photo_text({"visible_text": ["Gibson\nLes\tPaul\x00"]}), "Gibson Les Paul")

    def test_long_items_and_totals_are_bounded(self):
        out = pt.parse_photo_text({"visible_text": ["a" * 500]})
        self.assertEqual(len(out), pt.MAX_ITEM_CHARS)
        many = {"visible_text": [f"Marque{i} Modele{i} Numero{i}" for i in range(100)]}
        out = pt.parse_photo_text(many)
        self.assertLessEqual(len(out), pt.MAX_TOTAL_CHARS)
        self.assertLessEqual(len(out.split(" ; ")), pt.MAX_ITEMS)

    def test_accents_are_kept(self):
        self.assertEqual(pt.parse_photo_text({"visible_text": ["Épiphone Éléctrique"]}), "Épiphone Éléctrique")

    def test_schema_is_strict_and_requires_the_list(self):
        schema = pt.PHOTO_TEXT_JSON_SCHEMA["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertEqual(schema["schema"]["required"], ["visible_text"])
        self.assertFalse(schema["schema"]["additionalProperties"])

    def test_prompt_forbids_guessing(self):
        self.assertIn("N'invente rien", pt.PHOTO_TEXT_PROMPT)


if __name__ == "__main__":
    unittest.main()
