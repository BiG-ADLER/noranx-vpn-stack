#!/usr/bin/env python3
"""Static verification of project structure and imports for e2e readiness."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKS = [
    "bot.config",
    "bot.db.models",
    "bot.services.marzban",
    "bot.services.provisioner",
    "bot.handlers",
    "webhooks.app",
]


def main() -> int:
    errors = []
    for mod in CHECKS:
        try:
            importlib.import_module(mod)
            print(f"OK  {mod}")
        except Exception as e:
            print(f"FAIL {mod}: {e}")
            errors.append(mod)

    required = [
        "docker-compose.yml",
        ".env.example",
        "alembic/versions/001_initial.py",
        "infrastructure/README.md",
        "scripts/health_check.py",
    ]
    for rel in required:
        p = ROOT / rel
        if p.exists():
            print(f"OK  {rel}")
        else:
            print(f"MISSING {rel}")
            errors.append(rel)

    if errors:
        print(f"\n{len(errors)} check(s) failed")
        return 1
    print("\nE2E structure check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
