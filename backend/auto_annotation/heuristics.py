import cv2
from .config import CLASS_NAMES, NECK_RATIO_MIN, INCLUSION_RATIO_MIN

def rotated_rect_intersection_area(rect1, rect2):
    """Calcule l'aire d'intersection entre deux RotatedRect OpenCV."""
    res, pts = cv2.rotatedRectangleIntersection(rect1, rect2)
    if res == cv2.INTERSECT_NONE or pts is None:
        return 0.0
    return cv2.contourArea(pts)

def check_inclusion_obb(inner_rect, outer_rect):
    """Vérifie si inner_rect est presque totalement inclus dans outer_rect."""
    inter_area = rotated_rect_intersection_area(inner_rect, outer_rect)
    inner_w, inner_h = inner_rect[1]
    inner_area = inner_w * inner_h
    
    if inner_area == 0: 
        return False
    # Seuil configurable dans config.py (INCLUSION_RATIO_MIN)
    return (inter_area / inner_area) > INCLUSION_RATIO_MIN

def check_connectivity_obb(rect1, rect2):
    """Vérifie s'il y a une intersection non nulle entre deux RotatedRect."""
    return rotated_rect_intersection_area(rect1, rect2) > 0

def apply_heuristics(rects, classes):
    """
    Filtre 1: Heuristiques spatiales.
    Élimine les prédictions aberrantes en vérifiant les lois de la lutherie.
    """
    valid_indices = []
    
    # Indexation par type de pièce
    body_boxes = [i for i, c in enumerate(classes) if int(c) < len(CLASS_NAMES) and CLASS_NAMES[int(c)] == 'body']
    headstock_boxes = [i for i, c in enumerate(classes) if int(c) < len(CLASS_NAMES) and CLASS_NAMES[int(c)] == 'headstock']
    heel_boxes = [i for i, c in enumerate(classes) if int(c) < len(CLASS_NAMES) and CLASS_NAMES[int(c)] == 'heel']
    
    for i, (rect, cls) in enumerate(zip(rects, classes)):
        if int(cls) >= len(CLASS_NAMES):
            continue
        c_name = CLASS_NAMES[int(cls)]
        
        if c_name in ['pickups', 'soundhole']:
            # L'élément doit être situé à l'intérieur du corps (body)
            is_valid = any(check_inclusion_obb(rect, rects[bi]) for bi in body_boxes)
            if is_valid: 
                valid_indices.append(i)
                
        elif c_name == 'neck':
            # Ratio de forme : un manche est long et fin, jamais carré
            w, h = rect[1]
            w, h = max(w, 1), max(h, 1) # Éviter la division par zéro
            ratio = max(w/h, h/w)
            
            # Seuil configurable dans config.py (NECK_RATIO_MIN)
            # Un manche est long et fin. Valeur empirique : 2.0 (basses incluses)
            if ratio < NECK_RATIO_MIN:
                continue
            
            # Connectivité : un manche doit toucher AU MOINS UNE des pièces voisines détectées (corps,
            # tête, talon). Une partie hors cadre n'est pas annotée (règle Phase 1) : exiger corps ET
            # tête supprimerait les manches valides des plans serrés. Aucun voisin détecté : on garde
            # le manche (le ratio de forme a déjà été vérifié).
            neighbours = body_boxes + headstock_boxes + heel_boxes
            if not neighbours or any(check_connectivity_obb(rect, rects[ni]) for ni in neighbours):
                valid_indices.append(i)
                
        else:
            # body, headstock, heel, bridge, saddle, nut, plate : aucune heuristique exclusive pour l'instant
            valid_indices.append(i)

    return valid_indices
