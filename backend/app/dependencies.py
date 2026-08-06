from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
import hashlib

from sqlalchemy import select

from .models import DeviceToken, User, utcnow
from .security import decode_token


bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired login")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not available")
    return user


def get_vscode_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connect VS Code from the Student Dashboard")
    raw = credentials.credentials
    user = None
    if raw.startswith("gaint_vsc_"):
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        device = db.scalar(select(DeviceToken).where(DeviceToken.token_hash == token_hash))
        if device and not device.revoked_at and device.expires_at >= utcnow():
            user = db.get(User, device.user_id)
            device.last_used_at = utcnow()
            db.commit()
    else:
        payload = decode_token(raw)
        if payload:
            user = db.get(User, int(payload["sub"]))
    if not user or not user.active or user.role != "student":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid, expired or revoked VS Code connection")
    return user


def require_role(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return user

    return dependency
