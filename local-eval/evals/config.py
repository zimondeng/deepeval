"""Shared schema-v1 configuration validation for the local console."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

MAX_CASES = 10_000
MAX_FIELD_LENGTH = 8_192
MAX_QUESTIONS = 100
MAX_DATASET_BYTES = 10 * 1024 * 1024

_TOP_LEVEL = {
    "schema_version",
    "project",
    "jev",
    "evaluation",
    "dataset",
    "target",
    "component",
}
_SECRET_NAMES = {"authorization", "cookie", "set-cookie", "proxy-authorization"}


class ConfigValidationError(ValueError):
    """Validation failure with stable paths suitable for API field errors."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__(
            "; ".join(f"{path}: {message}" for path, message in errors.items())
        )


def validate_config(
    config: Mapping[str, Any], allowed_root: str | Path | None = None
) -> dict[str, Any]:
    """Validate and copy a schema-v1 configuration without contacting services."""
    errors: dict[str, str] = {}
    if not isinstance(config, Mapping):
        raise ConfigValidationError({"config": "must be an object"})

    _object(config, "config", _TOP_LEVEL, errors)
    if config.get("schema_version") != 1 or isinstance(
        config.get("schema_version"), bool
    ):
        errors["schema_version"] = "must be integer 1"

    for section in ("project", "jev", "evaluation", "dataset", "target"):
        if not isinstance(config.get(section), Mapping):
            errors[section] = "must be an object"
    if (
        "component" in config
        and config["component"] is not None
        and not isinstance(config["component"], Mapping)
    ):
        errors["component"] = "must be an object or null"

    project = config.get("project")
    if isinstance(project, Mapping):
        _object(project, "project", {"name", "description"}, errors)
        _string(project.get("name"), "project.name", errors, required=True)
        _string(project.get("description"), "project.description", errors)

    jev = config.get("jev")
    if isinstance(jev, Mapping):
        _object(
            jev,
            "jev",
            {
                "base_url",
                "model",
                "timeout",
                "proxy",
                "retry",
                "api_key",
                "credential_ref",
            },
            errors,
        )
        _url(jev.get("base_url"), "jev.base_url", errors, required=True)
        _string(jev.get("model"), "jev.model", errors, required=True)
        _number(jev.get("timeout"), "jev.timeout", errors, minimum=0.001)
        _number(jev.get("retry"), "jev.retry", errors, minimum=0, integer=True)
        _string(jev.get("proxy"), "jev.proxy", errors)
        _string(jev.get("api_key"), "jev.api_key", errors)
        if "credential_ref" in jev:
            _string(jev.get("credential_ref"), "jev.credential_ref", errors)
        _reject_secret_url(jev.get("proxy"), "jev.proxy", errors)

    evaluation = config.get("evaluation")
    if isinstance(evaluation, Mapping):
        _object(
            evaluation,
            "evaluation",
            {
                "engine",
                "scope",
                "threshold",
                "strict_mode",
                "questions",
                "evaluation_params",
                "include_reason",
                "rubric",
            },
            errors,
        )
        if evaluation.get("engine") != "system_one":
            errors["evaluation.engine"] = "must be 'system_one'"
        if evaluation.get("scope") not in {"e2e", "component"}:
            errors["evaluation.scope"] = "must be 'e2e' or 'component'"
        _number(
            evaluation.get("threshold"),
            "evaluation.threshold",
            errors,
            minimum=0,
            maximum=1,
        )
        _bool(evaluation.get("strict_mode"), "evaluation.strict_mode", errors)
        _bool(
            evaluation.get("include_reason"),
            "evaluation.include_reason",
            errors,
        )
        params = evaluation.get("evaluation_params")
        _list(params, "evaluation.evaluation_params", errors)
        if isinstance(params, list):
            supported = {"input", "actual_output"}
            for index, value in enumerate(params):
                if value not in supported:
                    errors[f"evaluation.evaluation_params[{index}]"] = (
                        "must be 'input' or 'actual_output'"
                    )
            if not params:
                errors["evaluation.evaluation_params"] = "must not be empty"
        questions = evaluation.get("questions")
        rubric = evaluation.get("rubric")
        rubric_enabled = rubric is not None
        if rubric_enabled:
            if questions not in (None, []):
                errors["evaluation.questions"] = (
                    "must be empty when rubric is enabled"
                )
        elif not isinstance(questions, list) or not questions:
            errors["evaluation.questions"] = (
                "must contain at least one question"
            )
        elif len(questions) > MAX_QUESTIONS:
            errors["evaluation.questions"] = (
                f"must contain at most {MAX_QUESTIONS} questions"
            )
        elif isinstance(questions, list):
            _questions(questions, errors)
        if rubric_enabled:
            if not isinstance(rubric, list) or not rubric:
                errors["evaluation.rubric"] = "must be a non-empty array"
            elif len(rubric) > MAX_QUESTIONS:
                errors["evaluation.rubric"] = f"must contain at most {MAX_QUESTIONS} criteria"
            else:
                _rubric(rubric, errors)

    dataset = config.get("dataset")
    if isinstance(dataset, Mapping):
        _object(dataset, "dataset", {"path", "max_cases", "max_bytes"}, errors)
        dataset_path = dataset.get("path")
        scope = config.get("evaluation", {}).get("scope") if isinstance(config.get("evaluation"), Mapping) else None
        if dataset_path not in (None, "") and scope != "component":
            errors["dataset.path"] = (
                "project dataset paths are no longer supported; upload a JSONL file"
            )
        _number(
            dataset.get("max_cases"),
            "dataset.max_cases",
            errors,
            minimum=1,
            maximum=MAX_CASES,
            integer=True,
        )
        _number(
            dataset.get("max_bytes"),
            "dataset.max_bytes",
            errors,
            minimum=1,
            maximum=MAX_DATASET_BYTES,
            integer=True,
        )

    target = config.get("target")
    if isinstance(target, Mapping):
        _object(
            target,
            "target",
            {
                "url",
                "headers",
                "body_template",
                "input_path",
                "turns_path",
                "output_path",
                "timeout",
            },
            errors,
        )
        _url(target.get("url"), "target.url", errors, required=False)
        _headers(target.get("headers"), "target.headers", errors)
        _string(target.get("body_template"), "target.body_template", errors)
        for name in ("input_path", "turns_path", "output_path"):
            _dot_path(target.get(name), f"target.{name}", errors)
        _number(target.get("timeout"), "target.timeout", errors, minimum=0.001)

    component = config.get("component")
    scope = evaluation.get("scope") if isinstance(evaluation, Mapping) else None
    if scope == "component" and not isinstance(component, Mapping):
        errors["component"] = "is required for component scope"
    if isinstance(component, Mapping):
        _object(
            component,
            "component",
            {"trace_path", "node_ids", "questions"},
            errors,
        )
        _path(
            component.get("trace_path"),
            "component.trace_path",
            errors,
            allowed_root,
            required=True,
        )
        if not isinstance(component.get("node_ids"), list) or not component.get(
            "node_ids"
        ):
            errors["component.node_ids"] = "must contain at least one node id"
        if "questions" in component:
            if (
                not isinstance(component["questions"], list)
                or not component["questions"]
            ):
                errors["component.questions"] = "must be a non-empty array"
            else:
                _questions(component["questions"], errors)

    if errors:
        raise ConfigValidationError(errors)
    return copy.deepcopy(dict(config))


def export_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return validated non-secret configuration suitable for persistence."""
    result = validate_config(config)
    jev = result.get("jev", {})
    if isinstance(jev, dict):
        jev.pop("api_key", None)
        if jev.get("credential_ref") is None:
            jev["credential_ref"] = "session"
    return result


def _object(
    value: Any, path: str, allowed: set[str], errors: dict[str, str]
) -> None:
    if not isinstance(value, Mapping):
        return
    for key in value:
        if key not in allowed:
            errors[f"{path}.{key}"] = "unknown field"


def _string(
    value: Any, path: str, errors: dict[str, str], required: bool = False
) -> None:
    if value is None and not required:
        return
    if not isinstance(value, str) or len(value) > MAX_FIELD_LENGTH:
        errors[path] = (
            "must be a non-empty string" if required else "must be a string"
        )
    elif required and not value.strip():
        errors[path] = "must be a non-empty string"


def _bool(value: Any, path: str, errors: dict[str, str]) -> None:
    if value is not None and not isinstance(value, bool):
        errors[path] = "must be boolean"


def _number(
    value: Any,
    path: str,
    errors: dict[str, str],
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        errors[path] = "must be a finite number"
        return
    if integer and not isinstance(value, int):
        errors[path] = "must be an integer"
    elif minimum is not None and value < minimum:
        errors[path] = f"must be at least {minimum}"
    elif maximum is not None and value > maximum:
        errors[path] = f"must be at most {maximum}"


def _list(value: Any, path: str, errors: dict[str, str]) -> None:
    if value is not None and not isinstance(value, list):
        errors[path] = "must be an array"


def _url(
    value: Any, path: str, errors: dict[str, str], required: bool = False
) -> None:
    if isinstance(value, str) and not value.strip() and not required:
        return
    _string(value, path, errors, required)
    if isinstance(value, str):
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            errors[path] = "must be an HTTP(S) URL without credentials"


def _reject_secret_url(value: Any, path: str, errors: dict[str, str]) -> None:
    if isinstance(value, str) and (
        urlparse(value).username or urlparse(value).password
    ):
        errors[path] = "must not contain credentials"


def _headers(value: Any, path: str, errors: dict[str, str]) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        errors[path] = "must be an object"
        return
    for key, header_value in value.items():
        if not isinstance(key, str) or not isinstance(header_value, str):
            errors[f"{path}.{key}"] = "must be strings"
        elif key.lower() in _SECRET_NAMES:
            errors[f"{path}.{key}"] = (
                "credential-bearing headers are not allowed"
            )


def _path(
    value: Any,
    path: str,
    errors: dict[str, str],
    allowed_root: str | Path | None,
    required: bool = False,
) -> None:
    _string(value, path, errors, required)
    if not isinstance(value, str) or allowed_root is None:
        return
    root = Path(allowed_root).resolve()
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        errors[path] = "must stay inside the allowed directory"
    else:
        if candidate.exists() and candidate.is_symlink():
            errors[path] = "symbolic links are not allowed"


def _dot_path(value: Any, path: str, errors: dict[str, str]) -> None:
    if value is None or value == "":
        return
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(".")
        or ".." in value.split(".")
    ):
        errors[path] = "must be a dot-separated field path"


def _questions(questions: list[Any], errors: dict[str, str]) -> None:
    from deepeval.metrics.jev_eval.questions import Choice, Noul, Score

    ids: set[str] = set()
    for index, question in enumerate(questions):
        path = f"evaluation.questions[{index}]"
        if not isinstance(question, Mapping):
            errors[path] = "must be an object"
            continue
        allowed = {
            "id",
            "type",
            "text",
            "weight",
            "true",
            "false",
            "options",
            "levels",
        }
        _object(question, path, allowed, errors)
        question_id = question.get("id")
        if not isinstance(question_id, str) or not question_id.strip():
            errors[f"{path}.id"] = "must be a non-empty string"
        elif question_id in ids:
            errors[f"{path}.id"] = "must be unique"
        else:
            ids.add(question_id)
        kind = question.get("type")
        _number(
            question.get("weight", 1.0),
            f"{path}.weight",
            errors,
            minimum=0.0000001,
        )
        if kind == "choice" and isinstance(question.get("options"), Mapping):
            for name, credit in question["options"].items():
                _number(
                    credit,
                    f"{path}.options.{name}",
                    errors,
                    minimum=0,
                    maximum=1,
                )
        try:
            data = {"weight": question.get("weight", 1.0)}
            if kind == "noul":
                data.update(
                    statement=question.get("text"),
                    true=question.get("true"),
                    false=question.get("false"),
                )
                Noul(**data)
            elif kind == "choice":
                data.update(
                    question=question.get("text"),
                    options=question.get("options"),
                )
                Choice(**data)
            elif kind == "score":
                data.update(
                    question=question.get("text"), levels=question.get("levels")
                )
                Score(**data)
            else:
                errors[f"{path}.type"] = "must be 'noul', 'choice' or 'score'"
        except Exception as exc:
            field = (
                "options"
                if kind == "choice"
                else "levels" if kind == "score" else "text"
            )
            if "weight" in str(exc).lower():
                field = "weight"
            errors[f"{path}.{field}"] = str(exc).split("\n")[-1]


def _rubric(criteria: list[Any], errors: dict[str, str]) -> None:
    ids: set[str] = set()
    for index, criterion in enumerate(criteria):
        path = f"evaluation.rubric[{index}]"
        if not isinstance(criterion, Mapping):
            errors[path] = "must be an object"
            continue
        _object(criterion, path, {"id", "text", "weight", "true", "false"}, errors)
        criterion_id = criterion.get("id")
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            errors[f"{path}.id"] = "must be a non-empty string"
        elif criterion_id in ids:
            errors[f"{path}.id"] = "must be unique"
        else:
            ids.add(criterion_id)
        _string(criterion.get("text"), f"{path}.text", errors, required=True)
        _number(criterion.get("weight", 1.0), f"{path}.weight", errors, minimum=0.0000001)
        _string(criterion.get("true"), f"{path}.true", errors, required=True)
        _string(criterion.get("false"), f"{path}.false", errors, required=True)
