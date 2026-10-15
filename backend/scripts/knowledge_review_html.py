"""Page de RELECTURE des fiches de la base « univers des guitares » : une page HTML autonome, à ouvrir dans ton
navigateur, qui montre pour chaque fiche de quoi la juger SUR PIÈCES — la fiche, ses sources (liens Wikidata /
Wikipédia / autre), et jusqu'à 4 de TES annonces où elle a été trouvée (photo, titre, prix, lien, extrait de la
description avec le mot déclencheur surligné). Boutons Approuver / Rejeter / Je ne sais pas, note libre, progression
sauvegardée dans le navigateur, export des décisions au format lu par `knowledge_review_apply.py`.

  # sur le serveur (`export DATABASE_URL=...`), lecture seule, 0 $ :
  python -m backend.scripts.knowledge_review_html --out ~/kb_relecture.html --top 100
  # sur ton ordinateur :
  scp ludovic@serveur.tail16b52e.ts.net:~/kb_relecture.html .      # puis ouvrir le fichier dans le navigateur
  # … relire, cliquer, « Exporter » → kb_decisions.txt ; le renvoyer sur le serveur :
  scp kb_decisions.txt ludovic@serveur.tail16b52e.ts.net:~/
  python -m backend.scripts.knowledge_review_apply ~/kb_decisions.txt --dry-run      # puis sans --dry-run

⚠️ La page contient des titres, liens et photos de TES annonces : ne jamais la versionner (dépôt GitHub public) ni la
publier. Elle reste sur le serveur et sur ton ordinateur.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata

from backend.scripts import knowledge_gate_report as rep

SNIPPET_CHARS = 280


def _fold(text):
    """Minuscules sans accents, MÊME longueur que le texte (un caractère -> un caractère) pour garder les positions."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFKD", ch)[:1] or ch
        out.append(base.lower() if base.isalnum() or base.isspace() else " ")
    return "".join(out)


def snippet_around(text, alias, width=SNIPPET_CHARS):
    """Extrait de `text` autour de `alias` : {before, hit, after}. Sans correspondance : début du texte, `hit` vide."""
    text = " ".join((text or "").split())
    tokens = [t for t in re.split(r"\s+", _fold(alias or "").strip()) if t]
    if tokens:
        pattern = r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(re.escape(t) for t in tokens) + r"(?![a-z0-9])"
        m = re.search(pattern, _fold(text))
        if m:
            start = max(0, m.start() - width // 2)
            end = min(len(text), m.end() + width // 2)
            return {"before": ("…" if start else "") + text[start:m.start()], "hit": text[m.start():m.end()],
                    "after": text[m.end():end] + ("…" if end < len(text) else "")}
    return {"before": text[:width] + ("…" if len(text) > width else ""), "hit": "", "after": ""}


def _image(deal):
    for col in ("storage_image_urls", "image_urls"):
        urls = deal.get(col)
        urls = json.loads(urls) if isinstance(urls, str) else urls
        if urls:
            return urls[0]
    return None


def fetch_sources(conn, ids):
    out = {}
    for r in conn.execute("SELECT knowledge_id, url, kind, title, publisher, excerpt FROM guitar_knowledge_source "
                          "WHERE knowledge_id = ANY(%s) ORDER BY id", (list(ids),)):
        out.setdefault(r["knowledge_id"], []).append(
            {k: r[k] for k in ("url", "kind", "title", "publisher", "excerpt")})
    return out


def build_cards(chosen, hits, examples, sources):
    """Données de la page (fonction pure) : une carte par fiche."""
    cards = []
    for f in chosen:
        listings = []
        for ex in examples.get(f["id"], []):
            d = ex["deal"]
            listings.append({"title": d.get("title"), "price": None if d.get("price") is None else str(d["price"]),
                             "link": d.get("link"), "image": _image(d), "alias": ex["alias"], "how": ex["how"],
                             "snippet": snippet_around(d.get("description") or d.get("title") or "", ex["alias"])})
        cards.append({
            "id": f["id"], "name": f["name"], "kind": f["kind"], "n_hits": hits[f["id"]], "relevance": f["relevance"],
            "countries": f.get("countries") or [], "years": rep._years(f), "parent": f.get("parent_name"),
            "description": " ".join((f.get("description") or "").split()), "aliases": (f.get("aliases") or [])[:15],
            "flags": f["hard"] + f["flags"], "sources": sources.get(f["id"], []), "listings": listings})
    return cards


def render_html(cards, generated=None):
    data = json.dumps({"generated": generated or time.strftime("%Y-%m-%d %H:%M"), "fiches": cards},
                      ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data).replace("__EXPORT_JS__", EXPORT_JS)


# La fonction d'export est isolée : elle est testée sous node contre `parse_sheet` (même format que la feuille texte).
EXPORT_JS = r"""function exportText(fiches, state) {
  let out = '';
  fiches.forEach((f, i) => {
    const s = state[f.id];
    if (s && (s.d === 'A' || s.d === 'R')) {
      const note = (s.note || '').replace(/\s+/g, ' ').trim();
      out += '#' + (i + 1) + '  ' + f.id + '  |  ' + f.name + '  (' + f.kind + ')\nDECISION: ' + s.d + (note ? ' ' + note : '') + '\n\n';
    }
  });
  return out;
}"""

PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relecture des fiches</title>
<style>
:root{--bg:#f6f6f4;--card:#fff;--fg:#1d1d1b;--mut:#6b6b66;--line:#ddddd6;--ok:#1a7f45;--ko:#b3261e;--hit:#ffe58a;--acc:#2a5db0}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--card:#21211e;--fg:#ecece6;--mut:#9a9a92;--line:#37372f;--hit:#6b5a12;--acc:#8ab4f8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
header b{font-size:16px}.sp{flex:1}
main{max-width:980px;margin:0 auto;padding:12px 16px 80px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:14px 0}
.card.A{border-left:6px solid var(--ok)}.card.R{border-left:6px solid var(--ko)}.card.Q{border-left:6px solid var(--mut)}
h2{margin:0 0 4px;font-size:18px}.mut{color:var(--mut);font-size:13px}
.flags span{display:inline-block;background:#b3261e22;color:var(--ko);border-radius:4px;padding:1px 6px;margin:2px 4px 2px 0;font-size:12px}
.desc{margin:8px 0}.src a{color:var(--acc)}.src li{margin:3px 0}.ex{color:var(--mut);font-style:italic}
.ls{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:10px}
.l{border:1px solid var(--line);border-radius:8px;padding:8px;display:flex;gap:8px}
.l img{width:84px;height:84px;object-fit:cover;border-radius:6px;flex:none;background:var(--line)}
.l a{color:var(--acc);word-break:break-word}.l mark{background:var(--hit);color:inherit;border-radius:3px;padding:0 2px}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;align-items:center}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:8px 14px;cursor:pointer}
button.A.on{background:var(--ok);color:#fff}button.R.on{background:var(--ko);color:#fff}button.Q.on{background:var(--mut);color:#fff}
input.note{flex:1;min-width:180px;font:inherit;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg)}
</style></head><body>
<header><b>Relecture des fiches</b><span id="prog" class="mut"></span><span class="sp"></span>
<label class="mut"><input type="checkbox" id="onlyTodo"> à décider seulement</label>
<button id="copy">Copier</button><button id="dl">Exporter kb_decisions.txt</button></header>
<main id="list"></main>
<script>
__EXPORT_JS__
const DATA = __DATA__;
const KEY = 'kbreview:' + DATA.generated;
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function el(tag, props, ...kids) {
  const n = document.createElement(tag);
  Object.entries(props || {}).forEach(([k, v]) => { if (k === 'class') n.className = v; else if (k.startsWith('on')) n[k] = v; else n.setAttribute(k, v); });
  kids.flat().forEach(c => n.append(c && c.nodeType ? c : document.createTextNode(c == null ? '' : c)));
  return n;
}
function listing(l) {
  const s = l.snippet || {};
  const img = l.image ? el('img', {src: l.image, loading: 'lazy', referrerpolicy: 'no-referrer', onerror: function () { this.style.display = 'none'; }}) : '';
  const title = l.link ? el('a', {href: l.link, target: '_blank', rel: 'noopener noreferrer'}, l.title || '(sans titre)') : (l.title || '(sans titre)');
  return el('div', {class: 'l'}, img, el('div', {},
    el('div', {}, title, l.price ? ' — ' + l.price + ' $' : ''),
    el('div', {class: 'mut'}, 'trouvée sur « ' + l.alias + ' » (' + l.how + ')'),
    el('div', {}, s.before, s.hit ? el('mark', {}, s.hit) : '', s.after)));
}
function card(f, i) {
  const st = state[f.id] || {};
  const c = el('div', {class: 'card ' + (st.d === '?' ? 'Q' : st.d || ''), id: 'c' + i});
  const set = d => { state[f.id] = Object.assign(state[f.id] || {}, {d: state[f.id] && state[f.id].d === d ? null : d}); save(); render(); };
  c.append(el('h2', {}, '#' + (i + 1) + ' ' + f.name), el('div', {class: 'mut'},
    f.kind + ' · trouvée dans ' + f.n_hits + ' annonce(s) · pays : ' + (f.countries.join(', ') || 'non renseigné') +
    ' · années : ' + f.years + ' · parent : ' + (f.parent || '—') + ' · pertinence : ' + f.relevance));
  if (f.flags.length) c.append(el('div', {class: 'flags'}, f.flags.map(x => el('span', {}, x))));
  c.append(el('div', {class: 'desc'}, f.description || '(aucune description)'),
    el('div', {class: 'mut'}, 'alias : ' + (f.aliases.join(', ') || '(aucun)')));
  if (f.sources.length) c.append(el('ul', {class: 'src'}, f.sources.map(s => el('li', {},
    el('a', {href: s.url, target: '_blank', rel: 'noopener noreferrer'}, s.title || s.url), ' ',
    el('span', {class: 'mut'}, '(' + (s.publisher || s.kind) + ')'), s.excerpt ? el('div', {class: 'ex'}, '« ' + s.excerpt + ' »') : ''))));
  else c.append(el('div', {class: 'mut'}, 'Aucune source enregistrée.'));
  c.append(el('div', {class: 'ls'}, f.listings.length ? f.listings.map(listing) : el('div', {class: 'mut'}, 'Aucune annonce d’exemple.')));
  const note = el('input', {class: 'note', placeholder: 'Note (facultatif) : pourquoi, la bonne valeur…', value: st.note || ''});
  note.oninput = () => { state[f.id] = Object.assign(state[f.id] || {}, {note: note.value}); save(); };
  c.append(el('div', {class: 'btns'},
    ...[['A', 'Approuver'], ['R', 'Rejeter'], ['?', 'Je ne sais pas']].map(([d, label]) =>
      el('button', {class: (d === '?' ? 'Q' : d) + (st.d === d ? ' on' : ''), onclick: () => set(d)}, label)), note));
  return c;
}
function render() {
  const only = document.getElementById('onlyTodo').checked;
  const list = document.getElementById('list');
  list.replaceChildren(...DATA.fiches.map((f, i) => [f, i]).filter(([f]) => !only || !(state[f.id] && state[f.id].d)).map(([f, i]) => card(f, i)));
  const n = DATA.fiches.filter(f => state[f.id] && state[f.id].d).length;
  const a = DATA.fiches.filter(f => state[f.id] && state[f.id].d === 'A').length;
  const r = DATA.fiches.filter(f => state[f.id] && state[f.id].d === 'R').length;
  document.getElementById('prog').textContent = n + ' / ' + DATA.fiches.length + ' décidées (' + a + ' approuvées, ' + r + ' rejetées)';
}
document.getElementById('onlyTodo').onchange = render;
document.getElementById('copy').onclick = () => navigator.clipboard.writeText(exportText(DATA.fiches, state));
document.getElementById('dl').onclick = () => {
  const url = URL.createObjectURL(new Blob([exportText(DATA.fiches, state)], {type: 'text/plain'}));
  const a = el('a', {href: url, download: 'kb_decisions.txt'}); document.body.append(a); a.click(); a.remove();
};
render();
</script></body></html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="~/kb_relecture.html")
    ap.add_argument("--top", type=int, default=rep.DEFAULT_TOP)
    ap.add_argument("--days", type=int, default=None, help="annonces des N derniers jours seulement")
    ap.add_argument("--max-hits", type=int, default=rep.DEFAULT_MAX_HITS,
                    help="écarte les fiches trouvées dans plus de N annonces (marques géantes) ; 0 = aucune limite")
    args = ap.parse_args(argv)

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        fiches, _ = rep.fetch_fiches(conn)
        examples = {}
        hits, n_deals = rep.hit_counts(conn, args.days, examples=examples)
        pool = rep.review_pool(fiches, hits, args.max_hits)
        chosen = pool[:args.top]
        cards = build_cards(chosen, hits, examples, fetch_sources(conn, [f["id"] for f in chosen]))
    path = os.path.expanduser(args.out)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(cards))
    print(f"Page écrite : {path} ({len(cards)} fiches sur {len(pool)} à relire, {n_deals} annonces examinées).")
    print("Contient des annonces réelles : ne pas la versionner ni la publier.")


if __name__ == "__main__":
    main()
