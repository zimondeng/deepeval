"""Serial, verified E2E execution for the local system_one console."""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any

from deepeval.metrics import JevEval
from deepeval.metrics.jev_eval import Choice, Noul, Score
from deepeval.test_case import LLMTestCase, SingleTurnParams

from evals.adapter import actual_output
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
    dataset_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a frozen E2E dataset serially and return its canonical report."""
    frozen_config = validate_config(copy.deepcopy(config))
    exported_config = export_config(frozen_config)
    if dataset_cases is None:
        raise ValueError("dataset upload is required")
    cases = copy.deepcopy(dataset_cases)
    maximum = frozen_config["dataset"].get("max_cases")
    if maximum is not None:
        cases = cases[:maximum]
    if not cases:
        raise ValueError("dataset must contain at least one case")

    frozen_cases = copy.deepcopy(cases)
    evaluation = frozen_config["evaluation"]
    rubric_enabled = bool(evaluation.get("rubric"))
    question_values = _question_values(evaluation)
    run_id = run_id or uuid.uuid4().hex[:12]
    store = reports
    store.create(
        run_id,
        exported_config,
        frozen_cases,
        snapshot={"cases": frozen_cases, "questions": copy.deepcopy(question_values)},
        questions=copy.deepcopy(question_values),
        rubric={"criteria": copy.deepcopy(question_values), "enabled": rubric_enabled},
    )
    jev = frozen_config["jev"]
    target = frozen_config["target"]
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
        questions=_questions(question_values),
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
            answers = getattr(model, "last_answers", None)
            question_results = _question_results(
                question_values, metric, answers
            )
            score_breakdown = _dump(metric.score_breakdown)
            reason = _normalize_question_diagnostics(
                question_values, question_results, score_breakdown, metric.reason
            )
            rubric_score = (
                _rubric_score(question_values, question_results)
                if rubric_enabled
                else None
            )
            quality_passed = (
                rubric_score["percentage"] >= evaluation["threshold"]
                if rubric_score is not None
                else metric.success is True
            )
            quality_values.append(quality_passed)
            diagnostics = (
                {
                    "metric_score": metric.score,
                    "metric_quality_passed": metric.success,
                }
                if rubric_enabled
                else {}
            )
            store.record_case(
                run_id,
                case["id"],
                execution_status="completed",
                verification_status="verified",
                quality_passed=quality_passed,
                score=(
                    rubric_score["percentage"]
                    if rubric_score is not None
                    else metric.score
                ),
                confidence=metric.confidence,
                reason=reason,
                score_breakdown=score_breakdown,
                question_results=question_results,
                rubric_score=rubric_score,
                **diagnostics,
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


def _rubric_score(values, results) -> dict[str, Any]:
    missing = [
        value["id"]
        for value in values
        if "answer" not in results.get(value["id"], {})
    ]
    if missing:
        raise RuntimeError(
            "Jev returned no structured answer for: " + ", ".join(missing)
        )
    total = sum(float(value.get("weight", 1.0)) for value in values)
    passed = sum(
        float(value.get("weight", 1.0))
        for value in values
        if results.get(value["id"], {}).get("answer") is True
    )
    return {
        "passed": passed,
        "total": total,
        "percentage": passed / total if total else 0.0,
    }


def _question_values(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    rubric = evaluation.get("rubric")
    if rubric:
        return [{**criterion, "type": "noul"} for criterion in rubric]
    return evaluation["questions"]


def evaluation_questions(config: dict[str, Any]) -> list[dict[str, Any]]:
    return copy.deepcopy(_question_values(config["evaluation"]))


def _normalize_question_diagnostics(
    values: list[dict[str, Any]],
    question_results: dict[str, dict[str, Any]],
    score_breakdown: list[dict[str, Any]],
    reason: str | None,
) -> str | None:
    replacements = []
    for index, value in enumerate(values):
        question = value["text"]
        result = question_results.get(value["id"], {})
        for diagnostic in (result, score_breakdown[index]):
            encoded = diagnostic.get("question")
            if isinstance(encoded, str) and encoded != question:
                replacements.append((encoded, question))
                diagnostic["question"] = question
    if reason is None:
        return None
    for encoded, question in replacements:
        reason = reason.replace(encoded, question)
    return reason


def _question_results(values, metric, answers) -> dict[str, Any]:
    if answers is None:
        return {}
    results = {}
    for index, value in enumerate(values):
        key = f"q_{index}"
        try:
            outcome = metric.score_breakdown[index]
        except (IndexError, TypeError):
            raise RuntimeError(
                f"Jev returned no score breakdown for question {value['id']!r}"
            ) from None
        result = _dump(outcome)
        # DeepEval may lose non-ASCII text in its diagnostic breakdown; the
        # configured question is the authoritative display value.
        result["question"] = value["text"]
        answer = (
            answers.nouls.get(key)
            or answers.choices.get(key)
            or answers.scores.get(key)
        )
        if answers.nouls.get(key) is not None:
            result["answer"] = answers.nouls[key].probability >= 0.5
        elif answers.choices.get(key) is not None:
            result["answer"] = answers.choices[key].choice
        elif answers.scores.get(key) is not None:
            result["answer"] = answers.scores[key].score
        if answer is not None and hasattr(answer, "confidence"):
            result["confidence"] = answer.confidence
        results[value["id"]] = result
    return results


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
