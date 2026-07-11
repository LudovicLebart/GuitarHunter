"""
Script one-shot pour poser (ou retirer) le custom claim Firebase `admin: true`
sur un compte utilisateur. Ce claim est lu par les règles Firestore
(collectionGroup sur `users`/`guitar_deals`) pour autoriser l'accès
cross-utilisateurs du Dashboard Administrateur.

Usage :
    python backend/scripts/set_admin_claim.py --email admin@example.com
    python backend/scripts/set_admin_claim.py --email admin@example.com --revoke
"""
import sys
import os
import argparse
import firebase_admin
from firebase_admin import auth, credentials

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from config import FIREBASE_KEY_PATH


def setup_firebase():
    if not firebase_admin._apps:
        if not os.path.exists(FIREBASE_KEY_PATH):
            print(f"❌ Erreur : Fichier de clé introuvable à {FIREBASE_KEY_PATH}")
            sys.exit(1)
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)


def set_admin_claim(email, revoke=False):
    setup_firebase()
    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        print(f"❌ Aucun utilisateur Firebase Auth trouvé pour l'email : {email}")
        sys.exit(1)

    current_claims = user.custom_claims or {}

    if revoke:
        if not current_claims.get('admin'):
            print(f"ℹ️  {email} ({user.uid}) n'a pas le claim admin. Rien à faire.")
            return
        new_claims = {k: v for k, v in current_claims.items() if k != 'admin'}
        auth.set_custom_user_claims(user.uid, new_claims)
        print(f"✅ Claim admin retiré pour {email} ({user.uid}).")
    else:
        if current_claims.get('admin'):
            print(f"ℹ️  {email} ({user.uid}) a déjà le claim admin. Rien à faire.")
            return
        new_claims = {**current_claims, 'admin': True}
        auth.set_custom_user_claims(user.uid, new_claims)
        print(f"✅ Claim admin posé pour {email} ({user.uid}).")

    print("⚠️  Le claim n'est pris en compte qu'au prochain rafraîchissement du token "
          "(l'utilisateur doit se reconnecter, ou attendre l'expiration du token en cours ~1h).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pose ou retire le custom claim admin sur un compte Firebase Auth")
    parser.add_argument("--email", required=True, help="Email du compte cible")
    parser.add_argument("--revoke", action="store_true", help="Retire le claim admin au lieu de le poser")
    args = parser.parse_args()

    set_admin_claim(args.email, revoke=args.revoke)
