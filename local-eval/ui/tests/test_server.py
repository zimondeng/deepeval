import json
from http.client import HTTPConnection
from pathlib import Path
import threading

import pytest

from ui.lifecycle import Task
from ui.server import ConsoleApp, create_server
from ui.reports import ReportStore


VALID_CONFIG = {
    "schema_version": 1,
    "project": {"name": "demo"},
    "jev": {
        "base_url": "https://emrank.tech",
        "model": "typesafe/jev-1.14.0",
        "api_key": "session-secret",
    },
    "evaluation": {
        "engine": "system_one",
        "scope": "e2e",
        "questions": [{"id": "q1", "type": "noul", "text": "Useful?"}],
    },
    "dataset": {"path": "cases.jsonl"},
    "target": {"url": "https://example.test/chat"},
    "component": None,
}


class FakeManager:
    def __init__(self):
        self._active = None
        self._tasks = {}

    def start(self, stdin_payload=None):
        task = Task("0123456789ab", "deepeval-task-0123456789ab", "running")
        self._tasks[task.run_id] = task
        self._active = task.run_id
        return task

    def cancel(self, run_id):
        task = self._tasks[run_id]
        task.status = "cancelled"
        self._active = None
        return task


def request(server, method, path, body=None, headers=None):
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        connection = HTTPConnection(*server.server_address)
        headers = {"Host": "127.0.0.1", **(headers or {})}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        return (
            response.status,
            response.getheader("Content-Type"),
            response.read(),
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_config_round_trip_never_returns_session_secret(tmp_path: Path):
    config = {
        **VALID_CONFIG,
        "dataset": {"path": str(tmp_path / "cases.jsonl")},
    }
    app = ConsoleApp(repo_root=tmp_path)
    server = create_server(app, "127.0.0.1", 0)
    status, content_type, body = request(server, "PUT", "/api/config", config)

    assert status == 200
    assert content_type.startswith("application/json")
    assert "session-secret" not in body.decode()

    server = create_server(app, "127.0.0.1", 0)
    status, _, body = request(server, "GET", "/api/config")
    assert status == 200
    assert "api_key" not in body.decode()
    assert json.loads(body)["jev"]["credential_ref"] == "session"


def test_validate_reports_field_errors_without_contacting_services(
    tmp_path: Path,
):
    app = ConsoleApp(repo_root=tmp_path)
    server = create_server(app, "127.0.0.1", 0)
    invalid = {**VALID_CONFIG, "evaluation": {"engine": "hybrid"}}

    status, _, body = request(server, "POST", "/api/config/validate", invalid)

    assert status == 422
    assert "evaluation.engine" in json.loads(body)["errors"]


def test_run_status_cancel_logs_and_report_routes(tmp_path: Path):
    manager = FakeManager()
    reports = ReportStore(tmp_path / "reports")
    app = ConsoleApp(tmp_path, manager=manager, reports=reports)
    config = {
        **VALID_CONFIG,
        "dataset": {"path": str(tmp_path / "cases.jsonl")},
    }
    assert (
        request(create_server(app, port=0), "PUT", "/api/config", config)[0]
        == 200
    )

    status, _, body = request(create_server(app, port=0), "POST", "/api/runs")
    run_id = json.loads(body)["run_id"]
    assert status == 202
    assert (
        json.loads(
            request(create_server(app, port=0), "GET", f"/api/runs/{run_id}")[2]
        )["status"]
        == "running"
    )
    assert json.loads(
        request(create_server(app, port=0), "GET", f"/api/runs/{run_id}/logs")[
            2
        ]
    )["events"]
    assert (
        request(create_server(app, port=0), "DELETE", f"/api/runs/{run_id}")[0]
        == 200
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.test"},
        {"Origin": "http://evil.test"},
    ],
)
def test_console_rejects_foreign_host_and_origin_without_mutating_config(
    tmp_path: Path, headers: dict[str, str]
):
    app = ConsoleApp(repo_root=tmp_path)
    server = create_server(app, "127.0.0.1", 0)

    status, _, _ = request(
        server,
        "PUT",
        "/api/config",
        VALID_CONFIG,
        headers=headers,
    )
    assert status == 403

    status, _, body = request(
        create_server(app, "127.0.0.1", 0), "GET", "/api/config"
    )
    assert status == 200
    assert json.loads(body) is None


def test_console_accepts_a_loopback_request_without_cross_origin_header(
    tmp_path: Path,
):
    server = create_server(ConsoleApp(repo_root=tmp_path), "127.0.0.1", 0)

    status, _, body = request(server, "GET", "/health")

    assert status == 200
    assert json.loads(body)["status"] == "ok"


def test_console_serves_accessible_native_sections(tmp_path: Path):
    server = create_server(ConsoleApp(repo_root=tmp_path), "127.0.0.1", 0)

    status, content_type, body = request(server, "GET", "/")

    page = body.decode()
    assert status == 200
    assert content_type.startswith("text/html")
    for section in (
        "model",
        "scope",
        "dataset",
        "questions",
        "target",
        "component",
    ):
        assert f'id="{section}"' in page
    assert 'aria-live="polite"' in page
    assert 'id="config-preview"' in page
