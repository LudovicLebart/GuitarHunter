"""Accès SQL (Postgres) pour le bot — miroir SYNCHRONE de `backend/repository.py`
(`FirestoreRepository`), même interface publique, pour que `backend/bot.py` puisse basculer
dessus sans réécriture (Phase A.1 du protocole de bascule, voir
`docs/management/plans/FIRESTORE_MIGRATION_PLAN.md` §5.3).

`deals_index` (sharding Firestore, 20 chunks) n'a pas d'équivalent ici — remplacé par de vraies
requêtes SQL indexées nativement (voir schema.sql). `get_deals_index_snapshot()` est repris tel
quel comme NOM de méthode (zéro changement dans bot.py) mais sa mise en oeuvre interroge
directement `guitar_deals`, pas un index à part.

Plusieurs méthodes de lecture (`get_deal_by_id`, `get_active_listings`, `get_retry_queue_listings`)
retournent des formes compatibles avec ce que `bot.py` lit AUJOURD'HUI d'un document/snapshot
Firestore (clés camelCase où c'est le cas côté Firestore, objets `.id`/`.to_dict()` pour les
requêtes multi-documents) — tracé méthode par méthode dans `bot.py`/`backend/services.py`, pas
une reconstruction générique et exhaustive du document Firestore d'origine.
"""
import logging
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from backend.deal_mapping import (
    AI_ANALYSIS_COLUMNS,
    CITY_FIELD_TO_COLUMN,
    DEAL_COLUMNS,
    DEAL_FIELD_TO_COLUMN,
    map_city,
    map_deal,
)

logger = logging.getLogger(__name__)


class _Row:
    """Duck-type minimal d'un DocumentSnapshot Firestore (`.id`/`.to_dict()`) — bot.py consomme
    `get_active_listings()`/`get_retry_queue_listings()`/`get_pending_commands()` sous cette
    forme ; reproduire l'interface plutôt que de modifier chaque site d'appel."""
    __slots__ = ("id", "_data")

    def __init__(self, id_, data):
        self.id = id_
        self._data = data

    def to_dict(self):
        return self._data


def _to_pg_param(value):
    """psycopg n'adapte pas automatiquement un dict/list Python en JSONB à l'écriture
    (contrairement à la lecture, où le JSONB revient déjà décodé) — contrairement à asyncpg
    (voir backend/api/db.py::_register_json_codecs), qui a été configuré pour le faire."""
    if isinstance(value, (dict, list)):
        return Jsonb(value)
    return value


def _deal_row_to_bot_shape(row: dict) -> dict:
    """Adapte une ligne `guitar_deals` (colonnes snake_case) aux quelques alias camelCase que
    `backend/bot.py` lit encore (`imageUrls`/`storageImageUrls`) — les champs partagés entre les
    deux mondes (`status`/`price`/`title`/`location`/`link`/`latitude`/`longitude`/`description`,
    tous issus du scraper tels quels côté Firestore) n'ont besoin d'aucun alias."""
    shaped = dict(row)
    shaped["imageUrls"] = row.get("image_urls")
    shaped["imageUrl"] = None  # jamais réellement écrit ; présent par défensive côté bot.py uniquement
    shaped["storageImageUrls"] = row.get("storage_image_urls")
    return shaped


class PostgresRepository:
    def __init__(self, pool, user_id: str, bucket=None, logger=None):
        """`logger` optionnel (repli sur le logger de module) : voir CLAUDE.md — tout module
        backend qui logue quelque chose d'observable par l'utilisateur doit accepter ce
        paramètre et le faire propager depuis `bot.py`, sans quoi ses logs (annonce créée,
        commande traitée, ...) resteraient invisibles dans le LogViewer (seul `bot.{uid[:8]}`,
        raccordé à `FirestoreHandler`, y est visible — piège déjà documenté et déjà rencontré
        dans d'autres modules, reproduit ici une première fois puis corrigé par cette revue)."""
        self.pool = pool
        self.user_id = user_id
        self._bucket = bucket
        self.logger = logger or logging.getLogger(__name__)

    # ------------------------------------------------------------------ structure / config

    def ensure_initial_structure(self, initial_config: dict):
        with self.pool.connection() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE uid = %s", (self.user_id,)).fetchone()
            if row is None:
                self.logger.info(f"User document for {self.user_id} not found. Creating with initial config.")
                conn.execute(
                    "INSERT INTO users (uid, bot_status, config) VALUES (%s, 'idle', %s)",
                    (self.user_id, _to_pg_param(initial_config)),
                )
            else:
                self.logger.info("User document already exists. Config preserved.")

    def get_user_config(self):
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT bot_status, config FROM users WHERE uid = %s", (self.user_id,)
            ).fetchone()
        if not row:
            return None
        return {**(row["config"] or {}), "botStatus": row["bot_status"]}

    def update_bot_status(self, status: str):
        with self.pool.connection() as conn:
            conn.execute("UPDATE users SET bot_status = %s WHERE uid = %s", (status, self.user_id))

    # ------------------------------------------------------------------ deals : lecture

    def get_deal_by_id(self, deal_id: str):
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM guitar_deals WHERE id = %s AND user_id = %s", (deal_id, self.user_id)
            ).fetchone()
        return _deal_row_to_bot_shape(row) if row else None

    def get_deals_index_snapshot(self):
        """Remplace l'index en chunks Firestore par une lecture directe — mêmes clés abrégées
        que côté Firestore (`title`/`p`/`la`/`lo`/`l`), seules consommées par
        `bot.py::_find_cross_platform_duplicate`/`_build_kijiji_city_labels`, pour zéro
        changement dans ces deux méthodes."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, title, price, latitude, longitude, location FROM guitar_deals WHERE user_id = %s",
                (self.user_id,),
            ).fetchall()
        return {
            row["id"]: {
                "title": row["title"], "p": row["price"],
                "la": row["latitude"], "lo": row["longitude"], "l": row["location"],
            }
            for row in rows
        }

    def get_active_listings(self):
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, link FROM guitar_deals WHERE user_id = %s AND status = 'analyzed'",
                (self.user_id,),
            ).fetchall()
        return [_Row(row["id"], {"link": row["link"]}) for row in rows]

    def get_retry_queue_listings(self):
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM guitar_deals WHERE user_id = %s AND status = 'retry_analysis'",
                (self.user_id,),
            ).fetchall()
        return [_Row(row["id"], _deal_row_to_bot_shape(row)) for row in rows]

    def delete_listing(self, listing_id: str):
        with self.pool.connection() as conn:
            conn.execute(
                "DELETE FROM guitar_deals WHERE id = %s AND user_id = %s", (listing_id, self.user_id)
            )

    # ------------------------------------------------------------------ deals : écriture

    def _get_manual_classification(self, deal_id: str):
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT manual_classification FROM guitar_deals WHERE id = %s AND user_id = %s",
                (deal_id, self.user_id),
            ).fetchone()
        return row and row.get("manual_classification")

    def _get_manual_analysis_overrides(self, deal_id: str) -> dict:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT manual_analysis_overrides FROM guitar_deals WHERE id = %s AND user_id = %s",
                (deal_id, self.user_id),
            ).fetchone()
        return (row and row.get("manual_analysis_overrides")) or {}

    def create_new_deal(self, deal_id: str, deal_data: dict, analysis_data: dict):
        status = "analyzed"
        if analysis_data.get("verdict") == "REJECTED":
            status = "rejected"
        merged = {
            **deal_data,
            "aiAnalysis": analysis_data,
            "timestamp": datetime.now(timezone.utc),
            "status": status,
            "initialVerdict": analysis_data.get("verdict"),
            "initialModelUsed": analysis_data.get("model_used"),
        }
        row, _unmapped = map_deal(deal_id, merged)
        row["user_id"] = self.user_id

        placeholders = ", ".join(["%s"] * len(DEAL_COLUMNS))
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in DEAL_COLUMNS if c != "id")
        with self.pool.connection() as conn:
            cursor = conn.execute(
                f"INSERT INTO guitar_deals ({', '.join(DEAL_COLUMNS)}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {set_clause} "
                f"WHERE guitar_deals.user_id = EXCLUDED.user_id",
                [_to_pg_param(row[c]) for c in DEAL_COLUMNS],
            )
            if cursor.rowcount == 0:
                self.logger.warning(
                    f"create_new_deal: id '{deal_id}' existe déjà pour un AUTRE utilisateur — "
                    f"écriture ignorée pour ne pas réassigner l'appartenance de l'annonce."
                )
                return
        self.logger.info(f"Created new deal '{deal_data.get('title', deal_id)}' with status '{status}'.")

    def update_deal_analysis(self, deal_id: str, analysis_data: dict):
        """Ne touche QUE les colonnes promues depuis aiAnalysis + ai_analysis_raw + status/
        timestamp — jamais les colonnes issues de `deal_data` (titre, prix, ...), absentes d'une
        simple ré-analyse, exactement comme le `.update()` partiel Firestore d'origine."""
        manual_overrides = self._get_manual_analysis_overrides(deal_id)
        if manual_overrides:
            analysis_data = {**analysis_data, **manual_overrides}
        status = "analyzed"
        if analysis_data.get("verdict") == "REJECTED":
            status = "rejected"

        row, _ = map_deal(deal_id, {"aiAnalysis": analysis_data})
        columns = AI_ANALYSIS_COLUMNS + ["ai_analysis_raw"]
        set_parts = [f"{c} = %s" for c in columns] + ["status = %s", '"timestamp" = %s']
        values = [_to_pg_param(row[c]) for c in columns] + [status, datetime.now(timezone.utc)]
        with self.pool.connection() as conn:
            conn.execute(
                f"UPDATE guitar_deals SET {', '.join(set_parts)} WHERE id = %s AND user_id = %s",
                [*values, deal_id, self.user_id],
            )
        self.logger.info(f"Updated analysis for deal '{deal_id}' with status '{status}'.")

    def update_deal_data_and_analysis(self, deal_id: str, deal_data: dict, analysis_data: dict):
        """Équivalent du `.update()` Firestore qui fusionne `deal_data` au niveau racine du
        document : ne touche QUE les colonnes correspondant aux clés réellement présentes dans
        `deal_data` (+ toujours les colonnes aiAnalysis/status/timestamp) — jamais les autres,
        contrairement à `create_new_deal` (INSERT complet)."""
        manual_overrides = self._get_manual_analysis_overrides(deal_id)
        if manual_overrides:
            analysis_data = {**analysis_data, **manual_overrides}
        status = "analyzed"
        if analysis_data.get("verdict") == "REJECTED":
            status = "rejected"

        row, _ = map_deal(deal_id, {**deal_data, "aiAnalysis": analysis_data})
        deal_data_columns = [DEAL_FIELD_TO_COLUMN[k] for k in deal_data if k in DEAL_FIELD_TO_COLUMN]
        columns = list(dict.fromkeys(deal_data_columns + AI_ANALYSIS_COLUMNS + ["ai_analysis_raw"]))
        set_parts = [f"{c} = %s" for c in columns] + ["status = %s", '"timestamp" = %s']
        values = [_to_pg_param(row[c]) for c in columns] + [status, datetime.now(timezone.utc)]
        with self.pool.connection() as conn:
            conn.execute(
                f"UPDATE guitar_deals SET {', '.join(set_parts)} WHERE id = %s AND user_id = %s",
                [*values, deal_id, self.user_id],
            )
        self.logger.info(f"Updated full data and analysis for deal '{deal_id}'. Status: '{status}'.")

    def update_deal_status(self, deal_id: str, status: str, error_message: str | None = None):
        with self.pool.connection() as conn:
            if status == "sold":
                conn.execute(
                    "UPDATE guitar_deals SET status = %s, sold_at = now() WHERE id = %s AND user_id = %s",
                    (status, deal_id, self.user_id),
                )
            elif error_message:
                # `ai_analysis_raw || jsonb_build_object(...)` fusionne DANS l'objet plutôt que de
                # le remplacer par un tableau (le piège ArrayUnion-sur-un-objet documenté côté
                # Firestore, voir repository.py::mark_deal_as_sold, n'a pas lieu d'être reproduit
                # ici — Postgres permet de faire ça correctement dès le départ).
                conn.execute(
                    """
                    UPDATE guitar_deals
                    SET status = %s,
                        ai_analysis_raw = COALESCE(ai_analysis_raw, '{}'::jsonb)
                            || jsonb_build_object('error', %s::text, 'error_at', now())
                    WHERE id = %s AND user_id = %s
                    """,
                    (status, error_message, deal_id, self.user_id),
                )
            else:
                conn.execute(
                    "UPDATE guitar_deals SET status = %s WHERE id = %s AND user_id = %s",
                    (status, deal_id, self.user_id),
                )
        self.logger.info(f"Updated status for deal '{deal_id}' to '{status}'.")

    def mark_deal_as_sold(self, deal_id: str, reason: str | None = None):
        with self.pool.connection() as conn:
            if reason:
                conn.execute(
                    """
                    UPDATE guitar_deals
                    SET status = 'sold', sold_at = now(), "timestamp" = now(),
                        sold_notes = COALESCE(sold_notes, '[]'::jsonb)
                            || jsonb_build_array(jsonb_build_object('info', %s::text, 'timestamp', now()))
                    WHERE id = %s AND user_id = %s
                    """,
                    (reason, deal_id, self.user_id),
                )
            else:
                conn.execute(
                    """UPDATE guitar_deals SET status = 'sold', sold_at = now(), "timestamp" = now()
                       WHERE id = %s AND user_id = %s""",
                    (deal_id, self.user_id),
                )
        self.logger.info(f"Deal '{deal_id}' marked as SOLD with soldAt timestamp.")

    def mark_all_for_reanalysis(self) -> int:
        with self.pool.connection() as conn:
            cur = conn.execute(
                "UPDATE guitar_deals SET status = 'retry_analysis' WHERE user_id = %s AND status = 'analyzed'",
                (self.user_id,),
            )
            return cur.rowcount

    # ------------------------------------------------------------------ villes

    def get_cities(self):
        """Villes actives pour cet utilisateur (fusion catalogue + préférences) — pas de repli
        "legacy" (contrairement à `repository.py::get_cities`) : cette architecture pré-catalogue
        partagé n'a pas d'équivalent côté Postgres, jamais construite ainsi."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.name, c.latitude, c.longitude, p.kijiji_radius_km
                FROM cities c
                JOIN user_city_prefs p ON p.city_id = c.id AND p.user_id = %s
                WHERE p.active = true
                """,
                (self.user_id,),
            ).fetchall()
        return [
            {
                "id": row["id"], "name": row["name"],
                "latitude": row["latitude"], "longitude": row["longitude"],
                "isScannable": True, "kijijiRadiusKm": row["kijiji_radius_km"],
            }
            for row in rows
        ]

    def get_all_catalog_cities(self) -> dict:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, latitude, longitude, needs_review, created_by FROM cities"
            ).fetchall()
        return {
            row["id"]: {
                "id": row["id"], "name": row["name"],
                "latitude": row["latitude"], "longitude": row["longitude"],
                "needsReview": row["needs_review"], "createdBy": row["created_by"],
            }
            for row in rows
        }

    def add_city_to_catalog(self, city_id: str, city_data: dict):
        """`.set(city_data, merge=True)` côté Firestore : ne touche QUE les champs présents dans
        `city_data`, comme `update_deal_data_and_analysis` ci-dessus pour les mêmes raisons.

        `INSERT ... ON CONFLICT DO UPDATE` ne suffit PAS ici : Postgres valide les contraintes
        NOT NULL (`name`) sur la ligne proposée par l'INSERT AVANT même de détecter un conflit —
        un merge partiel qui omet `name` sur une ville déjà existante lèverait donc une
        `NotNullViolation` alors qu'aucune colonne NOT NULL n'est censée être touchée (bug réel
        trouvé par le test `test_add_city_to_catalog_merge_does_not_clear_untouched_fields`).
        D'où la vérification d'existence explicite plutôt qu'un simple upsert : UPDATE partiel si
        la ville existe déjà, INSERT complet sinon (qui échoue correctement si `name` manque pour
        une VRAIE nouvelle ville — cas réel, pas un bug, une ville a besoin d'un nom)."""
        present = {
            CITY_FIELD_TO_COLUMN[k]: v for k, v in city_data.items()
            if k in CITY_FIELD_TO_COLUMN
        }
        if not present:
            return
        with self.pool.connection() as conn:
            exists = conn.execute("SELECT 1 FROM cities WHERE id = %s", (city_id,)).fetchone()
            if exists:
                set_clause = ", ".join(f"{c} = %s" for c in present)
                conn.execute(
                    f"UPDATE cities SET {set_clause} WHERE id = %s",
                    [*present.values(), city_id],
                )
            else:
                columns = ["id"] + list(present.keys())
                placeholders = ", ".join(["%s"] * len(columns))
                conn.execute(
                    f"INSERT INTO cities ({', '.join(columns)}) VALUES ({placeholders})",
                    [city_id] + list(present.values()),
                )
        self.logger.info(f"Ville '{city_data.get('name')}' (id={city_id}) ajoutée au catalogue partagé.")

    def set_city_user_pref(self, city_id: str, is_scannable: bool):
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO user_city_prefs (user_id, city_id, active) VALUES (%s, %s, %s)
                ON CONFLICT (user_id, city_id) DO UPDATE SET active = EXCLUDED.active
                """,
                (self.user_id, city_id, is_scannable),
            )
        self.logger.info(f"Préférence ville {city_id} pour user {self.user_id[:8]}: isScannable={is_scannable}")

    # ------------------------------------------------------------------ commandes

    def get_pending_commands(self):
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT id, type, payload FROM commands
                   WHERE user_id = %s AND status = 'pending' ORDER BY created_at ASC""",
                (self.user_id,),
            ).fetchall()
        return [_Row(str(row["id"]), {"type": row["type"], "payload": row["payload"]}) for row in rows]

    def mark_command_completed(self, command_id):
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE commands SET status = 'completed', completed_at = now() WHERE id = %s",
                (int(command_id),),
            )
        self.logger.info(f"Command '{command_id}' marked as completed.")

    def mark_command_failed(self, command_id, error_message: str):
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE commands SET status = 'failed', error_message = %s, completed_at = now() WHERE id = %s",
                (error_message, int(command_id)),
            )
        self.logger.info(f"Command '{command_id}' marked as failed: {error_message}")

    # ------------------------------------------------------------------ logs

    def delete_all_logs(self) -> int:
        with self.pool.connection() as conn:
            cur = conn.execute("DELETE FROM logs WHERE user_id = %s", (self.user_id,))
            return cur.rowcount

    # ------------------------------------------------------------------ images (Firebase Storage
    # — pas de changement de backend DB ici, identique à repository.py)

    def upload_images_to_storage(self, image_urls, deal_id):
        if not self._bucket:
            return [], []
        import uuid
        import requests

        stable_urls, gs_uris = [], []
        for i, url in enumerate(image_urls):
            if not url:
                continue
            try:
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    self.logger.warning(f"Image {i + 1}/{len(image_urls)} non téléchargeable (HTTP {response.status_code}) pour deal {deal_id}.")
                    continue
                blob_path = f"deals/{deal_id}/{i}_{uuid.uuid4().hex[:8]}.jpg"
                blob = self._bucket.blob(blob_path)
                blob.upload_from_string(response.content, content_type="image/jpeg")
                blob.make_public()
                stable_urls.append(blob.public_url)
                gs_uris.append(f"gs://{self._bucket.name}/{blob_path}")
                self.logger.info(f"   ☁️ Image {i + 1} uploadée pour deal {deal_id}: {blob_path}")
            except Exception as e:
                self.logger.warning(f"Erreur upload image {i + 1} pour deal {deal_id}: {e}")
        return stable_urls, gs_uris

    def list_deal_image_gs_uris(self, deal_id):
        if not self._bucket:
            return []
        prefix = f"deals/{deal_id}/"
        blobs = sorted(self._bucket.list_blobs(prefix=prefix), key=lambda b: b.name)
        return [f"gs://{self._bucket.name}/{blob.name}" for blob in blobs]

    def delete_deal_images(self, deal_id: str) -> int:
        if not self._bucket:
            self.logger.warning(f"delete_deal_images: Pas de bucket Storage configuré pour deal {deal_id}.")
            return 0
        try:
            prefix = f"deals/{deal_id}/"
            blobs = list(self._bucket.list_blobs(prefix=prefix))
            deleted_count = len(blobs)
            for blob in blobs:
                blob.delete()
            if deleted_count:
                self.logger.info(f"🗑️ {deleted_count} image(s) supprimée(s) du Storage pour deal {deal_id}.")
            with self.pool.connection() as conn:
                conn.execute(
                    "UPDATE guitar_deals SET storage_image_urls = NULL WHERE id = %s AND user_id = %s",
                    (deal_id, self.user_id),
                )
            return deleted_count
        except Exception as e:
            self.logger.error(f"Erreur lors de la suppression des images pour deal {deal_id}: {e}", exc_info=True)
            return 0

    def purge_rejected_images(self, retention_days=30, rejection_verdicts=None) -> int:
        if not self._bucket:
            self.logger.warning("purge_rejected_images: Pas de bucket Storage configuré.")
            return 0
        if rejection_verdicts is None:
            rejection_verdicts = ["BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE", "INCOMPLETE_DATA", "REJECTED"]
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        purged_count = 0
        BATCH_SIZE = 200
        try:
            while True:
                with self.pool.connection() as conn:
                    rows = conn.execute(
                        """
                        SELECT id FROM guitar_deals
                        WHERE user_id = %s AND verdict = ANY(%s) AND "timestamp" <= %s
                              AND storage_image_urls IS NOT NULL
                        LIMIT %s
                        """,
                        (self.user_id, rejection_verdicts, cutoff, BATCH_SIZE),
                    ).fetchall()
                if not rows:
                    break
                for row in rows:
                    deal_id = row["id"]
                    prefix = f"deals/{deal_id}/"
                    blobs = list(self._bucket.list_blobs(prefix=prefix))
                    for blob in blobs:
                        blob.delete()
                    # Toujours nettoyer la colonne, même sans blob trouvé (déjà supprimé, ou
                    # jamais uploadé) — sinon la ligne reste éligible au WHERE storage_image_urls
                    # IS NOT NULL et est re-sélectionnée indéfiniment à chaque passage de purge.
                    with self.pool.connection() as conn:
                        conn.execute(
                            "UPDATE guitar_deals SET storage_image_urls = NULL WHERE id = %s",
                            (deal_id,),
                        )
                    if blobs:
                        purged_count += len(blobs)
                        self.logger.info(f"🗑️ {len(blobs)} image(s) purgée(s) pour deal rejeté {deal_id} (ancien de {retention_days}j+).")
                if len(rows) < BATCH_SIZE:
                    break
        except Exception as e:
            self.logger.error(f"Erreur lors de la purge des images: {e}", exc_info=True)
        self.logger.info(f"Purge lifecycle terminée. {purged_count} image(s) supprimée(s).")
        return purged_count
