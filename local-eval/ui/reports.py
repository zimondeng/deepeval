"""Atomic, canonical reports for local evaluation runs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from xml.sax.saxutils import escape
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_TERMINAL = {"completed", "failed", "cancelled"}
_ITEM_DEFAULTS = {
    "execution_status": "not_run",
    "verification_status": "not_verified",
    "quality_passed": None,
    "score": None,
    "attempts": 0,
    "usage": None,
    "duration_seconds": None,
    "error": None,
}
_ITEM_FIELDS = set(_ITEM_DEFAULTS) | {
    "confidence",
    "reason",
    "score_breakdown",
    "output_source",
    "raw",
    "question_results",
    "rubric_score",
    "metric_score",
    "metric_quality_passed",
}
_SECRET_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "proxy",
    "token",
    "access_token",
    "refresh_token",
    "secret",
}


class ReportStore:
    """Persist one authoritative JSON document per run."""

    def __init__(self, folder: Path, secrets: Iterable[str] = ()):
        self._folder = Path(folder)
        self._secrets = tuple(secret for secret in secrets if secret)

    def create(
        self,
        run_id: str,
        config: dict[str, Any],
        cases: list[dict[str, Any]],
        spans: list[dict[str, Any]] | None = None,
        snapshot: Any = None,
        **metadata: Any,
    ) -> dict[str, Any]:
        report = {
            "schema_version": 2,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "execution_status": "queued",
            "verification_status": "not_verified",
            "quality_passed": None,
            "config": self._redact(config),
            "input_snapshot": self._snapshot(snapshot),
            "cases": {
                item["id"]: {
                    **dict(_ITEM_DEFAULTS),
                    "raw": self._redact(item),
                    "question_results": {},
                }
                for item in cases
                if isinstance(item.get("id"), str)
            },
            "spans": {
                item["id"]: dict(_ITEM_DEFAULTS)
                for item in (spans or [])
                if isinstance(item.get("id"), str)
            },
            "aggregate_score": metadata.pop("aggregate_score", None),
            **self._redact(metadata),
        }
        self._refresh_completeness(report)
        self._write(run_id, report)
        return report

    def record_case(
        self, run_id: str, case_id: str, **values: Any
    ) -> dict[str, Any]:
        return self._record("cases", run_id, case_id, values)

    def record_span(
        self, run_id: str, span_id: str, **values: Any
    ) -> dict[str, Any]:
        return self._record("spans", run_id, span_id, values)

    def finish(
        self,
        run_id: str,
        execution_status: str,
        verification_status: str,
        quality_passed: bool | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        report = self._read(run_id)
        if report["execution_status"] in _TERMINAL:
            return report
        complete = (
            report["completeness"]["completed"]
            == report["completeness"]["expected"]
        )
        has_error = any(
            item["error"]
            for section in (report["cases"], report["spans"])
            for item in section.values()
        )
        if execution_status != "completed" or not complete or has_error:
            quality_passed = None
        report["rubric_summary"] = self._rubric_summary(report)
        report.update(
            {
                "execution_status": execution_status,
                "verification_status": verification_status,
                "quality_passed": quality_passed,
                "error": self._redact(error),
            }
        )
        self._write(run_id, report)
        return report

    @staticmethod
    def _rubric_summary(report: dict[str, Any]) -> dict[str, Any]:
        scores = [item.get("rubric_score") for item in report.get("cases", {}).values() if item.get("rubric_score")]
        passed = sum(float(score.get("passed", 0)) for score in scores)
        total = sum(float(score.get("total", 0)) for score in scores)
        return {"cases": len(scores), "passed": passed, "total": total, "percentage": passed / total if total else 0.0}

    def set_aggregate(self, run_id: str, score: float) -> dict[str, Any]:
        report = self._read(run_id)
        report["aggregate_score"] = score
        self._write(run_id, report)
        return report

    def read(self, run_id: str) -> dict[str, Any]:
        return self._read(run_id)

    def page(self, run_id: str, page: int = 1, size: int = 10) -> dict[str, Any]:
        if page < 1 or size not in {10, 20, 50, 100}:
            raise ValueError("page must be >= 1 and size must be 10, 20, 50 or 100")
        report = self._read(run_id)
        items = list(report.get("cases", {}).items())
        start = (page - 1) * size
        total = len(items)
        pages = (total + size - 1) // size
        if page > max(pages, 1):
            raise ValueError("page is out of range")
        return {
            "schema_version": report.get("schema_version", 1),
            "run_id": report["run_id"],
            "execution_status": report["execution_status"],
            "verification_status": report["verification_status"],
            "quality_passed": report.get("quality_passed"),
            "aggregate_score": report.get("aggregate_score"),
            "rubric_summary": report.get("rubric_summary"),
            "completeness": report.get("completeness"),
            "config": report.get("config"),
            "input_snapshot": report.get("input_snapshot"),
            "questions": report.get("questions", []),
            "page": page,
            "size": size,
            "total": total,
            "pages": pages,
            "items": [
                {"case_id": case_id, **item}
                for case_id, item in items[start : start + size]
            ],
        }

    def export_xlsx(self, run_id: str) -> bytes:
        report = self._read(run_id)
        questions = report.get("questions", [])
        case_rows = [[
            "case_id", "execution_status", "verification_status",
            "quality_passed", "score", "metric_score",
            "metric_quality_passed", "rubric_passed", "rubric_total",
            "rubric_percentage", "input", "expected_output",
            "actual_output", "error",
        ]]
        judgment_rows = [[
            "case_id", "question_id", "question", "type", "answer",
            "confidence", "score", "reason", "probabilities", "raw_json",
        ]]
        for case_id, item in report.get("cases", {}).items():
            rubric = item.get("rubric_score") or {}
            raw = item.get("raw") or {}
            case_rows.append([
                case_id, item.get("execution_status"),
                item.get("verification_status"), item.get("quality_passed"),
                item.get("score"), item.get("metric_score"),
                item.get("metric_quality_passed"), rubric.get("passed"),
                rubric.get("total"), rubric.get("percentage"),
                raw.get("input"), raw.get("expected_output"),
                raw.get("actual_output"), item.get("error"),
            ])
            for question_id, result in (item.get("question_results") or {}).items():
                judgment_rows.append([
                    case_id, question_id, result.get("question"),
                    result.get("type"), result.get("answer"),
                    result.get("confidence"),
                    result.get("score", result.get("value")),
                    result.get("reason"), result.get("probabilities"),
                    self._json_text(result),
                ])
        overview = [
            ["field", "value"],
            ["run_id", report.get("run_id")],
            ["created_at", report.get("created_at")],
            ["execution_status", report.get("execution_status")],
            ["verification_status", report.get("verification_status")],
            ["quality_passed", report.get("quality_passed")],
            ["aggregate_score", report.get("aggregate_score")],
            ["rubric_summary", report.get("rubric_summary")],
            ["completeness", report.get("completeness")],
            ["total_cases", len(report.get("cases", {}))],
        ]
        question_rows = [["id", "text", "type", "weight", "true", "false"]]
        question_rows.extend([
            [q.get("id"), q.get("text"), q.get("type", "noul"),
             q.get("weight", 1.0), q.get("true"), q.get("false")]
            for q in questions
        ])
        raw_rows = [["json_path", "value_type", "value"]]
        raw_rows.extend(list(_flatten_report(report)))
        raw_json = self._json_text(report, sort_keys=True)
        raw_json_rows = [["json_chunk"]]
        raw_json_rows.extend([
            [raw_json[index : index + 32000]]
            for index in range(0, len(raw_json), 32000)
        ])
        return _xlsx({
            "Overview": overview,
            "Cases": case_rows,
            "Questions": question_rows,
            "Judgments": judgment_rows,
            "Criteria": judgment_rows,
            "Raw Report": raw_rows,
            "Raw JSON": raw_json_rows,
        })

    def latest(self) -> dict[str, Any] | None:
        paths = sorted(self._folder.glob("run_*.json"), key=self._sort_key)
        return self._read_path(paths[-1]) if paths else None

    def _record(
        self,
        section: str,
        run_id: str,
        item_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        report = self._read(run_id)
        if report["execution_status"] in _TERMINAL:
            return report
        item = report[section].get(item_id)
        if item is None:
            raise KeyError(item_id)
        item.update(
            {
                key: self._redact(value)
                for key, value in values.items()
                if key in _ITEM_FIELDS
            }
        )
        self._normalize_question_fields(report)
        self._refresh_completeness(report)
        self._write(run_id, report)
        return report

    def _refresh_completeness(self, report: dict[str, Any]) -> None:
        case_total = len(report["cases"])
        span_total = len(report["spans"])
        case_done = sum(
            item["execution_status"] == "completed"
            for item in report["cases"].values()
        )
        span_done = sum(
            item["execution_status"] == "completed"
            for item in report["spans"].values()
        )
        report["case_completeness"] = {
            "expected": case_total,
            "completed": case_done,
        }
        report["span_completeness"] = {
            "expected": span_total,
            "completed": span_done,
        }
        report["completeness"] = {
            "expected": case_total + span_total,
            "completed": case_done + span_done,
        }

    def _snapshot(self, content: Any) -> dict[str, Any] | None:
        if content is None:
            return None
        safe = self._redact(content)
        encoded = self._json_text(
            safe, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "content": safe,
        }

    def _read(self, run_id: str) -> dict[str, Any]:
        report = self._read_path(self._folder / f"run_{run_id}.json")
        self._normalize_question_fields(report)
        return report

    @staticmethod
    def _read_path(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _normalize_question_fields(report: dict[str, Any]) -> None:
        questions = report.get("questions") or []
        by_id = {
            question.get("id"): question.get("text")
            for question in questions
            if question.get("id") and isinstance(question.get("text"), str)
        }
        for item in report.get("cases", {}).values():
            results = item.get("question_results") or {}
            replacements = []
            for question_id, result in results.items():
                text = by_id.get(question_id)
                if text is None:
                    continue
                old = result.get("question")
                if isinstance(old, str) and old != text:
                    replacements.append((old, text))
                    result["question"] = text
            for index, result in enumerate(item.get("score_breakdown") or []):
                if index >= len(questions):
                    break
                text = questions[index].get("text")
                if not isinstance(text, str):
                    continue
                old = result.get("question")
                if isinstance(old, str) and old != text:
                    replacements.append((old, text))
                    result["question"] = text
            reason = item.get("reason")
            if isinstance(reason, str):
                for old, text in replacements:
                    reason = reason.replace(old, text)
                item["reason"] = reason

    def _write(self, run_id: str, report: dict[str, Any]) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        payload = self._json_text(report, indent=2) + '\n'
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._folder, delete=False
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, self._folder / f"run_{run_id}.json")
        latest = self._folder / "latest.json"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._folder, delete=False
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, latest)

    @staticmethod
    def _json_text(value: Any, **kwargs: Any) -> str:
        """Keep reports writable when input contains isolated surrogates."""
        return json.dumps(value, ensure_ascii=False, **kwargs).encode(
            "utf-8", errors="backslashreplace"
        ).decode("utf-8")

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, "***")
            return value
        if isinstance(value, dict):
            return {
                key: "***"
                if isinstance(key, str)
                and (
                    key.lower() in _SECRET_KEYS
                    or key.lower().endswith(("_token", "_key"))
                )
                else self._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value

    @staticmethod
    def _sort_key(path: Path) -> tuple[float, str]:
        return (path.stat().st_mtime, path.name)


def _flatten_report(value: Any, path: str = "$") -> list[tuple[str, str, Any]]:
    if isinstance(value, dict):
        if not value:
            return [(path, "object", "{}")]
        rows = []
        for key, item in value.items():
            rows.extend(_flatten_report(item, f"{path}.{key}"))
        return rows
    if isinstance(value, list):
        if not value:
            return [(path, "array", "[]")]
        rows = []
        for index, item in enumerate(value):
            rows.extend(_flatten_report(item, f"{path}[{index}]"))
        return rows
    kind = "null" if value is None else type(value).__name__
    return [(path, kind, value)]


def _xlsx_text(value: Any) -> str:
    text = str(value).encode("utf-8", errors="backslashreplace").decode(
        "utf-8"
    )
    text = "".join(
        char
        for char in text
        if char in "\t\n\r"
        or not (ord(char) < 32)
    )[:32767]
    if text.startswith(("=", "+", "-", "@")):
        text = "'" + text
    return escape(text)


def _xlsx(sheets: dict[str, list[list[Any]]]) -> bytes:
    def cell(value: Any, row: int, col: int) -> str:
        ref = ""
        n = col
        while n:
            n, rem = divmod(n - 1, 26)
            ref = chr(65 + rem) + ref
        ref += str(row)
        if value is None:
            return f"<c r=\"{ref}\"/>"
        if isinstance(value, bool):
            return f"<c r=\"{ref}\" t=\"b\"><v>{1 if value else 0}</v></c>"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"<c r=\"{ref}\"><v>{value}</v></c>"
        text = _xlsx_text(value)
        return f"<c r=\"{ref}\" t=\"inlineStr\"><is><t>{text}</t></is></c>"

    def sheet(rows):
        body = "".join(f"<row r=\"{r}\">{''.join(cell(v, r, c) for c, v in enumerate(row, 1))}</row>" for r, row in enumerate(rows, 1))
        return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>{body}</sheetData></worksheet>"

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>" + "".join(f"<Override PartName=\"/xl/worksheets/sheet{i}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>" for i in range(1, len(sheets)+1)) + "</Types>")
        archive.writestr("_rels/.rels", "<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>")
        names = list(sheets)
        archive.writestr("xl/workbook.xml", "<?xml version=\"1.0\"?><workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>" + "".join(f"<sheet name=\"{escape(name)}\" sheetId=\"{i}\" r:id=\"rId{i}\"/>" for i, name in enumerate(names, 1)) + "</sheets></workbook>")
        archive.writestr("xl/_rels/workbook.xml.rels", "<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">" + "".join(f"<Relationship Id=\"rId{i}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet{i}.xml\"/>" for i in range(1, len(names)+1)) + "</Relationships>")
        for i, name in enumerate(names, 1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", sheet(sheets[name]))
    return output.getvalue()
