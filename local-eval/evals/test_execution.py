import copy
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from evals.credentials import CredentialEnvelope
from evals.execution import run_e2e
from ui.reports import ReportStore


class _Handler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        self.requests.append((self.path, payload))
        if self.path == "/chat":
            body = {"actual_output": "target answer"}
        elif self.path == "/jev/v1/decisions":
            body = {
                "answers": {"q_0": {"type": "noul", "noul": 0.9}},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


@contextmanager
def fake_http():
    _Handler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def _config(tmp_path: Path, base_url: str) -> dict:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "case-1",
                "input": "hello",
                "actual_output": "fixture answer",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "schema_version": 1,
        "project": {"name": "test"},
        "jev": {"base_url": f"{base_url}/jev", "model": "fake/model"},
        "evaluation": {
            "engine": "system_one",
            "scope": "e2e",
            "threshold": 0.5,
            "questions": [
                {"id": "q1", "type": "noul", "text": "It is relevant."}
            ],
        },
        "dataset": {"path": str(dataset)},
        "target": {"url": f"{base_url}/chat"},
        "component": None,
    }


def test_run_e2e_is_serial_verified_and_freezes_snapshots(tmp_path):
    with fake_http() as base_url:
        config = _config(tmp_path, base_url)
        original = copy.deepcopy(config)
        report = run_e2e(
            config,
            CredentialEnvelope(jev_api_key="fake-key"),
            ReportStore(tmp_path / "reports", secrets=["fake-key"]),
            run_id="abc123",
        )

        config["project"]["name"] = "changed after start"
        assert report["execution_status"] == "completed"
        assert report["verification_status"] == "verified"
        assert report["quality_passed"] is True
        expected_config = {
            **original,
            "jev": {**original["jev"], "credential_ref": "session"},
        }
        assert report["config"] == expected_config
        assert (
            report["input_snapshot"]["content"][0]["actual_output"]
            == "fixture answer"
        )
        assert report["cases"]["case-1"]["output_source"] == "http"
        assert [path for path, _ in _Handler.requests] == [
            "/chat",
            "/jev/v1/decisions",
        ]


def test_target_failure_does_not_fallback_to_fixture(tmp_path):
    with fake_http() as base_url:
        config = _config(tmp_path, base_url)
        config["target"]["url"] = f"{base_url}/missing"

        report = run_e2e(
            config,
            CredentialEnvelope(jev_api_key="fake-key"),
            ReportStore(tmp_path / "reports", secrets=["fake-key"]),
            run_id="def456",
        )

        assert report["execution_status"] == "failed"
        assert report["verification_status"] == "not_verified"
        assert report["quality_passed"] is None
        assert "target" in report["cases"]["case-1"]["error"]
        assert [path for path, _ in _Handler.requests] == ["/missing"]
