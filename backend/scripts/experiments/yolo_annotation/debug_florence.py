#!/usr/bin/env python3
"""Debug: tester les différentes tâches Florence-2 sur une seule image."""
import torch, requests, json
from PIL import Image
from io import BytesIO
from transformers import AutoProcessor, AutoModelForCausalLM

model_id = "microsoft/Florence-2-large"
processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_id, trust_remote_code=True
).to("cuda").eval()

# Charger la première image usable
for line in open("dataset_a_phase0.jsonl"):
    d = json.loads(line)
    if d.get("usable"):
        data = d
        break

img = Image.open(BytesIO(requests.get(data["image_url"], timeout=10).content)).convert("RGB")
img.thumbnail((512, 512))
w, h = img.size
print(f"Image: {data['deal_id']}_{data.get('image_idx',0)} ({w}x{h})")
print(f"URL: {data['image_url']}\n")

# Test chaque tâche
tasks = [
    ("<OD>", "<OD>"),
    ("<DENSE_REGION_CAPTION>", "<DENSE_REGION_CAPTION>"),
    ("<CAPTION_TO_PHRASE_GROUNDING>a guitar with a neck, headstock, sound hole, and bridge saddle",
     "<CAPTION_TO_PHRASE_GROUNDING>"),
    ("<OPEN_VOCABULARY_DETECTION>guitar", "<OPEN_VOCABULARY_DETECTION>"),
    ("<OPEN_VOCABULARY_DETECTION>neck", "<OPEN_VOCABULARY_DETECTION>"),
    ("<OPEN_VOCABULARY_DETECTION>headstock", "<OPEN_VOCABULARY_DETECTION>"),
    ("<OPEN_VOCABULARY_DETECTION>sound hole", "<OPEN_VOCABULARY_DETECTION>"),
]

for prompt, task_key in tasks:
    inputs = processor(text=prompt, images=img, return_tensors="pt").to("cuda")
    with torch.no_grad():
        gen = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=3,
        )
    text = processor.batch_decode(gen, skip_special_tokens=False)[0]
    result = processor.post_process_generation(text, task=task_key, image_size=(w, h))
    print(f"Prompt: {prompt[:80]}")
    print(f"  Result: {str(result)[:400]}")
    print()
