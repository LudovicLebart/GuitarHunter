"""Accès Postgres du bot pour Leaf Hunter (pool SYNCHRONE `backend.pg_db`, comme `pg_repository.py`).

Tables : `vehicle_deals`, `user_vehicle_matches`, `vehicle_price_history` (voir `backend/api/schema.sql`). Ne touche à
AUCUNE table guitare. Le logger est passé par l'appelant (piège du logger : seul `bot.{uid8}` est visible dans l'app)."""
import logging
from typing import Any, Dict, Iterable, List, Optional

from psycopg.types.json import Jsonb

_COLUMNS = ("source", "source_id", "link", "title", "description", "year", "trim", "km", "battery_kwh_low",
            "battery_kwh_high", "battery_source", "soh_announced", "soh_evidence", "capacity_bars", "vin",
            "seller_type", "location", "latitude", "longitude", "distance_km", "verdict", "duplicate_of")
_ANALYSIS_KEYS = ("battery_score", "winter_fit", "equipment", "risk_flags", "mentions", "capacity_bars_evidence",
                  "detail_unavailable")


def listing_to_row(listing: Dict[str, Any]) -> Dict[str, Any]:
    """Annonce passée par le pipeline -> colonnes de `vehicle_deals` (la ville va dans `location`, l'URL dans `link`)."""
    row = {c: listing.get(c) for c in _COLUMNS}
    row["link"] = listing.get("url") or listing.get("link")
    row["location"] = listing.get("city") or listing.get("location")
    row["flags"] = list(listing.get("flags") or [])
    row["image_urls"] = list(listing.get("image_urls") or [])
    row["analysis"] = {k: listing[k] for k in _ANALYSIS_KEYS if listing.get(k) is not None}
    return row


class LeafRepository:
    def __init__(self, pool, logger: Optional[logging.Logger] = None):
        self.pool = pool
        self.log = logger or logging.getLogger(__name__)

    def upsert_listing(self, listing: Dict[str, Any]) -> Dict[str, Any]:
        """Crée ou met à jour l'annonce. Retourne {'action': 'new'|'price_drop'|'price_up'|'unchanged',
        'previous_price'}. Une annonce revue redevient active ; chaque changement de prix ajoute un point d'historique."""
        deal_id, price = listing["id"], listing.get("price")
        row = listing_to_row(listing)
        with self.pool.connection() as conn:
            with conn.transaction():
                old = conn.execute("SELECT price, original_price, price_drop_amount FROM vehicle_deals WHERE id = %s "
                                   "FOR UPDATE", (deal_id,)).fetchone()
                previous = float(old["price"]) if old and old["price"] is not None else None
                if old is None:
                    action = "new"
                elif price is None or previous is None or float(price) == previous:
                    action = "unchanged"
                else:
                    action = "price_drop" if float(price) < previous else "price_up"
                drop = old["price_drop_amount"] if old else None
                if action == "price_drop":
                    drop = previous - float(price)
                elif action == "price_up":
                    drop = None
                original = old["original_price"] if old and old["original_price"] is not None else price
                params = {**{k: (Jsonb(v) if isinstance(v, (dict, list)) else v) for k, v in row.items()},
                          "id": deal_id, "price": price, "original_price": original, "price_drop_amount": drop}
                cols = list(params)
                updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("id", "original_price"))
                conn.execute(
                    f"INSERT INTO vehicle_deals ({', '.join(cols)}) VALUES ({', '.join('%(' + c + ')s' for c in cols)}) "
                    f"ON CONFLICT (id) DO UPDATE SET {updates}, status = 'active', sold_at = NULL, "
                    f"last_seen_at = now(), \"timestamp\" = now()", params)
                if action in ("new", "price_drop", "price_up") and price is not None:
                    conn.execute("INSERT INTO vehicle_price_history (deal_id, price) VALUES (%s, %s)", (deal_id, price))
        return {"action": action, "previous_price": previous}

    def record_match(self, user_id: str, deal_id: str) -> bool:
        """Rend l'annonce visible pour l'utilisateur. True si le lien est nouveau."""
        with self.pool.connection() as conn:
            cur = conn.execute("INSERT INTO user_vehicle_matches (user_id, deal_id) VALUES (%s, %s) "
                               "ON CONFLICT DO NOTHING", (user_id, deal_id))
            return cur.rowcount > 0

    def touch_seen(self, deal_ids: Iterable[str]) -> int:
        """Annonce revue sans changement : met à jour `last_seen_at` (et la réactive si elle était marquée vendue)."""
        ids = list(deal_ids)
        if not ids:
            return 0
        with self.pool.connection() as conn:
            return conn.execute("UPDATE vehicle_deals SET last_seen_at = now(), status = 'active', sold_at = NULL "
                                "WHERE id = ANY(%s)", (ids,)).rowcount

    def mark_sold(self, deal_ids: Iterable[str]) -> int:
        ids = list(deal_ids)
        if not ids:
            return 0
        with self.pool.connection() as conn:
            return conn.execute("UPDATE vehicle_deals SET status = 'sold', sold_at = now(), \"timestamp\" = now() "
                                "WHERE id = ANY(%s) AND status <> 'sold'", (ids,)).rowcount

    def active_ids(self, source: Optional[str] = None) -> List[str]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT id FROM vehicle_deals WHERE status = 'active' AND (%s::text IS NULL OR source = %s)",
                                (source, source)).fetchall()
        return [r["id"] for r in rows]

    def get_vehicle(self, deal_id: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            return conn.execute("SELECT * FROM vehicle_deals WHERE id = %s", (deal_id,)).fetchone()

    def price_history(self, deal_id: str) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            return conn.execute("SELECT price, seen_at FROM vehicle_price_history WHERE deal_id = %s ORDER BY seen_at, id",
                                (deal_id,)).fetchall()

    def comparables(self) -> List[Dict[str, Any]]:
        """Annonces actives avec année, km et prix, pour la régression `scoring.price_fit`."""
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT year, km, price FROM vehicle_deals WHERE status = 'active' AND year IS NOT NULL "
                                "AND km IS NOT NULL AND price IS NOT NULL").fetchall()
        return [{"year": r["year"], "km": r["km"], "price": float(r["price"])} for r in rows]

    # ------------------------------------------------------------------ passages et configuration

    def get_leaf_config(self, user_id: str) -> Dict[str, Any]:
        """`users.config.leafConfig` brut ({} si absent : Leaf désactivé)."""
        with self.pool.connection() as conn:
            row = conn.execute("SELECT config FROM users WHERE uid = %s", (user_id,)).fetchone()
        cfg = (row or {}).get("config") or {}
        return cfg.get("leafConfig") or {}

    def record_run(self, user_id: str, source: str, outcome: str, detail: Optional[str] = None,
                   cards_seen: Optional[int] = None, kept: Optional[int] = None,
                   duration_ms: Optional[int] = None) -> None:
        """Un passage d'une source dans `scrape_runs` (source `leaf_<nom>`, distincte de `facebook`/`kijiji`)."""
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO scrape_runs (user_id, source, outcome, detail, cards_seen, kept, duration_ms) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                         (user_id, f"leaf_{source}", outcome, detail, cards_seen, kept, duration_ms))

    def recent_outcomes(self, user_id: str, source: str, limit: int = 5) -> List[str]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT outcome FROM scrape_runs WHERE user_id = %s AND source = %s "
                                "ORDER BY created_at DESC, id DESC LIMIT %s", (user_id, f"leaf_{source}", limit)).fetchall()
        return [r["outcome"] for r in rows]

    def mark_stale_sold(self, days: int = 7) -> int:
        """Annonces actives non revues depuis `days` jours : marquées vendues (nettoyage `LEAF_CLEANUP`)."""
        with self.pool.connection() as conn:
            return conn.execute("UPDATE vehicle_deals SET status = 'sold', sold_at = now(), \"timestamp\" = now() "
                                "WHERE status = 'active' AND last_seen_at < now() - make_interval(days => %s)",
                                (days,)).rowcount
