"""Vérification du ID token Firebase pour l'API Postgres — remplace les Firestore Security
Rules (FIRESTORE_MIGRATION_PLAN.md §1) : l'autorisation par ligne (`WHERE user_id = uid`)
prend le relais côté SQL, une fois le `uid` extrait ici.

Ce service n'a besoin que de Firebase Auth, pas de Firestore/Storage — initialisation
minimale et indépendante de `backend/database.py::DatabaseService` (qui reste, lui,
utilisé par le bot tant que la bascule n'a pas eu lieu).
"""
import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from fastapi import Header, HTTPException, status

FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH", "backend/config/serviceAccountKey.json")


def _ensure_firebase_app() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)


async def get_current_uid(authorization: str = Header(...)) -> str:
    """Dépendance FastAPI : extrait et vérifie le Bearer token Firebase, renvoie le `uid`.

    Lève 401 sur token absent/invalide/expiré plutôt que de laisser une requête non
    authentifiée atteindre une requête SQL filtrée par `user_id`.
    """
    _ensure_firebase_app()

    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "En-tête Authorization manquant ou mal formé (attendu: 'Bearer <token>').")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token Firebase invalide : {e}")

    return decoded["uid"]
