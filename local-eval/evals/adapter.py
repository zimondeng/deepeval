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
) -> tuple[str, str]:
    """Return (answer, source). source is fixture or http.

    No TARGET_BASE_URL: use the answer stored on the case.
    TARGET_BASE_URL set: POST to the live system. A failed call raises.
    It does not fall back to the fixture.
    """
    base = os.environ.get("TARGET_BASE_URL", "").strip()
    if not base:
        output = case.get("actual_output")
        if not isinstance(output, str) or not output.strip():
            raise RuntimeError(
                f"case {case.get('id')!r} has no actual_output and TARGET_BASE_URL is unset"
            )
        return output, "fixture"

    path = os.environ.get("TARGET_PATH", "/chat") or "/chat"
    url = base.rstrip("/") + path
    payload = json.dumps(
        {
            "id": case.get("id"),
            "input": case.get("input"),
            "turns": case.get("turns"),
        },
        ensure_ascii=False,
    ).encode("utf-8")
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
        with request_call(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"target call failed ({url}). Inside this container, localhost is "
            f"the container. Use http://host.docker.internal:<port> for a "
            f"service on the Windows host. {exc}"
        ) from exc
    output = body.get("actual_output") if isinstance(body, dict) else None
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("target response missing actual_output")
    return output, "http"
