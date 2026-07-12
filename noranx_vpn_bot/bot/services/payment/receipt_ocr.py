import asyncio
import io
import re
from dataclasses import dataclass

from bot.utils.logging import get_logger

logger = get_logger("c2c")

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


@dataclass
class OcrHints:
    amount: int | None = None
    ref: str | None = None
    confidence: float = 0.0


def _normalize_digits(text: str) -> str:
    return text.translate(_PERSIAN_DIGITS)


def _extract_from_text(text: str) -> OcrHints:
    normalized = _normalize_digits(text)
    amount: int | None = None
    ref: str | None = None
    confidence = 0.0

    amount_patterns = [
        r"(?:مبلغ|amount)[:\s]*([\d,٬]+)\s*(?:تومان|toman)?",
        r"([\d,٬]+)\s*(?:تومان|toman)",
        r"([\d,٬]+)\s*(?:ریال|rial)",
    ]
    for pat in amount_patterns:
        m = re.search(pat, normalized, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "").replace("٬", "")
            if raw.isdigit():
                val = int(raw)
                if "ریال" in m.group(0) or "rial" in m.group(0).lower():
                    val = val // 10
                amount = val
                confidence = max(confidence, 0.5)
                break

    ref_patterns = [
        r"(?:پیگیری|شماره\s*پیگیری|ref|reference)[:\s#]*(\d{6,})",
        r"(?:کد\s*پیگیری)[:\s]*(\d{6,})",
    ]
    for pat in ref_patterns:
        m = re.search(pat, normalized, re.IGNORECASE)
        if m:
            ref = m.group(1)
            confidence = max(confidence, 0.6)
            break

    if not ref:
        long_nums = re.findall(r"\b(\d{10,})\b", normalized)
        if long_nums:
            ref = long_nums[0]
            confidence = max(confidence, 0.3)

    return OcrHints(amount=amount, ref=ref, confidence=confidence)


def _run_tesseract(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageEnhance
    except ImportError:
        return ""

    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.0)
    try:
        return pytesseract.image_to_string(img, lang="fas+eng")
    except Exception:
        try:
            return pytesseract.image_to_string(img, lang="eng")
        except Exception as e:
            logger.debug("tesseract failed: %s", e)
            return ""


async def extract_receipt_hints(image_bytes: bytes, *, enabled: bool = True) -> OcrHints:
    if not enabled:
        return OcrHints()
    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(_run_tesseract, image_bytes),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning("ocr timeout")
        return OcrHints()
    except Exception as e:
        logger.debug("ocr error: %s", e)
        return OcrHints()

    if not text.strip():
        return OcrHints()
    return _extract_from_text(text)
