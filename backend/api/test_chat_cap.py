"""Plafond quotidien du chat par utilisateur (revue R-6-4) — sans base : la dépense est simulée."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.api import cost_alert, main


class ChatCapTest(unittest.TestCase):
    def _run(self, cost, admin=False):
        with patch.object(cost_alert, "user_today_chat_cost", AsyncMock(return_value=cost)), \
             patch.object(main, "is_admin_uid", return_value=admin):
            return asyncio.run(main._enforce_chat_cap(None, "uid"))

    def test_sous_le_plafond_passe(self):
        self.assertIsNone(self._run(0.5))

    def test_au_dela_du_plafond_refuse_429(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run(cost_alert.USER_DAILY_CAP_USD + 0.01)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_administrateur_non_plafonne(self):
        self.assertIsNone(self._run(99.0, admin=True))


class ChatPayloadTest(unittest.TestCase):
    """Revue R-6-5 : rôle et taille d'un message de chat."""

    def test_roles_et_taille(self):
        main._check_chat_payload("user", [{"text": "ok"}])
        main._check_chat_payload("model", [{"text": "ok"}])
        main._check_chat_payload(None, [{"text": "ok"}])
        for role in ("system", "assistant", "admin"):
            with self.assertRaises(HTTPException):
                main._check_chat_payload(role, [])
        with self.assertRaises(HTTPException):
            main._check_chat_payload("user", ["x" * (main.MAX_CHAT_PARTS_BYTES + 1)])


if __name__ == "__main__":
    unittest.main()
