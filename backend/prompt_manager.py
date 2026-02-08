import json
import logging
from typing import Dict, Any, List, Union

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Gère l'assemblage et la configuration des prompts pour l'IA.
    Architecture "Blocs" : Assemble le prompt système à partir de composants indépendants.
    """
    
    # Format JSON strict attendu par le parser
    JSON_FORMAT = """{
    "classification": "Stratocaster",
    "identification": "Marque, Modèle, Origine",
    "estimated_value": 0,
    "estimated_value_after_repair": 0,
    "verdict": "PEPITE / GOOD_DEAL / FAIR / BAD_DEAL / REJECTED",
    "visual_condition_score": "Note sur 10",
    "reasoning": "Rapport complet au format Markdown (Résumé, Analyse Modèle, Inspection, Verdict Financier, Conseils)"
}"""

    def __init__(self, prompts_path: str = 'prompts.json'):
        self.prompts_path = prompts_path
        self.base_config = self._load_base_config()
        self.taxonomy_str = self._format_taxonomy(self.base_config.get('taxonomy_guitares', {}))
        
        # Structure globale du prompt système (liste de lignes)
        self.system_structure = self.base_config.get('system_structure', [])

    def _load_base_config(self) -> Dict[str, Any]:
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Impossible de charger {self.prompts_path}: {e}")
            return {}

    def _format_taxonomy(self, taxonomy_data: Dict) -> str:
        return json.dumps(taxonomy_data, indent=2, ensure_ascii=False)

    def _ensure_list(self, value: Union[str, List[str]]) -> List[str]:
        """Convertit une chaîne ou une liste en liste de chaînes."""
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return value.split('\n')
        return []

    def _join_list(self, value: List[str]) -> str:
        """Joint une liste de chaînes avec des sauts de ligne."""
        return "\n".join(value)

    def get_system_prompt(self, firestore_config: Dict[str, Any]) -> str:
        """
        Construit le System Prompt complet en injectant les blocs dans la structure.
        """
        # 1. Récupérer les blocs (Priorité Firestore > JSON)
        # Note: 'prompt' dans Firestore correspond au Persona
        persona = self._ensure_list(firestore_config.get('prompt') or self.base_config.get('persona', []))
        rules = self._ensure_list(firestore_config.get('verdictRules') or self.base_config.get('verdict_rules', []))
        reasoning = self._ensure_list(firestore_config.get('reasoningInstruction') or self.base_config.get('reasoning_instruction', []))

        # 2. Préparer les blocs de texte
        persona_str = self._join_list(persona)
        rules_str = self._join_list(rules)
        reasoning_str = self._join_list(reasoning)

        # 3. Assemblage final via la structure
        final_lines = []
        
        # Si la structure n'est pas définie, on utilise un fallback
        structure = self.system_structure
        if not structure:
            structure = [
                "### IDENTITÉ", "{persona}", "",
                "### TAXONOMIE", "{taxonomy}", "",
                "### RÈGLES", "{verdict_rules}", "",
                "### STYLE", "{reasoning_instruction}", "",
                "### FORMAT", "{json_format}"
            ]

        for line in structure:
            line = line.replace("{persona}", persona_str)
            line = line.replace("{taxonomy}", self.taxonomy_str)
            line = line.replace("{verdict_rules}", rules_str)
            line = line.replace("{reasoning_instruction}", reasoning_str)
            line = line.replace("{json_format}", self.JSON_FORMAT)
            final_lines.append(line)
        
        return "\n".join(final_lines)

    def get_user_prompt(self, firestore_config: Dict[str, Any], listing_data: Dict[str, Any]) -> str:
        """
        Construit le User Prompt.
        """
        template_list = self._ensure_list(firestore_config.get('userPrompt') or self.base_config.get('user_prompt', []))
        template = self._join_list(template_list)
        
        # Injection des données
        return template.replace("{title}", str(listing_data.get('title', 'N/A'))) \
                       .replace("{price}", str(listing_data.get('price', 'N/A'))) \
                       .replace("{description}", str(listing_data.get('description', 'N/A')))
