# ADR 0001: Uploaded dataset snapshots and versioned reports

- Status: Accepted
- Date: 2026-10-23

## Context

The local evaluation console needs to evaluate a user-selected golden dataset,
retain the original inputs for review, and show question-level Jev results
without reading arbitrary JSONL files from the project tree. Reports must remain
readable after the temporary upload is removed.

## Decision

Each execution accepts a JSONL upload and freezes a sanitized dataset and
question configuration into its report snapshot. The temporary upload is
removed after parsing and is never treated as a project dataset path. New
reports use schema version 2 and expose immutable, input-order pagination.
Credentials are excluded from snapshots and reports.

## Consequences

- A run is reproducible from its report snapshot without retaining the upload.
- Upload validation happens before execution and rejects path-based datasets.
- Historical reports remain readable, but question-level results are not
  reconstructed when they were not recorded.
- Report storage grows with the retained sanitized dataset and results.
