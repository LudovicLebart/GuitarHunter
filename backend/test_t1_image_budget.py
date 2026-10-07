"""Tests du budget de tokens des photos du Portier local (backend/t1_image_budget.py) et de son branchement dans
`LLMClientsMixin._call_t1_provider` — sans réseau, sans Dell, sans IA."""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("APP_ID_TARGET", "test")
os.environ.setdefault("USER_IDS_TARGET", "test_user")

from PIL import Image

from backend import t1_image_budget as budget
from backend.t1_image_budget import estimate_image_tokens, estimate_text_tokens, fit_images_to_budget

# Prompt Portier réel mesuré : 6788 caractères = 2080 tokens (N=0 photo, diag_t1_image_budget.py)
PROMPT_6788 = "x" * 6788


def tall(n):
    """n photos 640×1386 (867 tokens chacune, mesuré)."""
    return [Image.new("RGB", (640, 1386)) for _ in range(n)]


class EstimationTest(unittest.TestCase):
    def test_calibration_sur_les_mesures_de_prod(self):
        self.assertEqual(estimate_image_tokens(640, 1386), 867)    # mesuré (diag_t1_image_budget, Catania)
        self.assertEqual(estimate_image_tokens(640, 296), 187)     # mesuré
        # 7 hautes + la basse = 7469 − 2080 mesurés ; la 8e haute fait dépasser 8192
        self.assertEqual(2080 + 7 * 867 + 187, 8336)

    def test_texte_estimation_prudente(self):
        self.assertGreaterEqual(estimate_text_tokens(PROMPT_6788), 2080)   # jamais sous la mesure réelle

    def test_minimum_un_patch(self):
        self.assertEqual(estimate_image_tokens(1, 1), 1 + budget.IMAGE_TOKEN_OVERHEAD)


class FitTest(unittest.TestCase):
    def test_tout_tient_aucune_modification(self):
        images = tall(2)
        out, info = fit_images_to_budget(images, PROMPT_6788, 8192, 600)
        self.assertIs(out, images)                       # mêmes objets : rien n'a bougé
        self.assertFalse(info["applied"])
        self.assertEqual(info["before"], info["after"])

    def test_desactive_si_contexte_zero(self):
        images = tall(8)
        out, info = fit_images_to_budget(images, PROMPT_6788, 0, 600)
        self.assertIs(out, images)
        self.assertFalse(info["applied"])

    def test_sans_photo(self):
        out, info = fit_images_to_budget([], PROMPT_6788, 8192, 600)
        self.assertEqual(out, [])
        self.assertFalse(info["applied"])

    def test_cas_catania_8_photos_reduites_sans_en_retirer(self):
        images = tall(7)[:6] + [Image.new("RGB", (640, 296))] + tall(1)        # 8 photos : total hors budget
        sizes_before = [i.size for i in images]
        out, info = fit_images_to_budget(images, PROMPT_6788, 8192, 600)
        self.assertTrue(info["applied"])
        self.assertEqual(len(out), 8)                    # AUCUNE photo retirée
        self.assertEqual(info["dropped"], 0)
        self.assertLess(info["scale"], 1.0)
        self.assertLessEqual(info["after"], info["budget"])
        self.assertGreater(info["before"], info["budget"])
        self.assertEqual([i.size for i in images], sizes_before)     # les originaux ne sont pas modifiés
        real_total = sum(estimate_image_tokens(*i.size) for i in out)
        self.assertLessEqual(real_total + estimate_text_tokens(PROMPT_6788), 8192 - 600)

    def test_coefficient_uniforme_et_proportions_gardees(self):
        out, info = fit_images_to_budget(tall(8), PROMPT_6788, 8192, 600)
        ratios = {round(o.size[0] / o.size[1], 2) for o in out}
        self.assertEqual(ratios, {round(640 / 1386, 2)})
        self.assertEqual(len({o.size for o in out}), 1)              # toutes réduites pareil

    def test_extreme_retire_les_dernieres_et_garde_les_premieres(self):
        huge = [Image.new("RGB", (4000, 4000)) for _ in range(6)]
        out, info = fit_images_to_budget(huge, PROMPT_6788, 3000, 600)       # budget minuscule
        self.assertTrue(info["applied"])
        self.assertGreater(info["dropped"], 0)
        self.assertEqual(len(out), 6 - info["dropped"])
        self.assertLessEqual(info["after"], info["budget"])

    def test_texte_seul_depasse_le_contexte_rien_a_sauver(self):
        images = tall(2)
        out, info = fit_images_to_budget(images, "x" * 40000, 8192, 600)
        self.assertIs(out, images)                       # on ne casse pas les photos pour un cas perdu d'avance
        self.assertFalse(info["applied"])

    def test_non_pil_leve_pour_que_la_prod_echoue_ouvert(self):
        with self.assertRaises(Exception):
            fit_images_to_budget([MagicMock()], PROMPT_6788, 8192, 600)


class MixinWiringTest(unittest.TestCase):
    def setUp(self):
        from backend.llm_clients import LLMClientsMixin
        self.Mixin = LLMClientsMixin

    def make(self):
        obj = self.Mixin.__new__(self.Mixin)
        obj.logger = MagicMock()
        return obj

    def test_local_recoit_les_photos_reduites_et_journalise(self):
        obj = self.make()
        images = tall(8)
        with patch.object(self.Mixin, "_call_openai_compatible_json", return_value=({"status": "FAIR"}, None)) as call:
            obj._call_t1_provider("local", PROMPT_6788, images, "gemini-x")
        sent = call.call_args.args[1]
        self.assertEqual(len(sent), 8)
        self.assertLess(sent[0].size[1], 1386)           # réduites
        self.assertEqual(images[0].size, (640, 1386))    # original intact
        self.assertTrue(any("photos réduites" in str(c) for c in obj.logger.info.call_args_list))

    def test_local_sans_depassement_envoie_les_memes_photos(self):
        obj = self.make()
        images = tall(2)
        with patch.object(self.Mixin, "_call_openai_compatible_json", return_value=({"status": "FAIR"}, None)) as call:
            obj._call_t1_provider("local", PROMPT_6788, images, "gemini-x")
        self.assertIs(call.call_args.args[1], images)
        obj.logger.info.assert_not_called()

    def test_qwen_cloud_garde_ses_photos_d_origine(self):
        obj = self.make()
        images = tall(8)
        with patch.object(self.Mixin, "_call_openai_compatible_json", return_value=({"status": "FAIR"}, None)) as call:
            obj._call_t1_provider("qwen", PROMPT_6788, images, "gemini-x")
        self.assertIs(call.call_args.args[1], images)    # seul le fournisseur local est concerné

    def test_echec_ouvert_si_la_correction_plante(self):
        obj = self.make()
        weird = [MagicMock()]                            # pas une photo PIL : la correction lève
        with patch.object(self.Mixin, "_call_openai_compatible_json", return_value=({"status": "FAIR"}, None)) as call:
            obj._call_t1_provider("local", PROMPT_6788, weird, "gemini-x")
        self.assertIs(call.call_args.args[1], weird)     # l'analyse continue avec les photos d'origine
        obj.logger.warning.assert_called()


if __name__ == "__main__":
    unittest.main()
