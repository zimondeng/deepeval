<!-- agent-spec:generated -->
# Python package architecture

## Scope

The installable package rooted at `deepeval/__init__.py`. Console script and pytest plugin registration are in `pyproject.toml`.

## Layout

These entry files are the boundaries this package actually ships. This list is a map, not a rule that every feature needs a new top-level package.

- CLI: `deepeval/cli/__init__.py`
- Metrics: `deepeval/metrics/__init__.py`
- Test cases: `deepeval/test_case/__init__.py`
- Datasets: `deepeval/dataset/__init__.py`
- Tracing: `deepeval/tracing/__init__.py`
- Models: `deepeval/models/__init__.py`
- Confident API client: `deepeval/confident/__init__.py`
- Framework integrations: `deepeval/integrations/__init__.py`

## Rules

### Rule 1: The console script and the pytest plugin are registered in pyproject.toml

Status: Explicit
Confidence: High

Description:
The deepeval console script loads deepeval.cli.main:app. The pytest11 plugin module is deepeval.plugins.plugin

Evidence:
- `pyproject.toml` "deepeval = 'deepeval.cli.main:app'"
- `pyproject.toml` "deepeval.plugins.plugin"

Preferred pattern:
Keep the public CLI on that module path. Register pytest integration through the pytest11 entry in `pyproject.toml`.

Exceptions:
none found

Verification:
not specified

### Rule 2: Built-in judge metrics use a local schema and make_template_class

Status: Observed
Confidence: Medium

Description:
Faithfulness and bias subclass BaseMetric, import their verdict models from a sibling schema module, and build the prompt class with make_template_class from deepeval.templates.

Evidence:
- `deepeval/metrics/faithfulness/faithfulness.py`
- `deepeval/metrics/bias/bias.py`

Preferred pattern:
For a new built-in judge metric, add the metric module and a schema module, and call make_template_class. Do not add a local template module unless you are matching the citation metric called out below.

Exceptions:
`deepeval/metrics/community/citation_faithfulness/citation_faithfulness.py` imports a local template module and does not call make_template_class. `deepeval/metrics/agent_loop_detection/agent_loop_detection.py` and `deepeval/metrics/tool_permission/tool_permission.py` ship without a schema module.

Verification:
not specified

## Observations

`CONTRIBUTING.md` says new metrics land under the community package, are not exported from deepeval.metrics, and use a folder with the metric class, a schema module, and a template module. `docs/content/docs/(community)/community-metrics-overview.mdx` repeats that community metrics are not exported from deepeval.metrics.

The code does not match that for two metrics. `deepeval/metrics/__init__.py` exports ToolPermissionMetric and AgentLoopDetectionMetric from `deepeval/metrics/tool_permission/tool_permission.py` and `deepeval/metrics/agent_loop_detection/agent_loop_detection.py`. Their doc pages still sit under the community docs folder. The only template module under the metrics tree is `deepeval/metrics/community/citation_faithfulness/template.py`.

Do not pick a winner from this spec. Read the metric you are editing and match that metric's neighbors.
