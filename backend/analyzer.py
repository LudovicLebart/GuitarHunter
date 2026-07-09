import json
import re
import time
import requests
import logging
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from backend.notifications import NotificationService
from config import (
    GEMINI_API_KEY,
    DEFAULT_MAIN_PROMPT,
    DEFAULT_GATEKEEPER_INSTRUCTION,
    DEFAULT_ANALYST_INSTRUCTION,
    DEFAULT_EXPERT_CONTEXT,
    DEFAULT_TAXONOMY,
    DEFAULT_FEW_SHOT_EXAMPLES,
    DEFAULT_REJECTION_VERDICTS,
    DEFAULT_PRO_PRICE_THRESHOLD,
    DEFAULT_PRO_DEAL_SCORE_THRESHOLD,
    DEFAULT_PRO_COMBINED_DEAL_SCORE,
    DEFAULT_PRO_RESTO_SCORE_THRESHOLD,
    DEFAULT_PRO_AUTH_SCORE_THRESHOLD,
    DEFAULT_PRO_CONFIDENCE_THRESHOLD,
)
from backend.scraping.parser import ListingParser

logger = logging.getLogger(__name__)

class DealAnalyzer:
    def __init__(self):
        self.models = {}
        self._model_error_last_notified = {}
        if not GEMINI_API_KEY:
            logger.warning("⚠️ Pas de clé API Gemini fournie.")
            return
        
        genai.configure(api_key=GEMINI_API_KEY)
        try:
            model_list = [f"ID: {m.name} | Display Name: {m.display_name}" for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            logger.info("--- Modèles Gemini Disponibles ---\n" + "\n".join(model_list))
        except Exception as e:
            logger.critical(f"CRITICAL: Impossible de lister les modèles Gemini : {e}", exc_info=True)

    def _get_model(self, model_name, system_instruction=None):
        cache_key = (model_name, hash(str(system_instruction)))
        if cache_key not in self.models:
            try:
                self.models[cache_key] = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.1}
                )
                logger.info(f"🤖 Modèle Gemini initialisé : {model_name}")
            except Exception as e:
                logger.error(f"⚠️ Erreur init {model_name} : {e}")
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
            logger.warning(f"⚠️ Impossible de traiter l'image {url}: {e}")
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

        taxonomy_str = json.dumps(taxonomy_data, indent=2, ensure_ascii=False)

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
            NotificationService.notify_model_error(model_name, error_text, user_email)
        except Exception as e:
            logger.error(f"⚠️ Échec de l'envoi de l'alerte modèle indisponible : {e}")

    def _call_gemini_json(self, model_name, content_parts, user_email=None):
        """Méthode utilitaire DRY pour appeler Gemini et parser le JSON."""
        model = self._get_model(model_name)
        if not model:
            return None, f"Modèle {model_name} non disponible."
        try:
            response = model.generate_content(content_parts)
            result = json.loads(self._clean_json_response(response.text))
            if isinstance(result, list):
                # Gemini répond parfois avec un tableau JSON au lieu d'un objet
                # (ex: [{...}]) — on normalise en dict pour que tous les appelants
                # (T1/T2/T3) puissent utiliser .get()/["clé"]= sans planter.
                result = result[0] if result and isinstance(result[0], dict) else {}
            return result, None
        except Exception as e:
            logger.error(f"❌ Erreur avec le modèle {model_name}: {e}")
            if self._is_model_unavailable_error(e):
                self._notify_model_unavailable(model_name, str(e), user_email)
            return None, str(e)

    def analyze_deal(self, listing_data, firestore_config=None, force_expert=False, user_comment=None, user_email=None):
        if not GEMINI_API_KEY:
            return {"verdict": "ERROR", "reasoning": "La clé API Gemini n'est pas configurée."}

        config = firestore_config.get('analysisConfig', {})
        gatekeeper_model_name = config.get('gatekeeperModel', 'gemini-2.5-flash-lite')
        analyst_model_name = config.get('mainModel', 'gemini-3.5-flash')
        # Rétrocompatibilité : 'proModel' est la nouvelle clé, 'expertModel' est l'ancienne (encore écrite par le frontend)
        expert_pro_model_name = config.get('proModel') or config.get('expertModel', 'gemini-2.5-pro')

        taxonomy = config.get('taxonomy', DEFAULT_TAXONOMY)
        few_shot_examples = config.get('fewShotExamples', DEFAULT_FEW_SHOT_EXAMPLES)
        rejection_verdicts = config.get('rejectionVerdicts', DEFAULT_REJECTION_VERDICTS)

        logger.info(f"🤖 Analyse Cascade pour : {listing_data.get('title', 'Inconnu')} (Force Expert: {force_expert})")

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

        # ==========================================
        # PHASE 1 : TIER 1 - PORTIER (Flash-Lite)
        # ==========================================
        if not force_expert:
            logger.info(f"   🛡️ Étape 1 : Portier ({gatekeeper_model_name})")
            model_chain.append(gatekeeper_model_name)
            gatekeeper_instruction = config.get('gatekeeperVerbosityInstruction', DEFAULT_GATEKEEPER_INSTRUCTION)
            if isinstance(gatekeeper_instruction, list):
                gatekeeper_instruction = "\n".join(gatekeeper_instruction)
            full_prompt_t1 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE PORTIER ---\n{gatekeeper_instruction}"
            
            result_t1, err_t1 = self._call_gemini_json(gatekeeper_model_name, [full_prompt_t1] + images, user_email)
            
            if err_t1 or not result_t1:
                # Fail-open vers l'Analyste
                gatekeeper_status = "ERROR_GATEKEEPER"
                gatekeeper_reason = err_t1 or "Le portier a planté silencieusement."
            else:
                gatekeeper_status = (result_t1.get('status') or result_t1.get('verdict') or 'UNKNOWN').upper()
                gatekeeper_reason = result_t1.get('reason') or result_t1.get('reasoning') or 'Pas de raison fournie.'
                
                if gatekeeper_status == 'UNKNOWN':
                    gatekeeper_status = 'ERROR'
                    gatekeeper_reason = f"Réponse IA invalide. Brut : {str(result_t1)}"
                
                logger.info(f"   👉 Verdict Portier : {gatekeeper_status} ({gatekeeper_reason})")

                legacy_rejection = ['REJECTED', 'REJECTED (SERVICE)']
                if gatekeeper_status in rejection_verdicts or gatekeeper_status in legacy_rejection or gatekeeper_status.startswith('REJECTED'):
                    gatekeeper_classification = result_t1.get('classification')
                    return {"verdict": gatekeeper_status, "reasoning": gatekeeper_reason, "classification": gatekeeper_classification, "model_used": " -> ".join(model_chain)}
        else:
            logger.info("   ⏩ Portier sauté (Force Expert).")

        # ==========================================
        # PHASE 2 : TIER 2 - ANALYSTE (Flash)
        # ==========================================
        logger.info(f"   🔍 Étape 2 : Analyste ({analyst_model_name}) - Structuration & Scores...")
        model_chain.append(analyst_model_name)
        analyst_instruction = config.get('analystVerbosityInstruction', DEFAULT_ANALYST_INSTRUCTION)
        if isinstance(analyst_instruction, list):
            analyst_instruction = "\n".join(analyst_instruction)
        full_prompt_t2 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE ANALYSTE ---\n{analyst_instruction}"
        
        result_t2, err_t2 = self._call_gemini_json(analyst_model_name, [full_prompt_t2] + images, user_email)
        
        if err_t2 or not result_t2:
            return {"verdict": gatekeeper_status, "reasoning": f"{gatekeeper_reason}\n\nErreur Tier 2 Analyste: {err_t2}", "model_used": " -> ".join(model_chain) + " (Error)"}

        # Formatage des variables pour la logique conditionnelle
        deal_score = result_t2.get('deal_score', 0)
        auth_score = result_t2.get('authenticity_score', 10) # 10 par défaut pour pas trigger fausement
        resto_score = result_t2.get('restoration_interest_score', 0)
        confidence = result_t2.get('confidence', 1.0)
        verdict = result_t2.get('verdict', '')
        
        # Extraction du prix
        numeric_price = ListingParser.extract_price_from_text(str(listing_data.get('price', '') or ''))
        
        logger.info(f"   📊 Scores T2 -> Deal: {deal_score} | Auth: {auth_score} | Resto: {resto_score} | Conf: {confidence} | Prix: {numeric_price}")

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
            logger.info(f"   ⭐ Étape 3 (DÉCLENCHÉE) : Expert Pro ({expert_pro_model_name}) - Motif : {trigger_reason}")
            model_chain.append(expert_pro_model_name)
            
            expert_context_raw = config.get('expertProContextInstruction', DEFAULT_EXPERT_CONTEXT)
            if isinstance(expert_context_raw, list):
                expert_context_raw = "\n".join(expert_context_raw)
            
            # Contextualisation de l'expert pro avec le json T2
            context_t3 = expert_context_raw.format(
                status=verdict,
                reasoning=result_t2.get('summary', 'Analyse rapide T2 terminée.')
            )
            
            full_prompt_t3 = f"{context_t3}\n\n{base_prompt}"
            
            result_t3, err_t3 = self._call_gemini_json(expert_pro_model_name, [full_prompt_t3] + images, user_email)
            
            if err_t3 or not result_t3:
                logger.error(f"❌ Erreur Expert Pro, fallback sur T2. Erreur: {err_t3}")
                result_t2["model_used"] = " -> ".join(model_chain) + " (T3 Failed, fallback T2)"
                return result_t2
            
            # L'Expert Pro écrase le T2
            result_t3["model_used"] = " -> ".join(model_chain)
            result_t3["tier3_trigger"] = trigger_reason
            logger.info(f"   ✅ Verdict Expert Pro : {result_t3.get('verdict', 'N/A')} | Deal: {result_t3.get('deal_score', '?')} | Auth: {result_t3.get('authenticity_score', '?')} | Conf: {result_t3.get('confidence', '?')} | Résumé: {result_t3.get('summary', 'N/A')}")
            return result_t3
            
        else:
            logger.info("   ✋ Fin de l'analyse (Tier 3 non déclenché).")
            result_t2["model_used"] = " -> ".join(model_chain)
            return result_t2
