import base64
import json
import re
import threading
import time
import requests
import logging
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from openai import OpenAI
from backend.notifications import NotificationService
from config import (
    GEMINI_API_KEY,
    DEFAULT_MAIN_PROMPT,
    DEFAULT_GATEKEEPER_INSTRUCTION,
    DEFAULT_ANALYST_INSTRUCTION,
    DEFAULT_EXPERT_CONTEXT,
    DEFAULT_SOLD_BACKFILL_INSTRUCTION,
    DEFAULT_TAXONOMY,
    DEFAULT_FEW_SHOT_EXAMPLES,
    DEFAULT_REJECTION_VERDICTS,
    DEFAULT_PRO_PRICE_THRESHOLD,
    DEFAULT_PRO_DEAL_SCORE_THRESHOLD,
    DEFAULT_PRO_COMBINED_DEAL_SCORE,
    DEFAULT_PRO_RESTO_SCORE_THRESHOLD,
    DEFAULT_PRO_AUTH_SCORE_THRESHOLD,
    DEFAULT_PRO_CONFIDENCE_THRESHOLD,
    TOKENROUTER_API_KEY,
    TOKENROUTER_BASE_URL,
    T1_OBSERVATION_QWEN_MODEL,
    T1_OBSERVATION_ENABLED,
    T1_GATEKEEPER_PROVIDER,
)
from backend.scraping.parser import ListingParser
from backend.taxonomy import (
    build_index as build_taxonomy_index,
    canonicalize as canonicalize_classification,
    matches_active_search_family,
)

logger = logging.getLogger(__name__)

# Rattrapage Chantier G (2026-09-19) : verdicts T1 jamais cachés par le routage
# `activeSearchFamilies`, quelle que soit la correspondance de classification — garde-fou non
# négociable, ne jamais masquer une pépite hors-filtre.
T1_PEPITE_TIER_VERDICTS = frozenset({"PEPITE", "FAST_FLIP", "LUTHIER_PROJ", "CASE_WIN", "COLLECTION"})

# Verdicts d'erreur du Portier (appel raté ou réponse malformée) — n'ont par définition aucune
# classification fiable, donc jamais soumis au routage Chantier G (`activeSearchFamilies`) au
# risque d'être routés à tort vers NOT_PROMOTED au lieu du fail-open habituel vers l'Analyste
# (Chantier H, porté depuis dev le 2026-09-22).
T1_ERROR_STATUSES = frozenset({"ERROR", "ERROR_GATEKEEPER"})

# Chantier H (porté depuis dev le 2026-09-22) : les 9 verdicts que `gatekeeper_verbosity_instruction`
# (prompts.json) autorise explicitement pour le champ `status` du Portier — seule liste fermée du
# contrat T1. Partagée par le schéma Gemini (enum natif du SDK) et le schéma OpenAI-compatible
# (Qwen) ci-dessous, pour que les deux appels T1 (le décideur réel et l'observation Chantier H)
# soient contraints à exactement le même vocabulaire.
T1_VALID_STATUSES = (
    "PEPITE", "FAST_FLIP", "LUTHIER_PROJ", "CASE_WIN", "COLLECTION",
    "FAIR", "BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE",
)

# Contrat JSON du Portier, tel qu'exigé par `gatekeeper_verbosity_instruction` (prompts.json) —
# { status, reasoning, brand, classification }. `classification` n'est pas contrainte par un enum
# et n'est pas requise : le prompt demande la valeur littérale "NULL" (une chaîne, pas un JSON
# null) quand le modèle est incertain.
T1_GATEKEEPER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(T1_VALID_STATUSES)},
        "reasoning": {"type": "string"},
        "brand": {"type": "string"},
        "classification": {"type": "string"},
    },
    "required": ["status", "reasoning", "brand"],
}

# Même contrat que ci-dessus, au format "json_schema" structuré des API compatibles OpenAI (Qwen
# via TokenRouter). `strict: True` + `additionalProperties: False` + les 4 champs tous `required`
# (contrainte du mode strict — pas de champ optionnel) : `classification` manquante doit donc être
# la chaîne littérale "NULL", déjà le comportement demandé par le prompt quand le Portier est
# incertain — pas un assouplissement du contrat.
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


class DealAnalyzer:
    def __init__(self, logger: logging.Logger = None):
        self.models = {}
        self._model_error_last_notified = {}
        # Index de taxonomie mémorisé : `canonicalize()` le reconstruisait pour CHAQUE annonce
        # analysée (200 nœuds parcourus à chaque fois) alors qu'il ne change qu'avec la config.
        self._taxonomy_index = None
        self._taxonomy_index_source = None
        # Chantier H (porté 2026-09-22) : `bot.py::_dispatch_analysis_batch` appelle désormais
        # cette même instance depuis plusieurs threads worker en parallèle (avant, un seul thread
        # par utilisateur appelait `analyze_deal` séquentiellement) — `self.models`/
        # `self._taxonomy_index` sont de simples caches "vérifier-puis-écrire" jamais protégés
        # jusqu'ici. Un seul verrou pour les deux : leur construction est rapide et purement
        # locale (aucun appel réseau tenu sous le verrou), donc pas de risque de contention
        # significative ni de deadlock croisé.
        self._cache_lock = threading.Lock()
        # Logger par-utilisateur (Firestore/LogViewer) injecté par bot.py ; repli sur le
        # logger de module si non fourni (scripts autonomes/tests).
        self.logger = logger or logging.getLogger(__name__)
        if not GEMINI_API_KEY:
            self.logger.warning("⚠️ Pas de clé API Gemini fournie.")
            return
        
        genai.configure(api_key=GEMINI_API_KEY)
        try:
            model_list = [f"ID: {m.name} | Display Name: {m.display_name}" for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            self.logger.info("--- Modèles Gemini Disponibles ---\n" + "\n".join(model_list))
        except Exception as e:
            self.logger.critical(f"CRITICAL: Impossible de lister les modèles Gemini : {e}", exc_info=True)

    def _get_model(self, model_name, system_instruction=None, response_schema=None):
        # `response_schema` fait partie de la clé de cache : un même modèle peut être appelé
        # avec ou sans schéma structuré selon l'appelant (T1 avec schéma, T2/T3 sans) — sans ça,
        # la première instance mise en cache déciderait pour tous les appels suivants au même
        # modèle, schéma ou pas (Chantier H, porté 2026-09-22).
        cache_key = (model_name, hash(str(system_instruction)), hash(str(response_schema)))
        with self._cache_lock:
            if cache_key not in self.models:
                try:
                    generation_config = {"response_mime_type": "application/json", "temperature": 0.1}
                    if response_schema is not None:
                        generation_config["response_schema"] = response_schema
                    self.models[cache_key] = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_instruction,
                        generation_config=generation_config
                    )
                    self.logger.info(f"🤖 Modèle Gemini initialisé : {model_name}")
                except Exception as e:
                    self.logger.error(f"⚠️ Erreur init {model_name} : {e}")
                    return None
            return self.models[cache_key]

    def _download_and_optimize_image(self, url, max_size=2048):
        try:
            if not url or "via.placeholder.com" in url: return None
            response = requests.get(url, timeout=10)
            if response.status_code != 200: return None
            
            img = Image.open(BytesIO(response.content))
            if img.size[0] > max_size or img.size[1] > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            return img.convert("RGB") if img.mode in ("RGBA", "P") else img
        except Exception as e:
            self.logger.warning(f"⚠️ Impossible de traiter l'image {url}: {e}")
            return None

    def _clean_json_response(self, text_response):
        match = re.search(r'```json\s*([\s\S]*?)\s*```', text_response)
        return match.group(1).strip() if match else text_response.strip()

    def _construct_base_user_prompt(self, listing_data, main_prompt_template, taxonomy_data, few_shot_examples=None):
        """Construit le prompt utilisateur de base (DRY)"""
        prompt_lines = main_prompt_template if isinstance(main_prompt_template, list) else str(main_prompt_template).split('\n')
        main_prompt_str = "\n".join(prompt_lines)
        
        examples_str = ""
        if few_shot_examples:
            examples_lines = few_shot_examples if isinstance(few_shot_examples, list) else str(few_shot_examples).split('\n')
            examples_str = "\n".join(examples_lines) + "\n\n"

        # sort_keys=True : garantit un préfixe identique octet pour octet entre threads/
        # redémarrages (le cache implicite Gemini est un match de préfixe exact) — sans ça,
        # l'ordre des clés d'un dict Python n'est pas garanti stable d'un process à l'autre.
        taxonomy_str = json.dumps(taxonomy_data, indent=2, ensure_ascii=False, sort_keys=True)

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
        
    def _is_model_unavailable_error(self, error_text):
        """Détecte si une erreur Gemini correspond à un modèle introuvable/retiré/non supporté."""
        needle = str(error_text).lower()
        return any(marker in needle for marker in ("404", "not found", "not supported", "is not supported for"))

    def _notify_model_unavailable(self, model_name, error_text, user_email):
        """Alerte email (throttlée à 1x/24h par modèle) si un modèle semble avoir été retiré."""
        if not user_email:
            return
        now = time.time()
        last_notified = self._model_error_last_notified.get(model_name, 0)
        if now - last_notified < 86400:  # 24h
            return
        self._model_error_last_notified[model_name] = now
        try:
            NotificationService.notify_model_error(model_name, error_text, user_email, logger=self.logger)
        except Exception as e:
            self.logger.error(f"⚠️ Échec de l'envoi de l'alerte modèle indisponible : {e}")

    def _notify_gatekeeper_failure(self, provider_label, error_text, user_email):
        """Alerte email (throttlée à 1x/24h par fournisseur) sur un échec du Portier T1 réel qui
        n'est PAS identifié comme une dépréciation de modèle — distinct de
        `_notify_model_unavailable` (ex: une image tronquée téléchargée depuis Marketplace ne
        doit pas affirmer à tort qu'un modèle Gemini a été retiré). Chantier H, porté depuis dev
        le 2026-09-22 — voir `_is_model_unavailable_error` pour la distinction entre les deux cas."""
        if not user_email:
            return
        now = time.time()
        last_notified = self._model_error_last_notified.get(provider_label, 0)
        if now - last_notified < 86400:  # 24h
            return
        self._model_error_last_notified[provider_label] = now
        try:
            NotificationService.notify_gatekeeper_failure(provider_label, error_text, user_email, logger=self.logger)
        except Exception as e:
            self.logger.error(f"⚠️ Échec de l'envoi de l'alerte Portier en échec : {e}")

    def _call_gemini_json(self, model_name, content_parts, user_email=None, max_retries=1, response_schema=None):
        """Méthode utilitaire DRY pour appeler Gemini et parser le JSON."""
        model = self._get_model(model_name, response_schema=response_schema)
        if not model:
            return None, f"Modèle {model_name} non disponible."
            
        current_parts = list(content_parts)
        for attempt in range(max_retries + 1):
            try:
                response = model.generate_content(current_parts)
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    image_count = sum(1 for p in current_parts if isinstance(p, Image.Image))
                    self.logger.info(
                        f"[tokens] model={model_name} images={image_count} "
                        f"in={getattr(usage, 'prompt_token_count', 0)} "
                        f"out={getattr(usage, 'candidates_token_count', 0)} "
                        f"cached={getattr(usage, 'cached_content_token_count', 0)} "
                        f"total={getattr(usage, 'total_token_count', 0)}"
                    )
                cleaned_text = self._clean_json_response(response.text)
                result = json.loads(cleaned_text)
                if isinstance(result, list):
                    # Gemini répond parfois avec un tableau JSON au lieu d'un objet
                    # (ex: [{...}]) — on normalise en dict pour que tous les appelants
                    # (T1/T2/T3) puissent utiliser .get()/["clé"]= sans planter.
                    result = result[0] if result and isinstance(result[0], dict) else {}
                return result, None
            except json.decoder.JSONDecodeError as e:
                self.logger.warning(f"⚠️ JSON invalide généré par {model_name} (tentative {attempt+1}/{max_retries+1}) : {e}")
                if attempt == max_retries:
                    self.logger.error(f"❌ Impossible de parser le JSON après {max_retries+1} tentatives. Réponse brute: {getattr(response, 'text', 'Aucun texte')[:500]}...")
                    return None, f"Erreur de format JSON: {e}"
                
                # Ajout d'une directive forte pour la tentative suivante
                retry_warning = "CRITICAL: The previous JSON output was invalid. Ensure ALL strings are properly escaped (e.g. use \\\" for quotes inside strings) and NO trailing commas exist. Output ONLY valid JSON."
                if isinstance(current_parts[0], str):
                    current_parts[0] = current_parts[0] + "\n\n" + retry_warning
                else:
                    current_parts.insert(0, retry_warning)
            except Exception as e:
                self.logger.error(f"❌ Erreur avec le modèle {model_name}: {e}")
                if self._is_model_unavailable_error(e):
                    self._notify_model_unavailable(model_name, str(e), user_email)
                return None, str(e)

    def _call_openai_compatible_json(self, prompt, images, model_name, api_key, base_url, response_format=None):
        """Chantier H (porté depuis dev le 2026-09-22) : appelle un modèle compatible OpenAI
        (Qwen via TokenRouter, etc.) et parse le JSON, avec la même tolérance que
        `_call_gemini_json` (accolades ```json```). Réutilise les images DÉJÀ téléchargées (objets
        PIL) — pas de second téléchargement des mêmes URLs. Ne lève jamais : renvoie toujours
        (dict|None, erreur|None). Utilisée à la fois pour la décision T1 réelle quand Qwen est le
        fournisseur primaire (`T1_GATEKEEPER_PROVIDER`) et pour l'observation miroir best-effort
        de l'autre fournisseur — dans les deux cas l'appelant décide comment traiter une erreur
        (fail-open pour la décision réelle, silencieusement ignorée pour l'observation).

        `response_format` : mode JSON large (`{"type": "json_object"}`, par défaut si omis) ou
        schéma structuré strict (`{"type": "json_schema", ...}`, voir
        `T1_GATEKEEPER_OPENAI_JSON_SCHEMA`) — au choix de l'appelant."""
        if not api_key:
            return None, "Clé API manquante."
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)
            content = [{"type": "text", "text": prompt}]
            for img in images:
                buf = BytesIO()
                img.save(buf, format="JPEG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": content}],
                response_format=response_format or {"type": "json_object"},
            )
            cleaned_text = self._clean_json_response(response.choices[0].message.content.strip())
            result = json.loads(cleaned_text)
            if isinstance(result, list):
                result = result[0] if result and isinstance(result[0], dict) else {}
            return result, None
        except Exception as e:
            self.logger.error(f"❌ Erreur avec le modèle {model_name} (TokenRouter) : {e}")
            return None, str(e)

    def _call_t1_provider(self, provider, full_prompt_t1, images, gatekeeper_model_name, user_email=None):
        """Chantier H (porté depuis dev le 2026-09-22) : point d'appel UNIQUE pour n'importe
        lequel des deux fournisseurs T1 (Qwen via TokenRouter, ou Gemini Flash-Lite), avec
        exactement le même prompt et le schéma structuré correspondant — réutilisé à la fois par
        le décideur réel et l'observation miroir, pour qu'un futur changement de l'appel (timeout,
        retry, format) ne puisse plus être fait dans un seul des deux endroits sans désynchroniser
        décision et observation."""
        if provider == "qwen":
            if not TOKENROUTER_API_KEY:
                return None, "Clé API TokenRouter manquante."
            return self._call_openai_compatible_json(
                full_prompt_t1, images, T1_OBSERVATION_QWEN_MODEL, TOKENROUTER_API_KEY, TOKENROUTER_BASE_URL,
                response_format=T1_GATEKEEPER_OPENAI_JSON_SCHEMA,
            )
        return self._call_gemini_json(
            gatekeeper_model_name, [full_prompt_t1] + images, user_email,
            response_schema=T1_GATEKEEPER_RESPONSE_SCHEMA,
        )

    def _run_t1_shadow_observation(self, full_prompt_t1, images, shadow_provider, gatekeeper_model_name, user_email=None):
        """Chantier H (porté depuis dev le 2026-09-22) — OBSERVATION EN MIROIR : rejoue le
        Portier avec EXACTEMENT le même prompt sur le fournisseur T1 qui N'EST PAS le décideur
        réel (`T1_GATEKEEPER_PROVIDER`), pour continuer à accumuler de la comparaison en
        conditions réelles après la bascule — n'influence JAMAIS `gatekeeper_status` ni la
        décision accept/reject réelle. Décideur "qwen" (défaut) -> observation sous
        `flashliteGatekeeper*` ; décideur "gemini" (repli) -> observation sous `qwenGatekeeper*`.

        Best-effort strict : toute erreur (clé absente, fournisseur indisponible, JSON invalide)
        est absorbée ici et ne doit jamais faire échouer l'analyse réelle qui l'entoure —
        coupe-circuit `T1_OBSERVATION_ENABLED` pour désactiver sans redéploiement si besoin.
        """
        if not T1_OBSERVATION_ENABLED:
            return {}
        prefix = "qwenGatekeeper" if shadow_provider == "qwen" else "flashliteGatekeeper"
        t0 = time.monotonic()
        result, err = self._call_t1_provider(shadow_provider, full_prompt_t1, images, gatekeeper_model_name, user_email)
        latency_s = round(time.monotonic() - t0, 1)
        if err or not result:
            self.logger.warning(f"   🔬 [Observation T1/{shadow_provider}] échec (ignoré, n'affecte pas l'analyse) : {err}")
            return {f"{prefix}Error": err, f"{prefix}LatencyS": latency_s}
        return {
            f"{prefix}Verdict": (result.get('status') or result.get('verdict') or None),
            f"{prefix}Brand": result.get('brand'),
            f"{prefix}Classification": result.get('classification'),
            f"{prefix}LatencyS": latency_s,
        }

    def analyze_deal(self, listing_data, firestore_config=None, force_expert=False, user_comment=None, user_email=None):
        """Cascade 3-Tiers, puis canonicalisation de la classification renvoyée par l'IA.

        La canonicalisation est faite ICI, sur le résultat final, plutôt que dans chacun des 5
        points de sortie de la cascade : un seul endroit à maintenir, impossible d'en oublier un.
        """
        result = self._run_analysis_cascade(listing_data, firestore_config, force_expert, user_comment, user_email)
        taxonomy = (firestore_config or {}).get('analysisConfig', {}).get('taxonomy', DEFAULT_TAXONOMY)
        return self._canonicalize_classification(result, taxonomy)

    def analyze_deal_light(self, listing_data, firestore_config=None, user_email=None):
        """Backfill léger : reconstitue UNIQUEMENT les champs structurés (scores/classification/
        marge/verdict) d'une annonce déjà VENDUE dont `aiAnalysis` a été perdu (bug `ArrayUnion`
        de `mark_deal_as_sold()`, corrigé le 2026-08-12 — voir JOURNAL.md), sans repasser par le
        Portier T1 (inutile : l'annonce est déjà vendue, pas besoin de la re-filtrer) ni risquer de
        déclencher l'Expert Pro T3 (coûteux, inutile pour de l'historique déjà écoulé). Un seul
        appel au modèle Analyste T2, avec une instruction dédiée (`sold_backfill_instruction`)
        demandant un JSON réduit sans champ de texte libre (pas de `analysis`/`reasoning`/
        `summary`/`visual_inspection`) — économise à la fois des appels entiers (T1, risque T3) et
        des tokens de sortie par appel, par rapport à `analyze_deal()`. Utilisé par
        `backend/scripts/backfill_sold_scores.py`.

        `model_used` est tagué `"backfill_leger -> {modèle}"` (2 maillons) plutôt qu'un simple nom
        de modèle : `StatsView.jsx::modelChainTokens` compte les maillons pour détecter qu'une
        annonce a atteint le Tier 2 (`length >= 2`) — un maillon unique ferait sous-compter ces
        annonces dans le Funnel alors qu'elles ont bien été scorées.
        """
        if not GEMINI_API_KEY:
            return {"verdict": "ERROR", "reasoning": "La clé API Gemini n'est pas configurée."}

        config = (firestore_config or {}).get('analysisConfig', {})
        analyst_model_name = config.get('mainModel', 'gemini-3.7-flash')
        taxonomy = config.get('taxonomy', DEFAULT_TAXONOMY)
        few_shot_examples = config.get('fewShotExamples', DEFAULT_FEW_SHOT_EXAMPLES)

        image_urls = (listing_data.get('imageUrls') or [listing_data.get('imageUrl')])[:8]
        images = [img for url in image_urls if (img := self._download_and_optimize_image(url))]

        base_prompt = self._construct_base_user_prompt(
            listing_data, config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT), taxonomy, few_shot_examples
        )
        backfill_instruction = config.get('soldBackfillInstruction', DEFAULT_SOLD_BACKFILL_INSTRUCTION)
        if isinstance(backfill_instruction, list):
            backfill_instruction = "\n".join(backfill_instruction)
        full_prompt = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE BACKFILL (VENTE HISTORIQUE) ---\n{backfill_instruction}"

        self.logger.info(f"   🩹 Backfill léger ({analyst_model_name}) : {listing_data.get('title', 'Inconnu')}")
        result, err = self._call_gemini_json(analyst_model_name, [full_prompt] + images, user_email)
        if err or not result:
            return {"verdict": "ERROR", "reasoning": f"Erreur backfill léger : {err}", "model_used": f"backfill_leger -> {analyst_model_name} (Error)"}

        result["model_used"] = f"backfill_leger -> {analyst_model_name}"
        return self._canonicalize_classification(result, taxonomy)

    def _get_taxonomy_index(self, taxonomy):
        """Index de taxonomie mémorisé, reconstruit uniquement si la taxonomie a changé.

        Comparaison par identité : `ConfigManager` réutilise le même objet de configuration entre
        deux analyses, donc l'index n'est reconstruit qu'après une vraie modification de la config
        (et une comparaison par identité qui échouerait à tort ne coûterait qu'une reconstruction,
        jamais un résultat faux). Verrouillé (`_cache_lock`, partagé avec `_get_model`) depuis que
        plusieurs workers peuvent appeler cette méthode en parallèle (Chantier H, porté
        2026-09-22) : sans ça, deux threads pourraient interfolier lecture/écriture de
        `_taxonomy_index`/`_taxonomy_index_source`.
        """
        with self._cache_lock:
            if self._taxonomy_index is None or self._taxonomy_index_source is not taxonomy:
                self._taxonomy_index = build_taxonomy_index(taxonomy)
                self._taxonomy_index_source = taxonomy
            return self._taxonomy_index

    def _canonicalize_classification(self, result, taxonomy):
        """Remplace `classification` par son chemin canonique complet, ou la retire si invalide.

        Le prompt EXIGE désormais un chemin complet, mais le prompt ne garantit rien (aucun
        `response_schema` côté SDK) : cette validation serveur est le vrai garde-fou. Une valeur
        ambiguë ou inconnue est écartée plutôt que stockée telle quelle — une annonce non classée
        est corrigeable à la main dans l'app, une annonce rangée dans la mauvaise catégorie passe
        inaperçue (c'est ainsi que des étuis se retrouvaient comptés comme des guitares).
        """
        if not isinstance(result, dict):
            return result

        raw = result.get('classification')
        if not raw:
            return result

        canonical, reason = canonicalize_classification(raw, taxonomy, self._get_taxonomy_index(taxonomy))
        if canonical:
            if canonical != raw:
                self.logger.info(f"   🧭 Classification normalisée : '{raw}' -> '{canonical}' ({reason})")
            result['classification'] = canonical
        else:
            self.logger.warning(
                f"   ⚠️ Classification rejetée ('{raw}', {reason}) : absente de la taxonomie ou "
                f"ambiguë (nom porté par plusieurs branches). L'annonce restera non classée — "
                f"corrigeable manuellement depuis la fiche."
            )
            result['classification'] = None
            result['classification_rejected'] = raw

        return result

    def _attach_gatekeeper_metadata(self, result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation):
        """Rattrapage Chantier G (2026-09-19) : attache marque/classification/verdict BRUTS du
        Portier à `result`, en place, et le retourne — nécessaires pour retrouver, sans rappeler
        le Portier, la classification d'une annonce `NOT_PROMOTED` quand le filtre
        `activeSearchFamilies` change (voir `bot.py::reevaluate_not_promoted`). `qwen_observation`
        (Chantier H, porté depuis dev le 2026-09-22) : merge l'observation miroir best-effort
        (`flashliteGatekeeper*`/`qwenGatekeeper*`, voir `_run_t1_shadow_observation`) — jamais
        utilisée pour la décision réelle. Stockée sans colonne Postgres dédiée : `result` devient
        `analysis_data`, qui atterrit tel quel dans `ai_analysis_raw` (JSONB, voir
        `deal_mapping.py::map_deal`) — aucune promotion de colonne nécessaire pour des champs
        purement d'observation, jamais lus par le frontend."""
        result["gatekeeperBrand"] = gatekeeper_brand
        result["gatekeeperClassification"] = gatekeeper_classification
        result["gatekeeperVerdict"] = gatekeeper_status
        result.update(qwen_observation)
        return result

    def _run_analysis_cascade(self, listing_data, firestore_config=None, force_expert=False, user_comment=None, user_email=None):
        """Point d'entrée public : point de sortie UNIQUE pour l'attache des métadonnées Portier
        (`_attach_gatekeeper_metadata`), quel que soit le chemin emprunté par `_run_analysis_cascade_body`
        (rejet T1, hors-recherche-active, erreur T2, échec T3 avec repli T2, succès T2/T3) — un futur
        point de sortie ajouté au corps de la cascade n'a qu'à retourner le même tuple `(result,
        gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)`, l'attache
        elle-même ne peut plus être oubliée à un site d'appel particulier (rattrapage Chantier G,
        2026-09-19)."""
        if not GEMINI_API_KEY:
            return {"verdict": "ERROR", "reasoning": "La clé API Gemini n'est pas configurée."}

        result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation = self._run_analysis_cascade_body(
            listing_data, firestore_config, force_expert, user_comment, user_email,
        )
        return self._attach_gatekeeper_metadata(
            result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation
        )

    def _run_analysis_cascade_body(self, listing_data, firestore_config=None, force_expert=False, user_comment=None, user_email=None):
        """Corps de la cascade 3-Tiers — chaque point de sortie retourne
        `(result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)`,
        jamais un dict déjà attaché (voir `_run_analysis_cascade`, seul appelant, qui fait
        l'attache une fois pour tous les chemins)."""
        config = firestore_config.get('analysisConfig', {})
        # Défauts alignés sur GEMINI_MODELS (config.py) — gemini-2.5-* est retiré par Google en
        # octobre 2026, ces fallbacks codés en dur sont ce qui est réellement utilisé si un compte
        # n'a jamais persisté sa config (voir CLAUDE.md § Points d'Attention Critiques).
        gatekeeper_model_name = config.get('gatekeeperModel', 'gemini-3.5-flash-lite')
        analyst_model_name = config.get('mainModel', 'gemini-3.7-flash')
        # Rétrocompatibilité : 'proModel' est la nouvelle clé, 'expertModel' est l'ancienne (encore écrite par le frontend)
        expert_pro_model_name = config.get('proModel') or config.get('expertModel', 'gemini-3.1-pro-preview')

        taxonomy = config.get('taxonomy', DEFAULT_TAXONOMY)
        few_shot_examples = config.get('fewShotExamples', DEFAULT_FEW_SHOT_EXAMPLES)
        rejection_verdicts = config.get('rejectionVerdicts', DEFAULT_REJECTION_VERDICTS)

        self.logger.info(f"🤖 Analyse Cascade pour : {listing_data.get('title', 'Inconnu')} (Force Expert: {force_expert})")

        # Téléchargement des images
        image_urls = (listing_data.get('imageUrls') or [listing_data.get('imageUrl')])[:8]
        images = [img for url in image_urls if (img := self._download_and_optimize_image(url))]

        # 1. Construction du Prompt de Base (DRY : Fait une seule fois)
        base_prompt = self._construct_base_user_prompt(listing_data, config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT), taxonomy, few_shot_examples)
        if user_comment:
            base_prompt += (
                f"\n\n### CORRECTION UTILISATEUR (PRIORITAIRE)\n"
                f"L'utilisateur a fourni la correction/précision suivante suite à une analyse précédente. "
                f"Tiens-en compte en priorité, elle prime sur ta propre analyse visuelle si contradiction :\n"
                f"\"{user_comment}\"\n"
            )

        model_chain = []
        gatekeeper_status = "MANUAL_RETRY"
        gatekeeper_reason = "Analyse experte demandée manuellement."
        gatekeeper_brand = None
        gatekeeper_classification = None
        # Chantier H (porté depuis dev le 2026-09-22) — observation miroir (jamais utilisée pour
        # la décision accept/reject réelle, voir _run_t1_shadow_observation). Fusionnée dans les 5
        # dicts de retour ci-dessous via _attach_gatekeeper_metadata, comme gatekeeperBrand/
        # gatekeeperClassification/gatekeeperVerdict.
        qwen_observation = {}

        # ==========================================
        # PHASE 1 : TIER 1 - PORTIER (bascule 2026-09-20 : Qwen par défaut, voir config.py)
        # ==========================================
        if not force_expert:
            t1_real_model_name = T1_OBSERVATION_QWEN_MODEL if T1_GATEKEEPER_PROVIDER == "qwen" else gatekeeper_model_name
            self.logger.info(f"   🛡️ Étape 1 : Portier ({t1_real_model_name})")
            model_chain.append(t1_real_model_name)
            gatekeeper_instruction = config.get('gatekeeperVerbosityInstruction', DEFAULT_GATEKEEPER_INSTRUCTION)
            if isinstance(gatekeeper_instruction, list):
                gatekeeper_instruction = "\n".join(gatekeeper_instruction)
            full_prompt_t1 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE PORTIER ---\n{gatekeeper_instruction}"

            # T1_GATEKEEPER_PROVIDER détermine qui décide réellement (accept/reject) — "qwen" par
            # défaut, "gemini" en repli. L'autre fournisseur continue de tourner en miroir,
            # best-effort, uniquement pour accumuler de la comparaison (jamais lu pour la
            # décision) — lancé en parallèle pour ne pas cumuler les deux latences sur chaque
            # annonce (~22s Qwen vs ~5s Gemini, peu importe lequel est réel).
            primary_provider = T1_GATEKEEPER_PROVIDER
            shadow_provider = "gemini" if primary_provider == "qwen" else "qwen"

            shadow_result_holder = [{}]

            def _observe_shadow():
                shadow_result_holder[0] = self._run_t1_shadow_observation(
                    full_prompt_t1, images, shadow_provider, gatekeeper_model_name, user_email
                )

            shadow_thread = threading.Thread(target=_observe_shadow, daemon=True)
            shadow_thread.start()

            result_t1, err_t1 = self._call_t1_provider(
                primary_provider, full_prompt_t1, images, gatekeeper_model_name, user_email
            )

            shadow_thread.join()
            qwen_observation = shadow_result_holder[0]

            if err_t1 or not result_t1:
                # Fail-open vers l'Analyste — mais avec une alerte explicite : contrairement à un
                # simple retry Gemini, un échec du DÉCIDEUR T1 RÉEL revient à ne plus filtrer
                # AUCUNE annonce (100% promues en Tier 2) tant que ça persiste.
                gatekeeper_status = "ERROR_GATEKEEPER"
                gatekeeper_reason = err_t1 or "Le portier a planté silencieusement."
                self.logger.error(f"   ❌ [Portier réel/{primary_provider}] échec — fail-open vers l'Analyste (aucun filtrage T1 pour cette annonce) : {gatekeeper_reason}")
                # Deux alertes distinctes : ne prétendre "modèle retiré" que si l'erreur y
                # ressemble vraiment (_is_model_unavailable_error) — sinon (image tronquée, panne
                # réseau/TokenRouter transitoire, etc.), une alerte honnête qui ne présume pas la
                # cause. Les deux sont throttlées séparément (clé distincte).
                if self._is_model_unavailable_error(gatekeeper_reason):
                    self._notify_model_unavailable(f"T1-{primary_provider}", gatekeeper_reason, user_email)
                else:
                    self._notify_gatekeeper_failure(f"T1-{primary_provider}", gatekeeper_reason, user_email)
            else:
                gatekeeper_status = (result_t1.get('status') or result_t1.get('verdict') or 'UNKNOWN').upper()
                gatekeeper_reason = result_t1.get('reason') or result_t1.get('reasoning') or 'Pas de raison fournie.'
                gatekeeper_brand = result_t1.get('brand')
                gatekeeper_classification = result_t1.get('classification')

                if gatekeeper_status == 'UNKNOWN':
                    gatekeeper_status = 'ERROR'
                    gatekeeper_reason = f"Réponse IA invalide. Brut : {str(result_t1)}"

                self.logger.info(f"   👉 Verdict Portier : {gatekeeper_status} ({gatekeeper_reason})")

                legacy_rejection = ['REJECTED', 'REJECTED (SERVICE)']
                if gatekeeper_status in rejection_verdicts or gatekeeper_status in legacy_rejection or gatekeeper_status.startswith('REJECTED'):
                    return (
                        {
                            "verdict": gatekeeper_status, "reasoning": gatekeeper_reason,
                            "classification": gatekeeper_classification,
                            "model_used": " -> ".join(model_chain),
                        },
                        gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation,
                    )

                # ==========================================
                # RATTRAPAGE CHANTIER G : ROUTAGE PAR RECHERCHE ACTIVE (promotion large)
                # ==========================================
                # Le mode par défaut ("tout analyser, filtrer après") reste inchangé tant
                # qu'aucune recherche active n'est configurée (`activeSearchFamilies` vide/absent).
                # Quand une recherche est active, seule une correspondance sur la FAMILLE de forme
                # (`gatekeeper_classification`, déjà produite par le Portier — aucun nouvel appel
                # ni champ de prompt) promeut vers T2/T3 ; le scraping et le Portier lui-même
                # continuent de tourner sur 100% des annonces, seul ce routage post-T1 change.
                # Garde-fou non négociable : un verdict pépite-tier (T1_PEPITE_TIER_VERDICTS)
                # passe TOUJOURS, correspondance ou non — ne jamais cacher une pépite hors-filtre.
                # Second garde-fou (Chantier H) : un verdict d'erreur (T1_ERROR_STATUSES — Portier
                # planté ou réponse malformée) n'a par définition aucune classification fiable ;
                # sans ce garde-fou, il se retrouvait routé vers NOT_PROMOTED (classification vide
                # ⇒ aucune correspondance) au lieu du fail-open habituel vers l'Analyste.
                active_search_families = config.get('activeSearchFamilies') or []
                if (
                    active_search_families
                    and gatekeeper_status not in T1_PEPITE_TIER_VERDICTS
                    and gatekeeper_status not in T1_ERROR_STATUSES
                ):
                    matches_active_search = matches_active_search_family(gatekeeper_classification, active_search_families)
                    if not matches_active_search:
                        self.logger.info(
                            f"   🔎 Hors recherche active ({', '.join(active_search_families)}) "
                            f"et pas une pépite ({gatekeeper_status}) — non promue vers T2/T3."
                        )
                        return (
                            {
                                "verdict": "NOT_PROMOTED",
                                "reasoning": (
                                    f"Ne correspond à aucune recherche active "
                                    f"({', '.join(active_search_families)}) et n'est pas jugée "
                                    f"pépite potentielle par le Portier."
                                ),
                                "classification": gatekeeper_classification,
                                "model_used": " -> ".join(model_chain),
                            },
                            gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation,
                        )
        else:
            self.logger.info("   ⏩ Portier sauté (Force Expert).")

        # ==========================================
        # PHASE 2 : TIER 2 - ANALYSTE (Flash)
        # ==========================================
        self.logger.info(f"   🔍 Étape 2 : Analyste ({analyst_model_name}) - Structuration & Scores...")
        model_chain.append(analyst_model_name)
        analyst_instruction = config.get('analystVerbosityInstruction', DEFAULT_ANALYST_INSTRUCTION)
        if isinstance(analyst_instruction, list):
            analyst_instruction = "\n".join(analyst_instruction)
        full_prompt_t2 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE ANALYSTE ---\n{analyst_instruction}"
        
        result_t2, err_t2 = self._call_gemini_json(analyst_model_name, [full_prompt_t2] + images, user_email)
        
        if err_t2 or not result_t2:
            return (
                {
                    "verdict": gatekeeper_status, "reasoning": f"{gatekeeper_reason}\n\nErreur Tier 2 Analyste: {err_t2}",
                    "model_used": " -> ".join(model_chain) + " (Error)",
                },
                gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation,
            )

        # Formatage des variables pour la logique conditionnelle
        deal_score = result_t2.get('deal_score', 0)
        auth_score = result_t2.get('authenticity_score', 10) # 10 par défaut pour pas trigger fausement
        resto_score = result_t2.get('restoration_interest_score', 0)
        confidence = result_t2.get('confidence', 1.0)
        verdict = result_t2.get('verdict', '')
        
        # Extraction du prix
        numeric_price = ListingParser.extract_price_from_text(str(listing_data.get('price', '') or ''))
        
        self.logger.info(f"   📊 Scores T2 -> Deal: {deal_score} | Auth: {auth_score} | Resto: {resto_score} | Conf: {confidence} | Prix: {numeric_price}")

        trigger_reason = None
        
        if force_expert:
            trigger_reason = "Analyse Pro forcée manuellement"
        elif numeric_price > config.get('proTriggerPriceThreshold', DEFAULT_PRO_PRICE_THRESHOLD) and deal_score >= 4:
            trigger_reason = f"Prix élevé ({numeric_price}) avec score correct ({deal_score})"
        elif deal_score >= config.get('proTriggerDealScoreThreshold', DEFAULT_PRO_DEAL_SCORE_THRESHOLD):
            trigger_reason = f"Score attractivité critique ({deal_score})"
        elif deal_score >= config.get('proTriggerCombinedDealScore', DEFAULT_PRO_COMBINED_DEAL_SCORE) and resto_score >= config.get('proTriggerRestoScoreThreshold', DEFAULT_PRO_RESTO_SCORE_THRESHOLD):
             trigger_reason = f"Combo Jackpot : Score correct ({deal_score}) + Restaurabilité majeure ({resto_score})"
        elif auth_score <= config.get('proTriggerAuthScoreThreshold', DEFAULT_PRO_AUTH_SCORE_THRESHOLD):
            trigger_reason = f"Doute authenticité potentiel ({auth_score})"
        elif confidence < config.get('proTriggerConfidenceThreshold', DEFAULT_PRO_CONFIDENCE_THRESHOLD):
            trigger_reason = f"Faible confiance T2 ({confidence})"
        elif verdict == 'COLLECTION':
            trigger_reason = "Verdict COLLECTION (Double validation requise)"

        # ==========================================
        # PHASE 3 : TIER 3 - EXPERT PRO (Conditionnel)
        # ==========================================
        if trigger_reason:
            self.logger.info(f"   ⭐ Étape 3 (DÉCLENCHÉE) : Expert Pro ({expert_pro_model_name}) - Motif : {trigger_reason}")
            model_chain.append(expert_pro_model_name)
            
            expert_context_raw = config.get('expertProContextInstruction', DEFAULT_EXPERT_CONTEXT)
            if isinstance(expert_context_raw, list):
                expert_context_raw = "\n".join(expert_context_raw)
            
            # Contextualisation de l'expert pro avec le json T2
            context_t3 = expert_context_raw.format(
                status=verdict,
                reasoning=result_t2.get('summary', 'Analyse rapide T2 terminée.')
            )
            
            # base_prompt avant context_t3 (et non l'inverse) : aligne T3 sur le pattern déjà
            # correct de T1/T2 (bloc statique taxonomie/prompt de base en tête, addendum
            # spécifique au Tier après) pour laisser le cache implicite Gemini matcher le
            # préfixe statique commun — l'ordre précédent plaçait le contexte T2 (dynamique,
            # différent à chaque annonce) en tête, détruisant tout préfixe cacheable pour T3.
            full_prompt_t3 = f"{base_prompt}\n\n{context_t3}"
            
            result_t3, err_t3 = self._call_gemini_json(expert_pro_model_name, [full_prompt_t3] + images, user_email)
            
            if err_t3 or not result_t3:
                self.logger.error(f"❌ Erreur Expert Pro, fallback sur T2. Erreur: {err_t3}")
                result_t2["model_used"] = " -> ".join(model_chain) + " (T3 Failed, fallback T2)"
                return (result_t2, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)

            # L'Expert Pro écrase le T2
            result_t3["model_used"] = " -> ".join(model_chain)
            result_t3["tier3_trigger"] = trigger_reason
            self.logger.info(f"   ✅ Verdict Expert Pro : {result_t3.get('verdict', 'N/A')} | Deal: {result_t3.get('deal_score', '?')} | Auth: {result_t3.get('authenticity_score', '?')} | Conf: {result_t3.get('confidence', '?')} | Résumé: {result_t3.get('summary', 'N/A')}")
            return (result_t3, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)

        else:
            self.logger.info("   ✋ Fin de l'analyse (Tier 3 non déclenché).")
            result_t2["model_used"] = " -> ".join(model_chain)
            return (result_t2, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)
