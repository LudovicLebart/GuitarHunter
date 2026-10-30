"""Schéma de la fiche maîtresse « Refaire l'angle du manche » : quel cas, quelle suite.

    python docs/fiches/_banque/build_angle_manche.py
Écrit le .svg dans docs/fiches/img/refaire-angle-du-manche/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import C, boite, fleche, svg, texte  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img", "refaire-angle-du-manche")
os.makedirs(IMG, exist_ok=True)

corps = "\n  ".join([
    texte(410, 32, "Quel cas ? Cela dépend de la façon dont le manche est fixé", 17, C["texte_doux"], True, "middle"),
    boite(210, 52, 400, 70, "Action trop haute malgré tout", "relief correct, sillet au plus bas", C["alerte"]),
    fleche(410, 124, 410, 150),
    boite(260, 152, 300, 56, "Comment le manche est-il fixé ?"),
    fleche(330, 210, 160, 252), fleche(490, 210, 640, 252),
    boite(30, 254, 260, 80, "Vissé", "cale pleine poche\nou ponçage du talon"),
    boite(520, 254, 280, 80, "Collé", "queue d'aronde ou tenon"),
    fleche(590, 336, 530, 372), fleche(730, 336, 710, 372),
    boite(400, 374, 200, 76, "Retailler et recoller", "(neck reset)"),
    boite(620, 374, 190, 76, "Convertir en vissé", "(joint modifié)"),
    fleche(500, 452, 560, 490), fleche(715, 452, 640, 490),
    boite(380, 492, 430, 70, "Manche collé : rallonge de touche", "caler ou recoller la rallonge", C["ok"]),
])
with open(os.path.join(IMG, "01-quel-cas.svg"), "w", encoding="utf-8", newline="\n") as f:
    f.write(svg(820, 580, "Quel cas pour refaire l'angle du manche",
                "Arbre de décision : action trop haute malgré relief correct et sillet au plus bas, puis fixation du manche : vissé (cale ou ponçage du talon) ou collé (retailler et recoller, ou convertir en vissé) ; pour un manche collé, caler ou recoller la rallonge de touche.", corps))
print("écrit : 01-quel-cas.svg")
