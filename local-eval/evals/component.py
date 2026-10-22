"""Native JevEval execution for selected Component trace spans."""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

from deepeval.metrics import JevEval
from deepeval.test_case import LLMTestCase

from evals.config import export_config, validate_config
from evals.credentials import CredentialEnvelope
from evals.emrank_jev import EmrankJevModel
from evals.execution import _questions
from ui.reports import ReportStore


def normalize_trace(
    trace: Mapping[str, Any], selected_ids: list[str]
) -> dict[str, Any]:
    """Validate a flat trace and return its deterministic nested representation."""
    if not isinstance(trace, Mapping):
        raise ValueError("trace must be an object")
    trace_id = trace.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("missing trace_id")
    spans = trace.get("spans")
    if not isinstance(spans, list) or not spans:
        raise ValueError("missing spans")

    by_id: dict[str, dict[str, Any]] = {}
    for span in spans:
        if not isinstance(span, Mapping):
            raise ValueError("span must be an object")
        span_id = span.get("span_id")
        if not isinstance(span_id, str) or not span_id.strip():
            raise ValueError("missing span_id")
        if span_id in by_id:
            raise ValueError(f"duplicate span_id: {span_id}")
        by_id[span_id] = copy.deepcopy(dict(span))

    for span in by_id.values():
        parent = span.get("parent_span_id")
        if parent is not None and parent not in by_id:
            raise ValueError(f"invalid parent span_id: {parent}")

    state: dict[str, int] = {}

    def visit(span_id: str) -> None:
        if state.get(span_id) == 1:
            raise ValueError(f"cycle in trace at span_id: {span_id}")
        if state.get(span_id) == 2:
            return
        state[span_id] = 1
        parent = by_id[span_id].get("parent_span_id")
        if parent is not None:
            visit(parent)
        state[span_id] = 2

    for span_id in by_id:
        visit(span_id)

    selected = list(selected_ids)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("selected span IDs must be unique and non-empty")
    missing = [span_id for span_id in selected if span_id not in by_id]
    if missing:
        raise ValueError(f"missing selected span_id: {missing[0]}")

    children: dict[str, list[dict[str, Any]]] = {
        span_id: [] for span_id in by_id
    }
    roots: list[dict[str, Any]] = []
    for span_id, span in by_id.items():
        span["children"] = children[span_id]
        parent = span.get("parent_span_id")
        if parent is None:
            roots.append(span)
        else:
            children[parent].append(span)

    return {
        "trace_id": trace_id,
        "context": copy.deepcopy(trace.get("context")),
        "metadata": copy.deepcopy(trace.get("metadata")),
        "spans": roots,
        "selected_span_ids": selected,
    }


def _model(config: Mapping[str, Any], credentials: CredentialEnvelope):
    jev = config["jev"]
    return EmrankJevModel(
        api_key=credentials.jev_api_key,
        base_url=jev["base_url"],
        model=jev["model"],
        timeout=jev.get("timeout") or 60,
        proxy=credentials.proxy,
        retry=jev.get("retry") or 0,
    )


def _selected_span(trace: Mapping[str, Any], span_id: str) -> dict[str, Any]:
    stack = list(trace.get("spans") or [])
    while stack:
        span = stack.pop()
        if span.get("span_id") == span_id:
            return span
        stack.extend(span.get("children") or [])
    raise KeyError(span_id)


def run_component(
    config: dict[str, Any],
    credentials: CredentialEnvelope,
    reports: ReportStore,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate selected spans through JevEval's native trace state."""
    frozen_config = validate_config(copy.deepcopy(config))
    exported_config = export_config(frozen_config)
    trace_path = Path(frozen_config["dataset"]["path"])
    raw_trace = json.loads(trace_path.read_text(encoding="utf-8"))
    component = frozen_config["component"]
    normalized = normalize_trace(raw_trace, component["node_ids"])
    run_id = run_id or uuid.uuid4().hex[:12]
    question_values = frozen_config["evaluation"]["questions"]
    question_mapping = {
        question["id"]: f"q_{index}"
        for index, question in enumerate(question_values)
    }
    selected = normalized["selected_span_ids"]
    reports.create(
        run_id,
        exported_config,
        [],
        spans=[{"id": span_id} for span_id in selected],
        snapshot=normalized,
        question_mapping=question_mapping,
        trace_id=normalized["trace_id"],
        aggregate_score=None,
    )
    model = _model(frozen_config, credentials)
    evaluation = frozen_config["evaluation"]
    metric = JevEval(
        name=frozen_config["project"]["name"],
        system_one_model=model,
        questions=_questions(question_values),
        include_reason=evaluation.get("include_reason", True),
        threshold=evaluation.get("threshold", 0.5),
        strict_mode=evaluation.get("strict_mode", False),
        async_mode=False,
        verbose_mode=False,
    )
    failures = False
    scores: list[float] = []
    for span_id in selected:
        span = _selected_span(normalized, span_id)
        try:
            test_case = LLMTestCase(
                input=str(span.get("input", "")),
                actual_output=(
                    str(span["output"])
                    if span.get("output") is not None
                    else None
                ),
                context=span.get("context", normalized.get("context")),
                metadata=span.get("metadata", normalized.get("metadata")),
            )
            test_case._trace_dict = span
            metric.measure(test_case, _show_indicator=False)
            if metric.score is None:
                raise RuntimeError("Jev returned no score")
            scores.append(metric.score)
            reports.record_span(
                run_id,
                span_id,
                execution_status="completed",
                verification_status="verified",
                quality_passed=metric.success,
                score=metric.score,
                confidence=metric.confidence,
                reason=metric.reason,
                score_breakdown=metric.score_breakdown,
                usage=model.last_usage,
                attempts=model.last_attempts,
            )
        except Exception as exc:
            failures = True
            reports.record_span(
                run_id,
                span_id,
                execution_status="failed",
                verification_status="not_verified",
                quality_passed=None,
                attempts=model.last_attempts,
                error=f"{type(exc).__name__}: {exc}",
            )

    aggregate = sum(scores) / len(scores) if scores and not failures else None
    if aggregate is not None:
        reports.set_aggregate(run_id, aggregate)
    quality_passed = (
        None
        if failures
        else all(
            item["quality_passed"] is True
            for item in reports.read(run_id)["spans"].values()
        )
    )
    return reports.finish(
        run_id,
        execution_status="failed" if failures else "completed",
        verification_status="not_verified" if failures else "verified",
        quality_passed=quality_passed,
    )
