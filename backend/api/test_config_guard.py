import unittest

from backend.api import config_guard
from backend.api.config_guard import validate_config_patch


class ConfigGuardTest(unittest.TestCase):
    def test_valeurs_normales_acceptees(self):
        validate_config_patch({"scanConfig": {"frequency": 60, "max_ads": 5, "distance": 0, "min_price": 0, "max_price": 3000},
                               "analysisConfig": {"proTriggerPriceThreshold": 1500, "proTriggerDealScoreThreshold": 8,
                                                  "mainModel": "gemini-3.5-flash"},
                               "exclusionKeywords": ["ukulele"]})
        validate_config_patch({"scanConfig": {"frequency": ""}})  # champ vide du formulaire

    def test_frequence_trop_basse_refusee(self):
        for bad in (1, 4, 0, -5, 100000, "60", True):
            with self.assertRaises(ValueError, msg=bad):
                validate_config_patch({"scanConfig": {"frequency": bad}})

    def test_seuils_et_tailles(self):
        with self.assertRaises(ValueError):
            validate_config_patch({"analysisConfig": {"proTriggerDealScoreThreshold": 99}})
        with self.assertRaises(ValueError):
            validate_config_patch({"analysisConfig": {"mainPrompt": "x" * 40_000}})
        with self.assertRaises(ValueError):
            validate_config_patch({"analysisConfig": {"junk": ["x" * 1000] * 400}})
        with self.assertRaises(ValueError):
            validate_config_patch({"scanConfig": "oops"})


class MergedSizeTest(unittest.TestCase):
    def test_config_fusionnee_trop_grosse_refusee(self):
        config_guard.validate_merged_size({"a": "x" * 1000})
        with self.assertRaises(ValueError):
            config_guard.validate_merged_size({"a": "x" * (config_guard.MAX_CONFIG_BYTES + 1)})


if __name__ == "__main__":
    unittest.main()
