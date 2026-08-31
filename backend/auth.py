import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from jose import jwt
from jose import JWTError
from passlib.context import CryptContext

from users_db import get_user_by_id

from typing import List

from projects_db import get_project_by_id, get_project_member

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _require_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Copy .env.example to .env at the repo root "
            "and set it to a long random string."
        )
    return secret


def create_access_token(user_id: int, email: str) -> str:
    secret = _require_jwt_secret()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    claims = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    secret = _require_jwt_secret()
    return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])


def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization header.")

    token = authorization[len("Bearer "):]
    try:
        claims = decode_access_token(token)
        user_id = int(claims["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")
    if not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User account is deactivated.")
    return user


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="SystemAdmin privileges required.")
    return current_user


def require_admin_or_consultant(project_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("is_admin"):
        return current_user
    member = get_project_member(project_id, current_user["id"])
    if member is None or member["role"] != "Consultant":
        raise HTTPException(status_code=403, detail="You are not authorized to manage this project's members.")
    return member


def require_project_role(allowed_roles: List[str]):
    def _dependency(project_id: int, current_user: dict = Depends(get_current_user)) -> dict:
        member = get_project_member(project_id, current_user["id"])
        if member is None:
            raise HTTPException(status_code=403, detail="You are not a member of this project.")
        if member["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Your project role does not permit this action.")
        return member
    return _dependency


# Does not check membership by itself — compose with require_project_role
# (e.g. require_project_member) on routes that need both checks.
def require_active_project(project_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    member = get_project_member(project_id, current_user["id"])
    if member is not None and member["role"] == "ClientUser" and project["status"] != "Active":
        raise HTTPException(status_code=403, detail="This project is not active yet.")

    return project
