import json
import re
import requests
import logging
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from config import GEMINI_API_KEY
from .prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class DealAnalyzer:
    def __init__(self):
        self.model = None
        self.prompt_manager = PromptManager()
        self.current_system_prompt_hash = None
        self.current_model_name = None
        self._init_gemini()

    def _init_gemini(self, system_instruction=None, model_name='gemini-2.0-flash'):
        """Initialise le modèle Gemini."""
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            
            try:
                # Si pas d'instruction système fournie, on prend celle par défaut du fichier
                if system_instruction is None:
                    system_instruction = self.prompt_manager.get_system_prompt({})

                self.model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.1
                    }
                )
                self.current_system_prompt_hash = hash(system_instruction)
                self.current_model_name = model_name
                logger.info(f"🤖 Modèle Gemini initialisé ({model_name}).")
            except Exception as e:
                logger.error(f"⚠️ Erreur init {model_name} : {e}")
        else:
            logger.warning("⚠️ Pas de clé API Gemini fournie.")

    def _ensure_model_config(self, firestore_config):
        """Vérifie si le prompt système ou le modèle a changé et réinitialise si nécessaire."""
        new_system_prompt = self.prompt_manager.get_system_prompt(firestore_config)
        new_model_name = firestore_config.get('geminiModel', 'gemini-2.0-flash')
        
        new_hash = hash(new_system_prompt)
        
        if self.current_system_prompt_hash != new_hash or self.current_model_name != new_model_name:
            logger.info(f"🔄 Mise à jour de la config IA détectée (Modèle: {new_model_name}). Réinitialisation.")
            self._init_gemini(system_instruction=new_system_prompt, model_name=new_model_name)

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

    def analyze_deal(self, listing_data, firestore_config=None):
        """Utilise Gemini pour évaluer si l'annonce est une bonne affaire."""
        if firestore_config is None:
            firestore_config = {}

        # Mise à jour dynamique du modèle si la config a changé
        self._ensure_model_config(firestore_config)

        if not self.model:
             logger.error("⚠️ Modèle Gemini non initialisé.")
             return {
                "verdict": "ERROR",
                "estimated_value": listing_data.get('price', 0),
                "reasoning": "Analyse IA impossible : Modèle non initialisé.",
                "confidence": 0
            }

        logger.info(f"🤖 Analyse IA pour : {listing_data.get('title', 'Inconnu')}...")

        # Téléchargement des images
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
        
        # Construction du message utilisateur via PromptManager
        user_message = self.prompt_manager.get_user_prompt(firestore_config, listing_data)

        try:
            content = [user_message]
            content.extend(images)
            
            if images:
                logger.info(f"   📸 {len(images)} images incluses dans l'analyse.")
            else:
                logger.info("   ⚠️ Analyse texte uniquement (pas d'image valide).")

            response = self.model.generate_content(content)
            
            text_response = response.text
            if text_response.startswith("```json"):
                text_response = text_response[7:]
            if text_response.startswith("```"):
                text_response = text_response[3:]
            if text_response.endswith("```"):
                text_response = text_response[:-3]
            
            text_response = text_response.strip()
            
            try:
                result = json.loads(text_response)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ Réponse non-JSON reçue : {text_response[:100]}...")
                return {
                    "verdict": "ERROR",
                    "estimated_value": listing_data.get('price', 0),
                    "reasoning": "Erreur format JSON: " + text_response[:200],
                    "confidence": 0
                }
            
            if isinstance(result, list):
                if len(result) > 0:
                    result = result[0]
                else:
                    return {
                        "verdict": "ERROR",
                        "estimated_value": listing_data.get('price', 0),
                        "reasoning": "L'IA a renvoyé une liste vide.",
                        "confidence": 0
                    }
            
            if 'estimated_value' in result:
                ev = result['estimated_value']
                if isinstance(ev, str):
                    try:
                        nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', ev.replace(',', '.'))]
                        if nums:
                            result['estimated_value'] = int(sum(nums) / len(nums))
                        else:
                            result['estimated_value'] = 0
                    except:
                        result['estimated_value'] = 0

            return result

        except Exception as e:
            error_str = str(e)
            if "403" in error_str and "leaked" in error_str:
                logger.critical("❌ ERREUR CRITIQUE : CLÉ API GEMINI BLOQUÉE.")
            else:
                logger.error(f"❌ Erreur Gemini: {e}")

            return {
                "verdict": "ERROR",
                "estimated_value": listing_data.get('price', 0),
                "reasoning": f"Erreur d'analyse IA : {e}",
                "confidence": 0
            }
