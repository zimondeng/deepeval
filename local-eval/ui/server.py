"""Loopback-only standard-library API and native console for local evaluation."""

from __future__ import annotations

import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from evals.config import ConfigValidationError, export_config, validate_config
from evals.credentials import CredentialEnvelope
from evals.emrank_jev import EmrankJevModel

from .lifecycle import (
    ActiveTaskError,
    SubprocessRunner,
    TaskManager,
    UnknownTaskError,
)
from .reports import ReportStore


class ConsoleApp:
    """Stateful service shared by the API handler and the native page."""

    def __init__(
        self,
        repo_root: Path,
        manager: TaskManager | None = None,
        reports: ReportStore | None = None,
        compose_file: str = "local-eval/compose.yaml",
    ):
        self.repo_root = Path(repo_root).resolve()
        self.reports = reports or ReportStore(
            self.repo_root / "local-eval/reports"
        )
        self.manager = manager or TaskManager(
            SubprocessRunner(self.repo_root, self.reports._folder),
            compose_file,
            os.environ.get("DEEPEVAL_EVAL_SERVICE", "eval"),
        )
        self.config: dict[str, Any] | None = None
        self.credentials = CredentialEnvelope()
        self.logs: dict[str, list[str]] = {}
        self.session_token = secrets.token_urlsafe(24)

    def save_config(self, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ConfigValidationError({"config": "must be an object"})
        value = dict(value)
        credentials = value.pop("credentials", {})
        if not isinstance(credentials, dict):
            raise ConfigValidationError({"credentials": "must be an object"})
        jev = value.get("jev")
        if not isinstance(jev, dict):
            jev = {}
            value["jev"] = jev
        key = credentials.get("jev_api_key") or jev.pop("api_key", None)
        self.credentials = CredentialEnvelope(
            jev_api_key=key,
            target_headers=credentials.get("target_headers", {}),
            proxy=credentials.get("proxy"),
        )
        self.config = validate_config(value, allowed_root=self.repo_root)
        return export_config(self.config)

    def validate(self, value: Any) -> dict[str, Any]:
        config = dict(value) if isinstance(value, dict) else value
        return export_config(
            validate_config(config, allowed_root=self.repo_root)
        )


class Handler(BaseHTTPRequestHandler):
    """HTTP boundary; only fixed routes and static files are exposed."""

    app: ConsoleApp

    def do_GET(self):
        if not self._safe_request():
            return
        if self.path == "/health":
            return self._json(
                200,
                {
                    "status": "ok",
                    "runner": "docker-compose",
                    "session_token": self.app.session_token,
                },
            )
        if self.path == "/api/config":
            return self._json(
                200, export_config(self.app.config) if self.app.config else None
            )
        if self.path.startswith("/api/runs/"):
            return self._run_get()
        if self.path == "/api/runs":
            return self._json(200, {"active": self.app.manager._active})
        if self.path == "/":
            return self._static("index.html", "text/html; charset=utf-8")
        if self.path == "/style.css":
            return self._static("style.css", "text/css; charset=utf-8")
        if self.path == "/app.js":
            return self._static("app.js", "text/javascript; charset=utf-8")
        self.send_error(404)

    def do_POST(self):
        if not self._safe_request():
            return
        try:
            payload = self._body()
            if self.path == "/api/config/validate":
                return self._json(
                    200, {"valid": True, "config": self.app.validate(payload)}
                )
            if self.path == "/api/jev/test":
                return self._jev_test()
            if self.path == "/api/runs":
                return self._start_run(payload)
            self.send_error(404)
        except ConfigValidationError as exc:
            self._json(422, {"valid": False, "errors": exc.errors})
        except ActiveTaskError as exc:
            self._json(409, {"error": str(exc)})
        except (ValueError, KeyError) as exc:
            self._json(400, {"error": str(exc)})

    def do_PUT(self):
        if not self._safe_request():
            return
        if self.path != "/api/config":
            self.send_error(404)
            return
        try:
            result = self.app.save_config(self._body())
            self._json(200, result)
        except ConfigValidationError as exc:
            self._json(422, {"valid": False, "errors": exc.errors})
        except (ValueError, KeyError) as exc:
            self._json(400, {"error": str(exc)})

    def do_DELETE(self):
        if not self._safe_request():
            return
        if self.path.startswith("/api/runs/"):
            run_id = self.path.rsplit("/", 1)[-1]
            try:
                task = self.app.manager.cancel(run_id)
                return self._json(
                    200, {"run_id": task.run_id, "status": task.status}
                )
            except UnknownTaskError:
                self._json(404, {"error": "unknown run"})
                return
        self.send_error(404)

    def _jev_test(self):
        if not self.app.credentials.jev_api_key:
            return self._json(
                200,
                {
                    "status": "not_verified",
                    "message": "Enter a Jev key for a live test.",
                },
            )
        jev = self.app.config["jev"] if self.app.config else {}
        model = EmrankJevModel(
            api_key=self.app.credentials.jev_api_key,
            base_url=jev.get("base_url"),
            model=jev.get("model"),
            timeout=jev.get("timeout") or 60,
            retry=jev.get("retry", 2),
        )
        try:
            model.decide(
                {"input": "health check", "actual_output": "health check"},
                {
                    "health_check": SimpleNamespace(
                        instructions="The answer is usable.",
                        true="yes",
                        false="no",
                    )
                },
            )
        except Exception as exc:
            return self._json(
                502,
                {
                    "status": "error",
                    "message": f"Jev test failed: {type(exc).__name__}",
                },
            )
        return self._json(
            200,
            {"status": "verified", "attempts": model.last_attempts},
        )

    def _start_run(self, payload: Any):
        if self.app.config is None:
            return self._json(
                409, {"error": "save a valid configuration first"}
            )
        if payload:
            self.app.save_config(payload)
        envelope = json.dumps(
            {
                "config": self.app.config,
                "credentials": json.loads(self.app.credentials.to_stdin()),
            },
            ensure_ascii=False,
        )
        run = self.app.manager.start(envelope)
        self.app.logs[run.run_id] = ["run queued", "docker evaluation started"]
        return self._json(202, {"run_id": run.run_id, "status": run.status})

    def _run_get(self):
        run_id, suffix = (
            self.path[len("/api/runs/") :].split("/", 1)
            if "/" in self.path[len("/api/runs/") :]
            else (self.path.rsplit("/", 1)[-1], "")
        )
        if suffix == "logs":
            return self._json(
                200, {"run_id": run_id, "events": self.app.logs.get(run_id, [])}
            )
        if suffix == "report":
            try:
                report = self.app.reports.read(run_id)
            except FileNotFoundError:
                return self._json(404, {"error": "report unavailable"})
            if report["execution_status"] in {
                "completed",
                "failed",
                "cancelled",
            }:
                try:
                    self.app.manager.finish(
                        run_id,
                        0 if report["execution_status"] == "completed" else 1,
                    )
                except (KeyError, UnknownTaskError):
                    pass
            return self._json(200, report)
        try:
            task = self.app.manager._tasks[run_id]
        except KeyError:
            return self._json(404, {"error": "unknown run"})
        return self._json(200, {"run_id": task.run_id, "status": task.status})

    def _safe_request(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0]
        origin = self.headers.get("Origin")
        origin_host = urlparse(origin).hostname if origin else host
        if host not in {"127.0.0.1", "localhost", "::1"} or origin_host not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            self._json(403, {"error": "loopback host required"})
            return False
        if (
            self.command in {"POST", "PUT", "DELETE"}
            and self.headers.get("X-Session-Token") != self.app.session_token
        ):
            self._json(403, {"error": "session token required"})
            return False
        return True

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 10 * 1024 * 1024:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _json(self, status: int, value: Any):
        body = (
            json.dumps(value, ensure_ascii=False)
            .encode("utf-8", errors="backslashreplace")
            + b'\n'
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, name: str, content_type: str):
        root = Path(__file__).with_name("static")
        path = root / name
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def create_server(app: ConsoleApp, host: str = "127.0.0.1", port: int = 8787):
    class BoundHandler(Handler):
        pass

    BoundHandler.app = app
    return ThreadingHTTPServer((host, port), BoundHandler)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    reports = Path(
        os.environ.get(
            "DEEPEVAL_RESULTS_FOLDER", str(repo_root / "local-eval/reports")
        )
    )
    app = ConsoleApp(
        repo_root,
        reports=ReportStore(reports),
        compose_file=os.environ.get(
            "DEEPEVAL_COMPOSE_FILE", "local-eval/compose.yaml"
        ),
    )
    app.manager.cleanup_stale()
    create_server(
        app,
        os.environ.get("DEEPEVAL_CONSOLE_HOST", "127.0.0.1"),
        int(os.environ.get("DEEPEVAL_CONSOLE_PORT", "8787")),
    ).serve_forever()


if __name__ == "__main__":
    main()
