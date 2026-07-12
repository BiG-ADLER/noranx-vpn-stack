import re

from bot.config import get_settings

_TOKEN_RE = re.compile(r"/sub/([^/?#]+)")


def _extract_token(url: str) -> str | None:
    m = _TOKEN_RE.search(url)
    return m.group(1) if m else None


def build_canonical_subscription_url(token: str) -> str:
    settings = get_settings()
    host = settings.public_subscription_host
    scheme = settings.public_subscription_scheme
    port = (settings.public_subscription_port or "").strip()
    base = f"{scheme}://{host}"
    if port:
        base = f"{base}:{port}"
    return f"{base}/sub/{token}"


def normalize_subscription_url(url: str | None) -> str | None:
    """Canonical public subscription URL from any legacy host/port."""
    if not url:
        return None
    token = _extract_token(url)
    if token:
        return build_canonical_subscription_url(token)
    return url
