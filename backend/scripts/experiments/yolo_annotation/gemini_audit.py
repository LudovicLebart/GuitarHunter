"""
Audit de fiabilité — Gemini comme auto-annotateur de parties de guitare.

Lance Gemini 2.5-flash sur un petit échantillon du dataset_a_frontal.jsonl,
dessine les bounding boxes (saddle/headstock/neck) sur chaque image, et produit
une page HTML d'audit pour inspection visuelle rapide.

Usage (depuis la racine du projet, dans le venv) :
    python backend/scripts/experiments/yolo_annotation/gemini_audit.py
    python backend/scripts/experiments/yolo_annotation/gemini_audit.py --limit 20
    python backend/scripts/experiments/yolo_annotation/gemini_audit.py --limit 50 --output audit_report.html

Dépendances : google-genai, pillow, requests, python-dotenv, pydantic
"""

import os
import json
import base64
import argparse
import html as html_lib
import io
import time
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

load_dotenv()

# ──────────────────────────────────────────────
# Schéma de réponse structurée
# ──────────────────────────────────────────────

class BoundingBox(BaseModel):
    ymin: int = Field(description="Minimum Y coordinate (0-1000, top is 0)")
    xmin: int = Field(description="Minimum X coordinate (0-1000, left is 0)")
    ymax: int = Field(description="Maximum Y coordinate (0-1000, bottom is 1000)")
    xmax: int = Field(description="Maximum X coordinate (0-1000, right is 1000)")


class PartBox(BaseModel):
    visible: bool = Field(description="True if the part is clearly visible in the image")
    box: Optional[BoundingBox] = Field(
        default=None,
        description="Bounding box coordinates, only if visible=True"
    )
    confidence: str = Field(
        default="",
        description="Brief confidence note: 'high', 'medium', or 'low'"
    )


class GuitarAnnotations(BaseModel):
    saddle: PartBox = Field(description="The bridge/saddle assembly (chevalet + sillet de chevalet).")
    headstock: PartBox = Field(description="The headstock (tête de manche) with tuning pegs.")
    neck: PartBox = Field(description="The fretboard/neck (manche + touche), excluding headstock and body.")
    overall_note: str = Field(
        default="",
        description="One short sentence: any issue with the image (occlusion, angle, blur, etc.)"
    )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

COLORS = {
    "saddle":    (220, 50,  50),   # rouge
    "headstock": (50,  180, 50),   # vert
    "neck":      (50,  100, 220),  # bleu
}

PROMPT = """You are analyzing a guitar listing photo to locate its main parts.
Identify and locate:
  - saddle: the bridge assembly (chevalet) — the piece on the guitar body where strings anchor
  - headstock: the headstock (tête) at the top of the neck, with tuning pegs
  - neck: the fretboard/neck (manche), the long part between headstock and body

CRITICAL RULES — read carefully before responding:
1. Set visible=False if the part is cut off, outside the frame, partially visible, or obscured.
   Do NOT guess or extrapolate coordinates for parts you cannot fully see.
2. Set visible=False if you are not sure the part is present — never hallucinate a bounding box.
3. Only set visible=True when the part is FULLY and CLEARLY visible inside the image frame.
4. If visible=True, provide a tight bounding box in 0-1000 coordinates (0,0 = top-left corner).
5. Set confidence to 'high' only if the box is precise; 'medium' if approximate; 'low' if uncertain.
6. In overall_note, describe what is visible (e.g. 'top half only — body and saddle cut off')."""


def load_image(url: str, max_size: int = 1024) -> Image.Image:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    img.thumbnail((max_size, max_size))
    return img


def draw_annotations(img: Image.Image, ann: GuitarAnnotations) -> Image.Image:
    """Retourne une copie de l'image avec les boxes et labels dessinés."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size

    for part_name, part_data in [
        ("saddle", ann.saddle),
        ("headstock", ann.headstock),
        ("neck", ann.neck),
    ]:
        if not part_data.visible or part_data.box is None:
            continue
        box = part_data.box
        x1 = int((box.xmin / 1000.0) * w)
        y1 = int((box.ymin / 1000.0) * h)
        x2 = int((box.xmax / 1000.0) * w)
        y2 = int((box.ymax / 1000.0) * h)
        color = COLORS[part_name]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=4)
        label = f"{part_name} [{part_data.confidence}]"
        tw = len(label) * 7
        draw.rectangle([x1, max(0, y1 - 20), x1 + tw, max(0, y1 - 2)], fill=color)
        draw.text((x1 + 2, max(0, y1 - 18)), label, fill=(255, 255, 255))

    return out


def pil_to_b64_jpeg(img: Image.Image, quality: int = 80) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ──────────────────────────────────────────────
# HTML
# ──────────────────────────────────────────────

HTML_HEADER = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Audit Gemini Auto-Annotateur — Guitar Hunter</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e0e0e8; --muted: #7a7d8a;
    --red: #dc3232; --green: #32c832; --blue: #3264dc; --yellow: #dca032;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; padding: 2rem; }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  .subtitle { color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }
  .summary { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
             padding: 1rem 1.5rem; margin-bottom: 2rem; display: flex; gap: 2rem; flex-wrap: wrap; }
  .stat { font-size: 0.9rem; }
  .stat span { font-size: 1.3rem; font-weight: bold; display: block; }
  .stat .ok  { color: var(--green); }
  .stat .warn{ color: var(--yellow); }
  .stat .err { color: var(--red); }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
          margin-bottom: 1.5rem; overflow: hidden; }
  .card-header { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border);
                 display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
  .card-num { font-weight: bold; color: var(--muted); min-width: 2.5rem; }
  .deal-id { font-family: monospace; font-size: 0.8rem; color: var(--muted); }
  .note { font-size: 0.85rem; color: var(--yellow); flex: 1; }
  .badge { font-size: 0.75rem; padding: 2px 8px; border-radius: 12px; font-weight: bold; }
  .badge-ok  { background: #1a3a1a; color: var(--green); }
  .badge-err { background: #3a1a1a; color: var(--red); }
  .badge-skip{ background: #3a3a1a; color: var(--yellow); }
  .images { display: flex; gap: 0; }
  .images > div { flex: 1; padding: 0.75rem; text-align: center; }
  .images > div:first-child { border-right: 1px solid var(--border); }
  .img-label { font-size: 0.75rem; color: var(--muted); margin-bottom: 0.4rem; }
  .images img { max-width: 100%; border-radius: 6px; }
  .parts { display: flex; gap: 0.5rem; padding: 0.6rem 1rem; border-top: 1px solid var(--border);
           flex-wrap: wrap; align-items: center; }
  .parts-label { font-size: 0.75rem; color: var(--muted); margin-right: 0.25rem; }
  .part { font-size: 0.8rem; padding: 3px 10px; border-radius: 12px; }
  .part-saddle    { background: #3a1010; color: #ff8080; border: 1px solid var(--red); }
  .part-headstock { background: #103a10; color: #80ff80; border: 1px solid var(--green); }
  .part-neck      { background: #10203a; color: #8080ff; border: 1px solid var(--blue); }
  .part-missing   { background: #2a2a2a; color: var(--muted); border: 1px solid var(--border); }
  .error-msg { padding: 1rem; color: var(--red); font-size: 0.85rem; }
</style>
</head>
<body>
<h1>🎸 Audit Gemini Auto-Annotateur</h1>
<p class="subtitle">Évaluation visuelle de la fiabilité des bounding boxes (saddle / headstock / neck)</p>
"""

HTML_FOOTER = "</body></html>\n"


def build_part_badges(ann: GuitarAnnotations) -> str:
    parts_html = '<span class="parts-label">Parties :</span>'
    for name, data in [("saddle", ann.saddle), ("headstock", ann.headstock), ("neck", ann.neck)]:
        if data.visible and data.box is not None:
            parts_html += f'<span class="part part-{name}">{name} ✓ [{data.confidence}]</span>'
        else:
            parts_html += f'<span class="part part-missing">{name} —</span>'
    return parts_html


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Audit Gemini auto-annotateur sur dataset_a_frontal.jsonl")
    parser.add_argument("--manifest", default="dataset_a_frontal.jsonl",
                        help="Chemin du manifest frontal (défaut: dataset_a_frontal.jsonl)")
    parser.add_argument("--limit", type=int, default=20,
                        help="Nombre d'images à auditer (défaut: 20)")
    parser.add_argument("--output", default="gemini_audit_report.html",
                        help="Fichier HTML de sortie (défaut: gemini_audit_report.html)")
    parser.add_argument("--model", default="gemini-2.5-flash",
                        help="Modèle Gemini (défaut: gemini-2.5-flash)")
    args = parser.parse_args()

    # Résoudre le manifest par rapport au script si nécessaire
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        script_dir = Path(__file__).parent
        manifest_path = script_dir / args.manifest
    if not manifest_path.exists():
        print(f"[ERREUR] Manifest introuvable : {args.manifest}")
        return

    print(f"[INFO] Manifest : {manifest_path}")

    records = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
            if len(records) >= args.limit:
                break

    print(f"[INFO] {len(records)} images a traiter (limite: {args.limit})")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERREUR] GEMINI_API_KEY non defini dans l'environnement.")
        return
    client = genai.Client(api_key=api_key)

    # Streaming HTML — ecriture directe dans le fichier, pas d'accumulation en RAM
    n_ok = 0
    n_partial = 0
    n_error = 0
    t_start = time.time()

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as out_f:
        out_f.write(HTML_HEADER)
        out_f.write('<div id="summary-placeholder"></div>\n')

        for i, data in enumerate(records):
            url = data.get("image_url", "")
            deal_id = data.get("deal_id", "?")
            classification = data.get("classification", "")
            print(f"\n[{i+1}/{len(records)}] deal_id={deal_id}")
            print(f"  URL : {url[:80]}")

            card_num_html = f'<span class="card-num">#{i+1}</span>'
            deal_meta_html = f'<span class="deal-id">{html_lib.escape(str(deal_id))}</span>'
            if classification:
                deal_meta_html += f' <span class="deal-id">| {html_lib.escape(str(classification))}</span>'

            # Chargement image
            try:
                pil_img = load_image(url)
            except Exception as e:
                n_error += 1
                print(f"  [ERR] Erreur chargement : {e}")
                out_f.write(f'<div class="card"><div class="card-header">{card_num_html}{deal_meta_html}'
                            f'<span class="badge badge-err">ERREUR CHARGEMENT</span></div>'
                            f'<div class="error-msg">ERR: {html_lib.escape(str(e))}</div></div>\n')
                out_f.flush()
                continue

            orig_b64 = pil_to_b64_jpeg(pil_img)

            # Appel Gemini
            try:
                response = client.models.generate_content(
                    model=args.model,
                    contents=[pil_img, PROMPT],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GuitarAnnotations,
                        temperature=0.0,
                    ),
                )
                ann: GuitarAnnotations = response.parsed
            except Exception as e:
                n_error += 1
                print(f"  [ERR] Erreur Gemini : {e}")
                out_f.write(f'<div class="card"><div class="card-header">{card_num_html}{deal_meta_html}'
                            f'<span class="badge badge-err">ERREUR API</span></div>'
                            f'<div class="images"><div><p class="img-label">Image originale</p>'
                            f'<img src="data:image/jpeg;base64,{orig_b64}" alt="original"></div>'
                            f'<div><p class="img-label">-</p></div></div>'
                            f'<div class="error-msg">ERR: {html_lib.escape(str(e))}</div></div>\n')
                out_f.flush()
                time.sleep(2)
                continue

            # Dessin boxes
            annotated_img = draw_annotations(pil_img, ann)
            ann_b64 = pil_to_b64_jpeg(annotated_img)

            # Stats
            n_visible = sum(1 for p in [ann.saddle, ann.headstock, ann.neck] if p.visible and p.box)
            if n_visible == 3:
                n_ok += 1
                badge = '<span class="badge badge-ok">3/3 OK</span>'
            elif n_visible > 0:
                n_partial += 1
                badge = f'<span class="badge badge-skip">{n_visible}/3 partiel</span>'
            else:
                n_error += 1
                badge = '<span class="badge badge-err">0/3 echec</span>'

            note_html = ""
            if ann.overall_note and ann.overall_note != "-":
                note_html = f'<span class="note">! {html_lib.escape(ann.overall_note)}</span>'

            parts_html = build_part_badges(ann)
            print(f"  [OK] {n_visible}/3 parties | note: {ann.overall_note or '-'}")

            out_f.write(
                f'<div class="card">'
                f'<div class="card-header">{card_num_html}{deal_meta_html}{badge}{note_html}</div>'
                f'<div class="images">'
                f'<div><p class="img-label">Image originale</p>'
                f'<img src="data:image/jpeg;base64,{orig_b64}" alt="original"></div>'
                f'<div><p class="img-label">Annotations Gemini ({args.model})</p>'
                f'<img src="data:image/jpeg;base64,{ann_b64}" alt="annotated"></div>'
                f'</div>'
                f'<div class="parts">{parts_html}</div>'
                f'</div>\n'
            )
            out_f.flush()
            time.sleep(0.5)

        elapsed = time.time() - t_start
        n_total = len(records)

        # Summary injecte via JS (ecrit en fin de fichier apres toutes les cartes)
        out_f.write(
            f'<script>document.getElementById("summary-placeholder").outerHTML='
            f'\'<div class="summary">'
            f'<div class="stat"><span class="ok">{n_ok}</span>3/3 complets</div>'
            f'<div class="stat"><span class="warn">{n_partial}</span>partiels</div>'
            f'<div class="stat"><span class="err">{n_error}</span>erreurs</div>'
            f'<div class="stat"><span>{n_total}</span>images</div>'
            f'<div class="stat"><span>{elapsed:.0f}s</span>duree</div>'
            f'<div class="stat"><span>{args.model}</span>modele</div>'
            f'</div>\';</script>\n'
        )
        out_f.write(HTML_FOOTER)

    print(f"\n{'=' * 60}")
    print(f"[OK] Rapport genere : {output_path.resolve()}")
    print(f"     3/3 complets : {n_ok}/{n_total}  |  partiels : {n_partial}  |  erreurs : {n_error}")
    print(f"     Duree : {elapsed:.0f}s")


if __name__ == "__main__":
    main()


