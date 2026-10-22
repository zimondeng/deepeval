<!-- agent-spec:generated -->
# Python conventions

## Scope

The root Python package declared in `pyproject.toml`. Formatter and linter config is also in `.pre-commit-config.yaml`.

## Rules

### Rule 1: Install Python dependencies with Poetry

Status: Explicit
Confidence: High

Description:
Poetry is the dependency installer for this package. The build backend is poetry-core, named in `pyproject.toml`.

Evidence:
- `CONTRIBUTING.md` "We recommend using Poetry to install dependencies."
- `pyproject.toml` "build-backend = "

Preferred pattern:
Create a virtualenv and run poetry install, as `CONTRIBUTING.md` describes.

Exceptions:
none found

Verification:
poetry install

### Rule 2: Black line length is 80

Status: Explicit
Confidence: High

Description:
Black formats Python to line-length 80. The setting lives under tool.black in `pyproject.toml`. Pre-commit runs the black hook.

Evidence:
- `pyproject.toml` "[tool.black]"
- `pyproject.toml` "line-length = 80"
- `.pre-commit-config.yaml` "id: black"

Preferred pattern:
Format Python with Black at line length 80 before a pull request.

Exceptions:
none found

Verification:
pre-commit runs the black hook. `.github/workflows/black.yml` runs Black on pull requests that are not limited to the TypeScript tree.

### Rule 3: Ruff uses line length 80 and auto-fix in pre-commit

Status: Explicit
Confidence: High

Description:
Ruff uses line-length 80 under tool.ruff and the pre-commit hook id is ruff. Its comment says it will auto-fix lint issues.

Evidence:
- `pyproject.toml` "[tool.ruff]"
- `pyproject.toml` "line-length = 80"
- `.pre-commit-config.yaml` "id: ruff"
- `.pre-commit-config.yaml` "auto-fix lint issues"

Preferred pattern:
Let Ruff fix lint issues. Keep the line length at 80.

Exceptions:
none found

Verification:
The pre-commit hook runs ruff with --fix. No separate Ruff CI workflow was found.

### Rule 4: Mypy strict is only the telemetry package

Status: Explicit
Confidence: High

Description:
Mypy strict, with ignore-missing-imports, is scoped to the telemetry package on purpose. The hook files path is deepeval/telemetry. No free strings are allowed to reach an analytics backend, and that only holds if it is checked.

Evidence:
- `.pre-commit-config.yaml` "Scoped to the telemetry package on purpose: no free strings are allowed to"
- `.pre-commit-config.yaml` "reach an analytics backend, and that only holds if it is checked."
- `.pre-commit-config.yaml` "files: ^deepeval/telemetry/"
- `.pre-commit-config.yaml` "[--strict, --ignore-missing-imports]"

Preferred pattern:
Do not expand this mypy hook past the telemetry package named in the hook. The comment says repo-wide strict typing is a separate project.

Exceptions:
none found

Verification:
pre-commit hook named mypy (telemetry)

## Observations

`CONTRIBUTING.md` says contributors optionally run Black. `.github/workflows/black.yml` runs Black with a check on pull requests, and `.pre-commit-config.yaml` runs the black hook. The line-length rule above still holds. Do not treat the word optionally as permission to skip Black on a pull request.

`pyproject.toml` depends on Ruff ^0.13.0. `.pre-commit-config.yaml` pins astral-sh/ruff-pre-commit at rev v0.6.9. Both are live. This spec does not pick a version.
