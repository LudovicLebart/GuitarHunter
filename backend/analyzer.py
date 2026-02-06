import json
import re
import requests
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from config import GEMINI_API_KEY, SYSTEM_PROMPT

class DealAnalyzer:
    def __init__(self):
        self.model = None
        self.user_prompt_template = "" # Sera défini par l'application
        self._init_gemini()

    def _init_gemini(self):
        """Initialise le modèle Gemini avec fallback."""
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            
            try:
                self.model = genai.GenerativeModel(
                    model_name='gemini-2.5-flash',
                    system_instruction=SYSTEM_PROMPT,
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.1
                    }
                )
                print("🤖 Modèle Gemini initialisé (gemini-2.0-flash).")
            except Exception as e:
                print(f"⚠️ Erreur init gemini-2.0-flash : {e}")

        else:
            print("⚠️ Pas de clé API Gemini fournie.")

    def update_prompt_template(self, new_template):
        """Met à jour le template de prompt utilisateur."""
        self.user_prompt_template = new_template

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
            print(f"⚠️ Impossible de télécharger l'image : {e}")
            return None

    def _optimize_image(self, img, max_size=2048):
        """Redimensionne et convertit l'image pour optimiser les tokens Gemini."""
        try:
            # Conservation du ratio d'aspect
            if img.size[0] > max_size or img.size[1] > max_size:
                w_percent = (max_size / float(img.size[0]))
                h_size = int((float(img.size[1]) * float(w_percent)))
                img = img.resize((max_size, h_size), Image.Resampling.LANCZOS)
            
            # Conversion en RGB
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            return img
        except Exception as e:
            print(f"⚠️ Erreur optimisation image : {e}")
            return img

    def analyze_deal(self, listing_data):
        """Utilise Gemini pour évaluer si l'annonce est une bonne affaire."""
        if not self.model:
             print("⚠️ Modèle Gemini non initialisé.")
             return {
                "verdict": "ERROR",
                "estimated_value": listing_data.get('price', 0),
                "reasoning": "Analyse IA impossible : Modèle non initialisé.",
                "confidence": 0
            }

        print(f"🤖 Analyse IA pour : {listing_data.get('title', 'Inconnu')}...")

        # Téléchargement des images
        images = []
        urls_to_process = listing_data.get('imageUrls', [])
        if not urls_to_process and listing_data.get('imageUrl'):
            urls_to_process = [listing_data['imageUrl']]
            
        # Limite à 8 images
        urls_to_process = urls_to_process[:8]

        for url in urls_to_process:
            img = self.download_image(url)
            if img:
                img = self._optimize_image(img)
                images.append(img)
        
        # Construction du message utilisateur
        if not self.user_prompt_template:
            # Fallback si le template n'est pas encore défini
            user_message = f"Analyse cette guitare : {listing_data.get('title')}, {listing_data.get('price')}$, {listing_data.get('description')}"
        else:
            user_message = self.user_prompt_template.replace("{title}", str(listing_data.get('title', 'N/A'))) \
                                                    .replace("{price}", str(listing_data.get('price', 'N/A'))) \
                                                    .replace("{description}", str(listing_data.get('description', 'N/A')))

        try:
            content = [user_message]
            content.extend(images)
            
            if images:
                print(f"   📸 {len(images)} images incluses dans l'analyse.")
            else:
                print("   ⚠️ Analyse texte uniquement (pas d'image valide).")

            response = self.model.generate_content(content)
            
            # Nettoyage de la réponse (au cas où le JSON est entouré de ```json ... ```)
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
                # Fallback si le modèle ne renvoie pas du JSON pur malgré la config
                print(f"⚠️ Réponse non-JSON reçue : {text_response[:100]}...")
                return {
                    "verdict": "ERROR",
                    "estimated_value": listing_data.get('price', 0),
                    "reasoning": "Erreur format JSON: " + text_response[:200],
                    "confidence": 0
                }
            
            # Gestion du cas où Gemini renvoie une liste
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
            
            # Conversion estimated_value en nombre
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
                print("\n" + "!"*60)
                print("❌ ERREUR CRITIQUE : CLÉ API GEMINI BLOQUÉE.")
                print("!"*60 + "\n")
            else:
                print(f"❌ Erreur Gemini: {e}")

            return {
                "verdict": "ERROR",
                "estimated_value": listing_data.get('price', 0),
                "reasoning": f"Erreur d'analyse IA : {e}",
                "confidence": 0
            }
