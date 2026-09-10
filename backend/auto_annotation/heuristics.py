import cv2
from .config import CLASS_NAMES

def rotated_rect_intersection_area(rect1, rect2):
    """Calcule l'aire d'intersection entre deux RotatedRect OpenCV."""
    res, pts = cv2.rotatedRectangleIntersection(rect1, rect2)
    if res == cv2.INTER_NONE or pts is None:
        return 0.0
    return cv2.contourArea(pts)

def check_inclusion_obb(inner_rect, outer_rect):
    """Vérifie si inner_rect est presque totalement inclus dans outer_rect."""
    inter_area = rotated_rect_intersection_area(inner_rect, outer_rect)
    inner_w, inner_h = inner_rect[1]
    inner_area = inner_w * inner_h
    
    if inner_area == 0: 
        return False
    # Un seuil de 80% d'inclusion est requis pour tolérer de légers débordements de boîte
    return (inter_area / inner_area) > 0.8 

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
            
            if ratio < 2.0: 
                continue
            
            # Connectivité : doit toucher le corps et la tête (si détectée)
            touches_body = any(check_connectivity_obb(rect, rects[bi]) for bi in body_boxes)
            touches_headstock = any(check_connectivity_obb(rect, rects[hi]) for hi in headstock_boxes) if headstock_boxes else True
            
            if touches_body and touches_headstock:
                valid_indices.append(i)
                
        elif c_name in ['body', 'headstock', 'bridge']:
            # Aucune heuristique exclusive pour l'instant
            valid_indices.append(i)

    return valid_indices
