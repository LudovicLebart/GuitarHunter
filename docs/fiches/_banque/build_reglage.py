"""Schémas des fiches de réglage : action, sillet, relief, truss rod (déblocage compris).

    python docs/fiches/_banque/build_reglage.py
Écrit les .svg dans docs/fiches/img/<slug>/ (voir README.md de ce dossier).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import (C, bon_mauvais, boite, ecrou_rotation, fleche, frette_corde, guitare_dessus, manche_profil,  # noqa: E402
                 repere, svg, texte)

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")


def ecrire(slug, nom, contenu):
    dossier = os.path.join(IMG, slug)
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, nom)
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenu)
    print("écrit :", os.path.normpath(chemin))


def ligne(x1, y1, x2, y2, col=None):
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{col or C["texte_doux"]}" stroke-width="2" stroke-dasharray="5 4" fill="none"/>'


# 1. Ordre des réglages de l'action ----------------------------------------------------------------------------
corps = "\n  ".join([
    guitare_dessus(x=40, y=215, echelle=0.9),
    # manche (x 348 à 618), sillet (618), chevalet (127)
    ligne(480, 150, 480, 196), repere(1, 480, 128), texte(505, 134, "Relief du manche (truss rod)", 15, C["texte"], True),
    ligne(618, 90, 618, 192), repere(2, 618, 68), texte(643, 74, "Sillet", 15, C["texte"], True),
    ligne(127, 258, 195, 338), repere(3, 215, 348), texte(240, 354, "Hauteur au chevalet", 15, C["texte"], True),
    texte(410, 30, "Toujours dans cet ordre : du manche vers le chevalet", 17, C["texte_doux"], True, "middle"),
    texte(410, 376, "On mesure à chaque étape, cordes accordées à leur tension de jeu.", 14, C["texte_doux"], False, "middle"),
])
ecrire("reglage-action", "01-ordre-des-reglages.svg", svg(
    820, 390, "Ordre des réglages de l'action",
    "Guitare vue de dessus avec trois repères : 1 relief du manche au truss rod, 2 sillet, 3 hauteur au chevalet.", corps))


# 2. Sillet : bon et trop bas ----------------------------------------------------------------------------------
def panneau_sillet(x0, bon):
    y_corde_sillet = 128 if bon else 146
    y_f1 = 137
    p = [f'<rect x="{x0 + 130}" y="140" width="270" height="50" fill="{C["manche"]}"/>',
         f'<rect x="{x0 + 100}" y="118" width="30" height="72" fill="#fff" stroke="{C["trait"]}" stroke-width="2"/>',
         f'<path d="M{x0 + 250 - 12} 140 q12 -10 24 0z" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>']
    # la corde : de la mécanique (haut gauche) au fond de l'entaille, puis droite vers le chevalet
    pente = (y_corde_sillet - 95) / 95
    y_f1_corde = y_corde_sillet + (150 / 270) * (y_f1 - 8 - y_corde_sillet + 6) if False else y_corde_sillet + (y_f1 - 3 - y_corde_sillet) * 0.15 - 2
    p.append(f'<path d="M{x0 + 20} 95 L{x0 + 115} {y_corde_sillet} L{x0 + 400} {y_corde_sillet - (4 if bon else 6)}" '
             f'stroke="#94a3b8" stroke-width="3" fill="none"/>')
    p.append(texte(x0 + 115, 108, "sillet", 13, C["texte_doux"], False, "middle"))
    p.append(texte(x0 + 250, 215, "1re frette", 13, C["texte_doux"], False, "middle"))
    p.append(bon_mauvais(x0 + 350, 60, bon))
    return "".join(p)


corps = "\n  ".join([
    panneau_sillet(0, True), panneau_sillet(410, False),
    texte(200, 40, "Entaille à la bonne profondeur", 16, C["ok"], True, "middle"),
    texte(610, 40, "Entaille trop profonde (sillet trop bas)", 16, C["ko"], True, "middle"),
    texte(200, 245, "Petit jour au-dessus de la 1re frette", 14, C["texte_doux"], False, "middle"),
    texte(200, 264, "(quelques dixièmes de mm)", 14, C["texte_doux"], False, "middle"),
    texte(610, 245, "La corde touche la 1re frette :", 14, C["texte_doux"], False, "middle"),
    texte(610, 264, "elle bourdonne à vide", 14, C["texte_doux"], False, "middle"),
    texte(410, 305, "On ne peut pas remettre de matière : limer le fond de l'entaille lentement, mesurer souvent.", 14, C["texte_doux"], False, "middle"),
])
ecrire("regler-sillet-de-tete", "01-hauteur-au-sillet.svg", svg(
    820, 320, "Hauteur du sillet : bon et trop bas",
    "Coupe du sillet : à gauche l'entaille laisse un petit jour au-dessus de la première frette, à droite elle est trop profonde et la corde touche la frette.", corps))

# 3. Action à la 12e frette ------------------------------------------------------------------------------------
corps = "\n  ".join([
    '<g transform="translate(300 195) scale(2.2)">' + frette_corde(0, 0, 30, None) + '</g>',
    repere(1, 90, 100), texte(115, 106, "Corde", 15, C["texte"], True), ligne(160, 100, 285, 100),
    repere(2, 300, 300), texte(325, 306, "Dessus de la 12e frette", 15, C["texte"], True), ligne(300, 282, 300, 208),
    repere(3, 600, 140), texte(625, 146, "Action = espace mesuré", 15, C["alerte"], True), ligne(600, 155, 400, 160, C["alerte"]),
    texte(410, 40, "Mesure à la 12e frette : du dessus de la frette au dessous de la corde", 16, C["texte_doux"], True, "middle"),
    texte(410, 338, "La frette de mesure (12e, 14e ou 17e) dépend de la source suivie.", 14, C["texte_doux"], False, "middle"),
    texte(410, 358, "Valeurs cibles par type d'instrument : fiche « Régler la hauteur des cordes au chevalet ».", 14, C["texte_doux"], False, "middle"),
])
ecrire("reglage-action", "03-action-12e-frette.svg", svg(
    820, 375, "Mesure de l'action à la 12e frette",
    "Zoom sur la 12e frette : la hauteur entre le dessus de la frette et le dessous de la corde est l'action.", corps))

# 4. Mesure du relief --------------------------------------------------------------------------------------------
manche, xs = manche_profil(60, 150, longueur=640, relief=15, capo=True, etiquettes=True)
y_corde = 150 - 6
x1, x14, x8 = xs[0], xs[13], xs[7]
t8 = (x8 - 60) / (x14 - 60)
y_surf8 = 150 + 4 * 15 * t8 * (1 - t8)
corps = "\n  ".join([
    manche,
    f'<line x1="{x1:.1f}" y1="{y_corde}" x2="{x14:.1f}" y2="{y_corde}" stroke="{C["alerte"]}" stroke-width="3"/>',
    f'<circle cx="{x14:.1f}" cy="{y_corde - 14}" r="12" fill="{C["ruban"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>',
    f'<path d="M{x8:.1f} {y_corde} V{y_surf8 - 3:.1f}" stroke="{C["texte"]}" stroke-width="3"/>',
    f'<path d="M{x8 - 8:.1f} {y_corde} h16 M{x8 - 8:.1f} {y_surf8 - 3:.1f} h16" stroke="{C["texte"]}" stroke-width="3"/>',
    repere(1, x1, 88), texte(x1 + 22, 94, "Capo sur la 1re frette", 14, C["texte"], True),
    repere(2, x14 - 175, 66), texte(x14 - 150, 72, "Corde appuyée à la dernière frette", 14, C["texte"], True),
    repere(3, x8, 230), texte(x8 + 22, 236, "Jauge d'épaisseur à la 8e frette", 14, C["texte"], True),
    ligne(x1, 100, x1, 126), ligne(x14 - 175, 80, x14 - 14, 126), ligne(x8, 218, x8, y_surf8 + 8),
    texte(410, 290, "La corde sert de règle droite ; l'espace mesuré au milieu est le relief (≈ 0,2 à 0,3 mm). Creux exagéré sur le dessin.", 14, C["texte_doux"], False, "middle"),
    texte(410, 28, "Mesure du relief du manche (cordes accordées)", 17, C["texte_doux"], True, "middle"),
])
ecrire("mesurer-relief-manche", "01-mesure-relief.svg", svg(
    820, 310, "Mesure du relief du manche",
    "Manche vu de côté : capo à la première frette, corde appuyée à la dernière frette, jauge d'épaisseur mesurant l'espace au milieu du manche.", corps))

# 5. Truss rod : sens de rotation --------------------------------------------------------------------------------
def panneau_rotation(x0, sens):
    horaire = sens == "horaire"
    man, _ = manche_profil(x0 + 70, 200, longueur=260, relief=3 if horaire else 14, corde=True)
    col = C["ok"] if horaire else C["ko"]
    return (ecrou_rotation(x0 + 200, 95, sens) + man
            + texte(x0 + 200, 40, "Serrer (sens horaire)" if horaire else "Desserrer (sens antihoraire)", 16, col, True, "middle")
            + texte(x0 + 200, 270, "Le manche se redresse" if horaire else "Le manche se creuse", 14, C["texte"], True, "middle")
            + texte(x0 + 200, 290, "Le relief diminue" if horaire else "Le relief augmente", 14, C["texte_doux"], False, "middle"))


corps = "\n  ".join([
    panneau_rotation(0, "horaire"), panneau_rotation(410, "antihoraire"),
    texte(410, 330, "Un quart de tour à la fois, sans à-coup, puis réaccorder et remesurer. Creux exagéré sur les dessins.", 14, C["texte_doux"], False, "middle"),
])
ecrire("reglage-truss-rod", "01-sens-de-rotation.svg", svg(
    820, 350, "Sens de rotation du truss rod",
    "Écrou de truss rod : serrer dans le sens horaire redresse le manche, desserrer dans le sens antihoraire augmente le relief.", corps))

# 6. Truss rod : où est l'accès -----------------------------------------------------------------------------------
def guitare_acces(x0, cote):
    g = guitare_dessus(x=x0, y=170, echelle=0.5)
    if cote == "tete":
        cx, cy = x0 + 0.5 * 690, 170
    else:
        cx, cy = x0 + 0.5 * 262, 170
    return g + f'<circle cx="{cx}" cy="{cy}" r="22" fill="none" stroke="{C["alerte"]}" stroke-width="5"/>'


corps = "\n  ".join([
    guitare_acces(25, "tete"), guitare_acces(435, "corps"),
    texte(210, 60, "Accès côté tête", 17, C["texte"], True, "middle"),
    texte(210, 275, "Derrière un cache ou sous le sillet", 14, C["texte_doux"], False, "middle"),
    texte(210, 295, "(fréquent sur les électriques)", 14, C["texte_doux"], False, "middle"),
    texte(620, 60, "Accès côté corps", 17, C["texte"], True, "middle"),
    texte(620, 275, "Par la rosace ou sous le pickguard", 14, C["texte_doux"], False, "middle"),
    texte(620, 295, "(fréquent sur les acoustiques)", 14, C["texte_doux"], False, "middle"),
    texte(410, 335, "Simple action : redresse seulement le manche. Double action : redresse et creuse. Identifier le type avant d'intervenir.", 14, C["texte_doux"], False, "middle"),
])
ecrire("reglage-truss-rod", "02-acces.svg", svg(
    820, 355, "Où se trouve l'accès du truss rod",
    "Deux guitares vues de dessus : à gauche l'accès du truss rod côté tête, à droite côté corps par la rosace.", corps))

# 7. Déblocage d'un truss rod coincé ---------------------------------------------------------------------------------
etapes = [("1  Détendre", "les cordes\nfranchement"), ("2  Lubrifier", "l'écrou, quelques\nminutes à heures"),
          ("3  Chauffer", "très doucement\n(jamais de flamme)"), ("4  Va-et-vient", "petits mouvements\ndans les deux sens"),
          ("5  Soulager", "la tige : légère\nflexion du manche")]
morceaux = []
for i, (t, s) in enumerate(etapes):
    x = 20 + i * 160
    morceaux.append(boite(x, 90, 140, 90, t, s))
    if i < 4:
        morceaux.append(fleche(x + 142, 135, x + 158, 135))
morceaux += [
    texte(410, 50, "Dans cet ordre, en s'arrêtant dès que ça tourne", 18, C["texte_doux"], True, "middle"),
    f'<path d="M410 190 V225" stroke="{C["ko"]}" stroke-width="3" stroke-dasharray="6 4"/>',
    boite(130, 225, 560, 78, "Toujours bloqué, écrou qui s'arrondit, craquement ?", "S'arrêter et confier l'instrument à un luthier", C["ko"]),
]
ecrire("debloquer-truss-rod", "01-ordre-de-deblocage.svg", svg(
    820, 330, "Ordre des essais pour débloquer un truss rod",
    "Cinq essais successifs : détendre les cordes, lubrifier, chauffer très doucement, tourner en va-et-vient, soulager la tige ; sinon luthier.",
    "\n  ".join(morceaux)))

# 8. Sillet de chevalet (acoustique) : retirer de la matière sous le sillet ----------------------------------------
corps = "\n  ".join([
    texte(410, 40, "Baisser l'action à la 12e frette : on retire de la matière sous le sillet", 17, C["texte_doux"], True, "middle"),
    # sillet vu de face : grave à gauche, aigu à droite
    f'<rect x="130" y="110" width="560" height="70" rx="6" fill="#fff" stroke="{C["trait"]}" stroke-width="3"/>',
    f'<polygon points="130,180 690,180 690,180 130,150" fill="{C["alerte"]}" opacity=".35"/>',
    f'<path d="M130 150 L690 180" stroke="{C["alerte"]}" stroke-width="3" stroke-dasharray="8 5"/>',
    texte(130, 100, "Grave", 15, C["texte"], True), texte(690, 100, "Aigu", 15, C["texte"], True, "end"),
    repere(1, 90, 235), texte(115, 241, "Tracer au crayon la ligne de coupe sous le sillet (pointillé rouge)", 15, C["texte"], True),
    repere(2, 90, 275), texte(115, 281, "Poncer bien à plat jusqu'à la ligne : on retire deux fois la baisse voulue côté grave", 15, C["texte"], True),
    repere(3, 90, 315), texte(115, 321, "Rien côté aigu : la matière retirée diminue jusqu'à zéro", 15, C["texte"], True),
    texte(410, 355, "Exemple StewMac : baisser la 12e frette de 0,020 po (0,5 mm) = retirer 0,040 po (1 mm) côté grave, 0 côté aigu.", 14, C["texte_doux"], False, "middle"),
])
ecrire("regler-hauteur-chevalet", "01-poncer-le-sillet.svg", svg(
    820, 375, "Baisser un sillet de chevalet d'acoustique",
    "Sillet vu de face : la zone rouge sous le sillet est retirée, plus épaisse côté cordes graves, nulle côté aigu.", corps))
