import hashlib
import json
import os
import sys
import tempfile
import traceback
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from types import TracebackType
from typing import Any

WEBSERVER_HOST = "localhost"
WEBSERVER_ENDPOINT = "/api/provenance/call"
PORT_FILE_SUFFIX = "-provenance-port.txt"


class ProvenanceHookError(RuntimeError):
    pass


def http_request(  # noqa: PLR0913
    method: str,
    host: str,
    port: int,
    location: str,
    *,
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> bytes:
    with closing(HTTPConnection(host, port, timeout=timeout)) as connection:
        connection.request(method, location, body=body, headers=dict(headers or {}))
        resp = connection.getresponse()
        response_body = resp.read()
        if not 200 <= resp.status < 300:
            response_text = response_body.decode("utf-8", errors="replace") or "<empty>"
            raise HTTPException(
                f"HTTP {resp.status} {resp.reason}: {response_text}"
            )
        return response_body


def get_server_port() -> int:
    claude_root = os.getenv("CLAUDE_PROJECT_DIR")
    if not claude_root:
        raise ProvenanceHookError("CLAUDE_PROJECT_DIR is not set")
    path_hash = hashlib.md5(
        claude_root.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    port_file = Path(tempfile.gettempdir()) / (path_hash + PORT_FILE_SUFFIX)

    return int(port_file.read_text("utf-8").strip())


def send_diff_to_webserver(file_path: str, timestamp_ms: int) -> bytes:
    try:
        port = get_server_port()
    except FileNotFoundError as e:
        raise ProvenanceHookError(
            f"Could not determine API port: {e.filename} does not exist") from e
    except Exception as e:
        raise ProvenanceHookError("Could not determine API port") from e

    url = f"http://{WEBSERVER_HOST}:{port}{WEBSERVER_ENDPOINT}"

    try:
        payload = {"file_path": file_path, "timestamp": timestamp_ms}
        return http_request(
            "POST",
            WEBSERVER_HOST,
            port=port,
            location=WEBSERVER_ENDPOINT,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={'Content-Type': 'application/json'},
            timeout=0.5
        )

    except (HTTPException, OSError, ConnectionError) as e:
        raise ProvenanceHookError(
            f"Network error while sending diff to {url}: {e}") from e
    except Exception as e:
        raise ProvenanceHookError(
            f"Unknown error while sending diff to {url}") from e


def _optional_tool_path(value: object) -> str | None:
    """Normalize optional tool path inputs to a truthy string or None."""
    if not isinstance(value, str):
        return None
    path = value.strip()
    return path or None


def extract_file_path(tool_name: str, tool_input: Mapping[str, Any]) -> str | None:
    if tool_name in {"Write", "Edit", "MultiEdit"}:
        return _optional_tool_path(tool_input.get("file_path"))
    if tool_name == "NotebookEdit":
        return _optional_tool_path(tool_input.get("notebook_path"))
    return None


def excepthook(
    exc_type: type[BaseException],
    value: BaseException,
    traceback_: TracebackType | None,
) -> None:
    traceback.print_exception(exc_type, value, traceback_, file=sys.stderr)
    sys.exit(1)


def main() -> int:
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "unknown")

    modification_tools = [
        "Write", "Edit", "MultiEdit", "NotebookEdit"
    ]

    if tool_name in modification_tools:
        tool_input = data.get("tool_input", {})
        file_path = extract_file_path(tool_name, tool_input)
        if file_path:
            timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)
            send_diff_to_webserver(file_path, timestamp_ms)
    return 0


if __name__ == "__main__":
    sys.excepthook = excepthook
    sys.exit(main())
