# =============================================================================
# ATTENTION — FICHIER DÉPLACÉ (plan V2.1)
# =============================================================================
# Ce module (Phase 6 — Post-Processing Déterministe) appartient au pipeline
# de PRODUCTION, pas au pipeline d'annotation (Phases 1-5).
#
# La version canonique est désormais :
#   backend/production_pipeline/post_processing.py
#
# Le routeur (headstock → OCR, autres → Vision) est dans :
#   backend/production_pipeline/router.py
#
# Ce fichier est conservé uniquement pour éviter des ImportError si d'anciens
# scripts y font référence. Ne pas le modifier ici.
# =============================================================================

from backend.production_pipeline.post_processing import (  # noqa: F401
    apply_route_ocr_surya,
    apply_route_vision_llm,
)

