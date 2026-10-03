"""Manifeste de crops pour le banc de rejeu « photos entières contre crops » (compare_qwen_local_vs_prod.py).

Format (JSON) : { "<id de l'annonce>": ["chemin/ou/url_du_crop_1.jpg", "…"], … }
Les chemins relatifs sont résolus à partir du dossier du manifeste. Les crops viendront du détecteur de parties une fois
entraîné ; en attendant, un manifeste fait à la main (ou par un script quelconque) suffit à tester le banc.

Module volontairement sans dépendance lourde (pas de psycopg) pour rester testable sur n'importe quel poste.
"""
import json
from io import BytesIO
from pathlib import Path


def load_manifest(path):
    """{id: [spécifications]} — les identifiants sont normalisés en chaînes ; une liste vide ou invalide est écartée."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("le manifeste de crops doit être un objet {id: [crops]}")
    manifest = {}
    for deal_id, specs in data.items():
        if isinstance(specs, list) and specs and all(isinstance(s, str) and s for s in specs):
            manifest[str(deal_id)] = specs
    return manifest


def resolve_spec(spec, base_dir):
    """URL telle quelle, chemin local résolu par rapport au dossier du manifeste."""
    if spec.startswith(("http://", "https://")):
        return spec
    p = Path(spec)
    return str(p if p.is_absolute() else Path(base_dir) / p)


def load_crop_image(spec, base_dir, download=None, max_size=2048):
    """Image PIL d'un crop (chemin local ou URL). `download(url)` fournit l'image pour les URLs ; renvoie None si
    illisible. Même règle de taille que l'analyseur : plafonné à `max_size`, jamais agrandi, converti en RGB."""
    from PIL import Image
    target = resolve_spec(spec, base_dir)
    try:
        if target.startswith(("http://", "https://")):
            return download(target) if download else None
        img = Image.open(BytesIO(Path(target).read_bytes()))
        if img.size[0] > max_size or img.size[1] > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return img.convert("RGB") if img.mode in ("RGBA", "P") else img
    except Exception as e:
        print(f"  ⚠️ Crop illisible ({target}) : {e}")
        return None


def images_for_deal(deal_id, manifest, base_dir, max_crops, download=None):
    """(mode, images) pour une annonce : 'crops' et les images du manifeste (au plus `max_crops`) si l'annonce y est et
    qu'au moins un crop est lisible ; sinon ('full', None) — l'appelant garde alors les photos entières."""
    specs = manifest.get(str(deal_id))
    if not specs:
        return "full", None
    images = [img for spec in specs[:max_crops] if (img := load_crop_image(spec, base_dir, download))]
    return ("crops", images) if images else ("full", None)
