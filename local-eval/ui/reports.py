"""Atomic, canonical reports for local evaluation runs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
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
    ) -> dict[str, Any]:
        report = {
            "schema_version": 1,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "execution_status": "queued",
            "verification_status": "not_verified",
            "quality_passed": None,
            "config": self._redact(config),
            "input_snapshot": self._snapshot(snapshot),
            "cases": {
                item["id"]: dict(_ITEM_DEFAULTS)
                for item in cases
                if isinstance(item.get("id"), str)
            },
            "spans": {
                item["id"]: dict(_ITEM_DEFAULTS)
                for item in (spans or [])
                if isinstance(item.get("id"), str)
            },
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
                key: self._redact(value) if key == "error" else value
                for key, value in values.items()
                if key in _ITEM_FIELDS
            }
        )
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
        encoded = json.dumps(
            safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "content": safe,
        }

    def _read(self, run_id: str) -> dict[str, Any]:
        return self._read_path(self._folder / f"run_{run_id}.json")

    @staticmethod
    def _read_path(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, run_id: str, report: dict[str, Any]) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
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

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, "***")
            return value
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value

    @staticmethod
    def _sort_key(path: Path) -> tuple[float, str]:
        return (path.stat().st_mtime, path.name)
