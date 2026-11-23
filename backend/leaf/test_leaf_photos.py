"""Lecture des photos par l'IA de Leaf : garde-fou, tri/lecture, cache, plafond. Données INVENTÉES (dépôt public), modèles SIMULÉS, images PIL
générées : aucun appel réseau. Les tests qui touchent la base se sautent sans `KB_TEST_DATABASE_URL`."""
import unittest

from PIL import Image

from backend.leaf import ai, photo_extract as px

K = lambda n, size=200: f"https://media.kijiji.ca/api/v1/ca-prod-fsbo-ads/images/{n}?rule=kijijica-{size}-jpg"
A = "https://prod.pictures.autoscout24.net/listing-images/abc_def.jpg/360x270.webp"


def listing(**kw):
    base = {"id": "leaf_test_1", "km": 90000, "image_urls": [K(i) for i in range(6)], "soh_announced": None}
    base.update(kw)
    return base


class TestUrls(unittest.TestCase):
    def test_sized_url_matches_the_front_helper(self):
        self.assertEqual(px.sized_url(K("a"), "large"), K("a", 1600))
        self.assertEqual(px.sized_url(K("a", 1600), "thumb"), K("a", 200))
        self.assertEqual(px.sized_url(A, "large"), A.replace("360x270", "1280x960"))
        self.assertEqual(px.sized_url("https://exemple.invalide/p.jpg", "large"), "https://exemple.invalide/p.jpg")
        self.assertEqual(px.sized_url(None), "")

    def test_fingerprint_ignores_the_requested_size_but_not_the_photos(self):
        a = px.fingerprint([K(0), K(1)])
        self.assertEqual(a, px.fingerprint([K(0, 1600), K(1, 640)]))
        self.assertEqual(px.fingerprint([A]), px.fingerprint([A.replace("360x270", "1280x960")]))
        self.assertNotEqual(a, px.fingerprint([K(0), K(2)]))
        self.assertNotEqual(a, px.fingerprint([K(1), K(0)]))

    def test_photo_urls_https_unique_and_capped(self):
        urls = px.photo_urls({"image_urls": [K(0), K(0), "http://non-https.invalide/x.jpg", 3, K(1)] + [K(i) for i in range(2, 30)]})
        self.assertEqual((urls[:2], len(urls)), ([K(0), K(1)], 16))


class TestParse(unittest.TestCase):
    def test_triage_keeps_valid_unique_indices_up_to_three(self):
        self.assertEqual(px.parse_triage({"indices": [2, 2, 9, -1, True, "1", 0, 4, 5, 3]}, 6), [2, 0, 4, 5])
        for bad in (None, [], {"indices": "x"}, {}):
            self.assertEqual(px.parse_triage(bad, 6), [])

    def test_readings_need_a_sent_photo_and_a_short_text(self):
        raw = {"readings": [{"photo": 0, "transcript": "SOH 91 %"}, {"photo": 5, "transcript": "hors plage"}, {"photo": 1, "transcript": "x"},
                            {"photo": 1, "transcript": "y" * 200}, {"photo": 1, "transcript": 5}, "z", {"photo": True, "transcript": "SOH 90 %"}]}
        self.assertEqual(px.parse_readings(raw, 2), [{"photo": 0, "transcript": "SOH 91 %"}])
        self.assertEqual(px.parse_readings({"readings": "x"}, 2), [])


class TestGuardrails(unittest.TestCase):
    def guard(self, *texts, km=90000, numbering=(4, 2, 7)):
        readings = [{"photo": i, "transcript": t} for i, t in enumerate(texts)]
        return px.apply_guardrails(readings, list(numbering), {"km": km})

    def test_soh_is_recomputed_from_the_transcript_and_carries_its_photo_number(self):
        out = self.guard("LeafSpy SOH 61,2 %", "Ahr 41.0")
        self.assertEqual(out["facts"]["soh_photo"], {"value": 61.2, "evidence": "LeafSpy SOH 61,2 %", "photo": 4, "source": "photo", "confidence": "low"})
        self.assertEqual((out["facts"]["ahr_photo"]["value"], out["facts"]["ahr_photo"]["photo"]), (41.0, 2))

    def test_transcripts_without_the_expected_format_give_nothing(self):
        out = self.guard("Batterie bonne", "87", "Température 20 °C", "SOH élevé")
        self.assertEqual((out["facts"], out["flags"]), ({}, []))

    def test_out_of_range_values_are_refused(self):
        self.assertEqual(self.guard("SOH 30 %", "Ahr 9")["facts"], {})
        self.assertEqual(self.guard("SOH 120 %")["facts"], {})

    def test_dashboard_bars_are_never_read_as_a_fact(self):
        self.assertEqual(self.guard("6 barres sur 12")["facts"], {})

    def test_km_only_raises_a_flag_never_replaces_the_listing(self):
        self.assertEqual(self.guard("Odo 148 000 km")["flags"], ["photo_km_mismatch"])
        self.assertEqual(self.guard("Odo 91 000 km")["flags"], [])                  # écart de 1 % : toléré
        self.assertEqual(self.guard("Odo 148 000 km", km=None)["flags"], [])
        self.assertNotIn("km", self.guard("Odo 148 000 km")["facts"])

    def test_first_soh_wins_when_several_photos_show_one(self):
        out = self.guard("SOH 88 %", "SOH 61 %")
        self.assertEqual(out["facts"]["soh_photo"]["value"], 88.0)


class FakeVision:
    """Simule `DealAnalyzer` : tri puis lecture sur le Dell, ou lecture directe sur Gemini."""
    def __init__(self, triage=None, readings=None, gemini=None, local_error=None, images=None):
        self.triage, self.readings, self.gemini, self.local_error, self.images = triage, readings, gemini, local_error, images
        self.calls, self.downloads = [], []

    def _download_images(self, urls):
        self.downloads.append(list(urls))
        n = len(urls) if self.images is None else self.images
        return [Image.new("RGB", (64, 64)) for _ in range(n)]

    def _fit_t1_local_images(self, prompt, images):
        return images

    def _call_openai_compatible_json(self, prompt, images, model, key, url, **kw):
        schema = (kw.get("response_format") or {}).get("json_schema", {}).get("name")
        if schema is None:                                    # appel de l'IA TEXTE : non simulé ici
            return None, "texte non simulé"
        self.calls.append(("local", schema, kw.get("action"), len(images)))
        if self.local_error:
            return None, self.local_error
        return (self.triage if schema == "leaf_photo_triage" else self.readings), None

    def _call_gemini_json(self, model, parts, **kw):
        self.calls.append(("gemini", None, kw.get("action"), len(parts) - 1))
        return (self.gemini, None) if self.gemini is not None else (None, "quota")


class TestReadPhotos(unittest.TestCase):
    def setUp(self):
        from backend import t1_circuit_breaker
        t1_circuit_breaker.record_success("local")
        self.addCleanup(t1_circuit_breaker.record_success, "local")

    def test_dell_triages_thumbnails_then_reads_only_the_selected_photos_in_high_resolution(self):
        v = FakeVision(triage={"indices": [3, 1]}, readings={"readings": [{"photo": 0, "transcript": "LeafSpy SOH 61,2 %"}]})
        out, err = ai.LeafAI(v).read_photos(listing())
        self.assertIsNone(err)
        self.assertEqual([c[:3] for c in v.calls], [("local", "leaf_photo_triage", "leaf_photo"), ("local", "leaf_photo_read", "leaf_photo")])
        self.assertEqual(v.downloads[0], [K(i, 640) for i in range(6)])               # tri : TOUTES les photos, en résolution moyenne
        self.assertEqual(v.downloads[1], [K(3, 1600), K(1, 1600)])                    # lecture : seulement les 2 retenues, en 1600 px
        self.assertEqual((out["selected"], out["provider"]), ([4, 2], "local"))       # numéros de la fiche, à partir de 1
        self.assertEqual((out["facts"]["soh_photo"]["value"], out["facts"]["soh_photo"]["photo"]), (61.2, 4))
        self.assertEqual(out["readings"], [{"photo": 4, "transcript": "LeafSpy SOH 61,2 %"}])
        self.assertEqual(out["fingerprint"], px.fingerprint(listing()["image_urls"]))

    def test_the_last_of_eleven_photos_can_be_selected_and_read(self):
        v = FakeVision(triage={"indices": [10]}, readings={"readings": [{"photo": 0, "transcript": "Ahr 41.0"}]})
        out, _ = ai.LeafAI(v).read_photos(listing(image_urls=[K(i) for i in range(11)]))
        self.assertEqual((len(v.downloads[0]), v.downloads[1], out["selected"]), (11, [K(10, 1600)], [11]))
        self.assertEqual(out["facts"]["ahr_photo"]["photo"], 11)

    def test_nothing_selected_means_no_reading_call(self):
        v = FakeVision(triage={"indices": []})
        out, err = ai.LeafAI(v).read_photos(listing())
        self.assertEqual((err, out["facts"], out["selected"], len(v.calls)), (None, {}, [], 1))

    def test_a_reading_that_invents_a_value_is_dropped_by_the_guardrail(self):
        v = FakeVision(triage={"indices": [0]}, readings={"readings": [{"photo": 0, "transcript": "Batterie en excellent état"}]})
        out, _ = ai.LeafAI(v).read_photos(listing())
        self.assertEqual(out["facts"], {})

    def test_dell_failure_falls_back_to_gemini_which_reads_every_photo_including_the_last_one(self):
        v = FakeVision(local_error="timeout", gemini={"readings": [{"photo": 2, "transcript": "SOH 77 %"}]})
        out, err = ai.LeafAI(v).read_photos(listing(image_urls=[K(i) for i in range(11)]))
        self.assertEqual((err, out["provider"]), (None, "gemini"))
        self.assertEqual((len(v.downloads[-1]), v.downloads[-1][0], v.downloads[-1][-1]), (11, K(0, 640), K(10, 640)))   # la 11e photo (tableau de bord) incluse
        self.assertEqual((out["facts"]["soh_photo"]["value"], out["facts"]["soh_photo"]["photo"]), (77.0, 3))

    def test_a_dead_dell_is_not_called_again_after_three_failures(self):
        v = FakeVision(local_error="timeout", gemini={"readings": []})
        for _ in range(3):
            ai.LeafAI(v).read_photos(listing())
        v.calls.clear()
        ai.LeafAI(v).read_photos(listing())
        self.assertEqual([c[0] for c in v.calls], ["gemini"])

    def test_missing_downloads_never_misnumber_the_photos(self):
        v = FakeVision(triage={"indices": [0]}, images=3, gemini=None)                # 3 vignettes sur 6 : abandon, pas de décalage
        out, err = ai.LeafAI(v).read_photos(listing())
        self.assertIsNone(out)
        self.assertIn("incomplètes", err)

    def test_no_photo_no_analyzer_unknown_provider(self):
        self.assertEqual(ai.LeafAI(FakeVision()).read_photos(listing(image_urls=[])), (None, "aucune photo"))
        self.assertEqual(ai.LeafAI(None).read_photos(listing())[1], "Analyseur indisponible (bot hors ligne).")
        self.assertEqual(ai.LeafAI(FakeVision()).read_photos(listing(), ("nope",))[0], None)


if __name__ == "__main__":
    unittest.main()
