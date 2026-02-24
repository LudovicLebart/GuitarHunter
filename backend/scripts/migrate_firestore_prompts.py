"""
Script de migration & audit Firestore.

Actions :
  1. Audite les clés RACINE du document user et propose de supprimer les inconnues.
  2. Ajoute les nouvelles clés de prompts Tier 2/3 dans analysisConfig (si absentes).
  3. Supprime les clés obsolètes dans analysisConfig.

Usage:
  python backend/scripts/migrate_firestore_prompts.py            # Interactif
  python backend/scripts/migrate_firestore_prompts.py --dry-run  # Aperçu sans modifier
"""

import sys
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# --- SETUP ---
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
root_dir = os.path.abspath(os.path.join(base_dir, '..'))
sys.path.append(root_dir)

load_dotenv(os.path.join(root_dir, '.env'))
APP_ID_TARGET = os.getenv('APP_ID_TARGET')
USER_ID_TARGET = os.getenv('USER_ID_TARGET')

cred_path = os.path.join(base_dir, 'config', 'serviceAccountKey.json')
if not os.path.exists(cred_path):
    print(f"❌ Erreur: Credentials introuvables à {cred_path}")
    sys.exit(1)

try:
    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"❌ Erreur Firebase: {e}")
    sys.exit(1)

# --- CHARGEMENT DES PROMPTS DEPUIS prompts.json ---
prompts_path = os.path.join(root_dir, 'prompts.json')
try:
    with open(prompts_path, 'r', encoding='utf-8') as f:
        prompts_data = json.load(f)
    print("✅ prompts.json chargé.")
except Exception as e:
    print(f"❌ Impossible de charger prompts.json : {e}")
    sys.exit(1)

# --- CONFIG ---

# Nouvelles clés à injecter dans analysisConfig
KEYS_TO_MIGRATE = {
    'analystVerbosityInstruction': 'analyst_verbosity_instruction',
    'expertProContextInstruction': 'expert_pro_context_instruction',
}

# Clés obsolètes dans analysisConfig à supprimer
KEYS_TO_DELETE_IN_ANALYSIS_CONFIG = [
    'expertContextInstruction',  # Remplacée par expertProContextInstruction
]

# Clés LÉGITIMES à la racine du document user (source : _init_firestore_structure dans bot.py)
VALID_ROOT_KEYS = {
    'exclusionKeywords',
    'scanConfig',
    'botStatus',
    'analysisConfig',
    'availableModels',
}


def run_migration(dry_run=False):
    tag = "[DRY-RUN] " if dry_run else ""

    if not APP_ID_TARGET or not USER_ID_TARGET:
        print("❌ APP_ID_TARGET ou USER_ID_TARGET manquants dans .env")
        sys.exit(1)

    user_ref = (
        db.collection('artifacts')
          .document(APP_ID_TARGET)
          .collection('users')
          .document(USER_ID_TARGET)
    )

    user_doc = user_ref.get()
    if not user_doc.exists:
        print(f"❌ Document utilisateur introuvable.")
        sys.exit(1)

    user_data = user_doc.to_dict()
    existing_analysis_config = user_data.get('analysisConfig', {})

    # ====================================================
    # ÉTAPE 1 : Audit des clés RACINE
    # ====================================================
    print(f"\n{'='*55}")
    print("📦 ÉTAPE 1 : Audit des clés racine du document user")
    print(f"{'='*55}")

    all_root_keys = set(user_data.keys())
    unknown_root_keys = all_root_keys - VALID_ROOT_KEYS

    print(f"\n   Clés valides trouvées : {sorted(all_root_keys & VALID_ROOT_KEYS)}")

    if unknown_root_keys:
        print(f"\n   ⚠️  Clés INCONNUES à la racine ({len(unknown_root_keys)}) :")
        for k in sorted(unknown_root_keys):
            val = user_data.get(k)
            preview = str(val)[:60] + "..." if len(str(val)) > 60 else str(val)
            print(f"      - '{k}' : {preview}")

        if not dry_run:
            confirm = input(f"\n   Supprimer ces {len(unknown_root_keys)} clé(s) inconnue(s) ? [o/N] : ").strip().lower()
            if confirm == 'o':
                root_deletions = {k: firestore.DELETE_FIELD for k in unknown_root_keys}
                user_ref.update(root_deletions)
                print(f"   ✅ {len(unknown_root_keys)} clé(s) racine supprimée(s).")
            else:
                print("   ⏭️  Suppression annulée.")
        else:
            print(f"\n   {tag}Seraient supprimées : {sorted(unknown_root_keys)}")
    else:
        print("\n   ✅ Aucune clé inconnue à la racine.")

    # ====================================================
    # ÉTAPE 2 : Injection de nouvelles clés dans analysisConfig
    # ====================================================
    print(f"\n{'='*55}")
    print("➕ ÉTAPE 2 : Injection des clés Tier 2/3 dans analysisConfig")
    print(f"{'='*55}")

    updates = {}
    for fs_key, json_key in KEYS_TO_MIGRATE.items():
        if fs_key in existing_analysis_config:
            print(f"\n   ⏭️  '{fs_key}' déjà présent.")
        else:
            value = prompts_data.get(json_key, '')
            if not value:
                print(f"\n   ⚠️  '{json_key}' introuvable dans prompts.json.")
                continue
            updates[f'analysisConfig.{fs_key}'] = value
            print(f"\n   ➕ '{fs_key}' sera ajouté.")

    if updates:
        if not dry_run:
            user_ref.update(updates)
            print(f"\n   ✅ {len(updates)} clé(s) ajoutée(s) dans analysisConfig.")
        else:
            print(f"\n   {tag}{len(updates)} clé(s) seraient ajoutées.")
    else:
        print("\n   ✅ analysisConfig déjà à jour.")

    # ====================================================
    # ÉTAPE 3 : Suppression des clés obsolètes dans analysisConfig
    # ====================================================
    print(f"\n{'='*55}")
    print("🗑️  ÉTAPE 3 : Nettoyage des clés obsolètes dans analysisConfig")
    print(f"{'='*55}")

    deletions = {}
    for key in KEYS_TO_DELETE_IN_ANALYSIS_CONFIG:
        if key in existing_analysis_config:
            deletions[f'analysisConfig.{key}'] = firestore.DELETE_FIELD
            print(f"\n   🗑️  '{key}' sera supprimée.")
        else:
            print(f"\n   ⏭️  '{key}' absente — rien à faire.")

    if deletions:
        if not dry_run:
            user_ref.update(deletions)
            print(f"\n   ✅ {len(deletions)} clé(s) obsolète(s) supprimée(s).")
        else:
            print(f"\n   {tag}{len(deletions)} clé(s) seraient supprimées.")
    else:
        print("\n   ✅ Aucune clé obsolète dans analysisConfig.")

    print(f"\n{'='*55}")
    print("🏁 Migration terminée.")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("🧪 Mode DRY-RUN — aucune modification ne sera appliquée.\n")
    run_migration(dry_run=dry_run)
