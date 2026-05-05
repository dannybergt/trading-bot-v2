"""
Database models for user management.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    alpaca_api_key = Column(String, nullable=True)
    alpaca_secret_key = Column(String, nullable=True)
    alpaca_paper = Column(Boolean, default=True)
    
    # Portfolio Settings
    trade_fee_absolute = Column(Integer, default=1) # in dollars/euros
    trade_fee_percent = Column(Integer, default=0) # percentage 0-100
    min_target_yield = Column(Integer, default=1) # minimum profit percentage
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    alert_settings = relationship("WatchlistAlertSetting", back_populates="user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    endpoint = Column(String, unique=True, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="watchlists")
    items = relationship("WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")
    alert_settings = relationship("WatchlistAlertSetting", back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistAlertSetting(Base):
    __tablename__ = "watchlist_alert_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    watchlist_id = Column(String, ForeignKey("watchlists.id"), index=True, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    toast_enabled = Column(Boolean, default=True, nullable=False)
    push_enabled = Column(Boolean, default=False, nullable=False)
    min_priority = Column(String, default="high", nullable=False)
    min_score = Column(Integer, default=70, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="alert_settings")
    watchlist = relationship("Watchlist", back_populates="alert_settings")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, index=True)
    watchlist_id = Column(String, ForeignKey("watchlists.id"), index=True, nullable=False)
    symbol = Column(String, nullable=False)
    name = Column(String, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    watchlist = relationship("Watchlist", back_populates="items")
    tags = relationship("WatchlistItemTag", back_populates="watchlist_item", cascade="all, delete-orphan")


class WatchlistItemTag(Base):
    __tablename__ = "watchlist_item_tags"

    id = Column(Integer, primary_key=True, index=True)
    watchlist_item_id = Column(Integer, ForeignKey("watchlist_items.id"), index=True, nullable=False)
    tag = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    watchlist_item = relationship("WatchlistItem", back_populates="tags")
