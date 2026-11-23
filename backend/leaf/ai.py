"""Leaf — niveau 2 (IA) : appel des modèles. Réutilise `DealAnalyzer` du bot (clients Gemini / compatibles OpenAI, enregistrement
`llm_usage`, alertes « modèle injoignable », sémaphore du Dell) sans le modifier.

Chaîne de fournisseurs, dans l'ordre configuré (`leafConfig.analysisConfig.providers`, défaut `local` puis `gemini`) : Qwen local sur
le Dell (gratuit), puis Gemini Flash en secours. Le premier fournisseur dont la réponse est UTILISABLE est retenu. Ne lève jamais :
renvoie (analyse | None, erreur | None). Chaque tentative est enregistrée dans `llm_usage` (action `leaf_t2`) par les clients."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from backend import t1_circuit_breaker
from backend.leaf import ai_extract, expert, photo_extract

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
                provider_label="local", timeout=config.T1_LOCAL_TIMEOUT_SECONDS,
                max_retries=0)       # pas de nouvelles tentatives du client : le fournisseur suivant (Gemini) sert de repli
        return result, err, config.T1_LOCAL_MODEL

    def _call_gemini(self, prompt: str) -> Tuple[Optional[dict], Optional[str], str]:
        import config
        model = config.GEMINI_MODELS["default_analyst"]
        result, err = self.analyzer._call_gemini_json(model, [prompt], action=ACTION)
        return result, err, model

    @staticmethod
    def _breaker_failure() -> None:
        import config
        t1_circuit_breaker.record_failure("local", config.T1_CIRCUIT_BREAKER_FAILURE_THRESHOLD, config.T1_CIRCUIT_BREAKER_COOLDOWN_SECONDS)

    def extract(self, listing: Dict[str, Any], providers: Sequence[str] = PROVIDERS, instructions: Optional[str] = None
                ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if self.analyzer is None:
            return None, "Analyseur indisponible (bot hors ligne)."
        prompt = ai_extract.build_prompt(listing, instructions)
        last_error = "aucun fournisseur configuré"
        for provider in providers:
            call = {"local": self._call_local, "gemini": self._call_gemini}.get(provider)
            if call is None:
                continue
            if provider == "local" and t1_circuit_breaker.is_open("local"):
                # Même coupe-circuit que le Portier des guitares (processus entier) : un Dell en panne n'est pas rappelé à chaque annonce
                # (60 s d'attente chacune) ; le premier appel après la pause sert de test.
                last_error = "local : Dell en pause (coupe-circuit)"
                self.log.warning("[Leaf] IA : Dell en pause (coupe-circuit), fournisseur suivant.")
                continue
            try:
                raw, err, model = call(prompt)
            except Exception as e:
                self.log.error(f"[Leaf] IA ({provider}) : {e}")
                last_error = f"{provider} : {e}"
                if provider == "local":
                    self._breaker_failure()
                continue
            if provider == "local":
                self._breaker_failure() if err else t1_circuit_breaker.record_success("local")
            parsed = ai_extract.parse_response(raw)
            if parsed is None:
                last_error = f"{provider} : {err or 'réponse inutilisable'}"
                self.log.warning(f"[Leaf] IA : réponse de {provider} inutilisable, fournisseur suivant.")
                continue
            ai = ai_extract.apply_guardrails(parsed, listing)
            ai.update({"provider": provider, "model": model, "fingerprint": ai_extract.fingerprint(listing, instructions), "version": ai_extract.AI_VERSION,
                       "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            if ai["rejected"]:
                self.log.info(f"[Leaf] IA : {ai['rejected']} fait(s) sans citation retrouvée dans l'annonce, écarté(s).")
            return ai, None
        return None, last_error

    def expert(self, listing: Dict[str, Any], images: Optional[list] = None, photo_numbers: Optional[list] = None,
               instructions: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Niveau 3 : avis de l'Expert (Claude, `T3_CLAUDE_MODEL`) sur UNE annonce, à la demande. Ne lève jamais.
        Aucun repli sur un autre modèle : un Expert qui échoue échoue visiblement (comme pour les guitares)."""
        if self.analyzer is None:
            return None, "Analyseur indisponible (bot hors ligne)."
        import config
        try:
            raw, err = self.analyzer._call_claude_json(config.T3_CLAUDE_MODEL, [expert.build_prompt(listing, instructions), *(images or [])], action="leaf_t3")
        except Exception as e:
            self.log.error(f"[Leaf] Expert : {e}")
            return None, str(e)
        opinion = expert.apply_guardrails(raw, listing, photo_count=len(images or []))
        if opinion is not None and photo_numbers:       # « Image k » -> numéro de la photo dans la fiche
            for n in opinion["photo_observations"]:
                n["photo"] = photo_numbers[n["photo"] - 1]
            opinion["photos_sent"] = list(photo_numbers)
        if opinion is None:
            return None, err or "réponse de l'Expert inutilisable"
        opinion.update({"model": config.T3_CLAUDE_MODEL, "version": expert.EXPERT_VERSION, "fingerprint": ai_extract.fingerprint(listing),
                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return opinion, None

    # ------------------------------------------------------------------ photos (captures LeafSpy, tableau de bord)

    def _local_vision(self, prompt: str, images: list, schema: dict) -> Tuple[Optional[dict], Optional[str]]:
        """Appel du modèle LOCAL (Qwen3-VL du Dell) avec des images, comme `LLMClientsMixin._t1_read_photo_text` des guitares : budget de
        contexte du Dell (`_fit_t1_local_images`), sémaphore partagé, coupe-circuit partagé, schéma JSON strict, aucune nouvelle tentative."""
        import config
        from backend.llm_clients import _T1_LOCAL_SEMAPHORE
        if t1_circuit_breaker.is_open("local"):
            return None, "Dell en pause (coupe-circuit)"
        fitted = self.analyzer._fit_t1_local_images(prompt, images)
        with _T1_LOCAL_SEMAPHORE:
            result, err = self.analyzer._call_openai_compatible_json(
                prompt, fitted, config.T1_LOCAL_MODEL, config.T1_LOCAL_API_KEY, config.T1_LOCAL_BASE_URL, response_format=schema,
                action="leaf_photo", provider_label="local", timeout=config.T1_LOCAL_TIMEOUT_SECONDS, max_retries=0)
        if err:
            self._breaker_failure()
        else:
            t1_circuit_breaker.record_success("local")
        return result, err

    def read_photos(self, listing: Dict[str, Any], providers: Sequence[str] = PROVIDERS, instructions: Optional[str] = None
                    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Lit les chiffres visibles sur les photos de l'annonce. Ne lève jamais : (lecture | None, erreur | None).

        Dell : TRI de TOUTES les photos en résolution moyenne (assez nette pour reconnaître un écran ; ~300 tokens chacune, ramenées au budget
        du Dell si besoin) puis LECTURE des captures retenues (4 au plus) en haute résolution. Gemini (secours) : lecture directe d'au plus 12 photos
        en résolution moyenne, sans tri. Rien n'est écrit sur disque :
        les images restent en mémoire. Le garde-fou (`photo_extract.apply_guardrails`) recalcule les valeurs depuis les transcriptions."""
        if self.analyzer is None:
            return None, "Analyseur indisponible (bot hors ligne)."
        urls = photo_extract.photo_urls(listing)
        read_prompt = instructions or photo_extract.READ_PROMPT
        if not urls:
            return None, "aucune photo"
        last_error = "aucun fournisseur configuré"
        for provider in providers:
            try:
                if provider == "local":
                    thumbs = self.analyzer._download_images([photo_extract.sized_url(u, "medium") for u in urls])
                    if len(thumbs) != len(urls):                    # une vignette manquante décalerait les numéros : on n'essaie pas
                        last_error = "local : photos de tri incomplètes"
                        continue
                    triage, err = self._local_vision(photo_extract.TRIAGE_PROMPT, thumbs, photo_extract.TRIAGE_JSON_SCHEMA)
                    if err or triage is None:
                        last_error = f"local : {err or 'tri sans réponse'}"
                        continue
                    chosen = photo_extract.parse_triage(triage, len(urls))
                    model = __import__("config").T1_LOCAL_MODEL
                    readings = []
                    if chosen:
                        big = self.analyzer._download_images([photo_extract.sized_url(urls[i], "large") for i in chosen])
                        if len(big) != len(chosen):
                            last_error = "local : photos en haute résolution incomplètes"
                            continue
                        raw, err = self._local_vision(read_prompt, big, photo_extract.READ_JSON_SCHEMA)
                        if err or raw is None:
                            last_error = f"local : {err or 'lecture sans réponse'}"
                            continue
                        readings = photo_extract.parse_readings(raw, len(big))
                        numbering = chosen
                    else:
                        numbering = []
                elif provider == "gemini":
                    import config
                    chosen = list(range(min(len(urls), photo_extract.MAX_GEMINI_PHOTOS)))
                    images = self.analyzer._download_images([photo_extract.sized_url(urls[i], "medium") for i in chosen])
                    if len(images) != len(chosen):
                        last_error = "gemini : photos incomplètes"
                        continue
                    model = config.GEMINI_MODELS["default_analyst"]
                    raw, err = self.analyzer._call_gemini_json(model, [read_prompt, *images], action="leaf_photo")
                    if raw is None:
                        last_error = f"gemini : {err or 'lecture sans réponse'}"
                        continue
                    readings = photo_extract.parse_readings(raw, len(images))
                    numbering = chosen
                else:
                    continue
            except Exception as e:
                self.log.error(f"[Leaf] Photos ({provider}) : {e}")
                last_error = f"{provider} : {e}"
                if provider == "local":
                    self._breaker_failure()
                continue
            guarded = photo_extract.apply_guardrails(readings, [i + 1 for i in numbering], listing)
            out = {"facts": guarded["facts"], "flags": guarded["flags"], "readings": [{"photo": (numbering[r["photo"]] + 1), "transcript": r["transcript"]} for r in readings],
                   "selected": [i + 1 for i in numbering], "provider": provider, "model": model,
                   "fingerprint": photo_extract.fingerprint(urls), "version": photo_extract.PHOTO_VERSION,
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            return out, None
        return None, last_error
