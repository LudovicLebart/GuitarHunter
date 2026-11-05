"""Schémas de la fiche « Caler la rallonge de touche » : un par étape clé.

    python docs/fiches/_banque/build_cale_rallonge.py
Écrit les .svg dans docs/fiches/img/caler-la-rallonge-de-touche/.
Coupe latérale : le manche est à gauche, la table à droite. Le manche est tourné autour du joint (écart exagéré).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coupe import RALLONGE, TOUCHE, Coupe  # noqa: E402
from kit import C, bon_mauvais, boite, cote, etiquette, fleche, repere, texte  # noqa: E402
from kit import ecrire as kit_ecrire  # noqa: E402

SLUG = "caler-la-rallonge-de-touche"
YT = 130            # dessus de la table
ANGLE = 8.8         # degrés, exagéré
OUIE = (190, 330)   # la rosace est reculée : le bout de la rallonge repose sur la table, le serre-joint passe par la rosace


def coupe(jx, cale=0.0, yt=YT, corps=200):
    """La coupe commune (`coupe.py`), manche tourné de ANGLE autour du joint. `cale` : 0 = pas de cale ; 1 = cale pleine ;
    entre les deux = cale trop mince (jour, en pointillés). Renvoie (Coupe, dessin, bout_x, bout_y) : bout = dessous de la rallonge à son extrémité."""
    c = Coupe(jx=jx, yt=yt, angle=ANGLE, longueur=100, corps=corps, ouie=OUIE)
    bx, by = c.pt(RALLONGE, 0)
    p = [c.corps(vide=False, legende_ouie=False), c.manche()]
    if cale:
        haut = yt - (yt - by) * cale
        p.append(f'<polygon points="{jx},{yt} {bx:.1f},{yt} {bx:.1f},{haut:.1f}" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>')
        if cale < 1:
            p.append(f'<polygon points="{jx},{yt} {bx:.1f},{haut:.1f} {bx:.1f},{by:.1f}" fill="none" stroke="{C["alerte"]}" stroke-width="2" stroke-dasharray="5 4"/>')
    return c, "".join(p), bx, by


def ecrire_svg(nom, largeur, hauteur, titre, desc, morceaux):
    kit_ecrire(SLUG, nom, largeur, hauteur, titre, desc, morceaux)


def sur_rallonge(c, u, haut=6):
    """Point au-dessus de la rallonge, à l'abscisse u du manche."""
    return c.pt(u, -TOUCHE - haut)


# 01 Vue d'ensemble : vide, puis cale ---------------------------------------------------------------------------------
c1, g1, bx1, by1 = coupe(140)
c2, g2, bx2, by2 = coupe(520, 1)
ecrire_svg("01-vide-sous-la-rallonge.svg", 820, 375, "Vide sous la rallonge de touche après un neck reset",
           "Coupe latérale : à gauche la rallonge décolle de la table après le reset ; à droite une cale en coin du même bois que la touche comble le vide.", [
    texte(190, 42, "Après le reset : la rallonge décolle", 16, C["texte"], True, "middle"),
    texte(610, 42, "Une cale en coin comble le vide", 16, C["ok"], True, "middle"),
    g1, g2,
    etiquette(1, c1.jx + 20, YT - 52, *sur_rallonge(c1, 60)),
    etiquette(2, bx1 + 42, YT - 6, bx1 - 8, (by1 + YT) / 2 + 2),
    etiquette(3, bx2 + 42, YT - 6, bx2 - 12, YT - 4),
    texte(40, 305, "1  Rallonge de touche", 14, C["texte"], True),
    texte(40, 325, "2  Vide qui grandit vers le bout", 14, C["texte"], True),
    texte(440, 305, "3  Cale : même bois que la touche, amincie vers le joint", 14, C["texte"], True),
    texte(410, 358, "Écart exagéré sur le dessin. Au-delà de la tolérance, on cale plutôt que de forcer la rallonge à plat.", 14, C["texte_doux"], False, "middle"),
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
c, g, bx, by = coupe(300)
ecrire_svg("03-mesurer-l-ecart.svg", 820, 375, "Mesurer l'écart sous le bout de la rallonge",
           "Coupe latérale : l'écart se mesure entre le dessous du bout de la rallonge et la table, manche serré à blanc.", [
    texte(410, 30, "Manche serré à blanc, comme il le sera au collage", 16, C["texte_doux"], True, "middle"),
    g,
    cote(bx + 14, by, bx + 14, YT, C["alerte"], dehors=True),
    etiquette(1, bx + 70, YT - 56, bx + 14, (by + YT) / 2), texte(bx + 92, YT - 50, "Écart au bout", 14, C["texte"], True),
    texte(410, 320, "Mesurer côté graves et côté aigus (cales d'épaisseur ou petits coins).", 14, C["texte_doux"], False, "middle"),
    texte(410, 342, "Si l'écart diffère d'un côté à l'autre : revoir l'alignement du manche avant de caler.", 14, C["texte_doux"], False, "middle"),
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
c, g, bx, by = coupe(300)
ecrire_svg("05-preparer-les-surfaces.svg", 820, 375, "Préparer les surfaces avant collage",
           "Coupe latérale : l'ancienne colle est retirée sous la rallonge et sur la table, sans toucher à la finition de la table autour.", [
    texte(410, 30, "Surfaces propres et saines avant d'essayer la cale", 16, C["texte_doux"], True, "middle"),
    g,
    etiquette(1, c.jx + 90, YT - 56, *c.pt(110, 0)),
    etiquette(2, c.jx + 120, YT + 76, c.jx + 120, YT + 6),
    texte(c.jx + 112, YT - 50, "Dessous de la rallonge : retirer l'ancienne colle", 14, C["texte"], True),
    texte(c.jx + 142, YT + 82, "Table : même chose, vernis intact autour", 14, C["texte"], True),
])

# 06 Étape 4 : ajuster à blanc ----------------------------------------------------------------------------------------
c1, g1, bx1, by1 = coupe(140, 1)
c2, g2, bx2, by2 = coupe(520, 0.55)
ecrire_svg("06-ajuster-a-blanc.svg", 820, 375, "Ajuster la cale à blanc",
           "Deux coupes : à gauche la cale épouse le dessous de la rallonge sans jour ; à droite la cale est trop mince et laisse un jour.", [
    texte(190, 42, "Cale ajustée : aucun jour", 16, C["ok"], True, "middle"),
    texte(610, 42, "Cale trop mince : jour sous la rallonge", 16, C["ko"], True, "middle"),
    g1, g2,
    bon_mauvais(bx1 + 50, YT - 40, True), bon_mauvais(bx2 + 50, YT - 40, False),
    texte(410, 318, "Serrer à blanc, sans colle : la rallonge repose sur la cale sur toute sa longueur,", 14, C["texte_doux"], False, "middle"),
    texte(410, 341, "sans être relevée ni forcée. Si la table est bombée, courber un peu le dessous de la cale.", 14, C["texte_doux"], False, "middle"),
])

# 07 Étape 5 : coller et serrer ---------------------------------------------------------------------------------------
Y7 = 170
c, g, bx, by = coupe(300, 1, yt=Y7, corps=380)
cx = c.jx + 150                                      # le serre-joint appuie à cet endroit de la rallonge
ht = by - 76                                         # barre du haut du serre-joint
ecrire_svg("07-coller-et-serrer.svg", 820, 400, "Coller la cale et serrer par la rosace",
           "Coupe latérale : un serre-joint en C appuie sur le bout de la rallonge et, par la rosace, sur une cale de serrage sous la table.", [
    texte(410, 28, "La colle de peau chaude fige vite : tout est préparé et répété à blanc avant d'encoller", 15, C["texte_doux"], True, "middle"),
    g,
    f'<rect x="{cx - 50}" y="{Y7 + 12}" width="100" height="16" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<path d="M{cx} {ht:.0f} H{c.jx + 250} V{Y7 + 90} H{cx}" stroke="{C["trait"]}" stroke-width="7" fill="none" stroke-linejoin="round"/>',
    fleche(cx, ht, cx, c.pt(150, -TOUCHE - 6)[1] - 4, C["alerte"]), fleche(cx, Y7 + 90, cx, Y7 + 32, C["alerte"]),
    etiquette(1, c.jx - 180, Y7 - 84, c.jx + 100, Y7 - 12),
    etiquette(2, c.jx + 60, Y7 + 116, cx - 20, Y7 + 22),
    etiquette(3, c.jx + 290, ht - 14, c.jx + 250, ht),
    texte(c.jx - 158, Y7 - 78, "Colle de peau : cale, puis rallonge", 14, C["texte"], True),
    texte(c.jx + 82, Y7 + 122, "Cale de serrage sous la table (passée par la rosace)", 14, C["texte"], True),
    texte(c.jx + 312, ht - 8, "Serre-joint en C", 14, C["texte"], True),
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

# 09 Fabriquer la cale en coin au rabot -------------------------------------------------------------------------------
# Cas « s'annule à zéro » : bloc-guide de 2 x e placé à 2 x L du bout mince ; la semelle touche le bloc, le dessus du coin
# (épaisseur e à L du bout mince), puis la base au bout mince.
BASE, XT, LNG, EP = 245, 640, 200, 36           # dessus de la planche-support, bout mince, longueur L, épaisseur e
XG = XT - 2 * LNG                                 # bloc-guide
pente = (2 * EP) / (2 * LNG)
ecrire_svg("09-fabriquer-au-rabot.svg", 820, 360, "Fabriquer la cale en coin au rabot",
           "Coupe latérale : la pièce est fixée au double face sur une planche plane ; un bloc-guide de deux fois l'épaisseur du gros bout, placé à deux fois la longueur du coin, soutient l'arrière de la semelle du rabot ; le coin s'annule au bout mince.", [
    texte(410, 28, "Le bloc-guide fixe la pente : la semelle repose sur lui et sur la planche, le coin s'arrête de lui-même", 15, C["texte_doux"], True, "middle"),
    f'<rect x="130" y="{BASE}" width="620" height="32" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    f'<rect x="{XT - LNG}" y="{BASE - 4}" width="{LNG}" height="4" fill="{C["ruban"]}" stroke="{C["ruban_trait"]}" stroke-width="1"/>',
    f'<rect x="{XT - LNG}" y="{BASE - 4 - EP}" width="{LNG}" height="{EP}" fill="none" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="5 4"/>',
    f'<polygon points="{XT - LNG},{BASE - 4} {XT},{BASE - 4} {XT - LNG},{BASE - 4 - EP}" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{XG - 15}" y="{BASE - 2 * EP}" width="30" height="{2 * EP}" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>',
    f'<polygon points="{XG - 10},{BASE - 2 * EP - 10 * pente:.1f} {XT},{BASE - 2 * EP + 2 * LNG * pente:.1f} {XT},{BASE - 2 * EP + 2 * LNG * pente - 40:.1f} {XG - 10},{BASE - 2 * EP - 10 * pente - 40:.1f}" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2" opacity="0.85"/>',
    texte(XG + 160, 112, "Rabot à longue semelle, lame très affûtée", 14, C["texte"], True, "middle"),
    texte(XG - 24, BASE - EP, "Bloc-guide (2 × e)", 14, C["texte"], True, "end"),
    texte(XT - LNG - 10, BASE - 14, "e", 14, C["texte"], True, "end"),
    texte(XT + 18, BASE - 28, "bout mince", 14, C["texte"], True),
    texte(XT + 18, BASE - 10, "(côté joint)", 14, C["texte"], True),
    f'<path d="M{XT - LNG} 302 H{XT} M{XT - LNG} 296 v12 M{XT} 296 v12" stroke="{C["texte_doux"]}" stroke-width="2"/>',
    f'<path d="M{XG} 322 H{XT} M{XG} 316 v12 M{XT} 316 v12" stroke="{C["texte_doux"]}" stroke-width="2"/>',
    texte(XT - LNG / 2, 296, "L (longueur du coin)", 14, C["texte"], True, "middle"),
    texte(XG + LNG, 340, "2 × L : distance du bloc-guide au bout mince", 14, C["texte"], True, "middle"),
])

# 10 Fabriquer la cale en coin à la ponceuse à bande ------------------------------------------------------------------
ecrire_svg("10-fabriquer-a-la-ponceuse.svg", 820, 340, "Fabriquer la cale en coin à la ponceuse à bande",
           "Coupe latérale : la planche support et la pièce, collées au double face, sont appuyées sur la bande ; l'appui est plus fort côté mince, qui est ponçu davantage.", [
    texte(410, 28, "Ponceuse à bande : la pièce reste collée à la planche, qu'on appuie plus fort côté mince", 15, C["texte_doux"], True, "middle"),
    f'<g transform="rotate(2.5 200 170)">'
    f'<rect x="200" y="150" width="500" height="30" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>'
    f'<rect x="250" y="180" width="320" height="4" fill="{C["ruban"]}" stroke="{C["ruban_trait"]}" stroke-width="1"/>'
    f'<rect x="250" y="184" width="320" height="30" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>'
    '</g>',
    f'<rect x="130" y="231" width="620" height="12" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="130" y="243" width="620" height="24" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    fleche(620, 98, 620, 160, C["alerte"]), fleche(260, 118, 260, 140, C["alerte"]),
    texte(640, 120, "appui plus fort côté mince", 14, C["alerte"], True),
    texte(130, 108, "appui léger", 14, C["texte"], True),
    texte(440, 262, "Bande abrasive en mouvement", 14, C["texte"], True, "middle"),
    texte(410, 296, "Planche plane, double face et pièce : le côté le plus appuyé est le plus ponçu, donc le plus mince.", 14, C["texte_doux"], False, "middle"),
    texte(410, 318, "Poncer court, mesurer, recommencer. Finir à la main pour ne pas passer sous l'épaisseur voulue.", 14, C["texte_doux"], False, "middle"),
])
