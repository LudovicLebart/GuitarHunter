"""Schémas de la fiche « Décoller la rallonge de touche » : un par étape clé.

    python docs/fiches/_banque/build_decoller_touche.py
Écrit les .svg dans docs/fiches/img/decoller-la-touche/.
Coupe latérale : manche à gauche, table à droite, rallonge de touche à plat sur la table.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coupe import RALLONGE, TASSEAU, Coupe  # noqa: E402
from kit import C, boite, etiquette, fleche, repere, texte  # noqa: E402
from kit import ecrire as kit_ecrire  # noqa: E402

SLUG = "decoller-la-touche"
YT = 150            # dessus de la table
OUIE = (190, 330)   # la rosace est reculée : le bout de la rallonge repose sur la table, la lame entre par la rosace
BAS = YT + 150      # sous le fond de la caisse : début des légendes du bas


def ecrire(nom, largeur, hauteur, titre, desc, morceaux):
    kit_ecrire(SLUG, nom, largeur, hauteur, titre, desc, morceaux)


def coupe():
    """La coupe commune (`coupe.py`), manche droit : renvoie (Coupe, dessin). La colle est la couche jaune entre la rallonge et la table."""
    c = Coupe(yt=YT, ouie=OUIE)
    x0, x1 = c.jx + TASSEAU, c.jx + RALLONGE
    colle = f'<rect x="{x0}" y="{YT - 3}" width="{x1 - x0}" height="3" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="1"/>'
    return c, c.corps(vide=False) + c.manche() + colle


def pied(lignes, y0=BAS + 36):
    """Légende du bas : une ligne par entrée."""
    return [texte(410, y0 + 22 * i, ligne, 14, C["texte_doux"], False, "middle") for i, ligne in enumerate(lignes)]


# 01 Ordre des opérations ---------------------------------------------------------------------------------------------
etapes = [("1  Vérifier", "boulons sous\nla rallonge"), ("2  Protéger", "incrustations,\njoints, table"), ("3  Chauffer", "la rallonge,\npar-dessus"),
          ("4  Tester", "la lame entre-t-elle\nsans forcer ?"), ("5  Décoller", "de la ouïe\nvers le joint")]
morceaux = [texte(410, 42, "Dans cet ordre, sans jamais forcer la lame", 17, C["texte_doux"], True, "middle")]
for i, (t, s) in enumerate(etapes):
    x = 10 + i * 162
    morceaux.append(boite(x, 80, 148, 90, t, s))
    if i < 4:
        morceaux.append(fleche(x + 150, 125, x + 160, 125))
morceaux.append(texte(410, 210, "Si la lame résiste : chauffer encore, puis retester. La rallonge est décollée avant de déposer le manche.", 14, C["texte_doux"], False, "middle"))
ecrire("01-ordre-des-operations.svg", 820, 235, "Ordre des opérations pour décoller la rallonge de touche",
       "Cinq étapes : vérifier les boulons, protéger, chauffer, tester, décoller de la ouïe vers le joint.", morceaux)

# 02 Étape 1 : vérifier les boulons -----------------------------------------------------------------------------------
c, dessin = coupe()
bx = c.jx + 100                                      # boulon éventuel, au milieu de la rallonge
ecrire("02-verifier-les-boulons.svg", 820, 400, "Chercher un boulon sous la rallonge",
       "Coupe latérale : certaines guitares ont un ou deux boulons qui tiennent la rallonge à la table ; on regarde avec un miroir avant de chauffer.", [
    texte(410, 30, "Avant de chauffer : chercher un boulon qui tient la rallonge", 16, C["texte_doux"], True, "middle"),
    dessin,
    f'<rect x="{bx - 5}" y="{YT - 10}" width="10" height="40" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{bx - 14}" y="{YT + 14}" width="28" height="8" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    etiquette(1, bx + 20, YT + 78, bx, YT + 18),
    texte(bx + 40, YT + 84, "Boulon éventuel, vu depuis l'intérieur de la caisse", 14, C["texte"], True),
] + pied(["Regarder avec un miroir et une lampe par la rosace. Avec un boulon, la rallonge se dévisse."]))

# 03 Étape 3 : chauffer -----------------------------------------------------------------------------------------------
c, dessin = coupe()
x0, x1 = c.jx + 10, c.jx + RALLONGE - 6
ecrire("03-chauffer.svg", 820, 400, "Chauffer la rallonge de touche par-dessus",
       "Coupe latérale : une cale de bois, une source de chaleur et une feuille d'aluminium posées sur la rallonge.", [
    texte(410, 30, "Chauffer par-dessus, quelques minutes, sans appui fort", 16, C["texte_doux"], True, "middle"),
    dessin,
    f'<rect x="{x0}" y="{YT - 22}" width="{x1 - x0}" height="6" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{x0}" y="{YT - 48}" width="{x1 - x0}" height="26" rx="6" fill="{C["alerte"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{x0}" y="{YT - 68}" width="{x1 - x0}" height="20" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    etiquette(1, 540, 56, x1 - 30, YT - 58), etiquette(2, 540, 92, x1 - 30, YT - 35), etiquette(3, 540, 128, x1 - 30, YT - 19),
    texte(562, 62, "Cale de bois : serrage léger", 14, C["texte"], True),
    texte(562, 98, "Couverture chauffante (ou fer)", 14, C["texte"], True),
    texte(562, 134, "Feuille d'aluminium", 14, C["texte"], True),
] + pied(["Source de chaleur : couverture chauffante, ou fer à souder sur un bloc d'aluminium.",
          "Ne jamais laisser la couverture chauffante reposer sur le vernis de la guitare.",
          "Les incrustations de touche peuvent roussir ou fondre : les couvrir d'aluminium."]))

# 04 Étapes 4 et 5 : glisser la lame ----------------------------------------------------------------------------------
c, dessin = coupe()
fin = c.jx + RALLONGE                                # bout de la rallonge
ecrire("04-glisser-la-lame.svg", 820, 400, "Glisser la lame sous la rallonge",
       "Coupe latérale : une spatule fine est glissée entre la rallonge et la table, de la rosace vers le joint, en restant à plat.", [
    texte(410, 30, "La lame doit entrer sans résistance : sinon, rechauffer", 16, C["texte_doux"], True, "middle"),
    dessin,
    f'<polygon points="{fin + 60},{YT - 3} {c.jx + 66},{YT - 2} {c.jx + 66},{YT} {fin + 60},{YT}" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{fin + 60}" y="{YT - 14}" width="70" height="14" rx="6" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    fleche(fin + 40, YT - 44, fin - 70, YT - 44),
    etiquette(1, fin + 100, YT - 76, fin - 30, YT - 44), etiquette(2, c.jx + 90, YT + 56, c.jx + 120, YT - 1),
    texte(fin + 120, YT - 70, "Elle progresse vers le joint", 14, C["texte"], True),
    texte(c.jx + 112, YT + 62, "Lame fine, à plat, sans entailler la table", 14, C["texte"], True),
] + pied(["Le bois de la table est plus tendre que la touche : une lame qui force l'entame ou l'arrache.",
          "Si la lame résiste, remettre la protection et rechauffer environ une minute."]))

# 05 Vue de dessus : où la colle résiste ------------------------------------------------------------------------------
ecrire("05-ou-la-colle-resiste.svg", 820, 280, "Où la colle résiste sous la rallonge",
       "Vue de dessus de la rallonge : le bout et les côtés se décollent facilement, une zone plus dure se trouve vers le centre, près du joint avec le manche.", [
    texte(410, 36, "Vue de dessus de la rallonge", 16, C["texte_doux"], True, "middle"),
    f'<rect x="60" y="90" width="150" height="80" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="210" y="90" width="520" height="80" fill="{C["noir"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<ellipse cx="300" cy="130" rx="70" ry="28" fill="{C["ko"]}" opacity="0.6"/>',
    f'<path d="M730 130 H680 M720 98 H680 M720 162 H680" stroke="{C["ok"]}" stroke-width="4" fill="none"/>',
    texte(130, 80, "Manche", 14, C["texte"], True, "middle"),
    texte(700, 80, "Bout et côtés : cèdent facilement", 14, C["texte"], True, "middle"),
    texte(300, 200, "Zone plus dure, près du joint : chauffer encore", 14, C["texte"], True, "middle"),
    texte(410, 252, "Se fier à la résistance de la lame sur la guitare, pas au dessin.", 14, C["texte_doux"], False, "middle"),
])
