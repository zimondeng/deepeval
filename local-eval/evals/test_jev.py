"""One real Jev call. A missing key or a failed call is not a pass."""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from deepeval.config.settings import get_settings
from deepeval.metrics import JevEval
from deepeval.metrics.jev_eval import Noul
from deepeval.test_case import LLMTestCase, SingleTurnParams

from evals.adapter import actual_output, load_jsonl
from evals.credentials import (
    CredentialEnvelope,
    envelope_secrets,
    redact_text,
)
from evals.emrank_jev import EmrankJevModel

CASE_ID = "property-certificate-001"
_REPORT_SECRETS: list[str] = []
DATASET = Path(
    os.environ.get("DATASET_PATH", "/eval/datasets/property_certificate.jsonl")
)


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    envelope = _read_credentials()
    secrets = envelope_secrets(envelope)
    _REPORT_SECRETS[:] = secrets
    settings = get_settings()
    mode = settings.DEEPEVAL_EVAL_MODE
    key = envelope.jev_api_key or (
        os.environ.get("JEV_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    key_set = bool(key)
    report = {
        "status": "not_verified",
        "checked_at": started,
        "case_id": CASE_ID,
        "metric": None,
        "score": None,
        "success": None,
        "confidence": None,
        "reason": None,
        "duration_seconds": None,
        "model": os.environ.get("JEV_MODEL", "typesafe/jev-1.14.0"),
        "usage": None,
        "eval_mode": mode,
        "output_source": None,
        "component_eval": "not_run",
        "error": None,
        "score_breakdown": None,
    }

    if mode != "system_one":
        report["status"] = "error"
        report["error"] = (
            f"DEEPEVAL_EVAL_MODE is {mode!r}, expected 'system_one'. "
            "hybrid is a different mode and is not used here."
        )
        return _finish(report, 1)
    if not key_set:
        report["error"] = (
            "JEV_API_KEY is not set. Jev was not called. Not a pass."
        )
        return _finish(report, 2)

    try:
        case = _case()
        if case.get("trace") or case.get("spans"):
            report["component_eval"] = (
                "skipped: this sample only scores the end-to-end answer. "
                "A component eval is JevEval with no evaluation_params on a traced test case."
            )
        output, source = actual_output(
            case,
            target_headers=dict(envelope.target_headers),
            proxy=envelope.proxy,
        )
        report["output_source"] = source
        jev_model = EmrankJevModel(
            api_key=envelope.jev_api_key,
            proxy=envelope.proxy,
        )
        metric = JevEval(
            name="gov-service-answer",
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            system_one_model=jev_model,
            threshold=0.5,
            async_mode=False,
            verbose_mode=False,
            questions=[
                Noul(
                    "actual_output 回应用户关于办理不动产权证所需材料的问题，而不是答非所问。"
                ),
                Noul("actual_output 没有编造一份具体的材料清单。"),
                Noul(
                    "actual_output 说明所需材料取决于登记业务类型，并指出需要对照办事指南确认。"
                ),
            ],
        )
        test_case = LLMTestCase(input=case["input"], actual_output=output)
        t0 = time.perf_counter()
        metric.measure(test_case, _show_indicator=False)
        report["duration_seconds"] = round(time.perf_counter() - t0, 3)
        report["metric"] = metric.__name__
        report["score"] = metric.score
        report["success"] = metric.success
        report["confidence"] = metric.confidence
        report["reason"] = metric.reason
        report["model"] = metric.evaluation_model
        report["usage"] = jev_model.last_usage
        report["score_breakdown"] = metric.score_breakdown
        if metric.score is None:
            report["status"] = "error"
            report["error"] = "Jev returned no score."
            return _finish(report, 1)
        report["status"] = "verified"
        return _finish(report, 0)
    except Exception as exc:
        report["status"] = "error"
        report["error"] = _redact(f"{type(exc).__name__}: {exc}")
        report["traceback"] = _redact(traceback.format_exc())
        return _finish(report, 1)


def _read_credentials() -> CredentialEnvelope:
    if sys.stdin.isatty():
        return CredentialEnvelope()
    try:
        return CredentialEnvelope.from_stdin(sys.stdin)
    except (EOFError, ValueError, json.JSONDecodeError):
        return CredentialEnvelope()


def _case() -> dict:
    for row in load_jsonl(DATASET):
        if row.get("id") == CASE_ID:
            return row
    raise RuntimeError(f"{CASE_ID} not found in {DATASET}")


def _redact(text: str) -> str:
    secrets = list(_REPORT_SECRETS)
    secrets.extend(
        [
            os.environ.get("JEV_API_KEY", ""),
            os.environ.get("OPENAI_API_KEY", ""),
        ]
    )
    return redact_text(text, secrets)


def _finish(report: dict, code: int) -> int:
    folder = Path(os.environ.get("DEEPEVAL_RESULTS_FOLDER", "/eval/reports"))
    folder.mkdir(parents=True, exist_ok=True)
    text = _redact(json.dumps(report, ensure_ascii=False, indent=2)) + "\n"
    (folder / "jev.json").write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
