"""
Prototype Phase 1 (docs/management/plans/NECK_RESET_VISION_PLAN.md §2/§7) : détection du motif
des frettes comme mire de calibration naturelle — LSD (Line Segment Detector, OpenCV) pour
détecter les segments, puis recherche d'une séquence de positions Y dont les écarts suivent la
loi de tempérament égal (ratio ~0.9439 entre frettes consécutives, `2**(-1/12)`).

STATUT RÉEL (2026-08-19, testé à la main sur 2 photos réelles du Dataset A, pas encore validé
à l'échelle) : **prometteur mais pas robuste**, pas un pipeline fini.
- **LSD brut sur la photo entière échoue** : la recherche brute-force de séquence géométrique
  (tolérance de ratio permissive) matche facilement du bruit de fond (texture de mur, rayures de
  plancher, motifs de couverture) sur toute la hauteur de l'image plutôt que les vraies frettes —
  observé concrètement, pas juste une inquiétude théorique.
- **Avec un recadrage manuel sur la silhouette de la guitare + contraintes ajoutées** (longueur de
  segment bornée à ~35% de la largeur du recadrage, centrage horizontal ±25%, envergure totale de
  la séquence bornée à ~35% de la hauteur du recadrage) : sur une photo bien frontale et nette,
  la séquence trouvée (13 positions) se recale correctement sur la zone du manche — encourageant,
  mais teste seulement "la bonne zone", pas un alignement frette-par-frette vérifié précisément.
- **Sur une 2e photo réelle (angle légèrement de travers, guitare classique)** : aucune séquence
  trouvée du tout avec les mêmes paramètres — le recadrage manuel imprécis et le centrage du manche
  non parfaitement vertical suffisent à faire échouer la détection. Pas robuste en l'état à la
  variabilité réelle des photos d'annonces.

**Le recadrage est actuellement manuel** (`--crop x1,y1,x2,y2`) — dans un vrai pipeline, il
faudrait soit une détection automatique du manche (pas juste la boîte englobante de la guitare
entière, qui inclut encore trop de fond), soit une contrainte géométrique plus forte que le simple
centrage horizontal. Piste non résolue.

Dépendances (pas dans requirements.txt — outil d'expérimentation R&D, pas le bot en production) :
  pip install opencv-python-headless numpy

Usage (test manuel, pas un outil batch) :
  python3 backend/scripts/experiments/phase1_fret_detection_prototype.py --crop X1,Y1,X2,Y2 photo.jpg
"""

import sys

import cv2
import numpy as np

RATIO = 2 ** (-1 / 12)  # ~0.9439, ratio d'écart entre frettes consécutives (tempérament égal)


def detect_lines(gray):
    lsd = cv2.createLineSegmentDetector(0)
    lines = lsd.detect(gray)[0]
    if lines is None:
        return []
    lines = np.asarray(lines)
    if lines.ndim == 3:  # certaines versions d'OpenCV renvoient (N, 1, 4)
        lines = lines[:, 0, :]
    return list(lines)  # chaque élément : [x1, y1, x2, y2]


def filter_near_horizontal(lines, angle_tol_deg=20, min_len=25, max_len_frac=0.9, img_w=None):
    out = []
    for x1, y1, x2, y2 in lines:
        length = np.hypot(x2 - x1, y2 - y1)
        if length < min_len:
            continue
        if img_w and length > max_len_frac * img_w:
            continue
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        angle = abs(angle) % 180
        if angle > 90:
            angle = 180 - angle
        if angle <= angle_tol_deg:
            out.append((x1, y1, x2, y2, length))
    return out


def cluster_by_y(segments, y_tol=8):
    """Regroupe les segments quasi-horizontaux en candidats de lignes de frette par Y médian."""
    items = sorted(segments, key=lambda s: (s[1] + s[3]) / 2)
    clusters = []
    for seg in items:
        ymid = (seg[1] + seg[3]) / 2
        if clusters and abs(ymid - clusters[-1]['y']) <= y_tol:
            c = clusters[-1]
            c['segs'].append(seg)
            c['y'] = np.mean([(s[1] + s[3]) / 2 for s in c['segs']])
            c['xmin'] = min(c['xmin'], seg[0], seg[2])
            c['xmax'] = max(c['xmax'], seg[0], seg[2])
        else:
            clusters.append({'y': ymid, 'segs': [seg], 'xmin': min(seg[0], seg[2]), 'xmax': max(seg[0], seg[2])})
    return clusters


def find_fret_sequence(ys, ratio_tol=0.15, min_frets=8, max_span=None):
    """
    Cherche la plus longue séquence de positions Y candidates dont les écarts consécutifs
    suivent le ratio de tempérament égal (progression géométrique décroissante). Brute force
    sur les paires de départ — les listes de candidats restent petites (quelques dizaines).

    `max_span` borne (seq[-1] - seq[0]) pour rejeter les séquences couvrant une fraction
    implausible de l'image — nécessaire empiriquement : une tolérance de ratio permissive
    matche aussi facilement du bruit de fond étalé sur toute la photo que de vraies frettes
    (voir STATUT RÉEL en tête de fichier).
    """
    ys = sorted(ys)
    best = []
    n = len(ys)
    for i in range(n):
        for j in range(i + 1, n):
            seq = [ys[i], ys[j]]
            d_prev = ys[j] - ys[i]
            if d_prev <= 1:
                continue
            k = j + 1
            while k < n:
                d = ys[k] - seq[-1]
                if d <= 0:
                    k += 1
                    continue
                expected = d_prev * RATIO
                if abs(d - expected) <= ratio_tol * expected:
                    seq.append(ys[k])
                    d_prev = d
                    k += 1
                else:
                    if d > expected * (1 + ratio_tol):
                        break
                    k += 1
            if max_span and (seq[-1] - seq[0]) > max_span:
                continue
            if len(seq) > len(best):
                best = seq
    return best if len(best) >= min_frets else []


def process(path, out_path, crop=None):
    img = cv2.imread(path)
    if crop:
        x1, y1, x2, y2 = crop
        img = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    lines = detect_lines(gray)
    # Les frettes ont une longueur bornée par la largeur du manche, pas celle de la photo/du recadrage.
    horiz = filter_near_horizontal(lines, angle_tol_deg=20, min_len=w * 0.06, max_len_frac=0.35, img_w=w)
    # Le manche est à peu près centré horizontalement sur un recadrage frontal — écarte les
    # segments dont le centre s'éloigne trop du milieu du recadrage (élimine l'essentiel du bruit
    # de fond, mais fragile si le manche n'est pas bien centré/vertical, cf. STATUT RÉEL).
    cx = w / 2
    horiz = [s for s in horiz if abs((s[0] + s[2]) / 2 - cx) < w * 0.25]
    clusters = cluster_by_y(horiz, y_tol=max(4, h * 0.006))

    candidate_ys = [c['y'] for c in clusters if len(c['segs']) >= 1]
    seq = find_fret_sequence(candidate_ys, max_span=h * 0.35)

    vis = img.copy()
    for x1, y1, x2, y2 in lines:
        cv2.line(vis, (int(x1), int(y1)), (int(x2), int(y2)), (180, 180, 180), 1)
    for c in clusters:
        cv2.line(vis, (int(c['xmin']), int(c['y'])), (int(c['xmax']), int(c['y'])), (255, 150, 0), 1)
    for y in seq:
        cv2.line(vis, (0, int(y)), (w, int(y)), (0, 0, 255), 2)

    cv2.imwrite(out_path, vis)
    print(f"{path}: {len(lines)} segments LSD, {len(horiz)} quasi-horizontaux, "
          f"{len(clusters)} clusters candidats, séquence retenue = {len(seq)} frettes -> {out_path}")
    return seq


if __name__ == "__main__":
    args = sys.argv[1:]
    crop = None
    if args and args[0] == "--crop":
        crop = tuple(int(v) for v in args[1].split(','))
        args = args[2:]
    for path in args:
        out = path.rsplit('.', 1)[0] + '_annotated.jpg'
        process(path, out, crop=crop)
