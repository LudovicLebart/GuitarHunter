"""Schémas de la fiche « Corriger l'angle d'un manche vissé » : un par moment clé.

    python docs/fiches/_banque/build_angle_manche_visse.py
Écrit les .svg dans docs/fiches/img/angle-manche-visse/.
Les angles et les épaisseurs sont exagérés pour qu'on les voie : rien n'est à l'échelle.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import C, fleche, repere, svg, texte  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img", "angle-manche-visse")


def ecrire(nom, largeur, hauteur, titre, desc, morceaux):
    os.makedirs(IMG, exist_ok=True)
    with open(os.path.join(IMG, nom), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg(largeur, hauteur, titre, desc, "\n  ".join(morceaux)))
    print("écrit :", nom)


# 01 Le signe : sillet de chevalet au plus bas, corde encore haute ------------------------------------------------------
FB = 200            # dessus de la touche
NUT = 140           # corde au sillet de tête
SADDLE = 186        # corde au sillet de chevalet (déjà au plus bas)
XN, XB, XM = 40, 700, 440
ym = NUT + (SADDLE - NUT) * (XM - XN) / (XB - XN)
XR = 300            # repère de la hauteur de corde
yr = NUT + (SADDLE - NUT) * (XR - XN) / (XB - XN)
ecrire("01-sillet-au-plus-bas.svg", 820, 350, "Le signe d'un angle trop faible",
       "Coupe latérale : le sillet de chevalet est déjà au plus bas, et la corde reste trop haute au-dessus des frettes.", [
    texte(410, 30, "Angle trop faible : même sillet de chevalet à fond, la corde reste haute", 16, C["texte_doux"], True, "middle"),
    f'<rect x="{XN}" y="{FB}" width="{XM + 90 - XN}" height="30" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{XN}" y="{FB - 8}" width="{XM + 90 - XN}" height="8" fill="{C["noir"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{XM + 90}" y="{FB + 16}" width="{820 - XM - 90 - 20}" height="40" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    f'<rect x="{XB - 30}" y="{SADDLE}" width="60" height="{FB + 16 - SADDLE}" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<line x1="{XN}" y1="{NUT}" x2="{XB}" y2="{SADDLE}" stroke="{C["trait"]}" stroke-width="3"/>',
    f'<path d="M{XR} {yr:.0f} V{FB - 8}" stroke="{C["ko"]}" stroke-width="4"/>',
    repere(1, XR + 26, (yr + FB - 8) / 2 + 2), repere(2, XB, SADDLE - 30),
    repere(1, 60, 270), texte(84, 276, "Corde trop haute au-dessus des frettes", 14, C["texte"], True),
    repere(2, 60, 300), texte(84, 306, "Sillet de chevalet déjà au plus bas", 14, C["texte"], True),
    texte(410, 336, "Relief correct, sillet à fond, action encore haute : l'angle du manche est en cause (dessin exagéré).", 13, C["texte_doux"], False, "middle"),
])

# 02 Cale partielle (à éviter) et cale pleine poche ---------------------------------------------------------------------
def panneau(x0, titre, pleine):
    h = 214                 # fond de la poche
    ep = 14                 # épaisseur de la cale au dos
    elems = [
        texte(x0 + 170, 70, titre, 16, C["texte"], True, "middle"),
        f'<rect x="{x0 - 10}" y="{h}" width="360" height="26" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    ]
    if pleine:
        elems.append(f'<polygon points="{x0},{h} {x0 + 340},{h} {x0 + 340},{h - ep}" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>')
        elems.append(f'<polygon points="{x0},{h} {x0 + 340},{h - ep} {x0 + 340},{h - 84} {x0},{h - 84}" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>')
    else:
        elems.append(f'<rect x="{x0}" y="{h - ep}" width="250" height="{ep}" fill="{C["ko"]}" opacity="0.35"/>')
        elems.append(f'<rect x="{x0 + 250}" y="{h - ep}" width="90" height="{ep}" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>')
        elems.append(f'<rect x="{x0}" y="{h - ep - 84}" width="340" height="84" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>')
    elems.append(f'<line x1="{x0 + 295}" y1="{h - 110}" x2="{x0 + 295}" y2="{h + 20}" stroke="{C["metal"]}" stroke-width="5" stroke-dasharray="6 4"/>')
    elems.append(texte(x0 + 8, h - 62, "vers la tête", 13, "#ffffff"))
    elems.append(texte(x0 + 332, h - 62, "vers le chevalet", 13, "#ffffff", False, "end"))
    return elems


ecrire("02-cale-partielle-et-pleine.svg", 820, 330, "Cale partielle ou cale pleine poche",
       "Coupe latérale du talon dans sa poche : une cale courte laisse un vide que la vis comble en tirant le talon ; une cale en coin sur toute la poche garde un contact complet.", [
    *panneau(20, "Cale partielle : à éviter", False),
    *panneau(440, "Cale pleine poche : en coin", True),
    texte(190, 282, "Vide sous le talon : la vis le tire", 13, C["texte"], True, "middle"),
    texte(190, 302, "et la fin de la touche se bosse", 13, C["texte"], True, "middle"),
    texte(610, 282, "Contact complet sur toute la poche :", 13, C["texte"], True, "middle"),
    texte(610, 302, "épais côté chevalet, nul côté tête", 13, C["texte"], True, "middle"),
    texte(410, 28, "Coupe latérale du talon dans sa poche (épaisseurs exagérées)", 16, C["texte_doux"], True, "middle"),
])

# 03 Contour, trous et épaisseurs de la cale ----------------------------------------------------------------------------
ecrire("03-contour-et-trous.svg", 820, 340, "Tracer et percer la cale",
       "Vue de dessus : un morceau d'érable un peu plus grand que la poche, le contour du talon tracé au crayon, quatre trous aux vis, épais côté chevalet.", [
    texte(410, 30, "Vue de dessus de la cale", 16, C["texte_doux"], True, "middle"),
    f'<rect x="120" y="60" width="440" height="190" fill="none" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="7 5"/>',
    f'<rect x="150" y="80" width="380" height="150" rx="14" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="3"/>',
    *[f'<circle cx="{x}" cy="{y}" r="11" fill="{C["fond"] if "fond" in C else "#fff"}" stroke="{C["trait"]}" stroke-width="2"/>' for x in (200, 480) for y in (110, 200)],
    fleche(430, 270, 520, 270),
    texte(150, 274, "Côté tête : presque nul", 14, C["texte"], True),
    texte(530, 274, "Côté chevalet : plus épais", 14, C["texte"], True),
    repere(1, 584, 90), repere(2, 584, 155), repere(3, 584, 220),
    texte(606, 96, "Pièce un peu plus grande", 14, C["texte"], True),
    texte(606, 161, "Contour du talon (crayon)", 14, C["texte"], True),
    texte(606, 226, "Trous : poinçon ou mèche", 14, C["texte"], True),
    texte(410, 316, "Départ vers 1,5 mm (0,060 po) ; au dos, 0,5 à 1 mm une fois en coin. Épaisseurs à ajuster par essais.", 14, C["texte_doux"], False, "middle"),
])
