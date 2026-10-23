"""Load a golden file and optionally call the system under test.

shortcut: one JSONL file and one POST {id, input, turns} -> {actual_output}.
Upgrade when a second target shape shows up.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def actual_output(
    case: dict,
    target_headers: dict[str, str] | None = None,
    proxy: str | None = None,
    target_url: str | None = None,
    target_path: str | None = None,
    timeout: float = 60,
    body_template: str | None = None,
    input_path: str | None = None,
    turns_path: str | None = None,
    output_path: str | None = None,
) -> tuple[str, str]:
    """Return (answer, source). source is fixture or http.

    No TARGET_BASE_URL: use the answer stored on the case.
    TARGET_BASE_URL set: POST to the live system. A failed call raises.
    It does not fall back to the fixture.
    """
    base = (target_url or os.environ.get("TARGET_BASE_URL", "")).strip()
    if not base:
        output = case.get("actual_output")
        if not isinstance(output, str) or not output.strip():
            raise RuntimeError(
                f"case {case.get('id')!r} has no actual_output and TARGET_BASE_URL is unset"
            )
        return output, "fixture"

    path = (
        target_path
        if target_path is not None
        else os.environ.get("TARGET_PATH", "/chat") or "/chat"
    )
    url = base.rstrip("/") + path if path else base
    values = {
        "id": case.get("id"),
        "input": _path_value(case, input_path, "input"),
        "turns": _path_value(case, turns_path, "turns"),
    }
    if body_template:
        body = body_template
        for key, value in values.items():
            quoted = json.dumps("{{" + key + "}}")
            replacement = json.dumps(value, ensure_ascii=False)
            body = body.replace(quoted, replacement).replace(
                "{{" + key + "}}", replacement
            )
        try:
            request_body = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "target body_template is not valid JSON"
            ) from exc
    else:
        request_body = values
    payload = json.dumps(request_body, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", **(target_headers or {})},
        method="POST",
    )
    try:
        opener = (
            urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )
            if proxy
            else None
        )
        request_call = opener.open if opener else urllib.request.urlopen
        with request_call(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"target call failed ({url}). Inside this container, localhost is "
            f"the container. Use http://host.docker.internal:<port> for a "
            f"service on the Windows host. {exc}"
        ) from exc
    output = body
    if output_path:
        for part in output_path.split("."):
            if not isinstance(output, dict) or part not in output:
                raise RuntimeError("target response missing output path")
            output = output[part]
    elif isinstance(body, dict):
        output = body.get("actual_output")
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("target response missing actual_output")
    return output, "http"


def _path_value(case: dict, path: str | None, default: str):
    if not path:
        return case.get(default)
    value = case
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise RuntimeError(f"case missing configured path: {path}")
        value = value[part]
    return value
