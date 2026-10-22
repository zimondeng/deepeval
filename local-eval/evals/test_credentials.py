import json
import subprocess
import sys
from pathlib import Path

from evals.credentials import CredentialEnvelope, redact_text


def test_credential_envelope_is_stdin_only_and_never_serializes_to_environment():
    envelope = CredentialEnvelope(
        jev_api_key="fake-jev-secret",
        target_headers={"X-Target-Token": "fake-target-secret"},
        proxy="http://proxy-user:fake-proxy-secret@proxy.test:8080",
    )

    payload = envelope.to_stdin()
    assert json.loads(payload) == {
        "jev_api_key": "fake-jev-secret",
        "target_headers": {"X-Target-Token": "fake-target-secret"},
        "proxy": "http://proxy-user:fake-proxy-secret@proxy.test:8080",
    }
    assert "fake-jev-secret" not in envelope.command_environment()
    assert envelope.command_arguments() == ()


def test_redaction_covers_jev_target_and_proxy_secrets():
    text = (
        "jev=fake-jev-secret target=fake-target-secret "
        "proxy=fake-proxy-secret"
    )

    assert (
        redact_text(
            text,
            ["fake-jev-secret", "fake-target-secret", "fake-proxy-secret"],
        )
        == "jev=[REDACTED] target=[REDACTED] proxy=[REDACTED]"
    )


def test_fake_child_receives_credentials_only_on_stdin(tmp_path: Path):
    script = tmp_path / "fake_child.py"
    script.write_text(
        "import json, os, sys\n"
        "value = json.load(sys.stdin)\n"
        "print(json.dumps({'stdin': value, 'env': dict(os.environ)}))\n",
        encoding="utf-8",
    )
    envelope = CredentialEnvelope(jev_api_key="fake-jev-secret")

    result = subprocess.run(
        [sys.executable, str(script)],
        input=envelope.to_stdin(),
        text=True,
        capture_output=True,
        check=True,
        env=envelope.command_environment(),
    )

    observed = json.loads(result.stdout)
    assert observed["stdin"]["jev_api_key"] == "fake-jev-secret"
    assert "fake-jev-secret" not in json.dumps(observed["env"])


def test_credentialed_jev_and_target_adapters_use_explicit_inputs(monkeypatch):
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from evals.adapter import actual_output
    from evals.emrank_jev import EmrankJevModel

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            json.loads(self.rfile.read(length))
            if self.path == "/jev/v1/decisions":
                body = {
                    "answers": {
                        "q_0": {"type": "noul", "noul": 0.9}
                    },
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            elif self.path == "/chat":
                body = {"actual_output": "target answer"}
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        model = EmrankJevModel(
            api_key="fake-jev",
            base_url=f"{base_url}/jev",
            model="fake/model",
        )

        class Question:
            instructions = "is valid?"

        answers, _ = model.decide(
            {"state": "x"},
            {"q_0": Question()},
        )
        assert answers.nouls["q_0"].probability == 0.9

        monkeypatch.setenv("TARGET_BASE_URL", base_url)
        output, source = actual_output(
            {"id": "1", "input": "x"},
            target_headers={"X-Target": "fake-target"},
        )
        assert (output, source) == ("target answer", "http")
    finally:
        server.shutdown()
