#!/usr/bin/env python3
"""Read-only smoke test for the officially documented GenFarmer Local API.

Calls only documented GET endpoints:
- /backend/auth/me
- /automation/apps
- /automation/runs

The script does not create/update/delete tasks, apps, or runs.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.genfarmer_client import (  # noqa: E402
    GenFarmerClient,
    GenFarmerError,
    GenFarmerHTTPError,
)

SENSITIVE_KEY_RE = re.compile(
    r"(?i)(email|phone|name|password|passwd|secret|token|authorization|api[_-]?key|cookie|credential)"
)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): ("<redacted>" if SENSITIVE_KEY_RE.search(str(k)) else sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def discover_user_id(data: Any) -> str | int | None:
    if not isinstance(data, dict):
        return None
    candidates = [data]
    for key in ("user", "data", "result"):
        nested = data.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    for obj in candidates:
        for key in ("id", "userId", "user_id"):
            if key in obj and isinstance(obj[key], (str, int)):
                return obj[key]
    return None


def shape(value: Any) -> str:
    if isinstance(value, dict):
        return "object keys=" + ",".join(sorted(map(str, value.keys()))[:20])
    if isinstance(value, list):
        return f"array length={len(value)}"
    return type(value).__name__


def main() -> int:
    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-api-smoke-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    client = GenFarmerClient(base_url, timeout=8.0, allow_mutations=False)
    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "safety": "official documented GET endpoints only; mutations disabled",
        "checks": [],
    }

    print("=" * 72)
    print("GENFARMER OFFICIAL API READ-ONLY SMOKE TEST")
    print("=" * 72)
    print(f"Base URL: {base_url}")
    print("Mutations: DISABLED")
    print(f"Evidence: {evidence_dir.relative_to(ROOT)}")

    user_id: str | int | None = None

    checks = [
        ("current_user", lambda: client.get_current_user()),
        ("apps", lambda: client.list_apps(user_id=user_id)),
        ("runs", lambda: client.list_runs(user_id=user_id)),
    ]

    # Run current-user first so userId can be passed to subsequent documented calls.
    try:
        current_user = client.get_current_user()
        user_id = discover_user_id(current_user)
        print(f"[OK] GET /backend/auth/me -> {shape(current_user)}")
        print(f"     discovered userId: {user_id if user_id is not None else 'not found'}")
        result["checks"].append({
            "name": "current_user",
            "ok": True,
            "shape": shape(current_user),
            "user_id": user_id,
            "data": sanitize(current_user),
        })
    except GenFarmerHTTPError as exc:
        print(f"[HTTP {exc.status}] GET /backend/auth/me")
        result["checks"].append({
            "name": "current_user",
            "ok": False,
            "status": exc.status,
            "data": sanitize(exc.data),
        })
    except GenFarmerError as exc:
        print(f"[ERROR] GET /backend/auth/me -> {exc}")
        result["checks"].append({"name": "current_user", "ok": False, "error": str(exc)})

    for name, call, endpoint in (
        ("apps", lambda: client.list_apps(user_id=user_id), "/automation/apps"),
        ("runs", lambda: client.list_runs(user_id=user_id), "/automation/runs"),
    ):
        try:
            data = call()
            print(f"[OK] GET {endpoint} -> {shape(data)}")
            result["checks"].append({
                "name": name,
                "ok": True,
                "shape": shape(data),
                "data": sanitize(data),
            })
        except GenFarmerHTTPError as exc:
            print(f"[HTTP {exc.status}] GET {endpoint}")
            result["checks"].append({
                "name": name,
                "ok": False,
                "status": exc.status,
                "data": sanitize(exc.data),
            })
        except GenFarmerError as exc:
            print(f"[ERROR] GET {endpoint} -> {exc}")
            result["checks"].append({"name": name, "ok": False, "error": str(exc)})

    out_path = evidence_dir / "result.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    success_count = sum(1 for check in result["checks"] if check.get("ok"))
    print("-" * 72)
    print(f"Successful documented GET checks: {success_count}/{len(result['checks'])}")
    print(f"Result: {out_path.relative_to(ROOT)}")
    print("No GenFarmer state was modified.")
    print("=" * 72)
    return 0 if success_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
