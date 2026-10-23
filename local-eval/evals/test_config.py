import copy
import json
import math
from pathlib import Path

import pytest

from evals.config import ConfigValidationError, export_config, validate_config


@pytest.fixture
def valid_config(tmp_path: Path) -> dict:
    return {
        "schema_version": 1,
        "project": {"name": "demo"},
        "jev": {
            "base_url": "https://emrank.tech",
            "model": "typesafe/jev-1.14.0",
            "api_key": "session-secret",
            "timeout": 60,
            "retry": 2,
        },
        "evaluation": {
            "engine": "system_one",
            "scope": "e2e",
            "threshold": 0.5,
            "strict_mode": False,
            "questions": [
                {
                    "id": "q1",
                    "type": "noul",
                    "text": "The answer is relevant.",
                    "weight": 1.0,
                }
            ],
        },
        "dataset": {"path": str(tmp_path / "cases.jsonl"), "max_cases": 100},
        "target": {"url": "https://example.test/chat", "timeout": 30},
        "component": None,
    }


def test_validate_accepts_schema_v1_and_returns_copy(valid_config):
    result = validate_config(valid_config)

    assert result == valid_config
    assert result is not valid_config


def test_unknown_fields_report_field_level_error(valid_config):
    config = copy.deepcopy(valid_config)
    config["evaluation"]["unexpected"] = True

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config)

    assert raised.value.errors == {"evaluation.unexpected": "unknown field"}


@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf])
def test_numeric_fields_reject_bool_and_non_finite_values(valid_config, value):
    config = copy.deepcopy(valid_config)
    config["evaluation"]["threshold"] = value

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config)

    assert "evaluation.threshold" in raised.value.errors


def test_engine_and_scope_are_separate_and_fixed(valid_config):
    config = copy.deepcopy(valid_config)
    config["evaluation"]["engine"] = "e2e"

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config)

    assert raised.value.errors["evaluation.engine"]


def test_invalid_questions_have_field_level_errors(valid_config):
    config = copy.deepcopy(valid_config)
    config["evaluation"]["questions"] = [
        {"id": "bad", "type": "choice", "text": "Pick", "options": {"only": 1}}
    ]

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config)

    assert "evaluation.questions[0].options" in raised.value.errors


@pytest.mark.parametrize("field_value", [True, math.nan, math.inf])
def test_question_weight_and_choice_credit_are_strict_numbers(
    valid_config, field_value
):
    config = copy.deepcopy(valid_config)
    config["evaluation"]["questions"][0]["weight"] = field_value
    config["evaluation"]["questions"][0]["type"] = "choice"
    config["evaluation"]["questions"][0]["text"] = "Pick"
    config["evaluation"]["questions"][0]["options"] = {
        "yes": field_value,
        "no": None,
    }

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config)

    assert "evaluation.questions[0].weight" in raised.value.errors


def test_component_scope_requires_component_config(valid_config):
    config = copy.deepcopy(valid_config)
    config["evaluation"]["scope"] = "component"
    config["component"] = None

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config)

    assert raised.value.errors["component"]


def test_dataset_path_must_stay_inside_allowed_root(valid_config, tmp_path):
    config = copy.deepcopy(valid_config)
    config["dataset"]["path"] = str(tmp_path.parent / "outside.jsonl")

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config, allowed_root=tmp_path)

    assert "dataset.path" in raised.value.errors


def test_limits_reject_oversized_dataset(valid_config):
    config = copy.deepcopy(valid_config)
    config["dataset"]["max_cases"] = 10001

    with pytest.raises(ConfigValidationError) as raised:
        validate_config(config)

    assert "dataset.max_cases" in raised.value.errors


def test_export_is_secret_free_and_does_not_mutate(valid_config):
    exported = export_config(valid_config)

    assert "api_key" not in json.dumps(exported)
    assert exported["jev"]["credential_ref"] == "session"
    assert valid_config["jev"]["api_key"] == "session-secret"


def test_fixture_target_may_omit_url(valid_config):
    config = {
        **valid_config,
        "target": {
            "url": "",
            "body_template": "",
            "output_path": "",
        },
    }

    validated = validate_config(config)

    assert validated["target"]["url"] == ""


def test_export_rejects_secrets_in_target_headers(valid_config):
    config = copy.deepcopy(valid_config)
    config["target"]["headers"] = {"Authorization": "Bearer secret"}

    with pytest.raises(ConfigValidationError) as raised:
        export_config(config)

    assert "target.headers.Authorization" in raised.value.errors
