"""Tests unitaires des fonctions de correspondance (map_deal/map_chat_message/
map_restoration_item/map_city) de export_firestore_to_postgres.py.

Aucune dépendance Firestore/Postgres ici (contrairement à backend/api/test_*.py) : ces fonctions
sont pures (dict Python en entrée, dict de colonnes en sortie), donc testables sans base réelle —
seule façon de valider ce mapping avant un vrai dry-run, cette session n'ayant aucun accès
Firestore (voir docstring en tête de export_firestore_to_postgres.py).
"""
import unittest
from datetime import datetime

from backend.scripts.export_firestore_to_postgres import (
    DEAL_COLUMNS, map_city, map_chat_message, map_deal, map_restoration_item,
)


class TestMapDeal(unittest.TestCase):
    def test_all_declared_columns_are_present(self):
        """Garde-fou structurel : DEAL_COLUMNS doit rester synchronisé avec ce que map_deal
        produit réellement (sinon l'UPSERT généré dynamiquement lèverait un KeyError en plein
        export) — plus fiable qu'une relecture manuelle des deux listes à chaque évolution."""
        row, _ = map_deal("deal-1", {"title": "Test"})
        for column in DEAL_COLUMNS:
            if column == "user_id":
                continue  # rempli par l'appelant (_migrate_deal), pas par map_deal lui-même
            self.assertIn(column, row, f"colonne '{column}' absente du dict produit par map_deal")

    def test_scalar_and_camel_fields(self):
        data = {
            "title": "Parlor satinée", "price": 450, "original_price": 500,
            "price_drop_amount": 50, "link": "https://x", "location": "Québec",
            "latitude": 46.8, "longitude": -71.2, "published_at_raw": "il y a 2h",
            "published_at_ts": 1757000000,
            "isFavorite": True, "isPurchased": False, "manualClassification": "parlor",
            "purchasePrice": None, "initialVerdict": "GOOD_DEAL", "initialModelUsed": "gemini",
        }
        row, unmapped = map_deal("deal-1", data)
        self.assertEqual(row["title"], "Parlor satinée")
        self.assertEqual(row["original_price"], 500)
        self.assertTrue(row["is_favorite"])
        self.assertFalse(row["is_purchased"])
        self.assertEqual(row["manual_classification"], "parlor")
        self.assertEqual(row["initial_verdict"], "GOOD_DEAL")
        self.assertEqual(row["published_at_ts"], 1757000000)
        self.assertEqual(unmapped, [])

    def test_ai_analysis_promoted_and_kept_raw(self):
        data = {
            "title": "x",
            "aiAnalysis": {
                "verdict": "GOOD_DEAL", "classification": "acoustique_acier.parlor",
                "deal_score": 8.0, "authenticity_score": 9, "brand": "Gibson",
                "reasoning": "texte long non promu",
            },
        }
        row, _ = map_deal("deal-1", data)
        self.assertEqual(row["verdict"], "GOOD_DEAL")
        self.assertEqual(row["classification"], "acoustique_acier.parlor")
        self.assertEqual(row["deal_score"], 8)  # smallint : float -> int
        self.assertIsInstance(row["deal_score"], int)
        self.assertEqual(row["brand"], "Gibson")
        # Le dict aiAnalysis complet (y compris 'reasoning', jamais promu) reste disponible tel quel.
        self.assertEqual(row["ai_analysis_raw"]["reasoning"], "texte long non promu")
        self.assertEqual(row["ai_analysis_raw"]["verdict"], "GOOD_DEAL")

    def test_ai_analysis_as_list_is_handled_defensively(self):
        """Garde-fou déjà présent côté lecture Firestore (repository.py::_update_deal_index) —
        reproduit ici pour ne pas planter sur un document historique dans cette forme."""
        row, _ = map_deal("deal-1", {"aiAnalysis": [{"verdict": "GOOD_DEAL"}]})
        self.assertEqual(row["verdict"], "GOOD_DEAL")

    def test_unmapped_top_level_fields_are_preserved_not_dropped(self):
        row, unmapped = map_deal("deal-1", {"title": "x", "champInconnu": 42})
        self.assertEqual(unmapped, ["champInconnu"])
        self.assertEqual(row["ai_analysis_raw"]["_unmapped"]["champInconnu"], 42)

    def test_sold_notes_promoted_to_own_column(self):
        """soldNotes a sa propre colonne (sold_notes) depuis la Phase A.1 (bascule bot) — plus
        besoin de la ranger dans ai_analysis_raw['_unmapped'] comme au tout premier jet."""
        row, unmapped = map_deal("deal-1", {"title": "x", "soldNotes": [{"info": "vendu cher"}]})
        self.assertEqual(row["sold_notes"], [{"info": "vendu cher"}])
        self.assertEqual(unmapped, [])

    def test_missing_status_defaults_to_analyzed(self):
        row, _ = map_deal("deal-1", {"title": "x"})
        self.assertEqual(row["status"], "analyzed")

    def test_missing_favorite_and_purchased_default_to_false_not_null(self):
        """is_favorite/is_purchased sont NOT NULL côté Postgres — un document Firestore ancien
        sans ces clés doit retomber sur False (bug réel trouvé par le test d'intégration contre
        un vrai Postgres, un NotNullViolationError invisible depuis ce seul test pur)."""
        row, _ = map_deal("deal-1", {"title": "x"})
        self.assertIs(row["is_favorite"], False)
        self.assertIs(row["is_purchased"], False)

    def test_timestamp_fields_pass_through_real_datetimes(self):
        ts = datetime(2026, 9, 1, 12, 0, 0)
        row, _ = map_deal("deal-1", {"timestamp": ts, "soldAt": ts})
        self.assertEqual(row["timestamp"], ts)
        self.assertEqual(row["sold_at"], ts)

    def test_chunk_id_silently_dropped_without_warning(self):
        """chunkId est un artefact du sharding deals_index (remplacé par de vrais index SQL,
        voir schema.sql) — volontairement PAS dans ai_analysis_raw['_unmapped']."""
        row, unmapped = map_deal("deal-1", {"title": "x", "chunkId": "chunk_3"})
        self.assertEqual(unmapped, [])


class TestMapChatMessage(unittest.TestCase):
    def test_basic_fields(self):
        data = {"role": "user", "parts": [{"text": "salut"}], "displayText": "salut",
                "createdAt": datetime(2026, 9, 1)}
        row = map_chat_message("deal-1", data)
        self.assertEqual(row["role"], "user")
        self.assertEqual(row["display_text"], "salut")
        self.assertFalse(row["is_error"])

    def test_restoration_proposal_states_merged_into_proposals(self):
        data = {
            "role": "model",
            "restorationProposals": [{"label": "Refret"}, {"label": "Nettoyage"}],
            "restorationProposalStates": {"0": {"status": "applied", "itemId": "fs-item-1"}},
        }
        row = map_chat_message("deal-1", data)
        self.assertEqual(row["restoration_proposals"][0]["status"], "applied")
        self.assertEqual(row["restoration_proposals"][0]["itemId"], "fs-item-1")
        self.assertEqual(row["restoration_proposals"][0]["label"], "Refret")
        # Le deuxième élément n'a pas d'état -> inchangé.
        self.assertNotIn("status", row["restoration_proposals"][1])

    def test_requalification_proposal_state_merged(self):
        data = {
            "role": "model",
            "requalificationProposal": {"classification": "acoustique_acier.dreadnought"},
            "requalificationProposalState": {"status": "applied"},
        }
        row = map_chat_message("deal-1", data)
        self.assertEqual(row["requalification_proposal"]["status"], "applied")
        self.assertEqual(row["requalification_proposal"]["classification"], "acoustique_acier.dreadnought")

    def test_no_state_leaves_proposals_untouched(self):
        data = {"role": "model", "restorationProposals": [{"label": "Refret"}]}
        row = map_chat_message("deal-1", data)
        self.assertEqual(row["restoration_proposals"], [{"label": "Refret"}])


class TestMapRestorationItem(unittest.TestCase):
    def test_defaults(self):
        row = map_restoration_item("deal-1", {"label": "Refret"}, proposed_by_message_id=None)
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["source"], "user")
        self.assertIsNone(row["proposed_by_message_id"])
        self.assertEqual(row["updated_at"], row["created_at"])  # repli sur created_at si absent

    def test_proposed_by_message_id_passed_through_when_resolved(self):
        row = map_restoration_item("deal-1", {"label": "x", "proposedByMessageId": "fs-msg-1"}, proposed_by_message_id=42)
        self.assertEqual(row["proposed_by_message_id"], 42)

    def test_order_and_photo_urls(self):
        row = map_restoration_item("deal-1", {"label": "x", "order": 2, "photoUrls": ["a.jpg"]}, proposed_by_message_id=None)
        self.assertEqual(row["item_order"], 2)
        self.assertEqual(row["photo_urls"], ["a.jpg"])


class TestMapCity(unittest.TestCase):
    def test_basic(self):
        row = map_city("12345", {"name": "Québec", "latitude": 46.8, "longitude": -71.2})
        self.assertEqual(row["id"], "12345")
        self.assertFalse(row["needs_review"])
        self.assertIsNone(row["created_by"])

    def test_needs_review_flag(self):
        row = map_city("12345", {"name": "Saint-Lambert", "needsReview": True, "createdBy": "uid-1"})
        self.assertTrue(row["needs_review"])
        self.assertEqual(row["created_by"], "uid-1")


if __name__ == "__main__":
    unittest.main()
