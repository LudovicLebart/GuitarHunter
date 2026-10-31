"""Page d'examen À L'AVEUGLE des annonces où Gemini et Sonnet divergent (suite de `replay_t3.py`).

Pour chaque annonce divergente : les photos, puis deux réponses anonymes A/B (ordre tiré au hasard). L'utilisateur
juge l'IDENTIFICATION et les DÉFAUTS visibles, jamais les prix. Les choix sont enregistrés dans le navigateur et
s'exportent en JSON ; `--score <export.json>` les dépouille avec la clé (fichier séparé, jamais montré).

  python -m backend.scripts.replay_t3_blind                         # écrit data/t3_replay_blind.html + _key.json
  python -m backend.scripts.replay_t3_blind --score export.json     # dépouille l'export

Lecture seule de la base (titres, prix, photos). Les fichiers produits contiennent des annonces : locaux, dans
`.gitignore` (`t3_replay*`), JAMAIS versionnés (dépôt public).
"""
import argparse
import base64
import html
import io
import json
import os
import random
import sys
import urllib.request

from backend.scripts.replay_t3 import DATA_DIR, JUDGED_FIELDS, MODELS, image_url_lists

DEFAULT_IN = os.path.join(DATA_DIR, "t3_replay.jsonl")
DEFAULT_PAGE = os.path.join(DATA_DIR, "t3_replay_blind.html")
DEFAULT_KEY = os.path.join(DATA_DIR, "t3_replay_blind_key.json")
VALUE_GAP = 0.4  # écart relatif de valeur à partir duquel deux réponses sont jugées divergentes
QUESTIONS = (("ident", "Quelle réponse a bien identifié la guitare (marque, modèle) ?"),
             ("defauts", "Laquelle a vu les vrais défauts, sans en inventer ?"),
             ("global", "Au total, laquelle vous semble la plus fiable ?"))


def first_result(row, model):
    return next((x["result"] for x in row["runs"][model] if x["result"]), None)


def diverges(row):
    """Verdict ou marque différents, ou valeur estimée à plus de 40 % d'écart (sur la 1re réponse de chaque modèle)."""
    g, c = first_result(row, "gemini"), first_result(row, "claude")
    if not g or not c:
        return False
    if g.get("verdict") != c.get("verdict"):
        return True
    a, b = g.get("estimated_value"), c.get("estimated_value")
    return bool(a and b and abs(a - b) / max(a, b) > VALUE_GAP)


def answer_html(result):
    parts = []
    for field in JUDGED_FIELDS:
        value = result.get(field)
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        parts.append(f"<dt>{html.escape(field)}</dt><dd>{html.escape(str(value))}</dd>")
    return "<dl>" + "".join(parts) + "</dl>"


def inline_image(url, max_edge=900):
    """Photo téléchargée et incrustée (data URI, réduite) : la page reste lisible dans une visionneuse de pièce jointe
    sans réseau. Repli sur l'URL d'origine si le téléchargement échoue."""
    try:
        from PIL import Image
        with urllib.request.urlopen(url, timeout=20) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
        img.thumbnail((max_edge, max_edge))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return url


def card_html(n, deal, answers):
    photos = "".join(f'<img loading="lazy" src="{html.escape(inline_image(u))}">'
                     for u in (image_url_lists(deal) or [[]])[0])
    radios = ""
    for key, text in QUESTIONS:
        opts = "".join(f'<label><input type="radio" name="{key}-{n}" value="{v}" data-id="{deal["id"]}" '
                       f'data-q="{key}">{label}</label>'
                       for v, label in (("A", "A"), ("B", "B"), ("egal", "Égal"), ("aucun", "Aucune")))
        radios += f'<div class="q"><p>{html.escape(text)}</p><div class="opts">{opts}</div></div>'
    return f"""<section class="deal" id="d{n}">
<h2>{n}. {html.escape(str(deal.get('title') or ''))}</h2>
<p class="meta">Prix demandé : {html.escape(str(deal.get('price')))} $ · {html.escape(str(deal.get('location') or ''))}</p>
<div class="photos">{photos}</div>
<div class="answers"><div><h3>Réponse A</h3>{answer_html(answers['A'])}</div><div><h3>Réponse B</h3>{answer_html(answers['B'])}</div></div>
{radios}
<textarea data-id="{deal['id']}" data-q="note" placeholder="Note (facultatif) : le défaut réel, l'erreur..."></textarea>
</section>"""


PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Examen à l'aveugle</title><style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1c1c1c;--mut:#666;--line:#ddd;--acc:#1a5fb4}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#aaa;--line:#333;--acc:#78aeed}}
body{margin:0;padding:0 16px 80px;background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,sans-serif;max-width:1100px;margin:auto}
h1{font-size:1.3rem}h2{font-size:1.1rem;margin:.2em 0}h3{font-size:1rem;margin:.3em 0}.meta{color:var(--mut);margin:.2em 0}
.deal{border-top:2px solid var(--line);padding:20px 0}.photos{display:flex;gap:8px;overflow-x:auto;padding:8px 0}
.photos img{height:200px;border-radius:6px;display:block}
.answers{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:700px){.answers{grid-template-columns:1fr}}
.answers>div{border:1px solid var(--line);border-radius:8px;padding:8px 12px;min-width:0}
dl{margin:0}dt{font-weight:600;font-size:.85rem;color:var(--mut);margin-top:6px}dd{margin:0;overflow-wrap:anywhere}
.q{margin:10px 0}.q p{margin:0 0 4px;font-weight:600}.opts{display:flex;flex-wrap:wrap;gap:8px}
.opts label{border:1px solid var(--line);border-radius:20px;padding:8px 16px;cursor:pointer}
.opts label:has(input:checked){background:var(--acc);color:#fff;border-color:var(--acc)}.opts input{display:none}
textarea{width:100%;box-sizing:border-box;min-height:56px;font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--bg);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;align-items:center}
button{font:inherit;padding:10px 18px;border-radius:8px;border:0;background:var(--acc);color:#fff;cursor:pointer}
</style></head><body>
<h1>Examen à l'aveugle — __N__ annonces</h1>
<p class="meta">Regardez les photos, puis comparez A et B. Ne jugez ni les prix ni le style : seulement la bonne identification et les défauts réellement visibles. Vos choix se sauvegardent tout seuls.</p>
__CARDS__
<div class="bar"><span id="count"></span><button id="export">Exporter les réponses</button></div>
<script>
const KEY='t3-blind-v1';let st={};try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}};
document.querySelectorAll('[data-id]').forEach(el=>{const id=el.dataset.id,q=el.dataset.q;
 if(el.type==='radio'){if(st[id]&&st[id][q]===el.value)el.checked=true;
  el.addEventListener('change',()=>{(st[id]=st[id]||{})[q]=el.value;save();count()})}
 else{el.value=(st[id]&&st[id][q])||'';el.addEventListener('input',()=>{(st[id]=st[id]||{})[q]=el.value;save()})}});
function count(){const n=document.querySelectorAll('.deal').length;
 const d=Object.values(st).filter(v=>v.ident&&v.defauts&&v.global).length;document.getElementById('count').textContent=d+' / '+n+' complétées'}
count();
document.getElementById('export').onclick=()=>{const t=JSON.stringify(st,null,1);
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:'application/json'}));a.download='t3_blind_export.json';a.click();
 if(navigator.clipboard)navigator.clipboard.writeText(t).catch(()=>{})};
</script></body></html>"""


# Variante publiée en Artifact privé (téléphone) : mêmes cartes, réponses gardées dans la base de l'artifact (`db`) pour
# que l'assistant les relise sans export ; repli sur le stockage du navigateur si la base est absente.
ARTIFACT_PAGE = """<title>Examen à l'aveugle</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root{--bg:#fbfaf8;--fg:#1d1d1b;--mut:#6a665f;--line:#d9d5cc;--acc:#1b5e8c;--on:#fff;--card:#f2efe9}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#141413;--fg:#ecebe6;--mut:#a09b90;--line:#34322e;--acc:#7ab4dd;--on:#101010;--card:#1e1d1b;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#141413;--fg:#ecebe6;--mut:#a09b90;--line:#34322e;--acc:#7ab4dd;--on:#101010;--card:#1e1d1b;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,sans-serif;max-width:1100px;margin:auto;
 padding-block:12px 96px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:1.3rem;text-wrap:balance}h2{font-size:1.1rem;margin:.2em 0;text-wrap:balance}h3{font-size:1rem;margin:.3em 0}.meta{color:var(--mut);margin:.2em 0}
.deal{border-top:2px solid var(--line);padding:20px 0}.photos{display:flex;gap:8px;overflow-x:auto;padding:8px 0}
.photos img{height:200px;max-width:none;border-radius:6px;display:block}
.answers{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:700px){.answers{grid-template-columns:1fr}}
.answers>div{background:var(--card);border-radius:8px;padding:8px 12px;min-width:0}
dl{margin:0}dt{font-weight:600;font-size:.85rem;color:var(--mut);margin-top:6px}dd{margin:0;overflow-wrap:anywhere}
.q{margin:12px 0}.q p{margin:0 0 6px;font-weight:600}.opts{display:flex;flex-wrap:wrap;gap:8px}
.opts label{border:1px solid var(--line);border-radius:20px;padding:10px 18px;cursor:pointer}
.opts label:has(input:checked){background:var(--acc);color:var(--on);border-color:var(--acc)}.opts input{position:absolute;opacity:0;pointer-events:none}
.opts label:has(input:focus-visible){outline:2px solid var(--acc);outline-offset:2px}
textarea{width:100%;box-sizing:border-box;min-height:56px;font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--bg);border-top:1px solid var(--line);
 padding:10px max(16px,env(safe-area-inset-right,0px)) calc(10px + env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px))}
</style>
<h1>Examen à l'aveugle — __N__ annonces</h1>
<p class="meta">Regardez les photos, puis comparez A et B. Ne jugez ni les prix ni le style : seulement la bonne identification et les défauts réellement visibles. Vos choix s'enregistrent tout seuls.</p>
__CARDS__
<div class="bar"><span id="count"></span> <span id="state" class="meta"></span></div>
<script>
const KEY='t3-blind-v1';let st={},db=null;
const ls={get(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}},set(v){try{localStorage.setItem(KEY,JSON.stringify(v))}catch(e){}}};
const els=[...document.querySelectorAll('[data-id]')];
function paint(){els.forEach(el=>{const v=(st[el.dataset.id]||{})[el.dataset.q];
 if(el.type==='radio')el.checked=(v===el.value);else if(document.activeElement!==el)el.value=v||''});count()}
function count(){const n=document.querySelectorAll('.deal').length;
 const d=Object.values(st).filter(v=>v.ident&&v.defauts&&v.global).length;document.getElementById('count').textContent=d+' / '+n+' complétées'}
function put(id){ls.set(st);if(db){db.doc('blind/'+id).set(st[id]).then(()=>{document.getElementById('state').textContent='enregistré'}).catch(()=>{document.getElementById('state').textContent='sur cet appareil seulement'})}}
els.forEach(el=>{const id=el.dataset.id,q=el.dataset.q;
 el.addEventListener(el.type==='radio'?'change':'input',()=>{(st[id]=st[id]||{})[q]=el.value;put(id);count()})});
st=ls.get();paint();
(async()=>{try{db=await claude.use('db');if(!db)return;
 const snap=await db.collection('blind').get();snap.docs.forEach(d=>{st[d.id]=Object.assign({},st[d.id],d.data())});paint();ls.set(st)}catch(e){}})();
</script>"""


def build(args):
    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...`.")
    with open(args.input, encoding="utf-8") as fh:
        rows = [r for r in map(json.loads, filter(str.strip, fh)) if diverges(r)]
    if not rows:
        sys.exit("Aucune annonce divergente.")
    rng = random.Random(args.seed)
    cards, key = [], {}
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        for n, row in enumerate(rows, 1):
            deal = conn.execute("SELECT id, title, price, location, storage_image_urls, image_urls "
                                "FROM guitar_deals WHERE id = %s", (row["id"],)).fetchone()
            if not deal:
                continue
            a_is = rng.choice(MODELS)
            b_is = MODELS[1] if a_is == MODELS[0] else MODELS[0]
            answers = {"A": first_result(row, a_is), "B": first_result(row, b_is)}
            key[row["id"]] = {"A": a_is, "B": b_is}
            cards.append(card_html(n, deal, answers))
    with open(args.page, "w", encoding="utf-8") as fh:
        fh.write((ARTIFACT_PAGE if args.artifact else PAGE)
                 .replace("__N__", str(len(cards))).replace("__CARDS__", "\n".join(cards)))
    with open(args.key, "w", encoding="utf-8") as fh:
        json.dump(key, fh, ensure_ascii=False, indent=1)
    print(f"{len(cards)} annonces divergentes → {args.page}\nClé (ne pas ouvrir avant d'avoir répondu) : {args.key}")


def score(args):
    with open(args.key, encoding="utf-8") as fh:
        key = json.load(fh)
    with open(args.score, encoding="utf-8") as fh:
        answers = json.load(fh)
    for q, text in QUESTIONS:
        wins = {"gemini": 0, "claude": 0, "egal": 0, "aucun": 0}
        for deal_id, a in answers.items():
            choice = a.get(q)
            if choice in ("A", "B") and deal_id in key:
                wins[key[deal_id][choice]] += 1
            elif choice in wins:
                wins[choice] += 1
        print(f"{text}\n   Sonnet {wins['claude']} | Gemini {wins['gemini']} | égal {wins['egal']} | aucune {wins['aucun']}")
    print(f"\n{len(answers)} annonces répondues.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=DEFAULT_IN)
    ap.add_argument("--page", default=DEFAULT_PAGE)
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--artifact", action="store_true", help="page prête à publier en Artifact (réponses dans sa base)")
    ap.add_argument("--score", default=None, help="export JSON de la page : dépouille les réponses avec la clé")
    args = ap.parse_args(argv)
    score(args) if args.score else build(args)


if __name__ == "__main__":
    main()
