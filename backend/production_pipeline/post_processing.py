import cv2

def apply_route_ocr_surya(image):
    """
    Phase 6 - Route OCR (Surya)
    Conversion en niveaux de gris + CLAHE extrême + Masque flou.
    Optimisation stricte pour la géométrie des caractères.
    """
    # 1. Niveaux de gris
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # 2. CLAHE (Contrast Limited Adaptive Histogram Equalization) Extrême
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    
    # 3. Masque flou (Unsharp Masking)
    blur = cv2.GaussianBlur(enhanced, (5, 5), 0)
    unsharp = cv2.addWeighted(enhanced, 1.5, blur, -0.5, 0)
    
    return unsharp

def apply_route_vision_llm(image):
    """
    Phase 6 - Route Vision (Oracle LLM métier)
    Filtre bilatéral + CLAHE sur la couche de luminance (LAB).
    Révèle les détails d'accastillage sans falsifier les teintes d'origine.
    """
    # 1. Filtre bilatéral (réduction du bruit numérique, préservation des arêtes)
    filtered = cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)
    
    # 2. Conversion en LAB Color Space
    lab = cv2.cvtColor(filtered, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    
    # 3. CLAHE uniquement sur le canal de Luminance (L)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl_channel = clahe.apply(l_channel)
    
    # 4. Fusion des canaux et retour en BGR
    merged_lab = cv2.merge((cl_channel, a_channel, b_channel))
    final = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)
    
    return final
