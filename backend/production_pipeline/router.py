"""
Phase 6 — Routeur de Post-Processing Déterministe
==================================================
Reçoit un crop redressé (issu de geometry.rotate_and_crop) et sa classe YOLO,
dispatche vers la route OCR ou Vision selon la sémantique de la pièce.

Règle de routage (plan V2.1) :
  - headstock → Route OCR (Surya) : extraction des inscriptions de marque
  - toutes autres classes → Route Vision LLM : analyse colorimétrique bois/accastillage
"""
import cv2
import numpy as np
from .post_processing import apply_route_ocr_surya, apply_route_vision_llm

# Classes dont le contenu texte prime (inscriptions marque/modèle)
OCR_CLASSES = {"headstock"}


def route_crop(crop: np.ndarray, class_name: str) -> np.ndarray:
    """
    Applique le pre-processing adapté avant envoi à l'Oracle final (LLM métier ou Surya OCR).

    Args:
        crop: Image recadrée et redressée (BGR numpy array, issue de geometry.rotate_and_crop).
        class_name: Nom de la classe YOLO de la pièce détectée.

    Returns:
        Image pre-processée prête pour l'Oracle.
    """
    if class_name in OCR_CLASSES:
        return apply_route_ocr_surya(crop)
    else:
        return apply_route_vision_llm(crop)
