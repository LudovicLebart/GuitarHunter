"""Leaf — niveau 2 (IA) : appel des modèles. Réutilise `DealAnalyzer` du bot (clients Gemini / compatibles OpenAI, enregistrement
`llm_usage`, alertes « modèle injoignable », sémaphore du Dell) sans le modifier.

Chaîne de fournisseurs, dans l'ordre configuré (`leafConfig.analysisConfig.providers`, défaut `local` puis `gemini`) : Qwen local sur
le Dell (gratuit), puis Gemini Flash en secours. Le premier fournisseur dont la réponse est UTILISABLE est retenu. Ne lève jamais :
renvoie (analyse | None, erreur | None). Chaque tentative est enregistrée dans `llm_usage` (action `leaf_t2`) par les clients."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from backend.leaf import ai_extract

ACTION = "leaf_t2"
PROVIDERS = ("local", "gemini")


class LeafAI:
    def __init__(self, analyzer: Any, logger: Optional[logging.Logger] = None):
        self.analyzer = analyzer
        self.log = logger or logging.getLogger(__name__)

    def _call_local(self, prompt: str) -> Tuple[Optional[dict], Optional[str], str]:
        import config
        from backend.llm_clients import _T1_LOCAL_SEMAPHORE        # un seul Dell pour tous les fils
        with _T1_LOCAL_SEMAPHORE:
            result, err = self.analyzer._call_openai_compatible_json(
                prompt, [], config.T1_LOCAL_MODEL, config.T1_LOCAL_API_KEY, config.T1_LOCAL_BASE_URL, action=ACTION,
                provider_label="local", timeout=config.T1_LOCAL_TIMEOUT_SECONDS)
        return result, err, config.T1_LOCAL_MODEL

    def _call_gemini(self, prompt: str) -> Tuple[Optional[dict], Optional[str], str]:
        import config
        model = config.GEMINI_MODELS["default_analyst"]
        result, err = self.analyzer._call_gemini_json(model, [prompt], action=ACTION)
        return result, err, model

    def extract(self, listing: Dict[str, Any], providers: Sequence[str] = PROVIDERS) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if self.analyzer is None:
            return None, "Analyseur indisponible (bot hors ligne)."
        prompt = ai_extract.build_prompt(listing)
        last_error = "aucun fournisseur configuré"
        for provider in providers:
            call = {"local": self._call_local, "gemini": self._call_gemini}.get(provider)
            if call is None:
                continue
            try:
                raw, err, model = call(prompt)
            except Exception as e:
                self.log.error(f"[Leaf] IA ({provider}) : {e}")
                last_error = f"{provider} : {e}"
                continue
            parsed = ai_extract.parse_response(raw)
            if parsed is None:
                last_error = f"{provider} : {err or 'réponse inutilisable'}"
                self.log.warning(f"[Leaf] IA : réponse de {provider} inutilisable, fournisseur suivant.")
                continue
            ai = ai_extract.apply_guardrails(parsed, listing)
            ai.update({"provider": provider, "model": model, "fingerprint": ai_extract.fingerprint(listing), "version": ai_extract.AI_VERSION,
                       "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            if ai["rejected"]:
                self.log.info(f"[Leaf] IA : {ai['rejected']} fait(s) sans citation retrouvée dans l'annonce, écarté(s).")
            return ai, None
        return None, last_error
