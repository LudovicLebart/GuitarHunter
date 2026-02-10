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
        self.models = {} # Cache pour les instances de modèles
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
        else:
            logger.warning("⚠️ Pas de clé API Gemini fournie.")

    def _get_model(self, model_name, system_instruction=None):
        """Récupère ou crée une instance de modèle Gemini."""
        if not GEMINI_API_KEY:
            return None

        cache_key = (model_name, hash(str(system_instruction)))
        
        if cache_key not in self.models:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.1
                    }
                )
                self.models[cache_key] = model
                logger.info(f"🤖 Modèle Gemini initialisé : {model_name}")
            except Exception as e:
                logger.error(f"⚠️ Erreur init {model_name} : {e}")
                return None
        
        return self.models[cache_key]

    def download_image(self, url):
        """Télécharge l'image depuis l'URL et la convertit en objet PIL Image."""
        try:
            if not url or "via.placeholder.com" in url:
                return None
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return Image.open(BytesIO(response.content))
            return None
        except Exception as e:
            logger.warning(f"⚠️ Impossible de télécharger l'image : {e}")
            return None

    def _optimize_image(self, img, max_size=2048):
        """Redimensionne et convertit l'image pour optimiser les tokens Gemini."""
        try:
            if img.size[0] > max_size or img.size[1] > max_size:
                w_percent = (max_size / float(img.size[0]))
                h_size = int((float(img.size[1]) * float(w_percent)))
                img = img.resize((max_size, h_size), Image.Resampling.LANCZOS)
            
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            return img
        except Exception as e:
            logger.warning(f"⚠️ Erreur optimisation image : {e}")
            return img

    def _clean_json_response(self, text_response):
        """Nettoie la réponse brute de Gemini pour extraire le JSON."""
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        if text_response.startswith("```"):
            text_response = text_response[3:]
        if text_response.endswith("```"):
            text_response = text_response[:-3]
        return text_response.strip()

    def _construct_user_prompt(self, listing_data, main_prompt_template):
        """Construit le prompt utilisateur de base avec les détails de l'annonce."""
        details = (
            f"Détails de l'annonce :\n"
            f"- Titre : {listing_data.get('title', 'N/A')}\n"
            f"- Prix : {listing_data.get('price', 'N/A')}\n"
            f"- Description : {listing_data.get('description', 'N/A')}\n"
            f"- Localisation : {listing_data.get('location', 'N/A')}\n"
        )
        
        if isinstance(main_prompt_template, list):
            main_prompt_str = "\n".join(main_prompt_template)
        else:
            main_prompt_str = str(main_prompt_template)
            
        return f"{main_prompt_str}\n\n{details}"

    def analyze_deal(self, listing_data, firestore_config=None, force_expert=False):
        """
        Analyse une annonce en utilisant une stratégie de cascade (Funnel).
        Si force_expert est True, on saute le Portier et on utilise directement l'Expert.
        """
        if firestore_config is None:
            firestore_config = {}

        analysis_config = firestore_config.get('analysisConfig', {})
        
        gatekeeper_model_name = analysis_config.get('gatekeeperModel', 'gemini-3-flash')
        expert_model_name = analysis_config.get('expertModel', 'gemini-2.5-flash')
        
        main_prompt = analysis_config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT)
        gatekeeper_instruction = analysis_config.get('gatekeeperVerbosityInstruction', DEFAULT_GATEKEEPER_INSTRUCTION)
        expert_context_template = analysis_config.get('expertContextInstruction', DEFAULT_EXPERT_CONTEXT)

        logger.info(f"🤖 Analyse Cascade pour : {listing_data.get('title', 'Inconnu')} (Force Expert: {force_expert})")

        images = []
        urls_to_process = listing_data.get('imageUrls', [])
        if not urls_to_process and listing_data.get('imageUrl'):
            urls_to_process = [listing_data['imageUrl']]
        
        urls_to_process = urls_to_process[:8]

        for url in urls_to_process:
            img = self.download_image(url)
            if img:
                img = self._optimize_image(img)
                images.append(img)

        base_user_prompt = self._construct_user_prompt(listing_data, main_prompt)
        
        # Variables pour le contexte expert
        status = "MANUAL_RETRY"
        reason = "Analyse experte demandée manuellement."

        # --- ÉTAPE 1 : LE PORTIER (Seulement si pas forcé) ---
        if not force_expert:
            logger.info(f"   🛡️ Étape 1 : Portier ({gatekeeper_model_name})")
            
            gatekeeper_model = self._get_model(gatekeeper_model_name)
            if not gatekeeper_model:
                return {"verdict": "ERROR", "reasoning": "Modèle Portier non disponible."}

            gatekeeper_full_prompt = f"{base_user_prompt}\n\n--- INSTRUCTION SPÉCIALE PORTIER ---\n{gatekeeper_instruction}"
            
            try:
                content = [gatekeeper_full_prompt]
                content.extend(images)
                
                response = gatekeeper_model.generate_content(content)
                result_json = json.loads(self._clean_json_response(response.text))
                
                status = result_json.get('status', 'UNKNOWN').upper()
                reason = result_json.get('reason', 'Pas de raison fournie.')
                
                is_promising = status in ['PEPITE', 'GOOD_DEAL']
                
                logger.info(f"   👉 Verdict Portier : {status} ({reason})")

                if not is_promising:
                    return {
                        "verdict": status,
                        "reason": reason,
                        "score": 0,
                        "model_used": gatekeeper_model_name,
                        "analysis": None
                    }

            except Exception as e:
                logger.error(f"❌ Erreur Portier: {e}")
                return {"verdict": "ERROR", "reasoning": f"Erreur Portier: {e}"}
        else:
            logger.info("   ⏩ Portier sauté (Force Expert activé).")

        # --- ÉTAPE 2 : L'EXPERT ---
        logger.info(f"   🧠 Étape 2 : Expert ({expert_model_name}) - Analyse approfondie...")
        
        expert_model = self._get_model(expert_model_name)
        if not expert_model:
             return {
                "verdict": status,
                "reason": reason,
                "model_used": f"{gatekeeper_model_name} (Expert failed)",
                "analysis": "L'analyse détaillée a échoué."
            }

        context_instruction = expert_context_template.format(status=status, reason=reason)
        expert_full_prompt = f"{context_instruction}\n\n{base_user_prompt}"
        
        try:
            content = [expert_full_prompt]
            content.extend(images)
            
            response = expert_model.generate_content(content)
            expert_result = json.loads(self._clean_json_response(response.text))
            
            expert_result['model_used'] = expert_model_name
            
            if 'estimated_value' in expert_result:
                ev = expert_result['estimated_value']
                if isinstance(ev, str):
                    try:
                        nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', ev.replace(',', '.'))]
                        if nums:
                            expert_result['estimated_value'] = int(sum(nums) / len(nums))
                        else:
                            expert_result['estimated_value'] = 0
                    except:
                        expert_result['estimated_value'] = 0
            
            return expert_result

        except Exception as e:
            logger.error(f"❌ Erreur Expert: {e}")
            return {
                "verdict": status,
                "reason": reason,
                "model_used": f"{gatekeeper_model_name} (Expert Error)",
                "analysis": f"Erreur lors de l'analyse détaillée : {e}"
            }
