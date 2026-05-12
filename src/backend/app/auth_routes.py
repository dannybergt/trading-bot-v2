"""
Authentication API routes: register, login, password reset, MFA.
"""
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app import audit_service
from app.database import get_db
from app.logging_config import fingerprint_value
from app.models import User, PasswordResetToken
from app.email_service import PasswordResetDeliveryError, send_password_reset_email
from app.push_service import PushConfigurationError, PushService
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    get_current_user,
    get_current_admin_user,
    generate_mfa_secret,
    hash_reset_token,
    get_mfa_provisioning_uri,
    mask_secret,
    verify_mfa_code,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)
_RATE_LIMITS = {
    "login": (5, 300),
    # Per-account login limit: stricter than the per-IP one because an
    # attacker that rotates source IPs would otherwise bypass the per-IP
    # bucket entirely. 10 attempts per 15 minutes against a single email.
    "login_per_account": (10, 900),
    "password_reset_request": (3, 900),
    "password_reset_confirm": (5, 900),
}
_rate_limit_buckets = defaultdict(deque)


def _enforce_rate_limit(scope: str, key: str):
    limit, window_seconds = _RATE_LIMITS[scope]
    bucket = _rate_limit_buckets[(scope, key)]
    now = time.time()
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
    bucket.append(now)


def _request_identity(request: Request, suffix: str = "") -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{suffix}".lower()


# --- Request/Response Models ---

class RegisterRequest(BaseModel):
    email: str
    password: str
    is_admin: bool = False

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    mfa_required: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class AdminPasswordResetRequest(BaseModel):
    new_password: str
    reset_mfa: bool = False

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class MFACodeRequest(BaseModel):
    code: str


class UserResponse(BaseModel):
    id: int
    email: str
    is_admin: bool
    is_active: bool
    mfa_enabled: bool
    alpaca_configured: bool = False

    class Config:
        from_attributes = True

class AlpacaConfigResponse(BaseModel):
    api_key: str | None
    secret_key_masked: str | None
    is_paper: bool

class AlpacaConfigRequest(BaseModel):
    api_key: str
    secret_key: str
    is_paper: bool = True

class PortfolioSettingsResponse(BaseModel):
    trade_fee_absolute: int
    trade_fee_percent: int
    min_target_yield: int
    capital_gains_tax_bps: int = 0
    income_tax_bps: int = 0
    display_currency: str = "USD"

class PortfolioSettingsRequest(BaseModel):
    trade_fee_absolute: int
    trade_fee_percent: int
    min_target_yield: int
    capital_gains_tax_bps: int = 0
    income_tax_bps: int = 0
    display_currency: str = "USD"

class PushSubscriptionRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


# --- Routes ---

@router.post("/register", response_model=UserResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user. First user becomes admin."""
    # Check if email already exists
    existing = db.query(User).filter(User.email == req.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # First user is admin
    user_count = db.query(User).count()
    is_admin = user_count == 0

    user = User(
        email=req.email.lower(),
        hashed_password=hash_password(req.password),
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(
        "user_registered",
        extra={
            "user_id": user.id,
            "is_admin": is_admin,
        },
    )
    audit_service.log_event(
        db,
        user_id=user.id,
        action=audit_service.ACTION_AUTH_REGISTER,
        actor_email=req.email,
        details={"is_admin": is_admin},
    )
    return user


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Login with email + password.
    If MFA is enabled, requires mfa_code field.
    """
    _enforce_rate_limit("login", _request_identity(request, req.email))
    # Second bucket keyed only on the email so an attacker that rotates
    # source IPs still hits a per-account ceiling.
    _enforce_rate_limit("login_per_account", req.email.lower())
    user = db.query(User).filter(User.email == req.email.lower()).first()

    audit_ctx = {
        "actor_email": req.email,
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }

    if not user or not verify_password(req.password, user.hashed_password):
        audit_service.log_event(
            db,
            action=audit_service.ACTION_AUTH_LOGIN_FAILED,
            outcome="failure",
            details={"reason": "invalid_credentials"},
            **audit_ctx,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        audit_service.log_event(
            db,
            user_id=user.id,
            action=audit_service.ACTION_AUTH_LOGIN_FAILED,
            outcome="denied",
            details={"reason": "account_inactive"},
            **audit_ctx,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # MFA check
    if user.mfa_enabled:
        if not req.mfa_code:
            # Tell frontend that MFA code is needed
            return {"mfa_required": True, "access_token": "", "refresh_token": "", "token_type": "bearer"}

        if not verify_mfa_code(user.mfa_secret, req.mfa_code):
            audit_service.log_event(
                db,
                user_id=user.id,
                action=audit_service.ACTION_AUTH_LOGIN_FAILED,
                outcome="failure",
                details={"reason": "invalid_mfa"},
                **audit_ctx,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    audit_service.log_event(
        db,
        user_id=user.id,
        action=audit_service.ACTION_AUTH_LOGIN,
        outcome="success",
        details={"mfa_used": bool(user.mfa_enabled)},
        **audit_ctx,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "mfa_required": False,
    }


@router.post("/refresh")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    """Refresh an expired access token using refresh token."""
    payload = decode_token(req.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    new_access_token = create_access_token(user.id, user.email)
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user profile."""
    # Add computed field for frontend convenience
    setattr(current_user, "alpaca_configured", bool(current_user.alpaca_api_key))
    return current_user

@router.get("/me/alpaca", response_model=AlpacaConfigResponse)
def get_my_alpaca_config(current_user: User = Depends(get_current_user)):
    """Get the user's Alpaca configuration with the secret key masked."""
    masked_secret = mask_secret(decrypt_secret(current_user.alpaca_secret_key))

    return {
        "api_key": current_user.alpaca_api_key,
        "secret_key_masked": masked_secret,
        "is_paper": current_user.alpaca_paper
    }

@router.put("/me/alpaca", response_model=AlpacaConfigResponse)
def update_my_alpaca_config(req: AlpacaConfigRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update the user's Alpaca API keys."""
    secret_changed = bool(req.secret_key and not req.secret_key.startswith("*"))
    current_user.alpaca_api_key = req.api_key

    # Only update secret if a new one is provided (not a masked string)
    if secret_changed:
        current_user.alpaca_secret_key = encrypt_secret(req.secret_key)

    current_user.alpaca_paper = req.is_paper
    db.commit()
    audit_service.log_event(
        db,
        user_id=current_user.id,
        action=audit_service.ACTION_SETTINGS_ALPACA,
        details={"is_paper": req.is_paper, "secret_rotated": secret_changed},
    )
    return get_my_alpaca_config(current_user)

@router.get("/me/portfolio-settings", response_model=PortfolioSettingsResponse)
def get_my_portfolio_settings(current_user: User = Depends(get_current_user)):
    return {
        "trade_fee_absolute": current_user.trade_fee_absolute,
        "trade_fee_percent": current_user.trade_fee_percent,
        "min_target_yield": current_user.min_target_yield,
        "capital_gains_tax_bps": current_user.capital_gains_tax_bps or 0,
        "income_tax_bps": current_user.income_tax_bps or 0,
        "display_currency": current_user.display_currency or "USD",
    }

@router.put("/me/portfolio-settings", response_model=PortfolioSettingsResponse)
def update_my_portfolio_settings(req: PortfolioSettingsRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.fx_service import SUPPORTED_CURRENCIES

    current_user.trade_fee_absolute = req.trade_fee_absolute
    current_user.trade_fee_percent = req.trade_fee_percent
    current_user.min_target_yield = req.min_target_yield
    current_user.capital_gains_tax_bps = max(0, min(req.capital_gains_tax_bps, 10000))
    current_user.income_tax_bps = max(0, min(req.income_tax_bps, 10000))
    # display_currency: validate against the supported set; fall back to USD
    # rather than 400 so an older client without the field doesn't break.
    requested_currency = (req.display_currency or "USD").upper().strip()
    if requested_currency in SUPPORTED_CURRENCIES:
        current_user.display_currency = requested_currency
    else:
        current_user.display_currency = "USD"
    db.commit()
    audit_service.log_event(
        db,
        user_id=current_user.id,
        action=audit_service.ACTION_SETTINGS_PORTFOLIO,
        details={
            "trade_fee_absolute": req.trade_fee_absolute,
            "trade_fee_percent": req.trade_fee_percent,
            "min_target_yield": req.min_target_yield,
            "capital_gains_tax_bps": current_user.capital_gains_tax_bps,
            "income_tax_bps": current_user.income_tax_bps,
            "display_currency": current_user.display_currency,
        },
    )
    return get_my_portfolio_settings(current_user)


# --- Password Reset ---

@router.post("/password-reset/request")
def request_password_reset(req: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    """
    Request a password reset. Generates a token and stores only a hash.
    """
    _enforce_rate_limit("password_reset_request", _request_identity(request, req.email))
    user = db.query(User).filter(User.email == req.email.lower()).first()

    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If the email exists, reset instructions have been queued."}

    # Invalidate existing tokens
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,
    ).update({"used": True})

    # Generate new token
    token = secrets.token_urlsafe(32)
    token_hash = hash_reset_token(token)
    reset = PasswordResetToken(
        user_id=user.id,
        token=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(reset)
    db.commit()

    if os.getenv("ENABLE_INSECURE_DEBUG_RESET_TOKENS", "").lower() in {"1", "true", "yes"}:
        logger.warning("Password reset debug token exposure is enabled")
        return {
            "message": "If the email exists, reset instructions have been queued.",
            "debug_reset_token": token,
        }

    try:
        send_password_reset_email(user.email, token)
    except PasswordResetDeliveryError as exc:
        logger.error(
            "password_reset_delivery_unavailable",
            extra={
                "user_id": user.id,
                "recipient_fingerprint": fingerprint_value(user.email),
                "error": str(exc),
            },
        )

    return {"message": "If the email exists, reset instructions have been queued."}


@router.post("/password-reset/confirm")
def confirm_password_reset(req: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
    """Reset password using the token."""
    _enforce_rate_limit("password_reset_confirm", _request_identity(request))
    token_hash = hash_reset_token(req.token)
    reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token_hash,
        PasswordResetToken.used == False,
    ).first()

    if not reset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    if reset.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired",
        )

    user = db.query(User).filter(User.id == reset.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = hash_password(req.new_password)
    reset.used = True
    db.commit()

    audit_service.log_event(
        db,
        user_id=user.id,
        action=audit_service.ACTION_AUTH_PASSWORD_RESET_CONFIRM,
        actor_email=user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    return {"message": "Password has been reset successfully"}


# --- MFA ---

@router.post("/mfa/setup")
def mfa_setup(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate MFA secret and provisioning URI for QR code."""
    secret = generate_mfa_secret()

    # Save secret but don't enable yet
    current_user.mfa_secret = secret
    db.commit()

    uri = get_mfa_provisioning_uri(secret, current_user.email)

    return {
        "secret": secret,
        "provisioning_uri": uri,
        "message": "Scan the QR code with your authenticator app, then verify with /mfa/enable",
    }


@router.post("/mfa/enable")
def mfa_enable(req: MFACodeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Verify MFA code and enable MFA for the user."""
    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA not set up. Call /mfa/setup first.",
        )

    if not verify_mfa_code(current_user.mfa_secret, req.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code. Please try again.",
        )

    current_user.mfa_enabled = True
    db.commit()

    audit_service.log_event(
        db,
        user_id=current_user.id,
        action=audit_service.ACTION_AUTH_MFA_ENABLE,
    )
    return {"message": "MFA enabled successfully", "mfa_enabled": True}


@router.post("/mfa/disable")
def mfa_disable(req: MFACodeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Disable MFA. Requires a valid current code for security."""
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled",
        )

    if not verify_mfa_code(current_user.mfa_secret, req.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code",
        )

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    db.commit()

    audit_service.log_event(
        db,
        user_id=current_user.id,
        action=audit_service.ACTION_AUTH_MFA_DISABLE,
    )
    return {"message": "MFA disabled successfully", "mfa_enabled": False}


# --- PUSH NOTIFICATIONS ---

@router.get("/push/config")
def get_push_config():
    """Return public Web Push configuration for browser subscription."""
    try:
        config = PushService.validate_configuration(require_config=False)
    except PushConfigurationError as exc:
        logger.error("push_config_invalid error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not configured correctly",
        ) from exc

    return {
        "configured": config["configured"],
        "publicKey": config.get("public_key"),
    }


@router.post("/push/subscribe")
def subscribe_push(req: PushSubscriptionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Save user web push subscription"""
    from app.models import PushSubscription
    # Check if this endpoint already exists
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == req.endpoint).first()
    if existing:
        if existing.user_id != current_user.id:
            existing.user_id = current_user.id
            db.commit()
        return {"message": "Subscription updated"}

    # Register new endpoint
    sub = PushSubscription(
        user_id=current_user.id,
        endpoint=req.endpoint,
        p256dh=req.p256dh,
        auth=req.auth
    )
    db.add(sub)
    db.commit()
    return {"message": "Subscribed securely to push notifications"}


# --- ADMIN USER MANAGEMENT ---

@router.get("/admin/users", response_model=list[UserResponse])
def get_all_users(admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """List all users."""
    return db.query(User).all()


@router.post("/admin/users", response_model=UserResponse)
def create_user_admin(req: RegisterRequest, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Admin endpoint to create a new user manually."""
    existing = db.query(User).filter(User.email == req.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=req.email.lower(),
        hashed_password=hash_password(req.password),
        is_admin=req.is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(
        "admin_created_user",
        extra={
            "user_id": user.id,
            "admin_user_id": admin.id,
            "is_admin": user.is_admin,
        },
    )
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_ADMIN_USER_CREATE,
        resource_type="user",
        resource_id=user.id,
        details={"target_email_fingerprint": fingerprint_value(user.email), "is_admin": user.is_admin},
    )
    return user


@router.put("/admin/users/{user_id}/reset-mfa", response_model=UserResponse)
def reset_user_mfa(user_id: int, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Reset MFA for a user who lost access."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    db.refresh(user)
    
    logger.info(
        "admin_reset_mfa",
        extra={
            "user_id": user.id,
            "admin_user_id": admin.id,
        },
    )
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_AUTH_MFA_RESET,
        resource_type="user",
        resource_id=user.id,
    )
    return user


@router.put("/admin/users/{user_id}/password", response_model=UserResponse)
def reset_user_password_admin(
    user_id: int,
    req: AdminPasswordResetRequest,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Admin endpoint to reset a user's password for account recovery."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(req.new_password)
    if req.reset_mfa:
        user.mfa_enabled = False
        user.mfa_secret = None

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,
    ).update({"used": True})

    db.commit()
    db.refresh(user)

    logger.info(
        "admin_reset_password",
        extra={
            "user_id": user.id,
            "admin_user_id": admin.id,
            "reset_mfa": req.reset_mfa,
        },
    )
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_ADMIN_USER_PASSWORD_RESET,
        resource_type="user",
        resource_id=user.id,
        details={"reset_mfa": req.reset_mfa},
    )
    return user


@router.put("/admin/users/{user_id}/status", response_model=UserResponse)
def toggle_user_status(user_id: int, active: bool, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Ban or unban a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    user.is_active = active
    db.commit()
    db.refresh(user)
    logger.info(
        "admin_updated_user_status",
        extra={
            "user_id": user.id,
            "admin_user_id": admin.id,
            "is_active": active,
        },
    )
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_ADMIN_USER_TOGGLE_ACTIVE,
        resource_type="user",
        resource_id=user.id,
        details={"is_active": active},
    )
    return user
