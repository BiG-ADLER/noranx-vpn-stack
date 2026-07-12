from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list, alias="ADMIN_IDS")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")

    marzban_url: str = Field(default="https://127.0.0.1:18000", alias="MARZBAN_URL")
    marzban_user: str = Field(default="", alias="MARZBAN_USER")
    marzban_pass: str = Field(default="", alias="MARZBAN_PASS")
    marzban_dry_run: bool = Field(default=False, alias="MARZBAN_DRY_RUN")
    marzban_verify_ssl: bool = Field(default=False, alias="MARZBAN_VERIFY_SSL")
    marzban_excluded_inbound_prefixes: str = Field(
        default="NRX-", alias="MARZBAN_EXCLUDED_INBOUND_PREFIXES"
    )

    ip_limiter_url: str = Field(default="http://127.0.0.1:6284", alias="IP_LIMITER_URL")
    ip_limiter_api_user: str = Field(default="", alias="IP_LIMITER_API_USER")
    ip_limiter_api_pass: str = Field(default="", alias="IP_LIMITER_API_PASS")
    provision_skip_limiters: bool = Field(default=False, alias="PROVISION_SKIP_LIMITERS")

    marzban_webhook_secret: str = Field(default="", alias="MARZBAN_WEBHOOK_SECRET")
    required_channel_id: str = Field(default="", alias="REQUIRED_CHANNEL_ID")
    required_channel_link: str = Field(default="", alias="REQUIRED_CHANNEL_LINK")

    ops_digest_hour: int = Field(default=9, alias="OPS_DIGEST_HOUR")
    ops_digest_minute: int = Field(default=0, alias="OPS_DIGEST_MINUTE")
    ops_channel_id: int = Field(default=0, alias="OPS_CHANNEL_ID")
    announcement_channel_id: int = Field(default=0, alias="ANNOUNCEMENT_CHANNEL_ID")

    nowpayments_api_key: str = Field(default="", alias="NOWPAYMENTS_API_KEY")
    nowpayments_ipn_secret: str = Field(default="", alias="NOWPAYMENTS_IPN_SECRET")
    nowpayments_sandbox: bool = Field(default=False, alias="NOWPAYMENTS_SANDBOX")

    c2c_mock: bool = Field(default=True, alias="C2C_MOCK")
    c2c_webhook_secret: str = Field(default="change-me-c2c", alias="C2C_WEBHOOK_SECRET")
    c2c_enabled: bool = Field(default=True, alias="C2C_ENABLED")
    c2c_dest_card: str = Field(default="", alias="C2C_DEST_CARD")
    c2c_dest_name: str = Field(default="", alias="C2C_DEST_NAME")
    c2c_review_channel_id: int = Field(default=0, alias="C2C_REVIEW_CHANNEL_ID")
    c2c_ocr_enabled: bool = Field(default=True, alias="C2C_OCR_ENABLED")
    c2c_sms_enabled: bool = Field(default=False, alias="C2C_SMS_ENABLED")
    c2c_sms_bank: str = Field(default="custom", alias="C2C_SMS_BANK")
    c2c_sms_patterns: str = Field(default="[]", alias="C2C_SMS_PATTERNS")

    webhook_host: str = Field(default="0.0.0.0", alias="WEBHOOK_HOST")
    webhook_port: int = Field(default=8080, alias="WEBHOOK_PORT")
    public_webhook_base_url: str = Field(default="http://127.0.0.1:8080", alias="PUBLIC_WEBHOOK_BASE_URL")

    public_subscription_host: str = Field(default="sub.ibaxgames.ir", alias="PUBLIC_SUBSCRIPTION_HOST")
    public_subscription_scheme: str = Field(default="https", alias="PUBLIC_SUBSCRIPTION_SCHEME")
    public_subscription_port: str = Field(default="", alias="PUBLIC_SUBSCRIPTION_PORT")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=False, alias="DEBUG")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    scheduler_max_concurrency: int = Field(default=5, alias="SCHEDULER_MAX_CONCURRENCY")
    max_purchase_quantity: int = Field(default=10, alias="MAX_PURCHASE_QUANTITY")

    referral_discount_percent: int = Field(default=10, alias="REFERRAL_DISCOUNT_PERCENT")
    referral_discount_valid_days: int = Field(default=30, alias="REFERRAL_DISCOUNT_VALID_DAYS")
    referral_wallet_reward_toman: int = Field(default=10000, alias="REFERRAL_WALLET_REWARD_TOMAN")
    channel_check_cache_seconds: int = Field(default=0, alias="CHANNEL_CHECK_CACHE_SECONDS")

    trial_data_limit_bytes: int = 104857600
    trial_duration_days: int = 1
    trial_sync_interval_minutes: int = Field(default=5, alias="TRIAL_SYNC_INTERVAL_MINUTES")
    plan_duration_days: int = 30
    traffic_anomaly_enabled: bool = Field(default=True, alias="TRAFFIC_ANOMALY_ENABLED")
    traffic_anomaly_interval_minutes: int = Field(default=15, alias="TRAFFIC_ANOMALY_INTERVAL_MINUTES")
    traffic_anomaly_watch_threshold: int = Field(default=3, alias="TRAFFIC_ANOMALY_WATCH_THRESHOLD")
    traffic_anomaly_disable_threshold: int = Field(default=5, alias="TRAFFIC_ANOMALY_DISABLE_THRESHOLD")
    traffic_anomaly_baseline_multiplier: float = Field(
        default=2.5, alias="TRAFFIC_ANOMALY_BASELINE_MULTIPLIER"
    )
    traffic_anomaly_cooldown_minutes: int = Field(default=30, alias="TRAFFIC_ANOMALY_COOLDOWN_MINUTES")
    traffic_anomaly_floor_1_device_bytes: int = Field(
        default=3221225472, alias="TRAFFIC_ANOMALY_FLOOR_1_DEVICE_BYTES"
    )
    traffic_anomaly_floor_2_device_bytes: int = Field(
        default=5368709120, alias="TRAFFIC_ANOMALY_FLOOR_2_DEVICE_BYTES"
    )
    traffic_anomaly_floor_3p_device_bytes: int = Field(
        default=7516192768, alias="TRAFFIC_ANOMALY_FLOOR_3P_DEVICE_BYTES"
    )

    fx_source: str = Field(default="tgju", alias="FX_SOURCE")
    fx_usd_irr_manual: int = Field(default=1777000, alias="FX_USD_IRR_MANUAL")
    fx_cache_ttl_seconds: int = Field(default=600, alias="FX_CACHE_TTL_SECONDS")
    fx_min_usd_recharge: float = Field(default=5.0, alias="FX_MIN_USD_RECHARGE")

    @field_validator(
        "marzban_dry_run",
        "marzban_verify_ssl",
        "nowpayments_sandbox",
        "c2c_mock",
        "c2c_enabled",
        "c2c_ocr_enabled",
        "c2c_sms_enabled",
        "provision_skip_limiters",
        "traffic_anomaly_enabled",
        "debug",
        mode="before",
    )
    @classmethod
    def parse_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    @field_validator("c2c_review_channel_id", "ops_channel_id", "announcement_channel_id", mode="before")
    @classmethod
    def parse_channel_id(cls, v: object) -> int:
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v.strip())
        return 0

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, int):
            return [v]
        if isinstance(v, str) and v.strip():
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
