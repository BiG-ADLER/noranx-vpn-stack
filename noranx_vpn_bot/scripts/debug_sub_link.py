#!/usr/bin/env python3
"""Debug panel + subscription reachability on CF-safe ports 2053 / 8443."""
import json
import subprocess
import time
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / ".cursor" / "debug-a73a01.log"
TOKEN = "dHRnNjg2MzEzNzQxMl9rdTNzcmxpMywxNzgxMjYzNTMxfKRrUSjWB4"
ORIGIN = "82.47.63.182"
CF_DE = subprocess.check_output(["dig", "+short", "de.bigadler.xyz", "@1.1.1.1"], text=True).strip().split("\n")[0]
CF_BOT = subprocess.check_output(["dig", "+short", "bot.bigadler.xyz", "@1.1.1.1"], text=True).strip().split("\n")[0]


def _log(hypothesis_id: str, message: str, data: dict, run_id: str = "port-migration") -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(
            json.dumps(
                {
                    "sessionId": "a73a01",
                    "runId": run_id,
                    "hypothesisId": hypothesis_id,
                    "location": "scripts/debug_sub_link.py",
                    "message": message,
                    "data": data,
                    "timestamp": int(time.time() * 1000),
                }
            )
            + "\n"
        )


def _curl(url: str, accept: str = "*/*", resolve: str | None = None) -> dict:
    cmd = [
        "curl", "-sk", "-o", "/tmp/sub_body", "-w", "%{http_code}",
        "-A", "Mozilla/5.0", "-H", f"Accept: {accept}",
        "--connect-timeout", "8", "-m", "12", url,
    ]
    if resolve:
        cmd[1:1] = ["--resolve", resolve]
    r = subprocess.run(cmd, capture_output=True, text=True)
    body = Path("/tmp/sub_body").read_text(errors="replace")[:160]
    return {"url": url, "accept": accept, "resolve": resolve, "http_code": r.stdout.strip(), "body_preview": body}


if __name__ == "__main__":
    tests = {
        "panel_cf_2053": _curl(
            "https://de.bigadler.xyz:2053/dashboard/",
            "text/html",
            f"de.bigadler.xyz:2053:{CF_DE}",
        ),
        "sub_cf_2053": _curl(
            f"https://de.bigadler.xyz:2053/sub/{TOKEN}",
            "text/html",
            f"de.bigadler.xyz:2053:{CF_DE}",
        ),
        "de_443_redirect": _curl(
            "https://de.bigadler.xyz/dashboard/",
            "text/html",
            f"de.bigadler.xyz:443:{CF_DE}",
        ),
        "bot_health_cf_8443": _curl(
            "https://bot.bigadler.xyz:8443/health",
            resolve=f"bot.bigadler.xyz:8443:{CF_BOT}",
        ),
        "nowpayments_cf_8443": _curl(
            "https://bot.bigadler.xyz:8443/webhooks/nowpayments",
            resolve=f"bot.bigadler.xyz:8443:{CF_BOT}",
        ),
    }
    for hid, data in tests.items():
        _log("verify", hid, data)
    print(json.dumps(tests, indent=2))
