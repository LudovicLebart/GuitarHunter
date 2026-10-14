"""Rejeu de l'Expert (Tier 3) : Gemini 3.1 Pro CONTRE Claude Sonnet 5.5, sur les mêmes annonces, avec le vrai prompt
de production — sans vérité terrain écrite à la main (voir `COST_OPTIMIZATION_CHANTIERS.md` Chantier F).

Question posée : « Sonnet 5.5 fait-il au moins aussi bien que Gemini comme Expert ? » Trois mesures complémentaires :

  1. COHÉRENCE (sans juge) : chaque modèle est appelé `--repeats` fois (2 par défaut) sur la MÊME entrée ; on compare
     ses réponses à elles-mêmes (verdict, marque, classification, écart de score et de valeur). C'est le défaut que
     l'utilisateur reproche à Gemini : des réponses différentes à la même question.
  2. QUALITÉ (juge à l'aveugle) : pour chaque annonce, un juge voit les photos, l'annonce, les affirmations que
     l'UTILISATEUR a écrites dans le chat de l'annonce (ce qu'il a constaté en vrai ou sur de nouvelles photos) et les
     deux réponses anonymisées, ordre tiré au hasard. Il départage par axe : identification, état, valeur,
     hallucination. Les deux modèles servent de juge (un juge favorise souvent son propre style) : seuls les
     désaccords entre juges sont signalés, à regarder à la main — aucune annotation par annonce n'est demandée.
  3. COÛT et LATENCE réels, relevés sur chaque appel.

RÉPONSE GEMINI : réutilisée telle que STOCKÉE en production (aucun nouvel appel Gemini Expert) uniquement si elle est
brute, c'est-à-dire si l'annonce est passée par l'Expert ET que l'utilisateur n'y a rien retouché. Dès qu'il a corrigé la
fiche à la main ou accepté une requalification du chat, la réponse stockée contient SA correction : la comparer à une
analyse repartie de zéro serait truqué en faveur de Gemini. Ces annonces-là (et celles sans réponse Expert stockée)
relancent donc Gemini, ce qui donne en plus sa cohérence avec lui-même. `--fresh-gemini` force le rejeu pour toutes.

Entrée identique pour les deux modèles quand Gemini est relancé : même prompt de base (config réelle de l'utilisateur), mêmes photos, même
contexte T2 (l'Analyste Gemini tourne UNE fois par annonce). La correction écrite par l'utilisateur n'est PAS injectée
dans le prompt (on rejoue l'analyse d'origine) ; elle ne sert qu'au juge.

Ne touche à rien en production : lecture seule de la base, `llm_usage.record` est neutralisé (les coûts sont relevés
en mémoire), rien n'est écrit dans `guitar_deals`.

Usage (sur le serveur, `export DATABASE_URL=... ANTHROPIC_API_KEY=...`, GEMINI_API_KEY dans .env) :
  python -m backend.scripts.replay_t3 --dry-run                       # liste ce qui serait rejoué, 0 appel payant
  python -m backend.scripts.replay_t3 --limit 3                       # essai sur 3 annonces
  python -m backend.scripts.replay_t3                                 # toutes les candidates, 2 passages par modèle
Les ids viennent de `truth_candidates.jsonl` (`--ids a,b,c` pour en choisir d'autres). Le fichier de sortie contient
des titres et extraits de chat : local, dans `.gitignore`, JAMAIS versionné (dépôt public).
"""
import argparse
import json
import os
import random
import statistics
import sys
import time

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_CANDIDATES = os.path.join(DATA_DIR, "truth_candidates.jsonl")
DEFAULT_OUT = os.path.join(DATA_DIR, "t3_replay.jsonl")
MODELS = ("gemini", "claude")
AXES = ("identification", "etat", "valeur", "hallucination")
OWNER_MSG_LIMIT = 15
OWNER_MSG_CHARS = 700

# Champs de la réponse Expert montrés au juge (le reste — model_used, tier3_trigger… — trahirait le modèle).
JUDGED_FIELDS = ("brand", "model_name", "production_year", "country_of_origin", "color", "classification",
                 "visual_inspection", "estimated_value", "resale_potential", "deal_score", "authenticity_score",
                 "condition_score", "verdict", "analysis", "summary")

JUDGE_PROMPT = """Tu es un luthier expert et un juge impartial. Deux analystes (A et B) ont évalué la MÊME annonce de
guitare d'occasion à partir des mêmes photos. Tu départages leurs réponses.

# L'annonce
{listing}

# Ce que le propriétaire a affirmé après coup (chat avec l'assistant)
Ce sont ses constats en personne ou sur de nouvelles photos : ils font foi sur l'objet. Ses QUESTIONS ne sont pas des
faits. Une réponse qui CONTREDIT un de ces constats a tort ; ne reproche rien à un analyste qui ignore une information
qui n'était ni dans l'annonce ni sur les photos.
{owner}

# Réponse A
{answer_a}

# Réponse B
{answer_b}

# Consignes
Regarde les photos toi-même. Compare par axe — « A », « B » ou « tie » :
- identification : marque, modèle, époque, pays, type d'instrument (acoustique/électrique, étui, ampli…) ;
- etat : défauts et réparations VRAIMENT visibles (fissure, manche, talon, cordier, finition) ; un défaut inventé ou un
  défaut réel manqué compte contre l'analyste ;
- valeur : fourchette de prix réaliste pour le marché d'occasion québécois, cohérente avec l'état et la décote ;
- hallucination : GAGNE celui qui invente le MOINS (détail non visible, modèle précis affirmé sans preuve, fait technique faux).
« overall » : lequel serait le plus utile et le plus fiable pour un acheteur-luthier. Reste factuel, ignore le style et la longueur.
Réponds UNIQUEMENT par ce JSON :
{{"identification": "A|B|tie", "etat": "A|B|tie", "valeur": "A|B|tie", "hallucination": "A|B|tie", "overall": "A|B|tie",
 "errors_a": ["erreur factuelle précise", ...], "errors_b": ["..."], "explanation": "2 phrases"}}"""


# ----------------------------------------------------------------------------- logique pure (testée sans réseau)

def _norm(value):
    return " ".join(str(value or "").lower().split())


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def stability(runs):
    """Cohérence d'un modèle avec lui-même sur une annonce : `runs` = réponses (dict) obtenues sur la MÊME entrée.
    Retourne None s'il y a moins de 2 réponses valides. Comparaison de la 1re réponse à chacune des suivantes."""
    runs = [r for r in runs if r]
    if len(runs) < 2:
        return None
    first, others = runs[0], runs[1:]
    same_verdict = same_brand = same_class = 0
    d_score, d_value = [], []
    for o in others:
        same_verdict += _norm(first.get("verdict")) == _norm(o.get("verdict"))
        same_brand += _norm(first.get("brand")) == _norm(o.get("brand"))
        same_class += _norm(first.get("classification")) == _norm(o.get("classification"))
        a, b = _num(first.get("deal_score")), _num(o.get("deal_score"))
        if a is not None and b is not None:
            d_score.append(abs(a - b))
        a, b = _num(first.get("estimated_value")), _num(o.get("estimated_value"))
        if a is not None and b is not None and (a + b) > 0:
            d_value.append(abs(a - b) / ((a + b) / 2))
    n = len(others)
    return {"verdict": same_verdict / n, "brand": same_brand / n, "classification": same_class / n,
            "deal_score_gap": statistics.mean(d_score) if d_score else None,
            "value_gap_pct": statistics.mean(d_value) if d_value else None}


def unblind(judgment, a_is):
    """Remplace A/B par le nom du modèle (`a_is` = modèle caché derrière « A »). Valeur invalide → « tie »."""
    b_is = "claude" if a_is == "gemini" else "gemini"
    names = {"A": a_is, "B": b_is}
    out = {k: names.get(str(judgment.get(k, "")).strip().upper(), "tie") for k in (*AXES, "overall")}
    out["errors"] = {a_is: list(judgment.get("errors_a") or []), b_is: list(judgment.get("errors_b") or [])}
    out["explanation"] = judgment.get("explanation", "")
    return out


def tally(judgments):
    """`judgments` = liste de dicts `unblind` d'UN juge → victoires par modèle et par axe."""
    counts = {k: {"gemini": 0, "claude": 0, "tie": 0} for k in (*AXES, "overall")}
    for j in judgments:
        for k in counts:
            counts[k][j.get(k, "tie")] += 1
    return counts


def mean_ignoring_none(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def cost_usd(usage_rows, pricing, price_for, as_of):
    """Coût d'une liste de lignes d'usage `{model, input_tokens, cached_tokens, output_tokens, thoughts_tokens}`."""
    total = 0.0
    for r in usage_rows:
        tier = price_for(r["model"], as_of, pricing)
        if tier is None:
            continue
        inp, cached = r.get("input_tokens", 0), r.get("cached_tokens", 0)
        total += ((inp - cached) * tier["in"] + cached * tier["in"] * tier["cached"]
                  + (r.get("output_tokens", 0) + r.get("thoughts_tokens", 0)) * tier["out"]) / 1e6
    return total


def stored_result(deal):
    """Réponse Expert telle que stockée en base : champs promus en colonnes + reste dans `ai_analysis_raw`."""
    raw = deal.get("ai_analysis_raw") if isinstance(deal.get("ai_analysis_raw"), dict) else {}
    out = dict(raw)
    for k in ("brand", "model_name", "production_year", "country_of_origin", "color", "classification", "verdict",
              "deal_score", "authenticity_score", "condition_score", "liquidity_score", "restoration_interest_score"):
        if deal.get(k) is not None:
            out[k] = deal[k]
    return out


def was_edited_by_user(deal):
    """Fiche retouchée par l'utilisateur : correction manuelle OU requalification du chat acceptée."""
    return bool(deal.get("manual_analysis_overrides") or deal.get("manual_classification") or deal.get("requal_applied"))


def use_stored_gemini(deal, fresh_gemini=False):
    """Vrai si la réponse Expert stockée est une sortie brute de Gemini, donc réutilisable telle quelle."""
    return bool(not fresh_gemini and deal.get("tier3_trigger") and not was_edited_by_user(deal))


def is_contested(row):
    """Annonce où les deux juges se contredisent, ou où un même juge change d'avis selon l'ordre A/B."""
    verdicts = {j: {x["overall"] for x in js} for j, js in row.get("judgments", {}).items() if js}
    return len({frozenset(v) for v in verdicts.values()}) > 1 or any(len(v) > 1 for v in verdicts.values())


def judged_view(result):
    return json.dumps({k: result.get(k) for k in JUDGED_FIELDS if result.get(k) not in (None, "")},
                      ensure_ascii=False, indent=1)


def owner_block(messages):
    if not messages:
        return "(aucun message du propriétaire)"
    return "\n".join(f"- {' '.join(m.split())[:OWNER_MSG_CHARS]}" for m in messages[:OWNER_MSG_LIMIT])


# ----------------------------------------------------------------------------- E/S

def load_ids(path, explicit, limit):
    if explicit:
        ids = [i.strip() for i in explicit.split(",") if i.strip()]
    else:
        with open(path, encoding="utf-8") as fh:
            ids = [json.loads(line)["id"] for line in fh if line.strip()]
    return ids[:limit] if limit else ids


def fetch_inputs(conn, deal_id, user_id):
    deal = conn.execute("SELECT * FROM guitar_deals WHERE id = %s", (deal_id,)).fetchone()
    if not deal:
        return None, []
    deal["requal_applied"] = bool(conn.execute(
        "SELECT bool_or(requalification_proposal->>'status' = 'applied') AS r FROM deal_chat WHERE deal_id = %s",
        (deal_id,)).fetchone()["r"])
    msgs = conn.execute(
        "SELECT display_text FROM deal_chat WHERE deal_id = %s AND role = 'user' AND NOT is_error "
        "AND COALESCE(display_text, '') <> '' ORDER BY created_at", (deal_id,)).fetchall()
    seen, owner = set(), []
    for m in msgs:  # doublons exacts retirés (le chat en contient)
        t = " ".join(str(m["display_text"]).split())
        if t not in seen:
            seen.add(t)
            owner.append(t)
    return deal, owner


def image_url_lists(deal):
    """Listes d'URLs à essayer, dans l'ordre de la production (copies Storage d'abord : les URLs Facebook d'origine
    expirent), 8 photos au plus."""
    lists = []
    for key in ("storage_image_urls", "image_urls"):
        urls = deal.get(key)
        if isinstance(urls, list):
            urls = [u for u in urls if isinstance(u, str)][:8]
            if urls:
                lists.append(urls)
    return lists


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", default=DEFAULT_CANDIDATES)
    ap.add_argument("--ids", default=None, help="ids séparés par des virgules (remplace le fichier de candidates)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--repeats", type=int, default=2, help="appels par modèle et par annonce (cohérence), défaut 2")
    ap.add_argument("--user", default=None, help="uid dont on prend la config (défaut : l'unique utilisateur)")
    ap.add_argument("--fresh-gemini", action="store_true",
                    help="relancer aussi Gemini (défaut : réutiliser sa réponse Expert déjà stockée)")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="n'appelle aucun modèle, liste le plan et le coût attendu")
    ap.add_argument("--seed", type=int, default=7, help="graine de l'ordre A/B (reproductible)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv("DATABASE_URL", "").replace("\r", "").strip()
    if not dsn:
        sys.exit("DATABASE_URL absent : `export DATABASE_URL=...` (ces scripts ne lisent pas .env).")
    ids = load_ids(args.candidates, args.ids, args.limit)
    if not ids:
        sys.exit("Aucune annonce à rejouer.")

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.read_only = True
        users = conn.execute("SELECT uid, config FROM users").fetchall()
        if args.user:
            users = [u for u in users if u["uid"] == args.user]
        elif len(users) > 1:
            # Le chat est partagé (pas d'uid) : on devine l'utilisateur par ses favoris et ses achats sur ces annonces.
            guess = conn.execute(
                "SELECT uid, count(*) AS n FROM (SELECT user_id AS uid FROM user_deal_state "
                "WHERE deal_id = ANY(%(ids)s) AND is_favorite UNION ALL SELECT purchased_by_user_id FROM guitar_deals "
                "WHERE id = ANY(%(ids)s) AND purchased_by_user_id IS NOT NULL) t GROUP BY uid ORDER BY n DESC",
                {"ids": ids}).fetchall()
            if guess and (len(guess) == 1 or guess[0]["n"] > guess[1]["n"]):
                users = [u for u in users if u["uid"] == guess[0]["uid"]]
                print(f"Config de l'utilisateur {guess[0]['uid']} ({guess[0]['n']} favoris/achats sur ces annonces).")
        if len(users) != 1:
            sys.exit(f"{len(users)} utilisateurs possibles : précise --user <uid> ({[u['uid'] for u in users]}).")
        config = (users[0]["config"] or {}).get("analysisConfig", {})
        inputs = {i: fetch_inputs(conn, i, users[0]["uid"]) for i in ids}

    plan = [i for i in ids if inputs[i][0]]
    stored = [i for i in plan if use_stored_gemini(inputs[i][0], args.fresh_gemini)]
    n_expert = sum(args.repeats * (1 if i in stored else len(MODELS)) for i in plan)
    print(f"{len(plan)} annonces à rejouer, {args.repeats} passages par modèle = {n_expert} appels Expert "
          f"({len(stored)} annonces avec réponse Gemini stockée réutilisée, {len(plan) - len(stored)} avec Gemini relancé)"
          + ("" if args.no_judge else f" + {len(plan) * 2 * 2} jugements (2 juges × 2 ordres)") + ".")
    for i in ids:
        deal, owner = inputs[i]
        if not deal:
            print(f"  {i}  ABSENTE de la base (ignorée)")
            continue
        why = "stockée" if i in stored else ("Gemini relancé : fiche retouchée par toi" if was_edited_by_user(deal)
                                             else "Gemini relancé : pas de réponse Expert stockée")
        print(f"  {i}  photos={len((image_url_lists(deal) or [[]])[0])}  messages propriétaire={len(owner)}  [{why}]")
        if i in stored:
            absent = [f for f in JUDGED_FIELDS if stored_result(deal).get(f) in (None, "")]
            if absent:  # une réponse stockée plus maigre fausserait le jugement : à voir AVANT de payer
                print(f"       ⚠ champs absents de la réponse stockée : {', '.join(absent)}")
    if args.dry_run:
        return

    # Imports lourds (SDK Gemini/Anthropic, config qui exige APP_ID_TARGET) seulement pour un vrai rejeu.
    os.environ.setdefault("APP_ID_TARGET", "replay")
    os.environ.setdefault("USER_IDS_TARGET", "replay")
    from datetime import date
    from backend import analyzer as analyzer_mod, llm_usage
    from backend.scripts.cost_dashboard import PRICING, price_for
    import config as cfg

    # Échouer AVANT de dépenser : une clé manquante fait échouer chaque appel de ce côté, sans bruit.
    missing = [n for n, v in (("GEMINI_API_KEY", cfg.GEMINI_API_KEY), ("ANTHROPIC_API_KEY", cfg.ANTHROPIC_API_KEY)) if not v]
    if missing:
        sys.exit(f"Clé(s) absente(s) : {', '.join(missing)} (GEMINI_API_KEY dans .env, ANTHROPIC_API_KEY exportée).")

    # Une clé présente mais FAUSSE (mal collée, révoquée) passerait le test ci-dessus : un vrai mini-appel (quelques
    # tokens) la refuse tout de suite, avant que Gemini ne dépense pour rien.
    from backend import llm_clients
    try:
        llm_clients._get_claude_client().messages.create(
            model=cfg.T3_CLAUDE_MODEL, max_tokens=64, messages=[{"role": "user", "content": "ok"}])
    except Exception as e:
        if getattr(e, "status_code", None) in (401, 403):
            sys.exit(f"Clé Anthropic refusée ({e}). Refais : read -rsp 'Clé : ' ANTHROPIC_API_KEY; export ANTHROPIC_API_KEY")
        print(f"⚠ Test de la clé Anthropic non concluant, on continue : {e}")

    captured = []
    llm_usage.record = lambda **kw: captured.append(kw)  # rien n'est écrit dans llm_usage
    an = analyzer_mod.DealAnalyzer()
    rng = random.Random(args.seed)
    gemini_model = config.get("proModel") or config.get("expertModel", "gemini-3.1-pro-preview")
    judges = {"gemini": lambda parts: an._call_gemini_json(gemini_model, parts, action="replay_judge"),
              "claude": lambda parts: an._call_claude_json(cfg.T3_CLAUDE_MODEL, parts, action="replay_judge")}

    def run_t3(provider, base_prompt, images, result_t2):
        analyzer_mod.T3_PROVIDER = provider
        before = len(captured)
        t0 = time.monotonic()
        try:
            res = an._run_t3_phase(base_prompt, images, config, gemini_model, None, [], result_t2, "replay")
            # Même normalisation de la classification que la production (`analyze_deal`), pour comparer à armes égales.
            res = an._canonicalize_classification(res, config.get("taxonomy", cfg.DEFAULT_TAXONOMY))
            err = None
        except RuntimeError as e:
            res, err = None, str(e)
        return {"result": res, "error": err, "seconds": round(time.monotonic() - t0, 1),
                "usage": [dict(r) for r in captured[before:]]}

    out_rows = []
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out, "w", encoding="utf-8").close()
    try:
        for n, deal_id in enumerate(plan, 1):
            deal, owner = inputs[deal_id]
            print(f"\n[{n}/{len(plan)}] {deal_id}")
            listing = {"title": deal.get("title"), "price": deal.get("price"), "description": deal.get("description"),
                       "location": deal.get("location")}
            images = []
            for urls in image_url_lists(deal):  # repli sur la liste suivante si aucune photo ne se télécharge
                images = [im for u in urls if (im := an._download_and_optimize_image(u))]
                if images:
                    break
            if not images:
                print("   ✗ aucune photo téléchargeable — ignorée")
                continue
            base_prompt = an._construct_base_user_prompt(
                listing, config.get("mainAnalysisPrompt", cfg.DEFAULT_MAIN_PROMPT),
                config.get("taxonomy", cfg.DEFAULT_TAXONOMY),
                config.get("fewShotExamples", cfg.DEFAULT_FEW_SHOT_EXAMPLES))
            analyzer_mod.T3_PROVIDER = "gemini"
            result_t2, err_t2 = an._run_t2_phase(base_prompt, images, config, config.get(
                "mainModel", "gemini-3.7-flash"), None, [])
            if err_t2 or not result_t2:
                print(f"   ✗ T2 en échec ({err_t2}) — ignorée")
                continue
            runs = {m: [] for m in MODELS}
            models = MODELS
            if deal_id in stored:
                models = ("claude",)
                runs["gemini"].append({"result": stored_result(deal), "error": None, "seconds": 0, "usage": [],
                                       "stored": True})
            for r in range(args.repeats):
                for m in sorted(models, reverse=True):  # Claude d'abord : un échec Claude se voit avant la dépense Gemini
                    run = run_t3(m, base_prompt, images, result_t2)
                    runs[m].append(run)
                    ok = "ok" if run["result"] else f"ÉCHEC {run['error']}"
                    print(f"   {m:<6} #{r + 1}  {run['seconds']:>5}s  {ok}")
            row = {"id": deal_id, "title": deal.get("title"), "runs": runs, "judgments": {},
                   "judge_usage": [], "gemini_stored": deal_id in stored, "edited_by_user": was_edited_by_user(deal)}
            if not args.no_judge:
                first = {m: next((x["result"] for x in runs[m] if x["result"]), None) for m in MODELS}
                if all(first.values()):
                    listing_txt = (f"Titre : {listing['title']}\nPrix : {listing['price']}\nLieu : {listing['location']}\n"
                                   f"Description : {listing['description']}")
                    for jname, jcall in judges.items():
                        row["judgments"][jname] = []
                        for a_is in rng.sample(MODELS, 2):  # les deux ordres, tirés dans un ordre aléatoire
                            b_is = "claude" if a_is == "gemini" else "gemini"
                            prompt = JUDGE_PROMPT.format(listing=listing_txt, owner=owner_block(owner),
                                                         answer_a=judged_view(first[a_is]), answer_b=judged_view(first[b_is]))
                            before = len(captured)
                            raw, err = jcall([prompt] + images)
                            row["judge_usage"].extend(dict(u) for u in captured[before:])
                            if raw:
                                row["judgments"][jname].append(unblind(raw, a_is))
                            else:
                                print(f"   ✗ juge {jname} en échec : {err}")
            out_rows.append(row)
            with open(args.out, "a", encoding="utf-8") as fh:  # écrit au fil de l'eau : un arrêt ne perd rien de payé
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    finally:
        print(f"\nÉcrit : {args.out}  (local, dans .gitignore — ne jamais versionner)")

    report(out_rows, PRICING, price_for, date.today())


def report(rows, pricing, price_for, today):
    print("\n================ RÉSULTATS ================")
    print(f"{len(rows)} annonces rejouées.\n")
    print("COHÉRENCE avec soi-même (même entrée, appels répétés) — plus haut = mieux, écarts : plus bas = mieux")
    for m in MODELS:
        stabs = [s for r in rows if (s := stability([x["result"] for x in r["runs"][m]]))]
        if not stabs:
            print(f"  {m:<7} (pas assez de réponses valides)")
            continue
        g = lambda k: mean_ignoring_none(s[k] for s in stabs)
        fmt = lambda v, f: "-" if v is None else f.format(v)
        print(f"  {m:<7} même verdict {g('verdict'):.0%} | même marque {g('brand'):.0%} | même classification "
              f"{g('classification'):.0%} | écart deal_score {fmt(g('deal_score_gap'), '{:.1f}')} | "
              f"écart valeur {fmt(g('value_gap_pct'), '{:.0%}')}  (sur {len(stabs)} annonces)")
    print("\nFIABILITÉ, LATENCE, COÛT par appel Expert")
    for m in MODELS:
        calls = [x for r in rows for x in r["runs"][m] if not x.get("stored")]
        if not calls:
            print(f"  {m:<7} réponses déjà stockées en production : pas de nouvel appel, donc ni latence ni coût mesurés")
            continue
        fails = sum(1 for x in calls if not x["result"])
        usage = [u for x in calls for u in x["usage"]]
        cost = cost_usd(usage, pricing, price_for, today)
        secs = sorted(x["seconds"] for x in calls)
        p50 = secs[len(secs) // 2] if secs else 0
        print(f"  {m:<7} échecs {fails}/{len(calls)} | latence médiane {p50}s | coût moyen "
              f"${cost / max(len(calls), 1):.3f} (total ${cost:.2f})")
    print("\nQUALITÉ — victoires par axe (juge à l'aveugle, 2 ordres A/B par annonce)")
    for jname in MODELS:
        js = [j for r in rows for j in r["judgments"].get(jname, [])]
        if not js:
            continue
        c = tally(js)
        print(f"  juge {jname} ({len(js)} jugements)")
        for k in (*AXES, "overall"):
            v = c[k]
            print(f"     {k:<15} gemini {v['gemini']:>2} | claude {v['claude']:>2} | égalité {v['tie']:>2}")
    contested = [r for r in rows if is_contested(r)]
    if contested:
        print(f"\nÀ REGARDER À LA MAIN ({len(contested)} annonces où les juges ou les deux ordres se contredisent) :")
        for r in contested:
            print(f"  {r['id']}  {r['title']}")
    judge_cost = cost_usd([u for r in rows for u in r.get("judge_usage", [])], pricing, price_for, today)
    print(f"\nCoût des jugements (non inclus ci-dessus) : ${judge_cost:.2f}")
    print("\nLecture : un juge favorise souvent son propre style ; ne retiens un avantage que s'il apparaît chez LES DEUX juges.")


if __name__ == "__main__":
    main()
