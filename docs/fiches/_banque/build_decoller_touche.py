"""Schémas de la fiche « Décoller la rallonge de touche » : un par étape clé.

    python docs/fiches/_banque/build_decoller_touche.py
Écrit les .svg dans docs/fiches/img/decoller-la-touche/.
Coupe latérale : manche à gauche, table à droite, rallonge de touche à plat sur la table.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import C, boite, fleche, repere, svg, texte  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img", "decoller-la-touche")
YT = 170            # dessus de la table
JOINT = 190         # joint manche / corps
FIN = 670           # bout de la rallonge


def ecrire(nom, largeur, hauteur, titre, desc, morceaux):
    os.makedirs(IMG, exist_ok=True)
    with open(os.path.join(IMG, nom), "w", encoding="utf-8", newline="\n") as f:
        f.write(svg(largeur, hauteur, titre, desc, "\n  ".join(morceaux)))
    print("écrit :", nom)


def coupe(x0=20):
    """Manche, rallonge posée sur la table, table (écart entre la rallonge et la table : colle)."""
    return "".join([
        f'<rect x="{x0}" y="{YT - 9}" width="{JOINT - x0}" height="79" fill="{C["manche"]}"/>',
        f'<rect x="{x0}" y="{YT - 18}" width="{FIN - x0}" height="9" fill="{C["noir"]}" stroke="{C["trait"]}" stroke-width="2"/>',
        f'<rect x="{JOINT}" y="{YT - 9}" width="{FIN - JOINT}" height="9" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>',
        f'<rect x="{JOINT}" y="{YT}" width="{FIN + 90 - JOINT}" height="14" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    ])


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
bx = JOINT + 200
ecrire("02-verifier-les-boulons.svg", 820, 290, "Chercher un boulon sous la rallonge",
       "Coupe latérale : certaines guitares ont un ou deux boulons qui tiennent la rallonge à la table ; on regarde avec un miroir avant de chauffer.", [
    coupe(),
    f'<rect x="{bx}" y="{YT - 9}" width="12" height="40" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{bx - 8}" y="{YT + 14}" width="28" height="8" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    repere(1, bx + 6, YT + 72),
    f'<path d="M{bx + 6} {YT + 58} V{YT + 34}" stroke="{C["texte_doux"]}" stroke-width="2" stroke-dasharray="5 4"/>',
    texte(bx + 30, YT + 78, "Boulon éventuel, vu depuis l'intérieur de la caisse", 14, C["texte"], True),
    texte(410, 30, "Avant de chauffer : chercher un boulon qui tient la rallonge", 16, C["texte_doux"], True, "middle"),
    texte(410, 262, "Regarder avec un miroir et une lampe par la rosace. Avec un boulon, la rallonge se dévisse.", 14, C["texte_doux"], False, "middle"),
])

# 03 Étape 3 : chauffer -----------------------------------------------------------------------------------------------
ecrire("03-chauffer.svg", 820, 330, "Chauffer la rallonge de touche par-dessus",
       "Coupe latérale : une cale de bois, une source de chaleur et une feuille d'aluminium posées sur la rallonge.", [
    coupe(),
    f'<rect x="{JOINT + 20}" y="{YT - 30}" width="{FIN - JOINT - 40}" height="10" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{JOINT + 20}" y="{YT - 66}" width="{FIN - JOINT - 40}" height="34" rx="6" fill="{C["alerte"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{JOINT + 20}" y="{YT - 88}" width="{FIN - JOINT - 40}" height="20" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    repere(1, 90, 56), repere(2, 90, 100), repere(3, 90, 144),
    texte(112, 62, "Cale de bois : serrage léger", 14, C["texte"], True),
    texte(112, 106, "Couverture chauffante, ou fer et bloc d'aluminium", 14, C["texte"], True),
    texte(112, 150, "Feuille d'aluminium", 14, C["texte"], True),
    texte(410, 28, "Chauffer par-dessus, quelques minutes, sans appui fort", 16, C["texte_doux"], True, "middle"),
    texte(410, 262, "Ne jamais laisser la couverture chauffante reposer sur le vernis de la guitare.", 14, C["texte_doux"], False, "middle"),
    texte(410, 284, "Les incrustations de touche peuvent roussir ou fondre : les couvrir d'aluminium.", 14, C["texte_doux"], False, "middle"),
])

# 04 Étapes 4 et 5 : glisser la lame ----------------------------------------------------------------------------------
ly = YT - 4
ecrire("04-glisser-la-lame.svg", 820, 320, "Glisser la lame sous la rallonge",
       "Coupe latérale : une spatule fine est glissée entre la rallonge et la table, de la ouïe vers le joint, en restant à plat.", [
    coupe(),
    f'<polygon points="{FIN + 20},{ly - 4} 360,{ly - 2} 360,{ly + 2} {FIN + 20},{ly + 4}" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    f'<rect x="{FIN + 20}" y="{ly - 8}" width="70" height="16" rx="6" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
    fleche(620, YT - 56, 460, YT - 56),
    repere(1, 540, YT - 90), repere(2, 400, YT + 62),
    texte(562, YT - 84, "Elle progresse vers le joint", 14, C["texte"], True),
    texte(422, YT + 68, "Lame fine, à plat, sans entailler la table", 14, C["texte"], True),
    texte(410, 28, "La lame doit entrer sans résistance : sinon, rechauffer", 16, C["texte_doux"], True, "middle"),
    texte(410, 262, "Le bois de la table est plus tendre que la touche : une lame qui force l'entame ou l'arrache.", 14, C["texte_doux"], False, "middle"),
    texte(410, 284, "Si la lame résiste, remettre la protection et rechauffer environ une minute.", 14, C["texte_doux"], False, "middle"),
])

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
