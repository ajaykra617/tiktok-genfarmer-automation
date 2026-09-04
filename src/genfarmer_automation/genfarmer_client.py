"""Small GenFarmer Local API client based on the official API documentation.

Official docs:
https://genfarmer-support.gitbook.io/genfarmer-eng/main-menu-bar/api

Mutating methods are disabled by default. Set ``allow_mutations=True`` explicitly
only for an authorized workflow after the target IDs/payloads have been verified.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request


class GenFarmerError(RuntimeError):
    """Base error for GenFarmer client failures."""


class MutationDisabledError(GenFarmerError):
    """Raised when a mutating API call is attempted without opt-in."""


class GenFarmerHTTPError(GenFarmerError):
    """HTTP error returned by the GenFarmer Local API."""

    def __init__(self, method: str, path: str, status: int, data: Any):
        self.method = method
        self.path = path
        self.status = status
        self.data = data
        super().__init__(f"GenFarmer {method} {path} returned HTTP {status}")


@dataclass(frozen=True)
class APIResponse:
    status: int
    method: str
    path: str
    url: str
    data: Any
    content_type: str


class GenFarmerClient:
    """Client for the documented GenFarmer Local API surface."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        allow_mutations: bool = False,
    ) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an http(s) URL")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.allow_mutations = allow_mutations

    def _build_url(self, path: str, query: Mapping[str, Any] | None = None) -> str:
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        if query:
            cleaned = {
                key: value
                for key, value in query.items()
                if value is not None
            }
            if cleaned:
                url += "?" + urllib.parse.urlencode(cleaned, doseq=True)
        return url

    @staticmethod
    def _decode(raw: bytes, content_type: str) -> Any:
        text = raw.decode("utf-8", errors="replace")
        if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return text

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any = None,
    ) -> APIResponse:
        method = method.upper()
        if method != "GET" and not self.allow_mutations:
            raise MutationDisabledError(
                f"{method} {path} blocked: create the client with "
                "allow_mutations=True only for an authorized verified workflow"
            )

        url = self._build_url(path, query)
        body: bytes | None = None
        headers = {
            "Accept": "application/json,text/plain,*/*;q=0.5",
            "User-Agent": "tiktok-genfarmer-automation/0.1",
        }
        if json_body is not None:
            body = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(2_000_000)
                content_type = resp.headers.get("Content-Type", "")
                return APIResponse(
                    status=resp.status,
                    method=method,
                    path=path,
                    url=resp.geturl(),
                    data=self._decode(raw, content_type),
                    content_type=content_type,
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read(2_000_000)
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            data = self._decode(raw, content_type)
            raise GenFarmerHTTPError(method, path, exc.code, data) from exc
        except urllib.error.URLError as exc:
            raise GenFarmerError(f"GenFarmer request failed: {exc.reason}") from exc

    # ------------------------- documented read endpoints --------------------

    def get_current_user(self) -> Any:
        return self.request("GET", "/backend/auth/me").data

    def list_apps(
        self,
        *,
        user_id: str | int | None = None,
        page: int = 1,
        limit: int = 25,
        order: str = "desc",
        order_by: str = "updatedAt",
    ) -> Any:
        return self.request(
            "GET",
            "/automation/apps",
            query={
                "userId": user_id,
                "page": page,
                "limit": limit,
                "order": order,
                "orderBy": order_by,
            },
        ).data

    def get_app(self, app_id: str) -> Any:
        return self.request("GET", f"/automation/apps/{app_id}").data

    def list_runs(
        self,
        *,
        user_id: str | int | None = None,
        page: int = 1,
        limit: int = 25,
        order: str = "desc",
        order_by: str = "createdAt",
    ) -> Any:
        return self.request(
            "GET",
            "/automation/runs",
            query={
                "userId": user_id,
                "page": page,
                "limit": limit,
                "order": order,
                "orderBy": order_by,
            },
        ).data

    def get_run_storages(self, run_id: str, *, page: int = 1, limit: int = 25) -> Any:
        return self.request(
            "GET",
            f"/automation/runs/{run_id}/storages",
            query={"page": page, "limit": limit},
        ).data

    # ------------------------ documented mutation endpoints -----------------
    # These all remain fail-closed unless allow_mutations=True was explicit.

    def create_run(
        self,
        *,
        user_id: int,
        task_id: str,
        app_id: str,
        status: int = 0,
    ) -> Any:
        return self.request(
            "POST",
            "/automation/runs",
            json_body={
                "userId": user_id,
                "taskId": task_id,
                "appId": app_id,
                "status": status,
            },
        ).data

    def create_task(
        self,
        *,
        app_id: str,
        user_id: int,
        name: str,
        input_values: Sequence[Any] | None = None,
        devices: Mapping[str, Any] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "appId": app_id,
            "input": list(input_values or []),
            "userId": user_id,
            "name": name,
        }
        if devices is not None:
            payload["devices"] = dict(devices)
        return self.request("POST", "/automation/tasks", json_body=payload).data

    def update_app(
        self,
        *,
        app_id: str,
        user_id: int,
        name: str,
        version: str,
        script: Mapping[str, Any],
        description: str = "",
    ) -> Any:
        return self.request(
            "PUT",
            "/automation/apps",
            json_body={
                "id": app_id,
                "userId": user_id,
                "name": name,
                "description": description,
                "version": version,
                "script": dict(script),
            },
        ).data

    def execute_run(self, run_id: str, *, device_ids: Sequence[str] | None = None) -> Any:
        return self.request(
            "PUT",
            f"/automation/runs/{run_id}/run",
            json_body={"deviceIds": list(device_ids or [])},
        ).data

    def add_devices_to_task(
        self,
        task_id: str,
        devices: Sequence[Mapping[str, Any]],
        *,
        enabled: bool = True,
    ) -> Any:
        return self.request(
            "PUT",
            f"/automation/tasks/{task_id}/add-devices",
            json_body={"devices": {"enabled": enabled, "list": [dict(x) for x in devices]}},
        ).data

    def remove_devices_from_task(
        self,
        task_id: str,
        devices: Sequence[Mapping[str, Any]],
        *,
        enabled: bool = False,
    ) -> Any:
        return self.request(
            "PUT",
            f"/automation/tasks/{task_id}/remove-devices",
            json_body={"devices": {"enabled": enabled, "list": [dict(x) for x in devices]}},
        ).data

    def update_task(self, task_id: str, payload: Mapping[str, Any]) -> Any:
        return self.request("PUT", f"/automation/tasks/{task_id}", json_body=dict(payload)).data

    def delete_apps(self, app_ids: Sequence[str]) -> Any:
        return self.request("DELETE", "/automation/apps", json_body={"ids": list(app_ids)}).data

    def delete_tasks(self, task_ids: Sequence[str]) -> Any:
        return self.request("DELETE", "/automation/tasks", json_body={"ids": list(task_ids)}).data
