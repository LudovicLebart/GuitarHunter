"""
Chantier I — compare `qwen_local` (Qwen3-VL-8B-Instruct, Dell T5810 via Ollama) au verdict du
Portier T1 DÉJÀ enregistré en production (`gatekeeperVerdict` dans `ai_analysis_raw` — Qwen
cloud via TokenRouter depuis la bascule du 2026-09-20, Gemini avant) sur des annonces déjà
analysées. Un seul appel réel par annonce (`qwen_local`) — le verdict prod n'est JAMAIS rappelé,
juste relu depuis la base. Même angle que `compare_qwen_flashlite_agreement.py` (Chantier H, sur
la branche `claude/firestore-postgres-migration`) : le cas qui compte vraiment est
"Cloud ACCEPTE, Local REJETTE" (rappel perdu, opportunité définitivement manquée si `qwen_local`
devenait un jour LE Portier), pas l'inverse (juste une ré-analyse T2 en trop, coût négligeable).

Lit le clone Postgres local (Chantier A, `guitarhunter_pg_staging`) plutôt que Firestore —
AUCUNE credential Firebase nécessaire. Doit tourner SUR le serveur (Lenovo ThinkCentre) : la
base n'est joignable qu'en localhost (`DATABASE_URL` par défaut, auth locale sans mot de passe
réseau — voir `backend/pg_db.py` sur la branche de migration). Le réseau vers le Dell
(`qwen_local`, 100.94.33.54:11434) est déjà validé depuis ce même tailnet.

Reconstruit le prompt EXACT du Portier de prod (mêmes fonctions que `backend/analyzer.py`,
dupliquées ici à dessein plutôt qu'importées — même principe que `compare_qwen_flashlite_agreement.py`
: rester lisible seul, sans tirer la dépendance lourde `google.generativeai` juste pour ces
quelques fonctions), y compris la config utilisateur réelle (`users.config->>'analysisConfig'`)
si elle diverge des défauts de `prompts.json` — pas seulement les défauts.

Dépendances (à installer sur le serveur si absentes) : psycopg[binary], openai, pillow, requests.

Usage :
    python -m backend.scripts.compare_qwen_local_vs_prod --limit 15
    python -m backend.scripts.compare_qwen_local_vs_prod --limit 15 --model qwen3-vl:4b  (repli si le 8B étouffe)

Corrections Chantier I-0 (TODO.md, 2026-09-24) appliquées ici : plafond de 4 images/annonce et
`num_ctx` fixé (marge VRAM sur le 8B, 8Go de la RTX 2060 Super), VRAM Ollama (`/api/ps`) loggée
avant/après le run, `--model` pour basculer sur le repli `qwen3-vl:4b`, métriques taux JSON
valide / latence P90 / taux de statuts hors enum en fin de résumé.
"""
import argparse
import base64
import json
import os
import sys
import time
from io import BytesIO

import psycopg
import requests
from openai import OpenAI
from PIL import Image
from psycopg.rows import dict_row

sys.path.insert(0, os.getcwd())

from config import (
    DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_MAIN_PROMPT, DEFAULT_TAXONOMY,
    DEFAULT_FEW_SHOT_EXAMPLES,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmark", "results")

# Même défaut que backend/pg_db.py, mais pointé sur la base réellement peuplée par l'export
# Chantier A (guitarhunter_pg_staging, 6533 annonces au 2026-09-14 — voir JOURNAL.md sur
# claude/firestore-postgres-migration), pas "guitarhunter" (le nom générique du module).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://guitarhunter@localhost/guitarhunter_pg_staging")

# Dupliqués de backend/analyzer.py (T1_VALID_STATUSES, T1_GATEKEEPER_OPENAI_JSON_SCHEMA) — même
# rationale que compare_qwen_flashlite_agreement.py : pas d'import direct d'analyzer.py.
T1_VALID_STATUSES = frozenset({
    "PEPITE", "FAST_FLIP", "LUTHIER_PROJ", "CASE_WIN", "COLLECTION",
    "FAIR", "BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE",
})
T1_REJECTION_VERDICTS = frozenset({"BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE"})
T1_GATEKEEPER_OPENAI_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "t1_gatekeeper_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": list(T1_VALID_STATUSES)},
                "reasoning": {"type": "string"},
                "brand": {"type": "string"},
                "classification": {"type": "string"},
            },
            "required": ["status", "reasoning", "brand", "classification"],
            "additionalProperties": False,
        },
    },
}

# Mêmes défauts que backend/benchmark/candidates.py::call_qwen_local (Chantier I) — dupliqués
# ici plutôt qu'importés (candidates.py tire anthropic/google.generativeai au chargement, inutile
# ici, même philosophie d'imports légers que le reste de ce fichier).
QWEN_LOCAL_BASE_URL = os.getenv("QWEN_LOCAL_BASE_URL", "http://100.94.33.54:11434/v1")
QWEN_LOCAL_MODEL = os.getenv("QWEN_LOCAL_MODEL", "qwen3-vl:8b")
QWEN_LOCAL_API_KEY = os.getenv("QWEN_LOCAL_API_KEY", "ollama")
# Endpoint natif Ollama (pas /v1, l'API compatible OpenAI n'expose pas /api/ps) — même host/port,
# utilisé uniquement pour lire la VRAM des modèles chargés (Chantier I-0, marge VRAM sur le 8B).
QWEN_LOCAL_NATIVE_BASE_URL = QWEN_LOCAL_BASE_URL.rsplit("/v1", 1)[0]

# Chantier I-0 (TODO.md, 2026-09-24) : la RTX 2060 Super du Dell n'a que ~1,2 Go de marge avec le
# 8B (6982/8192 MiB mesurés à l'installation) — Qwen3-VL supporte nativement un contexte bien plus
# grand (dizaines de milliers de tokens), et Ollama dimensionne le cache KV en VRAM sur cette base
# si rien n'est précisé. Fixé à une valeur plafond largement suffisante pour le prompt Portier
# (taxonomie + few-shot, quelques milliers de tokens) mais bien en-deçà du défaut du modèle.
# REVU (2026-09-27) : demander 8192 ne suffit pas à l'obtenir — VRAM insuffisante pour un cache KV
# à cette taille, Ollama retombe SILENCIEUSEMENT sur 4096 (confirmé via `ollama ps` et les logs
# `truncating input prompt limit=4096`). La valeur ici reste la demande envoyée à Ollama (utile si
# la marge VRAM s'améliore un jour côté MAX_IMAGES ci-dessous) — mais ne pas supposer qu'elle est
# honorée sans revérifier `ollama ps`/les logs après un changement.
QWEN_LOCAL_NUM_CTX = int(os.getenv("QWEN_LOCAL_NUM_CTX", "8192"))
# Idem : chaque image consomme du contexte une fois encodée — plafonné à 4 (au lieu de 8, le
# plafond utilisé ailleurs dans le projet pour les appels cloud) pour rester sous la marge VRAM.
# Laissé à 4 (2026-09-27, pas réduit à 2 malgré la pression sur les 4096 tokens réellement
# disponibles — décision utilisateur) : les images sont le signal le plus riche pour ce que le
# texte seul ne peut pas révéler (voir `study_visual_dependence.py`, ~23-43% des verdicts en
# dépendent) — le compromis retenu passe par le réordonnancement du prompt (taxonomie sacrifiable
# en premier) plutôt que par moins d'images.
MAX_IMAGES = int(os.getenv("QWEN_LOCAL_MAX_IMAGES", "4"))
# Expérimentation 2026-09-27 (TODO.md § Chantier I) : le script n'avait jamais de plafond sur la
# génération — sur un 8B, le decode (génération token par token) domine largement la latence,
# bien plus que le prompt lui-même. Les raisonnements confus observés sur le run n=141 (plusieurs
# centaines de mots pour certains) expliquent une bonne part des P90 ~35s mesurés.
# RÉGRESSION TROUVÉE (2026-09-27, même jour) : un premier plafond à 600 provoquait des réponses
# JSON VIDES (`content` = "") sur certaines annonces — Qwen3 est un modèle "thinking", Ollama
# sépare son raisonnement interne (`reasoning_content`) du JSON final (`content`) ; si le plafond
# tombe pendant la phase de réflexion, `content` ne contient jamais rien. Remonté à 2000 pour
# laisser assez de marge à la réflexion + la réponse — reste fini, juste moins agressif.
QWEN_LOCAL_MAX_OUTPUT_TOKENS = int(os.getenv("QWEN_LOCAL_MAX_OUTPUT_TOKENS", "2000"))


def _is_rejected(verdict):
    return verdict in T1_REJECTION_VERDICTS


def _download_and_optimize_image(url, max_size=2048):
    """Copie fidèle de DealAnalyzer._download_and_optimize_image (backend/analyzer.py)."""
    try:
        if not url or "via.placeholder.com" in url:
            return None
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        img = Image.open(BytesIO(response.content))
        if img.size[0] > max_size or img.size[1] > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return img.convert("RGB") if img.mode in ("RGBA", "P") else img
    except Exception as e:
        print(f"  ⚠️ Image illisible ({url}) : {e}")
        return None


def _construct_base_user_prompt(listing_data, main_prompt_template, taxonomy_data, few_shot_examples=None):
    """Copie fidèle de DealAnalyzer._construct_base_user_prompt (backend/analyzer.py) — même
    sérialisation JSON (sort_keys, separators compacts) pour reconstruire OCTET POUR OCTET le
    même préfixe que celui réellement envoyé au Portier de prod."""
    prompt_lines = main_prompt_template if isinstance(main_prompt_template, list) else str(main_prompt_template).split('\n')
    main_prompt_str = "\n".join(prompt_lines)

    examples_str = ""
    if few_shot_examples:
        examples_lines = few_shot_examples if isinstance(few_shot_examples, list) else str(few_shot_examples).split('\n')
        examples_str = "\n".join(examples_lines) + "\n\n"

    taxonomy_str = json.dumps(taxonomy_data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

    return (
        f"{main_prompt_str}\n\n"
        f"### TAXONOMIE DE RÉFÉRENCE\n"
        f"{taxonomy_str}\n\n"
        f"{examples_str}"
        f"Détails de l'annonce :\n"
        f"- Titre : {listing_data.get('title', 'N/A')}\n"
        f"- Prix : {listing_data.get('price', 'N/A')}\n"
        f"- Description : {listing_data.get('description', 'N/A')}\n"
        f"- Localisation : {listing_data.get('location', 'N/A')}\n"
    )


def _construct_simplified_gatekeeper_prompt(listing_data, taxonomy_data, gatekeeper_instruction):
    """Variante d'expérimentation (2026-09-27, TODO.md § Chantier I) : le prompt fidèle
    (`_construct_base_user_prompt` + instruction Portier concaténée à la fin) fait lire à
    Qwen3-VL-8B ~17000 caractères de prompt T2 (analyste complet, scores, few-shot calibrés pour
    un modèle plus gros) AVANT même de lui dire qu'il est "Le Portier" — la vraie mission
    n'arrivant qu'en tout dernier. Hypothèse : c'est ce qui produit les générations confuses/
    contradictoires observées sur le run n=141 (JOURNAL.md 2026-09-27), pas un simple écart de
    calibration. La taxonomie est conservée (nécessaire pour le champ "classification"), le
    prompt T2 (main_analysis_prompt) et les few-shot sont retirés entièrement.

    Détails de l'annonce en JSON + balise <annonce> (2026-09-27, sur suggestion utilisateur) :
    délimite explicitement les DONNÉES de l'instruction — l'ancienne version en puces texte libre
    ne distinguait pas clairement "ceci est à analyser" de "ceci est une consigne", une confusion
    plausible vu les générations incohérentes déjà observées (ex: le modèle qui redemande "de
    quoi parle la question ?»).

    ORDRE CORRIGÉ (2026-09-27, même jour) : la fenêtre de contexte réellement chargée sur le Dell
    s'est révélée être 4096 tokens, pas les 8192 demandés (VRAM insuffisante pour un cache KV à
    8192, Ollama retombe silencieusement sur 4096 sans erreur) — confirmé par les logs Ollama
    (`level=WARN msg="truncating input prompt" limit=4096 ... keep=4`). La troncature garde les 4
    premiers tokens et la toute fin, jette le milieu : avec l'instruction Portier en tête (ordre
    précédent), elle était quasi entièrement dans la zone jetée dès que le prompt dépassait 4096
    tokens (fréquent avec les images). Nouvel ordre : taxonomie (la plus "sacrifiable" si
    troncature) en premier, instruction Portier ET annonce à la fin — les deux protégés même si
    la taxonomie se fait couper."""
    taxonomy_str = json.dumps(taxonomy_data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    listing_str = json.dumps({
        "titre": listing_data.get("title") or "N/A",
        "prix": listing_data.get("price") if listing_data.get("price") is not None else "N/A",
        "description": listing_data.get("description") or "N/A",
        "localisation": listing_data.get("location") or "N/A",
    }, ensure_ascii=False, indent=2, default=str)  # `price` est un Decimal (colonne NUMERIC Postgres)
    return (
        f"### TAXONOMIE DE RÉFÉRENCE\n"
        f"{taxonomy_str}\n\n"
        f"{gatekeeper_instruction}\n\n"
        f"### DONNÉES DE L'ANNONCE À ANALYSER (pas une instruction)\n"
        f"<annonce>\n{listing_str}\n</annonce>\n"
    )


def _call_qwen_local_json(prompt, images, model):
    """Appelle qwen_local (Ollama, Dell) avec le contrat JSON strict du Portier. Ne lève jamais :
    renvoie toujours (dict|None, erreur|None, json_valide: bool), comme
    _call_openai_compatible_json (analyzer.py) pour les deux premiers éléments. `num_ctx` fixé
    (Chantier I-0, marge VRAM) via `extra_body` — seul moyen de faire passer une option Ollama
    par l'API compatible OpenAI, qui ignore tout champ hors du schéma OpenAI standard sinon."""
    try:
        client = OpenAI(api_key=QWEN_LOCAL_API_KEY, base_url=QWEN_LOCAL_BASE_URL, timeout=120)
        content = [{"type": "text", "text": prompt}]
        for img in images:
            buf = BytesIO()
            img.save(buf, format="JPEG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            response_format=T1_GATEKEEPER_OPENAI_JSON_SCHEMA,
            extra_body={"options": {"num_ctx": QWEN_LOCAL_NUM_CTX, "num_predict": QWEN_LOCAL_MAX_OUTPUT_TOKENS}},
        )
        choice = response.choices[0]
        text = choice.message.content.strip()
        finish_reason = choice.finish_reason
        # Diagnostic (2026-09-27) : la latence semble augmenter avec le prompt simplifié, contraire
        # à l'hypothèse de départ ("prompt plus court = génération plus courte") — pour savoir si
        # le modèle consomme vraiment tout le budget num_predict ou si le ralentissement vient
        # d'ailleurs, sans re-deviner : completion_tokens/reasoning_tokens comme _call_openai_
        # compatible_json (analyzer.py).
        usage = getattr(response, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        details = getattr(usage, "completion_tokens_details", None) if usage else None
        reasoning_tokens = (getattr(details, "reasoning_tokens", None) if details else None)
    except Exception as e:
        return None, str(e), False, None, None

    if not text:
        # content vide + finish_reason="length" = num_predict atteint pendant la réflexion interne
        # du modèle (thinking), avant tout JSON — pas une erreur de parsing classique, à distinguer
        # d'un JSON simplement malformé.
        return (None, f"réponse vide (finish_reason={finish_reason!r}, "
                f"num_predict={QWEN_LOCAL_MAX_OUTPUT_TOKENS} peut-être trop bas)",
                False, completion_tokens, reasoning_tokens)

    try:
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        if isinstance(result, list):
            result = result[0] if result and isinstance(result[0], dict) else {}
        return result, None, True, completion_tokens, reasoning_tokens
    except Exception as e:
        return (None, f"réponse non-JSON (finish_reason={finish_reason!r}) : {e}",
                False, completion_tokens, reasoning_tokens)


def _log_ollama_vram(label):
    """Chantier I-0 : logue les modèles actuellement chargés en VRAM sur le Dell (endpoint natif
    Ollama /api/ps, absent de l'API compatible OpenAI) — repère visuel de marge avant/après le
    run, pas une mesure exacte (la VRAM totale du GPU n'est pas exposée par cet endpoint)."""
    try:
        resp = requests.get(f"{QWEN_LOCAL_NATIVE_BASE_URL}/api/ps", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        if not models:
            print(f"  📊 VRAM Ollama ({label}) : aucun modèle chargé.")
            return
        for m in models:
            size_vram_gb = m.get("size_vram", 0) / (1024 ** 3)
            print(f"  📊 VRAM Ollama ({label}) : {m.get('name')} — {size_vram_gb:.2f} Go en VRAM.")
    except Exception as e:
        print(f"  ⚠️ Lecture VRAM Ollama ({label}) impossible : {e}")


def _percentile(values, pct):
    """P90 (ou autre) sans dépendance numpy — interpolation linéaire simple, suffisante pour un
    script de diagnostic ponctuel."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _get_user_analysis_config(conn, user_id, cache):
    """Config réelle de l'utilisateur (analysisConfig, si personnalisée en base) plutôt que les
    seuls défauts de prompts.json — un utilisateur ayant modifié son instruction Portier via
    ConfigPanel recevrait sinon une comparaison faussée (prompt différent de celui réellement
    envoyé au Qwen cloud pour ses annonces). Repli silencieux sur {} si absent/vide : les appels
    .get(clé, DÉFAUT) plus bas retombent alors sur les défauts, comme le fait analyzer.py."""
    if user_id in cache:
        return cache[user_id]
    analysis_config = {}
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT config FROM users WHERE uid = %s", (user_id,))
            row = cur.fetchone()
            if row and row.get("config"):
                raw = row["config"]
                raw = json.loads(raw) if isinstance(raw, str) else raw
                analysis_config = raw.get("analysisConfig") or {}
    except Exception as e:
        print(f"  ⚠️ Config utilisateur {user_id} illisible, défauts utilisés : {e}")
    cache[user_id] = analysis_config
    return analysis_config


def main():
    parser = argparse.ArgumentParser(
        description="Compare qwen_local (Dell) au verdict Portier déjà en base (Postgres, Chantier A)."
    )
    parser.add_argument("--limit", type=int, default=15, help="Nombre d'annonces à rejouer (défaut : 15).")
    parser.add_argument("--model", default=QWEN_LOCAL_MODEL,
                         help="Modèle Ollama à interroger (défaut : qwen3-vl:8b). "
                              "Repli si le 8B étouffe : qwen3-vl:4b.")
    parser.add_argument("--simplified-prompt", action="store_true",
                         help="Expérimental (2026-09-27) : prompt T1 minimal pour le local "
                              "(instruction Portier + taxonomie, sans le prompt T2/few-shot) au "
                              "lieu du prompt fidèle à la prod. Le verdict cloud comparé reste "
                              "inchangé (toujours celui réellement stocké en base).")
    args = parser.parse_args()

    est_minutes = round(args.limit * 20 / 60, 1)
    print(f"🔍 Connexion à {DATABASE_URL.split('@')[-1]} — jusqu'à {args.limit} annonce(s) "
          f"à rejouer sur {args.model} (~{est_minutes} min estimées, ~20s/annonce).")
    _log_ollama_vram("avant le run")

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT gd.id, udm.user_id, gd.title, gd.price, gd.description, gd.location,
                       gd.image_urls, gd.storage_image_urls, gd.ai_analysis_raw, gd.link,
                       gd."timestamp"
                FROM guitar_deals gd
                LEFT JOIN LATERAL (
                    SELECT user_id FROM user_deal_matches
                    WHERE deal_id = gd.id
                    LIMIT 1
                ) udm ON true
                WHERE gd.ai_analysis_raw ->> 'gatekeeperVerdict' IS NOT NULL
                ORDER BY gd."timestamp" DESC
                LIMIT %s
                """,
                (args.limit,),
            )
            rows = cur.fetchall()

        print(f"📦 {len(rows)} annonce(s) avec un gatekeeperVerdict déjà en base (les plus récentes).\n")
        if not rows:
            print("Rien à comparer — l'export Chantier A a-t-il bien tourné sur cette base ?")
            return

        config_cache = {}
        agree_accept = agree_reject = 0
        cloud_accept_local_reject = []
        cloud_reject_local_accept = []
        n_excluded_invalid = 0
        n_failed_call = 0
        n_json_valid = 0
        n_status_out_of_enum = 0
        latencies_s = []
        completion_tokens_list = []
        prompt_tokens_est_list = []

        for i, row in enumerate(rows, 1):
            ai = row["ai_analysis_raw"]
            ai = json.loads(ai) if isinstance(ai, str) else (ai or {})
            cloud_verdict = ai.get("gatekeeperVerdict")
            if cloud_verdict not in T1_VALID_STATUSES:
                n_excluded_invalid += 1
                continue

            print(f"[{i}/{len(rows)}] {row['id']} — '{(row['title'] or '')[:60]}'")

            analysis_config = _get_user_analysis_config(conn, row["user_id"], config_cache)
            taxonomy = analysis_config.get("taxonomy", DEFAULT_TAXONOMY)
            few_shot = analysis_config.get("fewShotExamples", DEFAULT_FEW_SHOT_EXAMPLES)
            gatekeeper_instruction = analysis_config.get("gatekeeperVerbosityInstruction", DEFAULT_GATEKEEPER_INSTRUCTION)
            if isinstance(gatekeeper_instruction, list):
                gatekeeper_instruction = "\n".join(gatekeeper_instruction)
            main_prompt = analysis_config.get("mainAnalysisPrompt", DEFAULT_MAIN_PROMPT)

            if args.simplified_prompt:
                full_prompt_t1 = _construct_simplified_gatekeeper_prompt(row, taxonomy, gatekeeper_instruction)
            else:
                base_prompt = _construct_base_user_prompt(row, main_prompt, taxonomy, few_shot)
                full_prompt_t1 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE PORTIER ---\n{gatekeeper_instruction}"

            # storage_image_urls (Firebase Storage, stable) préféré à image_urls (Facebook,
            # peut avoir expiré depuis l'analyse d'origine) — même priorité que le reste du projet.
            image_urls = row.get("storage_image_urls") or row.get("image_urls") or []
            image_urls = json.loads(image_urls) if isinstance(image_urls, str) else image_urls
            images = [img for url in image_urls[:MAX_IMAGES] if (img := _download_and_optimize_image(url))]

            # Diagnostic (2026-09-27) : la fenêtre réellement disponible sur le Dell s'est révélée
            # être 4096 tokens, pas les 8192 demandés (voir QWEN_LOCAL_NUM_CTX ci-dessus) — cette
            # estimation grossière (4 caractères/token, n'inclut PAS le coût des images) donne un
            # signal immédiat de risque de troncature sans avoir à consulter les logs du Dell.
            prompt_chars = len(full_prompt_t1)
            prompt_tokens_est = prompt_chars // 4
            prompt_tokens_est_list.append(prompt_tokens_est)
            if prompt_tokens_est > 3000:  # marge avant 4096 pour le coût des images, non compté ici
                print(f"  ⚠️ Prompt texte ~{prompt_tokens_est} tokens (hors images) — "
                      f"risque de troncature (limite connue : 4096).")

            t0 = time.monotonic()
            result, err, json_valid, completion_tokens, reasoning_tokens = _call_qwen_local_json(
                full_prompt_t1, images, args.model
            )
            latency_s = round(time.monotonic() - t0, 1)
            latencies_s.append(latency_s)
            if completion_tokens is not None:
                completion_tokens_list.append(completion_tokens)
            if json_valid:
                n_json_valid += 1

            tok_info = f", {completion_tokens} tokens" if completion_tokens is not None else ""
            if reasoning_tokens:
                tok_info += f" (dont {reasoning_tokens} de réflexion)"

            if err or not result:
                print(f"  ❌ Échec qwen_local ({latency_s}s{tok_info}) : {err}")
                n_failed_call += 1
                continue

            local_verdict = (result.get("status") or "UNKNOWN").upper()
            print(f"  Cloud (prod) = {cloud_verdict} | Local (Dell) = {local_verdict} ({latency_s}s{tok_info})")
            if local_verdict not in T1_VALID_STATUSES:
                n_status_out_of_enum += 1
                print(f"  ⚠️ Statut hors enum T1 attendu : {local_verdict!r}")

            c_rej, l_rej = _is_rejected(cloud_verdict), _is_rejected(local_verdict)
            if not c_rej and not l_rej:
                agree_accept += 1
            elif c_rej and l_rej:
                agree_reject += 1
            elif not c_rej and l_rej:
                cloud_accept_local_reject.append((row, cloud_verdict, local_verdict, result.get("reasoning")))
            else:
                cloud_reject_local_accept.append((row, cloud_verdict, local_verdict, result.get("reasoning")))

        _log_ollama_vram("après le run")

        n = agree_accept + agree_reject + len(cloud_accept_local_reject) + len(cloud_reject_local_accept)
        n_attempted = n + n_failed_call
        json_valid_rate = (100 * n_json_valid / n_attempted) if n_attempted else 0.0
        p90_latency_s = _percentile(latencies_s, 90)
        out_of_enum_rate = (100 * n_status_out_of_enum / n_json_valid) if n_json_valid else 0.0
        avg_completion_tokens = (round(sum(completion_tokens_list) / len(completion_tokens_list), 1)
                                  if completion_tokens_list else None)
        p90_completion_tokens = _percentile(completion_tokens_list, 90)
        p90_prompt_tokens_est = _percentile(prompt_tokens_est_list, 90)

        print(f"\n{'=' * 60}\nRÉSUMÉ ({n} comparaison(s) valide(s), "
              f"{n_excluded_invalid} exclue(s) verdict cloud invalide, "
              f"{n_failed_call} échec(s) d'appel qwen_local)\n{'=' * 60}")
        print(f"  Taux JSON valide : {n_json_valid}/{n_attempted} ({json_valid_rate:.1f}%)")
        print(f"  Latence P90 : {p90_latency_s:.1f}s" if p90_latency_s is not None else "  Latence P90 : n/a")
        if avg_completion_tokens is not None:
            print(f"  Tokens générés : moyenne {avg_completion_tokens}, P90 {p90_completion_tokens:.0f} "
                  f"(plafond num_predict={QWEN_LOCAL_MAX_OUTPUT_TOKENS})")
        if p90_prompt_tokens_est is not None:
            print(f"  Prompt texte (estimation, hors images) : P90 ~{p90_prompt_tokens_est:.0f} tokens "
                  f"(limite de contexte réelle connue : 4096)")
        print(f"  Statuts hors enum T1 (sur JSON valides) : {n_status_out_of_enum}/{n_json_valid} "
              f"({out_of_enum_rate:.1f}%)")
        if n == 0:
            print("Aucune comparaison valide obtenue.")
            return
        print(f"  Accord ACCEPT/ACCEPT : {agree_accept} ({100 * agree_accept / n:.1f}%)")
        print(f"  Accord REJECT/REJECT : {agree_reject} ({100 * agree_reject / n:.1f}%)")
        print(f"  Cloud ACCEPTE, Local REJETTE (coûteux si bascule locale, rappel perdu) : "
              f"{len(cloud_accept_local_reject)} ({100 * len(cloud_accept_local_reject) / n:.1f}%)")
        print(f"  Cloud REJETTE, Local ACCEPTE (faux positif, coût marginal T2) : "
              f"{len(cloud_reject_local_accept)} ({100 * len(cloud_reject_local_accept) / n:.1f}%)")

        if cloud_accept_local_reject:
            print(f"\n{'=' * 60}\nDÉTAIL — Cloud accepte, Local aurait rejeté (n={len(cloud_accept_local_reject)})\n{'=' * 60}")
            for row, cv, lv, reasoning in cloud_accept_local_reject:
                print(f"- {row['id']} : '{(row['title'] or '')[:60]}' — Cloud={cv} Local={lv}")
                print(f"    lien : {row.get('link') or '(absent)'}")
                if reasoning:
                    print(f"    raisonnement local : {str(reasoning)[:300]}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "compare_qwen_local_vs_prod.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "model": args.model,
            "simplified_prompt": args.simplified_prompt,
            "n_total": n,
            "agree_accept": agree_accept,
            "agree_reject": agree_reject,
            "n_excluded_invalid": n_excluded_invalid,
            "n_failed_call": n_failed_call,
            "n_json_valid": n_json_valid,
            "json_valid_rate_pct": round(json_valid_rate, 1),
            "p90_latency_s": p90_latency_s,
            "avg_completion_tokens": avg_completion_tokens,
            "p90_completion_tokens": p90_completion_tokens,
            "max_output_tokens_cap": QWEN_LOCAL_MAX_OUTPUT_TOKENS,
            "p90_prompt_tokens_est": p90_prompt_tokens_est,
            "n_status_out_of_enum": n_status_out_of_enum,
            "out_of_enum_rate_pct": round(out_of_enum_rate, 1),
            "cloud_accept_local_reject": [
                {"id": row["id"], "title": row.get("title"), "link": row.get("link"),
                 "cloud_verdict": cv, "local_verdict": lv, "local_reasoning": reasoning}
                for row, cv, lv, reasoning in cloud_accept_local_reject
            ],
            "cloud_reject_local_accept_count": len(cloud_reject_local_accept),
        }, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
