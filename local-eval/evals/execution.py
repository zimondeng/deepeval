"""Serial, verified E2E execution for the local system_one console."""

from __future__ import annotations

import copy
import time
import uuid
from pathlib import Path
from typing import Any

from deepeval.metrics import JevEval
from deepeval.metrics.jev_eval import Choice, Noul, Score
from deepeval.test_case import LLMTestCase, SingleTurnParams

from evals.adapter import actual_output, load_jsonl
from evals.config import export_config, validate_config
from evals.credentials import CredentialEnvelope
from evals.emrank_jev import EmrankJevModel
from ui.reports import ReportStore


_PARAMS = {
    "input": SingleTurnParams.INPUT,
    "actual_output": SingleTurnParams.ACTUAL_OUTPUT,
}


def run_e2e(
    config: dict[str, Any],
    credentials: CredentialEnvelope,
    reports: ReportStore,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run a frozen E2E dataset serially and return its canonical report."""
    frozen_config = validate_config(copy.deepcopy(config))
    exported_config = export_config(frozen_config)
    dataset_path = Path(frozen_config["dataset"]["path"])
    cases = load_jsonl(dataset_path)
    maximum = frozen_config["dataset"].get("max_cases")
    if maximum is not None:
        cases = cases[:maximum]
    if not cases:
        raise ValueError("dataset must contain at least one case")

    frozen_cases = copy.deepcopy(cases)
    run_id = run_id or uuid.uuid4().hex[:12]
    store = reports
    store.create(
        run_id,
        exported_config,
        frozen_cases,
        snapshot=frozen_cases,
    )
    jev = frozen_config["jev"]
    target = frozen_config["target"]
    evaluation = frozen_config["evaluation"]
    model = EmrankJevModel(
        api_key=credentials.jev_api_key,
        base_url=jev["base_url"],
        model=jev["model"],
        timeout=jev.get("timeout") or 60,
        proxy=credentials.proxy,
        retry=jev.get("retry", 2),
    )
    params = evaluation.get("evaluation_params") or ["input", "actual_output"]
    metric = JevEval(
        name=frozen_config["project"]["name"],
        evaluation_params=[_PARAMS[name] for name in params],
        system_one_model=model,
        threshold=evaluation.get("threshold", 0.5),
        async_mode=False,
        verbose_mode=False,
        questions=_questions(evaluation["questions"]),
    )
    failures = False
    quality_values: list[bool] = []
    for case in frozen_cases:
        started = time.perf_counter()
        try:
            output, source = actual_output(
                case,
                target_headers=target.get("headers"),
                proxy=credentials.proxy,
                target_url=target["url"],
                target_path="",
                timeout=target.get("timeout") or 60,
                body_template=target.get("body_template"),
                input_path=target.get("input_path"),
                turns_path=target.get("turns_path"),
                output_path=target.get("output_path"),
            )
            metric.measure(
                LLMTestCase(input=case["input"], actual_output=output),
                _show_indicator=False,
            )
            if metric.score is None:
                raise RuntimeError("Jev returned no score")
            quality_values.append(metric.success is True)
            store.record_case(
                run_id,
                case["id"],
                execution_status="completed",
                verification_status="verified",
                quality_passed=metric.success,
                score=metric.score,
                confidence=metric.confidence,
                reason=metric.reason,
                score_breakdown=_dump(metric.score_breakdown),
                usage=model.last_usage,
                attempts=model.last_attempts,
                duration_seconds=round(time.perf_counter() - started, 3),
                output_source=source,
            )
        except Exception as exc:
            failures = True
            store.record_case(
                run_id,
                case["id"],
                execution_status="failed",
                verification_status="not_verified",
                quality_passed=None,
                attempts=model.last_attempts,
                duration_seconds=round(time.perf_counter() - started, 3),
                error=f"{type(exc).__name__}: {exc}",
            )
    return store.finish(
        run_id,
        execution_status="failed" if failures else "completed",
        verification_status="not_verified" if failures else "verified",
        quality_passed=None if failures else all(quality_values),
    )


def _questions(values: list[dict[str, Any]]) -> list[Any]:
    questions = []
    for value in values:
        kind = value["type"]
        common = {"weight": value.get("weight", 1.0)}
        if kind == "noul":
            questions.append(
                Noul(
                    statement=value["text"],
                    true=value.get("true"),
                    false=value.get("false"),
                    **common,
                )
            )
        elif kind == "choice":
            questions.append(
                Choice(
                    question=value["text"], options=value["options"], **common
                )
            )
        else:
            questions.append(
                Score(question=value["text"], levels=value["levels"], **common)
            )
    return questions


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value
