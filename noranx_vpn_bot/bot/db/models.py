import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base
from bot.db.types import pg_enum


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"
    LIMITED = "limited"
    PROVISIONING_FAILED = "provisioning_failed"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    PROVISIONING = "provisioning"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    WALLET = "wallet"
    NOWPAYMENTS = "nowpayments"
    C2C = "c2c"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PENDING_REVIEW = "pending_review"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class WalletTxType(str, enum.Enum):
    DEPOSIT = "deposit"
    PURCHASE = "purchase"
    REFUND = "refund"
    ADMIN_ADJUST = "admin_adjust"


class DiscountType(str, enum.Enum):
    PERCENT = "percent"
    FIXED = "fixed"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    ANSWERED = "answered"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TrafficAnomalyStatus(str, enum.Enum):
    WATCH = "watch"
    DISABLED = "disabled"
    FALSE_POSITIVE = "false_positive"
    RESOLVED = "resolved"


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_users.id"), nullable=True)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    wallet_balance_toman: Mapped[int] = mapped_column(Integer, default=0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    wallet_transactions: Mapped[list["WalletTransaction"]] = relationship(back_populates="user")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name_fa: Mapped[str] = mapped_column(String(128))
    device_count: Mapped[int] = mapped_column(Integer)
    price_toman: Mapped[int] = mapped_column(Integer)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    marzban_username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    subscription_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_limit: Mapped[int] = mapped_column(Integer, default=1)
    ip_limit: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        pg_enum(SubscriptionStatus, "subscriptionstatus"), default=SubscriptionStatus.ACTIVE
    )
    used_traffic_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    data_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["TelegramUser"] = relationship(back_populates="subscriptions")
    plan: Mapped["Plan | None"] = relationship(back_populates="subscriptions")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_toman: Mapped[int] = mapped_column(Integer)
    discount_id: Mapped[int | None] = mapped_column(ForeignKey("discount_codes.id"), nullable=True)
    total_toman: Mapped[int] = mapped_column(Integer)
    status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "orderstatus"), default=OrderStatus.PENDING
    )
    is_renewal: Mapped[bool] = mapped_column(Boolean, default=False)
    renew_subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )
    preferred_username: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["TelegramUser"] = relationship(back_populates="orders")
    plan: Mapped["Plan"] = relationship(lazy="joined")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    subscription: Mapped["Subscription | None"] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("external_id", "provider", name="uq_payment_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    recharge_package_id: Mapped[int | None] = mapped_column(
        ForeignKey("recharge_packages.id"), nullable=True
    )
    provider: Mapped[PaymentProvider] = mapped_column(pg_enum(PaymentProvider, "paymentprovider"))
    external_id: Mapped[str] = mapped_column(String(128))
    amount_toman: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "paymentstatus"), default=PaymentStatus.PENDING
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped["Order | None"] = relationship(back_populates="payments")


class C2CReceiptDedup(Base):
    __tablename__ = "c2c_receipt_dedup"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    amount_toman: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    tx_type: Mapped[WalletTxType] = mapped_column(pg_enum(WalletTxType, "wallettxtype"))
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["TelegramUser"] = relationship(back_populates="wallet_transactions")


class RechargePackage(Base):
    __tablename__ = "recharge_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount_toman: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DiscountCode(Base):
    __tablename__ = "discount_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    discount_type: Mapped[DiscountType] = mapped_column(pg_enum(DiscountType, "discounttype"))
    value: Mapped[int] = mapped_column(Integer)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)
    min_order_toman: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applicable_plan_slugs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_for_user_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_users.id"), nullable=True)


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referee_id", name="uq_referral_referee"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    referee_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reward_discount_id: Mapped[int | None] = mapped_column(ForeignKey("discount_codes.id"), nullable=True)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="درخواست پشتیبانی")
    category: Mapped[str] = mapped_column(String(64), default="other")
    status: Mapped[TicketStatus] = mapped_column(
        pg_enum(TicketStatus, "ticketstatus"), default=TicketStatus.OPEN
    )
    priority: Mapped[TicketPriority] = mapped_column(
        pg_enum(TicketPriority, "ticketpriority"), default=TicketPriority.NORMAL
    )
    assignee_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["SupportMessage"]] = relationship(back_populates="ticket")
    notes: Mapped[list["SupportTicketNote"]] = relationship(back_populates="ticket")


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    from_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")


class SupportTicketNote(Base):
    __tablename__ = "support_ticket_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["SupportTicket"] = relationship(back_populates="notes")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ProvisioningLog(Base):
    __tablename__ = "provisioning_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    step: Mapped[str] = mapped_column(String(64))
    service: Mapped[str] = mapped_column(String(32))
    request_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemState(Base):
    """Key-value store for runtime state (last webhook, etc.)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GuidePlatform(Base):
    __tablename__ = "guide_platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    title_fa: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    apps: Mapped[list["GuideApp"]] = relationship(back_populates="platform")


class GuideApp(Base):
    __tablename__ = "guide_apps"
    __table_args__ = (UniqueConstraint("platform_id", "slug", name="uq_guide_app_platform_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("guide_platforms.id"), index=True)
    slug: Mapped[str] = mapped_column(String(32))
    title_fa: Mapped[str] = mapped_column(String(128))
    download_url: Mapped[str] = mapped_column(String(512), default="")
    extra_tip: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    platform: Mapped["GuidePlatform"] = relationship(back_populates="apps")
    steps: Mapped[list["GuideStep"]] = relationship(back_populates="app", order_by="GuideStep.step_no")


class GuideStep(Base):
    __tablename__ = "guide_steps"
    __table_args__ = (UniqueConstraint("app_id", "step_no", name="uq_guide_step_app_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("guide_apps.id"), index=True)
    step_no: Mapped[int] = mapped_column(Integer)
    body_fa: Mapped[str] = mapped_column(Text)

    app: Mapped["GuideApp"] = relationship(back_populates="steps")


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrafficUsageSnapshot(Base):
    __tablename__ = "traffic_usage_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), index=True, nullable=True
    )
    marzban_username: Mapped[str] = mapped_column(String(32), index=True)
    used_traffic_bytes: Mapped[int] = mapped_column(BigInteger)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class TrafficAnomalyEvent(Base):
    __tablename__ = "traffic_anomaly_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), index=True, nullable=True
    )
    marzban_username: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[TrafficAnomalyStatus] = mapped_column(
        pg_enum(TrafficAnomalyStatus, "trafficanomalystatus"), index=True
    )
    score: Mapped[int] = mapped_column(Integer, default=0)
    delta_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    delta_minutes: Mapped[int] = mapped_column(Integer, default=0)
    rate_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    device_limit: Mapped[int] = mapped_column(Integer, default=1)
    threshold_floor_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    baseline_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
