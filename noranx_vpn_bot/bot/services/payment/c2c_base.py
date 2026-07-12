from dataclasses import dataclass
from typing import Protocol
import hashlib
import json

from bot.config import Settings
from bot.services.payment.c2c_utils import build_instructions, generate_payment_ref


@dataclass
class PaymentIntent:
    external_id: str
    amount_toman: int
    instructions: str
    payment_url: str | None = None
    payment_id: int | None = None


@dataclass
class VerifiedPayment:
    external_id: str
    amount_toman: int
    user_id: int
    order_id: int | None
    package_id: int | None


class C2CAdapter(Protocol):
    async def create_recharge(
        self, user_id: int, package_id: int, amount_toman: int
    ) -> PaymentIntent: ...

    async def create_order_payment(
        self, user_id: int, order_id: int, amount_toman: int
    ) -> PaymentIntent: ...

    async def verify_webhook(self, headers: dict, body: bytes) -> VerifiedPayment | None: ...


class MockC2CAdapter:
    """Simulates automated C2C — webhook can be triggered via /webhooks/c2c/mock."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._secret = settings.c2c_webhook_secret
        self._pending: dict[str, VerifiedPayment] = {}

    def _make_intent(
        self,
        external_id: str,
        amount_toman: int,
        user_id: int,
        *,
        order_id: int | None = None,
        package_id: int | None = None,
    ) -> PaymentIntent:
        self._pending[external_id] = VerifiedPayment(
            external_id=external_id,
            amount_toman=amount_toman,
            user_id=user_id,
            order_id=order_id,
            package_id=package_id,
        )
        token = hashlib.sha256(f"{external_id}:{self._secret}".encode()).hexdigest()[:16]
        instructions = build_instructions(self._settings, external_id, amount_toman)
        instructions += (
            f"\n\n🧪 حالت تست — mock webhook:\n"
            f"POST /webhooks/c2c/mock/{external_id}\n"
            f"توکن: {token}"
        )
        return PaymentIntent(
            external_id=external_id,
            amount_toman=amount_toman,
            payment_url=None,
            instructions=instructions,
        )

    async def create_recharge(
        self, user_id: int, package_id: int, amount_toman: int
    ) -> PaymentIntent:
        external_id = generate_payment_ref()
        return self._make_intent(
            external_id, amount_toman, user_id, package_id=package_id
        )

    async def create_order_payment(
        self, user_id: int, order_id: int, amount_toman: int
    ) -> PaymentIntent:
        external_id = generate_payment_ref()
        return self._make_intent(
            external_id, amount_toman, user_id, order_id=order_id
        )

    async def verify_webhook(self, headers: dict, body: bytes) -> VerifiedPayment | None:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        secret = headers.get("x-c2c-secret") or headers.get("X-C2C-Secret")
        if secret != self._secret:
            return None
        external_id = data.get("external_id")
        if not external_id or external_id not in self._pending:
            return None
        return self._pending.pop(external_id)


class ManualC2CAdapter:
    """Manual card-to-card — user transfers and uploads receipt for admin review."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def create_recharge(
        self, user_id: int, package_id: int, amount_toman: int
    ) -> PaymentIntent:
        external_id = generate_payment_ref()
        return PaymentIntent(
            external_id=external_id,
            amount_toman=amount_toman,
            payment_url=None,
            instructions=build_instructions(self._settings, external_id, amount_toman),
        )

    async def create_order_payment(
        self, user_id: int, order_id: int, amount_toman: int
    ) -> PaymentIntent:
        external_id = generate_payment_ref()
        return PaymentIntent(
            external_id=external_id,
            amount_toman=amount_toman,
            payment_url=None,
            instructions=build_instructions(self._settings, external_id, amount_toman),
        )

    async def verify_webhook(self, headers: dict, body: bytes) -> VerifiedPayment | None:
        return None


def get_c2c_adapter(settings: Settings) -> C2CAdapter:
    if settings.c2c_mock:
        return MockC2CAdapter(settings)
    return ManualC2CAdapter(settings)
