"""
Database models for user management.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text
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
    min_target_yield = Column(Integer, default=1) # minimum NET profit percentage after fees + taxes
    # Capital gains / Abgeltungssteuer rate in basis points (e.g. 26375 = 26.375%).
    # Stored as integer basis points so SQLite + PostgreSQL stay aligned
    # without introducing a Numeric column. Default 0 = no tax model applied.
    capital_gains_tax_bps = Column(Integer, default=0)
    # Optional income-tax fallback in basis points for jurisdictions/brokers
    # that tax short-term gains as ordinary income.
    income_tax_bps = Column(Integer, default=0)
    # ISO-4217 currency code the user wants money values displayed in. The
    # actual conversion happens client-side against FX rates served from
    # `/api/fx/rates`; this field only persists the preference.
    display_currency = Column(String(8), default="USD", server_default="USD", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    alert_settings = relationship("WatchlistAlertSetting", back_populates="user", cascade="all, delete-orphan")
    alert_deliveries = relationship("WatchlistAlertDelivery", back_populates="user", cascade="all, delete-orphan")
    alert_rules = relationship("AlertRule", back_populates="user", cascade="all, delete-orphan")
    alert_events = relationship("AlertEvent", back_populates="user", cascade="all, delete-orphan")
    paper_orders = relationship("PaperOrder", back_populates="user", cascade="all, delete-orphan")
    paper_transactions = relationship("PaperTransaction", back_populates="user", cascade="all, delete-orphan")


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
    alert_deliveries = relationship("WatchlistAlertDelivery", back_populates="watchlist", cascade="all, delete-orphan")
    alert_rules = relationship("AlertRule", back_populates="watchlist", cascade="all, delete-orphan")
    alert_events = relationship("AlertEvent", back_populates="watchlist", cascade="all, delete-orphan")


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


class WatchlistAlertDelivery(Base):
    __tablename__ = "watchlist_alert_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    watchlist_id = Column(String, ForeignKey("watchlists.id"), index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    channel = Column(String, index=True, nullable=False)
    alert_key = Column(String, index=True, nullable=False)
    alert_type = Column(String, nullable=False)
    priority_label = Column(String, nullable=False)
    priority_score = Column(Integer, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="alert_deliveries")
    watchlist = relationship("Watchlist", back_populates="alert_deliveries")


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


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    watchlist_id = Column(String, ForeignKey("watchlists.id"), index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False, default="")
    rule_type = Column(String, index=True, nullable=False)
    threshold_value = Column(Float, nullable=True)
    direction = Column(String, nullable=True)
    tag = Column(String, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="alert_rules")
    watchlist = relationship("Watchlist", back_populates="alert_rules")
    events = relationship("AlertEvent", back_populates="rule", cascade="all, delete-orphan")


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    alert_rule_id = Column(Integer, ForeignKey("alert_rules.id"), index=True, nullable=False)
    watchlist_id = Column(String, ForeignKey("watchlists.id"), index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    severity = Column(String, index=True, nullable=False, default="medium")
    status = Column(String, index=True, nullable=False, default="open")
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    triggered_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="alert_events")
    rule = relationship("AlertRule", back_populates="events")
    watchlist = relationship("Watchlist", back_populates="alert_events")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    # Nullable so failed-login attempts (where the user could not be
    # identified) still produce a record. The actor_fingerprint covers
    # those cases.
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    actor_fingerprint = Column(String, nullable=True)
    action = Column(String, index=True, nullable=False)
    resource_type = Column(String, index=True, nullable=True)
    resource_id = Column(String, nullable=True)
    outcome = Column(String, nullable=False, default="success")
    details_json = Column(Text, nullable=False, default="{}")
    ip_fingerprint = Column(String, nullable=True)
    user_agent_fingerprint = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)
    qty = Column(Float, nullable=False)
    limit_price = Column(Float, nullable=True)
    status = Column(String, index=True, nullable=False, default="pending")
    source = Column(String, nullable=False, default="manual")
    rejection_reason = Column(String, nullable=True)
    placed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    filled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="paper_orders")
    transactions = relationship("PaperTransaction", back_populates="order", cascade="all, delete-orphan")


class PaperTransaction(Base):
    __tablename__ = "paper_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("paper_orders.id"), index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fee_absolute = Column(Float, nullable=False, default=0.0)
    fee_percent_amount = Column(Float, nullable=False, default=0.0)
    tax_amount = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    executed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)

    user = relationship("User", back_populates="paper_transactions")
    order = relationship("PaperOrder", back_populates="transactions")


class AutoExecutionLimits(Base):
    """Per-user automation risk limits.

    The `enabled` column is the master kill-switch. Even when `enabled=True`,
    the automation pipeline only places an order after `evaluate_proposal`
    returns `allowed=True`. Every check (max-position-size, max-daily-loss,
    max-open-positions, max-portfolio-beta, allowed-asset-classes,
    halt-triggers, Net-Yield-Gate) must pass independently.
    """

    __tablename__ = "auto_execution_limits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=False)
    # `paper` (default) routes evaluated proposals into the internal
    # paper-trading book; `live` routes them through the Alpaca broker
    # service. Phase 4e ships paper-mode wired up; live-mode requires an
    # additional explicit user opt-in handled in a follow-up.
    mode = Column(String, nullable=False, default="paper")
    max_position_size_usd = Column(Float, nullable=False, default=500.0)
    max_daily_loss_usd = Column(Float, nullable=False, default=200.0)
    max_open_positions = Column(Integer, nullable=False, default=5)
    max_portfolio_beta = Column(Float, nullable=False, default=2.0)
    # Comma-separated list of asset classes (e.g. "stock,etf").
    allowed_asset_classes = Column(String, nullable=False, default="")
    # JSON map: {"trend_following": 50, "mean_reversion": 50}.
    per_strategy_budget_pct = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AutoExecutionEvent(Base):
    """Audit row for every automation evaluation + outcome."""

    __tablename__ = "auto_execution_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    proposal_id = Column(String, nullable=True)
    symbol = Column(String, nullable=True)
    side = Column(String, nullable=True)
    # proposed | accepted | rejected | executed | failed | halted
    status = Column(String, index=True, nullable=False)
    reason = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
