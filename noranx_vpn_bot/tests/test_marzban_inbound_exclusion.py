"""Tests for Marzban inbound exclusion (noranx CDN isolation)."""

from unittest.mock import MagicMock

from bot.services.marzban import _build_proxies_inbounds


def test_build_proxies_inbounds_excludes_nrx_tags():
    settings = MagicMock()
    settings.marzban_excluded_inbound_prefixes = "NRX-"
    inbounds_data = {
        "vless": [{"tag": "VLESS WS"}, {"tag": "NRX-VLESS-WS"}],
        "trojan": [{"tag": "Trojan WS"}, {"tag": "NRX-TROJAN-WS"}],
        "vmess": [{"tag": "VMESS WS"}, {"tag": "NRX-VMESS-WS"}],
    }
    proxies, inbounds = _build_proxies_inbounds(inbounds_data, settings)
    assert "vless" in proxies
    assert inbounds["vless"] == ["VLESS WS"]
    assert inbounds["trojan"] == ["Trojan WS"]
    assert inbounds["vmess"] == ["VMESS WS"]
    assert "NRX-VLESS-WS" not in str(inbounds)
