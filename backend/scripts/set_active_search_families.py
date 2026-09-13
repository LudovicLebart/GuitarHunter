"""Chantier G (validation) : configure `analysisConfig.activeSearchFamilies` pour tester le
routage T1->T2/T3 par recherche active en conditions réelles (voir
docs/management/plans/COST_OPTIMIZATION_CHANTIERS.md, Chantier G).

Valeur choisie : famille "Parlor" (`guitare.acoustique_acier.formes_standard.Parlor`, chemin
canonique exact de `prompts.json::taxonomy_master`) — reprend l'exemple donné par l'utilisateur
lui-même ("guitares parlor"), au niveau "promotion large" (famille de forme, pas modèle précis).

Écrit sur TOUS les utilisateurs enregistrés via une mise à jour en notation pointée
(`analysisConfig.activeSearchFamilies`), qui ne touche QUE ce champ sans écraser le reste
d'`analysisConfig` (gatekeeperModel, prompts, etc.). Sans effet réel sur un utilisateur sans
volume actif.

Pour désactiver (revenir au comportement "tout analyser" par défaut) : relancer avec
--clear, qui remet le champ à une liste vide.

Usage :
  python -m backend.scripts.set_active_search_families
  python -m backend.scripts.set_active_search_families --clear
"""
import argparse
import os
import sys

sys.path.insert(0, os.getcwd())

ACTIVE_SEARCH_FAMILIES = ["guitare.acoustique_acier.formes_standard.Parlor"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true", help="Remet activeSearchFamilies à [] (désactive le filtre).")
    args = parser.parse_args()

    from backend.scripts.export_neck_reset_sample import setup_firebase
    from config import APP_ID_TARGET

    db = setup_firebase()
    users_ref = db.collection('artifacts').document(APP_ID_TARGET).collection('users')
    user_ids = [doc.id for doc in users_ref.stream()]
    print(f"🔍 {len(user_ids)} utilisateur(s) trouvé(s).")

    value = [] if args.clear else ACTIVE_SEARCH_FAMILIES
    for uid in user_ids:
        users_ref.document(uid).update({"analysisConfig.activeSearchFamilies": value})
        print(f"  ✅ {uid} : activeSearchFamilies = {value}")

    if args.clear:
        print("\nFiltre désactivé pour tous les utilisateurs — comportement 'tout analyser' restauré.")
    else:
        print(f"\nFiltre activé : seules les annonces classées sous '{value[0]}' (ou une pépite, "
              f"garde-fou) seront promues vers T2/T3. Relancer avec --clear pour désactiver.")


if __name__ == "__main__":
    main()
