# -*- coding: utf-8 -*-
"""InvenTree API connection settings and helpers for the rack viewer."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

def _get_settings_file() -> Path:
    env_path = os.getenv("INVENTREE_SETTINGS")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidate = exe_dir / "inventree-viewer-settings.json"
        if candidate.exists():
            return candidate
        fallback = Path(r"D:\mansouri\Programs\Inventree\rack-viewer\inventree-viewer-settings.json")
        if fallback.exists():
            return fallback
        return candidate
    candidate = Path(__file__).with_name("inventree-viewer-settings.json")
    if not candidate.exists():
        fallback = Path(r"D:\mansouri\Programs\Inventree\rack-viewer\inventree-viewer-settings.json")
        if fallback.exists():
            return fallback
    return candidate

SETTINGS_FILE = _get_settings_file()

AUTH_REQUIRED_TITLE = "Authentication required"
ACCESS_DENIED_TITLE = "Access denied"
API_ERROR_TITLE = "API error"


def _needs_loopback_rewrite(host: str) -> bool:
    """True for *.localhost — Python on Windows often cannot resolve these."""
    return (host or "").lower().rstrip(".").endswith(".localhost")


def resolve_request_url(url: str) -> tuple[str, dict[str, str]]:
    """Connect via 127.0.0.1 but preserve the original Host header for reverse proxies."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not _needs_loopback_rewrite(host):
        return url, {}

    port = parsed.port
    host_header = host if port is None else f"{host}:{port}"
    netloc = f"127.0.0.1:{port}" if port is not None else "127.0.0.1"
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{netloc}"

    resolved = urlunparse(parsed._replace(netloc=netloc))
    return resolved, {"Host": host_header}


def _conn_request_url(conn: "InventreeConnection", path: str) -> tuple[str, dict[str, str]]:
    if path.startswith(("http://", "https://")):
        return resolve_request_url(path)
    base = conn.normalized_base().rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return resolve_request_url(f"{base}{path}")


class ApiPermissionError(PermissionError):
    """HTTP 401/403 — insufficient API permissions."""

    def __init__(
        self,
        status: int,
        message: str,
        *,
        path: str = "",
        action: str = "",
    ) -> None:
        super().__init__(message)
        self.status = status
        self.path = path
        self.action = action
        self.title = AUTH_REQUIRED_TITLE if status == 401 else ACCESS_DENIED_TITLE


class ApiHttpError(RuntimeError):
    """Other HTTP/API failures."""

    def __init__(self, status: int, message: str, *, path: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.path = path
        self.title = API_ERROR_TITLE


@dataclass
class InventreeConnection:
    base_url: str = "http://127.0.0.1:8080"
    username: str = "admin"
    password: str = "inventree"
    api_token: str = ""

    def normalized_base(self) -> str:
        url = (self.base_url or "").strip().rstrip("/")
        if not url:
            url = "http://127.0.0.1:8080"
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url

    def display_host(self) -> str:
        base = self.normalized_base()
        return base.replace("https://", "").replace("http://", "")

    def resolve_token(self, timeout: int = 20) -> str:
        token = (self.api_token or "").strip()
        if token:
            return token
        creds = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        url, extra_headers = _conn_request_url(self, "/api/user/token/")
        headers = {"Authorization": f"Basic {creds}", "Accept": "application/json", **extra_headers}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))["token"]
        except urllib.error.HTTPError as exc:
            body = _read_http_error_body(exc)
            _raise_for_http_status(
                exc.code,
                body,
                path="/api/user/token/",
                action="sign in to the API",
            )
            raise

    def token_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Token {token}", "Accept": "application/json"}


def _read_http_error_body(exc: urllib.error.HTTPError) -> dict | str:
    err = exc.read().decode("utf-8", errors="replace")
    try:
        return json.loads(err)
    except json.JSONDecodeError:
        return err


def _extract_detail(body: dict | str) -> str:
    if isinstance(body, str):
        return body.strip()
    if isinstance(body, dict):
        for key in ("detail", "message", "error"):
            value = body.get(key)
            if value:
                return str(value) if not isinstance(value, (dict, list)) else json.dumps(value)
        non_field = body.get("non_field_errors")
        if isinstance(non_field, list) and non_field:
            return "; ".join(str(item) for item in non_field)
        return json.dumps(body, ensure_ascii=False)
    return str(body)


def format_permission_message(
    status: int,
    body: dict | str = "",
    *,
    path: str = "",
    action: str = "",
) -> str:
    if status == 401:
        lines = [
            "Authentication failed or your API token has expired.",
            "Check username, password, or API token in Connection settings.",
        ]
    else:
        lines = [
            "Your InvenTree account does not have permission for this operation.",
            "Ask an administrator to grant the required role or permissions.",
        ]
    if action:
        lines.append(f"Required access: {action}")
    detail = _extract_detail(body)
    if detail and detail.lower() not in {"forbidden", "not authenticated", "authentication credentials were not provided."}:
        lines.append(f"Server response: {detail}")
    if path:
        lines.append(f"API: {path}")
    return "\n".join(lines)


def _raise_for_http_status(
    status: int,
    body: dict | str,
    *,
    path: str = "",
    action: str = "",
) -> None:
    if status in (401, 403):
        raise ApiPermissionError(
            status,
            format_permission_message(status, body, path=path, action=action),
            path=path,
            action=action,
        )
    if status >= 400:
        detail = _extract_detail(body) or f"HTTP {status}"
        raise ApiHttpError(status, detail, path=path)


def raise_api_response(
    status: int,
    body: dict | str,
    *,
    path: str = "",
    action: str = "",
) -> None:
    if status in (200, 201, 204):
        return
    _raise_for_http_status(status, body, path=path, action=action)


def api_error_title(exc: Exception) -> str:
    if isinstance(exc, ApiPermissionError):
        return exc.title
    if isinstance(exc, ApiHttpError):
        return exc.title
    return API_ERROR_TITLE


def part_web_url(conn: InventreeConnection, part_pk: int) -> str:
    """Open the part in the InvenTree web UI (edit from there)."""
    return f"{conn.normalized_base().rstrip('/')}/web/part/{part_pk}"


def load_settings() -> InventreeConnection:
    target = _get_settings_file()
    if not target.exists():
        return InventreeConnection()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return InventreeConnection(
            base_url=str(data.get("base_url") or InventreeConnection.base_url),
            username=str(data.get("username") or InventreeConnection.username),
            password=str(data.get("password") or InventreeConnection.password),
            api_token=str(data.get("api_token") or ""),
        )
    except (OSError, json.JSONDecodeError, TypeError):
        return InventreeConnection()


def save_settings(conn: InventreeConnection) -> None:
    target = _get_settings_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(conn), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_connection(conn: InventreeConnection) -> tuple[bool, str]:
    try:
        token = conn.resolve_token(timeout=20)
        url, extra_headers = _conn_request_url(conn, "/api/")
        headers = {**conn.token_headers(token), **extra_headers}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            json.loads(resp.read().decode("utf-8"))
        return True, f"Connected to {conn.display_host()}"
    except ApiPermissionError as exc:
        return False, str(exc)
    except urllib.error.HTTPError as exc:
        body = _read_http_error_body(exc)
        if exc.code in (401, 403):
            return False, format_permission_message(exc.code, body, path="/api/", action="access the API")
        return False, f"HTTP {exc.code}: {_extract_detail(body) or exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Could not reach server: {exc.reason}"
    except Exception as exc:
        return False, str(exc)


def ref_pk(value) -> int | None:
    """Extract primary key from an API reference (int or nested object)."""
    if value is None:
        return None
    if isinstance(value, dict):
        pk = value.get("pk")
        return int(pk) if pk is not None else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def api_get(
    conn: InventreeConnection,
    path: str,
    token: str,
    timeout: int = 60,
    *,
    action: str = "read data",
) -> dict:
    url, extra_headers = _conn_request_url(conn, path)
    headers = {**conn.token_headers(token), **extra_headers}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = _read_http_error_body(exc)
        _raise_for_http_status(exc.code, body, path=path, action=action)


DIMENSION_PARAM_NAMES = ("Length", "Width", "Height")
LOCATION_DIMENSION_PARAM_NAMES = ("Bin Length", "Bin Width", "Bin Height")
LOCATION_MODEL_TYPE = "stock.stocklocation"

_LOCATION_DIM_KEYS = {
    "Bin Length": "length",
    "Bin Width": "width",
    "Bin Height": "height",
}


def parse_dimension_mm(text: str) -> float | None:
    """Parse a dimension field value such as ``150`` or ``150 mm``."""
    cleaned = str(text or "").strip().lower().replace("mm", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def format_dimension_mm(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return f"{int(round(value))} mm"
    return f"{value:.1f} mm"


def fetch_part_dimension_records(
    conn: InventreeConnection,
    part_pk: int,
    token: str,
    timeout: int = 60,
) -> dict[str, dict]:
    """Return Length/Width/Height parameter records for a part."""
    data = api_get(
        conn,
        f"/api/parameter/?model_type=part.part&model_id={part_pk}",
        token,
        timeout=timeout,
        action="view part parameters",
    )
    items = data.get("results", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}

    out: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        tpl = item.get("template_detail") or {}
        name = tpl.get("name") if isinstance(tpl, dict) else ""
        if name not in DIMENSION_PARAM_NAMES:
            continue
        key = name.lower()
        out[key] = {
            "pk": item.get("pk"),
            "template_pk": ref_pk(tpl) or ref_pk(item.get("template")),
            "data": str(item.get("data") or "").strip(),
        }
    return out


def fetch_part_dimensions(
    conn: InventreeConnection,
    part_pk: int,
    token: str,
    timeout: int = 60,
) -> dict[str, str]:
    """Return Length/Width/Height parameter values for a part (e.g. ``10 mm``)."""
    records = fetch_part_dimension_records(conn, part_pk, token, timeout=timeout)
    return {key: rec["data"] for key, rec in records.items() if rec.get("data")}


def _fetch_dimension_records(
    conn: InventreeConnection,
    model_type: str,
    model_id: int,
    param_names: tuple[str, ...],
    token: str,
    timeout: int = 60,
    *,
    action: str,
) -> dict[str, dict]:
    data = api_get(
        conn,
        f"/api/parameter/?model_type={model_type}&model_id={model_id}",
        token,
        timeout=timeout,
        action=action,
    )
    items = data.get("results", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}

    out: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        tpl = item.get("template_detail") or {}
        name = tpl.get("name") if isinstance(tpl, dict) else ""
        if name not in param_names:
            continue
        key = name.lower().replace("bin ", "")
        out[key] = {
            "pk": item.get("pk"),
            "template_pk": ref_pk(tpl) or ref_pk(item.get("template")),
            "data": str(item.get("data") or "").strip(),
        }
    return out


def fetch_location_dimension_records(
    conn: InventreeConnection,
    location_pk: int,
    token: str,
    timeout: int = 60,
) -> dict[str, dict]:
    """Return Bin Length/Width/Height parameter records for a stock location."""
    return _fetch_dimension_records(
        conn,
        LOCATION_MODEL_TYPE,
        location_pk,
        LOCATION_DIMENSION_PARAM_NAMES,
        token,
        timeout=timeout,
        action="view location parameters",
    )


def fetch_location_dimensions(
    conn: InventreeConnection,
    location_pk: int,
    token: str,
    timeout: int = 60,
) -> dict[str, str]:
    """Return Bin Length/Width/Height values for a stock location."""
    records = fetch_location_dimension_records(conn, location_pk, token, timeout=timeout)
    return {key: rec["data"] for key, rec in records.items() if rec.get("data")}


def build_location_dimensions_index(
    conn: InventreeConnection,
    token: str,
    timeout: int = 120,
) -> dict[int, tuple[float, float, float]]:
    """Map stock-location PK -> (length, width, height) in mm from bin parameters."""
    params = fetch_all(
        conn,
        "/api/parameter/?limit=250",
        token,
        timeout=timeout,
        action="view location parameters",
    )
    by_location: dict[int, dict[str, float]] = {}
    for item in params:
        if item.get("model_type") != LOCATION_MODEL_TYPE:
            continue
        loc_pk = item.get("model_id")
        if loc_pk is None:
            continue
        tpl = item.get("template_detail") or {}
        name = tpl.get("name") if isinstance(tpl, dict) else ""
        key = _LOCATION_DIM_KEYS.get(name or "")
        if not key:
            continue
        value = parse_dimension_mm(str(item.get("data") or ""))
        if value is not None:
            by_location.setdefault(int(loc_pk), {})[key] = value

    out: dict[int, tuple[float, float, float]] = {}
    for loc_pk, dims in by_location.items():
        if all(axis in dims for axis in ("length", "width", "height")):
            out[loc_pk] = (dims["length"], dims["width"], dims["height"])
    return out


def _dimension_template_pks(
    conn: InventreeConnection,
    token: str,
) -> dict[str, int]:
    templates = fetch_all(
        conn,
        "/api/parameter/template/?limit=250",
        token,
        action="view parameter templates",
    )
    return {
        str(row.get("name") or ""): int(row["pk"])
        for row in templates
        if row.get("name") in DIMENSION_PARAM_NAMES and row.get("pk") is not None
    }


def _location_dimension_template_pks(
    conn: InventreeConnection,
    token: str,
) -> dict[str, int]:
    templates = fetch_all(
        conn,
        "/api/parameter/template/?limit=250",
        token,
        action="view parameter templates",
    )
    return {
        str(row.get("name") or ""): int(row["pk"])
        for row in templates
        if row.get("name") in LOCATION_DIMENSION_PARAM_NAMES and row.get("pk") is not None
    }


def save_part_dimensions(
    conn: InventreeConnection,
    token: str,
    part_pk: int,
    *,
    length: str,
    width: str,
    height: str,
    records: dict[str, dict] | None = None,
) -> None:
    """Create or update Length/Width/Height parameters for a part."""
    existing = records if records is not None else fetch_part_dimension_records(conn, part_pk, token)
    templates = _dimension_template_pks(conn, token)

    for dim_key, raw in (("length", length), ("width", width), ("height", height)):
        parsed = parse_dimension_mm(raw)
        if parsed is None:
            continue

        data_str = format_dimension_mm(parsed)
        record = existing.get(dim_key) or {}
        param_pk = record.get("pk")
        if param_pk:
            api_patch(
                conn,
                f"/api/parameter/{param_pk}/",
                token,
                {"data": data_str},
                action="change part parameters",
            )
            continue

        template_name = dim_key.capitalize()
        template_pk = record.get("template_pk") or templates.get(template_name)
        if template_pk is None:
            raise ApiHttpError(
                400,
                f'Parameter template "{template_name}" was not found on the server.',
                path="/api/parameter/template/",
            )

        api_post(
            conn,
            "/api/parameter/",
            token,
            {
                "template": int(template_pk),
                "model_type": "part.part",
                "model_id": part_pk,
                "data": data_str,
            },
            action="change part parameters",
        )


def save_location_bin_dimensions(
    conn: InventreeConnection,
    token: str,
    location_pk: int,
    *,
    length: str,
    width: str,
    height: str,
    records: dict[str, dict] | None = None,
) -> None:
    """Create or update Bin Length/Width/Height parameters for a stock location."""
    existing = (
        records
        if records is not None
        else fetch_location_dimension_records(conn, location_pk, token)
    )
    templates = _location_dimension_template_pks(conn, token)
    label_for_key = {"length": "Bin Length", "width": "Bin Width", "height": "Bin Height"}

    for dim_key, raw in (("length", length), ("width", width), ("height", height)):
        parsed = parse_dimension_mm(raw)
        if parsed is None:
            continue

        data_str = format_dimension_mm(parsed)
        record = existing.get(dim_key) or {}
        param_pk = record.get("pk")
        if param_pk:
            api_patch(
                conn,
                f"/api/parameter/{param_pk}/",
                token,
                {"data": data_str},
                action="change location parameters",
            )
            continue

        template_name = label_for_key[dim_key]
        template_pk = record.get("template_pk") or templates.get(template_name)
        if template_pk is None:
            raise ApiHttpError(
                400,
                f'Parameter template "{template_name}" was not found on the server.',
                path="/api/parameter/template/",
            )

        api_post(
            conn,
            "/api/parameter/",
            token,
            {
                "template": int(template_pk),
                "model_type": LOCATION_MODEL_TYPE,
                "model_id": location_pk,
                "data": data_str,
            },
            action="change location parameters",
        )


def api_delete(
    conn: InventreeConnection,
    path: str,
    token: str,
    timeout: int = 120,
    *,
    action: str = "delete data",
) -> None:
    status, resp = api_request(conn, "DELETE", path, token, timeout=timeout)
    raise_api_response(status, resp, path=path, action=action)


def fetch_all(
    conn: InventreeConnection,
    path: str,
    token: str,
    timeout: int = 120,
    *,
    action: str = "read data",
) -> list[dict]:
    items: list[dict] = []
    url: str | None = _conn_request_url(conn, path)[0]
    while url:
        request_url, extra_headers = resolve_request_url(url)
        headers = {**conn.token_headers(token), **extra_headers}
        req = urllib.request.Request(request_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = _read_http_error_body(exc)
            _raise_for_http_status(exc.code, body, path=path, action=action)
        items.extend(data.get("results", data if isinstance(data, list) else []))
        url = data.get("next") if isinstance(data, dict) else None
    return items


def api_request(
    conn: InventreeConnection,
    method: str,
    path: str,
    token: str,
    data: dict | None = None,
    timeout: int = 120,
) -> tuple[int, dict | str]:
    headers = conn.token_headers(token)
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    url, extra_headers = _conn_request_url(conn, path)
    headers.update(extra_headers)
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err_body = _read_http_error_body(exc)
        return exc.code, err_body


def api_patch(
    conn: InventreeConnection,
    path: str,
    token: str,
    data: dict,
    timeout: int = 120,
    *,
    action: str = "update data",
) -> dict:
    status, resp = api_request(conn, "PATCH", path, token, data, timeout=timeout)
    raise_api_response(status, resp, path=path, action=action)
    return resp if isinstance(resp, dict) else {}


def api_post(
    conn: InventreeConnection,
    path: str,
    token: str,
    data: dict,
    timeout: int = 120,
    *,
    action: str = "create data",
) -> dict:
    status, resp = api_request(conn, "POST", path, token, data, timeout=timeout)
    raise_api_response(status, resp, path=path, action=action)
    return resp if isinstance(resp, dict) else {}
