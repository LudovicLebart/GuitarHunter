import os
import json
import base64
from pathlib import Path
from PIL import Image, ImageDraw
import requests
import io
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# We request coordinates from 0-1000 for precision.
class BoundingBox(BaseModel):
    ymin: int = Field(description='Minimum Y coordinate (0-1000, top is 0)')
    xmin: int = Field(description='Minimum X coordinate (0-1000, left is 0)')
    ymax: int = Field(description='Maximum Y coordinate (0-1000, bottom is 1000)')
    xmax: int = Field(description='Maximum X coordinate (0-1000, right is 1000)')

class GuitarAnnotations(BaseModel):
    saddle: BoundingBox = Field(description='The bridge assembly (chevalet).')
    headstock: BoundingBox = Field(description='The headstock (tête) with tuning pegs.')
    neck: BoundingBox = Field(description='The fretboard/neck (manche).')

def load_image(url: str, max_size: int = 1024):
    resp = requests.get(url, timeout=10)
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    img.thumbnail((max_size, max_size))
    return img

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="dataset_a_frontal.jsonl")
    parser.add_argument("--output_dir", default="yolo_dataset")
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    out_dir = Path(args.output_dir)
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    previews_dir = out_dir / "previews"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    previews_dir.mkdir(parents=True, exist_ok=True)

    records = []
    if os.path.exists(args.manifest):
        with open(args.manifest, "r", encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
                if args.limit and len(records) >= args.limit:
                    break

    prompt = '''Locate the bridge assembly (chevalet), headstock (tête), and fretboard/neck (manche) of the guitar.
Return the coordinates as values between 0 and 1000, where 0,0 is top-left and 1000,1000 is bottom-right.'''

    for i, data in enumerate(records):
        img_url = data["image_url"]
        img_id = f"img_{i:04d}"
        print(f"[{i+1}/{len(records)}] Analyzing {img_url}")

        try:
            pil_img = load_image(img_url)
            w, h = pil_img.size
            pil_img.save(images_dir / f"{img_id}.jpg")

            response = client.models.generate_content(
                model='gemini-2.5-pro',
                contents=[pil_img, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=GuitarAnnotations,
                ),
            )

            ann = response.parsed
            
            draw = ImageDraw.Draw(pil_img)
            yolo_lines = []
            
            # YOLO classes: 0: saddle, 1: headstock, 2: neck
            for cls_id, part, box in [(0, 'saddle', ann.saddle), (1, 'headstock', ann.headstock), (2, 'neck', ann.neck)]:
                # Convert 0-1000 back to absolute pixels
                x1 = (box.xmin / 1000.0) * w
                y1 = (box.ymin / 1000.0) * h
                x2 = (box.xmax / 1000.0) * w
                y2 = (box.ymax / 1000.0) * h
                
                # YOLO format: xc, yc, bw, bh (normalized to 0-1)
                xc = ((x1 + x2) / 2) / w
                yc = ((y1 + y2) / 2) / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                yolo_lines.append(f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")
                
                color = {0: "red", 1: "green", 2: "blue"}[cls_id]
                draw.rectangle([x1, y1, x2, y2], outline=color, width=4)
                draw.text((x1, max(0, y1 - 15)), part, fill=color)

            with open(labels_dir / f"{img_id}.txt", "w") as f:
                f.writelines(yolo_lines)
            
            pil_img.save(previews_dir / f"{img_id}_preview.jpg")
            print(f"Saved {img_id}.txt and preview.")

        except Exception as e:
            print(f"Error processing {img_url}: {e}")

if __name__ == "__main__":
    main()
