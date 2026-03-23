"""
Authentication utilities: JWT tokens, password hashing, MFA.
"""
import base64
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from cryptography.fernet import Fernet, InvalidToken
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import pyotp

from app.database import get_db
from app.models import User

# --- Config ---
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 7
INITIAL_ADMIN_PASSWORD_MIN_LENGTH = 12
logger = logging.getLogger(__name__)


def _get_required_secret(name: str, min_length: int = 32) -> str:
    value = os.getenv(name, "").strip()
    if len(value) < min_length:
        raise RuntimeError(f"{name} must be set and at least {min_length} characters long")
    return value


def _build_fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


JWT_SECRET = _get_required_secret("JWT_SECRET")
APP_ENCRYPTION_SECRET = os.getenv("APP_ENCRYPTION_KEY", JWT_SECRET).strip()
if len(APP_ENCRYPTION_SECRET) < 32:
    raise RuntimeError("APP_ENCRYPTION_KEY must be at least 32 characters long when set")

_fernet = _build_fernet(APP_ENCRYPTION_SECRET)

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT Tokens ---
def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def encrypt_secret(secret: str) -> str:
    if not secret:
        return secret
    if secret.startswith("enc:"):
        return secret
    return f"enc:{_fernet.encrypt(secret.encode('utf-8')).decode('utf-8')}"


def decrypt_secret(secret: Optional[str]) -> Optional[str]:
    if not secret:
        return secret
    if not secret.startswith("enc:"):
        return secret
    try:
        return _fernet.decrypt(secret[4:].encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored secret could not be decrypted",
        ) from exc


def mask_secret(secret: Optional[str]) -> Optional[str]:
    if not secret:
        return None
    if len(secret) <= 4:
        return "***"
    return "*" * 8 + secret[-4:]


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- FastAPI Dependencies ---
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: extracts and validates the JWT token,
    returns the authenticated User or raises 401.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user is an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Same as get_current_user but returns None instead of raising 401.
    Useful for endpoints that work both with and without auth.
    """
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


# --- MFA (TOTP) ---
def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def get_mfa_provisioning_uri(secret: str, email: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name="AutoTrade Pro")


def verify_mfa_code(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)  # allows ±30s drift


def _get_initial_admin_config() -> dict | None:
    email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    mfa_enabled = os.getenv("INITIAL_ADMIN_MFA_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not email and not password:
        return None
    if not email or not password:
        raise RuntimeError("INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD must either both be set or both be empty")
    if len(password) < INITIAL_ADMIN_PASSWORD_MIN_LENGTH:
        raise RuntimeError(
            f"INITIAL_ADMIN_PASSWORD must be at least {INITIAL_ADMIN_PASSWORD_MIN_LENGTH} characters long"
        )
    return {
        "email": email,
        "password": password,
        "mfa_enabled": mfa_enabled,
    }


def ensure_initial_admin(db: Session) -> User | None:
    config = _get_initial_admin_config()
    if not config:
        return None

    admin_exists = db.query(User).filter(User.is_admin == True).first()
    if admin_exists:
        logger.info(
            "initial_admin_bootstrap_skipped_existing_admin",
            extra={"user_id": admin_exists.id},
        )
        return admin_exists

    user = db.query(User).filter(User.email == config["email"]).first()
    if user:
        user.is_admin = True
        user.is_active = True
        user.hashed_password = hash_password(config["password"])
        user.mfa_enabled = config["mfa_enabled"]
        if not config["mfa_enabled"]:
            user.mfa_secret = None
        action = "promoted"
    else:
        user = User(
            email=config["email"],
            hashed_password=hash_password(config["password"]),
            is_admin=True,
            is_active=True,
            mfa_enabled=config["mfa_enabled"],
        )
        db.add(user)
        action = "created"

    db.commit()
    db.refresh(user)
    logger.warning(
        "initial_admin_bootstrapped",
        extra={
            "user_id": user.id,
            "action": action,
            "mfa_enabled": user.mfa_enabled,
        },
    )
    return user
