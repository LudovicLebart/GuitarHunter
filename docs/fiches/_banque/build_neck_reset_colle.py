"""Schémas de la fiche « Refaire l'angle d'un manche collé » : un par moment clé.

    python docs/fiches/_banque/build_neck_reset_colle.py
Écrit les .svg dans docs/fiches/img/neck-reset-manche-colle/.
Toute la géométrie (manche, talon, table, chevalet…) vient de `coupe.py`, partagée avec les autres fiches de la série.
Coupes latérales, manche à gauche, corps à droite ; angles et épaisseurs exagérés, rien n'est à l'échelle.
"""
import math
import os
import sys
from functools import partial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coupe import FOND, FRETTE_15, OUIE, SELLE, TABLE, TALON_H, TASSEAU, TOUCHE, Coupe  # noqa: E402
from kit import C, cote, ecrire, etiquette, fleche, rappel, texte  # noqa: E402

SLUG = "neck-reset-manche-colle"
sortie = partial(ecrire, SLUG)
A_PX = 20                                             # l'écart A du dessin, en pixels
ANGLE_APRES = math.degrees(math.atan(A_PX / SELLE))   # l'angle qui ferait toucher la règle au haut du chevalet (≈ 3,7°)
ANGLE_DESSIN = 8                                      # angle du schéma 03, forcé pour que le coin se voie


def point(x, y, couleur, r=7):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{couleur}" stroke="#fff" stroke-width="2"/>'


def pied(lignes, y0):
    """Légende du bas : une ligne par entrée."""
    return [texte(40, y0 + 22 * i, ligne, 14) for i, ligne in enumerate(lignes)]


# 01 Les trois mesures ------------------------------------------------------------------------------------------------------
c = Coupe(yt=170, angle=0)
JX, YT = c.jx, c.yt
sx, sy = c.selle                                      # haut du chevalet, à l'aplomb du milieu du sillet
yr = YT - TOUCHE - 6                                  # la règle posée sur les frettes
m = [
    texte(410, 30, "À mesurer avant de déposer le manche : A, B et C", 16, C["texte_doux"], True, "middle"),
    c.corps(vide=False), c.chevalet(), c.manche(),
    # la règle réelle, puis son prolongement ; la règle d'un manche bien réglé touche le haut du chevalet
    f'<line x1="44" y1="{yr}" x2="{sx - 32}" y2="{yr}" stroke="{C["ok"]}" stroke-width="5"/>',
    f'<line x1="{sx - 32}" y1="{yr}" x2="{sx + 56}" y2="{yr}" stroke="{C["ok"]}" stroke-width="1.5" stroke-dasharray="4 3"/>',
    f'<line x1="{JX}" y1="{yr}" x2="{sx}" y2="{sy}" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="7 5"/>',
    texte(52, yr - 12, "Règle posée sur les frettes", 14, C["ok"], True, halo=True),
    texte(JX + 36, yr - 36, "règle d'un manche bien réglé : elle touche le haut du chevalet", 13, C["texte_doux"], False, halo=True),
    # A : haut du chevalet / règle, à droite du chevalet
    rappel(sx + 3, sy, sx + 62, sy), cote(sx + 56, sy, sx + 56, yr, C["ko"]),
    texte(sx + 70, (sy + yr) / 2 + 7, "A", 20, C["ko"], True),
    # C : du joint au milieu du sillet
    rappel(JX, YT - 14, JX, YT - 96), rappel(sx, sy - 10, sx, YT - 96), cote(JX, YT - 90, sx, YT - 90, C["texte"]),
    texte((JX + sx) / 2, YT - 100, "C", 20, C["texte"], True, "middle"),
    # B : la face du talon, tracée en blanc dans le talon
    cote(JX - 16, YT + 3, JX - 16, YT + TALON_H - 3, "#fff"),
    texte(JX - 40, YT + TALON_H / 2 + 7, "B", 20, "#fff", True, "middle"),
    texte(sx + 56, YT + 70, "X = A × B ÷ C", 17, C["texte"], True, "middle"),
    texte(sx + 56, YT + 90, "(coin à retirer", 13, C["texte_doux"], False, "middle"),
    texte(sx + 56, YT + 106, "en bas du talon)", 13, C["texte_doux"], False, "middle"),
]
m += pied([
    "A : écart, au chevalet, entre la règle posée sur les frettes et le haut du chevalet",
    "B : hauteur du talon, du dessous de la touche au bas du talon  ·  C : du joint au milieu du sillet",
    "Les trois mesures se prennent avant la dépose ; la formule donne X, à retirer en bas du talon.",
], YT + FOND + 40)
sortie("01-trois-mesures.svg", 820, 420, "Les trois mesures avant de déposer le manche",
       "Coupe latérale : une règle posée sur les frettes arrive sous le haut du chevalet (écart A) ; B est la hauteur du talon, "
       "C la distance du joint au milieu du sillet de chevalet.", m)

# 02 La dépose à la vapeur --------------------------------------------------------------------------------------------------
c = Coupe(yt=170, angle=0)
JX, YT = c.jx, c.yt
hx = JX + FRETTE_15                                   # le trou, dans la fente de la 15e frette (retirée)
m = [
    texte(410, 30, "Très peu de vapeur, puis on ébranle le manche avant de le sortir", 16, C["texte_doux"], True, "middle"),
    c.corps(), c.manche(sans_15=True),
    f'<rect x="{hx - 2.5}" y="{YT - TOUCHE}" width="5" height="{TOUCHE}" fill="{C["fond"]}"/>',
    # chiffon autour de l'aiguille, chiffons secs dans la caisse contre le tasseau
    f'<rect x="{hx - 21}" y="{YT - 20}" width="42" height="11" rx="5" fill="#fff" stroke="{C["trait"]}" stroke-width="1.5"/>',
    f'<rect x="{JX + TASSEAU + 6}" y="{YT + FOND - 62}" width="130" height="62" rx="18" fill="#fff" stroke="{C["trait"]}" '
    f'stroke-width="2" stroke-dasharray="6 4"/>',
    # l'aiguille (dans l'axe du trou), son tuyau et le générateur
    f'<line x1="{hx}" y1="{YT - 4}" x2="{hx}" y2="{YT - 56}" stroke="{C["metal"]}" stroke-width="5" stroke-linecap="round"/>',
    f'<line x1="{hx}" y1="{YT - 4}" x2="{hx}" y2="{YT - 56}" stroke="{C["trait"]}" stroke-width="1.5"/>',
    f'<path d="M{hx} {YT - 56} C{hx} {YT - 86} {hx + 20} {YT - 86} {hx + 52} {YT - 86}" fill="none" stroke="{C["trait"]}" stroke-width="3"/>',
    f'<rect x="{hx + 52}" y="{YT - 103}" width="60" height="34" rx="7" fill="{C["alerte"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    texte(hx + 82, YT - 81, "vapeur", 13, "#fff", True, "middle"),
    # traction vers le haut sur le manche près du talon, ébranlement de côté
    fleche(JX - 34, YT - 22, JX - 34, YT - 92, C["ok"], 5),
    f'<circle cx="104" cy="{YT - 80}" r="11" fill="#fff" stroke="{C["texte"]}" stroke-width="2.5"/><circle cx="104" cy="{YT - 80}" r="3.5" fill="{C["texte"]}"/>',
    f'<circle cx="150" cy="{YT - 80}" r="11" fill="#fff" stroke="{C["texte"]}" stroke-width="2.5"/>'
    f'<path d="M144 {YT - 86} l12 12 M156 {YT - 86} l-12 12" stroke="{C["texte"]}" stroke-width="2.5"/>',
    texte(40, YT - 46, "Ébranler d'un côté à l'autre", 14, C["texte"], True, halo=True),
    texte(40, YT - 29, "(⊙ vers soi, ⊗ loin de soi)", 13, C["texte_doux"], False, halo=True),
    etiquette(1, hx - 52, YT - 66, hx - 3, YT - 12),
    etiquette(2, JX + 110, YT + 30, JX + 46, YT + 26),
    etiquette(3, JX + 150, YT + FOND - 90, JX + 110, YT + FOND - 40),
    etiquette(4, JX - 78, YT - 92, JX - 34, YT - 66, C["ok"]),
]
m += pied([
    "1  Trou de 2,5 mm dans la fente de la frette 15 (frette retirée), aiguille de vapeur, chiffon autour",
    "2  Vide au fond de la queue d'aronde, que le trou rejoint",
    "3  Chiffons secs dans la caisse, autour de la zone du manche",
    "4  Tirer le manche vers le haut, en l'ébranlant ; ne jamais forcer : un talon qui casse est pire qu'une vapeur de plus",
], YT + FOND + 36)
sortie("02-depose-vapeur.svg", 820, 440, "Déposer le manche à la vapeur",
       "Coupe latérale : un trou dans la fente de la frette 15 rejoint le vide au fond de la queue d'aronde ; une aiguille y "
       "envoie un peu de vapeur pendant qu'on ébranle le manche en le tirant vers le haut.", m)

# 03 Retailler le talon -----------------------------------------------------------------------------------------------------
LONG3, CORPS3, YT3 = 170, 150, 130
a = Coupe(jx=240, yt=YT3, angle=0, longueur=LONG3, corps=CORPS3)
b = Coupe(jx=600, yt=YT3, angle=ANGLE_DESSIN, longueur=LONG3, corps=CORPS3)
xw = a.jx - TALON_H * math.tan(math.radians(ANGLE_DESSIN))     # fond du coin retiré
tete0, tete1 = b.pt(-LONG3, 0, 0), b.pt(-LONG3, 0)
m = [
    texte(410, 28, "Retailler le talon : un coin retiré en bas, nul au point P", 16, C["texte_doux"], True, "middle"),
    texte(a.jx - 80, 64, "Avant", 16, C["texte"], True, "middle"), texte(b.jx - 80, 64, "Après", 16, C["texte"], True, "middle"),
    a.corps(vide=False), a.manche(), a.coin_talon(0, ANGLE_DESSIN),
    point(a.jx, YT3, C["ok"]), texte(a.jx - 34, YT3 - 14, "P", 20, C["ok"], True, halo=True),
    rappel(a.jx, YT3 + TALON_H, a.jx, YT3 + TALON_H + 34), rappel(xw, YT3 + TALON_H, xw, YT3 + TALON_H + 34),
    cote(xw, YT3 + TALON_H + 28, a.jx, YT3 + TALON_H + 28, C["ko"], dehors=True),
    texte(a.jx - 32, YT3 + TALON_H + 52, "X", 20, C["ko"], True, "middle"),
    etiquette(1, a.jx - 120, YT3 + 118, a.jx - 6, YT3 + 92, C["ko"]),
    b.corps(vide=False), b.manche(angle=0, fantome=True), b.manche(),
    point(b.jx, YT3, C["ok"]), texte(b.jx - 34, YT3 - 14, "P", 20, C["ok"], True, halo=True),
    fleche(tete0[0] + 6, tete0[1] - 20, tete1[0] + 6, tete1[1] - 20 + 2, C["ok"], 3),
    texte(b.jx - LONG3 - 8, YT3 - 36, "la tête descend", 13, C["ok"], True, halo=True),
]
m += pied([
    "1  Le coin se retire sur la face du talon qui touche le corps : épaisseur X en bas, nulle en P",
    "P ne bouge pas : le manche pivote autour de lui, la tête descend, la règle monte vers le haut du chevalet.",
    "Retirer d'abord les deux tiers de X, le reste à l'essai. Angle et épaisseurs exagérés.",
], YT3 + FOND + 66)
sortie("03-retailler-le-talon.svg", 820, 410, "Retailler le talon : un coin retiré en bas, nul au point P",
       "Deux coupes latérales. Avant : le coin à retirer sur la face du talon, d'épaisseur X en bas et nulle au point P. Après : le "
       "manche a pivoté autour de P, la tête est descendue (position d'origine en pointillés).", m)

# 04 Collage et serrage -----------------------------------------------------------------------------------------------------
c = Coupe(yt=150, angle=ANGLE_APRES)
JX, YT = c.jx, c.yt
BRAS = JX + 105                                                # axe de la vis du serre-joint 2
dessous = [c.pt(u, 0) for u in (0, 112)]                       # dessous de la rallonge, jusqu'au bord de la rosace
metal = f'fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"'
m = [
    texte(410, 28, "Deux serre-joints : un sur la queue d'aronde, un par la rosace pour la rallonge", 16, C["texte_doux"], True, "middle"),
    c.corps(legende_ouie=False), c.manche(),
    # colle de peau : faces de la queue d'aronde et dessous de la rallonge
    c.poly(c.tenon(), "none", C["colle"], 4),
    f'<line x1="{dessous[0][0]:.1f}" y1="{dessous[0][1] - 2:.1f}" x2="{dessous[1][0]:.1f}" y2="{dessous[1][1] - 2:.1f}" stroke="{C["colle"]}" stroke-width="4"/>',
    # serre-joint 1 : cale fendue sur la touche, cale garnie de liège sous le fond ; son corps passe devant la coupe
    c.cale_sur_touche(-26, 62),
    f'<rect x="{JX + 2}" y="{YT + FOND + 10}" width="60" height="12" fill="{C["ruban"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>',
    f'<line x1="{JX + 20}" y1="{YT - 80}" x2="{JX + 20}" y2="{YT + FOND + 60}" stroke="{C["trait"]}" stroke-width="10" opacity=".28"/>',
    fleche(JX + 20, YT - 82, JX + 20, YT - 38, C["ko"], 5), fleche(JX + 20, YT + FOND + 60, JX + 20, YT + FOND + 26, C["ko"], 5),
    # serre-joint 2 : par la rosace, cale fendue sur la rallonge, cale sur la barre d'épaule
    f'<rect x="{BRAS - 18}" y="{YT + TABLE}" width="36" height="16" fill="#e8cf9b" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    c.cale_sur_touche(86, 124),
    f'<rect x="{JX + 205}" y="{YT - 54}" width="10" height="136" {metal}/>',
    f'<rect x="{BRAS - 6}" y="{YT - 54}" width="{JX + 215 - BRAS + 6}" height="9" {metal}/>',
    f'<rect x="{BRAS - 6}" y="{YT + 73}" width="{JX + 215 - BRAS + 6}" height="9" {metal}/>',
    f'<rect x="{BRAS - 4}" y="{YT - 45}" width="8" height="12" {metal}/>',
    f'<rect x="{BRAS - 4}" y="{YT + 42}" width="8" height="31" {metal}/>',
    f'<rect x="{BRAS - 20}" y="{YT + TABLE + 16}" width="40" height="14" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    # le jeu sous la rallonge, à blanc
    cote(dessous[1][0] + 8, dessous[1][1], dessous[1][0] + 8, YT, C["ko"], dehors=True),
    etiquette(1, JX + 70, YT - 100, JX + 20, YT - 66),
    etiquette(2, JX + 262, YT - 66, JX + 215, YT - 50),
    etiquette(3, JX - 84, YT + 70, JX + 8, YT + 40, C["ruban_trait"]),
    etiquette(4, JX + 200, YT + 10, dessous[1][0] + 10, (dessous[1][1] + YT) / 2, C["ko"]),
]
m += pied([
    "1  Serre-joint sur la queue d'aronde : cale fendue sur la touche, cale garnie de liège sous le fond",
    "2  Serre-joint par la rosace pour la rallonge : cale fendue dessus, cale qui épouse la barre d'épaule",
    "3  Colle de peau sur les faces de la queue d'aronde et sous la rallonge de touche (en jaune)",
    "4  Jeu sous la rallonge, mesuré à blanc : environ 0,5 mm (très exagéré ici)",
    "Le serre-joint 1 est dessiné vu de face : son corps passe devant la coupe. Une nuit de serrage.",
], YT + FOND + 88)
sortie("04-collage-et-serrage.svg", 820, 490, "Coller et serrer le manche et la rallonge de touche",
       "Coupe latérale : un serre-joint sur la queue d'aronde (cale fendue sur la touche, cale garnie de liège sous le fond), un "
       "second par la rosace pour la rallonge avec une cale sur la barre d'épaule ; colle sur les faces de la queue d'aronde et sous "
       "la rallonge ; jeu à blanc sous la rallonge.", m)
