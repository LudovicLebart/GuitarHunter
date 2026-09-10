import cv2
from .config import IMAGES_DIR, LABELS_DIR

def save_yolo_obb_format(image_id, image, obb_boxes, classes, final_indices):
    """
    Sauvegarde le dataset distillé au format YOLO-OBB pour l'entraînement de production.
    Le format attendu par Ultralytics YOLO-OBB est généralement :
    class x_center y_center width height rotation
    (Toutes les valeurs étant normalisées, et la rotation en radians).
    """
    if not final_indices:
        return
        
    img_path = IMAGES_DIR / f"{image_id}.jpg"
    lbl_path = LABELS_DIR / f"{image_id}.txt"

    # Sauvegarde de l'image originale (non redressée — l'OBB encode déjà l'angle)
    ok = cv2.imwrite(str(img_path), image)
    if not ok:
        raise IOError(
            f"cv2.imwrite a échoué pour {img_path} — "
            "vérifier les permissions et l'espace disque."
        )
    
    with open(lbl_path, 'w') as f:
        for i in final_indices:
            cls = int(classes[i])
            
            # Récupération des 4 coins normalisés (x1, y1, x2, y2, x3, y3, x4, y4)
            # Flatten permet de passer d'une matrice (4, 2) à un tableau plat (8)
            coords_norm = obb_boxes.xyxyxyxyn[i].cpu().numpy().flatten()
            
            # Format attendu: class x1 y1 x2 y2 x3 y3 x4 y4
            coords_str = " ".join([f"{val:.6f}" for val in coords_norm])
            f.write(f"{cls} {coords_str}\n")
