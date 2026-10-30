"""Schémas de la fiche « Caler la rallonge de touche » : un par étape clé.

    python docs/fiches/_banque/build_cale_rallonge.py
Écrit les .svg dans docs/fiches/img/caler-la-rallonge-de-touche/.
Coupe latérale : le manche est à gauche, la table à droite. Le manche est tourné autour du joint (écart exagéré).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import C, bon_mauvais, boite, fleche, repere, svg, texte  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img", "caler-la-rallonge-de-touche")
YT = 170            # dessus de la table
LONG = 220          # longueur de la rallonge
ANGLE = 8.8         # degrés, exagéré
SA, CA = math.sin(math.radians(ANGLE)), math.cos(math.radians(ANGLE))


def ecrire(nom, contenu):
    os.makedirs(IMG, exist_ok=True)
    with open(os.path.join(IMG, nom), "w", encoding="utf-8", newline="\n") as f:
        f.write(contenu)
    print("écrit :", nom)


def coupe(x0, cale=0.0):
    """Manche + table. `cale` : 0 = pas de cale ; 1 = cale pleine ; entre les deux = cale trop mince (jour).
    Renvoie (svg, joint, bout_x, bout_y) : bout = dessous de la rallonge à son extrémité."""
    joint = x0 + 110
    bx, by = joint + LONG * CA, YT - LONG * SA
    p = [
        f'<g transform="rotate(-{ANGLE} {joint} {YT})">'
        f'<rect x="{x0}" y="{YT}" width="{joint - x0}" height="70" fill="{C["manche"]}"/>'
        f'<rect x="{x0}" y="{YT - 9}" width="{joint - x0 + LONG}" height="9" fill="{C["noir"]}" stroke="{C["trait"]}" stroke-width="2"/>'
        '</g>',
        f'<rect x="{joint}" y="{YT}" width="{LONG + 70}" height="14" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    ]
    if cale:
        haut = YT - (YT - by) * cale
        p.append(f'<polygon points="{joint},{YT} {bx:.1f},{YT} {bx:.1f},{haut:.1f}" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>')
        if cale < 1:
            p.append(f'<polygon points="{joint},{YT} {bx:.1f},{haut:.1f} {bx:.1f},{by:.1f}" fill="none" stroke="{C["alerte"]}" stroke-width="2" stroke-dasharray="5 4"/>')
    return "".join(p), joint, bx, by


def ecrire_svg(nom, largeur, hauteur, titre, desc, morceaux):
    ecrire(nom, svg(largeur, hauteur, titre, desc, "\n  ".join(morceaux)))


# 01 Vue d'ensemble : vide, puis cale ---------------------------------------------------------------------------------
g1, j1, bx1, by1 = coupe(20)
g2, j2, bx2, by2 = coupe(440, 1)
ecrire_svg("01-vide-sous-la-rallonge.svg", 820, 350, "Vide sous la rallonge de touche après un neck reset",
           "Coupe latérale : à gauche la rallonge décolle de la table après le reset ; à droite une cale en coin du même bois que la touche comble le vide.", [
    g1, g2,
    texte(210, 42, "Après le reset : la rallonge décolle", 16, C["texte"], True, "middle"),
    texte(630, 42, "Une cale en coin comble le vide", 16, C["ok"], True, "middle"),
    repere(1, j1 + 120, 100), repere(2, bx1 + 30, YT - 14), repere(3, bx2 + 30, YT - 14),
    texte(40, 285, "1  Rallonge de touche", 14, C["texte"], True),
    texte(40, 305, "2  Vide qui grandit vers le bout", 14, C["texte"], True),
    texte(440, 285, "3  Cale : même bois que la touche, amincie vers le joint", 14, C["texte"], True),
    texte(410, 338, "Écart exagéré sur le dessin. Au-delà de la tolérance, on cale plutôt que de forcer la rallonge à plat.", 14, C["texte_doux"], False, "middle"),
])

# 02 Ordre des opérations ---------------------------------------------------------------------------------------------
etapes = [("1  Mesurer", "écart au bout"), ("2  Tailler", "coin, même bois\nque la touche"), ("3  Préparer", "surfaces\npropres"),
          ("4  Ajuster", "à blanc,\nsans jour"), ("5  Coller", "cale, puis\nrallonge"), ("6  Affleurer", "côtés de la\ncale")]
morceaux = [texte(410, 42, "Dans cet ordre, avec la rallonge serrée à blanc avant toute colle", 17, C["texte_doux"], True, "middle")]
for i, (t, s) in enumerate(etapes):
    x = 10 + i * 135
    morceaux.append(boite(x, 80, 120, 90, t, s))
    if i < 5:
        morceaux.append(fleche(x + 122, 125, x + 133, 125))
morceaux.append(texte(410, 210, "Ne pas couper la cale à sa taille avant d'avoir vérifié qu'elle s'ajuste.", 14, C["texte_doux"], False, "middle"))
ecrire_svg("02-ordre-des-operations.svg", 820, 235, "Ordre des opérations pour caler une rallonge de touche",
           "Six étapes : mesurer l'écart, tailler le coin, préparer les surfaces, ajuster à blanc, coller, affleurer.", morceaux)

# 03 Étape 1 : mesurer l'écart ----------------------------------------------------------------------------------------
g, j, bx, by = coupe(230)
ecrire_svg("03-mesurer-l-ecart.svg", 820, 335, "Mesurer l'écart sous le bout de la rallonge",
           "Coupe latérale : l'écart se mesure entre le dessous du bout de la rallonge et la table, manche serré à blanc.", [
    g,
    f'<path d="M{bx:.1f} {by:.1f} V{YT}" stroke="{C["alerte"]}" stroke-width="3"/>',
    f'<path d="M{bx - 9:.1f} {by:.1f} h18 M{bx - 9:.1f} {YT} h18" stroke="{C["alerte"]}" stroke-width="3"/>',
    repere(1, bx + 70, (by + YT) / 2), texte(bx + 95, (by + YT) / 2 + 6, "Écart au bout", 14, C["texte"], True),
    texte(410, 30, "Manche serré à blanc, comme il le sera au collage", 16, C["texte_doux"], True, "middle"),
    texte(410, 290, "Mesurer côté graves et côté aigus (cales d'épaisseur ou petits coins).", 14, C["texte_doux"], False, "middle"),
    texte(410, 312, "Si l'écart diffère d'un côté à l'autre : revoir l'alignement du manche avant de caler.", 14, C["texte_doux"], False, "middle"),
])

# 04 Étape 2 : tailler le coin ----------------------------------------------------------------------------------------
ecrire_svg("04-tailler-le-coin.svg", 820, 270, "Tailler le coin dans le bois de la touche",
           "À gauche le coin vu de profil : épaisseur égale à l'écart mesuré au gros bout, presque nulle au joint. À droite le coin vu de dessus, un peu plus grand que la rallonge.", [
    texte(200, 42, "Vu de profil", 16, C["texte"], True, "middle"),
    f'<polygon points="60,160 340,160 340,100" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="3"/>',
    texte(60, 185, "≈ 0 côté joint", 14, C["texte"], True),
    texte(340, 185, "épaisseur = écart mesuré", 14, C["texte"], True, "end"),
    f'<path d="M358 100 V160 M350 100 h16 M350 160 h16" stroke="{C["alerte"]}" stroke-width="3"/>',
    texte(620, 42, "Vu de dessus", 16, C["texte"], True, "middle"),
    f'<rect x="480" y="90" width="280" height="76" rx="3" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="3"/>',
    texte(620, 134, "un peu plus grand que la rallonge", 14, C["texte"], True, "middle"),
    texte(410, 232, "Même bois que la touche. On le coupe à sa taille seulement une fois ajusté.", 14, C["texte_doux"], False, "middle"),
])

# 05 Étape 3 : préparer les surfaces ----------------------------------------------------------------------------------
g, j, bx, by = coupe(110)
ecrire_svg("05-preparer-les-surfaces.svg", 820, 290, "Préparer les surfaces avant collage",
           "Coupe latérale : l'ancienne colle est retirée sous la rallonge et sur la table, sans toucher à la finition de la table autour.", [
    g,
    repere(1, j + 130, 108), repere(2, j + 120, 232),
    f'<path d="M{j + 130:.0f} 124 L{j + 150:.0f} {YT - 38:.0f}" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="5 4" fill="none"/>',
    f'<path d="M{j + 120:.0f} 216 L{j + 120:.0f} {YT + 18:.0f}" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="5 4" fill="none"/>',
    texte(j + 156, 112, "Dessous de la rallonge : retirer l'ancienne colle", 14, C["texte"], True),
    texte(j + 146, 238, "Table : même chose, vernis intact autour", 14, C["texte"], True),
    texte(410, 30, "Surfaces propres et saines avant d'essayer la cale", 16, C["texte_doux"], True, "middle"),
])

# 06 Étape 4 : ajuster à blanc ----------------------------------------------------------------------------------------
g1, j1, bx1, by1 = coupe(20, 1)
g2, j2, bx2, by2 = coupe(440, 0.55)
ecrire_svg("06-ajuster-a-blanc.svg", 820, 340, "Ajuster la cale à blanc",
           "Deux coupes : à gauche la cale épouse le dessous de la rallonge sans jour ; à droite la cale est trop mince et laisse un jour.", [
    g1, g2,
    texte(190, 42, "Cale ajustée : aucun jour", 16, C["ok"], True, "middle"),
    texte(610, 42, "Cale trop mince : jour sous la rallonge", 16, C["ko"], True, "middle"),
    bon_mauvais(bx1 + 40, 70, True), bon_mauvais(bx2 + 40, 70, False),
    texte(410, 285, "Serrer à blanc, sans colle : la rallonge repose sur la cale sur toute sa longueur,", 14, C["texte_doux"], False, "middle"),
    texte(410, 308, "sans être relevée ni forcée. Si la table est bombée, courber un peu le dessous de la cale.", 14, C["texte_doux"], False, "middle"),
])

# 07 Étape 5 : coller et serrer ---------------------------------------------------------------------------------------
g, j, bx, by = coupe(120, 1)
cx = bx - 30
ecrire_svg("07-coller-et-serrer.svg", 820, 330, "Coller la cale et serrer par la rosace",
           "Coupe latérale : un serre-joint en C appuie sur le bout de la rallonge et, par la rosace, sur une cale de serrage sous la table.", [
    g,
    f'<rect x="{cx - 50:.0f}" y="{YT + 14}" width="100" height="16" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<path d="M{cx:.0f} {by - 76:.0f} H{bx + 70:.0f} V{YT + 78} H{cx:.0f}" stroke="{C["trait"]}" stroke-width="7" fill="none" stroke-linejoin="round"/>',
    fleche(cx, by - 76, cx, by - 16, C["alerte"]), fleche(cx, YT + 78, cx, YT + 34, C["alerte"]),
    repere(1, j + 85, 118), repere(2, bx + 120, YT + 150), repere(3, bx + 120, by - 100),
    f'<path d="M{j + 85:.0f} 134 L{j + 110:.0f} {YT - 12:.0f}" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="5 4" fill="none"/>',
    texte(j - 60, 100, "Colle de peau : cale, puis rallonge", 14, C["texte"], True),
    texte(bx + 145, YT + 150, "Cale de serrage sous la table", 14, C["texte"], True, "start"),
    texte(bx + 145, YT + 170, "(passée par la rosace)", 14, C["texte"], True, "start"),
    texte(bx + 145, by - 94, "Serre-joint en C", 14, C["texte"], True),
    texte(410, 30, "La colle de peau chaude fige vite : tout est préparé et répété à blanc avant d'encoller", 15, C["texte_doux"], True, "middle"),
])

# 08 Étape 6 : affleurer ----------------------------------------------------------------------------------------------
ecrire_svg("08-affleurer.svg", 820, 270, "Affleurer les côtés de la cale",
           "Vue de dessus : la cale dépasse un peu sur les côtés de la rallonge ; on la reprend au ras de la touche sans toucher la table.", [
    texte(410, 36, "Vue de dessus de la rallonge", 16, C["texte_doux"], True, "middle"),
    f'<rect x="120" y="100" width="560" height="64" fill="{C["noir"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="440" y="92" width="240" height="8" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>',
    f'<rect x="440" y="164" width="240" height="8" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>',
    repere(1, 560, 60), repere(2, 330, 214),
    f'<path d="M560 76 V90" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="5 4"/>',
    texte(585, 66, "Cale qui dépasse sur les côtés", 14, C["texte"], True),
    texte(355, 220, "Reprendre au ras de la touche (racloir, lime plate),", 14, C["texte"], True),
    texte(355, 240, "sans toucher la finition de la table", 14, C["texte"], True),
])
