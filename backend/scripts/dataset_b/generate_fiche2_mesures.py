"""
Fiche 2 (1 page imprimable) — Journal de session Dataset B : un tableau dense, une LIGNE par
configuration (pas une page par configuration — trop lourd à recopier ensuite dans le CSV, retour
utilisateur 2026-08-28). Identification de la guitare/session en en-tête (constante sur la feuille),
puis une ligne par configuration testée pendant la séance. Transcription en fin de séance, en un
seul lot, dans configurations.csv + mesures.csv (docs/management/plans/NECK_RESET_VISION_PLAN.md §2
pour les métriques, §4 étape 2/§5 pour le contexte).
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "assets", "dataset_b_protocole", "fiche2_grille_mesures.pdf")

styles = getSampleStyleSheet()
title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=15, spaceAfter=2, textColor=colors.HexColor("#1a1a1a"))
subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#555555"), spaceAfter=6)
h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#0b3d91"))
cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8.3, leading=10.5, alignment=TA_LEFT)
cell_b = ParagraphStyle("CellBold", parent=cell, fontName="Helvetica-Bold")
th = ParagraphStyle("TH", parent=styles["Normal"], fontSize=7, leading=8.3, alignment=TA_CENTER, textColor=colors.white, fontName="Helvetica-Bold")
td = ParagraphStyle("TD", parent=styles["Normal"], fontSize=8, leading=9.5, alignment=TA_CENTER)
legend_style = ParagraphStyle("Legend", parent=styles["Normal"], fontSize=7, leading=9.5, textColor=colors.HexColor("#555555"), spaceBefore=4)

doc = SimpleDocTemplate(
    OUT, pagesize=letter,
    topMargin=12 * mm, bottomMargin=10 * mm, leftMargin=12 * mm, rightMargin=12 * mm,
)

story = []
story.append(Paragraph("Guitar Hunter — Dataset B", subtitle_style))
story.append(Paragraph("Journal de session — une ligne par configuration", title_style))
story.append(Paragraph(
    "Une feuille par guitare/séance. Remplir une ligne à chaque configuration (état initial puis chaque cale), "
    "transcrire tout le tableau en une fois dans configurations.csv + mesures.csv en fin de séance.",
    subtitle_style,
))
story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0b3d91"), spaceAfter=6))

# --- Identification (constante pour la feuille) ---
story.append(Paragraph("Identification (valable pour toute la feuille)", h2))
id_data = [
    [Paragraph("Guitare", cell_b), Paragraph("_______________________________", cell),
     Paragraph("Jonction", cell_b), Paragraph("[ ] Vissé   [ ] Collé", cell)],
    [Paragraph("Date", cell_b), Paragraph("_______________________________", cell),
     Paragraph("Mesureur", cell_b), Paragraph("_______________________________", cell)],
    [Paragraph("Outil de mesure", cell_b), Paragraph("_______________________________", cell),
     Paragraph("Ø corde Mi grave", cell_b), Paragraph("_______________ mm (si constant sur la séance)", cell)],
    [Paragraph("Relief (mesuré 1x, ne plus toucher)", cell_b), Paragraph("_______________ mm", cell),
     Paragraph("Photos type annonce", cell_b), Paragraph("fichiers ______________ à ______________", cell)],
]
t_id = Table(id_data, colWidths=[26 * mm, 60 * mm, 26 * mm, 74 * mm])
t_id.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t_id)

# --- Tableau de session ---
story.append(Paragraph("Configurations testées", h2))

headers = ["Config\n(id court)", "Cale\n(mm)", "Pos.\n(T/C)", "AG\n(mm)", "AA\n(mm)", "Sillet\n(mm)", "Proj.\n(mm)", "Décol.\n(O/N)", "Fichiers\n(plage)"]
header_row = [Paragraph(h.replace("\n", "<br/>"), th) for h in headers]

data = [header_row]
n_rows = 11
for _ in range(n_rows):
    data.append([Paragraph("&nbsp;", td) for _ in headers])

col_widths = [30 * mm, 15 * mm, 13 * mm, 16 * mm, 16 * mm, 16 * mm, 15 * mm, 15 * mm, 20 * mm]
t = Table(data, colWidths=col_widths, rowHeights=[13 * mm] + [8 * mm] * n_rows)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3d91")),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fb")]),
]))
story.append(t)

story.append(Paragraph(
    "<b>AG</b> = action 12e frette corde Mi grave · <b>AA</b> = action 12e frette corde Mi aigu · "
    "<b>Sillet</b> = hauteur de sillet de chevalet restante · <b>Pos.</b> = extrémité calée : <b>T</b>ête (augmente l'action, l'usage prévu de ce protocole) "
    "ou <b>C</b>orps/chevalet (effet inverse), vide si état initial (sans cale) · "
    "<b>Proj. chevalet</b> = règle droite posée sur les frettes, hauteur au-dessus du chevalet (méthode standard luthier), en mm — remplace un angle en degrés, non mesurable simplement · "
    "<b>Décol.</b> = décollement chevalet/table visible · <b>Fichiers</b> = plage de numéros des 5 vues soignées (Fiche 1, section B) pour cette configuration, ex. 231-238 "
    "(les photos type annonce, section C, sont notées une fois par séance en en-tête, pas par ligne).",
    legend_style,
))

story.append(Spacer(1, 8))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
story.append(Paragraph(
    "Guitar Hunter — Projet R&D neck-reset · docs/management/plans/NECK_RESET_VISION_PLAN.md §2/§4/§5 · "
    "Chaque ligne = une ligne dans configurations.csv + mesures.csv (backend/scripts/dataset_b/).",
    ParagraphStyle("Footer", parent=styles["Normal"], fontSize=6.8, textColor=colors.HexColor("#888888"), spaceBefore=3),
))

doc.build(story)
print(f"OK -> {OUT}")
