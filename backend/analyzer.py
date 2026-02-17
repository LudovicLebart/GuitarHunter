import json
import re
import requests
import logging
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from config import GEMINI_API_KEY, DEFAULT_PROMPTS

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

    def _construct_user_prompt(self, listing_data, prompts):
        """
        Assemble dynamiquement le prompt à partir des parties modulaires.
        """
        system_structure = "\n".join(prompts.get('system_structure', []))
        
        # Helper pour formater les sections
        def format_section(key):
            content = prompts.get(key, "")
            if isinstance(content, list):
                return "\n".join(content)
            if isinstance(content, dict):
                return json.dumps(content, indent=2, ensure_ascii=False)
            return str(content)

        # Remplacement des placeholders
        prompt = system_structure.format(
            persona=format_section('persona'),
            taxonomy=format_section('taxonomy_guitares'),
            verdict_rules=format_section('verdict_rules'),
            reasoning_instruction=format_section('reasoning_instruction'),
            json_output_format=format_section('json_output_format')
        )

        # Ajout des détails de l'annonce
        user_prompt_template = "\n".join(prompts.get('user_prompt', []))
        final_prompt = prompt + "\n\n" + user_prompt_template.format(
            title=listing_data.get('title', 'N/A'),
            price=listing_data.get('price', 'N/A'),
            description=listing_data.get('description', 'N/A')
        )
        
        return final_prompt

    def analyze_deal(self, listing_data, firestore_config=None, force_expert=False):
        if not GEMINI_API_KEY:
            return {"verdict": "ERROR", "reasoning": "La clé API Gemini n'est pas configurée."}

        # Utilise la config de Firestore ou les prompts par défaut
        prompts = {**DEFAULT_PROMPTS, **(firestore_config or {})}
        
        analysis_config = prompts.get('analysisConfig', {})
        gatekeeper_model_name = analysis_config.get('gatekeeperModel', 'gemini-1.5-flash-latest')
        expert_model_name = analysis_config.get('expertModel', 'gemini-1.5-pro-latest')
        
        logger.info(f"🤖 Analyse Cascade pour : {listing_data.get('title', 'Inconnu')} (Force Expert: {force_expert})")

        image_urls = (listing_data.get('imageUrls') or [listing_data.get('imageUrl')])[:8]
        images = [img for url in image_urls if (img := self._download_and_optimize_image(url))]

        # Construction du prompt de base (identique pour les deux modèles)
        base_prompt = self._construct_user_prompt(listing_data, prompts)
        
        gatekeeper_status, gatekeeper_reason = "MANUAL_RETRY", "Analyse experte demandée manuellement."

        if not force_expert:
            logger.info(f"   🛡️ Étape 1 : Portier ({gatekeeper_model_name})")
            gatekeeper_model = self._get_model(gatekeeper_model_name)
            if not gatekeeper_model:
                return {"verdict": "ERROR", "reasoning": "Modèle Portier non disponible.", "model_used": gatekeeper_model_name}
            
            # Ajout de l'instruction de concision pour le portier
            gatekeeper_prompt = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE PORTIER ---\n{prompts.get('gatekeeper_verbosity_instruction', '')}"
            
            try:
                response = gatekeeper_model.generate_content([gatekeeper_prompt] + images)
                result = json.loads(self._clean_json_response(response.text))
                
                gatekeeper_status = (result.get('status') or result.get('verdict') or 'UNKNOWN').upper()
                gatekeeper_reason = result.get('reason') or result.get('reasoning') or 'Pas de raison fournie.'
                
                if gatekeeper_status == 'UNKNOWN':
                    gatekeeper_status = 'ERROR'
                    gatekeeper_reason = f"Réponse IA invalide (Status UNKNOWN). Réponse brute : {str(result)}"
                
                logger.info(f"   👉 Verdict Portier : {gatekeeper_status} ({gatekeeper_reason})")

                if gatekeeper_status in ['REJECTED_ITEM', 'REJECTED_SERVICE', 'BAD_DEAL', 'INCOMPLETE_DATA']:
                    return {"verdict": gatekeeper_status, "reasoning": gatekeeper_reason, "model_used": gatekeeper_model_name}

            except Exception as e:
                logger.error(f"❌ Erreur Portier: {e}")
                gatekeeper_status = "ERROR_GATEKEEPER"
                gatekeeper_reason = f"Le portier a planté : {e}"
        else:
            logger.info("   ⏩ Portier sauté (Force Expert activé).")

        logger.info(f"   🧠 Étape 2 : Expert ({expert_model_name}) - Analyse approfondie...")
        expert_model = self._get_model(expert_model_name)
        if not expert_model:
            return {"verdict": gatekeeper_status, "reasoning": f"{gatekeeper_reason}\n\nL'analyse experte a échoué car le modèle expert n'était pas disponible.", "model_used": f"{gatekeeper_model_name} (Expert failed)"}

        expert_context_instruction = "\n".join(prompts.get('expert_context_instruction', []))
        context = expert_context_instruction.format(status=gatekeeper_status, reasoning=gatekeeper_reason)
        
        expert_prompt = f"{context}\n\n{base_prompt}"
        
        try:
            response = expert_model.generate_content([expert_prompt] + images)
            expert_result = json.loads(self._clean_json_response(response.text))
            
            return {"model_used": expert_model_name, **expert_result}
        except Exception as e:
            logger.error(f"❌ Erreur Expert: {e}")
            return {"verdict": gatekeeper_status, "reasoning": f"L'analyse experte a échoué après un premier verdict de '{gatekeeper_status}'.\nErreur: {e}", "model_used": f"{gatekeeper_model_name} (Expert Error)"}
