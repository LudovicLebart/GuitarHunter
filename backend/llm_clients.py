"""Clients LLM de `DealAnalyzer` (Gemini, API compatibles OpenAI : Qwen/TokenRouter, Dell/Ollama) et
contrat JSON du Portier T1 (verdicts valides + schémas). Extrait de `backend/analyzer.py` le 2026-10-02
(1000 lignes, une méthode de 337) SANS changement de comportement : les méthodes sont les mêmes, déplacées
dans un mixin que `DealAnalyzer` hérite — `self._call_gemini_json(...)`, `self._call_t1_provider(...)`, etc.
fonctionnent donc exactement comme avant (bot.py, scripts, tests). `backend/analyzer.py` ré-exporte les
constantes T1_* pour que `from backend.analyzer import T1_...` continue de marcher.

État supposé sur `self` (posé par `DealAnalyzer.__init__`) : `logger`, `models`, `_cache_lock`,
`_model_error_last_notified`. Les tests qui patchent `OpenAI`/`TOKENROUTER_API_KEY` doivent cibler
`backend.llm_clients`, plus `backend.analyzer`."""
import base64
import json
import threading
import time
from io import BytesIO

import google.generativeai as genai
from openai import OpenAI
from PIL import Image

from backend import llm_usage
from backend.notifications import NotificationService
from config import (
    TOKENROUTER_API_KEY,
    TOKENROUTER_BASE_URL,
    T1_OBSERVATION_QWEN_MODEL,
    T1_LOCAL_BASE_URL,
    T1_LOCAL_MODEL,
    T1_LOCAL_API_KEY,
    T1_LOCAL_MAX_CONCURRENCY,
    T1_LOCAL_TIMEOUT_SECONDS,
)
import re

# Un seul Dell pour tous les threads utilisateurs : sémaphore au niveau du module (voir config.py).
_T1_LOCAL_SEMAPHORE = threading.BoundedSemaphore(T1_LOCAL_MAX_CONCURRENCY)

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


class LLMClientsMixin:
    """Méthodes d'appel aux fournisseurs LLM (voir docstring du module)."""

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

    def _clean_json_response(self, text_response):
        match = re.search(r'```json\s*([\s\S]*?)\s*```', text_response)
        return match.group(1).strip() if match else text_response.strip()

    def _is_model_unavailable_error(self, error_text):
        """Détecte si une erreur Gemini correspond à un modèle introuvable/retiré/non supporté."""
        return llm_usage.is_model_unavailable(error_text)

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

    def _call_gemini_json(self, model_name, content_parts, user_email=None, max_retries=1, response_schema=None, action=None):
        """Méthode utilitaire DRY pour appeler Gemini et parser le JSON."""
        model = self._get_model(model_name, response_schema=response_schema)
        if not model:
            llm_usage.record(provider="gemini", model=model_name, action=action, ok=False, error_type="other")
            return None, f"Modèle {model_name} non disponible."
            
        current_parts = list(content_parts)
        for attempt in range(max_retries + 1):
            # Une ligne `llm_usage` par TENTATIVE (chaque tentative est facturée), ok ou non.
            usage_row = {"provider": "gemini", "model": model_name, "action": action, "latency_ms": None}
            t_call = time.monotonic()
            try:
                response = model.generate_content(current_parts)
                latency_ms = int((time.monotonic() - t_call) * 1000)
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
                    # Chantier C-0 : une ligne par appel dans Postgres (best-effort).
                    _in = getattr(usage, 'prompt_token_count', 0) or 0
                    _out = getattr(usage, 'candidates_token_count', 0) or 0
                    _thoughts = getattr(usage, 'thoughts_token_count', None)
                    if _thoughts is None:  # SDK ancien : déduire du total
                        _thoughts = max(0, (getattr(usage, 'total_token_count', 0) or 0) - _in - _out)
                    usage_row.update(
                        images=image_count, input_tokens=_in,
                        cached_tokens=getattr(usage, 'cached_content_token_count', 0) or 0,
                        output_tokens=_out, thoughts_tokens=_thoughts,
                    )
                usage_row["latency_ms"] = latency_ms
                cleaned_text = self._clean_json_response(response.text)
                result = json.loads(cleaned_text)
                if isinstance(result, list):
                    # Gemini répond parfois avec un tableau JSON au lieu d'un objet
                    # (ex: [{...}]) — on normalise en dict pour que tous les appelants
                    # (T1/T2/T3) puissent utiliser .get()/["clé"]= sans planter.
                    result = result[0] if result and isinstance(result[0], dict) else {}
                llm_usage.record(**usage_row)  # succès : enregistré APRÈS le parse, pas avant
                return result, None
            except json.decoder.JSONDecodeError as e:
                llm_usage.record(**usage_row, ok=False, error_type="json")
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
                if usage_row.get("latency_ms") is None:
                    usage_row["latency_ms"] = int((time.monotonic() - t_call) * 1000)
                llm_usage.record(**usage_row, ok=False, error_type=llm_usage.classify_error(e))
                self.logger.error(f"❌ Erreur avec le modèle {model_name}: {e}")
                if self._is_model_unavailable_error(e):
                    self._notify_model_unavailable(model_name, str(e), user_email)
                return None, str(e)

    def _call_openai_compatible_json(self, prompt, images, model_name, api_key, base_url, response_format=None, action=None, provider_label=None, timeout=60, max_retries=2):
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
        `T1_GATEKEEPER_OPENAI_JSON_SCHEMA`) — au choix de l'appelant.

        `provider_label` : valeur écrite dans `llm_usage.provider`. Par défaut déduite de `base_url`
        ("tokenrouter" ou "openai_compatible") ; les appels au Dell passent "local" pour qu'ils ne
        se confondent plus avec n'importe quel endpoint compatible OpenAI (avant le 2026-09-29, seul
        `model` les distinguait)."""
        provider = provider_label or ("tokenrouter" if "tokenrouter" in (base_url or "").lower() else "openai_compatible")
        usage_row = {"provider": provider, "model": model_name, "action": action, "images": len(images),
                     "latency_ms": None}
        t_start = time.monotonic()
        if not api_key:
            llm_usage.record(**usage_row, ok=False, error_type="no_key")
            return None, "Clé API manquante."
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)
            content = [{"type": "text", "text": prompt}]
            for img in images:
                buf = BytesIO()
                img.save(buf, format="JPEG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            t_call = time.monotonic()
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": content}],
                response_format=response_format or {"type": "json_object"},
            )
            latency_ms = int((time.monotonic() - t_call) * 1000)
            # Chantier C-0 : même ligne [tokens] que Gemini + enregistrement Postgres. `out` exclut
            # le raisonnement (reasoning_tokens), compté à part comme pour Gemini.
            usage = getattr(response, "usage", None)
            if usage:
                completion = getattr(usage, "completion_tokens", 0) or 0
                details = getattr(usage, "completion_tokens_details", None)
                reasoning = (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
                prompt_details = getattr(usage, "prompt_tokens_details", None)
                cached = (getattr(prompt_details, "cached_tokens", 0) or 0) if prompt_details else 0
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                self.logger.info(
                    f"[tokens] model={model_name} images={len(images)} in={prompt_tokens} "
                    f"out={max(0, completion - reasoning)} cached={cached} "
                    f"total={getattr(usage, 'total_tokens', 0) or 0}"
                )
                usage_row.update(input_tokens=prompt_tokens, cached_tokens=cached,
                                 output_tokens=max(0, completion - reasoning), thoughts_tokens=reasoning)
            usage_row["latency_ms"] = latency_ms
            cleaned_text = self._clean_json_response(response.choices[0].message.content.strip())
            result = json.loads(cleaned_text)
            if isinstance(result, list):
                result = result[0] if result and isinstance(result[0], dict) else {}
            llm_usage.record(**usage_row)  # succès : enregistré APRÈS le parse, pas avant
            return result, None
        except Exception as e:
            self.logger.error(f"❌ Erreur avec le modèle {model_name} ({provider}) : {e}")
            if usage_row.get("latency_ms") is None:
                usage_row["latency_ms"] = int((time.monotonic() - t_start) * 1000)
            llm_usage.record(**usage_row, ok=False, error_type=llm_usage.classify_error(e))
            return None, str(e)

    def _call_t1_provider(self, provider, full_prompt_t1, images, gatekeeper_model_name, user_email=None, action="t1_gatekeeper"):
        """Chantier H/I : point d'appel UNIQUE pour n'importe lequel des fournisseurs T1 ("local"
        Dell/Ollama, "qwen" via TokenRouter, ou "gemini" Flash-Lite), avec exactement le même
        prompt et le schéma structuré correspondant — réutilisé à la fois par la chaîne de
        décision réelle (`T1_PROVIDER_CHAIN`) et l'observation miroir historique, pour qu'un futur
        changement de l'appel (timeout, retry, format) ne puisse plus être fait dans un seul
        endroit sans désynchroniser décision et observation."""
        if provider == "local":
            # Sérialise les appels vers le Dell (voir T1_LOCAL_MAX_CONCURRENCY) : la file d'attente
            # se fait ici, hors timeout HTTP, et non dans Ollama où elle gonflait la latence et
            # déclenchait des timeouts/retries. 0 retry : la chaîne T1 gère déjà le repli.
            with _T1_LOCAL_SEMAPHORE:
                return self._call_openai_compatible_json(
                    full_prompt_t1, images, T1_LOCAL_MODEL, T1_LOCAL_API_KEY, T1_LOCAL_BASE_URL,
                    response_format=T1_GATEKEEPER_OPENAI_JSON_SCHEMA, action=action,
                    provider_label="local", timeout=T1_LOCAL_TIMEOUT_SECONDS, max_retries=0,
                )
        if provider == "qwen":
            # Clé absente : `_call_openai_compatible_json` la détecte lui-même, renvoie une erreur ET
            # enregistre l'échec dans `llm_usage` (error_type="no_key") — pas de garde-fou ici, sinon
            # l'échec ne laisserait aucune ligne.
            return self._call_openai_compatible_json(
                full_prompt_t1, images, T1_OBSERVATION_QWEN_MODEL, TOKENROUTER_API_KEY, TOKENROUTER_BASE_URL,
                response_format=T1_GATEKEEPER_OPENAI_JSON_SCHEMA, action=action,
            )
        return self._call_gemini_json(
            gatekeeper_model_name, [full_prompt_t1] + images, user_email,
            response_schema=T1_GATEKEEPER_RESPONSE_SCHEMA, action=action,
        )

    @staticmethod
    def _t1_model_name_for(provider, gatekeeper_model_name):
        """Nom de modèle correspondant à un fournisseur T1 — pour le logging (`model_chain`)."""
        if provider == "local":
            return T1_LOCAL_MODEL
        if provider == "qwen":
            return T1_OBSERVATION_QWEN_MODEL
        return gatekeeper_model_name
