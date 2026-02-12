import json
import re
import requests
import logging
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from config import GEMINI_API_KEY, DEFAULT_MAIN_PROMPT, DEFAULT_GATEKEEPER_INSTRUCTION, DEFAULT_EXPERT_CONTEXT

logger = logging.getLogger(__name__)

class DealAnalyzer:
    def __init__(self):
        self.models = {}
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

    def _construct_user_prompt(self, listing_data, main_prompt_template, for_gatekeeper=False):
        """Construit le prompt utilisateur. Si for_gatekeeper est True, retire les instructions de formatage JSON complexe."""
        
        prompt_lines = main_prompt_template if isinstance(main_prompt_template, list) else str(main_prompt_template).split('\n')
        
        if for_gatekeeper:
            # On filtre tout ce qui se trouve après "### FORMAT DE RÉPONSE JSON STRICT"
            filtered_lines = []
            for line in prompt_lines:
                if "### FORMAT DE RÉPONSE JSON STRICT" in line:
                    break
                filtered_lines.append(line)
            main_prompt_str = "\n".join(filtered_lines)
        else:
            main_prompt_str = "\n".join(prompt_lines)

        return (
            f"{main_prompt_str}\n\n"
            f"Détails de l'annonce :\n"
            f"- Titre : {listing_data.get('title', 'N/A')}\n"
            f"- Prix : {listing_data.get('price', 'N/A')}\n"
            f"- Description : {listing_data.get('description', 'N/A')}\n"
            f"- Localisation : {listing_data.get('location', 'N/A')}\n"
        )

    def analyze_deal(self, listing_data, firestore_config=None, force_expert=False):
        if not GEMINI_API_KEY:
            return {"verdict": "ERROR", "reasoning": "La clé API Gemini n'est pas configurée."}

        config = firestore_config.get('analysisConfig', {})
        gatekeeper_model_name = config.get('gatekeeperModel', 'gemini-2.5-flash-lite')
        expert_model_name = config.get('expertModel', 'gemini-2.5-flash')
        
        logger.info(f"🤖 Analyse Cascade pour : {listing_data.get('title', 'Inconnu')} (Force Expert: {force_expert})")

        image_urls = (listing_data.get('imageUrls') or [listing_data.get('imageUrl')])[:8]
        images = [img for url in image_urls if (img := self._download_and_optimize_image(url))]

        # Prompt complet pour l'expert
        base_prompt_expert = self._construct_user_prompt(listing_data, config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT), for_gatekeeper=False)
        
        gatekeeper_status, gatekeeper_reason = "MANUAL_RETRY", "Analyse experte demandée manuellement."

        if not force_expert:
            logger.info(f"   🛡️ Étape 1 : Portier ({gatekeeper_model_name})")
            gatekeeper_model = self._get_model(gatekeeper_model_name)
            if not gatekeeper_model:
                return {"verdict": "ERROR", "reasoning": "Modèle Portier non disponible.", "model_used": gatekeeper_model_name}
            
            # Prompt allégé pour le portier
            base_prompt_gatekeeper = self._construct_user_prompt(listing_data, config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT), for_gatekeeper=True)
            
            try:
                response = gatekeeper_model.generate_content([f"{base_prompt_gatekeeper}\n\n--- INSTRUCTION SPÉCIALE PORTIER ---\n{config.get('gatekeeperVerbosityInstruction', DEFAULT_GATEKEEPER_INSTRUCTION)}"] + images)
                result = json.loads(self._clean_json_response(response.text))
                
                # Flexibilité : Accepter 'verdict' comme alias de 'status'
                gatekeeper_status = result.get('status') or result.get('verdict') or 'UNKNOWN'
                gatekeeper_status = gatekeeper_status.upper()
                
                # Flexibilité : Accepter 'reasoning' comme alias de 'reason'
                gatekeeper_reason = result.get('reason') or result.get('reasoning') or 'Pas de raison fournie.'
                
                if gatekeeper_status == 'UNKNOWN':
                    gatekeeper_status = 'ERROR'
                    gatekeeper_reason = f"Réponse IA invalide (Status UNKNOWN). Réponse brute : {str(result)}"
                    logger.warning(f"   ⚠️ Statut 'UNKNOWN' requalifié en 'ERROR'. Réponse : {result}")
                
                logger.info(f"   👉 Verdict Portier : {gatekeeper_status} ({gatekeeper_reason})")

                if gatekeeper_status not in ['PEPITE', 'GOOD_DEAL']:
                    return {"verdict": gatekeeper_status, "reasoning": gatekeeper_reason, "model_used": gatekeeper_model_name}

            except Exception as e:
                logger.error(f"❌ Erreur Portier: {e}")
                return {"verdict": "ERROR", "reasoning": f"Erreur Portier: {e}", "model_used": gatekeeper_model_name}
        else:
            logger.info("   ⏩ Portier sauté (Force Expert activé).")

        logger.info(f"   🧠 Étape 2 : Expert ({expert_model_name}) - Analyse approfondie...")
        expert_model = self._get_model(expert_model_name)
        if not expert_model:
            return {"verdict": gatekeeper_status, "reasoning": f"{gatekeeper_reason}\n\nL'analyse experte a échoué car le modèle expert n'était pas disponible.", "model_used": f"{gatekeeper_model_name} (Expert failed)"}

        context = config.get('expertContextInstruction', DEFAULT_EXPERT_CONTEXT).format(status=gatekeeper_status, reason=gatekeeper_reason)
        
        try:
            response = expert_model.generate_content([f"{context}\n\n{base_prompt_expert}"] + images)
            expert_result = json.loads(self._clean_json_response(response.text))
            
            final_result = {
                "model_used": expert_model_name,
                **expert_result
            }
            return final_result
        except Exception as e:
            logger.error(f"❌ Erreur Expert: {e}")
            return {"verdict": gatekeeper_status, "reasoning": f"L'analyse experte a échoué après un premier verdict de '{gatekeeper_status}'.\nErreur: {e}", "model_used": f"{gatekeeper_model_name} (Expert Error)"}
