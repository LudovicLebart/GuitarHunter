"""Schémas de la fiche « Diagnostiquer un talon ou une éclisse qui se décolle ».

    python docs/fiches/_banque/build_diagnostic_joint_manche.py
Écrit les .svg dans docs/fiches/img/diagnostiquer-joint-manche-caisse/.
Schémas simplifiés (proportions non respectées), construction d'acoustique à manche en queue d'aronde.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit import C, bon_mauvais, boite, fleche, repere, svg, texte  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img", "diagnostiquer-joint-manche-caisse")
BLOC = "#e5c98f"


def ecrire(nom, contenu):
    os.makedirs(IMG, exist_ok=True)
    with open(os.path.join(IMG, nom), "w", encoding="utf-8", newline="\n") as f:
        f.write(contenu)
    print("écrit :", nom)


def rect(x, y, w, h, fill, stroke=None, sw=2, extra=""):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{s}{extra}/>'


def pastille(n, x, y):
    return repere(n, x, y, couleur=C["alerte"])


# 01 Les six joints ----------------------------------------------------------------------------------------------------
def schema_01():
    p = []
    # Panneau A : coupe longitudinale (manche à gauche, table en haut, dos en bas)
    p.append(texte(210, 34, "A. Coupe dans l'axe de la guitare", 16, C["texte"], True, "middle"))
    p.append(rect(20, 95, 120, 40, C["manche"], C["trait"]))                       # manche
    p.append(rect(100, 95, 40, 205, C["manche"], C["trait"]))                      # talon
    p.append(rect(140, 120, 70, 170, BLOC, C["bois_trait"]))                       # bloc
    p.append(rect(140, 110, 250, 10, C["bois"], C["bois_trait"]))                  # table
    p.append(rect(140, 290, 250, 10, C["bois"], C["bois_trait"]))                  # dos
    p.append(f'<polygon points="140,140 195,150 195,215 140,225" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>')
    p.append(texte(272, 205, "caisse vide", 14, C["texte_doux"], False, "middle"))
    p.append(pastille(1, 168, 183))
    p.append(pastille(2, 250, 100))
    p.append(pastille(3, 250, 316))
    p.append(pastille(4, 122, 260))
    p.append(texte(155, 142, "queue d'aronde", 13, C["texte_doux"]))
    # Panneau B : coupe horizontale (vue de dessus)
    p.append(texte(615, 34, "B. Coupe horizontale, vue de dessus", 16, C["texte"], True, "middle"))
    p.append(rect(380, 150, 90, 70, C["manche"], C["trait"]))                      # manche
    p.append(rect(470, 120, 50, 130, C["manche"], C["trait"]))                     # talon
    p.append(rect(520, 120, 70, 130, BLOC, C["bois_trait"]))                       # bloc
    p.append(rect(470, 108, 320, 12, C["bois"], C["bois_trait"]))                  # éclisse haut
    p.append(rect(470, 250, 320, 12, C["bois"], C["bois_trait"]))                  # éclisse bas
    p.append(f'<polygon points="520,140 575,148 575,222 520,230" fill="none" stroke="{C["trait"]}" stroke-width="2" stroke-dasharray="5 4"/>')
    p.append(texte(690, 192, "caisse vide", 14, C["texte_doux"], False, "middle"))
    p.append(pastille(5, 495, 100))
    p.append(pastille(6, 555, 100))
    p.append(pastille(5, 495, 270))
    p.append(pastille(6, 555, 270))
    # Légende
    leg = [(1, "queue d'aronde / bloc"), (2, "bloc / table"), (3, "bloc / dos"),
           (4, "talon / bloc"), (5, "talon / éclisse"), (6, "bloc / éclisse")]
    for i, (n, t) in enumerate(leg):
        x = 40 + (i // 3) * 270
        y = 350 + (i % 3) * 32
        p.append(repere(n, x, y, t, C["alerte"]))
    p.append(texte(560, 358, "Chaque numéro est un joint collé", 14, C["texte_doux"]))
    p.append(texte(560, 378, "qui peut lâcher. Lequel ?", 14, C["texte_doux"]))
    p.append(texte(560, 410, "Schéma simplifié, hors proportions.", 13, C["texte_doux"]))
    ecrire("01-les-six-joints.svg", svg(820, 440, "Les six joints possibles d'un talon qui se décolle",
        "Deux coupes simplifiées d'une guitare acoustique : dans l'axe et vue de dessus. Six joints numérotés : queue d'aronde et bloc, bloc et table, bloc et dos, talon et bloc, talon et éclisse, bloc et éclisse.", "\n  ".join(p)))


# 02 Témoins au crayon ------------------------------------------------------------------------------------------------
def joint(x, decalage):
    s = [rect(x, 110, 110, 150, C["bois"], C["bois_trait"]), rect(x + 130, 110, 110, 150, BLOC, C["bois_trait"]),
         rect(x + 110, 110, 20, 150, C["fond"], None)]
    s.append(f'<line x1="{x + 110}" y1="110" x2="{x + 110}" y2="260" stroke="{C["trait"]}" stroke-width="2"/>')
    s.append(f'<line x1="{x + 130}" y1="110" x2="{x + 130}" y2="260" stroke="{C["trait"]}" stroke-width="2"/>')
    s.append(f'<line x1="{x + 30}" y1="185" x2="{x + 110}" y2="185" stroke="{C["noir"]}" stroke-width="4"/>')
    s.append(f'<line x1="{x + 130}" y1="{185 + decalage}" x2="{x + 210}" y2="{185 + decalage}" stroke="{C["noir"]}" stroke-width="4"/>')
    return "".join(s)


def schema_02():
    p = [texte(150, 34, "Cordes détendues (référence)", 16, C["texte"], True, "middle"),
         texte(550, 34, "Accordé un ton plus bas, 10 à 15 min", 16, C["texte"], True, "middle")]
    p.append(joint(30, 0))
    p.append(joint(430, 26))
    p.append(texte(150, 285, "Le trait traverse le joint sans cassure", 14, C["texte_doux"], False, "middle"))
    p.append(texte(550, 285, "Le trait est cassé : ce joint travaille", 14, C["texte_doux"], False, "middle"))
    p.append(bon_mauvais(150, 325, True))
    p.append(bon_mauvais(550, 325, False))
    p.append(fleche(620, 187, 620, 210, C["alerte"], 3))
    p.append(texte(640, 205, "décalage", 13, C["alerte"], True))
    p.append(texte(410, 365, "Même trait, même endroit, même distance de l'appareil photo, avec une règle dans le cadre.", 14, C["texte_doux"], False, "middle"))
    ecrire("02-temoins-au-crayon.svg", svg(820, 390, "Témoins au crayon sur un joint",
        "À gauche, un trait de crayon traverse un joint sans cassure (cordes détendues). À droite, après un accordage plus bas, le trait est décalé de part et d'autre du joint : ce joint travaille.", "\n  ".join(p)))


# 03 Cales d'épaisseur aux trois hauteurs --------------------------------------------------------------------------
def schema_03():
    p = [texte(410, 34, "Mesurer le jour du joint talon / éclisse à trois hauteurs", 16, C["texte"], True, "middle")]
    # talon à gauche (manche), éclisse à droite, jour en coin plus large vers le bas (côté dos)
    p.append(rect(150, 70, 190, 260, C["manche"], C["trait"]))
    p.append(f'<polygon points="342,70 562,70 562,330 372,330" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>')
    p.append(texte(245, 200, "talon", 15, "#fff", True, "middle"))
    p.append(texte(467, 200, "éclisse", 15, C["bois_trait"], True, "middle"))
    for n, y, jour in ((1, 100, "0,2 mm"), (2, 200, "0,6 mm"), (3, 300, "1,1 mm")):
        p.append(f'<line x1="570" y1="{y}" x2="602" y2="{y}" stroke="{C["trait"]}" stroke-width="2" stroke-dasharray="4 4"/>')
        p.append(repere(n, 625, y))
    p.append(texte(60, 110, "côté table", 14, C["texte_doux"]))
    p.append(texte(60, 210, "milieu", 14, C["texte_doux"]))
    p.append(texte(60, 310, "côté dos", 14, C["texte_doux"]))
    p.append(fleche(115, 120, 115, 295, C["trait"], 2))
    # tableau de lecture
    p.append(texte(660, 105, "Exemple de relevé", 14, C["texte"], True))
    p.append(texte(660, 130, "1 : 0,2 mm", 14, C["texte_doux"]))
    p.append(texte(660, 155, "2 : 0,6 mm", 14, C["texte_doux"]))
    p.append(texte(660, 180, "3 : 1,1 mm", 14, C["texte_doux"]))
    p.append(texte(660, 215, "Plus large côté dos :", 14, C["texte"], True))
    p.append(texte(660, 237, "le manche a basculé.", 14, C["texte_doux"]))
    p.append(texte(660, 270, "Égal partout :", 14, C["texte"], True))
    p.append(texte(660, 292, "translation ou", 14, C["texte_doux"]))
    p.append(texte(660, 312, "bloc arraché.", 14, C["texte_doux"]))
    p.append(texte(410, 365, "Relever à droite et à gauche, cordes détendues puis tendues (ou un ton plus bas).", 14, C["texte_doux"], False, "middle"))
    ecrire("03-cales-aux-trois-hauteurs.svg", svg(820, 390, "Mesurer le jour du joint à trois hauteurs",
        "Vue de côté du joint entre le talon et l'éclisse : un jour en coin, plus large côté dos. Trois points de mesure aux cales d'épaisseur, du côté de la table au côté du dos.", "\n  ".join(p)))


# 04 Arbre de décision ------------------------------------------------------------------------------------------------
def schema_04():
    p = [boite(280, 20, 260, 70, "Test des témoins au crayon", "Un ton plus bas, 10 à 15 min")]
    p.append(fleche(410, 90, 410, 125))
    p.append(boite(280, 125, 260, 70, "Quel trait se casse ?", "Photos avant / après"))
    cases = [
        (20, "Trapèze / bloc", "Queue d'aronde lâche\n(cas A)", "Dépose du manche ou\nconversion en vissé\nAvis du luthier d'abord", C["ko"]),
        (300, "Bloc / dos ou éclisses", "Bloc décollé\n(cas C ou D)", "Recoller le bloc\n(branche 1)\nSerrage à blanc d'abord", C["ok"]),
        (580, "Aucun, jour visible", "Talon / éclisse seul\n(cas B)", "Recoller l'éclisse\net le liseré\n(branche 1)", C["ok"]),
    ]
    for x, titre, sous, action, couleur in cases:
        p.append(fleche(410, 195, x + 110, 245, C["trait"], 2))
        p.append(boite(x, 245, 220, 70, titre, sous, couleur))
        p.append(fleche(x + 110, 315, x + 110, 345, C["trait"], 2))
        p.append(boite(x, 345, 220, 90, "Ensuite", action, couleur))
    p.append(boite(280, 455, 260, 70, "En parallèle : ligne dans la table ?", "Regarder de l'intérieur", C["alerte"]))
    p.append(texte(410, 550, "Fissure confirmée : la réparer avant de retendre les cordes.", 14, C["texte_doux"], False, "middle"))
    ecrire("04-arbre-de-decision.svg", svg(820, 570, "Arbre de décision du diagnostic du joint manche-caisse",
        "Selon le trait de crayon qui se casse sous tension : queue d'aronde lâche, bloc décollé, ou talon et éclisse seuls. Contrôle en parallèle de la table.", "\n  ".join(p)))


if __name__ == "__main__":
    schema_01()
    schema_02()
    schema_03()
    schema_04()
