import cv2
import numpy as np

def parse_obb(obb_boxes, index):
    """
    Extrait un RotatedRect OpenCV depuis un objet OBB d'Ultralytics.
    
    Args:
        obb_boxes: L'objet boîte Ultralytics contenant les boîtes OBB.
        index: L'indice de la boîte à extraire.
    Returns:
        tuple: ((center_x, center_y), (width, height), angle_in_degrees)
    """
    coords = obb_boxes.xywhr[index].cpu().numpy()
    x_c, y_c, w, h, angle_rad = coords
    angle_deg = np.degrees(angle_rad)
    return ((x_c, y_c), (w, h), angle_deg)

def rotate_and_crop(image, rect):
    """
    Redresse l'image selon l'angle de la boîte orientée (OBB), 
    puis effectue un recadrage orthogonal parfait pour le VLM.
    Empêche les bords d'être coupés (clipping) en agrandissant le canevas de rotation.
    """
    center, size, angle = rect
    center = tuple(map(int, center))
    size = tuple(map(int, size))
    w, h = size
    
    # 1. Matrice de rotation initiale
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    
    # 2. Calcul des nouvelles dimensions (Bounding Box de l'image entière tournée)
    h_orig, w_orig = image.shape[:2]
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    nW = int((h_orig * sin) + (w_orig * cos))
    nH = int((h_orig * cos) + (w_orig * sin))
    
    # 3. Ajustement de la matrice pour appliquer la translation (éviter le clipping)
    M[0, 2] += (nW / 2) - center[0]
    M[1, 2] += (nH / 2) - center[1]
    
    # 4. Redressement de l'image sur le nouveau canevas agrandi
    img_rot = cv2.warpAffine(image, M, (nW, nH), flags=cv2.INTER_CUBIC)
    
    # 5. Calcul des nouvelles coordonnées du centre sur l'image tournée
    new_center_x = int(nW / 2)
    new_center_y = int(nH / 2)
    
    # 6. Recadrage orthogonal
    start_x = max(0, new_center_x - w // 2)
    end_x = min(nW, new_center_x + w // 2)
    start_y = max(0, new_center_y - h // 2)
    end_y = min(nH, new_center_y + h // 2)
    
    crop = img_rot[start_y:end_y, start_x:end_x]
    return crop
