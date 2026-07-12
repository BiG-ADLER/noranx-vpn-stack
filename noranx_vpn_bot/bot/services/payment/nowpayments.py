import hashlib
import hmac
import json
import logging
from dataclasses import dataclass

import httpx

from bot.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class NowPaymentInvoice:
    external_id: str
    payment_id: str
    pay_url: str
    amount_toman: int
    amount_usd: float = 0.0


class NowPaymentsError(Exception):
    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class NowPaymentsService:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.nowpayments_api_key
        self._ipn_secret = settings.nowpayments_ipn_secret
        self._sandbox = settings.nowpayments_sandbox
        self._base = (
            "https://api-sandbox.nowpayments.io/v1"
            if self._sandbox
            else "https://api.nowpayments.io/v1"
        )

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def health_check(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "API key not set"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base}/status",
                    headers={"x-api-key": self._api_key},
                )
                if resp.status_code == 200:
                    mode = "sandbox" if self._sandbox else "production"
                    return True, f"OK ({mode})"
                return False, f"HTTP {resp.status_code}"
        except httpx.HTTPError as e:
            return False, str(e)

    async def create_payment_usd(
        self,
        amount_usd: float,
        order_id: str,
        description: str,
        ipn_callback_url: str,
        *,
        min_usd: float = 5.0,
    ) -> NowPaymentInvoice:
        price_usd = max(round(amount_usd, 2), min_usd)
        payload = {
            "price_amount": price_usd,
            "price_currency": "usd",
            "pay_currency": "usdttrc20",
            "order_id": order_id,
            "order_description": description,
            "ipn_callback_url": ipn_callback_url,
        }
        headers = {"x-api-key": self._api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self._base}/invoice", json=payload, headers=headers)
            if resp.status_code >= 400:
                self._raise_api_error(resp)
            data = resp.json()
            invoice_id = str(data.get("id", ""))
            pay_url = data.get("invoice_url") or ""
            if not invoice_id or not pay_url:
                raise NowPaymentsError("پاسخ نامعتبر از درگاه پرداخت.")
            return NowPaymentInvoice(
                external_id=invoice_id,
                payment_id=invoice_id,
                pay_url=pay_url,
                amount_toman=0,
                amount_usd=price_usd,
            )

    async def create_payment(
        self,
        amount_toman: int,
        order_id: str,
        description: str,
        ipn_callback_url: str,
    ) -> NowPaymentInvoice:
        """Legacy helper — prefer create_payment_usd for wallet recharge."""
        price_usd = max(round(amount_toman / 500_000, 2), 0.5)
        payload = {
            "price_amount": price_usd,
            "price_currency": "usd",
            "pay_currency": "usdttrc20",
            "order_id": order_id,
            "order_description": description,
            "ipn_callback_url": ipn_callback_url,
        }
        headers = {"x-api-key": self._api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self._base}/invoice", json=payload, headers=headers)
            if resp.status_code >= 400:
                self._raise_api_error(resp)
            data = resp.json()
            invoice_id = str(data.get("id", ""))
            pay_url = data.get("invoice_url") or ""
            if not invoice_id or not pay_url:
                raise NowPaymentsError("پاسخ نامعتبر از درگاه پرداخت.")
            return NowPaymentInvoice(
                external_id=invoice_id,
                payment_id=invoice_id,
                pay_url=pay_url,
                amount_toman=amount_toman,
            )

    def _raise_api_error(self, resp: httpx.Response) -> None:
        try:
            data = resp.json()
            code = data.get("code")
            message = data.get("message") or resp.text
        except json.JSONDecodeError:
            code = None
            message = resp.text or f"HTTP {resp.status_code}"

        logger.warning("NowPayments error %s: %s", resp.status_code, message)

        if resp.status_code == 403 and code == "INVALID_API_KEY" and self._sandbox:
            message = (
                "کلید API با حالت sandbox سازگار نیست. "
                "در .env مقدار NOWPAYMENTS_SANDBOX=false بگذارید یا کلید sandbox بسازید."
            )

        raise NowPaymentsError(message, code=code, status_code=resp.status_code)

    def verify_ipn(self, headers: dict, body: bytes) -> dict | None:
        sig = headers.get("x-nowpayments-sig") or headers.get("X-Nowpayments-Sig", "")
        if not self._ipn_secret or not sig:
            return None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return None
        sorted_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(
            self._ipn_secret.encode(),
            sorted_payload.encode(),
            hashlib.sha512,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return payload
