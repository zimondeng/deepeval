import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepeval.metrics import JevEval
from deepeval.metrics.jev_eval import Noul
from deepeval.models import DeepEvalBaseSystemOneModel
from deepeval.models.system_one.schema import NoulAnswer, SystemOneAnswers
from deepeval.test_case import LLMTestCase, SingleTurnParams

from evals import execution
from evals.emrank_jev import EmrankJevModel
from evals.credentials import CredentialEnvelope
from ui.reports import ReportStore


class _Response:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_a5_jev_retries_transient_failures_only(monkeypatch):
    calls = []

    class Transient:
        code = 503

        def read(self, *_args, **_kwargs):
            return b"temporary"

    responses = iter(
        [
            Transient(),
            _Response({"answers": {"q": {"type": "noul", "noul": 1}}}),
        ]
    )

    def fake_open(*_args, **_kwargs):
        calls.append(1)
        response = next(responses)
        if isinstance(response, Transient):
            from urllib.error import HTTPError

            raise HTTPError("http://jev.test", response.code, "busy", {}, None)
        return response

    monkeypatch.setattr("evals.emrank_jev.urlopen", fake_open)
    monkeypatch.setattr("evals.emrank_jev.time.sleep", lambda *_args: None)
    model = EmrankJevModel(
        api_key="fake-key", base_url="http://jev.test", retry=1
    )

    answers, _ = model.decide({}, {"q": SimpleNamespace(instructions="valid")})

    assert answers.nouls["q"].probability == 1
    assert model.last_attempts == 2
    assert len(calls) == 2


def test_a5_jev_does_not_retry_auth_or_malformed_responses(monkeypatch):
    from urllib.error import HTTPError

    calls = []

    def auth_failure(*_args, **_kwargs):
        calls.append("auth")
        raise HTTPError("http://jev.test", 401, "unauthorized", {}, None)

    monkeypatch.setattr("evals.emrank_jev.urlopen", auth_failure)
    model = EmrankJevModel(
        api_key="fake-key", base_url="http://jev.test", retry=2
    )
    with pytest.raises(RuntimeError):
        model.decide({}, {"q": SimpleNamespace(instructions="valid")})
    assert calls == ["auth"]

    calls.clear()
    malformed_calls = []

    def malformed(*_args, **_kwargs):
        malformed_calls.append(1)
        return _Response("bad")

    monkeypatch.setattr("evals.emrank_jev.urlopen", malformed)
    with pytest.raises(Exception):
        model.decide({}, {"q": SimpleNamespace(instructions="valid")})
    assert len(malformed_calls) == 1


def test_a5_target_failure_is_not_retried(monkeypatch):
    from urllib.error import URLError

    calls = []

    def target_failure(*_args, **_kwargs):
        calls.append(1)
        raise URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", target_failure)
    with pytest.raises(RuntimeError):
        from evals.adapter import actual_output

        actual_output(
            {"id": "case", "input": "hello"},
            target_url="http://target.test",
            target_path="",
        )
    assert len(calls) == 1


def test_a7_execution_score_matches_direct_jev_eval(
    tmp_path: Path, monkeypatch
):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {"id": "case-1", "input": "hello", "actual_output": "answer"}
        )
        + "\n",
        encoding="utf-8",
    )
    config = {
        "schema_version": 1,
        "project": {"name": "consistency"},
        "jev": {"base_url": "http://jev.test", "model": "fake/model"},
        "evaluation": {
            "engine": "system_one",
            "scope": "e2e",
            "threshold": 0.5,
            "questions": [
                {"id": "relevant", "type": "noul", "text": "Relevant?"}
            ],
        },
        "dataset": {},
        "target": {"url": "http://target.test"},
        "component": None,
    }

    class FakeModel(DeepEvalBaseSystemOneModel):
        def __init__(self):
            super().__init__("fake/model")
            self.last_usage = {"input_tokens": 1, "output_tokens": 1}
            self.last_attempts = 1

        def load_model(self):
            return None

        def decide(self, _state, _questions):
            return (
                SystemOneAnswers(nouls={"q_0": NoulAnswer(probability=0.75)}),
                None,
            )

        async def a_decide(self, state, questions):
            return self.decide(state, questions)

        def get_model_name(self):
            return "fake/model"

    monkeypatch.setattr(
        execution, "EmrankJevModel", lambda **_kwargs: FakeModel()
    )
    monkeypatch.setattr(
        execution,
        "actual_output",
        lambda *args, **kwargs: ("answer", "fixture"),
    )
    report = execution.run_e2e(
        config,
        CredentialEnvelope(jev_api_key="fake-key"),
        ReportStore(tmp_path / "reports", secrets=["fake-key"]),
        run_id="a7",
        dataset_cases=[{"id": "case-1", "input": "hello", "actual_output": "answer", "expected_output": "answer"}],
    )

    direct = JevEval(
        name="consistency",
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        system_one_model=FakeModel(),
        threshold=0.5,
        async_mode=False,
        verbose_mode=False,
        questions=[Noul(statement="Relevant?")],
    )
    direct.measure(
        LLMTestCase(input="hello", actual_output="answer"),
        _show_indicator=False,
    )

    assert report["cases"]["case-1"]["score"] == direct.score
    assert report["cases"]["case-1"]["quality_passed"] is direct.success
    assert report["quality_passed"] is direct.success
