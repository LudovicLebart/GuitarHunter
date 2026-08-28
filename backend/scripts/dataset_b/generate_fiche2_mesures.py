"""
Fiche 2 (1 page imprimable) — Grille de mesures Dataset B, un exemplaire par configuration
(docs/management/plans/NECK_RESET_VISION_PLAN.md §2 pour les métriques, §4 étape 2/§5 pour le contexte).

Régénère docs/assets/dataset_b_protocole/fiche2_grille_mesures.pdf. Nécessite reportlab
(`pip install reportlab`). Usage : python3 backend/scripts/dataset_b/generate_fiche2_mesures.py
"""
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "assets", "dataset_b_protocole", "fiche2_grille_mesures.pdf")

styles = getSampleStyleSheet()
title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=15, spaceAfter=2, textColor=colors.HexColor("#1a1a1a"))
subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#555555"), spaceAfter=8)
h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#0b3d91"))
body_small = ParagraphStyle("BodySmall", parent=styles["Normal"], fontSize=7.6, leading=9.6, textColor=colors.HexColor("#444444"))
cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8.3, leading=10.5, alignment=TA_LEFT)
cell_b = ParagraphStyle("CellBold", parent=cell, fontName="Helvetica-Bold")

doc = SimpleDocTemplate(
    OUT, pagesize=letter,
    topMargin=14 * mm, bottomMargin=12 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
)

story = []
story.append(Paragraph("Guitar Hunter — Dataset B", subtitle_style))
story.append(Paragraph("Grille de mesures — une fiche par configuration", title_style))
story.append(Paragraph(
    "À remplir immédiatement après chaque réglage de cale (ou pour l'état initial), avant de passer à la configuration suivante. "
    "Reporter le même identifiant de configuration sur les fichiers photo correspondants (Fiche 1).",
    body_small,
))
story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0b3d91"), spaceBefore=6, spaceAfter=6))

# --- Identification ---
story.append(Paragraph("Identification", h2))
id_data = [
    [Paragraph("Guitare (nom/description)", cell_b), Paragraph("________________________________________________", cell)],
    [Paragraph("Type de jonction", cell_b), Paragraph("[ ] Manche vissé      [ ] Manche collé", cell)],
    [Paragraph("Identifiant de configuration", cell_b), Paragraph("________________________________________________", cell)],
    [Paragraph("Épaisseur de cale (mm)", cell_b), Paragraph("_______________  Position :  [ ] Fond (talon)   [ ] Avant (touche)   [ ] Sans cale (état initial)", cell)],
    [Paragraph("Date", cell_b), Paragraph("_______________________     Mesureur : ______________________________", cell)],
    [Paragraph("Outil de mesure utilisé", cell_b), Paragraph("________________________________________________", cell)],
]
t_id = Table(id_data, colWidths=[52 * mm, 110 * mm])
t_id.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(t_id)

# --- Mesures ---
story.append(Paragraph("Mesures géométriques", h2))
mesures_data = [
    [Paragraph("Métrique", cell_b), Paragraph("Valeur", cell_b), Paragraph("Unité", cell_b)],
    [Paragraph("Action à la 12e frette — corde Mi grave", cell), Paragraph("_______________", cell), Paragraph("mm", cell)],
    [Paragraph("Action à la 12e frette — corde Mi aigu", cell), Paragraph("_______________", cell), Paragraph("mm", cell)],
    [Paragraph("Diamètre corde Mi grave utilisée (étalon local)", cell), Paragraph("_______________", cell), Paragraph("mm", cell)],
    [Paragraph("Hauteur de sillet de chevalet restante", cell), Paragraph("_______________", cell), Paragraph("mm", cell)],
    [Paragraph("Angle du manche (si mesurable — sinon laisser vide)", cell), Paragraph("_______________", cell), Paragraph("degrés", cell), ],
    [Paragraph("Décollement chevalet/table visible ?", cell), Paragraph("[ ] Oui   [ ] Non", cell), Paragraph("—", cell)],
]
t_mes = Table(mesures_data, colWidths=[100 * mm, 40 * mm, 22 * mm])
t_mes.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3d91")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.3),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fb")]),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
]))
story.append(t_mes)

# --- Notes ---
story.append(Paragraph("Notes / état général", h2))
notes_lines = [["_" * 108] for _ in range(6)]
t_notes = Table(notes_lines, colWidths=[162 * mm])
t_notes.setStyle(TableStyle([
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#cccccc")),
    ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
]))
story.append(t_notes)

# --- Photos checklist ---
story.append(Paragraph("Photos prises pour cette configuration", h2))
photo_check = Paragraph(
    "[ ] 1. Ensemble &nbsp;&nbsp; [ ] 2. Sillet de chevalet &nbsp;&nbsp; [ ] 3. Table (chevalet) &nbsp;&nbsp; "
    "[ ] 4. 12e frette &nbsp;&nbsp; [ ] 5. Profil (optionnelle)",
    ParagraphStyle("PhotoCheck", parent=styles["Normal"], fontSize=9, leading=13),
)
story.append(photo_check)

story.append(Spacer(1, 10))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
story.append(Paragraph(
    "Guitar Hunter — Projet R&D neck-reset · docs/management/plans/NECK_RESET_VISION_PLAN.md §2/§4/§5 · "
    "Une fiche = une ligne dans configurations.csv + mesures.csv (backend/scripts/dataset_b/).",
    ParagraphStyle("Footer", parent=styles["Normal"], fontSize=6.8, textColor=colors.HexColor("#888888"), spaceBefore=3),
))

doc.build(story)
print(f"OK -> {OUT}")
