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
title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=15, spaceAfter=2, textColor=colors.HexColor("#1a1a1a"))
subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#555555"), spaceAfter=8)
h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#0b3d91"))
h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=9.5, spaceBefore=4, spaceAfter=2, textColor=colors.HexColor("#333333"))
body = ParagraphStyle("BodyCustom", parent=styles["Normal"], fontSize=8.3, leading=10.8, alignment=TA_LEFT, spaceAfter=2)
body_small = ParagraphStyle("BodySmall", parent=styles["Normal"], fontSize=7.8, leading=9.8, textColor=colors.HexColor("#333333"))
warn_style = ParagraphStyle("Warn", parent=styles["Normal"], fontSize=8, leading=10.5, textColor=colors.HexColor("#7a1f1f"), backColor=colors.HexColor("#fdf0f0"), borderPadding=5, spaceBefore=4, spaceAfter=2)

doc = SimpleDocTemplate(
    OUT, pagesize=letter,
    topMargin=14 * mm, bottomMargin=12 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
)

story = []
story.append(Paragraph("Guitar Hunter — Dataset B", subtitle_style))
story.append(Paragraph("Protocole : réglage d'angle par cale (manche vissé) + prise de photo", title_style))
story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0b3d91"), spaceAfter=6))

# --- Section A ---
story.append(Paragraph("A. Réglage de l'angle du manche par cale (manche vissé uniquement)", h2))

story.append(Paragraph("<b>Matériel</b> : tournevis cruciforme adapté, cales (carton épais / plastique fin / placage bois, ~0,3–1 mm), pied à coulisse ou règle fine, accordeur, appareil photo/téléphone.", body))

steps_a = [
    "Détendre les 6 cordes (pas besoin de les retirer entièrement, juste relâcher la tension) pour limiter la contrainte pendant le démontage.",
    "Repérer/marquer la position du manche avant retrait (photo des vis en place, ou marque légère au crayon sur le contour de la poche) pour le repositionner exactement pareil ensuite.",
    "Dévisser les vis du talon (souvent 4), en soutenant le manche pour qu'il ne tombe pas à la dernière vis.",
    "Découper la cale à la taille de la poche, sans obstruer les trous de vis ni l'accès à la tige de réglage si elle passe par là.",
    "<b>Choisir la position selon l'effet recherché</b> : cale au fond de la poche (côté talon/corps) → incline la tête vers le bas → augmente l'angle de cassure des cordes sur le chevalet → typiquement augmente l'action. Cale à l'avant (côté touche) → effet inverse.",
    "Reposer le manche, revisser progressivement <b>en croix</b> (pas une vis à fond puis les autres), sans forcer.",
    "Réaccorder, puis tirer légèrement sur chaque corde et réaccorder 2-3 fois — une mesure prise juste après remontage n'est pas fiable (tension pas stabilisée).",
    "Mesurer (fiche 2) puis photographier (section B) <b>avant</b> de passer à la cale suivante.",
    "Noter l'épaisseur <b>exacte</b> de chaque cale (pied à coulisse), pas une estimation qualitative.",
]
story.append(ListFlowable(
    [ListItem(Paragraph(s, body), spaceAfter=2) for s in steps_a],
    bulletType="1", start=1, leftIndent=12,
))

story.append(Paragraph(
    "<b>ATTENTION</b> — Si une vis résiste anormalement, si un craquement se fait entendre, ou en cas de doute : arrêter et consulter un luthier. "
    "Ce protocole est un test empirique pour la collecte de données, pas un mode opératoire professionnel garanti.",
    warn_style,
))

# --- Section B ---
story.append(Paragraph("B. Prise de photo — 5 vues, à répéter pour CHAQUE configuration de cale", h2))

photo_data = [
    ["#", "Vue", "Cadrage"],
    ["1", "Ensemble manche + corps", "Même cadre, du sillet de tête jusqu'au chevalet, bien frontal."],
    ["2", "Gros plan sillet de chevalet", "Zone où les cordes reposent sur le chevalet."],
    ["3", "Gros plan table derrière le chevalet", "Pour repérer un éventuel décollement chevalet/table."],
    ["4", "Gros plan 12e frette", "Cordes bien visibles au-dessus de la frette."],
    ["5", "Vue de profil (optionnelle, haute valeur)", "En visée le long du manche depuis la tête."],
]
t = Table(photo_data, colWidths=[8 * mm, 62 * mm, 92 * mm])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3d91")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTSIZE", (0, 0), (-1, -1), 7.8),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fb")]),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t)
story.append(Spacer(1, 5))

story.append(Paragraph("Conseils pratiques", h3))
tips = [
    "Lumière diffuse (près d'une fenêtre) plutôt qu'un flash direct — évite les reflets durs sur les cordes métalliques.",
    "Fond neutre et contrasté, sans motif derrière la guitare.",
    "Appareil perpendiculaire au sujet (pas d'angle qui déforme), sauf la vue 5 qui est volontairement en visée.",
    "Verrouiller la mise au point sur la zone d'intérêt (toucher l'écran sur le sillet/la frette) plutôt que l'auto large.",
    "Se rapprocher physiquement plutôt que d'utiliser le zoom numérique.",
    "Garder le même appareil et la même distance approximative d'une configuration à l'autre pour rester comparable.",
]
story.append(ListFlowable(
    [ListItem(Paragraph(s, body_small), spaceAfter=1.5) for s in tips],
    bulletType="bullet", leftIndent=10, bulletFontSize=6,
))

story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
story.append(Paragraph(
    "Guitar Hunter — Projet R&D neck-reset · docs/management/plans/NECK_RESET_VISION_PLAN.md §4/§5 · "
    "Nommer les fichiers photo avec l'identifiant de configuration (voir Fiche 2) pour l'association ultérieure.",
    ParagraphStyle("Footer", parent=styles["Normal"], fontSize=6.8, textColor=colors.HexColor("#888888"), spaceBefore=3),
))

doc.build(story)
print(f"OK -> {OUT}")
