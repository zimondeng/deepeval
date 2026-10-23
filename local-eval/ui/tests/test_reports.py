import io
import json
import zipfile
from pathlib import Path

from ui.reports import ReportStore


def test_report_is_canonical_and_reconstructs_latest_from_run_file(
    tmp_path: Path,
):
    store = ReportStore(tmp_path, secrets=["jev-secret"])
    store.create(
        "abc123",
        config={"evaluation": {"engine": "system_one", "scope": "e2e"}},
        cases=[{"id": "case-1", "input": "hello"}],
        snapshot={"cases": [{"id": "case-1", "input": "hello"}]},
    )

    store.record_case(
        "abc123",
        "case-1",
        execution_status="completed",
        verification_status="verified",
        quality_passed=True,
        score=0.9,
        attempts=2,
        usage={"input_tokens": 10, "output_tokens": 4},
        duration_seconds=1.25,
        error="request failed with jev-secret",
    )
    finished = store.finish(
        "abc123",
        execution_status="completed",
        verification_status="verified",
        quality_passed=True,
    )

    assert finished["execution_status"] == "completed"
    assert finished["verification_status"] == "verified"
    assert finished["quality_passed"] is None
    assert finished["completeness"] == {"expected": 1, "completed": 1}
    assert finished["cases"]["case-1"] == {
        "execution_status": "completed",
        "verification_status": "verified",
        "quality_passed": True,
        "score": 0.9,
        "attempts": 2,
        "usage": {"input_tokens": 10, "output_tokens": 4},
        "duration_seconds": 1.25,
        "error": "request failed with ***",
        "raw": {"id": "case-1", "input": "hello"},
        "question_results": {},
    }
    assert finished["input_snapshot"]["sha256"]
    assert finished["input_snapshot"]["content"] == {
        "cases": [{"id": "case-1", "input": "hello"}]
    }

    latest = store.latest()
    assert latest == finished
    (tmp_path / "latest.json").unlink()
    assert store.latest() == finished
    assert not (tmp_path / "jev.json").exists()
    assert not (tmp_path / "smoke.json").exists()


def test_span_completeness_and_partial_quality_are_not_overstated(
    tmp_path: Path,
):
    store = ReportStore(tmp_path)
    store.create(
        "def456",
        config={},
        cases=[{"id": "case-1"}],
        spans=[{"id": "span-1"}, {"id": "span-2"}],
    )

    store.record_span(
        "def456",
        "span-1",
        execution_status="completed",
        verification_status="verified",
        quality_passed=True,
        score=1.0,
        attempts=1,
        usage=None,
        duration_seconds=0.2,
    )
    report = store.finish(
        "def456",
        execution_status="completed",
        verification_status="partial",
        quality_passed=None,
    )

    assert report["completeness"] == {"expected": 3, "completed": 1}
    assert report["case_completeness"] == {"expected": 1, "completed": 0}
    assert report["span_completeness"] == {"expected": 2, "completed": 1}
    assert report["quality_passed"] is None
    assert report["spans"]["span-2"]["execution_status"] == "not_run"
    assert report["spans"]["span-1"]["usage"] is None


def test_terminal_report_cannot_be_overwritten_by_late_events(tmp_path: Path):
    store = ReportStore(tmp_path)
    store.create("fedcba", config={}, cases=[{"id": "case-1"}])
    completed = store.finish(
        "fedcba",
        execution_status="completed",
        verification_status="verified",
        quality_passed=False,
    )

    late = store.record_case(
        "fedcba",
        "case-1",
        execution_status="failed",
        verification_status="not_verified",
        quality_passed=None,
        score=None,
        attempts=3,
        usage=None,
        duration_seconds=9.0,
        error="late error",
    )

    assert late == completed
    assert json.loads((tmp_path / "run_fedcba.json").read_text()) == completed


def test_report_escapes_isolated_surrogates_in_input(tmp_path: Path):
    store = ReportStore(tmp_path)
    invalid = "bad" + chr(0xDCBB)
    store.create(
        "surrogate1",
        config={"project": {"name": invalid}},
        cases=[{"id": "case-1", "input": invalid}],
        snapshot={"input": invalid},
    )

    report = store.read("surrogate1")

    assert "\\udcbb" in (tmp_path / "run_surrogate1.json").read_text(
        encoding="utf-8"
    )
    assert report["input_snapshot"]["content"]["input"] == invalid


def test_report_redacts_nested_values_and_excel_cells(tmp_path: Path):
    store = ReportStore(tmp_path, secrets=["TOPSECRET"])
    store.create(
        "secret1",
        config={},
        cases=[{"id": "case-1", "input": "TOPSECRET"}],
        snapshot={"input": "TOPSECRET"},
    )
    store.record_case(
        "secret1",
        "case-1",
        execution_status="completed",
        verification_status="verified",
        quality_passed=True,
        score=1.0,
        usage={"token": "TOPSECRET"},
        reason="TOPSECRET",
        question_results={"q": {"reason": "TOPSECRET"}},
        rubric_score={"passed": 1, "total": 1, "reason": "TOPSECRET"},
    )
    report = store.finish(
        "secret1",
        execution_status="completed",
        verification_status="verified",
        quality_passed=True,
    )

    assert "TOPSECRET" not in json.dumps(report)
    workbook = store.export_xlsx("secret1")
    assert b"TOPSECRET" not in workbook
    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        workbook_xml = archive.read("xl/workbook.xml")
    assert b"Judgments" in workbook_xml
    assert b"Raw Report" in workbook_xml
    assert b"Raw JSON" in workbook_xml


def test_xlsx_sanitizes_controls_and_formula_text(tmp_path: Path):
    store = ReportStore(tmp_path)
    store.create("xlsx1", config={}, cases=[{"id": "case-1"}])
    store.record_case(
        "xlsx1",
        "case-1",
        execution_status="completed",
        verification_status="verified",
        quality_passed=True,
        reason="=1+1\x00\x01",
        question_results={"q": {"reason": "=1+1\x00\x01"}},
    )
    store.finish(
        "xlsx1",
        execution_status="completed",
        verification_status="verified",
        quality_passed=True,
    )

    workbook = store.export_xlsx("xlsx1")
    assert b"=1+1" not in workbook
    assert b"&#x1;" not in workbook
