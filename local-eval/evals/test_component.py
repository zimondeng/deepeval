import json
from pathlib import Path

import pytest

from evals.component import normalize_trace, run_component
from evals.credentials import CredentialEnvelope
from ui.reports import ReportStore
from deepeval.models import DeepEvalBaseSystemOneModel


def _trace(**overrides):
    value = {
        "trace_id": "trace-1",
        "context": ["trace context"],
        "spans": [
            {
                "span_id": "root",
                "parent_span_id": None,
                "name": "root",
                "input": "question",
                "output": "root output",
            },
            {
                "span_id": "selected",
                "parent_span_id": "root",
                "name": "selected",
                "input": "component input",
                "output": "component output",
                "context": ["span context"],
            },
        ],
    }
    value.update(overrides)
    return value


def test_normalize_trace_preserves_ids_relationships_and_context():
    normalized = normalize_trace(_trace(), ["selected"])

    assert normalized["trace_id"] == "trace-1"
    assert normalized["selected_span_ids"] == ["selected"]
    assert normalized["spans"][0]["span_id"] == "root"
    assert normalized["spans"][0]["children"][0]["span_id"] == "selected"
    assert normalized["spans"][0]["children"][0]["parent_span_id"] == "root"
    assert normalized["spans"][0]["children"][0]["context"] == ["span context"]
    assert normalized["context"] == ["trace context"]


@pytest.mark.parametrize(
    "spans, message",
    [
        ([{"span_id": "other"}], "missing"),
        (
            [
                {"span_id": "root", "parent_span_id": None},
                {"span_id": "root", "parent_span_id": None},
            ],
            "duplicate",
        ),
        ([{"span_id": "child", "parent_span_id": "missing"}], "parent"),
        (
            [
                {"span_id": "a", "parent_span_id": "b"},
                {"span_id": "b", "parent_span_id": "a"},
            ],
            "cycle",
        ),
    ],
)
def test_normalize_trace_rejects_invalid_graph(spans, message):
    with pytest.raises(ValueError, match=message):
        normalize_trace({"trace_id": "trace-1", "spans": spans}, ["root"])


def test_run_component_uses_native_jev_trace_state_and_aggregates(
    tmp_path: Path, monkeypatch
):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps(_trace()), encoding="utf-8")
    config = {
        "schema_version": 1,
        "project": {"name": "component"},
        "jev": {"base_url": "http://jev.test", "model": "fake/model"},
        "evaluation": {
            "engine": "system_one",
            "scope": "component",
            "threshold": 0.5,
            "questions": [
                {"id": "relevant", "type": "noul", "text": "Relevant"}
            ],
        },
        "dataset": {"path": str(trace_path)},
        "target": {"url": "http://target.test"},
        "component": {"trace_path": "spans", "node_ids": ["selected"]},
    }
    calls = []

    class FakeModel(DeepEvalBaseSystemOneModel):
        def __init__(self):
            super().__init__("fake")
            self.last_usage = {"input_tokens": 2, "output_tokens": 1}
            self.last_attempts = 1

        def load_model(self):
            return None

        def decide(self, state, questions):
            calls.append((state, questions))
            from deepeval.models.system_one.schema import (
                NoulAnswer,
                SystemOneAnswers,
            )

            return (
                SystemOneAnswers(nouls={"q_0": NoulAnswer(probability=1)}),
                None,
            )

        async def a_decide(self, state, questions):
            return self.decide(state, questions)

        def get_model_name(self):
            return "fake"

    monkeypatch.setattr(
        "evals.component._model", lambda *args, **kwargs: FakeModel()
    )
    report = run_component(
        config,
        CredentialEnvelope(jev_api_key="fake-key"),
        ReportStore(tmp_path / "reports", secrets=["fake-key"]),
        run_id="component1",
    )

    assert report["execution_status"] == "completed"
    assert report["quality_passed"] is True
    assert report["aggregate_score"] == 1.0
    assert report["spans"]["selected"]["score"] == 1.0
    assert report["question_mapping"] == {"relevant": "q_0"}
    assert calls[0][0]["trace"]["input"] == "component input"
    assert (
        report["input_snapshot"]["content"]["spans"][0]["children"][0][
            "span_id"
        ]
        == "selected"
    )


def test_run_component_does_not_aggregate_failed_nodes(tmp_path, monkeypatch):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps(_trace()), encoding="utf-8")
    config = {
        "schema_version": 1,
        "project": {"name": "component"},
        "jev": {"base_url": "http://jev.test", "model": "fake/model"},
        "evaluation": {
            "engine": "system_one",
            "scope": "component",
            "questions": [
                {"id": "relevant", "type": "noul", "text": "Relevant"}
            ],
        },
        "dataset": {"path": str(trace_path)},
        "target": {"url": "http://target.test"},
        "component": {"trace_path": "spans", "node_ids": ["selected"]},
    }

    class BrokenModel(DeepEvalBaseSystemOneModel):
        def __init__(self):
            super().__init__("fake")
            self.last_usage = None
            self.last_attempts = 1

        def load_model(self):
            return None

        def decide(self, state, questions):
            raise RuntimeError("jev unavailable")

        async def a_decide(self, state, questions):
            return self.decide(state, questions)

        def get_model_name(self):
            return "fake"

    monkeypatch.setattr(
        "evals.component._model", lambda *args, **kwargs: BrokenModel()
    )
    report = run_component(
        config,
        CredentialEnvelope(jev_api_key="fake-key"),
        ReportStore(tmp_path / "reports", secrets=["fake-key"]),
        run_id="component2",
    )

    assert report["execution_status"] == "failed"
    assert report["quality_passed"] is None
    assert report["aggregate_score"] is None


def test_selected_component_inherits_trace_and_ancestor_context():
    from evals.component import _effective_span, _selected_span

    trace = normalize_trace(
        {
            "trace_id": "trace-1",
            "context": ["trace context"],
            "metadata": {"trace": "yes"},
            "spans": [
                {
                    "span_id": "root",
                    "parent_span_id": None,
                    "context": ["root context"],
                    "metadata": {"root": "yes"},
                },
                {
                    "span_id": "selected",
                    "parent_span_id": "root",
                    "context": ["span context"],
                    "metadata": {"span": "yes"},
                },
            ],
        },
        ["selected"],
    )

    selected = _effective_span(trace, _selected_span(trace, "selected"))

    assert selected["context"] == [
        "trace context",
        "root context",
        "span context",
    ]
    assert selected["metadata"] == {
        "trace": "yes",
        "root": "yes",
        "span": "yes",
    }
