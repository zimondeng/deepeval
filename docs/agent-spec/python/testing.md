<!-- agent-spec:generated -->
# Python testing

## Scope

Pytest configuration in `pyproject.toml` and the workflows `.github/workflows/test_core.yml`, `.github/workflows/test_metrics.yml`, and `.github/workflows/test_integrations.yml`.

## Rules

### Rule 1: Pytest skips skip_test, isolates dotenv, and uses asyncio auto mode

Status: Explicit
Confidence: High

Description:
Default pytest addopts use -m 'not skip_test'. The skip_test marker means skip the test. The enable_dotenv marker is what allows a test to load .env files via autoload_dotenv(). asyncio_mode is set so async tests run in auto mode.

Evidence:
- `pyproject.toml` "-m 'not skip_test'"
- `pyproject.toml` "skip_test: skip the test"
- `pyproject.toml` "enable_dotenv: allow this test to load .env files via autoload_dotenv()"
- `pyproject.toml` "asyncio_mode = "

Preferred pattern:
Mark a test skip_test to keep it out of the default run. Do not load a dotenv file unless the test is marked enable_dotenv.

Exceptions:
none found

Verification:
poetry run pytest

### Rule 2: CI runs core, metric, and integration tests as separate pytest trees

Status: Observed
Confidence: High

Description:
Three workflows invoke poetry run pytest on different trees: core tests, metric tests, and integration tests. Integration jobs go one directory deeper, for example the langchain integration tests.

Evidence:
- `.github/workflows/test_core.yml`
- `.github/workflows/test_metrics.yml`
- `.github/workflows/test_integrations.yml`

Preferred pattern:
Put a new test in the existing tree for that area and run it with pytest. Core behavior goes with the core workflow, metric scoring with the metrics workflow, and a framework adapter with the integrations workflow.

Exceptions:
The core workflow does not run the synthesizer and datasets suites in the same step as the rest of core. It runs those paths in a later step. See `.github/workflows/test_core.yml`.

Verification:
poetry run pytest, scoped to the tree you changed. CI uses poetry.

## Observations

`tests/test_metrics/test_faithfulness_metric.py` and `tests/test_metrics/test_bias_metric.py` are the metric-suite counterparts of the two judge metrics in the architecture spec. One pair of test files is not a naming rule.
