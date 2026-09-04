from __future__ import annotations

from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import SaaSConfig
from .database import SaaSDatabase


@dataclass(frozen=True)
class Identity:
    id: int
    uid: str
    email: str
    name: str
    role: str


class AuthService:
    COOKIE = "tesda_session"

    def __init__(self, cfg: SaaSConfig, db: SaaSDatabase):
        self.cfg, self.db = cfg, db
        self.signer = URLSafeTimedSerializer(cfg.session_secret, salt="tesda-saas-session-v1")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(cfg.firebase_service_account_path), {"projectId":cfg.firebase_project_id})

    def exchange(self, id_token: str) -> str:
        try:
            claims = auth.verify_id_token(id_token, check_revoked=True)
        except Exception as exc:
            raise HTTPException(401, "Firebase sign-in could not be verified") from exc
        email = claims.get("email", "")
        if not email or not claims.get("email_verified", False):
            raise HTTPException(403, "Verify your email address before continuing")
        user = self.db.user_for_token(claims["uid"], email, claims.get("name", ""), self.cfg.admin_email)
        return self.signer.dumps({"uid": claims["uid"], "id": user["id"], "email": email,
                                  "name": user["display_name"], "role": user["role"]})

    def current(self, request: Request, required: bool=True) -> Identity | None:
        token = request.cookies.get(self.COOKIE)
        if not token:
            if required: raise HTTPException(401, "Sign in required")
            return None
        try:
            data = self.signer.loads(token, max_age=7 * 24 * 3600)
            return Identity(data["id"], data["uid"], data["email"], data.get("name", ""), data["role"])
        except (BadSignature, SignatureExpired, KeyError) as exc:
            if required: raise HTTPException(401, "Session expired; sign in again") from exc
            return None
