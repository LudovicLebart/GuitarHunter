import os
import json
import requests
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

from google import genai
from google.genai import types

load_dotenv()

# Initialize the new SDK client
client = genai.Client()

def box_to_yolo(box_1000, img_w, img_h):
    """Convert [ymin, xmin, ymax, xmax] (0-1000) to YOLO."""
    ymin, xmin, ymax, xmax = box_1000
    w = (xmax - xmin) / 1000.0
    h = (ymax - ymin) / 1000.0
    xc = (xmin + xmax) / 2.0 / 1000.0
    yc = (ymin + ymax) / 2.0 / 1000.0
    return xc, yc, w, h

# Load first image
data = None
for line in open("dataset_a_phase0.jsonl"):
    d = json.loads(line)
    if d.get("usable"):
        data = d
        break

print(f"Test on image: {data['image_url']}")
resp = requests.get(data['image_url'])
img = Image.open(BytesIO(resp.content)).convert("RGB")

# Prompt
prompt = """
You are an expert guitar appraiser.
Identify the bounding boxes for the following 5 parts of the guitar in the image:
1. headstock
2. neck (fretboard only, do not include the strings over the soundhole)
3. heel (neck joint where it meets the body)
4. soundhole
5. saddle (bridge)

Return a JSON object with this exact structure, where boxes are [ymin, xmin, ymax, xmax] scaled 0-1000:
{
  "headstock": [ymin, xmin, ymax, xmax],
  "neck": [ymin, xmin, ymax, xmax],
  "heel": [ymin, xmin, ymax, xmax],
  "soundhole": [ymin, xmin, ymax, xmax],
  "saddle": [ymin, xmin, ymax, xmax]
}
If a part is absolutely not visible, omit it from the JSON.
"""

response = client.models.generate_content(
    model='gemini-2.5-pro',
    contents=[img, prompt],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,
    ),
)

print(response.text)

try:
    results = json.loads(response.text)
    from PIL import ImageDraw
    vis = img.copy()
    draw = ImageDraw.Draw(vis)
    w, h = img.size
    for part, boxes in results.items():
        if isinstance(boxes[0], list):
            box = boxes[0]
        else:
            box = boxes
        ymin, xmin, ymax, xmax = box
        xmin = int(xmin * w / 1000)
        ymin = int(ymin * h / 1000)
        xmax = int(xmax * w / 1000)
        ymax = int(ymax * h / 1000)
        draw.rectangle([xmin, ymin, xmax, ymax], outline="red", width=3)
        draw.text((xmin, ymin), part, fill="red")
    vis.save("gemini_genai_test.jpg")
    print("Saved vis to gemini_genai_test.jpg")
except Exception as e:
    print("Error parsing:", e)
