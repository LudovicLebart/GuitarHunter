import os
import json
import argparse
import time
from pathlib import Path
from io import BytesIO
import requests
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

class GuitarFilterResult(BaseModel):
    is_frontal_full_body_acoustic: bool = Field(
        description="True ONLY if the image shows a full acoustic guitar perfectly from the front. The headstock, the entire neck, and the entire body (including the bridge/saddle) MUST all be visible and not cut off. False if it's an electric guitar, a back view, a macro shot, or if parts are cut off."
    )
    reasoning: str = Field(description="Brief explanation of the decision.")

def load_image(url: str, max_size: int = 1024):
    resp = requests.get(url, timeout=10)
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    img.thumbnail((max_size, max_size))
    return img

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=r"backend\scripts\data\dataset_a_manifest.jsonl")
    parser.add_argument("--output", default="dataset_a_frontal.jsonl")
    parser.add_argument("--limit", type=int, default=10000)
    args = parser.parse_args()

    # Load data
    records = []
    with open(args.manifest, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            # Only process those with at least one image url
            if data.get("image_urls") and len(data["image_urls"]) > 0:
                # Expand image_urls into records
                for idx, url in enumerate(data["image_urls"]):
                    record_copy = dict(data)
                    record_copy["image_url"] = url
                    record_copy["image_idx"] = idx
                    records.append(record_copy)

    print(f"Loaded {len(records)} images.")
    
    # Init Gemini client
    # Assumes GEMINI_API_KEY is set in environment
    client = genai.Client()
    
    out_dir = Path("frontal_filter_results")
    out_dir.mkdir(exist_ok=True)
    
    results_file = open(args.output, "w", encoding="utf-8")
    
    kept_count = 0
    t0 = time.time()
    
    for i, record in enumerate(records[:args.limit]):
        url = record["image_url"]
        print(f"\n[{i+1}/{args.limit}] Analyzing {url}")
        
        try:
            img = load_image(url)
        except Exception as e:
            print(f"  -> Error loading image: {e}")
            continue
            
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[img, "Analyze this image of a guitar."],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GuitarFilterResult,
                    temperature=0.0,
                ),
            )
            result = json.loads(response.text)
            print(f"  -> {result['is_frontal_full_body_acoustic']} (Reason: {result['reasoning']})")
            
            # Save visual result
            if result['is_frontal_full_body_acoustic']:
                img.save(out_dir / f"kept_{i}.jpg")
                kept_count += 1
                
                # Write to manifest
                record["gemini_frontal"] = True
                record["gemini_reasoning"] = result["reasoning"]
                results_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                
            else:
                img.save(out_dir / f"rejected_{i}.jpg")
                
        except Exception as e:
            print(f"  -> Gemini API error: {e}")
            # wait a bit in case of quota limit
            time.sleep(2)
            
    results_file.close()
    
    elapsed = time.time() - t0
    print(f"\n--- Done in {elapsed:.1f}s ---")
    print(f"Kept {kept_count}/{args.limit} images as perfect frontal shots.")

if __name__ == "__main__":
    main()
