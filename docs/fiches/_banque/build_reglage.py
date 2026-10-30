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

# 8. Sillet de chevalet (acoustique) : poncer le dessous du sillet -------------------------------------------------------
def sillet_face(x0, titre, retire, couleur):
    """Sillet vu de face (grave à gauche, aigu à droite) ; `retire` = (épaisseur grave, épaisseur aigu) en px."""
    g, a = retire
    return "".join([
        f'<rect x="{x0}" y="110" width="340" height="62" rx="6" fill="#fff" stroke="{C["trait"]}" stroke-width="3"/>',
        f'<polygon points="{x0},172 {x0 + 340},172 {x0 + 340},{172 - a} {x0},{172 - g}" fill="{C["alerte"]}" opacity=".35"/>',
        f'<path d="M{x0} {172 - g} L{x0 + 340} {172 - a}" stroke="{C["alerte"]}" stroke-width="3" stroke-dasharray="8 5"/>',
        texte(x0, 100, "Grave", 14, C["texte"], True), texte(x0 + 340, 100, "Aigu", 14, C["texte"], True, "end"),
        texte(x0 + 170, 70, titre, 16, couleur, True, "middle"),
    ])


corps = "\n  ".join([
    sillet_face(40, "Cas courant : ponçage à plat", (16, 16), C["ok"]),
    sillet_face(440, "Cas particulier : en dégradé", (30, 0), C["eau_trait"]),
    texte(210, 205, "Action trop haute partout", 14, C["texte_doux"], False, "middle"),
    texte(210, 224, "même épaisseur sur toute la longueur", 14, C["texte_doux"], False, "middle"),
    texte(610, 205, "Seules les cordes graves sont trop hautes", 14, C["texte_doux"], False, "middle"),
    texte(610, 224, "plus côté grave, zéro côté aigu", 14, C["texte_doux"], False, "middle"),
    repere(1, 60, 285, "Dessous du sillet sur papier de verre collé sur un support plan, mouvement régulier"),
    repere(2, 60, 325, "Vérifier que le dessous reste plan, remettre en place, réaccorder, remesurer"),
    texte(410, 30, "Baisser l'action : on ponce le dessous du sillet (la zone rouge est retirée)", 17, C["texte_doux"], True, "middle"),
    texte(410, 365, "Baisser la 12e frette de 0,020 po (0,5 mm) demande de retirer environ 0,040 po (1 mm) sous le sillet (exemple StewMac).", 14, C["texte_doux"], False, "middle"),
])
ecrire("regler-hauteur-chevalet", "01-poncer-le-sillet.svg", svg(
    820, 385, "Baisser un sillet de chevalet d'acoustique",
    "Sillet vu de face. À gauche, ponçage à plat : même épaisseur retirée sur toute la longueur. À droite, ponçage en dégradé : plus de matière côté grave, rien côté aigu.", corps))


# 9. Relief visé : plages par instrument et par style de jeu --------------------------------------------------------------
LIGNES = [  # (libellé, bas, haut en pouces, couleur, source)
    ("Électrique", 0.004, 0.008, "#2563eb", "StewMac"),
    ("Acoustique", 0.006, 0.012, "#16a34a", "StewMac"),
    ("Basse", 0.008, 0.015, "#7c3aed", "StewMac"),
    ("Classique (nylon)", 0.008, 0.010, "#b45309", "luthiers, forums"),
    ("Jeu léger à médium", 0.0095, 0.0105, "#0891b2", "Premier Guitar : environ 0,010"),
    ("Jeu agressif ou capo", 0.015, 0.020, "#dc2626", "Premier Guitar"),
]
X0, ECH = 250, 20800          # origine et pixels par pouce (0,025 po = 520 px)
morceaux = [texte(410, 32, "Relief visé (valeurs de départ ; sources et frettes de mesure différentes)", 17, C["texte_doux"], True, "middle")]
for pouce in (0, 0.005, 0.010, 0.015, 0.020, 0.025):
    x = X0 + pouce * ECH
    morceaux.append(f'<path d="M{x:.0f} 55 V{55 + 40 * len(LIGNES) + 15}" stroke="#cbd5e1" stroke-width="1"/>')
    morceaux.append(texte(f"{x:.0f}", 50, f"{pouce:.3f} po".replace(".", ","), 12, C["texte_doux"], False, "middle"))
    morceaux.append(texte(f"{x:.0f}", 55 + 40 * len(LIGNES) + 32, f"{pouce * 25.4:.2f} mm".replace(".", ","), 12, C["texte_doux"], False, "middle"))
for i, (nom, bas, haut, col, src) in enumerate(LIGNES):
    y = 70 + 40 * i
    morceaux.append(texte(X0 - 12, y + 19, nom, 15, C["texte"], True, "end"))
    morceaux.append(f'<rect x="{X0 + bas * ECH:.0f}" y="{y}" width="{max((haut - bas) * ECH, 8):.0f}" height="26" rx="5" fill="{col}" opacity=".85"/>')
    morceaux.append(texte(f"{X0 + haut * ECH + 12:.0f}", y + 19, src, 12, C["texte_doux"]))
morceaux.append(texte(410, 70 + 40 * len(LIGNES) + 62,
                      "Les frettes de mesure diffèrent selon les sources (6e à 8e) ; aucune source lue ne cite la 10e.", 13, C["texte_doux"], False, "middle"))
contenu = svg(820, 70 + 40 * len(LIGNES) + 80, "Relief visé par type d'instrument et style de jeu",
              "Barres horizontales en pouces et millimètres : électrique 0,004 à 0,008, acoustique 0,006 à 0,012, basse 0,008 à 0,015, "
              "classique 0,008 à 0,010, jeu léger à médium environ 0,010, jeu agressif ou capo 0,015 à 0,020.", "\n  ".join(morceaux))
ecrire("mesurer-relief-manche", "02-relief-vise.svg", contenu)
ecrire("reglage-truss-rod", "03-relief-vise.svg", contenu)


# 10. Mesure du relief à la règle crantée (cales sous la règle, vers la 10e case) ------------------------------------------
T10 = (1 - 2 ** (-10 / 12)) / (1 - 2 ** (-22 / 12))     # position de la 10e case entre le sillet et la 22e, en fraction
manche, xs = manche_profil(60, 170, longueur=700, relief=13, frettes=22, corde=False, pic=T10)   # creux maximal à la 10e case
x0, y0 = 60, 170
fin = xs[-1]
creux10 = 13   # creux maximal, à la 10e case
encoches = "".join(f'<rect x="{px - 4:.1f}" y="{y0 - 6}" width="8" height="6" fill="{C["fond"]}"/>' for px in xs)
corps = "\n  ".join([
    manche,
    f'<rect x="{x0 - 6}" y="{y0 - 10}" width="{fin - x0 + 12:.1f}" height="10" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>',
    encoches,
    f'<line x1="{x0 - 14}" y1="{y0 - 24}" x2="{fin + 40:.1f}" y2="{y0 - 24}" stroke="#94a3b8" stroke-width="2"/>',
    f'<rect x="{xs[9] - 11:.1f}" y="{y0}" width="22" height="{max(creux10 - 3, 4):.1f}" fill="{C["colle"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>',
    texte(f"{xs[9]:.1f}", y0 + 52, "10e case : creux maximal", 13, C["alerte"], True, "middle"),
    repere(1, 70, 78), texte(95, 84, "Règle crantée sur la touche (crans au droit des frettes)", 14, C["texte"], True),
    ligne(150, 92, 190, y0 - 11),
    repere(2, 70, 112), texte(95, 118, "Cordes accordées, sous tension, dans les crans", 14, C["texte"], True),
    ligne(300, 126, 330, y0 - 25),
    repere(3, 150, 245), texte(175, 251, "Cales sous la règle, là où le creux est le plus grand", 14, C["texte"], True),
    texte(175, 270, "(vers la 10e case)", 14, C["texte_doux"], True),
    ligne(420, 238, xs[9] - 4, y0 + creux10 + 2),
    texte(410, 30, "Mesure du relief à la règle crantée (cordes accordées)", 17, C["texte_doux"], True, "middle"),
    texte(410, 300, "On mesure là où le creux est le plus grand : la cale qui passe tout juste donne le creux (0,20 à 0,25 mm visés). Creux exagéré.", 14, C["texte_doux"], False, "middle"),
])
ecrire("mesurer-relief-manche", "03-regle-crantee.svg", svg(
    820, 320, "Mesure du relief à la règle crantée",
    "Manche vu de côté : une règle crantée repose sur la touche à chaque bout, les cordes passent dans les crans, et des cales glissées sous la règle vers la 10e case mesurent le creux.", corps))
