import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Gère l'assemblage et la configuration des prompts pour l'IA.
    Architecture "Blocs" : Assemble le prompt système à partir de composants indépendants.
    """
    def __init__(self, prompts_path: str = 'prompts.json'):
        self.prompts_path = prompts_path
        self.base_config = self._load_base_config()
        self.taxonomy_str = self._format_taxonomy(self.base_config.get('taxonomy_guitares', {}))
        
        # Le template système est fixe et définit la structure globale
        self.system_template = self._join_if_list(self.base_config.get('system_template', ""))

    def _load_base_config(self) -> Dict[str, Any]:
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Impossible de charger {self.prompts_path}: {e}")
            return {}

    def _format_taxonomy(self, taxonomy_data: Dict) -> str:
        return json.dumps(taxonomy_data, indent=2, ensure_ascii=False)

    def _join_if_list(self, value: Any) -> str:
        if isinstance(value, list):
            return "\n".join(value)
        return str(value) if value is not None else ""

    def get_system_prompt(self, firestore_config: Dict[str, Any]) -> str:
        """
        Construit le System Prompt complet en injectant les blocs dans le template.
        """
        # 1. Récupérer le Persona (champ 'prompt' dans Firestore)
        persona = firestore_config.get('prompt')
        if not persona:
            persona = self.base_config.get('persona', "")
        persona = self._join_if_list(persona)

        # 2. Récupérer les règles de verdict
        rules = firestore_config.get('verdictRules')
        if not rules:
            rules = self.base_config.get('verdict_rules', "")
        rules = self._join_if_list(rules)

        # 3. Récupérer les instructions de raisonnement
        reasoning = firestore_config.get('reasoningInstruction')
        if not reasoning:
            reasoning = self.base_config.get('reasoning_instruction', "")
        reasoning = self._join_if_list(reasoning)

        # 4. Assemblage final via le template
        # Si le template n'est pas chargé correctement, on fait un fallback basique
        if not self.system_template:
            return f"{persona}\n\n{rules}\n\n{reasoning}"

        final_prompt = self.system_template.replace("{persona}", persona)
        final_prompt = final_prompt.replace("{taxonomy}", self.taxonomy_str)
        final_prompt = final_prompt.replace("{verdict_rules}", rules)
        final_prompt = final_prompt.replace("{reasoning_instruction}", reasoning)
        
        return final_prompt

    def get_user_prompt(self, firestore_config: Dict[str, Any], listing_data: Dict[str, Any]) -> str:
        """
        Construit le User Prompt.
        """
        template = firestore_config.get('userPrompt')
        if not template:
            template = self.base_config.get('user_prompt', "")
        
        template = self._join_if_list(template)
        
        # Injection des données
        return template.replace("{title}", str(listing_data.get('title', 'N/A'))) \
                       .replace("{price}", str(listing_data.get('price', 'N/A'))) \
                       .replace("{description}", str(listing_data.get('description', 'N/A')))
