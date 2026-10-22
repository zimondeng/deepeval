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
