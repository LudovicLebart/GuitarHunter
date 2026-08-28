"""
Fiche 1 (1 page imprimable) — Protocole Dataset B (docs/management/plans/NECK_RESET_VISION_PLAN.md
§4 étape 2, §5) : réglage de l'angle de manche vissé par cale + prise de photo.

Régénère docs/assets/dataset_b_protocole/fiche1_protocole_cale_photos.pdf. Nécessite reportlab
(`pip install reportlab`). Usage : python3 backend/scripts/dataset_b/generate_fiche1_protocole.py
"""
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem, HRFlowable
)
from reportlab.lib.enums import TA_LEFT

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "assets", "dataset_b_protocole", "fiche1_protocole_cale_photos.pdf")

styles = getSampleStyleSheet()
title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=13.5, spaceAfter=1, textColor=colors.HexColor("#1a1a1a"))
subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#555555"), spaceAfter=4)
h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=10.5, spaceBefore=2, spaceAfter=1, textColor=colors.HexColor("#0b3d91"))
h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=9, spaceBefore=2, spaceAfter=1, textColor=colors.HexColor("#333333"))
body = ParagraphStyle("BodyCustom", parent=styles["Normal"], fontSize=7.9, leading=9.8, alignment=TA_LEFT, spaceAfter=1)
body_small = ParagraphStyle("BodySmall", parent=styles["Normal"], fontSize=7.4, leading=9, textColor=colors.HexColor("#333333"))
warn_style = ParagraphStyle("Warn", parent=styles["Normal"], fontSize=7.6, leading=9.6, textColor=colors.HexColor("#7a1f1f"), backColor=colors.HexColor("#fdf0f0"), borderPadding=4, spaceBefore=2, spaceAfter=1)

doc = SimpleDocTemplate(
    OUT, pagesize=letter,
    topMargin=9 * mm, bottomMargin=8 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
)

story = []
story.append(Paragraph("Guitar Hunter — Dataset B", subtitle_style))
story.append(Paragraph("Protocole : réglage d'angle par cale (manche vissé) + prise de photo", title_style))
story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0b3d91"), spaceAfter=6))

# --- Section A ---
story.append(Paragraph("A. Réglage de l'angle du manche par cale (manche vissé uniquement)", h2))

story.append(Paragraph("<b>Matériel</b> : tournevis cruciforme adapté, cales simples (carton rigide/plastique/placage, ~0,3–1 mm — pas besoin de biseau), pied à coulisse, règle droite longue, ruban de masquage, accordeur, appareil photo/téléphone.", body))

steps_a = [
    "Détendre les 6 cordes (pas besoin de les retirer entièrement) pour limiter la contrainte pendant le démontage.",
    "Mesurer et noter le relief actuel du manche une seule fois en début de séance (capo 1re case, appui dernière frette, jeu à la 7e-8e) — <b>ne plus toucher au truss rod</b> ensuite, pour ne pas confondre son effet avec celui de la cale.",
    "Marquer la position du manche avant retrait (ruban de masquage, pas crayon/cutter sur le vernis) pour le repositionner exactement pareil.",
    "Dévisser les vis du talon (souvent 4), soutenir le manche, le soulever <b>bien droit</b> sans le faire basculer (évite l'éclat de vernis au bord de la poche).",
    "Découper une cale simple, assez grande pour caler <b>une seule extrémité</b> de la poche (pas besoin de couvrir toute la poche).",
    "<b>Position sans ambiguïté</b> : cale à l'extrémité de la poche <b>côté tête</b> → le manche penche vers l'avant, s'enfonce vers la table → l'action <b>augmente</b> → c'est ce qui simule le besoin de neck reset (mécanique confirmée : angle de renversement). Côté corps/chevalet ferait l'effet inverse, pas l'objectif ici.",
    "Reposer le manche, revisser <b>en croix</b> sans forcer — technique anti-usure : revisser à l'envers doucement jusqu'au \"clic\" dans le filet existant avant de visser pour de bon.",
    "Vérifier l'alignement des cordes sur les bords de la touche après remontage (une cale peut décaler le manche latéralement).",
    "Réaccorder, tirer légèrement sur chaque corde et réaccorder 2-3 fois — une mesure prise juste après remontage n'est pas fiable.",
    "Mesurer (fiche 2) puis photographier (sections B et C) avant de passer à la cale suivante. Épaisseur au pied à coulisse arrondie à 0,05 mm (la répétabilité réelle du geste est d'environ ±0,1 mm, ne pas sur-préciser).",
    "<b>En fin de séance</b> : revenir à la configuration initiale (sans cale), remesurer — donne une estimation de l'erreur mesure + remontage.",
]
story.append(ListFlowable(
    [ListItem(Paragraph(s, body), spaceAfter=1.2) for s in steps_a],
    bulletType="1", start=1, leftIndent=16, bulletDedent=16,
))

story.append(Spacer(1, 2))
story.append(Paragraph(
    "<b>ATTENTION</b> — Si une vis résiste anormalement, si un craquement se fait entendre, ou en cas de doute : arrêter et consulter un luthier. "
    "Ce protocole est un test empirique pour la collecte de données, pas un mode opératoire professionnel garanti.",
    warn_style,
))

# --- Section B ---
story.append(Paragraph("B. Prise de photo soignée — 5 vues, à répéter pour CHAQUE configuration de cale", h2))

table_cell = ParagraphStyle("TableCell", parent=styles["Normal"], fontSize=7.3, leading=8.8)
table_cell_b = ParagraphStyle("TableCellB", parent=table_cell, fontName="Helvetica-Bold", textColor=colors.white)
photo_data = [
    [Paragraph("#", table_cell_b), Paragraph("Vue", table_cell_b), Paragraph("Cadrage", table_cell_b)],
    [Paragraph("1", table_cell), Paragraph("Ensemble manche + corps", table_cell), Paragraph("Même cadre, du sillet de tête jusqu'au chevalet, bien frontal.", table_cell)],
    [Paragraph("2", table_cell), Paragraph("Gros plan sillet de chevalet", table_cell), Paragraph("Vue RASANTE (quasi parallèle à la table) — pas de trois-quarts, sinon la hauteur exposée est écrasée.", table_cell)],
    [Paragraph("3", table_cell), Paragraph("Gros plan table derrière le chevalet", table_cell), Paragraph("1 cliché en lumière diffuse + 1 en lumière rasante (torche latérale) — un décollement se voit surtout en rasant.", table_cell)],
    [Paragraph("4", table_cell), Paragraph("Gros plan 12e frette", table_cell), Paragraph("Vue RASANTE dans le plan des frettes (pas perpendiculaire) — sommets des frettes voisines alignés = bon angle.", table_cell)],
    [Paragraph("5", table_cell), Paragraph("Vue de profil (optionnelle, haute valeur)", table_cell), Paragraph("En visée le long du manche depuis la tête.", table_cell)],
]
t = Table(photo_data, colWidths=[7 * mm, 48 * mm, 129 * mm])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3d91")),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fb")]),
    ("TOPPADDING", (0, 0), (-1, -1), 2),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t)
story.append(Spacer(1, 2))

story.append(Paragraph("Conseils pratiques", h3))
tips = [
    "Lumière diffuse (près d'une fenêtre) pour les vues 1/2/4/5 ; lumière rasante en complément pour la vue 3 (voir tableau).",
    "Fond neutre et contrasté, sans motif derrière la guitare.",
    "Perpendiculaire à la table pour la vue 1, RASANT pour les vues 2/4 (voir tableau), volontairement en visée pour la vue 5.",
    "Verrouiller la mise au point sur la zone d'intérêt ; désactiver HDR/mode \"beauté\" (déforme les détails fins comme une corde de 0,3 mm) ; garder les fichiers originaux.",
    "Se rapprocher physiquement plutôt que zoomer ; vérifier que le téléphone ne bascule pas seul sur un objectif grand-angle en gros plan.",
    "1 photo avec un réglet millimétré posé dans le plan du sillet/12e frette par configuration — vérifie l'hypothèse \"corde = étalon\", jamais testée jusqu'ici.",
    "1re photo de chaque série = une \"ardoise\" (papier avec l'identifiant de configuration) — sécurité vu la transcription en un seul lot en fin de séance.",
    "Garder le même appareil et la même distance approximative d'une configuration à l'autre.",
]
story.append(ListFlowable(
    [ListItem(Paragraph(s, body_small), spaceAfter=0.5) for s in tips],
    bulletType="bullet", leftIndent=10, bulletFontSize=6,
))

# --- Section C ---
story.append(Paragraph("C. Photos type annonce — 3 à 5 clichés PAR GUITARE/SÉANCE (pas par configuration)", h2))
story.append(Paragraph(
    "Objectif : simuler une vraie photo de vendeur peu soigné, pour un futur test de bout en bout de la chaîne de mesure automatique — "
    "pas pour \"entraîner\" la localisation : 20-60 photos sur seulement 2 guitares ne suffisent pas à ça (avis convergent de 2 revues externes), "
    "et l'entraînement/la calibration de la localisation ont surtout besoin d'annotations visuelles sur des photos variées (prévu séparément sur "
    "Dataset A, pas ici). Reproduire si possible le cadrage de vraies annonces (guitare contre un mur/canapé, dans un étui, photo d'écran) plutôt "
    "qu'inventer une \"mauvaise photo\" abstraite. Varier éclairage/angle/cadrage entre les clichés. <b>Une seule série par guitare suffit</b>, pas "
    "à refaire à chaque cale.",
    body,
))

story.append(Spacer(1, 3))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
story.append(Paragraph(
    "Guitar Hunter — Projet R&D neck-reset · docs/management/plans/NECK_RESET_VISION_PLAN.md §4/§5 · "
    "Nommer les fichiers photo avec l'identifiant de configuration (voir Fiche 2) pour l'association ultérieure.",
    ParagraphStyle("Footer", parent=styles["Normal"], fontSize=6.8, textColor=colors.HexColor("#888888"), spaceBefore=3),
))

doc.build(story)
print(f"OK -> {OUT}")
