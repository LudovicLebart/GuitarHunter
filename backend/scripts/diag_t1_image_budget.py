"""Diagnostic (lecture seule, 0 $) : POURQUOI 8 photos font halluciner le Portier local, alors que 4 photos non.

Rejoue UNE annonce sur le Dell en faisant varier un seul facteur à la fois et relève, pour chaque appel, le nombre
de tokens d'entrée réellement comptés par Ollama (`usage.prompt_tokens`) — la mesure qui manquait :
  - nombre de photos N = 1..8 à taille d'origine (2048 px) : où `prompt_tokens` plafonne-t-il (≈ `num_ctx`, donc
    troncature) et à partir de quel N les verdicts / raisonnements deviennent-ils incohérents ?
  - N = 8 avec photos réduites (1536, 1024, 768, 512 px) : si l'incohérence disparaît, c'est un problème de budget
    de tokens — on garde les 8 photos en les réduisant, plutôt que d'en retirer ;
  - N = 8 avec le TEXTE placé APRÈS les images (en prod/rejeu il est placé avant) : si l'incohérence disparaît, c'est
    le texte (consigne + annonce) qui est tronqué quand le contexte déborde.

Ne modifie rien (ni base, ni prod). À lancer sur le serveur, même DATABASE_URL que le bot, Dell allumé :

    export DATABASE_URL="$(grep -h '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | tr -d '\\r')"
    python -m backend.scripts.diag_t1_image_budget --id kijiji_1744378028 --repeat 3

Utilise le prompt Portier PAR DÉFAUT (taxonomie + instruction de prompts.json), pas la configuration utilisateur : si
elle diffère, passer `--instruction-file`. Température 0 + graine 42 (isole l'effet du facteur testé ; le modèle
local n'est quand même pas parfaitement déterministe : d'où --repeat).
"""
import argparse
import base64
import json
import os
import sys
import time
from collections import Counter
from io import BytesIO

import psycopg
from openai import OpenAI
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.scripts.compare_qwen_local_vs_prod import (  # noqa: E402
    ACTIVE_T1_SCHEMA, QWEN_LOCAL_API_KEY, QWEN_LOCAL_BASE_URL, QWEN_LOCAL_MAX_OUTPUT_TOKENS, QWEN_LOCAL_MODEL,
    QWEN_LOCAL_NUM_CTX, _download_and_optimize_image,
)
from backend.t1_prompt import build_t1_gatekeeper_prompt  # noqa: E402
from config import DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_TAXONOMY  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://guitarhunter@localhost/guitarhunter_pg_staging")


def shrink(img, side):
    """Copie réduite de `img` (plus grand côté ≤ `side`), sans toucher l'original."""
    copy = img.copy()
    if max(copy.size) > side:
        copy.thumbnail((side, side))
    return copy


def call(prompt, images, text_last, temperature, seed):
    """Un appel Portier ; renvoie (verdict, raisonnement, tokens d'entrée, tokens de sortie, secondes, erreur)."""
    client = OpenAI(api_key=QWEN_LOCAL_API_KEY, base_url=QWEN_LOCAL_BASE_URL, timeout=180)
    parts = []
    for img in images:
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG")
        parts.append({"type": "image_url",
                      "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}})
    text = {"type": "text", "text": prompt}
    content = parts + [text] if text_last else [text] + parts
    options = {"num_ctx": QWEN_LOCAL_NUM_CTX, "num_predict": QWEN_LOCAL_MAX_OUTPUT_TOKENS}
    if temperature is not None:
        options.update({"temperature": temperature, "seed": seed})
    t0 = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=QWEN_LOCAL_MODEL, messages=[{"role": "user", "content": content}],
            response_format=ACTIVE_T1_SCHEMA, extra_body={"options": options})
        usage = getattr(response, "usage", None)
        result = json.loads(response.choices[0].message.content.strip())
        return ((result.get("status") or "?").upper(), (result.get("reasoning") or "").replace("\n", " "),
                getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None),
                round(time.monotonic() - t0, 1), None)
    except Exception as e:  # diagnostic : on note l'échec et on continue
        return "ERREUR", "", None, None, round(time.monotonic() - t0, 1), str(e)[:120]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="identifiant de l'annonce (ex : kijiji_1744378028)")
    ap.add_argument("--repeat", type=int, default=3, help="appels par configuration (défaut 3)")
    ap.add_argument("--max-n", type=int, default=8, help="nombre maximal de photos testé (défaut 8)")
    ap.add_argument("--sizes", default="1536,1024,768,512",
                    help="tailles (plus grand côté, px) testées avec max-n photos, séparées par des virgules")
    ap.add_argument("--instruction-file", default=None, help="remplace l'instruction Portier par défaut")
    ap.add_argument("--temperature", type=float, default=0.0, help="défaut 0 ; -1 = réglage par défaut du modèle")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    temperature = None if args.temperature < 0 else args.temperature

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        row = conn.execute("SELECT id, title, price, description, location, image_urls, storage_image_urls "
                           "FROM guitar_deals WHERE id = %s", (args.id,)).fetchone()
    if not row:
        raise SystemExit(f"annonce introuvable : {args.id}")
    urls = row.get("storage_image_urls") or row.get("image_urls") or []
    urls = json.loads(urls) if isinstance(urls, str) else urls
    print(f"Annonce « {(row['title'] or '')[:60]} » : {len(urls)} photo(s) en base ; test jusqu'à {args.max_n}.")
    images = [img for url in urls[:args.max_n] if (img := _download_and_optimize_image(url))]
    if len(images) < 2:
        raise SystemExit("moins de 2 photos exploitables : rien à comparer")
    print("Tailles d'origine (px) :", ", ".join(f"{i.size[0]}x{i.size[1]}" for i in images))

    instruction = DEFAULT_GATEKEEPER_INSTRUCTION
    if args.instruction_file:
        with open(args.instruction_file, encoding="utf-8") as fh:
            instruction = fh.read().strip()
    if isinstance(instruction, list):
        instruction = "\n".join(instruction)
    prompt = build_t1_gatekeeper_prompt(row, DEFAULT_TAXONOMY, instruction)
    print(f"Prompt texte ≈ {len(prompt) // 4} tokens (estimation) ; num_ctx demandé = {QWEN_LOCAL_NUM_CTX}\n")

    n_max = len(images)
    configs = [(f"N={n} photos, taille d'origine", images[:n], False) for n in range(0, n_max + 1)]
    for side in [int(s) for s in args.sizes.split(",") if s.strip()]:
        configs.append((f"N={n_max} photos réduites à {side}px", [shrink(i, side) for i in images], False))
    configs.append((f"N={n_max} photos, texte placé APRÈS les images", images, True))

    print(f"{'configuration':<44} {'tokens entrée':<16} {'verdicts':<46} {'s':>5}")
    for label, imgs, text_last in configs:
        runs = [call(prompt, imgs, text_last, temperature, args.seed) for _ in range(args.repeat)]
        tokens = sorted({r[2] for r in runs if r[2] is not None})
        verdicts = ", ".join(f"{v}×{n}" for v, n in Counter(r[0] for r in runs).most_common())
        mean_s = round(sum(r[4] for r in runs) / len(runs), 1)
        print(f"{label:<44} {','.join(map(str, tokens)) or '?':<16} {verdicts:<46} {mean_s:>5}")
        print(f"     ex. raisonnement : {runs[0][1][:150] or runs[0][5]}")


if __name__ == "__main__":
    main()
