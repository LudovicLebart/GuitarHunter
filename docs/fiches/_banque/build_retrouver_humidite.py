"""Reconstruit `docs/fiches/img/retrouver-humidite-normale/01-sac-et-hygrometre.svg` avec la banque d'éléments.

    python docs/fiches/_banque/build_retrouver_humidite.py
Exemple type d'assemblage : chaque fiche qui veut un schéma écrit un petit script de ce genre, relancé à chaque retouche.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import (bol_eponge, guitare_dessus, hygrometre, repere, sac, svg, texte, C)  # noqa: E402

SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img", "retrouver-humidite-normale",
                      "01-sac-et-hygrometre.svg")

corps = "\n  ".join([
    sac(20, 50, 780, 270, "Sac plastique fermé, une nuit"),
    guitare_dessus(x=50, y=190, echelle=0.8),
    bol_eponge(470, 235),
    hygrometre(520, 115),
    repere(1, 250, 302, "Guitare à plat"),
    repere(2, 620, 280, "Bol d'eau + éponge"),
    repere(3, 585, 95, "Hygromètre : viser 45 à 55 %"),
    texte(410, 352, "L'eau reste dans le bol : seul l'air du sac s'humidifie (la vapeur ne mouille pas la guitare).",
          15, C["texte_doux"], False, "middle"),
])
with open(SORTIE, "w", encoding="utf-8", newline="\n") as f:
    f.write(svg(820, 375, "Méthode du sac : remettre l'air autour de la guitare à une humidité normale",
                "Guitare à plat dans un sac plastique fermé, avec un bol d'eau contenant une éponge et un hygromètre. "
                "L'eau reste dans le bol, la vapeur humidifie l'air du sac.", corps))
print("écrit :", os.path.normpath(SORTIE))
