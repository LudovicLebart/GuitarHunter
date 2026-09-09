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


def verify_token(token: str) -> str:
    """Vérifie un ID token Firebase brut (sans le préfixe `Bearer `) et renvoie le `uid`.

    Partagé entre l'auth HTTP (en-tête `Authorization`) et l'auth WebSocket (le navigateur
    ne peut pas poser d'en-tête personnalisé sur une connexion WS native — le token est donc
    passé en paramètre de requête `?token=...` côté client, voir main.py).
    """
    _ensure_firebase_app()
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as e:
        raise ValueError(f"Token Firebase invalide : {e}")
    return decoded["uid"]


async def get_current_uid(authorization: str = Header(...)) -> str:
    """Dépendance FastAPI (routes HTTP) : extrait et vérifie le Bearer token Firebase.

    Lève 401 sur token absent/invalide/expiré plutôt que de laisser une requête non
    authentifiée atteindre une requête SQL filtrée par `user_id`.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "En-tête Authorization manquant ou mal formé (attendu: 'Bearer <token>').")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        return verify_token(token)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
