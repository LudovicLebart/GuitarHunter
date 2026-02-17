import sys
import os
import json
import logging

# Ajout du chemin racine pour les imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.analyzer import DealAnalyzer
from config import GEMINI_API_KEY

# Configuration du logging pour voir les sorties
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_prompt_logic():
    """
    Test simple pour vérifier que Gemini comprend la nouvelle logique de classification.
    On simule une annonce "CASE_WIN" évidente.
    """
    if not GEMINI_API_KEY:
        print("❌ ERREUR: Pas de clé API Gemini configurée.")
        return

    analyzer = DealAnalyzer()
    
    # Cas de test : Une guitare bas de gamme mais avec un étui rigide Gibson de valeur
    mock_listing = {
        "title": "Guitare électrique avec étui rigide Gibson",
        "price": 150,
        "description": "Je vends ma vieille guitare First Act, elle ne marche plus très bien. Mais je la donne avec un étui rigide Gibson Les Paul original en parfait état (valeur 200$). Pas d'échange.",
        "location": "Montreal",
        "imageUrls": [] # Pas d'images pour ce test textuel
    }

    print(f"\n--- TEST: Envoi de l'annonce simulée ---")
    print(f"Titre: {mock_listing['title']}")
    print(f"Prix: {mock_listing['price']}$")
    print(f"Description: {mock_listing['description']}")
    print("-" * 30)

    # On force l'expert pour avoir l'analyse complète directement
    # On charge la config depuis prompts.json (simulé ici car analyzer le fait en interne ou via firestore)
    # Pour ce test unitaire, on va laisser analyzer utiliser ses défauts, 
    # MAIS analyzer.py charge DEFAULT_MAIN_PROMPT depuis config.py qui lui même ne lit pas prompts.json dynamiquement
    # Il faut s'assurer que analyzer utilise bien le contenu de prompts.json mis à jour.
    
    # HACK: On va lire prompts.json manuellement et le passer à analyzer si possible, 
    # ou alors on compte sur le fait que config.py a été rechargé ou que analyzer lit prompts.json.
    # Vérifions analyzer.py... Il importe DEFAULT_MAIN_PROMPT de config.py.
    # config.py lit-il prompts.json ? Non, il a des constantes.
    # C'est un problème pour le test si on vient de modifier prompts.json mais pas config.py.
    
    # SOLUTION: On va lire prompts.json ici et construire la config Firestore simulée.
    with open('prompts.json', 'r', encoding='utf-8') as f:
        prompts_data = json.load(f)
    
    firestore_config = {
        'analysisConfig': {
            'mainAnalysisPrompt': prompts_data['main_analysis_prompt'],
            'expertModel': 'gemini-2.5-flash', # Ou un modèle valide
            'gatekeeperModel': 'gemini-2.5-flash-lite'
        }
    }

    result = analyzer.analyze_deal(mock_listing, firestore_config=firestore_config, force_expert=True)

    print("\n--- RÉSULTAT DE L'ANALYSE ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Vérifications basiques
    verdict = result.get('verdict')
    specs = result.get('specs', {})
    
    if verdict == 'CASE_WIN':
        print("\n✅ SUCCÈS: Verdict 'CASE_WIN' correctement identifié.")
    elif verdict == 'PEPITE':
        print("\n⚠️ PARTIEL: Verdict 'PEPITE' (Acceptable, car très rentable).")
    else:
        print(f"\n❌ ÉCHEC: Verdict attendu 'CASE_WIN', obtenu '{verdict}'.")

    if specs.get('case_value', 0) > 100:
        print(f"✅ SUCCÈS: Valeur de l'étui bien estimée ({specs.get('case_value')}$).")
    else:
        print(f"❌ ÉCHEC: Valeur de l'étui sous-estimée ({specs.get('case_value')}$).")

if __name__ == "__main__":
    test_prompt_logic()
