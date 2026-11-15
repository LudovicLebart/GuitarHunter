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


# 01 Les joints autour du talon ---------------------------------------------------------------------------------------
def schema_01():
    p = []
    # Panneau A : coupe dans l'axe (manche à gauche, table en haut, dos en bas). L'éclisse passe entre talon et bloc.
    p.append(texte(210, 34, "A. Coupe dans l'axe de la guitare", 16, C["texte"], True, "middle"))
    p.append(rect(20, 110, 80, 30, C["manche"], C["trait"]))                       # manche
    p.append(rect(100, 110, 40, 190, C["manche"], C["trait"]))                     # talon
    p.append(rect(140, 110, 250, 10, C["bois"], C["bois_trait"]))                  # table
    p.append(rect(140, 290, 250, 10, C["bois"], C["bois_trait"]))                  # dos
    p.append(rect(140, 120, 20, 170, C["bois"], C["bois_trait"]))                  # éclisse (entre talon et bloc)
    p.append(rect(160, 120, 70, 170, BLOC, C["bois_trait"]))                       # bloc
    p.append(f'<polygon points="140,150 215,145 215,215 140,210" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>')  # tenon
    p.append(rect(20, 95, 260, 15, C["noir"], C["trait"]))                         # touche + rallonge sur la table
    p.append(texte(60, 107, "touche", 12, "#fff", True, "middle"))
    p.append(texte(305, 205, "caisse vide", 14, C["texte_doux"], False, "middle"))
    p.append(texte(185, 188, "tenon", 13, "#fff", True, "middle"))
    p.append(pastille(1, 190, 165))
    p.append(pastille(2, 195, 120))
    p.append(pastille(3, 195, 290))
    p.append(pastille(4, 262, 110))
    p.append(pastille(5, 140, 248))
    p.append(pastille(6, 160, 272))
    # Panneau B : coupe horizontale (vue de dessus). Tenon évasé : étroit à la racine, large dans le bloc.
    p.append(texte(615, 34, "B. Coupe horizontale, vue de dessus", 16, C["texte"], True, "middle"))
    p.append(rect(380, 150, 70, 70, C["manche"], C["trait"]))                      # manche
    p.append(rect(450, 120, 40, 130, C["manche"], C["trait"]))                     # talon
    p.append(rect(490, 120, 20, 130, C["bois"], C["bois_trait"]))                  # éclisse
    p.append(rect(510, 120, 70, 130, BLOC, C["bois_trait"]))                       # bloc
    p.append(rect(490, 108, 300, 12, C["bois"], C["bois_trait"]))                  # éclisse haut
    p.append(rect(490, 250, 300, 12, C["bois"], C["bois_trait"]))                  # éclisse bas
    p.append(f'<polygon points="490,168 570,145 570,225 490,202" fill="{C["manche"]}" stroke="{C["trait"]}" stroke-width="2"/>')
    p.append(texte(530, 191, "tenon", 13, "#fff", True, "middle"))
    p.append(texte(690, 192, "caisse vide", 14, C["texte_doux"], False, "middle"))
    p.append(pastille(1, 530, 152))
    p.append(pastille(5, 490, 130))
    p.append(pastille(6, 510, 240))
    # Légende
    leg = [(1, "tenon (queue d'aronde) / bloc"), (2, "bloc / table"), (3, "bloc / dos"),
           (4, "rallonge de touche / table"), (5, "talon / éclisse"), (6, "bloc / éclisse")]
    for i, (n, t) in enumerate(leg):
        x = 40 + (i // 3) * 300
        y = 350 + (i % 3) * 32
        p.append(repere(n, x, y, t, C["alerte"]))
    p.append(texte(640, 358, "Chaque numéro est", 14, C["texte_doux"]))
    p.append(texte(640, 378, "un joint collé qui", 14, C["texte_doux"]))
    p.append(texte(640, 398, "peut lâcher.", 14, C["texte_doux"]))
    p.append(texte(410, 445, "Le joint dos / éclisse près du talon peut aussi lâcher. Schéma simplifié, hors proportions.", 13, C["texte_doux"], False, "middle"))
    ecrire("01-les-six-joints.svg", svg(820, 465, "Les joints autour du talon d'une acoustique",
        "Deux coupes simplifiées d'une guitare acoustique à manche en queue d'aronde, dans l'axe et vue de dessus. L'éclisse passe entre le talon et le bloc, traversée par le tenon. Six joints numérotés : tenon et bloc, bloc et table, bloc et dos, rallonge de touche et table, talon et éclisse, bloc et éclisse.", "\n  ".join(p)))


# 02 Témoins au crayon ------------------------------------------------------------------------------------------------
def joint(x, decalage):
    s = [rect(x, 110, 110, 150, C["manche"], C["trait"]), rect(x + 130, 110, 110, 150, C["bois"], C["bois_trait"])]
    s.append(texte(x + 55, 135, "talon", 14, "#fff", True, "middle"))
    s.append(texte(x + 185, 135, "éclisse", 14, C["bois_trait"], True, "middle"))
    s.append(f'<line x1="{x + 30}" y1="185" x2="{x + 110}" y2="185" stroke="#fff" stroke-width="4"/>')
    s.append(f'<line x1="{x + 130}" y1="{185 + decalage}" x2="{x + 210}" y2="{185 + decalage}" stroke="{C["noir"]}" stroke-width="4"/>')
    return "".join(s)


def schema_02():
    p = [texte(150, 34, "Cordes détendues (référence)", 16, C["texte"], True, "middle"),
         texte(550, 34, "Accordé un ton plus bas, 10 à 15 min", 16, C["texte"], True, "middle")]
    p.append(joint(30, 0))
    p.append(joint(430, 26))
    p.append(texte(150, 285, "Le trait reste aligné de part et d'autre", 14, C["texte_doux"], False, "middle"))
    p.append(texte(550, 285, "Le trait est décalé : ce joint travaille", 14, C["texte_doux"], False, "middle"))
    p.append(bon_mauvais(150, 325, True))
    p.append(bon_mauvais(550, 325, False))
    p.append(fleche(620, 187, 620, 210, C["alerte"], 3))
    p.append(texte(640, 205, "décalage", 13, C["alerte"], True))
    p.append(texte(410, 370, "Même trait, même endroit, même distance de l'appareil photo, avec une règle dans le cadre.", 14, C["texte_doux"], False, "middle"))
    p.append(texte(410, 394, "Sur un fini noir : crayon gras blanc, ou deux bandes de ruban de masquage portant le même trait.", 14, C["texte_doux"], False, "middle"))
    ecrire("02-temoins-au-crayon.svg", svg(820, 415, "Témoins au crayon sur un joint",
        "À gauche, un trait traverse le joint talon/éclisse et reste aligné (cordes détendues). À droite, après un accordage plus bas, le trait est décalé de part et d'autre du joint : ce joint travaille.", "\n  ".join(p)))


# 03 Cales d'épaisseur aux trois hauteurs --------------------------------------------------------------------------
def schema_03():
    p = [texte(410, 34, "Mesurer le jour du joint talon / éclisse à trois hauteurs", 16, C["texte"], True, "middle")]
    # talon à gauche (manche), éclisse à droite, jour en coin plus large vers le bas (côté dos)
    p.append(rect(150, 70, 190, 260, C["manche"], C["trait"]))
    p.append(f'<polygon points="342,70 562,70 562,330 372,330" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>')
    p.append(texte(245, 200, "talon", 15, "#fff", True, "middle"))
    p.append(texte(467, 200, "éclisse", 15, C["bois_trait"], True, "middle"))
    for n, y in ((1, 100), (2, 200), (3, 300)):
        p.append(f'<line x1="570" y1="{y}" x2="602" y2="{y}" stroke="{C["trait"]}" stroke-width="2" stroke-dasharray="4 4"/>')
        p.append(repere(n, 625, y))
    p.append(texte(60, 110, "côté table", 14, C["texte_doux"]))
    p.append(texte(60, 210, "milieu", 14, C["texte_doux"]))
    p.append(texte(60, 310, "côté dos", 14, C["texte_doux"]))
    p.append(fleche(115, 120, 115, 295, C["trait"], 2))
    # lecture
    p.append(texte(655, 105, "Exemple de relevé", 14, C["texte"], True))
    p.append(texte(655, 130, "1 : 0,2 mm", 14, C["texte_doux"]))
    p.append(texte(655, 155, "2 : 0,5 mm", 14, C["texte_doux"]))
    p.append(texte(655, 180, "3 : 0,9 mm", 14, C["texte_doux"]))
    p.append(texte(655, 215, "Plus large côté dos :", 14, C["texte"], True))
    p.append(texte(655, 235, "le manche a pu pivoter", 13, C["texte_doux"]))
    p.append(texte(655, 253, "vers l'avant (angle", 13, C["texte_doux"]))
    p.append(texte(655, 271, "refermé), à confirmer.", 13, C["texte_doux"]))
    p.append(texte(655, 305, "Égal partout : piste", 14, C["texte"], True))
    p.append(texte(655, 325, "à vérifier (joint ouvert,", 13, C["texte_doux"]))
    p.append(texte(655, 343, "sec, déplacement).", 13, C["texte_doux"]))
    p.append(texte(410, 370, "Relever à droite et à gauche, pendant la fenêtre de tension de l'étape 5.", 14, C["texte_doux"], False, "middle"))
    ecrire("03-cales-aux-trois-hauteurs.svg", svg(820, 395, "Mesurer le jour du joint à trois hauteurs",
        "Vue de côté du joint entre le talon et l'éclisse : un jour en coin, plus large côté dos. Trois points de mesure aux cales d'épaisseur, du côté de la table au côté du dos.", "\n  ".join(p)))


# 04 Arbre de décision ------------------------------------------------------------------------------------------------
def schema_04():
    p = [boite(280, 20, 260, 70, "Fenêtre de tension (étape 5)", "Témoins, cales, action, règle")]
    p.append(fleche(410, 90, 410, 125))
    p.append(boite(280, 125, 260, 70, "Un trait se casse-t-il ?", "Photos avant / après"))
    # colonnes 1 et 2 : oui, selon le joint
    for x, titre, sous, action, couleur in (
        (15, "Tenon / bloc", "Queue d'aronde lâche", "Dépose du manche ou\nconversion en vissé :\navis du luthier d'abord", C["ko"]),
        (215, "Bloc / dos / éclisses", "Bloc ou dos décollé", "Recoller le bloc ou le\njoint dos/éclisse.\nSerrage à blanc d'abord", C["ok"]),
    ):
        p.append(fleche(410, 195, x + 95, 245, C["trait"], 2))
        p.append(boite(x, 245, 190, 80, titre, sous, couleur))
        p.append(fleche(x + 95, 325, x + 95, 355, C["trait"], 2))
        p.append(boite(x, 355, 190, 100, "Ensuite", action, couleur))
    p.append(texte(275, 232, "oui", 13, C["texte_doux"], True))
    # non : règle sur les frettes
    p.append(fleche(410, 195, 610, 245, C["trait"], 2))
    p.append(texte(560, 222, "non", 13, C["texte_doux"], True))
    p.append(boite(415, 245, 390, 80, "Aucun trait ne casse", "La règle sur les frettes\natterrit-elle trop bas ?"))
    for x, titre, sous in ((415, "Oui : angle refermé", "Refaire l'angle du\nmanche (neck reset)"), (615, "Non : talon / éclisse", "Recoller l'éclisse\net le liseré")):
        p.append(fleche(x + 95, 325, x + 95, 355, C["trait"], 2))
        p.append(boite(x, 355, 190, 100, titre, sous, C["ok"] if x > 600 else C["ko"]))
    p.append(boite(280, 485, 260, 70, "En parallèle : ligne dans la table ?", "Regarder de l'intérieur", C["alerte"]))
    p.append(texte(410, 585, "Fissure confirmée : la réparer avant de retendre les cordes.", 14, C["texte_doux"], False, "middle"))
    ecrire("04-arbre-de-decision.svg", svg(820, 605, "Arbre de décision du diagnostic du joint manche-caisse",
        "Selon le trait qui se casse sous tension : queue d'aronde lâche, bloc ou dos décollé. Sans trait cassé, une règle trop basse sur le chevalet indique un angle de manche refermé ; sinon, talon et éclisse seuls. Contrôle en parallèle de la table.", "\n  ".join(p)))


if __name__ == "__main__":
    schema_01()
    schema_02()
    schema_03()
    schema_04()
