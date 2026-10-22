"""Run the saved console configuration inside the evaluation container."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from evals.component import run_component
from evals.credentials import CredentialEnvelope, envelope_secrets
from evals.execution import run_e2e
from ui.reports import ReportStore


def main() -> int:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("console payload must be an object")
    config = payload.get("config")
    credentials = CredentialEnvelope.from_stdin(
        __import__("io").StringIO(json.dumps(payload.get("credentials", {})))
    )
    reports = ReportStore(
        Path(os.environ.get("DEEPEVAL_RESULTS_FOLDER", "/eval/reports")),
        secrets=envelope_secrets(credentials),
    )
    run_id = os.environ.get("DEEPEVAL_RUN_ID") or None
    if config["evaluation"]["scope"] == "component":
        report = run_component(config, credentials, reports, run_id)
    else:
        report = run_e2e(config, credentials, reports, run_id)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["execution_status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
